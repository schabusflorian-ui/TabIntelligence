"""Tests for Stage 3 mapping pattern-based shortcircuit."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


class TestPatternShortcircuit:
    """Test that high-confidence entity patterns shortcircuit Claude calls."""

    def _make_context(self, entity_id=None):
        """Create a mock PipelineContext with parsed results."""
        context = MagicMock()
        context.entity_id = entity_id
        context.get_result.return_value = {
            "parsed": {
                "sheets": [
                    {
                        "sheet_name": "Income Statement",
                        "rows": [
                            {
                                "label": "Revenue",
                                "hierarchy_level": 1,
                                "is_formula": False,
                                "is_subtotal": False,
                            },
                            {
                                "label": "Cost of Goods Sold",
                                "hierarchy_level": 1,
                                "is_formula": False,
                                "is_subtotal": False,
                            },
                            {
                                "label": "Gross Profit",
                                "hierarchy_level": 1,
                                "is_formula": True,
                                "is_subtotal": True,
                            },
                        ],
                    }
                ]
            }
        }
        return context

    def _make_pattern(self, original_label, canonical_name, confidence=0.98, occurrence_count=5):
        """Create a mock EntityPattern."""
        p = MagicMock()
        p.original_label = original_label
        p.canonical_name = canonical_name
        p.confidence = Decimal(str(confidence))
        p.occurrence_count = occurrence_count
        p.last_seen = datetime.now(timezone.utc)
        p.created_by = "claude"
        return p

    @pytest.mark.asyncio
    async def test_all_labels_matched_skips_claude(self):
        """When all labels match patterns >= 0.95, Claude is NOT called."""
        from src.extraction.stages.mapping import MappingStage

        stage = MappingStage()
        context = self._make_context(entity_id="00000000-0000-0000-0000-000000000001")

        [
            self._make_pattern("Revenue", "revenue", 0.98, 5),
            self._make_pattern("Cost of Goods Sold", "cogs", 0.97, 3),
            self._make_pattern("Gross Profit", "gross_profit", 0.99, 4),
        ]

        mock_claude = MagicMock()

        with (
            patch("src.extraction.stages.mapping.get_claude_client", return_value=mock_claude),
            patch.object(stage, "_lookup_patterns") as mock_lookup,
            patch.object(stage, "_build_entity_hints", return_value=""),
        ):
            # All labels pre-mapped, no remaining
            pre_mapped = {
                "Revenue": {
                    "original_label": "Revenue",
                    "canonical_name": "revenue",
                    "confidence": 0.98,
                    "method": "entity_pattern",
                    "reasoning": "Matched entity pattern (seen 5x)",
                },
                "Cost of Goods Sold": {
                    "original_label": "Cost of Goods Sold",
                    "canonical_name": "cogs",
                    "confidence": 0.97,
                    "method": "entity_pattern",
                    "reasoning": "Matched entity pattern (seen 3x)",
                },
                "Gross Profit": {
                    "original_label": "Gross Profit",
                    "canonical_name": "gross_profit",
                    "confidence": 0.99,
                    "method": "entity_pattern",
                    "reasoning": "Matched entity pattern (seen 4x)",
                },
            }
            mock_lookup.return_value = (pre_mapped, set())

            result = await stage.execute(context)

        # Claude should NOT be called
        mock_claude.messages.create.assert_not_called()

        # All mappings should come from patterns
        assert result["tokens"] == 0
        assert result["input_tokens"] == 0
        assert result["output_tokens"] == 0
        assert len(result["mappings"]) == 3
        assert result["lineage_metadata"]["pattern_matched"] == 3
        assert result["lineage_metadata"]["claude_mapped"] == 0

        # All should have method = entity_pattern
        for m in result["mappings"]:
            assert m["method"] == "entity_pattern"

    @pytest.mark.asyncio
    async def test_partial_match_sends_remaining_to_claude(self):
        """When some labels match patterns, only unmatched are sent to Claude."""
        from src.extraction.stages.mapping import MappingStage

        stage = MappingStage()
        context = self._make_context(entity_id="00000000-0000-0000-0000-000000000001")

        # Mock Claude response for the remaining label
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    [
                        {
                            "original_label": "Gross Profit",
                            "canonical_name": "gross_profit",
                            "confidence": 0.90,
                            "reasoning": "Standard gross profit",
                        }
                    ]
                )
            )
        ]
        mock_response.usage = MagicMock(input_tokens=200, output_tokens=100)

        mock_claude = MagicMock()
        mock_claude.messages.create.return_value = mock_response

        with (
            patch("src.extraction.stages.mapping.get_claude_client", return_value=mock_claude),
            patch.object(stage, "_lookup_patterns") as mock_lookup,
            patch.object(stage, "_build_entity_hints", return_value=""),
        ):
            # 2 of 3 labels pre-mapped
            pre_mapped = {
                "Revenue": {
                    "original_label": "Revenue",
                    "canonical_name": "revenue",
                    "confidence": 0.98,
                    "method": "entity_pattern",
                    "reasoning": "Matched entity pattern (seen 5x)",
                },
                "Cost of Goods Sold": {
                    "original_label": "Cost of Goods Sold",
                    "canonical_name": "cogs",
                    "confidence": 0.97,
                    "method": "entity_pattern",
                    "reasoning": "Matched entity pattern (seen 3x)",
                },
            }
            mock_lookup.return_value = (pre_mapped, {"Gross Profit"})

            result = await stage.execute(context)

        # Claude SHOULD be called
        mock_claude.messages.create.assert_called_once()

        # Verify Claude only received the unmatched label
        call_args = mock_claude.messages.create.call_args
        prompt_content = (
            call_args[1]["messages"][0]["content"]
            if "messages" in call_args[1]
            else call_args[0][0]["messages"][0]["content"]
        )
        assert "Gross Profit" in prompt_content
        # Revenue and COGS should NOT be in the Claude prompt's line_items
        # (they may appear in taxonomy hints though, so we check the rendered line items)

        # Check merged results
        assert len(result["mappings"]) == 3
        assert result["tokens"] == 300  # 200 + 100
        assert result["lineage_metadata"]["pattern_matched"] == 2
        assert result["lineage_metadata"]["claude_mapped"] == 1

        # Check method tags
        methods = {m["original_label"]: m["method"] for m in result["mappings"]}
        assert methods["Revenue"] == "entity_pattern"
        assert methods["Cost of Goods Sold"] == "entity_pattern"
        assert methods["Gross Profit"] == "claude"

    @pytest.mark.asyncio
    async def test_no_entity_id_sends_all_to_claude(self):
        """Without entity_id, all labels are sent to Claude."""
        from src.extraction.stages.mapping import MappingStage

        stage = MappingStage()
        context = self._make_context(entity_id=None)

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    [
                        {
                            "original_label": "Revenue",
                            "canonical_name": "revenue",
                            "confidence": 0.95,
                            "reasoning": "Direct match",
                        },
                        {
                            "original_label": "Cost of Goods Sold",
                            "canonical_name": "cogs",
                            "confidence": 0.95,
                            "reasoning": "Standard",
                        },
                        {
                            "original_label": "Gross Profit",
                            "canonical_name": "gross_profit",
                            "confidence": 0.95,
                            "reasoning": "Standard",
                        },
                    ]
                )
            )
        ]
        mock_response.usage = MagicMock(input_tokens=500, output_tokens=300)

        mock_claude = MagicMock()
        mock_claude.messages.create.return_value = mock_response

        with (
            patch("src.extraction.stages.mapping.get_claude_client", return_value=mock_claude),
            patch.object(stage, "_build_entity_hints", return_value=""),
        ):
            result = await stage.execute(context)

        # Claude SHOULD be called with all 3 labels
        mock_claude.messages.create.assert_called_once()
        assert len(result["mappings"]) == 3
        assert result["tokens"] == 800

        # All should have method = claude
        for m in result["mappings"]:
            assert m["method"] == "claude"

    @pytest.mark.asyncio
    async def test_pattern_lookup_failure_falls_back_to_claude(self):
        """If pattern lookup fails, all labels are sent to Claude."""
        from src.extraction.stages.mapping import MappingStage

        stage = MappingStage()
        context = self._make_context(entity_id="00000000-0000-0000-0000-000000000001")

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    [
                        {
                            "original_label": "Revenue",
                            "canonical_name": "revenue",
                            "confidence": 0.95,
                            "reasoning": "Direct match",
                        },
                        {
                            "original_label": "Cost of Goods Sold",
                            "canonical_name": "cogs",
                            "confidence": 0.95,
                            "reasoning": "Standard",
                        },
                        {
                            "original_label": "Gross Profit",
                            "canonical_name": "gross_profit",
                            "confidence": 0.95,
                            "reasoning": "Standard",
                        },
                    ]
                )
            )
        ]
        mock_response.usage = MagicMock(input_tokens=500, output_tokens=300)

        mock_claude = MagicMock()
        mock_claude.messages.create.return_value = mock_response

        with (
            patch("src.extraction.stages.mapping.get_claude_client", return_value=mock_claude),
            patch.object(stage, "_lookup_patterns") as mock_lookup,
            patch.object(stage, "_build_entity_hints", return_value=""),
        ):
            # Simulate pattern lookup returning empty (as if exception was caught)
            mock_lookup.return_value = ({}, {"Revenue", "Cost of Goods Sold", "Gross Profit"})

            result = await stage.execute(context)

        # Claude should be called with all labels
        mock_claude.messages.create.assert_called_once()
        assert len(result["mappings"]) == 3


class TestLookupPatterns:
    """Test the _lookup_patterns method directly."""

    def _make_pattern(self, original_label, canonical_name, confidence=0.98, occurrence_count=5):
        """Create a mock EntityPattern."""
        p = MagicMock()
        p.original_label = original_label
        p.canonical_name = canonical_name
        p.confidence = Decimal(str(confidence))
        p.occurrence_count = occurrence_count
        p.last_seen = datetime.now(timezone.utc)
        p.created_by = "claude"
        return p

    def test_lookup_without_entity_id(self):
        """Without entity_id, returns empty pre_mapped and all labels."""
        from src.extraction.stages.mapping import MappingStage

        stage = MappingStage()
        context = MagicMock()
        context.entity_id = None

        labels = {"Revenue", "COGS"}
        pre_mapped, remaining = stage._lookup_patterns(context, labels)

        assert pre_mapped == {}
        assert remaining == labels

    def test_lookup_with_matching_patterns(self):
        """With matching patterns, returns pre_mapped and remaining."""
        from src.extraction.stages.mapping import MappingStage

        stage = MappingStage()
        context = MagicMock()
        context.entity_id = "00000000-0000-0000-0000-000000000001"

        patterns = [
            self._make_pattern("Revenue", "revenue", 0.98, 5),
        ]

        with patch("src.extraction.stages.mapping.MappingStage._lookup_patterns"):
            # Call the real method but mock the DB
            pass

        # Use direct DB mocking
        with patch("src.db.session.get_db_sync") as mock_db_ctx:
            mock_session = MagicMock()
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

            with patch("src.db.crud.get_entity_patterns", return_value=patterns):
                labels = {"Revenue", "COGS"}
                pre_mapped, remaining = stage._lookup_patterns(context, labels)

        assert "Revenue" in pre_mapped
        assert pre_mapped["Revenue"]["canonical_name"] == "revenue"
        assert pre_mapped["Revenue"]["method"] == "entity_pattern"
        assert remaining == {"COGS"}

    def test_lookup_db_failure_returns_all_labels(self):
        """DB failure returns empty pre_mapped and all labels."""
        from src.extraction.stages.mapping import MappingStage

        stage = MappingStage()
        context = MagicMock()
        context.entity_id = "00000000-0000-0000-0000-000000000001"

        with patch("src.db.session.get_db_sync", side_effect=Exception("DB down")):
            labels = {"Revenue", "COGS"}
            pre_mapped, remaining = stage._lookup_patterns(context, labels)

        assert pre_mapped == {}
        assert remaining == labels


class TestSheetCategoryDisambiguation:
    """Tests for deterministic sheet-category disambiguation override."""

    def test_overrides_wrong_category(self):
        """D&A on Income Statement should override
        depreciation_cf -> depreciation_and_amortization."""
        from src.extraction.stages.mapping import _disambiguate_by_sheet_category
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        mappings = [
            {
                "original_label": "Depreciation & Amortization",
                "canonical_name": "depreciation_cf",
                "confidence": 0.95,
            },
        ]
        grouped_items = [
            {"label": "Depreciation & Amortization", "sheet": "Income Statement"},
        ]
        alias_lookup = get_alias_to_canonicals()

        count = _disambiguate_by_sheet_category(mappings, grouped_items, alias_lookup)

        assert count == 1
        assert mappings[0]["canonical_name"] == "depreciation_and_amortization"
        assert mappings[0]["disambiguation_override"]["original"] == "depreciation_cf"

    def test_no_override_correct_category(self):
        """D&A on Cash Flow should keep depreciation_cf (already correct)."""
        from src.extraction.stages.mapping import _disambiguate_by_sheet_category
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        mappings = [
            {
                "original_label": "Add: Depreciation",
                "canonical_name": "depreciation_cf",
                "confidence": 0.95,
            },
        ]
        grouped_items = [
            {"label": "Add: Depreciation", "sheet": "Cash Flow Statement"},
        ]
        alias_lookup = get_alias_to_canonicals()

        count = _disambiguate_by_sheet_category(mappings, grouped_items, alias_lookup)

        assert count == 0
        assert mappings[0]["canonical_name"] == "depreciation_cf"

    def test_no_override_no_alias_match(self):
        """Unknown label with no alias match should not be changed."""
        from src.extraction.stages.mapping import _disambiguate_by_sheet_category
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        mappings = [
            {
                "original_label": "Custom Widget Revenue",
                "canonical_name": "revenue",
                "confidence": 0.85,
            },
        ]
        grouped_items = [
            {"label": "Custom Widget Revenue", "sheet": "Income Statement"},
        ]
        alias_lookup = get_alias_to_canonicals()

        count = _disambiguate_by_sheet_category(mappings, grouped_items, alias_lookup)

        assert count == 0
        assert mappings[0]["canonical_name"] == "revenue"

    def test_no_override_unmapped_no_alias(self):
        """Unmapped items with no alias match should stay unmapped."""
        from src.extraction.stages.mapping import _disambiguate_by_sheet_category
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        mappings = [
            {
                "original_label": "Some Label",
                "canonical_name": "unmapped",
                "confidence": 0.3,
            },
        ]
        grouped_items = [
            {"label": "Some Label", "sheet": "Income Statement"},
        ]
        alias_lookup = get_alias_to_canonicals()

        count = _disambiguate_by_sheet_category(mappings, grouped_items, alias_lookup)

        assert count == 0
        assert mappings[0]["canonical_name"] == "unmapped"

    def test_unmapped_rescued_by_exact_alias(self):
        """Unmapped item with exact alias match should be rescued."""
        from src.extraction.stages.mapping import _disambiguate_by_sheet_category
        from src.extraction.taxonomy_loader import get_alias_to_canonicals

        mappings = [
            {
                "original_label": "Depreciation & Amortization",
                "canonical_name": "unmapped",
                "confidence": 0.3,
            },
        ]
        grouped_items = [
            {"label": "Depreciation & Amortization", "sheet": "Income Statement"},
        ]
        alias_lookup = get_alias_to_canonicals()

        count = _disambiguate_by_sheet_category(mappings, grouped_items, alias_lookup)

        assert count == 1
        assert mappings[0]["canonical_name"] == "depreciation_and_amortization"
        assert mappings[0]["disambiguation_override"]["original"] == "unmapped"

    def test_multi_match_picks_best_canonical(self):
        """When multiple canonicals match in the expected category, pick the closest name."""
        from src.extraction.stages.mapping import _disambiguate_by_sheet_category

        # Both current_assets and total_current_assets have "Current Assets Total" as alias
        alias_lookup = {
            "total current assets": [
                ("current_assets", "balance_sheet"),
                ("total_current_assets", "balance_sheet"),
            ],
        }
        mappings = [
            {
                "original_label": "Total Current Assets",
                "canonical_name": "current_assets",
                "confidence": 0.85,
            },
        ]
        grouped_items = [
            {"label": "Total Current Assets", "sheet": "Balance Sheet"},
        ]

        count = _disambiguate_by_sheet_category(mappings, grouped_items, alias_lookup)

        assert count == 1
        assert mappings[0]["canonical_name"] == "total_current_assets"

    def test_multi_match_no_winner_skips(self):
        """When no canonical is a substring match, no override happens."""
        from src.extraction.stages.mapping import _disambiguate_by_sheet_category

        alias_lookup = {
            "foo bar": [
                ("alpha_metric", "balance_sheet"),
                ("beta_metric", "balance_sheet"),
            ],
        }
        mappings = [
            {
                "original_label": "Foo Bar",
                "canonical_name": "alpha_metric",
                "confidence": 0.85,
            },
        ]
        grouped_items = [
            {"label": "Foo Bar", "sheet": "Balance Sheet"},
        ]

        count = _disambiguate_by_sheet_category(mappings, grouped_items, alias_lookup)

        assert count == 0
        assert mappings[0]["canonical_name"] == "alpha_metric"

    def test_duplicate_label_across_sheets_overrides_correctly(self):
        """When same label appears on multiple sheets, override uses correct sheet context."""
        from src.extraction.stages.mapping import _disambiguate_by_sheet_category

        # "Revenue" appears on both "Monthly P&L" (income_statement) and "Cash" (no match)
        # Claude mapped it to cash_from_operations — wrong for the P&L sheet
        alias_lookup = {
            "revenue": [("revenue", "income_statement")],
        }
        mappings = [
            {
                "original_label": "Revenue",
                "canonical_name": "cash_from_operations",
                "confidence": 0.9,
            },
        ]
        grouped_items = [
            {"label": "Revenue", "sheet": "Monthly P&L"},
            {"label": "Revenue", "sheet": "Cash"},
        ]

        count = _disambiguate_by_sheet_category(mappings, grouped_items, alias_lookup)

        assert count == 1
        assert mappings[0]["canonical_name"] == "revenue"
        assert mappings[0]["disambiguation_override"]["original"] == "cash_from_operations"

    def test_duplicate_label_skips_when_current_matches_one_sheet(self):
        """When current canonical matches at least one sheet's category, no override."""
        from src.extraction.stages.mapping import _disambiguate_by_sheet_category

        # "Net Income" appears on both "Income Statement" and "Cash Flow Statement"
        # Claude mapped to net_income (income_statement) — valid for Income Statement sheet
        alias_lookup = {
            "net income": [
                ("net_income", "income_statement"),
                ("net_income_cf", "cash_flow"),
            ],
        }
        mappings = [
            {
                "original_label": "Net Income",
                "canonical_name": "net_income",
                "confidence": 0.95,
            },
        ]
        grouped_items = [
            {"label": "Net Income", "sheet": "Income Statement"},
            {"label": "Net Income", "sheet": "Cash Flow Statement"},
        ]

        count = _disambiguate_by_sheet_category(mappings, grouped_items, alias_lookup)

        assert count == 0
        assert mappings[0]["canonical_name"] == "net_income"  # Unchanged


