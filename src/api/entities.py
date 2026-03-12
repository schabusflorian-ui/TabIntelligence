"""Entity CRUD API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from uuid import UUID

from src.api.schemas import (
    EntityCreateRequest, EntityDetailResponse, EntityListResponse,
    EntityResponse, UpdateEntityRequest,
)
from src.db.session import get_db
from src.db import crud
from src.auth.dependencies import get_current_api_key, require_entity_scope
from src.api.rate_limit import limiter
from src.core.exceptions import DatabaseError
from src.core.logging import api_logger as logger

router = APIRouter(prefix="/api/v1/entities", tags=["entities"])


@router.get("/", response_model=EntityListResponse)
@limiter.limit("500/hour")
def list_entities(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """List all entities with pagination."""
    try:
        entities = crud.list_entities(db, limit=limit, offset=offset)
        return {
            "count": len(entities),
            "entities": [
                {
                    "id": str(e.id),
                    "name": e.name,
                    "industry": e.industry,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in entities
            ],
        }
    except DatabaseError as e:
        logger.error(f"Database error listing entities: {str(e)}")
        raise HTTPException(500, "Database error listing entities")


@router.post("/", status_code=201, response_model=EntityResponse)
@limiter.limit("100/hour")
def create_entity(
    request: Request,
    body: EntityCreateRequest,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Create a new entity."""
    try:
        entity = crud.create_entity(db, name=body.name, industry=body.industry)
        return {
            "id": str(entity.id),
            "name": entity.name,
            "industry": entity.industry,
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
        }
    except DatabaseError as e:
        logger.error(f"Database error creating entity: {str(e)}")
        raise HTTPException(500, "Database error creating entity")


@router.get("/{entity_id}", response_model=EntityDetailResponse)
def get_entity(
    entity_id: str,
    db: Session = Depends(get_db),
    _api_key=Depends(require_entity_scope),
):
    """Get entity by ID with pattern and file counts."""
    try:
        entity_uuid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    try:
        entity = crud.get_entity(db, entity_uuid)
        if not entity:
            raise HTTPException(404, "Entity not found")

        patterns_count = len(entity.entity_patterns) if entity.entity_patterns else 0

        # Count files linked to this entity
        from src.db.models import File
        files_count = db.query(File).filter(File.entity_id == entity_uuid).count()

        return {
            "id": str(entity.id),
            "name": entity.name,
            "industry": entity.industry,
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
            "patterns_count": patterns_count,
            "files_count": files_count,
        }
    except DatabaseError as e:
        logger.error(f"Database error getting entity: {str(e)}")
        raise HTTPException(500, "Database error getting entity")


@router.patch("/{entity_id}", response_model=EntityResponse)
def update_entity(
    entity_id: str,
    body: UpdateEntityRequest,
    db: Session = Depends(get_db),
    _api_key=Depends(require_entity_scope),
):
    """Update an entity's name and/or industry."""
    try:
        entity_uuid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    if body.name is None and body.industry is None:
        raise HTTPException(400, "At least one of 'name' or 'industry' must be provided")

    try:
        entity = crud.update_entity(db, entity_uuid, name=body.name, industry=body.industry)
        return {
            "id": str(entity.id),
            "name": entity.name,
            "industry": entity.industry,
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
        }
    except DatabaseError as e:
        if "not found" in str(e).lower():
            raise HTTPException(404, "Entity not found")
        logger.error(f"Database error updating entity: {str(e)}")
        raise HTTPException(500, "Database error updating entity")


@router.delete("/{entity_id}", status_code=204)
def delete_entity(
    entity_id: str,
    db: Session = Depends(get_db),
    _api_key=Depends(require_entity_scope),
):
    """Delete an entity and its associated patterns."""
    try:
        entity_uuid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    try:
        deleted = crud.delete_entity(db, entity_uuid)
        if not deleted:
            raise HTTPException(404, "Entity not found")
        return None
    except DatabaseError as e:
        logger.error(f"Database error deleting entity: {str(e)}")
        raise HTTPException(500, "Database error deleting entity")
