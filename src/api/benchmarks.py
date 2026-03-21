"""Benchmark API endpoints for viewing accuracy trends and category heatmaps."""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.api.schemas import (
    BenchmarkHeatmapResponse,
    BenchmarkRunResponse,
    BenchmarkTrendsResponse,
)
from src.auth.dependencies import get_current_api_key
from src.db.session import get_db

router = APIRouter(prefix="/api/v1/benchmarks", tags=["benchmarks"])


@router.get("/trends", response_model=BenchmarkTrendsResponse)
def get_trends(
    fixture_name: Optional[str] = Query(None, description="Filter by fixture name"),
    limit: int = Query(50, ge=1, le=200, description="Max runs to return"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get benchmark accuracy trends over time.

    Returns mapping F1, precision, recall, triage accuracy, and value
    tolerance match rate for each run, ordered by date descending.
    """
    from src.db.crud import get_benchmark_trends

    runs = get_benchmark_trends(db, fixture_name=fixture_name, limit=limit)
    return BenchmarkTrendsResponse(
        fixture_name=fixture_name,
        count=len(runs),
        runs=[BenchmarkRunResponse(**r) for r in runs],
    )


@router.get("/category-heatmap", response_model=BenchmarkHeatmapResponse)
def get_category_heatmap(
    fixture_name: Optional[str] = Query(None, description="Filter by fixture name"),
    limit: int = Query(10, ge=1, le=50, description="Max runs for heatmap columns"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get category-level accuracy as a heatmap.

    Categories (income_statement, balance_sheet, etc.) as rows,
    recent benchmark runs as columns. Each cell contains the F1 score.
    """
    from src.db.crud import get_benchmark_category_heatmap

    return get_benchmark_category_heatmap(db, fixture_name=fixture_name, limit=limit)
