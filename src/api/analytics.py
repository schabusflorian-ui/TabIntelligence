"""Analytics API endpoints.

Cross-entity comparison, portfolio aggregation, trends,
taxonomy coverage, and cost tracking.
"""
from collections import defaultdict
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from uuid import UUID

from src.api.schemas import (
    CostAnalyticsResponse,
    CrossEntityComparisonResponse,
    EntityFinancialsResponse,
    EntityTrendsResponse,
    ExtractionFactResponse,
    FactsListResponse,
    PortfolioSummaryResponse,
    TaxonomyCoverageResponse,
)
from src.db.session import get_db
from src.db import crud
from src.auth.dependencies import get_current_api_key
from src.api.rate_limit import limiter
from src.core.exceptions import DatabaseError
from src.core.logging import api_logger as logger

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
        None, description="Filter by statement type (e.g. income_statement, balance_sheet, cash_flow)"
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
        [n.strip() for n in canonical_names.split(",") if n.strip()]
        if canonical_names
        else None
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
        values = [
            {"period": p, "amount": grouped[cn][p]}
            for p in sorted(grouped[cn])
        ]
        # Find taxonomy_category from any fact with this canonical_name
        cat = next(
            (f.taxonomy_category for f in facts if f.canonical_name == cn and f.taxonomy_category),
            None,
        )
        all_items.append({
            "canonical_name": cn,
            "taxonomy_category": cat,
            "values": values,
        })

    # Apply pagination
    total_items = len(all_items)
    items = all_items[offset:offset + limit]

    return EntityFinancialsResponse(
        entity_id=entity_id,
        entity_name=entity.name,
        items=items,
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
    from src.db.models import File, ExtractionJob, JobStatusEnum

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

    items = []
    for cn in sorted(grouped):
        if not grouped[cn]:
            continue  # skip items where all values failed parsing
        values = [
            {"period": p, "amount": grouped[cn][p]}
            for p in sorted(grouped[cn])
        ]
        items.append({
            "canonical_name": cn,
            "taxonomy_category": None,
            "values": values,
        })

    return EntityFinancialsResponse(
        entity_id=str(entity_id),
        entity_name=None,
        items=items,
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
    period: str = Query(..., description="Period string to compare"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Compare multiple entities on specific financial items for a given period."""
    try:
        id_list = [UUID(eid.strip()) for eid in entity_ids.split(",") if eid.strip()]
    except ValueError:
        raise HTTPException(400, "Invalid entity_id in list")

    if not id_list:
        raise HTTPException(400, "At least one entity_id is required")

    name_list = [n.strip() for n in canonical_names.split(",") if n.strip()]
    if not name_list:
        raise HTTPException(400, "At least one canonical_name is required")

    # Resolve entity names
    entities = {
        str(e.id): e.name
        for e in db.query(crud.Entity).filter(crud.Entity.id.in_(id_list)).all()
    }

    try:
        facts = crud.get_cross_entity_comparison(
            db,
            entity_ids=id_list,
            canonical_names=name_list,
            period=period,
        )
    except DatabaseError:
        raise HTTPException(500, "Database error querying comparison")

    # Build comparison structure
    # Group by canonical_name -> list of entity values
    grouped: dict = defaultdict(list)
    seen: set = set()
    for f in facts:
        key = (f.canonical_name, str(f.entity_id))
        if key in seen:
            continue  # keep first (latest) only
        seen.add(key)
        grouped[f.canonical_name].append({
            "entity_id": str(f.entity_id),
            "entity_name": entities.get(str(f.entity_id)),
            "amount": float(f.value),
            "confidence": f.confidence,
        })

    # Ensure all entities appear even if no facts
    comparisons = []
    for cn in name_list:
        entity_values = grouped.get(cn, [])
        seen_entity_ids = {ev["entity_id"] for ev in entity_values}
        for eid in id_list:
            if str(eid) not in seen_entity_ids:
                entity_values.append({
                    "entity_id": str(eid),
                    "entity_name": entities.get(str(eid)),
                    "amount": None,
                    "confidence": None,
                })
        comparisons.append({
            "canonical_name": cn,
            "period": period,
            "entities": entity_values,
        })

    return CrossEntityComparisonResponse(
        canonical_names=name_list,
        period=period,
        comparisons=comparisons,
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
            {"grade": q["grade"], "count": q["count"]}
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
        trend=trend,
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
            {
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
            {
                "entity_id": e["entity_id"],
                "entity_name": e["entity_name"],
                "total_cost": e["total_cost"],
                "job_count": e["job_count"],
            }
            for e in result["cost_by_entity"]
        ],
        cost_trend_daily=[
            {"date": d["date"], "cost": d["cost"], "job_count": d["job_count"]}
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
                created_at=f.created_at.isoformat() if f.created_at else None,
            )
            for f in facts
        ],
        count=len(facts),
        limit=limit,
        offset=offset,
    )
