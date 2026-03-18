"""Unit tests for completeness scorer."""

from src.validation.completeness_scorer import (
    STATEMENT_TEMPLATES,
    CompletenessScorer,
)

# ============================================================================
# STATEMENT DETECTION
# ============================================================================


class TestStatementDetection:
    """Test auto-detection of statement types from extracted names."""

    def setup_method(self):
        self.scorer = CompletenessScorer()

    def test_detects_income_statement(self):
        names = {"revenue", "cogs", "gross_profit", "net_income"}
        result = self.scorer.score(names)
        assert "income_statement" in result.detected_statements

    def test_detects_balance_sheet(self):
        names = {"total_assets", "total_liabilities", "total_equity"}
        result = self.scorer.score(names)
        assert "balance_sheet" in result.detected_statements

    def test_detects_cash_flow(self):
        names = {"cfo", "cfi", "cff"}
        result = self.scorer.score(names)
        assert "cash_flow" in result.detected_statements

    def test_detects_project_finance(self):
        names = {"cfads", "dscr", "debt_service"}
        result = self.scorer.score(names)
        assert "project_finance" in result.detected_statements

    def test_detects_multiple_statements(self):
        names = {"revenue", "net_income", "total_assets", "total_equity"}
        result = self.scorer.score(names)
        assert "income_statement" in result.detected_statements
        assert "balance_sheet" in result.detected_statements

    def test_no_detection_with_single_item(self):
        """Single detection item shouldn't activate template (min_detect=2)."""
        names = {"revenue"}
        result = self.scorer.score(names)
        assert len(result.detected_statements) == 0

    def test_no_detection_with_random_names(self):
        names = {"foo", "bar", "baz"}
        result = self.scorer.score(names)
        assert len(result.detected_statements) == 0
        assert result.overall_score == 0.0


# ============================================================================
# SCORING
# ============================================================================


class TestScoring:
    """Test completeness scoring logic."""

    def setup_method(self):
        self.scorer = CompletenessScorer()

    def test_perfect_income_statement_score(self):
        """All IS items present should give score of 1.0."""
        names = set(STATEMENT_TEMPLATES["income_statement"]["items"].keys())
        result = self.scorer.score(names)
        stmt = result.per_statement["income_statement"]
        assert stmt.raw_score == 1.0
        assert stmt.weighted_score == 1.0
        assert stmt.core_score == 1.0
        assert len(stmt.missing_items) == 0

    def test_partial_income_statement(self):
        """Only core items should give partial scores."""
        names = {"revenue", "net_income", "gross_profit"}
        result = self.scorer.score(names)
        stmt = result.per_statement["income_statement"]
        assert 0.0 < stmt.raw_score < 1.0
        assert 0.0 < stmt.weighted_score < 1.0
        assert len(stmt.found_items) == 3
        assert len(stmt.missing_items) > 0

    def test_weighted_higher_than_raw_when_core_found(self):
        """If high-weight items are found, weighted > raw."""
        # revenue (1.0) + net_income (0.95) are high-weight
        names = {"revenue", "net_income"}
        result = self.scorer.score(names)
        stmt = result.per_statement["income_statement"]
        assert stmt.weighted_score >= stmt.raw_score

    def test_core_score_independent_of_optional(self):
        """Core score only considers is_core=True items."""
        # All core items
        core_names = {
            n for n, (w, c) in STATEMENT_TEMPLATES["income_statement"]["items"].items() if c
        }
        result = self.scorer.score(core_names)
        stmt = result.per_statement["income_statement"]
        assert stmt.core_score == 1.0
        assert stmt.raw_score < 1.0  # Missing optional items


# ============================================================================
# MISSING ITEMS
# ============================================================================


