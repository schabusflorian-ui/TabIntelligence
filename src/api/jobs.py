"""Job management API endpoints (list, status, export, retry, review, lineage, diff)."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.api.middleware import get_client_ip, log_audit_event
from src.api.rate_limit import limiter
from src.api.schemas import (
    ExtractionDiffResponse,
    ItemLineageResponse,
    JobListResponse,
    JobStatusResponse,
    ReviewDecisionRequest,
)
from src.auth.dependencies import get_current_api_key
from src.auth.models import APIKey
from src.core.exceptions import DatabaseError
from src.core.logging import api_logger as logger
from src.db import crud
from src.db.models import CorrectionHistory, JobStatusEnum
from src.db.session import get_db
from src.jobs.tasks import run_extraction_task
from src.lineage.differ import ExtractionDiffer

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

# Canonical stage ordering — single source of truth
STAGE_ORDER = ["parsing", "triage", "mapping", "validation", "enhanced_mapping"]
STAGE_INDEX = {name: idx + 1 for idx, name in enumerate(STAGE_ORDER)}


@router.get("/", response_model=JobListResponse)
@limiter.limit("500/hour")
async def list_jobs(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_current_api_key),
):
    """List extraction jobs with optional status filtering and pagination."""
    # Validate status if provided
    status_enum = None
    if status:
        try:
            status_enum = JobStatusEnum(status)
        except ValueError:
            valid = [s.value for s in JobStatusEnum]
            raise HTTPException(400, f"Invalid status. Must be one of: {valid}")

    try:
        jobs = crud.list_jobs(db, limit=min(limit, 200), offset=offset, status=status_enum)
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
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                    "updated_at": j.updated_at.isoformat() if j.updated_at else None,
                }
                for j in jobs
            ],
        }
    except DatabaseError as e:
        logger.error(f"Database error listing jobs: {str(e)}")
        raise HTTPException(500, "Database error listing jobs")


@router.get("/{job_id}", response_model=JobStatusResponse)
@limiter.limit("500/hour")
async def get_job_status(
    request: Request,
    job_id: str,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_current_api_key),
):
    """Get job status."""
    logger.debug(f"Job status requested: {job_id}")

    try:
        job_uuid = UUID(job_id)
    except ValueError:
        logger.warning(f"Invalid job_id format: {job_id}")
        raise HTTPException(400, "Invalid job_id format")

    try:
        job = crud.get_job(db, job_uuid)

        if not job:
            logger.warning(f"Job not found: {job_id}")
            raise HTTPException(404, "Job not found")

        # Audit trail
        log_audit_event(
            db=db,
            action="view",
            resource_type="job",
            resource_id=job_uuid,
            api_key_id=api_key.id,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            status_code=200,
        )

        # Derive stages_completed from current_stage
        stages_completed = None
        if job.status.value == "completed":
            stages_completed = len(STAGE_ORDER)
        elif job.current_stage:
            stages_completed = STAGE_INDEX.get(job.current_stage, 0)

        # Convert database model to API response format
        result = job.result
        return {
            "job_id": str(job.job_id),
            "file_id": str(job.file_id),
            "status": job.status.value,
            "current_stage": job.current_stage,
            "progress_percent": job.progress_percent,
            "stages_completed": stages_completed,
            "total_stages": 5,
            "result": result,
            "quality": result.get("quality") if result else None,
            "model_type": result.get("model_type") if result else None,
            "error": job.error,
        }

    except DatabaseError as e:
        logger.error(f"Database error retrieving job: {str(e)}")
        raise HTTPException(500, "Database error retrieving job status")


@router.get("/{job_id}/export")
@limiter.limit("500/hour")
async def export_job_result(
    request: Request,
    job_id: str,
    format: str = "json",
    min_confidence: Optional[float] = None,
    canonical_name: Optional[str] = None,
    sheet: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_current_api_key),
):
    """
    Export extraction results in JSON or CSV format.

    Query parameters:
        format: "json" (default) or "csv"
        min_confidence: Filter line items by minimum confidence (0.0 - 1.0)
        canonical_name: Filter by canonical name (e.g. "revenue")
        sheet: Filter by sheet name
    """
    # Validate format
    if format not in ("json", "csv"):
        raise HTTPException(400, "format must be 'json' or 'csv'")

    if min_confidence is not None and not (0.0 <= min_confidence <= 1.0):
        raise HTTPException(400, "min_confidence must be between 0.0 and 1.0")

    # Validate job_id
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job_id format")

    # Fetch job
    try:
        job = crud.get_job(db, job_uuid)
    except DatabaseError as e:
        logger.error(f"Database error exporting job: {str(e)}")
        raise HTTPException(500, "Database error")

    if not job:
        raise HTTPException(404, "Job not found")

    if job.status not in (JobStatusEnum.COMPLETED, JobStatusEnum.NEEDS_REVIEW):
        raise HTTPException(
            409,
            f"Job is not completed (status: {job.status.value}). "
            f"Export is only available for completed or needs_review jobs.",
        )

    if not job.result:
        raise HTTPException(404, "Job has no results")

    result = job.result
    line_items = result.get("line_items", [])

    # Apply filters
    if min_confidence is not None:
        line_items = [li for li in line_items if li.get("confidence", 0) >= min_confidence]

    if canonical_name:
        line_items = [li for li in line_items if li.get("canonical_name") == canonical_name]

    if sheet:
        line_items = [li for li in line_items if li.get("sheet") == sheet]

    # Audit trail
    log_audit_event(
        db=db,
        action="export",
        resource_type="job",
        resource_id=job_uuid,
        api_key_id=api_key.id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        details={
            "format": format,
            "min_confidence": min_confidence,
            "line_items_exported": len(line_items),
        },
        status_code=200,
    )

    if format == "csv":
        return _build_csv_response(result, line_items, job_id)

    # JSON export — return filtered result
    return {
        "job_id": str(job.job_id),
        "file_id": str(job.file_id),
        "sheets": result.get("sheets", []),
        "line_items": line_items,
        "line_items_count": len(line_items),
        "tokens_used": result.get("tokens_used", 0),
        "cost_usd": result.get("cost_usd", 0.0),
        "validation": result.get("validation"),
        "quality": result.get("quality"),
        "model_type": result.get("model_type"),
        "validation_delta": result.get("validation_delta"),
        "filters_applied": {
            "min_confidence": min_confidence,
            "canonical_name": canonical_name,
            "sheet": sheet,
        },
    }


@router.post("/{job_id}/retry")
@limiter.limit("20/hour")
async def retry_job(
    request: Request,
    job_id: str,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_current_api_key),
):
    """
    Retry a failed extraction job.

    Creates a new job for the same file and enqueues a new Celery task.
    Only failed jobs can be retried.
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job_id format")

    job = crud.get_job(db, job_uuid)
    if not job:
        raise HTTPException(404, "Job not found")

    if job.status != JobStatusEnum.FAILED:
        raise HTTPException(
            409, f"Only failed jobs can be retried (current status: {job.status.value})"
        )

    # Look up file record to get s3_key for re-extraction
    file_record = crud.get_file(db, job.file_id)
    if not file_record or not file_record.s3_key:
        raise HTTPException(404, "Original file not found in storage")

    # Create new job for the same file
    new_job = crud.create_extraction_job(db, file_id=job.file_id)

    # Check for checkpoint data from the failed job to enable resume
    resume_from_stage = None
    old_result = job.result or {}
    last_completed = old_result.get("_last_completed_stage")
    stage_results = old_result.get("_stage_results", {})

    if last_completed and stage_results:
        # Seed new job with checkpoint data so _preload_checkpoint can find it
        new_job.result = {"_stage_results": stage_results, "_last_completed_stage": last_completed}
        db.commit()

        # Determine which stage to resume from (the one after the last completed)
        try:
            idx = STAGE_ORDER.index(last_completed)
            if idx + 1 < len(STAGE_ORDER):
                resume_from_stage = STAGE_ORDER[idx + 1]
        except ValueError:
            pass

    # Enqueue Celery task (task downloads from S3 itself using s3_key)
    entity_id = str(file_record.entity_id) if file_record.entity_id else None
    task = run_extraction_task.delay(
        job_id=str(new_job.job_id),
        s3_key=file_record.s3_key,
        entity_id=entity_id,
        resume_from_stage=resume_from_stage,
    )

    resumed_stages = list(stage_results.keys()) if resume_from_stage else []
    logger.info(
        f"Job retry: original={job_id}, new_job={new_job.job_id}, task={task.id}"
        + (
            f", resuming from {resume_from_stage} (reusing {resumed_stages})"
            if resume_from_stage
            else ""
        )
    )

    # Audit trail
    log_audit_event(
        db=db,
        action="retry",
        resource_type="job",
        resource_id=job_uuid,
        api_key_id=api_key.id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        details={
            "original_job_id": job_id,
            "new_job_id": str(new_job.job_id),
            "resume_from_stage": resume_from_stage,
        },
        status_code=201,
    )

    response = {
        "original_job_id": job_id,
        "new_job_id": str(new_job.job_id),
        "task_id": task.id,
        "status": "processing",
        "message": "Re-extraction started",
    }
    if resume_from_stage:
        response["resumed_from"] = resume_from_stage
        response["reused_stages"] = resumed_stages

    return response


