"""
End-to-end tests for the full 5-stage extraction pipeline.

Validates that all stages execute correctly, produce expected results,
and that lineage, metrics, and data flow work across the entire pipeline.
"""
import pytest

from src.extraction.orchestrator import extract
from src.extraction.registry import registry


class TestFullPipelineExecution:
    """Test the complete 5-stage pipeline end-to-end."""

    @pytest.mark.asyncio
    async def test_all_five_stages_registered(self):
        """All 5 extraction stages must be registered."""
        pipeline = registry.get_pipeline()
        stage_names = [s.name for s in pipeline]

        assert len(pipeline) == 5
        assert stage_names == [
            "parsing", "triage", "mapping", "validation", "enhanced_mapping"
        ]

    @pytest.mark.asyncio
    async def test_stage_numbers_sequential(self):
        """Stage numbers must be 1-5 in order."""
        pipeline = registry.get_pipeline()
        assert [s.stage_number for s in pipeline] == [1, 2, 3, 4, 5]

    @pytest.mark.asyncio
    async def test_pipeline_returns_all_required_keys(self, mock_anthropic, sample_xlsx):
        """Pipeline result must contain all required top-level keys."""
        result = await extract(sample_xlsx, file_id="e2e-test-1")

        required_keys = {
            "file_id", "sheets", "triage", "line_items",
            "tokens_used", "cost_usd", "job_id",
            "validation", "lineage_summary", "final_lineage_id",
        }
        assert required_keys.issubset(result.keys())

    @pytest.mark.asyncio
    async def test_pipeline_file_id_preserved(self, mock_anthropic, sample_xlsx):
        """file_id passed to extract() must appear in result."""
        result = await extract(sample_xlsx, file_id="my-file-id-42")
        assert result["file_id"] == "my-file-id-42"

    @pytest.mark.asyncio
    async def test_pipeline_generates_job_id(self, mock_anthropic, sample_xlsx):
        """Pipeline must generate a UUID job_id if none provided."""
        result = await extract(sample_xlsx, file_id="e2e-test-2")
        assert result["job_id"] is not None
        # UUID format: 8-4-4-4-12 hex chars
        parts = result["job_id"].split("-")
        assert len(parts) == 5

    @pytest.mark.asyncio
    async def test_pipeline_uses_provided_job_id(self, mock_anthropic, sample_xlsx):
        """Pipeline must use the job_id when explicitly provided."""
        result = await extract(
            sample_xlsx, file_id="e2e-test-3", job_id="custom-job-123"
        )
        assert result["job_id"] == "custom-job-123"


class TestLineageTracking:
    """Test lineage tracking across all 5 stages."""

    @pytest.mark.asyncio
    async def test_lineage_summary_present(self, mock_anthropic, sample_xlsx):
        """Lineage summary must be present in result."""
        result = await extract(sample_xlsx, file_id="lineage-test-1")

        summary = result["lineage_summary"]
        assert summary is not None
        assert "total_events" in summary
        assert "stages" in summary
        assert "event_types" in summary

    @pytest.mark.asyncio
    async def test_lineage_covers_all_stages(self, mock_anthropic, sample_xlsx):
        """Lineage must have events for all 5 stages."""
        result = await extract(sample_xlsx, file_id="lineage-test-2")

        summary = result["lineage_summary"]
        assert summary["total_events"] == 5
        assert sorted(summary["stages"]) == [1, 2, 3, 4, 5]

    @pytest.mark.asyncio
    async def test_lineage_event_types_match_stages(self, mock_anthropic, sample_xlsx):
        """Lineage event types must match the stage names."""
        result = await extract(sample_xlsx, file_id="lineage-test-3")

        summary = result["lineage_summary"]
        expected_types = {"parsing", "triage", "mapping", "validation", "enhanced_mapping"}
        assert set(summary["event_types"]) == expected_types

    @pytest.mark.asyncio
    async def test_final_lineage_id_present(self, mock_anthropic, sample_xlsx):
        """Final lineage ID (from Stage 5) must be set."""
        result = await extract(sample_xlsx, file_id="lineage-test-4")
        assert result["final_lineage_id"] is not None
        assert isinstance(result["final_lineage_id"], str)
        assert len(result["final_lineage_id"]) == 36  # UUID length


class TestTokenAndCostTracking:
    """Test token accumulation and cost calculation across stages."""

    @pytest.mark.asyncio
    async def test_tokens_accumulated_across_stages(self, mock_anthropic, sample_xlsx):
        """Tokens must be accumulated from all stages that use Claude."""
        result = await extract(sample_xlsx, file_id="token-test-1")

        # Mock returns 500 input + 300 output = 800 tokens per Claude call
        # Stages 1-3 each call Claude = 2400 tokens minimum
        # Stage 4 may or may not call Claude depending on validation flags
        # Stage 5 skips Claude call (all mappings at 0.95 confidence)
        assert result["tokens_used"] >= 2400

    @pytest.mark.asyncio
    async def test_cost_calculated_from_tokens(self, mock_anthropic, sample_xlsx):
        """Cost must be derived from token usage."""
        result = await extract(sample_xlsx, file_id="cost-test-1")

        assert result["cost_usd"] > 0
        # Cost formula: tokens * 0.003 / 1000
        expected_cost = result["tokens_used"] * 0.003 / 1000
        assert abs(result["cost_usd"] - expected_cost) < 1e-10

    @pytest.mark.asyncio
    async def test_cost_is_reasonable(self, mock_anthropic, sample_xlsx):
        """Cost for a test extraction should be tiny."""
        result = await extract(sample_xlsx, file_id="cost-test-2")
        assert result["cost_usd"] < 0.10  # Way under $0.10 for mock


