"""Completeness scorer for financial extraction results.

Scores how much of the expected financial data was actually extracted,
using statement templates that define core and optional items per
financial statement type (income statement, balance sheet, cash flow,
project finance).

Statement type is auto-detected from the set of extracted canonical names,
so a corporate P&L extraction is not penalized for missing project finance items.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class MissingItem:
    """A single item that was expected but not extracted."""

    canonical_name: str
    category: str
    weight: float  # importance weight (0.0 to 1.0)
    is_core: bool


@dataclass
class StatementCompleteness:
    """Completeness result for a single statement type."""

    statement_type: str
    expected_items: List[str]
    found_items: List[str]
    missing_items: List[MissingItem]
    raw_score: float  # found / expected (unweighted)
    weighted_score: float  # weighted by importance
    core_score: float  # core items only


@dataclass
class CompletenessResult:
    """Overall completeness scoring result."""

    overall_score: float  # 0.0 to 1.0 (weighted average)
    overall_raw_score: float  # unweighted ratio
    detected_statements: List[str]  # which statement types were detected
    per_statement: Dict[str, StatementCompleteness] = field(default_factory=dict)
    total_expected: int = 0
    total_found: int = 0
    total_missing: int = 0
    missing_items: List[MissingItem] = field(default_factory=list)
    model_type: Optional[str] = None


# ---- Statement Templates ----
# Each template defines:
#   detection_items: canonical names that indicate this statement type is present
#   min_detect: minimum number of detection_items needed to activate this template
#   items: {canonical_name: (weight, is_core)} — expected items with importance weights

STATEMENT_TEMPLATES: Dict[str, Dict] = {
    "income_statement": {
        "detection_items": {"revenue", "cogs", "gross_profit", "net_income", "ebitda", "ebit"},
        "min_detect": 2,
        "items": {
            "revenue": (1.0, True),
            "cogs": (0.9, True),
            "gross_profit": (0.95, True),
            "ebitda": (0.85, True),
            "ebit": (0.8, True),
            "net_income": (0.95, True),
            "depreciation": (0.6, False),
            "interest_expense": (0.7, False),
            "tax_expense": (0.65, False),
            "ebt": (0.6, False),
            "opex": (0.7, False),
        },
    },
    "balance_sheet": {
        "detection_items": {"total_assets", "total_liabilities", "total_equity", "current_assets"},
        "min_detect": 2,
        "items": {
            "total_assets": (1.0, True),
            "total_liabilities": (0.95, True),
            "total_equity": (0.95, True),
            "current_assets": (0.8, True),
            "cash": (0.85, True),
            "current_liabilities": (0.8, True),
            "long_term_debt": (0.75, False),
            "accounts_receivable": (0.7, False),
            "accounts_payable": (0.7, False),
            "ppe": (0.65, False),
        },
    },
    "cash_flow": {
        "detection_items": {"cfo", "cfi", "cff", "net_change_cash", "fcf"},
        "min_detect": 2,
        "items": {
            "cfo": (1.0, True),
            "cfi": (0.9, True),
            "cff": (0.9, True),
            "net_change_cash": (0.85, True),
            "capex": (0.8, True),
            "fcf": (0.75, False),
        },
    },
    "project_finance": {
        "detection_items": {"cfads", "cfae", "dscr", "debt_service", "equity_irr"},
        "min_detect": 2,
        "items": {
            "cfads": (1.0, True),
            "dscr": (0.95, True),
            "debt_service": (0.9, True),
            "cfae": (0.85, True),
            "llcr": (0.7, False),
            "plcr": (0.65, False),
            "dsra_balance": (0.6, False),
        },
    },
    "debt_schedule": {
        "detection_items": {
            "debt_opening_balance",
            "debt_closing_balance",
            "debt_service",
            "interest_expense",
        },
        "min_detect": 2,
        "items": {
            "debt_opening_balance": (0.9, True),
            "debt_closing_balance": (0.9, True),
            "debt_service": (0.85, True),
            "interest_expense": (0.8, True),
            "debt_drawdown": (0.7, False),
            "debt_mandatory_repayment": (0.7, False),
        },
    },
    "construction_budget": {
        "detection_items": {
            "total_investment",
            "development_costs",
            "equity_contribution",
            "construction_cost",
        },
        "min_detect": 2,
        "items": {
            "total_investment": (1.0, True),
            "development_costs": (0.9, True),
            "equity_contribution": (0.85, True),
            "construction_cost": (0.8, True),
            "contingency": (0.6, False),
            "land_cost": (0.5, False),
        },
    },
    "covenant_compliance": {
        "detection_items": {"dscr", "llcr", "plcr", "debt_covenants"},
        "min_detect": 2,
        "items": {
            "dscr": (1.0, True),
            "llcr": (0.9, True),
            "plcr": (0.85, False),
            "debt_covenants": (0.7, False),
        },
    },
    "returns_analysis": {
        "detection_items": {"equity_irr", "pre_tax_irr", "post_tax_irr", "equity_returns"},
        "min_detect": 2,
        "items": {
            "equity_irr": (1.0, True),
            "pre_tax_irr": (0.85, True),
            "post_tax_irr": (0.8, False),
            "equity_returns": (0.7, False),
        },
    },
    "saas_metrics": {
        "detection_items": {"arr", "mrr", "net_revenue_retention"},
        "min_detect": 2,
        "items": {
            "arr": (1.0, True),
            "mrr": (0.9, True),
            "net_revenue_retention": (0.8, True),
            "cac": (0.7, False),
            "ltv": (0.7, False),
            "burn_rate": (0.6, False),
            "churn_rate": (0.6, False),
            "customer_count": (0.5, False),
            "ltv_cac_ratio": (0.5, False),
            "cash_runway_months": (0.5, False),
        },
    },
}


# ---- Model Type Detection Signals ----
_IS_INDICATORS = {"revenue", "cogs", "gross_profit", "net_income", "ebitda", "ebit"}
_PF_INDICATORS = {
    "cfads",
    "cfae",
    "dscr",
    "debt_service",
    "equity_irr",
    "llcr",
    "plcr",
    "dsra_balance",
}
_CONSTRUCTION_INDICATORS = {
    "total_investment",
    "development_costs",
    "equity_contribution",
    "construction_cost",
    "contingency",
}
_SAAS_INDICATORS = {"arr", "mrr", "churn_rate", "ltv", "cac", "net_revenue_retention", "burn_rate"}


class CompletenessScorer:
    """Scores extraction completeness against expected statement templates."""

    def __init__(
        self,
        taxonomy_items: Optional[List[Dict]] = None,
        templates: Optional[Dict[str, Dict]] = None,
    ):
        """
        Args:
            taxonomy_items: Full taxonomy list (used for category metadata).
            templates: Override statement templates. Defaults to STATEMENT_TEMPLATES.
        """
        self.taxonomy = {item["canonical_name"]: item for item in (taxonomy_items or [])}
        self.templates = templates or STATEMENT_TEMPLATES

    def detect_model_type(
        self,
        extracted_names: Set[str],
        is_project_finance: Optional[bool] = None,
    ) -> str:
        """Detect the financial model type from extracted canonical names.

        Args:
            extracted_names: Set of all canonical names that were extracted.
            is_project_finance: Optional explicit hint (e.g. from triage stage).

        Returns:
            One of: "corporate", "project_finance", "construction_only", "mixed", "saas"
        """
        saas_count = len(extracted_names & _SAAS_INDICATORS)
        pf_count = len(extracted_names & _PF_INDICATORS)
        is_count = len(extracted_names & _IS_INDICATORS)
        construction_count = len(extracted_names & _CONSTRUCTION_INDICATORS)

        # SaaS takes priority — distinctive metrics
        # But SaaS + strong PF signals → mixed (e.g. fintech with ARR+MRR+DSCR+CFADS)
        if saas_count >= 2:
            if pf_count >= 3:
                return "mixed"
            return "saas"

        # Construction-only: PF signals present but IS signals mostly absent
        if (is_project_finance or pf_count >= 2) and construction_count >= 2 and is_count <= 1:
            return "construction_only"

        # Mixed: both PF and IS signals are strong
        if pf_count >= 3 and is_count >= 2:
            return "mixed"

        # Pure project finance
        if pf_count >= 3 or is_project_finance:
            return "project_finance"

        return "corporate"

    def score(
        self, extracted_names: Set[str], model_type: Optional[str] = None
    ) -> CompletenessResult:
        """Score completeness of extracted data against templates.

        Args:
            extracted_names: Set of all canonical names that were extracted.
            model_type: Optional model type to exclude irrelevant templates.

        Returns:
            CompletenessResult with per-statement and overall scores.
        """
        # Exclude irrelevant templates based on model type
        exclude_templates: Set[str] = set()
        if model_type == "construction_only":
            exclude_templates.add("income_statement")

        detected = self._detect_statements(extracted_names, exclude_templates)

        if not detected:
            return CompletenessResult(
                overall_score=0.0,
                overall_raw_score=0.0,
                detected_statements=[],
            )

        per_statement: Dict[str, StatementCompleteness] = {}
        all_missing: List[MissingItem] = []
        total_expected = 0
        total_found = 0
        # Deduplicate across templates: items like dscr/llcr/plcr appear in
        # both project_finance and covenant_compliance — count each once.
        seen_expected: Set[str] = set()
        seen_found: Set[str] = set()

        for template_name in detected:
            template = self.templates[template_name]
            stmt = self._score_statement(template_name, template, extracted_names)
            per_statement[template_name] = stmt
            for item in stmt.missing_items:
                if item.canonical_name not in seen_expected:
                    all_missing.append(item)
            for item_name in stmt.expected_items:
                if item_name not in seen_expected:
                    total_expected += 1
                    seen_expected.add(item_name)
            for item_name in stmt.found_items:
                if item_name not in seen_found:
                    total_found += 1
                    seen_found.add(item_name)

        # Overall score: weighted average of per-statement weighted_scores,
        # weighted by number of expected items in each template
        total_weight = sum(len(self.templates[t]["items"]) for t in detected)
        if total_weight > 0:
            overall = (
                sum(
                    per_statement[t].weighted_score * len(self.templates[t]["items"])
                    for t in detected
                )
                / total_weight
            )
        else:
            overall = 0.0

        overall_raw = total_found / max(total_expected, 1)

        return CompletenessResult(
            overall_score=round(overall, 4),
            overall_raw_score=round(overall_raw, 4),
            detected_statements=detected,
            per_statement=per_statement,
            total_expected=total_expected,
            total_found=total_found,
            total_missing=total_expected - total_found,
            missing_items=all_missing,
            model_type=model_type,
        )

    def _detect_statements(
        self,
        extracted_names: Set[str],
        exclude_templates: Optional[Set[str]] = None,
    ) -> List[str]:
        """Determine which statement types the extraction covers.

        A template is active if at least `min_detect` of its `detection_items`
        appear in the extracted set and it is not in the exclusion set.
        """
        detected = []
        for name, template in self.templates.items():
            if exclude_templates and name in exclude_templates:
                continue
            detection_items = template["detection_items"]
            # min_detect >= 2 is intentional: single-item overlap is too noisy
            # for reliable template detection.  A model with only "revenue"
            # should not activate the full income_statement template.
            min_detect = template["min_detect"]
            overlap = len(detection_items & extracted_names)
            if overlap >= min_detect:
                detected.append(name)
        return sorted(detected)

    def _score_statement(
        self,
        template_name: str,
        template: Dict,
        extracted_names: Set[str],
    ) -> StatementCompleteness:
        """Score completeness for a single statement template."""
        items = template["items"]
        expected = list(items.keys())
        found = [name for name in expected if name in extracted_names]
        missing = []

        for name in expected:
            if name not in extracted_names:
                weight, is_core = items[name]
                category = self.taxonomy.get(name, {}).get("category", template_name)
                missing.append(
                    MissingItem(
                        canonical_name=name,
                        category=category,
                        weight=weight,
                        is_core=is_core,
                    )
                )

        # Raw score: unweighted ratio
        raw_score = len(found) / max(len(expected), 1)

        # Weighted score: importance-weighted
        total_weight = sum(w for w, _ in items.values())
        found_weight = sum(items[n][0] for n in found)
        weighted_score = found_weight / max(total_weight, 0.001)

        # Core score: only is_core=True items
        core_items = {n: w for n, (w, c) in items.items() if c}
        core_found = [n for n in core_items if n in extracted_names]
        core_total_weight = sum(core_items.values())
        core_found_weight = sum(core_items[n] for n in core_found)
        core_score = core_found_weight / max(core_total_weight, 0.001)

        return StatementCompleteness(
            statement_type=template_name,
            expected_items=expected,
            found_items=found,
            missing_items=missing,
            raw_score=round(raw_score, 4),
            weighted_score=round(weighted_score, 4),
            core_score=round(core_score, 4),
        )
