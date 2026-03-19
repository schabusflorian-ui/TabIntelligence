"""Taxonomy API endpoints for browsing and searching canonical line items."""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.api.schemas import (
    ChangelogResponse,
    DeprecateResponse,
    HierarchyNode,
    TaxonomyItemResponse,
    TaxonomyListResponse,
    TaxonomySearchResponse,
    TaxonomyStatsResponse,
)
from src.auth.dependencies import get_current_api_key
from src.db.session import get_db
from src.guidelines.taxonomy import TaxonomyManager


# ============================================================================
# Suggestion Response Models
# ============================================================================


class TaxonomySuggestionResponse(BaseModel):
    id: UUID
    suggestion_type: str
    canonical_name: Optional[str] = None
    suggested_text: str
    evidence_count: int
    evidence_jobs: Optional[list] = None
    status: str
    created_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TaxonomySuggestionListResponse(BaseModel):
    count: int
    suggestions: List[TaxonomySuggestionResponse]

router = APIRouter(prefix="/api/v1/taxonomy", tags=["taxonomy"])

# Separate router for /{canonical_name} wildcard routes.  Must be included
# AFTER ``router`` in main.py so that fixed paths (/suggestions, /changelog,
# /stats, etc.) are matched before the wildcard.  Starlette's trie-based
# routing can otherwise prefer path-parameter routes over exact-match siblings
# registered on the same router.
detail_router = APIRouter(prefix="/api/v1/taxonomy", tags=["taxonomy"])

_manager = TaxonomyManager()