class TestTriageBehavior:
    """Test that triage decisions flow correctly through the pipeline."""

    @pytest.mark.asyncio
    async def test_triage_list_returned(self, mock_anthropic, sample_xlsx):
        """Triage decisions must appear in result."""
        result = await extract(sample_xlsx, file_id="triage-test-1")

        assert isinstance(result["triage"], list)
        assert len(result["triage"]) == 3  # Mock has 3 sheets triaged

    @pytest.mark.asyncio
    async def test_triage_contains_tier_info(self, mock_anthropic, sample_xlsx):
        """Each triage entry must have tier and decision."""
        result = await extract(sample_xlsx, file_id="triage-test-2")

        for entry in result["triage"]:
            assert "sheet_name" in entry
            assert "tier" in entry
            assert "decision" in entry

    @pytest.mark.asyncio
    async def test_tier4_sheets_excluded_from_line_items(self, mock_anthropic, sample_xlsx):
        """Tier 4 (SKIP) sheets must not produce line items."""
        result = await extract(sample_xlsx, file_id="triage-test-3")

        tier4_sheets = {
            t["sheet_name"]
            for t in result["triage"]
            if t.get("tier") == 4
        }
        assert "Scratch - Working" in tier4_sheets

        line_item_sheets = {li["sheet"] for li in result["line_items"]}
        assert tier4_sheets.isdisjoint(line_item_sheets)

    @pytest.mark.asyncio
    async def test_tier1_sheets_produce_line_items(self, mock_anthropic, sample_xlsx):
        """Tier 1 sheets with rows must produce line items."""
        result = await extract(sample_xlsx, file_id="triage-test-4")

        # Income Statement is tier 1 and has 3 rows in mock data
        income_items = [
            li for li in result["line_items"]
            if li["sheet"] == "Income Statement"
        ]
        assert len(income_items) == 3


