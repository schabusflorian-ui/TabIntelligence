"""Taxonomy API endpoints for browsing and searching canonical line items."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from src.db.session import get_db
from src.auth.dependencies import get_current_api_key
from src.guidelines.taxonomy import TaxonomyManager

router = APIRouter(prefix="/api/v1/taxonomy", tags=["taxonomy"])

_manager = TaxonomyManager()


@router.get("/")
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


@router.get("/stats")
def taxonomy_stats(
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get taxonomy statistics by category."""
    return _manager.get_statistics(db)


@router.get("/search")
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


@router.get("/hierarchy")
def taxonomy_hierarchy(
    category: Optional[str] = Query(None, description="Filter by category"),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get taxonomy as a parent-child hierarchy."""
    hierarchy = _manager.get_hierarchy(db, category)
    result = {}
    for name, data in hierarchy.items():
        result[name] = {
            "canonical_name": data["item"].canonical_name,
            "display_name": data["item"].display_name,
            "category": data["item"].category,
            "children": [
                {
                    "canonical_name": child.canonical_name,
                    "display_name": child.display_name,
                }
                for child in data["children"]
            ],
        }
    return result


@router.get("/{canonical_name}")
def get_taxonomy_item(
    canonical_name: str,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get a specific taxonomy item by canonical name."""
    item = _manager.get_by_canonical_name(db, canonical_name)
    if not item:
        from fastapi import HTTPException
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
    }
