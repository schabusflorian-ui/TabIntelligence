"""Dead Letter Queue admin API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from src.api.rate_limit import limiter
from src.auth.dependencies import get_current_api_key
from src.core.exceptions import DatabaseError
from src.core.logging import api_logger as logger
from src.db import crud
from src.db.session import get_db

router = APIRouter(prefix="/api/v1/admin/dlq", tags=["admin-dlq"])


@router.get("/")
@limiter.limit("500/hour")
def list_dlq_entries(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    only_unreplayed: bool = Query(False),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """List dead letter queue entries."""
    try:
        entries = crud.list_dlq_entries(
            db, limit=limit, offset=offset, only_unreplayed=only_unreplayed
        )
        return {
            "count": len(entries),
            "entries": [
                {
                    "dlq_id": str(e.dlq_id),
                    "task_id": e.task_id,
                    "task_name": e.task_name,
                    "error": e.error,
                    "replayed": e.replayed,
                    "replayed_at": e.replayed_at.isoformat() if e.replayed_at else None,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in entries
            ],
        }
    except DatabaseError as e:
        logger.error(f"Database error listing DLQ entries: {str(e)}")
        raise HTTPException(500, "Database error listing DLQ entries")


@router.get("/{dlq_id}")
def get_dlq_entry(
    dlq_id: str,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get a specific DLQ entry with full details including traceback."""
    try:
        dlq_uuid = UUID(dlq_id)
    except ValueError:
        raise HTTPException(400, "Invalid dlq_id format")

    try:
        entry = crud.get_dlq_entry(db, dlq_uuid)
        if not entry:
            raise HTTPException(404, "DLQ entry not found")

        return {
            "dlq_id": str(entry.dlq_id),
            "task_id": entry.task_id,
            "task_name": entry.task_name,
            "task_args": entry.task_args,
            "task_kwargs": entry.task_kwargs,
            "error": entry.error,
            "traceback": entry.traceback,
            "replayed": entry.replayed,
            "replayed_at": entry.replayed_at.isoformat() if entry.replayed_at else None,
            "replayed_task_id": entry.replayed_task_id,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
    except DatabaseError as e:
        logger.error(f"Database error getting DLQ entry: {str(e)}")
        raise HTTPException(500, "Database error getting DLQ entry")


@router.post("/{dlq_id}/replay")
@limiter.limit("20/hour")
def replay_dlq_entry(
    request: Request,
    dlq_id: str,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Replay a failed task from the DLQ."""
    try:
        dlq_uuid = UUID(dlq_id)
    except ValueError:
        raise HTTPException(400, "Invalid dlq_id format")

    try:
        entry = crud.get_dlq_entry(db, dlq_uuid)
        if not entry:
            raise HTTPException(404, "DLQ entry not found")

        from src.jobs.celery_app import celery_app

        task = celery_app.send_task(
            entry.task_name,
            args=entry.task_args,
            kwargs=entry.task_kwargs,
            queue="extraction",
        )
        crud.mark_dlq_entry_replayed(db, dlq_uuid, str(task.id))

        logger.info(f"DLQ entry {dlq_id} replayed as task {task.id}")

        return {
            "dlq_id": dlq_id,
            "new_task_id": str(task.id),
            "status": "replayed",
        }

    except HTTPException:
        raise
    except DatabaseError as e:
        logger.error(f"Database error replaying DLQ entry: {str(e)}")
        raise HTTPException(500, "Database error replaying DLQ entry")
    except Exception as e:
        logger.error(f"Failed to replay DLQ entry {dlq_id}: {e}")
        raise HTTPException(500, f"Replay failed: {str(e)}")


@router.delete("/{dlq_id}", status_code=204)
def delete_dlq_entry(
    dlq_id: str,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Delete a DLQ entry."""
    try:
        dlq_uuid = UUID(dlq_id)
    except ValueError:
        raise HTTPException(400, "Invalid dlq_id format")

    try:
        deleted = crud.delete_dlq_entry(db, dlq_uuid)
        if not deleted:
            raise HTTPException(404, "DLQ entry not found")
        return None
    except DatabaseError as e:
        logger.error(f"Database error deleting DLQ entry: {str(e)}")
        raise HTTPException(500, "Database error deleting DLQ entry")
