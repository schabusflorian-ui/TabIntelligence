"""File management API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID

from src.db.session import get_db
from src.db import crud
from src.auth.dependencies import get_current_api_key
from src.core.exceptions import DatabaseError
from src.core.logging import api_logger as logger

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.get("/")
def list_files(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """List uploaded files with pagination."""
    try:
        files = crud.list_files(db, limit=limit, offset=offset)
        return {
            "count": len(files),
            "limit": limit,
            "offset": offset,
            "items": [_serialize_file(f) for f in files],
        }
    except DatabaseError as e:
        logger.error(f"Database error listing files: {str(e)}")
        raise HTTPException(500, "Database error listing files")


@router.get("/{file_id}")
def get_file(
    file_id: str,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get file metadata by ID."""
    try:
        file_uuid = UUID(file_id)
    except ValueError:
        raise HTTPException(400, "Invalid file_id format")

    try:
        file = crud.get_file(db, file_uuid)
        if not file:
            raise HTTPException(404, "File not found")
        return _serialize_file(file)
    except DatabaseError as e:
        logger.error(f"Database error getting file: {str(e)}")
        raise HTTPException(500, "Database error getting file")


def _serialize_file(file) -> dict:
    """Serialize a File record for API response."""
    return {
        "file_id": str(file.file_id),
        "filename": file.filename,
        "file_size": file.file_size,
        "s3_key": file.s3_key,
        "content_hash": file.content_hash,
        "entity_id": str(file.entity_id) if file.entity_id else None,
        "uploaded_at": file.uploaded_at.isoformat() if file.uploaded_at else None,
    }