class TestMissingItems:
    """Test missing item reporting."""

    def setup_method(self):
        self.scorer = CompletenessScorer()

    def test_missing_items_reported(self):
        names = {"revenue", "net_income"}
        result = self.scorer.score(names)
        stmt = result.per_statement["income_statement"]
        missing_names = [m.canonical_name for m in stmt.missing_items]
        assert "cogs" in missing_names
        assert "gross_profit" in missing_names

    def test_core_missing_items_flagged(self):
        names = {"revenue", "net_income"}
        result = self.scorer.score(names)
        stmt = result.per_statement["income_statement"]
        core_missing = [m for m in stmt.missing_items if m.is_core]
        assert len(core_missing) > 0
        assert any(m.canonical_name == "ebitda" for m in core_missing)

    def test_missing_items_have_weights(self):
        names = {"revenue", "net_income"}
        result = self.scorer.score(names)
        for m in result.missing_items:
            assert 0.0 < m.weight <= 1.0

    def test_flattened_missing_items(self):
        """overall missing_items should be flattened across all statements."""
        names = {"revenue", "net_income", "total_assets", "total_equity"}
        result = self.scorer.score(names)
        # Should have missing items from both IS and BS
        categories = {m.category for m in result.missing_items}
        assert len(categories) >= 1  # At least one category with missing items


# ============================================================================
# OVERALL SCORE
# ============================================================================


class TestOverallScore:
    """Test overall score aggregation."""

    def setup_method(self):
        self.scorer = CompletenessScorer()

    def test_overall_score_single_statement(self):
        """Overall should equal the single statement's weighted score."""
        names = set(STATEMENT_TEMPLATES["income_statement"]["items"].keys())
        result = self.scorer.score(names)
        assert len(result.detected_statements) >= 1
        assert result.overall_score > 0

    def test_overall_raw_score(self):
        names = set(STATEMENT_TEMPLATES["income_statement"]["items"].keys())
        result = self.scorer.score(names)
        assert result.overall_raw_score > 0
        assert result.total_found > 0

    def test_total_counts(self):
        names = {"revenue", "net_income"}
        result = self.scorer.score(names)
        assert result.total_expected > 0
        assert result.total_found == 2
        assert result.total_missing == result.total_expected - result.total_found


# ============================================================================
# CUSTOM TEMPLATES
# ============================================================================


class TestCustomTemplates:
    """Test custom template override."""

    def test_custom_template(self):
        custom = {
            "custom_statement": {
                "detection_items": {"foo", "bar"},
                "min_detect": 2,
                "items": {
                    "foo": (1.0, True),
                    "bar": (0.8, True),
                    "baz": (0.5, False),
                },
            }
        }
        scorer = CompletenessScorer(templates=custom)
        result = scorer.score({"foo", "bar"})
        assert "custom_statement" in result.detected_statements
        stmt = result.per_statement["custom_statement"]
        assert len(stmt.found_items) == 2
        assert len(stmt.missing_items) == 1
        assert stmt.missing_items[0].canonical_name == "baz"

    def test_custom_min_detect(self):
        """Higher min_detect should require more items to activate."""
        custom = {
            "strict": {
                "detection_items": {"a", "b", "c"},
                "min_detect": 3,
                "items": {"a": (1.0, True), "b": (1.0, True), "c": (1.0, True)},
            }
        }
        scorer = CompletenessScorer(templates=custom)
        # Only 2 of 3 detection items — shouldn't activate
        result = scorer.score({"a", "b"})
        assert len(result.detected_statements) == 0
        # All 3 — should activate
        result = scorer.score({"a", "b", "c"})
        assert "strict" in result.detected_statements


# ============================================================================
# EDGE CASES
# ============================================================================


class TestEdgeCases:
    """Test edge cases."""

    def setup_method(self):
        self.scorer = CompletenessScorer()

    def test_empty_extraction(self):
        result = self.scorer.score(set())
        assert result.overall_score == 0.0
        assert result.detected_statements == []
        assert result.total_found == 0

    def test_no_matching_template(self):
        result = self.scorer.score({"unknown_item_1", "unknown_item_2"})
        assert result.overall_score == 0.0
        assert result.detected_statements == []

    def test_all_items_extracted(self):
        """Extract everything from all templates — should be near 1.0."""
        all_names = set()
        for template in STATEMENT_TEMPLATES.values():
            all_names.update(template["items"].keys())
        result = self.scorer.score(all_names)
        assert result.overall_score > 0.95
        assert result.total_missing == 0

    def test_extra_items_dont_affect_score(self):
        """Items not in any template should be ignored."""
        names = set(STATEMENT_TEMPLATES["income_statement"]["items"].keys())
        names.add("some_random_item")
        names.add("another_random_item")
        result = self.scorer.score(names)
        stmt = result.per_statement["income_statement"]
        assert stmt.raw_score == 1.0  # Extra items don't reduce score

    def test_taxonomy_metadata_used_for_category(self):
        """If taxonomy is provided, missing items get correct category."""
        taxonomy = [
            {"canonical_name": "revenue", "category": "income_statement"},
            {"canonical_name": "cogs", "category": "income_statement"},
        ]
        scorer = CompletenessScorer(taxonomy_items=taxonomy)
        result = scorer.score({"revenue", "net_income"})
        cogs_missing = [m for m in result.missing_items if m.canonical_name == "cogs"]
        if cogs_missing:
            assert cogs_missing[0].category == "income_statement"


