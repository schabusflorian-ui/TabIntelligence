"""
Derivation Rules Registry

Declarative definitions of financial metric derivations.
Each rule specifies a target canonical, the formula, input canonicals,
confidence propagation mode, and optional model-type constraints.

Priority determines processing order within a multi-pass DAG:
  lower number = computed earlier (inputs for higher-priority rules).
"""

from typing import List, Optional
from dataclasses import dataclass, field


@dataclass
class DerivationRule:
    id: str                              # Unique rule identifier (e.g. "DR-001")
    target: str                          # Target canonical name
    formula: str                         # Human-readable formula string (for logging)
    inputs: List[str]                    # Input canonical names required
    confidence_mode: str                 # "min" | "product" | "weighted"
    priority: int                        # Processing pass (1 = earliest)
    derivation_discount: float = 1.0     # Multiplied into propagated confidence
    model_types: Optional[List[str]] = None  # None = all; list = restrict to these
    consistency_threshold: float = 0.03  # Max relative divergence for consistency check


# ─────────────────────────────────────────────────────────────────────────────
# Income Statement chain
# ─────────────────────────────────────────────────────────────────────────────
DERIVATION_RULES: List[DerivationRule] = [

    DerivationRule(
        id="DR-001",
        target="gross_profit",
        formula="revenue - cogs",
        inputs=["revenue", "cogs"],
        confidence_mode="min",
        priority=1,
    ),

    DerivationRule(
        id="DR-002a",
        target="ebitda",
        formula="ebit + depreciation + amortization",
        inputs=["ebit", "depreciation", "amortization"],
        confidence_mode="min",
        priority=2,
    ),

    DerivationRule(
        id="DR-002b",
        target="ebitda",
        formula="ebit + depreciation_and_amortization",
        inputs=["ebit", "depreciation_and_amortization"],
        confidence_mode="min",
        priority=3,  # fallback — only used if DR-002a inputs unavailable
    ),

    DerivationRule(
        id="DR-003",
        target="ebt",
        formula="ebit - interest_expense",
        inputs=["ebit", "interest_expense"],
        confidence_mode="min",
        priority=2,
    ),

    DerivationRule(
        id="DR-004",
        target="net_income",
        formula="ebt - tax_expense",
        inputs=["ebt", "tax_expense"],
        confidence_mode="min",
        priority=3,
    ),

    DerivationRule(
        id="DR-005",
        target="ebitda_addbacks",
        formula="adjusted_ebitda - ebitda",
        inputs=["adjusted_ebitda", "ebitda"],
        confidence_mode="min",
        priority=3,
    ),

    # ─────────────────────────────────────────────────────────────────────────
    # Balance Sheet derived items
    # ─────────────────────────────────────────────────────────────────────────

    DerivationRule(
        id="DR-010",
        target="net_debt",
        formula="total_debt - cash",
        inputs=["total_debt", "cash"],
        confidence_mode="min",
        priority=1,
    ),

    DerivationRule(
        id="DR-011",
        target="net_working_capital",
        formula="total_current_assets - total_current_liabilities",
        inputs=["total_current_assets", "total_current_liabilities"],
        confidence_mode="min",
        priority=1,
    ),

    # ─────────────────────────────────────────────────────────────────────────
    # Cash Flow derived items
    # ─────────────────────────────────────────────────────────────────────────

    DerivationRule(
        id="DR-020",
        target="fcf",
        formula="cfo - capex",
        inputs=["cfo", "capex"],
        confidence_mode="min",
        priority=1,
    ),

    # ─────────────────────────────────────────────────────────────────────────
    # Key ratios — always compute (Tier 1 from audit)
    # ─────────────────────────────────────────────────────────────────────────

    DerivationRule(
        id="DR-030",
        target="debt_to_ebitda",
        formula="total_debt / ebitda",
        inputs=["total_debt", "ebitda"],
        confidence_mode="product",
        derivation_discount=0.95,
        priority=2,
        consistency_threshold=0.02,
    ),

    DerivationRule(
        id="DR-031",
        target="interest_coverage",
        formula="ebit / interest_expense",
        inputs=["ebit", "interest_expense"],
        confidence_mode="product",
        derivation_discount=0.95,
        priority=2,
        consistency_threshold=0.02,
    ),

    DerivationRule(
        id="DR-032",
        target="net_debt_to_ebitda",
        formula="net_debt / ebitda",
        inputs=["net_debt", "ebitda"],
        confidence_mode="product",
        derivation_discount=0.95,
        priority=3,  # depends on DR-010 (net_debt)
        consistency_threshold=0.02,
    ),

    DerivationRule(
        id="DR-033",
        target="gross_margin",
        formula="gross_profit / revenue",
        inputs=["gross_profit", "revenue"],
        confidence_mode="product",
        derivation_discount=0.95,
        priority=2,
        consistency_threshold=0.02,
    ),

    DerivationRule(
        id="DR-034",
        target="ebitda_margin",
        formula="ebitda / revenue",
        inputs=["ebitda", "revenue"],
        confidence_mode="product",
        derivation_discount=0.95,
        priority=3,
        consistency_threshold=0.02,
    ),

    DerivationRule(
        id="DR-035",
        target="net_margin_pct",
        formula="net_income / revenue",
        inputs=["net_income", "revenue"],
        confidence_mode="product",
        derivation_discount=0.95,
        priority=4,
        consistency_threshold=0.02,
    ),

    # ─────────────────────────────────────────────────────────────────────────
    # Project Finance (Tier 2 from audit)
    # ─────────────────────────────────────────────────────────────────────────

    DerivationRule(
        id="DR-040",
        target="dscr_project_finance",
        formula="cfads / debt_service",
        inputs=["cfads", "debt_service"],
        confidence_mode="product",
        derivation_discount=0.95,
        priority=2,
        model_types=["project_finance"],
        consistency_threshold=0.03,
    ),

    DerivationRule(
        id="DR-041",
        target="cfae",
        formula="cfads + debt_service",  # debt_service is negative in most models
        inputs=["cfads", "debt_service"],
        confidence_mode="min",
        priority=2,
        model_types=["project_finance"],
    ),

    DerivationRule(
        id="DR-042",
        target="dscr_corporate",
        formula="cfo / debt_service",
        inputs=["cfo", "debt_service"],
        confidence_mode="product",
        derivation_discount=0.95,
        priority=2,
        model_types=["corporate", "leveraged"],
        consistency_threshold=0.03,
    ),

    DerivationRule(
        id="DR-043",
        target="loan_to_cost",
        formula="total_debt / total_investment",
        inputs=["total_debt", "total_investment"],
        confidence_mode="product",
        derivation_discount=0.95,
        priority=2,
        model_types=["project_finance"],
    ),

    DerivationRule(
        id="DR-044",
        target="covenant_headroom",
        formula="dscr_project_finance - distribution_lock_up",
        inputs=["dscr_project_finance", "distribution_lock_up"],
        confidence_mode="min",
        priority=3,
        model_types=["project_finance"],
    ),

    # ─────────────────────────────────────────────────────────────────────────
    # Liquidity (Tier 1 from audit)
    # ─────────────────────────────────────────────────────────────────────────

    DerivationRule(
        id="DR-050",
        target="current_ratio",
        formula="total_current_assets / total_current_liabilities",
        inputs=["total_current_assets", "total_current_liabilities"],
        confidence_mode="product",
        derivation_discount=0.95,
        priority=2,
        consistency_threshold=0.02,
    ),

    # ─────────────────────────────────────────────────────────────────────────
    # Efficiency / Working Capital (Tier 1 from audit)
    # ─────────────────────────────────────────────────────────────────────────

    DerivationRule(
        id="DR-060",
        target="days_sales_outstanding",
        formula="accounts_receivable / revenue * 365",
        inputs=["accounts_receivable", "revenue"],
        confidence_mode="product",
        derivation_discount=0.95,
        priority=2,
    ),

    DerivationRule(
        id="DR-061",
        target="days_payable_outstanding",
        formula="accounts_payable / cogs * 365",
        inputs=["accounts_payable", "cogs"],
        confidence_mode="product",
        derivation_discount=0.95,
        priority=2,
    ),
]


def get_rules_for_model_type(model_type: Optional[str]) -> List[DerivationRule]:
    """Return rules applicable to a given model type.

    Rules with model_types=None apply to all models.
    Rules with a model_types list apply only when model_type matches.
    """
    result = []
    for rule in DERIVATION_RULES:
        if rule.model_types is None:
            result.append(rule)
        elif model_type and model_type.lower() in [m.lower() for m in rule.model_types]:
            result.append(rule)
    # Sort by priority (lowest first = computed first)
    return sorted(result, key=lambda r: r.priority)
