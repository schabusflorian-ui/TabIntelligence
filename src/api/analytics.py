"""Analytics API endpoints.

Cross-entity comparison, portfolio aggregation, trends,
taxonomy coverage, and cost tracking.
"""

from collections import defaultdict
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from src.api.rate_limit import limiter
from src.api.schemas import (
    AcceptSuggestionRequest,
    AcceptSuggestionResponse,
    AnomalyDetectionResponse,
    ConfidenceCalibrationResponse,
    CostAnalyticsResponse,
    CrossEntityComparisonResponse,
    EntityFinancialsResponse,
    EntityTrendsResponse,
    ExtractionFactResponse,
    FactsListResponse,
    MappingSuggestion,
    MultiPeriodComparisonResponse,
    PortfolioSummaryResponse,
    QualityTrendResponse,
    StructuredStatementResponse,
    SuggestionResponse,
    TaxonomyCoverageResponse,
    UnmappedLabelAggregationResponse,
)
from src.auth.dependencies import get_current_api_key
from src.core.exceptions import DatabaseError
from src.db import crud
from src.db.session import get_db

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


# ============================================================================
# GET /entity/{entity_id}/financials
# ============================================================================


@router.get(
    "/entity/{entity_id}/financials",
    response_model=EntityFinancialsResponse,
)
@limiter.limit("500/hour")
def entity_financials(
    request: Request,
    entity_id: str,
    canonical_names: Optional[str] = Query(
        None, description="Comma-separated canonical names to filter"
    ),
    period_start: Optional[str] = Query(None),
    period_end: Optional[str] = Query(None),
    statement_type: Optional[str] = Query(
        None,
        description="Filter by statement type (e.g. income_statement, balance_sheet, cash_flow)",
    ),
    limit: int = Query(100, ge=1, le=500, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Items to skip"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get financial data for an entity, grouped by canonical name and period."""
    try:
        entity_uuid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    entity = crud.get_entity(db, entity_uuid)
    if not entity:
        raise HTTPException(404, "Entity not found")

    name_list = (
        [n.strip() for n in canonical_names.split(",") if n.strip()] if canonical_names else None
    )

    try:
        facts = crud.get_entity_financials(
            db,
            entity_id=entity_uuid,
            canonical_names=name_list,
            period_start=period_start,
            period_end=period_end,
            statement_type=statement_type,
        )
    except DatabaseError:
        raise HTTPException(500, "Database error querying financials")

    source = "facts"
    if not facts:
        # JSON fallback: look for completed jobs linked to this entity
        facts_from_json = _financials_from_json(db, entity_uuid, name_list)
        if facts_from_json:
            return facts_from_json
        # No data at all — return empty
        return EntityFinancialsResponse(
            entity_id=entity_id,
            entity_name=entity.name,
            items=[],
            periods=[],
            source="none",
        )

    # Group facts by canonical_name -> period -> value
    grouped: dict = defaultdict(dict)
    all_periods: set = set()
    for f in facts:
        # Keep only the latest value per (canonical_name, period)
        key = f.canonical_name
        if f.period not in grouped[key]:
            grouped[key][f.period] = float(f.value)
            all_periods.add(f.period)

    all_items = []
    for cn in sorted(grouped):
        values = [{"period": p, "amount": grouped[cn][p]} for p in sorted(grouped[cn])]
        # Find taxonomy_category from any fact with this canonical_name
        cat = next(
            (f.taxonomy_category for f in facts if f.canonical_name == cn and f.taxonomy_category),
            None,
        )
        all_items.append(
            {
                "canonical_name": cn,
                "taxonomy_category": cat,
                "values": values,
            }
        )

    # Apply pagination
    total_items = len(all_items)
    items = all_items[offset : offset + limit]

    return EntityFinancialsResponse(
        entity_id=entity_id,
        entity_name=entity.name,
        items=items,  # type: ignore[arg-type]
        periods=sorted(all_periods),
        source=source,
        total_items=total_items,
    )


def _financials_from_json(
    db: Session,
    entity_id: UUID,
    canonical_names: Optional[List[str]],
) -> Optional[EntityFinancialsResponse]:
    """Fallback: build financials from ExtractionJob.result JSON."""
    from src.db.models import ExtractionJob, File, JobStatusEnum

    jobs = (
        db.query(ExtractionJob)
        .join(File, ExtractionJob.file_id == File.file_id)
        .filter(
            File.entity_id == entity_id,
            ExtractionJob.status == JobStatusEnum.COMPLETED,
            ExtractionJob.result.isnot(None),
        )
        .order_by(ExtractionJob.created_at.desc())
        .limit(5)
        .all()
    )
    if not jobs:
        return None

    grouped: dict = defaultdict(dict)
    all_periods: set = set()
    for job in jobs:
        for item in (job.result or {}).get("line_items", []):
            cn = item.get("canonical_name")
            if not cn or cn == "unmapped":
                continue
            if canonical_names and cn not in canonical_names:
                continue
            for period, value in (item.get("values") or {}).items():
                if period not in grouped[cn]:
                    try:
                        grouped[cn][period] = float(value)
                        all_periods.add(period)
                    except (ValueError, TypeError):
                        pass

    if not grouped:
        return None

    # Build canonical_name -> category lookup for enrichment
    from src.extraction.taxonomy_loader import load_taxonomy_json

    cn_to_cat: dict = {}
    try:
        tax_data = load_taxonomy_json()
        for cat, cat_items in tax_data.get("categories", {}).items():
            for ti in cat_items:
                cn_to_cat[ti["canonical_name"]] = cat
    except Exception:
        pass  # graceful fallback: taxonomy_category stays None

    items = []
    for cn in sorted(grouped):
        if not grouped[cn]:
            continue  # skip items where all values failed parsing
        values = [{"period": p, "amount": grouped[cn][p]} for p in sorted(grouped[cn])]
        items.append(
            {
                "canonical_name": cn,
                "taxonomy_category": cn_to_cat.get(cn),
                "values": values,
            }
        )

    return EntityFinancialsResponse(
        entity_id=str(entity_id),
        entity_name=None,
        items=items,  # type: ignore[arg-type]
        periods=sorted(all_periods),
        source="json_fallback",
    )


# ============================================================================
# GET /compare
# ============================================================================


@router.get("/compare", response_model=CrossEntityComparisonResponse)
@limiter.limit("500/hour")
def cross_entity_compare(
    request: Request,
    entity_ids: str = Query(..., description="Comma-separated entity UUIDs"),
    canonical_names: str = Query(..., description="Comma-separated canonical names"),
    period: Optional[str] = Query(None, description="Exact period string to compare"),
    period_normalized: Optional[str] = Query(
        None, description="Match on normalized period (e.g. FY2024)"
    ),
    year: Optional[str] = Query(None, description="Match by calendar year (e.g. 2024)"),
    include_metadata: bool = Query(False, description="Include normalization metadata"),
    target_currency: Optional[str] = Query(
        None, description="Convert all values to this currency (e.g. USD)"
    ),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Compare multiple entities on specific financial items.

    Supports three period matching modes:
    - period: exact raw period string match
    - period_normalized: match on normalized period (e.g. FY2024)
    - year: match any fact whose normalized period contains this year
    """
    if not period and not period_normalized and not year:
        raise HTTPException(400, "One of 'period', 'period_normalized', or 'year' is required")

    # Parse year as integer with a helpful error message
    year_int: Optional[int] = None
    if year is not None:
        try:
            year_int = int(year)
        except ValueError:
            raise HTTPException(
                400,
                f"'year' must be a number (e.g. 2024). "
                f"Use 'period_normalized' for values like '{year}'.",
            )

    try:
        id_list = [UUID(eid.strip()) for eid in entity_ids.split(",") if eid.strip()]
    except ValueError:
        raise HTTPException(400, "Invalid entity_id in list")

    if not id_list:
        raise HTTPException(400, "At least one entity_id is required")

    name_list = [n.strip() for n in canonical_names.split(",") if n.strip()]
    if not name_list:
        raise HTTPException(400, "At least one canonical_name is required")

    # Resolve entity objects (for name + metadata)
    entity_objs = {
        str(e.id): e for e in db.query(crud.Entity).filter(crud.Entity.id.in_(id_list)).all()
    }
    entity_names = {eid: e.name for eid, e in entity_objs.items()}

    try:
        facts = crud.get_cross_entity_comparison(
            db,
            entity_ids=id_list,
            canonical_names=name_list,
            period=period,
            period_normalized=period_normalized,
            year=year_int,
        )
    except DatabaseError:
        raise HTTPException(500, "Database error querying comparison")

    # Check fiscal year alignment
    normalization_notes: list[str] = []
    fye_values = set()
    for e in entity_objs.values():
        fye_values.add(e.fiscal_year_end or 12)
    if len(fye_values) > 1:
        details = ", ".join(
            f"{entity_objs[eid].name}={entity_objs[eid].fiscal_year_end or 12}"
            for eid in sorted(entity_objs.keys())
        )
        normalization_notes.append(
            f"Fiscal year ends differ: {details}. Period comparison may not be apples-to-apples."
        )

    if target_currency:
        normalization_notes.append(f"Values converted to {target_currency} where possible.")

    # Build comparison structure grouped by canonical_name
    grouped: dict = defaultdict(list)
    seen: set = set()
    for f in facts:
        key = (f.canonical_name, str(f.entity_id))
        if key in seen:
            continue
        seen.add(key)
        entity_obj = entity_objs.get(str(f.entity_id))
        ev = {
            "entity_id": str(f.entity_id),
            "entity_name": entity_names.get(str(f.entity_id)),
            "amount": float(f.value),
            "confidence": f.confidence,
        }
        if include_metadata or target_currency:
            ev["period_raw"] = f.period
            ev["period_normalized"] = f.period_normalized
            ev["currency_code"] = f.currency_code
            ev["source_unit"] = f.source_unit
            ev["fiscal_year_end"] = entity_obj.fiscal_year_end if entity_obj else None

        # Currency conversion
        if target_currency and f.currency_code and f.currency_code != target_currency:
            from src.normalization.fx_service import FxService

            fx = FxService()
            result = fx.convert(float(f.value), f.currency_code, target_currency, db)
            if result:
                ev["original_amount"] = ev["amount"]
                ev["amount"] = result["converted_amount"]
                ev["converted_amount"] = result["converted_amount"]
                ev["fx_rate_used"] = result["fx_rate_used"]
            else:
                ev["original_amount"] = ev["amount"]
                ev["converted_amount"] = None
                ev["fx_rate_used"] = None

        grouped[f.canonical_name].append(ev)

    # Build alignment warnings per comparison item
    comparisons = []
    for cn in name_list:
        entity_values = grouped.get(cn, [])
        seen_entity_ids = {ev["entity_id"] for ev in entity_values}
        for eid in id_list:
            if str(eid) not in seen_entity_ids:
                ev = {
                    "entity_id": str(eid),
                    "entity_name": entity_names.get(str(eid)),
                    "amount": None,
                    "confidence": None,
                }
                if include_metadata:
                    eo = entity_objs.get(str(eid))
                    ev["fiscal_year_end"] = eo.fiscal_year_end if eo else None
                entity_values.append(ev)

        alignment_warnings = []
        if len(fye_values) > 1:
            alignment_warnings.append("Fiscal year ends differ across compared entities")

        comparisons.append(
            {
                "canonical_name": cn,
                "period": period,
                "entities": entity_values,
                "alignment_warnings": alignment_warnings,
            }
        )

    return CrossEntityComparisonResponse(
        canonical_names=name_list,
        period=period,
        period_normalized=period_normalized,
        year=year,
        comparisons=comparisons,  # type: ignore[arg-type]
        normalization_notes=normalization_notes,
    )


# ============================================================================
# GET /portfolio/summary
# ============================================================================


@router.get("/portfolio/summary", response_model=PortfolioSummaryResponse)
@limiter.limit("500/hour")
def portfolio_summary(
    request: Request,
    entity_ids: Optional[str] = Query(
        None, description="Comma-separated entity UUIDs (all if omitted)"
    ),
    period: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Aggregate portfolio summary across entities."""
    id_list = None
    if entity_ids:
        try:
            id_list = [UUID(eid.strip()) for eid in entity_ids.split(",") if eid.strip()]
        except ValueError:
            raise HTTPException(400, "Invalid entity_id in list")

    try:
        summary = crud.get_portfolio_summary(db, entity_ids=id_list, period=period)
    except DatabaseError:
        raise HTTPException(500, "Database error computing portfolio summary")

    return PortfolioSummaryResponse(
        total_entities=summary["total_entities"],
        total_jobs=summary["total_jobs"],
        total_facts=summary["total_facts"],
        avg_confidence=summary["avg_confidence"],
        quality_distribution=[
            {"grade": q["grade"], "count": q["count"]}  # type: ignore[misc]
            for q in summary["quality_distribution"]
        ],
        period=period,
    )


# ============================================================================
# GET /entity/{entity_id}/trends
# ============================================================================


@router.get(
    "/entity/{entity_id}/trends",
    response_model=EntityTrendsResponse,
)
@limiter.limit("500/hour")
def entity_trends(
    request: Request,
    entity_id: str,
    canonical_name: str = Query(..., description="Canonical name to track"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get time-series trend for a specific item, including YoY change."""
    try:
        entity_uuid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    entity = crud.get_entity(db, entity_uuid)
    if not entity:
        raise HTTPException(404, "Entity not found")

    try:
        facts = crud.get_entity_trends(db, entity_id=entity_uuid, canonical_name=canonical_name)
    except DatabaseError:
        raise HTTPException(500, "Database error querying trends")

    # Deduplicate: keep latest fact per period
    seen_periods: dict = {}
    for f in facts:
        if f.period not in seen_periods:
            seen_periods[f.period] = float(f.value)

    # Build trend with YoY
    sorted_periods = sorted(seen_periods.keys())
    trend = []
    prev_amount = None
    for p in sorted_periods:
        amount = seen_periods[p]
        yoy = None
        if prev_amount is not None and prev_amount != 0:
            yoy = round((amount - prev_amount) / abs(prev_amount) * 100, 2)
        trend.append({"period": p, "amount": amount, "yoy_change_pct": yoy})
        prev_amount = amount

    return EntityTrendsResponse(
        entity_id=entity_id,
        canonical_name=canonical_name,
        trend=trend,  # type: ignore[arg-type]
    )


# ============================================================================
# GET /taxonomy/coverage
# ============================================================================


@router.get("/taxonomy/coverage", response_model=TaxonomyCoverageResponse)
@limiter.limit("500/hour")
def taxonomy_coverage(
    request: Request,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Taxonomy coverage analytics — which items are mapped and which aren't."""
    try:
        result = crud.get_taxonomy_coverage(db)
    except DatabaseError:
        raise HTTPException(500, "Database error computing taxonomy coverage")

    return TaxonomyCoverageResponse(
        total_taxonomy_items=result["total_taxonomy_items"],
        items_ever_mapped=result["items_ever_mapped"],
        coverage_pct=result["coverage_pct"],
        most_common=[
            {  # type: ignore[misc]
                "canonical_name": item["canonical_name"],
                "category": item["category"],
                "times_mapped": item["times_mapped"],
                "avg_confidence": item["avg_confidence"],
            }
            for item in result["most_common"]
        ],
        never_mapped=result["never_mapped"],
    )


# ============================================================================
# GET /costs
# ============================================================================


@router.get("/costs", response_model=CostAnalyticsResponse)
@limiter.limit("500/hour")
def cost_analytics(
    request: Request,
    entity_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="ISO date string"),
    date_to: Optional[str] = Query(None, description="ISO date string"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Cost analytics across extraction jobs."""
    entity_uuid = None
    if entity_id:
        try:
            entity_uuid = UUID(entity_id)
        except ValueError:
            raise HTTPException(400, "Invalid entity_id format")

    try:
        result = crud.get_cost_analytics(
            db,
            entity_id=entity_uuid,
            date_from=date_from,
            date_to=date_to,
        )
    except DatabaseError:
        raise HTTPException(500, "Database error computing cost analytics")

    return CostAnalyticsResponse(
        total_cost=result["total_cost"],
        total_jobs=result["total_jobs"],
        avg_cost_per_job=result["avg_cost_per_job"],
        cost_by_entity=[
            {  # type: ignore[misc]
                "entity_id": e["entity_id"],
                "entity_name": e["entity_name"],
                "total_cost": e["total_cost"],
                "job_count": e["job_count"],
            }
            for e in result["cost_by_entity"]
        ],
        cost_trend_daily=[
            {"date": d["date"], "cost": d["cost"], "job_count": d["job_count"]}  # type: ignore[misc]
            for d in result["cost_trend_daily"]
        ],
    )


# ============================================================================
# GET /facts — Query Decomposed Extraction Facts
# ============================================================================


@router.get("/facts", response_model=FactsListResponse)
@limiter.limit("500/hour")
def query_facts(
    request: Request,
    entity_id: Optional[str] = None,
    canonical_name: Optional[str] = None,
    period: Optional[str] = None,
    job_id: Optional[str] = None,
    min_confidence: Optional[float] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Query decomposed extraction facts with optional filters."""
    try:
        entity_uuid = UUID(entity_id) if entity_id else None
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    try:
        job_uuid = UUID(job_id) if job_id else None
    except ValueError:
        raise HTTPException(400, "Invalid job_id format")

    facts = crud.query_extraction_facts(
        db,
        entity_id=entity_uuid,
        canonical_name=canonical_name,
        period=period,
        job_id=job_uuid,
        min_confidence=min_confidence,
        limit=limit,
        offset=offset,
    )

    return FactsListResponse(
        facts=[
            ExtractionFactResponse(
                id=str(f.id),
                job_id=str(f.job_id),
                entity_id=str(f.entity_id) if f.entity_id else None,
                canonical_name=f.canonical_name,
                original_label=f.original_label,
                period=f.period,
                period_normalized=f.period_normalized,
                value=float(f.value),
                confidence=f.confidence,
                sheet_name=f.sheet_name,
                row_index=f.row_index,
                mapping_method=f.mapping_method,
                taxonomy_category=f.taxonomy_category,
                validation_passed=f.validation_passed,
                currency_code=f.currency_code,
                source_unit=f.source_unit,
                source_scale=f.source_scale,
                created_at=f.created_at.isoformat() if f.created_at else None,
            )
            for f in facts
        ],
        count=len(facts),
        limit=limit,
        offset=offset,
    )


# ============================================================================
# GET /entity/{entity_id}/statement — Structured Statement (Phase 7)
# ============================================================================

VALID_CATEGORIES = {
    "income_statement",
    "balance_sheet",
    "cash_flow",
    "debt_schedule",
    "metrics",
    "project_finance",
}


@router.get(
    "/entity/{entity_id}/statement",
    response_model=StructuredStatementResponse,
)
@limiter.limit("500/hour")
def entity_statement(
    request: Request,
    entity_id: str,
    category: str = Query(..., description="Statement category"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get a structured financial statement for an entity, organized by taxonomy hierarchy."""
    if category not in VALID_CATEGORIES:
        raise HTTPException(
            400,
            f"Invalid category '{category}'. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}",
        )

    try:
        entity_uuid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    entity = crud.get_entity(db, entity_uuid)
    if not entity:
        raise HTTPException(404, "Entity not found")

    try:
        result = crud.get_structured_statement(db, entity_uuid, category)
    except DatabaseError:
        raise HTTPException(500, "Database error querying structured statement")

    return StructuredStatementResponse(
        entity_id=entity_id,
        entity_name=result["entity_name"],
        category=result["category"],
        periods=result["periods"],
        items=result["items"],
        total_items=result["total_items"],
    )


# ============================================================================
# GET /entity/{entity_id}/compare-periods — Multi-Period Comparison (Phase 7)
# ============================================================================


@router.get(
    "/entity/{entity_id}/compare-periods",
    response_model=MultiPeriodComparisonResponse,
)
@limiter.limit("500/hour")
def compare_periods(
    request: Request,
    entity_id: str,
    canonical_names: str = Query(..., description="Comma-separated canonical names"),
    periods: str = Query(..., description="Comma-separated periods (e.g. FY2023,FY2024)"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Compare specific financial items across multiple periods with computed deltas."""
    try:
        entity_uuid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    entity = crud.get_entity(db, entity_uuid)
    if not entity:
        raise HTTPException(404, "Entity not found")

    name_list = [n.strip() for n in canonical_names.split(",") if n.strip()]
    if not name_list:
        raise HTTPException(400, "At least one canonical_name is required")

    period_list = [p.strip() for p in periods.split(",") if p.strip()]
    if not period_list:
        raise HTTPException(400, "At least one period is required")

    try:
        result = crud.get_multi_period_comparison(
            db,
            entity_id=entity_uuid,
            canonical_names=name_list,
            periods=period_list,
        )
    except DatabaseError:
        raise HTTPException(500, "Database error querying period comparison")

    return MultiPeriodComparisonResponse(
        entity_id=entity_id,
        entity_name=result["entity_name"],
        canonical_names=result["canonical_names"],
        periods=result["periods"],
        items=result["items"],
    )


# ============================================================================
# GET /confidence-calibration — Intelligence Layer
# ============================================================================


@router.get("/confidence-calibration", response_model=ConfidenceCalibrationResponse)
@limiter.limit("500/hour")
def confidence_calibration(
    request: Request,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Confidence calibration analytics.

    Returns bucketed accuracy data comparing predicted confidence
    to actual correctness (based on whether items were subsequently corrected).
    """
    try:
        result = crud.get_confidence_calibration(db)
    except DatabaseError:
        raise HTTPException(500, "Database error computing confidence calibration")

    return ConfidenceCalibrationResponse(
        buckets=result["buckets"],
        total_facts=result["total_facts"],
        total_corrections=result["total_corrections"],
    )


# ============================================================================
# GET /unmapped-labels — Taxonomy Gap Analysis
# ============================================================================


@router.get("/unmapped-labels", response_model=UnmappedLabelAggregationResponse)
@limiter.limit("500/hour")
def unmapped_label_aggregation(
    request: Request,
    min_occurrences: int = Query(1, ge=1, description="Minimum occurrence count"),
    min_entities: int = Query(1, ge=1, description="Min distinct entities with this label"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Cross-entity unmapped label aggregation for taxonomy gap analysis.

    Returns labels sorted by total occurrence count, showing which unmapped
    labels appear most frequently across entities — key signal for taxonomy gaps.
    """
    try:
        result = crud.get_unmapped_label_aggregation(
            db,
            min_occurrences=min_occurrences,
            min_entities=min_entities,
            limit=limit,
            offset=offset,
        )
    except DatabaseError:
        raise HTTPException(500, "Database error querying unmapped labels")

    return UnmappedLabelAggregationResponse(**result)


# ============================================================================
# GET /anomalies — Cross-Entity Anomaly Detection
# ============================================================================


@router.get("/anomalies", response_model=AnomalyDetectionResponse)
@limiter.limit("500/hour")
def detect_anomalies(
    request: Request,
    canonical_names: str = Query(..., description="Comma-separated canonical names"),
    period_normalized: Optional[str] = Query(None, description="Normalized period to analyze"),
    year: Optional[int] = Query(None, description="Year to analyze"),
    entity_ids: Optional[str] = Query(None, description="Scope to specific entity UUIDs"),
    method: str = Query("iqr", description="Detection method: 'iqr' or 'zscore'"),
    threshold: float = Query(1.5, description="IQR multiplier or Z-score threshold"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Detect outlier values across entities for given canonical names.

    Uses IQR (interquartile range) or Z-score methods to flag
    statistically unusual values relative to peers.
    """
    if method not in ("iqr", "zscore"):
        raise HTTPException(400, "method must be 'iqr' or 'zscore'")

    if not period_normalized and not year:
        raise HTTPException(400, "One of 'period_normalized' or 'year' is required")

    name_list = [n.strip() for n in canonical_names.split(",") if n.strip()]
    if not name_list:
        raise HTTPException(400, "At least one canonical_name is required")

    # Parse optional entity_ids filter
    eid_filter: Optional[List[UUID]] = None
    if entity_ids:
        try:
            eid_filter = [UUID(eid.strip()) for eid in entity_ids.split(",") if eid.strip()]
        except ValueError:
            raise HTTPException(400, "Invalid entity_id in list")

    # Query facts
    try:
        facts = crud.get_facts_for_anomaly_detection(
            db,
            canonical_names=name_list,
            period_normalized=period_normalized,
            year=year,
            entity_ids=eid_filter,
        )
    except DatabaseError:
        raise HTTPException(500, "Database error querying facts for anomaly detection")

    # Resolve entity names
    all_entity_ids = list({f.entity_id for f in facts if f.entity_id})
    entity_names = {}
    if all_entity_ids:
        entities = db.query(crud.Entity).filter(crud.Entity.id.in_(all_entity_ids)).all()
        entity_names = {str(e.id): e.name for e in entities}

    # Group facts by (canonical_name, period_normalized)
    from collections import defaultdict as dd

    groups: dict[tuple, list] = dd(list)
    for f in facts:
        key = (f.canonical_name, f.period_normalized or f.period)
        groups[key].append(f)

    # Run anomaly detection
    from src.normalization.anomaly_detection import detect_iqr_anomalies, detect_zscore_anomalies

    detector = detect_iqr_anomalies if method == "iqr" else detect_zscore_anomalies
    summaries = []
    total_outliers = 0
    total_items = 0

    for (cn, pn), group_facts in sorted(groups.items()):
        values = [
            (str(f.entity_id), entity_names.get(str(f.entity_id)), float(f.value))
            for f in group_facts
            if f.value is not None
        ]
        if len(values) < 3:
            continue

        results = detector(values, threshold)
        outlier_count = sum(1 for r in results if r.is_outlier)
        total_outliers += outlier_count
        total_items += len(results)

        items = [
            {
                "entity_id": r.entity_id,
                "entity_name": r.entity_name,
                "canonical_name": cn,
                "period": pn,
                "value": r.value,
                "is_outlier": r.is_outlier,
                "z_score": r.z_score,
                "iqr_distance": r.iqr_distance,
                "direction": r.direction,
            }
            for r in results
        ]

        summaries.append(
            {
                "canonical_name": cn,
                "period": pn,
                "peer_count": results[0].peer_count if results else 0,
                "peer_mean": results[0].peer_mean if results else 0,
                "peer_median": results[0].peer_median if results else 0,
                "outlier_count": outlier_count,
                "items": items,
            }
        )

    return AnomalyDetectionResponse(
        method=method,
        threshold=threshold,
        summaries=summaries,  # type: ignore[arg-type]
        total_outliers=total_outliers,
        total_items=total_items,
    )


# ============================================================================
# GET /unmapped-labels/{label}/suggestions — Taxonomy Gap Suggestions
# ============================================================================


@router.get(
    "/unmapped-labels/{label}/suggestions",
    response_model=SuggestionResponse,
)
@limiter.limit("500/hour")
def unmapped_label_suggestions(
    request: Request,
    label: str,
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get mapping suggestions for an unmapped label.

    Uses fuzzy matching against EntityPatterns, Taxonomy aliases,
    and LearnedAliases to suggest canonical name mappings.
    """
    from src.normalization.suggestion_engine import suggest_for_label

    results = suggest_for_label(db, label, limit=limit)

    return SuggestionResponse(
        label=label,
        suggestions=[MappingSuggestion(**s) for s in results],
    )


# ============================================================================
# POST /unmapped-labels/{label}/accept — Accept a Suggestion
# ============================================================================


@router.post(
    "/unmapped-labels/{label}/accept",
    response_model=AcceptSuggestionResponse,
)
@limiter.limit("200/hour")
def accept_unmapped_suggestion(
    request: Request,
    label: str,
    body: AcceptSuggestionRequest,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Accept a mapping suggestion: create EntityPattern and/or LearnedAlias.

    If entity_id is provided, creates an EntityPattern for that entity.
    Always creates or updates a LearnedAlias for the canonical mapping.
    """
    from src.db.models import EntityPattern, LearnedAlias, Taxonomy

    # Validate canonical_name exists in taxonomy
    taxonomy_item = (
        db.query(Taxonomy)
        .filter(Taxonomy.canonical_name == body.canonical_name)
        .first()
    )
    if not taxonomy_item:
        raise HTTPException(400, f"Unknown canonical name: {body.canonical_name}")

    pattern_created = False
    alias_created = False

    # Create EntityPattern if entity_id provided
    if body.entity_id:
        try:
            entity_uuid = UUID(body.entity_id)
        except ValueError:
            raise HTTPException(400, f"Invalid entity_id: {body.entity_id}")

        existing = (
            db.query(EntityPattern)
            .filter(
                EntityPattern.entity_id == entity_uuid,
                EntityPattern.original_label == label,
                EntityPattern.canonical_name == body.canonical_name,
            )
            .first()
        )
        if not existing:
            from datetime import datetime, timezone

            pattern = EntityPattern(
                entity_id=entity_uuid,
                original_label=label,
                canonical_name=body.canonical_name,
                confidence=0.85,
                created_by="user_correction",
                last_seen=datetime.now(timezone.utc),
            )
            db.add(pattern)
            pattern_created = True

    # Create or update LearnedAlias
    existing_alias = (
        db.query(LearnedAlias)
        .filter(
            LearnedAlias.canonical_name == body.canonical_name,
            LearnedAlias.alias_text == label,
        )
        .first()
    )
    if existing_alias:
        existing_alias.occurrence_count += 1
    else:
        alias = LearnedAlias(
            canonical_name=body.canonical_name,
            alias_text=label,
            occurrence_count=1,
        )
        db.add(alias)
        alias_created = True

    db.commit()

    return AcceptSuggestionResponse(
        label=label,
        canonical_name=body.canonical_name,
        pattern_created=pattern_created,
        alias_created=alias_created,
    )


# ============================================================================
# GET /entity/{entity_id}/quality-trend — Quality Grade Trending
# ============================================================================


@router.get(
    "/entity/{entity_id}/quality-trend",
    response_model=QualityTrendResponse,
)
@limiter.limit("500/hour")
def entity_quality_trend(
    request: Request,
    entity_id: str,
    limit: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get quality grade trend over time for an entity."""
    try:
        entity_uuid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    entity = crud.get_entity(db, entity_uuid)
    if not entity:
        raise HTTPException(404, "Entity not found")

    snapshots = crud.get_quality_trend(db, entity_uuid, limit=limit)

    return QualityTrendResponse(
        entity_id=str(entity.id),
        entity_name=entity.name,
        snapshots=snapshots,
    )