class TestLineItemStructure:
    """Test that line items have correct structure and canonical mappings."""

    @pytest.mark.asyncio
    async def test_line_items_have_required_fields(self, mock_anthropic, sample_xlsx):
        """Every line item must have all required fields."""
        result = await extract(sample_xlsx, file_id="item-test-1")

        required_fields = {
            "sheet", "row", "original_label", "canonical_name",
            "values", "confidence", "hierarchy_level",
        }
        for item in result["line_items"]:
            assert required_fields.issubset(item.keys()), (
                f"Missing fields in line item: {required_fields - item.keys()}"
            )

    @pytest.mark.asyncio
    async def test_canonical_names_from_mapping(self, mock_anthropic, sample_xlsx):
        """Line items must have canonical names assigned by mapping stage."""
        result = await extract(sample_xlsx, file_id="item-test-2")

        canonical_names = {li["canonical_name"] for li in result["line_items"]}
        # Mock mapping: Revenue→revenue, COGS→cogs, Gross Profit→gross_profit
        expected = {"revenue", "cogs", "gross_profit"}
        assert canonical_names == expected

    @pytest.mark.asyncio
    async def test_original_labels_preserved(self, mock_anthropic, sample_xlsx):
        """Original labels from parsing must be preserved in line items."""
        result = await extract(sample_xlsx, file_id="item-test-3")

        original_labels = {li["original_label"] for li in result["line_items"]}
        expected = {"Revenue", "Cost of Goods Sold", "Gross Profit"}
        assert original_labels == expected

    @pytest.mark.asyncio
    async def test_values_from_parsing(self, mock_anthropic, sample_xlsx):
        """Line item values must come from the parsing stage."""
        result = await extract(sample_xlsx, file_id="item-test-4")

        revenue_item = next(
            li for li in result["line_items"]
            if li["canonical_name"] == "revenue"
        )
        assert revenue_item["values"] == {
            "FY2022": 100000, "FY2023": 115000, "FY2024E": 132000
        }

    @pytest.mark.asyncio
    async def test_confidence_from_mapping(self, mock_anthropic, sample_xlsx):
        """Line item confidence must come from the mapping stage."""
        result = await extract(sample_xlsx, file_id="item-test-5")

        for item in result["line_items"]:
            # All mock mappings have 0.95 confidence
            assert item["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_row_indices_from_parsing(self, mock_anthropic, sample_xlsx):
        """Row indices must come from the parsing stage."""
        result = await extract(sample_xlsx, file_id="item-test-6")

        row_indices = {li["original_label"]: li["row"] for li in result["line_items"]}
        # Mock parsing data has specific row indices
        assert row_indices["Revenue"] == 2
        assert row_indices["Cost of Goods Sold"] == 4
        assert row_indices["Gross Profit"] == 5


class TestValidationStageIntegration:
    """Test that Stage 4 validation integrates correctly in the pipeline."""

    @pytest.mark.asyncio
    async def test_validation_result_present(self, mock_anthropic, sample_xlsx):
        """Validation result must be present in pipeline output."""
        result = await extract(sample_xlsx, file_id="val-test-1")
        assert result["validation"] is not None

    @pytest.mark.asyncio
    async def test_validation_has_period_results(self, mock_anthropic, sample_xlsx):
        """Validation must have per-period results."""
        result = await extract(sample_xlsx, file_id="val-test-2")

        validation = result["validation"]
        assert "period_results" in validation
        assert "flags" in validation
        assert "overall_confidence" in validation

    @pytest.mark.asyncio
    async def test_validation_checks_gross_profit(self, mock_anthropic, sample_xlsx):
        """Validation should check gross_profit = revenue - cogs.

        Mock data: Revenue=100k, COGS=40k, Gross Profit=60k.
        60000 == 100000 - 40000 is True, so this check should pass.
        """
        result = await extract(sample_xlsx, file_id="val-test-3")

        validation = result["validation"]
        period_results = validation["period_results"]

        # The mock data has 3 periods: FY2022, FY2023, FY2024E
        assert len(period_results) >= 1

        # With correct data, checks should pass (no error flags)
        error_flags = [
            f for f in validation["flags"] if f["severity"] == "error"
        ]
        # gross_profit derivation check should pass (60000 == 100000 - 40000)
        gp_errors = [
            f for f in error_flags
            if "gross profit" in f.get("message", "").lower()
            or f.get("item") == "gross_profit"
        ]
        assert len(gp_errors) == 0, "Gross profit validation should pass with mock data"

    @pytest.mark.asyncio
    async def test_overall_confidence_between_0_and_1(self, mock_anthropic, sample_xlsx):
        """Overall confidence must be a valid ratio."""
        result = await extract(sample_xlsx, file_id="val-test-4")

        confidence = result["validation"]["overall_confidence"]
        assert 0.0 <= confidence <= 1.0


class TestEnhancedMappingSkipBehavior:
    """Test that Stage 5 correctly skips when all mappings are high-confidence."""

    @pytest.mark.asyncio
    async def test_enhanced_mapping_skips_high_confidence(self, mock_anthropic, sample_xlsx):
        """Stage 5 should skip when all mappings have confidence >= 0.7.

        Mock mapping data has all items at 0.95 confidence, so Stage 5
        should detect 0 candidates and skip the Claude API call.
        """
        result = await extract(sample_xlsx, file_id="enhanced-test-1")

        # All line items should still have their original canonical names
        canonical_names = {li["canonical_name"] for li in result["line_items"]}
        assert canonical_names == {"revenue", "cogs", "gross_profit"}

        # Confidence should remain at 0.95 (not changed by Stage 5)
        for item in result["line_items"]:
            assert item["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_enhanced_mapping_preserves_all_mappings(self, mock_anthropic, sample_xlsx):
        """Stage 5 must not lose any mappings even when skipping."""
        result = await extract(sample_xlsx, file_id="enhanced-test-2")

        # Should still have all 3 line items
        assert len(result["line_items"]) == 3


class TestSheetHandling:
    """Test sheet discovery and handling across the pipeline."""

    @pytest.mark.asyncio
    async def test_sheets_list_from_parsing(self, mock_anthropic, sample_xlsx):
        """Result sheets list must come from the parsing stage."""
        result = await extract(sample_xlsx, file_id="sheet-test-1")

        # Mock parsing returns Income Statement and Balance Sheet
        assert "Income Statement" in result["sheets"]
        assert "Balance Sheet" in result["sheets"]
        assert len(result["sheets"]) == 2

    @pytest.mark.asyncio
    async def test_empty_sheet_produces_no_line_items(self, mock_anthropic, sample_xlsx):
        """Balance Sheet (empty rows in mock) should produce no line items."""
        result = await extract(sample_xlsx, file_id="sheet-test-2")

        balance_items = [
            li for li in result["line_items"]
            if li["sheet"] == "Balance Sheet"
        ]
        assert len(balance_items) == 0


class TestPipelineIdempotency:
    """Test that running the pipeline twice produces consistent results."""

    @pytest.mark.asyncio
    async def test_same_input_same_structure(self, mock_anthropic, sample_xlsx):
        """Two runs with same input should produce structurally identical results."""
        result1 = await extract(sample_xlsx, file_id="idem-test-1")
        result2 = await extract(sample_xlsx, file_id="idem-test-1")

        # Same structure (job_id and lineage IDs will differ)
        assert result1["sheets"] == result2["sheets"]
        assert result1["triage"] == result2["triage"]
        assert len(result1["line_items"]) == len(result2["line_items"])
        assert result1["tokens_used"] == result2["tokens_used"]

        # Line items should have same data (order may vary)
        labels1 = sorted(li["original_label"] for li in result1["line_items"])
        labels2 = sorted(li["original_label"] for li in result2["line_items"])
        assert labels1 == labels2