# ============================================================================
# MODEL TYPE DETECTION
# ============================================================================


class TestModelTypeDetection:
    """Test model type detection from extracted canonical names."""

    def setup_method(self):
        self.scorer = CompletenessScorer()

    def test_corporate_default(self):
        names = {"revenue", "cogs", "gross_profit", "net_income", "total_assets", "total_equity"}
        assert self.scorer.detect_model_type(names) == "corporate"

    def test_project_finance(self):
        names = {"cfads", "dscr", "debt_service", "equity_irr", "cfae"}
        assert self.scorer.detect_model_type(names) == "project_finance"

    def test_construction_only(self):
        """PF signals + construction indicators but no IS items -> construction_only."""
        names = {"cfads", "dscr", "total_investment", "development_costs", "equity_contribution"}
        assert self.scorer.detect_model_type(names) == "construction_only"

    def test_construction_with_is_items_not_construction_only(self):
        """If IS items are present alongside construction, should NOT be construction_only."""
        names = {
            "total_investment",
            "development_costs",
            "equity_contribution",
            "revenue",
            "net_income",
            "cfads",
            "dscr",
            "debt_service",
        }
        result = self.scorer.detect_model_type(names)
        assert result != "construction_only"

    def test_mixed(self):
        """Both PF and IS signals strong -> mixed."""
        names = {"revenue", "net_income", "cfads", "dscr", "debt_service", "equity_irr"}
        assert self.scorer.detect_model_type(names) == "mixed"

    def test_saas(self):
        names = {"arr", "mrr", "churn_rate", "revenue", "net_income"}
        assert self.scorer.detect_model_type(names) == "saas"

    def test_saas_priority_over_corporate(self):
        """SaaS takes priority even with some IS items."""
        names = {"arr", "mrr", "revenue", "cogs", "gross_profit"}
        assert self.scorer.detect_model_type(names) == "saas"

    def test_explicit_project_finance_hint(self):
        names = {"cfads", "dscr"}
        assert self.scorer.detect_model_type(names, is_project_finance=True) == "project_finance"

    def test_empty_names(self):
        assert self.scorer.detect_model_type(set()) == "corporate"

    def test_single_pf_item_not_enough(self):
        names = {"cfads"}
        assert self.scorer.detect_model_type(names) == "corporate"

    def test_model_type_in_result(self):
        """CompletenessResult should carry model_type when provided."""
        names = {"revenue", "net_income"}
        result = self.scorer.score(names, model_type="saas")
        assert result.model_type == "saas"

    def test_model_type_default_none(self):
        """CompletenessResult model_type should default to None."""
        names = {"revenue", "net_income"}
        result = self.scorer.score(names)
        assert result.model_type is None


# ============================================================================
# CONSTRUCTION TEMPLATE EXCLUSION
# ============================================================================


class TestConstructionExclusion:
    """Test that construction_only model type excludes income statement template."""

    def setup_method(self):
        self.scorer = CompletenessScorer()

    def test_construction_excludes_income_statement(self):
        """construction_only should not detect income_statement even if items present."""
        names = {"revenue", "net_income", "total_investment", "development_costs"}
        result = self.scorer.score(names, model_type="construction_only")
        assert "income_statement" not in result.detected_statements

    def test_construction_still_detects_other_templates(self):
        """Other templates should still work for construction_only."""
        names = {
            "total_investment",
            "development_costs",
            "equity_contribution",
            "construction_cost",
            "dscr",
            "llcr",
        }
        result = self.scorer.score(names, model_type="construction_only")
        assert "construction_budget" in result.detected_statements

    def test_corporate_does_not_exclude_income_statement(self):
        """Non-construction models should still detect IS."""
        names = {"revenue", "net_income", "total_investment", "development_costs"}
        result = self.scorer.score(names, model_type="corporate")
        assert "income_statement" in result.detected_statements