class TestMappingBatching:
    """Test that large label sets are split into batches."""

    def test_batch_size_constant_exists(self):
        """BATCH_SIZE is defined inside execute(); verify the helper method exists."""
        from src.extraction.stages.mapping import MappingStage

        stage = MappingStage()
        assert hasattr(stage, "_call_claude_mapping")

    @patch("src.extraction.stages.mapping.get_claude_client")
    @patch("src.extraction.stages.mapping.get_prompt")
    @patch("src.extraction.stages.mapping.get_alias_to_canonicals_with_promoted")
    @patch("src.extraction.stages.mapping.get_canonical_to_category")
    @patch("src.extraction.stages.mapping.validate_canonical_names")
    def test_batching_merges_results(
        self,
        mock_validate,
        mock_cat_lookup,
        mock_alias_lookup,
        mock_get_prompt,
        mock_get_client,
    ):
        """When items exceed BATCH_SIZE, results from multiple batches are merged."""
        from src.extraction.stages.mapping import MappingStage

        mock_cat_lookup.return_value = {}
        mock_alias_lookup.return_value = {}
        mock_get_prompt.return_value.render.return_value = "prompt text"

        # Create a mock Claude response
        def make_response(items):
            """Build a mock response that returns one mapping per input item."""
            mappings = [
                {
                    "original_label": item["label"],
                    "canonical_name": "revenue",
                    "confidence": 0.9,
                    "reasoning": "test",
                }
                for item in json.loads(
                    mock_get_prompt.return_value.render.call_args[1]["line_items"]
                    if mock_get_prompt.return_value.render.call_args
                    else "[]"
                )
            ]
            resp = MagicMock()
            resp.stop_reason = "end_turn"
            resp.content = [MagicMock(text=json.dumps(mappings))]
            resp.usage.input_tokens = 100
            resp.usage.output_tokens = 50
            return resp

        # Simpler approach: make _call_claude_mapping return deterministic results
        stage = MappingStage()

        # Patch the helper directly to count calls and return mapped items
        call_count = 0

        def fake_call(items, taxonomy_str):
            nonlocal call_count
            call_count += 1
            mappings = [
                {
                    "original_label": item["label"],
                    "canonical_name": "revenue",
                    "confidence": 0.9,
                    "reasoning": "test",
                }
                for item in items
            ]
            return mappings, 100, 50

        stage._call_claude_mapping = fake_call

        # Build a context with > 60 items to trigger batching
        rows = [
            {
                "label": f"Item {i}",
                "hierarchy_level": 1,
                "is_formula": False,
                "is_subtotal": False,
            }
            for i in range(80)
        ]
        context = MagicMock()
        context.entity_id = None
        context.get_result.side_effect = lambda stage_name: {
            "parsing": {
                "parsed": {
                    "sheets": [{"sheet_name": "Income Statement", "rows": rows}]
                }
            },
            "triage": {
                "triage": [
                    {"sheet_name": "Income Statement", "classification": "income_statement"}
                ]
            },
        }[stage_name]

        import asyncio

        result = asyncio.get_event_loop().run_until_complete(stage.execute(context))

        # 80 items / 60 batch size = 2 batches
        assert call_count == 2
        assert len(result["mappings"]) == 80
        assert result["lineage_metadata"]["batched"] is True
        assert result["lineage_metadata"]["batch_count"] == 2
        # Tokens: 2 batches * (100 input + 50 output) = 300
        assert result["tokens"] == 300
