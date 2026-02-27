"""Job management API endpoints (lineage)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from src.db.session import get_db
from src.db import crud
from src.auth.dependencies import get_current_api_key
from src.core.exceptions import DatabaseError
from src.core.logging import api_logger as logger

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/{job_id}/lineage")
def get_job_lineage(
    job_id: str,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get lineage events for a job, showing the full extraction audit trail."""
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job_id format")

    try:
        job = crud.get_job(db, job_uuid)
        if not job:
            raise HTTPException(404, "Job not found")

        events = crud.get_job_lineage(db, job_uuid)
        return {
            "job_id": job_id,
            "status": job.status.value,
            "events_count": len(events),
            "events": [
                {
                    "event_id": str(e.event_id),
                    "stage_name": e.stage_name,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                    "data": e.data,
                }
                for e in events
            ],
        }
    except DatabaseError as e:
        logger.error(f"Database error getting lineage: {str(e)}")
        raise HTTPException(500, "Database error getting lineage")