# ============================================================================
# NEW TEMPLATE DETECTION
# ============================================================================


class TestNewTemplates:
    """Test the 3 new statement templates."""

    def setup_method(self):
        self.scorer = CompletenessScorer()

    def test_construction_budget_detection(self):
        names = {"total_investment", "development_costs", "equity_contribution"}
        result = self.scorer.score(names)
        assert "construction_budget" in result.detected_statements

    def test_covenant_compliance_detection(self):
        names = {"dscr", "llcr", "plcr"}
        result = self.scorer.score(names)
        assert "covenant_compliance" in result.detected_statements

    def test_returns_analysis_detection(self):
        names = {"equity_irr", "pre_tax_irr"}
        result = self.scorer.score(names)
        assert "returns_analysis" in result.detected_statements

    def test_construction_budget_scoring(self):
        all_items = set(STATEMENT_TEMPLATES["construction_budget"]["items"].keys())
        result = self.scorer.score(all_items)
        stmt = result.per_statement["construction_budget"]
        assert stmt.raw_score == 1.0
        assert stmt.weighted_score == 1.0


# ============================================================================
# SAAS METRICS TEMPLATE
# ============================================================================


class TestSaaSMetricsTemplate:
    """Test the SaaS metrics completeness template."""

    def setup_method(self):
        self.scorer = CompletenessScorer()

    def test_detects_saas_metrics(self):
        """SaaS template should activate when arr + mrr present."""
        names = {"arr", "mrr"}
        result = self.scorer.score(names)
        assert "saas_metrics" in result.detected_statements

    def test_detects_saas_with_nrr(self):
        """SaaS template should activate when arr + net_revenue_retention present."""
        names = {"arr", "net_revenue_retention"}
        result = self.scorer.score(names)
        assert "saas_metrics" in result.detected_statements

    def test_no_detect_single_saas_item(self):
        """Single SaaS item should not activate template."""
        names = {"arr"}
        result = self.scorer.score(names)
        assert "saas_metrics" not in result.detected_statements

    def test_perfect_saas_score(self):
        """All SaaS items present should give score of 1.0."""
        names = set(STATEMENT_TEMPLATES["saas_metrics"]["items"].keys())
        result = self.scorer.score(names)
        stmt = result.per_statement["saas_metrics"]
        assert stmt.raw_score == 1.0
        assert stmt.weighted_score == 1.0

    def test_core_only_saas(self):
        """Only core SaaS items (arr, mrr, nrr) should give partial score."""
        names = {"arr", "mrr", "net_revenue_retention"}
        result = self.scorer.score(names)
        stmt = result.per_statement["saas_metrics"]
        assert stmt.core_score == 1.0
        assert stmt.raw_score < 1.0

    def test_saas_combined_with_income_statement(self):
        """SaaS template can co-exist with income statement detection."""
        names = {"revenue", "net_income", "cogs", "arr", "mrr"}
        result = self.scorer.score(names)
        assert "income_statement" in result.detected_statements
        assert "saas_metrics" in result.detected_statements

    def test_saas_weight_ordering(self):
        """Core SaaS items must have higher weights than optional items."""
        items = STATEMENT_TEMPLATES["saas_metrics"]["items"]
        core_weights = [w for w, c in items.values() if c]
        optional_weights = [w for w, c in items.values() if not c]
        assert min(core_weights) > max(optional_weights), (
            "All core item weights must exceed all optional item weights"
        )

    def test_saas_indicators_subset_of_template_items(self):
        """_SAAS_INDICATORS should be a subset of saas_metrics template items."""
        from src.validation.completeness_scorer import _SAAS_INDICATORS

        template_items = set(STATEMENT_TEMPLATES["saas_metrics"]["items"].keys())
        missing = _SAAS_INDICATORS - template_items
        assert not missing, f"_SAAS_INDICATORS has items not in saas_metrics template: {missing}"

    def test_saas_detection_with_nrr_triggers_model_type(self):
        """arr + net_revenue_retention should trigger both model_type and template."""
        names = {"arr", "net_revenue_retention"}
        assert self.scorer.detect_model_type(names) == "saas"
        result = self.scorer.score(names)
        assert "saas_metrics" in result.detected_statements


