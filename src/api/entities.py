"""Entity CRUD API endpoints."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from src.api.rate_limit import limiter
from src.api.schemas import (
    EntityCreateRequest,
    EntityDetailResponse,
    EntityListResponse,
    EntityResponse,
    JobListResponse,
    UpdateEntityRequest,
)
from src.auth.dependencies import get_current_api_key, require_entity_scope
from src.core.exceptions import DatabaseError
from src.core.logging import api_logger as logger
from src.db import crud
from src.db.session import get_db

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
                    "fiscal_year_end": e.fiscal_year_end,
                    "default_currency": e.default_currency,
                    "reporting_standard": e.reporting_standard,
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
        entity = crud.create_entity(
            db,
            name=body.name,
            industry=body.industry,
            fiscal_year_end=body.fiscal_year_end,
            default_currency=body.default_currency,
            reporting_standard=body.reporting_standard,
        )
        return {
            "id": str(entity.id),
            "name": entity.name,
            "industry": entity.industry,
            "fiscal_year_end": entity.fiscal_year_end,
            "default_currency": entity.default_currency,
            "reporting_standard": entity.reporting_standard,
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
            "fiscal_year_end": entity.fiscal_year_end,
            "default_currency": entity.default_currency,
            "reporting_standard": entity.reporting_standard,
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

    update_fields = {
        k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None
    }
    if not update_fields:
        raise HTTPException(400, "At least one field must be provided")

    try:
        entity = crud.update_entity(
            db,
            entity_uuid,
            name=body.name,
            industry=body.industry,
            fiscal_year_end=body.fiscal_year_end,
            default_currency=body.default_currency,
            reporting_standard=body.reporting_standard,
        )
        return {
            "id": str(entity.id),
            "name": entity.name,
            "industry": entity.industry,
            "fiscal_year_end": entity.fiscal_year_end,
            "default_currency": entity.default_currency,
            "reporting_standard": entity.reporting_standard,
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
        }
    except DatabaseError as e:
        if "not found" in str(e).lower():
            raise HTTPException(404, "Entity not found")
        logger.error(f"Database error updating entity: {str(e)}")
        raise HTTPException(500, "Database error updating entity")


@router.get("/{entity_id}/jobs", response_model=JobListResponse)
@limiter.limit("500/hour")
def get_entity_jobs(
    request: Request,
    entity_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """List extraction jobs for a specific entity."""
    try:
        entity_uuid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    entity = crud.get_entity(db, entity_uuid)
    if not entity:
        raise HTTPException(404, "Entity not found")

    status_enum = None
    if status:
        try:
            from src.db.models import JobStatusEnum

            status_enum = JobStatusEnum(status)
        except ValueError:
            raise HTTPException(400, "Invalid status")

    try:
        jobs = crud.get_entity_jobs(
            db, entity_uuid, limit=limit, offset=offset, status=status_enum
        )
        return {
            "count": len(jobs),
            "limit": limit,
            "offset": offset,
            "jobs": [
                {
                    "job_id": str(j.job_id),
                    "file_id": str(j.file_id),
                    "status": j.status.value,
                    "current_stage": j.current_stage,
                    "progress_percent": j.progress_percent,
                    "error": j.error,
                    "filename": j.file.filename if j.file else None,
                    "entity_id": entity_id,
                    "entity_name": entity.name,
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                    "updated_at": j.updated_at.isoformat() if j.updated_at else None,
                }
                for j in jobs
            ],
        }
    except DatabaseError as e:
        logger.error(f"Database error getting entity jobs: {str(e)}")
        raise HTTPException(500, "Database error getting entity jobs")


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