@router.post("/{job_id}/review")
@limiter.limit("100/hour")
async def review_job(
    request: Request,
    job_id: str,
    body: ReviewDecisionRequest,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_current_api_key),
):
    """
    Approve or reject a job in NEEDS_REVIEW status.

    - approve: transitions to COMPLETED
    - reject: transitions to FAILED with optional reason
    """

    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job_id format")

    try:
        job = crud.review_job(db, job_uuid, body.decision, body.reason)
    except DatabaseError as e:
        if "not found" in str(e):
            raise HTTPException(404, "Job not found")
        if "not in NEEDS_REVIEW" in str(e):
            raise HTTPException(409, str(e))
        raise HTTPException(500, "Database error during review")

    log_audit_event(
        db=db,
        action="review",
        resource_type="job",
        resource_id=job_uuid,
        api_key_id=api_key.id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        details={
            "decision": body.decision,
            "reason": body.reason,
            "previous_status": "needs_review",
            "new_status": job.status.value,
        },
        status_code=200,
    )

    return {
        "job_id": job_id,
        "previous_status": "needs_review",
        "new_status": job.status.value,
        "decision": body.decision,
        "reason": body.reason,
        "message": f"Job {body.decision}d successfully",
    }


@router.get("/{job_id}/lineage")
@limiter.limit("500/hour")
def get_job_lineage(
    request: Request,
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


@router.get("/{job_id}/lineage/{canonical_name}")
def get_item_provenance(
    job_id: str,
    canonical_name: str,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get provenance for a specific canonical item across all periods.

    Returns all line items matching the canonical_name, each with full
    provenance (source cells, mapping method, validation status, etc.).
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job_id format")

    try:
        job = crud.get_job(db, job_uuid)
        if not job:
            raise HTTPException(404, "Job not found")

        if not job.result:
            raise HTTPException(404, "Job has no results")

        line_items = job.result.get("line_items", [])
        matches = [li for li in line_items if li.get("canonical_name") == canonical_name]

        if not matches:
            raise HTTPException(
                404,
                f"No line item with canonical_name '{canonical_name}'",
            )

        return {
            "job_id": job_id,
            "canonical_name": canonical_name,
            "occurrences": len(matches),
            "items": matches,
        }
    except DatabaseError as e:
        logger.error(f"Database error getting item provenance: {str(e)}")
        raise HTTPException(500, "Database error getting item provenance")


@router.get("/{job_id}/diff/{other_job_id}", response_model=ExtractionDiffResponse)
@limiter.limit("500/hour")
def get_extraction_diff(
    request: Request,
    job_id: str,
    other_job_id: str,
    canonical_name: Optional[str] = None,
    min_change_pct: Optional[float] = None,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Compare two extraction jobs and return the diff."""
    try:
        job_a_uuid = UUID(job_id)
        job_b_uuid = UUID(other_job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job_id format")

    try:
        job_a = crud.get_job(db, job_a_uuid)
        if not job_a:
            raise HTTPException(404, f"Job {job_id} not found")

        job_b = crud.get_job(db, job_b_uuid)
        if not job_b:
            raise HTTPException(404, f"Job {other_job_id} not found")

        _diffable = (JobStatusEnum.COMPLETED, JobStatusEnum.NEEDS_REVIEW)
        if job_a.status not in _diffable:
            raise HTTPException(
                409, f"Job {job_id} is not completed (status: {job_a.status.value})"
            )
        if job_b.status not in _diffable:
            raise HTTPException(
                409, f"Job {other_job_id} is not completed (status: {job_b.status.value})"
            )

        differ = ExtractionDiffer()
        result = differ.diff(
            db,
            job_id,
            other_job_id,
            canonical_name=canonical_name,
            min_change_pct=min_change_pct,
        )

        # Cross-entity warning
        entity_a = getattr(job_a.file, "entity_id", None) if job_a.file else None
        entity_b = getattr(job_b.file, "entity_id", None) if job_b.file else None
        if entity_a and entity_b and entity_a != entity_b:
            result.warnings.append(
                "Jobs belong to different entities \u2014 diff may not be meaningful"
            )

        # Correction metadata
        corr_a = (
            db.query(CorrectionHistory)
            .filter(
                CorrectionHistory.job_id == job_a_uuid,
                CorrectionHistory.reverted == False,  # noqa: E712
            )
            .count()
        )
        corr_b = (
            db.query(CorrectionHistory)
            .filter(
                CorrectionHistory.job_id == job_b_uuid,
                CorrectionHistory.reverted == False,  # noqa: E712
            )
            .count()
        )
        if corr_a or corr_b:
            result.metadata["job_a_corrections"] = corr_a
            result.metadata["job_b_corrections"] = corr_b

        return result.to_dict()
    except DatabaseError as e:
        logger.error(f"Database error getting diff: {str(e)}")
        raise HTTPException(500, "Database error getting diff")


@router.get("/{job_id}/item-lineage/{canonical_name}", response_model=ItemLineageResponse)
@limiter.limit("500/hour")
def get_item_lineage(
    request: Request,
    job_id: str,
    canonical_name: str,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Get the transformation chain for a specific canonical item."""
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job_id format")

    try:
        job = crud.get_job(db, job_uuid)
        if not job:
            raise HTTPException(404, "Job not found")

        if not job.result:
            raise HTTPException(404, "Job has no results")

        item_lineage = (job.result or {}).get("item_lineage", {})
        if canonical_name not in item_lineage:
            raise HTTPException(404, f"No item lineage for '{canonical_name}'")

        return {
            "job_id": job_id,
            "canonical_name": canonical_name,
            "transformations": item_lineage[canonical_name],
        }
    except DatabaseError as e:
        logger.error(f"Database error getting item lineage: {str(e)}")
        raise HTTPException(500, "Database error getting item lineage")


def _build_csv_response(result: dict, line_items: list, job_id: str):
    """Build a CSV response from extraction line items."""
    import csv
    import io

    from starlette.responses import StreamingResponse

    output = io.StringIO()
    writer = csv.writer(output)

    # Collect all period columns from values across all line items
    period_columns_set: set[str] = set()
    for li in line_items:
        period_columns_set.update(li.get("values", {}).keys())
    period_columns = sorted(period_columns_set)

    # Write header (includes provenance columns after period data)
    header: list[str] = (
        [
            "sheet",
            "row",
            "original_label",
            "canonical_name",
            "confidence",
            "hierarchy_level",
        ]
        + period_columns
        + [
            "source_cell",
            "mapping_method",
            "taxonomy_category",
            "validation_passed",
        ]
    )
    writer.writerow(header)

    # Write data rows
    for li in line_items:
        values = li.get("values", {})
        prov = li.get("provenance", {})

        # Flatten provenance into CSV columns
        source_cells = prov.get("source_cells", [])
        source_cell = source_cells[0].get("cell_ref", "") if source_cells else ""
        mapping_method = prov.get("mapping", {}).get("method", "")
        taxonomy_cat = prov.get("mapping", {}).get("taxonomy_category", "")
        val_prov = prov.get("validation")
        val_passed = str(val_prov.get("all_passed", "")).lower() if val_prov else ""

        row = (
            [
                li.get("sheet", ""),
                li.get("row", ""),
                li.get("original_label", ""),
                li.get("canonical_name", ""),
                li.get("confidence", ""),
                li.get("hierarchy_level", ""),
            ]
            + [values.get(period, "") for period in period_columns]
            + [
                source_cell,
                mapping_method,
                taxonomy_cat,
                val_passed,
            ]
        )
        writer.writerow(row)

    csv_content = output.getvalue()
    output.close()

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="extraction_{job_id}.csv"',
        },
    )