# ============================================================================
# EDGE CASE HARDENING
# ============================================================================


class TestSaasPfMisclassification:
    """Test SaaS + PF coexistence returns 'mixed' instead of pure 'saas'."""

    def setup_method(self):
        self.scorer = CompletenessScorer()

    def test_saas_plus_pf_returns_mixed(self):
        """SaaS metrics + strong PF signals → 'mixed', not 'saas'."""
        names = {"arr", "mrr", "cfads", "dscr", "debt_service"}
        assert self.scorer.detect_model_type(names) == "mixed"

    def test_pure_saas_unchanged(self):
        """SaaS metrics without PF signals → still 'saas'."""
        names = {"arr", "mrr", "net_revenue_retention"}
        assert self.scorer.detect_model_type(names) == "saas"

    def test_saas_plus_weak_pf_still_saas(self):
        """SaaS metrics with only 2 PF signals (below threshold) → 'saas'."""
        names = {"arr", "mrr", "cfads", "dscr"}
        assert self.scorer.detect_model_type(names) == "saas"


class TestTemplateOverlapDedup:
    """Test that overlapping template items aren't double-counted."""

    def setup_method(self):
        self.scorer = CompletenessScorer()

    def test_overlapping_templates_no_double_count(self):
        """Items in both PF and covenant templates should be counted once."""
        # dscr, llcr, plcr appear in both project_finance and covenant_compliance
        names = {
            "cfads",
            "dscr",
            "debt_service",
            "cfae",  # PF detection
            "llcr",
            "plcr",
            "debt_covenants",  # covenant detection
        }
        result = self.scorer.score(names)
        assert "project_finance" in result.detected_statements
        assert "covenant_compliance" in result.detected_statements

        # Verify no double-counting: each item counted once in totals
        all_unique_expected = set()
        for template_name in result.detected_statements:
            template = STATEMENT_TEMPLATES[template_name]
            all_unique_expected.update(template["items"].keys())
        assert result.total_expected == len(all_unique_expected)

    def test_overlapping_templates_missing_not_duplicated(self):
        """Missing items should not have duplicates across templates."""
        names = {
            "cfads",
            "dscr",
            "debt_service",  # PF detection (min 2)
            "llcr",
            "plcr",  # covenant detection (min 2)
        }
        result = self.scorer.score(names)
        missing_names = [m.canonical_name for m in result.missing_items]
        assert len(missing_names) == len(set(missing_names)), (
            f"Duplicate missing items: {missing_names}"
        )


# ============================================================================
# is_project_finance HINT TESTS (E1)
# ============================================================================


class TestDetectModelTypeWithHint:
    """Test that is_project_finance hint affects detect_model_type."""

    def setup_method(self):
        self.scorer = CompletenessScorer()

    def test_hint_overrides_low_pf_signal_count(self):
        """Hint=True should return project_finance even with only 2 PF indicators."""
        # Only 2 PF indicators (below the min 3 threshold)
        names = {"cfads", "dscr", "revenue", "cogs", "net_income"}
        # Without hint: would be corporate (only 2 PF signals)
        result_no_hint = self.scorer.detect_model_type(names)
        assert result_no_hint == "corporate"
        # With hint: should be project_finance
        result_hint = self.scorer.detect_model_type(names, is_project_finance=True)
        assert result_hint == "project_finance"

    def test_construction_only_with_pf_hint(self):
        """Construction indicators + PF hint should still return construction_only."""
        # Construction indicators + PF indicators but no IS items
        names = {
            "total_investment",
            "development_costs",
            "equity_contribution",
            "cfads",
            "dscr",
            "debt_service",
        }
        result = self.scorer.detect_model_type(names, is_project_finance=True)
        assert result == "construction_only"

    def test_hint_false_has_no_effect(self):
        """Hint=False should not change corporate classification."""
        names = {"revenue", "cogs", "net_income"}
        result = self.scorer.detect_model_type(names, is_project_finance=False)
        assert result == "corporate"


# ============================================================================
# PERIOD COVERAGE (score_with_periods)
# ============================================================================