@router.get("/", response_model=TaxonomyListResponse)
def list_taxonomy(
    category: Optional[str] = Query(None, description="Filter by category"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """List all taxonomy items, optionally filtered by category."""
    if category:
        items = _manager.get_by_category(db, category)
    else:
        items = _manager.get_all(db)

    return {
        "count": len(items),
        "items": [
            {
                "canonical_name": item.canonical_name,
                "category": item.category,
                "display_name": item.display_name,
                "aliases": item.aliases or [],
                "definition": item.definition,
                "typical_sign": item.typical_sign,
                "parent_canonical": item.parent_canonical,
                "validation_rules": item.validation_rules,
            }
            for item in items
        ],
    }


@router.get("/stats", response_model=TaxonomyStatsResponse)
def taxonomy_stats(
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get taxonomy statistics by category."""
    return _manager.get_statistics(db)


@router.get("/search", response_model=TaxonomySearchResponse)
def search_taxonomy(
    q: str = Query(..., min_length=1, description="Search query"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Search taxonomy by canonical name or alias."""
    results = _manager.search(db, q)
    return {
        "query": q,
        "count": len(results),
        "items": [
            {
                "canonical_name": item.canonical_name,
                "category": item.category,
                "display_name": item.display_name,
                "aliases": item.aliases or [],
                "definition": item.definition,
                "typical_sign": item.typical_sign,
            }
            for item in results
        ],
    }


@router.get("/hierarchy", response_model=Dict[str, HierarchyNode])
def taxonomy_hierarchy(
    category: Optional[str] = Query(None, description="Filter by category"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get taxonomy as a recursive parent-child hierarchy."""

    def _serialize_node(node):
        item = node["item"]
        return {
            "canonical_name": item.canonical_name,
            "display_name": item.display_name,
            "category": item.category,
            "typical_sign": item.typical_sign,
            "children": [_serialize_node(child) for child in node["children"]],
        }

    hierarchy = _manager.get_hierarchy(db, category)
    return {name: _serialize_node(data) for name, data in hierarchy.items()}


# ============================================================================
# Taxonomy Suggestion Endpoints
# ============================================================================


@router.get("/suggestions", response_model=TaxonomySuggestionListResponse)
def list_suggestions(
    status: Optional[str] = Query(None, description="Filter by status: pending, accepted, rejected"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """List taxonomy improvement suggestions, optionally filtered by status."""
    from src.db.crud import list_taxonomy_suggestions

    suggestions = list_taxonomy_suggestions(db, status=status)
    return {
        "count": len(suggestions),
        "suggestions": [
            TaxonomySuggestionResponse.model_validate(s) for s in suggestions
        ],
    }


@router.post(
    "/suggestions/{suggestion_id}/accept",
    response_model=TaxonomySuggestionResponse,
)
def accept_suggestion(
    suggestion_id: UUID,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Accept a pending taxonomy suggestion."""
    from src.db.crud import accept_taxonomy_suggestion

    try:
        suggestion = accept_taxonomy_suggestion(db, suggestion_id)
        return TaxonomySuggestionResponse.model_validate(suggestion)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/suggestions/{suggestion_id}/reject",
    response_model=TaxonomySuggestionResponse,
)
def reject_suggestion(
    suggestion_id: UUID,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Reject a pending taxonomy suggestion."""
    from src.db.crud import reject_taxonomy_suggestion

    try:
        suggestion = reject_taxonomy_suggestion(db, suggestion_id)
        return TaxonomySuggestionResponse.model_validate(suggestion)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Taxonomy Governance (Deprecation & Changelog)
# ============================================================================


@router.get("/changelog", response_model=ChangelogResponse)
def get_changelog(
    canonical_name: Optional[str] = Query(None, description="Filter by canonical name"),
    limit: int = Query(100, ge=1, le=500, description="Max entries to return"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get taxonomy changelog entries, optionally filtered by canonical_name."""
    from src.api.schemas import ChangelogEntry
    from src.db.crud import get_taxonomy_changelog

    entries = get_taxonomy_changelog(db, canonical_name=canonical_name, limit=limit)
    return ChangelogResponse(
        count=len(entries),
        entries=[
            ChangelogEntry(
                id=str(e.id),
                canonical_name=e.canonical_name,
                field_name=e.field_name,
                old_value=e.old_value,
                new_value=e.new_value,
                changed_by=e.changed_by,
                taxonomy_version=e.taxonomy_version,
                created_at=e.created_at.isoformat() if e.created_at else "",
            )
            for e in entries
        ],
    )


@detail_router.post("/{canonical_name}/deprecate", response_model=DeprecateResponse)
def deprecate_item(
    canonical_name: str,
    redirect_to: Optional[str] = Query(None, description="Redirect to this canonical name"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Deprecate a taxonomy item, optionally redirecting to another."""
    from src.db.crud import deprecate_taxonomy_item

    try:
        item = deprecate_taxonomy_item(
            db,
            canonical_name=canonical_name,
            redirect_to=redirect_to,
            deprecated_by="api",
        )
        return DeprecateResponse(
            canonical_name=item.canonical_name,
            deprecated=item.deprecated,
            deprecated_redirect=item.deprecated_redirect,
            deprecated_at=item.deprecated_at.isoformat() if item.deprecated_at else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@detail_router.get("/{canonical_name}", response_model=TaxonomyItemResponse)
def get_taxonomy_item(
    canonical_name: str,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get a specific taxonomy item by canonical name."""
    item = _manager.get_by_canonical_name(db, canonical_name)
    if not item:
        raise HTTPException(status_code=404, detail=f"Taxonomy item '{canonical_name}' not found")

    return {
        "canonical_name": item.canonical_name,
        "category": item.category,
        "display_name": item.display_name,
        "aliases": item.aliases or [],
        "definition": item.definition,
        "typical_sign": item.typical_sign,
        "parent_canonical": item.parent_canonical,
        "validation_rules": item.validation_rules,
        "deprecated": getattr(item, 'deprecated', False),
        "deprecated_redirect": getattr(item, 'deprecated_redirect', None),
        "deprecated_at": getattr(item, 'deprecated_at', None).isoformat() if getattr(item, 'deprecated_at', None) else None,
    }