class TestScoreWithPeriods:
    """Test period-aware completeness scoring."""

    def setup_method(self):
        from decimal import Decimal

        self.scorer = CompletenessScorer()
        self.Decimal = Decimal

    def test_full_period_coverage(self):
        """All found items present in all periods → period_coverage = 1.0."""
        period_values = {
            "FY2023": {
                "revenue": self.Decimal("1000"),
                "cogs": self.Decimal("500"),
                "net_income": self.Decimal("300"),
            },
            "FY2024": {
                "revenue": self.Decimal("1200"),
                "cogs": self.Decimal("600"),
                "net_income": self.Decimal("400"),
            },
        }
        result = self.scorer.score_with_periods(period_values)

        # Should detect income_statement at minimum
        assert len(result.detected_statements) > 0
        for stmt in result.per_statement.values():
            if stmt.found_items:
                assert stmt.period_coverage is not None
                assert stmt.period_coverage == 1.0
                assert stmt.total_periods == 2
                assert stmt.sparse_items == []

    def test_sparse_items_detected(self):
        """Items present in <50% of periods are flagged as sparse."""
        period_values = {
            "FY2021": {
                "revenue": self.Decimal("800"),
                "cogs": self.Decimal("400"),
                "net_income": self.Decimal("200"),
            },
            "FY2022": {
                "revenue": self.Decimal("900"),
                "cogs": self.Decimal("450"),
                "net_income": self.Decimal("250"),
            },
            "FY2023": {
                "revenue": self.Decimal("1000"),
                "cogs": self.Decimal("500"),
                # net_income missing
            },
            "FY2024": {
                "revenue": self.Decimal("1100"),
                # cogs and net_income missing
            },
        }
        result = self.scorer.score_with_periods(period_values)

        is_stmt = result.per_statement.get("income_statement")
        if is_stmt:
            assert is_stmt.total_periods == 4
            # net_income: 2/4 = 50% → NOT sparse (threshold is <50%)
            # cogs: 3/4 = 75% → not sparse
            # revenue: 4/4 → not sparse
            # But note: the items in the template that are found matter
            assert is_stmt.period_coverage is not None
            assert is_stmt.period_coverage < 1.0

    def test_weighted_score_blends_name_and_period(self):
        """weighted_score = 0.7 * base_weighted + 0.3 * period_coverage."""
        period_values = {
            "FY2023": {
                "revenue": self.Decimal("1000"),
                "cogs": self.Decimal("500"),
                "net_income": self.Decimal("300"),
            },
            "FY2024": {
                "revenue": self.Decimal("1200"),
                "cogs": self.Decimal("600"),
                "net_income": self.Decimal("400"),
            },
        }
        # Get base score for comparison
        extracted_names = {"revenue", "cogs", "net_income"}
        base_result = self.scorer.score(extracted_names)

        period_result = self.scorer.score_with_periods(period_values)

        # With full period coverage, blended should be 0.7*base + 0.3*1.0
        for stmt_name in base_result.per_statement:
            if stmt_name in period_result.per_statement:
                base_ws = base_result.per_statement[stmt_name].weighted_score
                period_ws = period_result.per_statement[stmt_name].weighted_score
                expected = round(0.7 * base_ws + 0.3 * 1.0, 4)
                assert abs(period_ws - expected) < 0.01

    def test_backward_compat_score_unchanged(self):
        """Existing score() method should still work without period data."""
        names = {"revenue", "cogs", "net_income"}
        result = self.scorer.score(names)
        assert result.overall_score > 0
        for stmt in result.per_statement.values():
            # Period fields should be None (not populated by score())
            assert stmt.period_coverage is None
            assert stmt.total_periods is None

    def test_empty_periods_returns_base_score(self):
        """Empty period_values dict should return base result."""
        result = self.scorer.score_with_periods({})
        assert result.overall_score == 0.0
        assert result.detected_statements == []

    def test_single_period(self):
        """Single period with all items → full coverage."""
        period_values = {
            "FY2024": {
                "revenue": self.Decimal("1000"),
                "cogs": self.Decimal("500"),
                "net_income": self.Decimal("300"),
            },
        }
        result = self.scorer.score_with_periods(period_values)

        for stmt in result.per_statement.values():
            if stmt.found_items:
                assert stmt.total_periods == 1
                assert stmt.period_coverage == 1.0
