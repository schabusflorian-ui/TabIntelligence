"""File management API endpoints."""

import hashlib
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.api.metrics import duplicate_uploads_total, file_upload_bytes, file_uploads_total
from src.api.middleware import get_client_ip, log_audit_event
from src.api.rate_limit import limiter
from src.auth.dependencies import get_current_api_key
from src.auth.models import APIKey
from src.core.config import get_settings
from src.core.exceptions import DatabaseError, FileStorageError
from src.core.logging import api_logger as logger
from src.core.logging import log_exception
from src.db import crud
from src.db.constraint_handler import handle_integrity_error
from src.db.models import ExtractionJob
from src.db.session import get_db
from src.jobs.tasks import run_extraction_task
from src.storage.s3 import get_s3_client

router = APIRouter(prefix="/api/v1/files", tags=["files"])

# XLSX files are ZIP archives (PK header), XLS files have OLE2 compound doc header
_XLSX_MAGIC = b"PK\x03\x04"
_XLS_MAGIC = b"\xd0\xcf\x11\xe0"


@router.post("/upload")
@limiter.limit("100/hour")
async def upload_file(
    request: Request,
    file: UploadFile,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_current_api_key),
    entity_id: Optional[str] = None,
):
    """Upload Excel file for extraction."""
    logger.info(f"File upload requested: {file.filename}, entity_id: {entity_id}")

    # Enforce entity scope: scoped keys can only upload to their own entity
    if api_key.entity_id and entity_id:
        try:
            if UUID(entity_id) != api_key.entity_id:
                raise HTTPException(403, "API key does not have access to this entity")
        except ValueError:
            raise HTTPException(400, "Invalid entity_id format")

    # Validate file extension
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        logger.warning(f"Invalid file type rejected: {file.filename}")
        raise HTTPException(400, "File must be an Excel file (.xlsx or .xls)")

    try:
        # Use configured max file size
        max_file_size = get_settings().max_file_size_bytes

        # Read file content and check size
        file_bytes = await file.read()
        file_size = len(file_bytes)

        if file_size > max_file_size:
            logger.warning(f"File too large rejected: {file.filename} ({file_size} bytes)")
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {max_file_size // (1024 * 1024)}MB",
            )

        # Validate magic bytes — ensure the file is actually an Excel file
        if file.filename.endswith(".xlsx"):
            if not file_bytes[:4].startswith(_XLSX_MAGIC):
                logger.warning(f"Invalid XLSX magic bytes rejected: {file.filename}")
                raise HTTPException(400, "File content is not a valid XLSX file")
        elif file.filename.endswith(".xls"):
            if not file_bytes[:4].startswith(_XLS_MAGIC):
                logger.warning(f"Invalid XLS magic bytes rejected: {file.filename}")
                raise HTTPException(400, "File content is not a valid XLS file")

        # Compute content hash for deduplication
        content_hash = hashlib.sha256(file_bytes).hexdigest()

        # Check for duplicate file (optimistic fast path)
        existing_file = crud.get_file_by_hash(db, content_hash)
        if existing_file:
            existing_job = (
                db.query(ExtractionJob)
                .filter(ExtractionJob.file_id == existing_file.file_id)
                .order_by(ExtractionJob.created_at.desc())
                .first()
            )

            logger.info(
                f"Duplicate file detected: hash={content_hash[:16]}..., "
                f"existing_file_id={existing_file.file_id}"
            )
            duplicate_uploads_total.inc()

            return {
                "file_id": str(existing_file.file_id),
                "job_id": str(existing_job.job_id) if existing_job else None,
                "status": "duplicate",
                "message": "File with identical content already uploaded",
                "original_upload": existing_file.uploaded_at.isoformat()
                if existing_file.uploaded_at
                else None,
            }

        # --- Upload to S3 if available ---
        filename = file.filename or "unknown.xlsx"
        s3_key = None
        try:
            settings = get_settings()
            s3_client = get_s3_client(settings)
        except (FileStorageError, Exception) as s3_init_err:
            logger.warning(f"S3 not configured, proceeding without storage: {s3_init_err}")
            s3_client = None

        if s3_client:
            file_id_for_key = uuid4()
            s3_key = s3_client.generate_s3_key(file_id=file_id_for_key, filename=filename)
            try:
                s3_client.upload_file(
                    file_bytes=file_bytes,
                    s3_key=s3_key,
                    metadata={
                        "filename": filename,
                        "entity_id": str(entity_id) if entity_id else "",
                    },
                )
            except (FileStorageError, Exception) as upload_err:
                logger.warning(f"S3 upload failed, proceeding without storage: {upload_err}")
                s3_key = None

        # --- Create DB records ---
        try:
            db_file = crud.create_file(
                db,
                filename=filename,
                file_size=file_size,
                s3_key=s3_key,
                entity_id=UUID(entity_id) if entity_id else None,
                content_hash=content_hash,
            )
        except (IntegrityError, DatabaseError):
            db.rollback()
            # Race condition: another request inserted the same content_hash
            existing_file = crud.get_file_by_hash(db, content_hash)
            if existing_file:
                existing_job = (
                    db.query(ExtractionJob)
                    .filter(ExtractionJob.file_id == existing_file.file_id)
                    .order_by(ExtractionJob.created_at.desc())
                    .first()
                )

                logger.info(
                    f"Duplicate file detected (race condition): hash={content_hash[:16]}..., "
                    f"existing_file_id={existing_file.file_id}"
                )
                duplicate_uploads_total.inc()

                return {
                    "file_id": str(existing_file.file_id),
                    "job_id": str(existing_job.job_id) if existing_job else None,
                    "status": "duplicate",
                    "message": "File with identical content already uploaded",
                    "original_upload": existing_file.uploaded_at.isoformat()
                    if existing_file.uploaded_at
                    else None,
                }
            raise

        db_job = crud.create_extraction_job(db, file_id=db_file.file_id)

        logger.info(
            f"File uploaded - filename: {file.filename}, file_id: {db_file.file_id}, "
            f"job_id: {db_job.job_id}, size: {file_size} bytes, s3_key: {s3_key}"
        )

        # --- Enqueue Celery task ---
        # Pass file_bytes directly when S3 is not available (local dev)
        try:
            task_kwargs: dict[str, Any] = {
                "job_id": str(db_job.job_id),
                "entity_id": entity_id,
            }
            if s3_key:
                task_kwargs["s3_key"] = s3_key
            else:
                task_kwargs["file_bytes"] = file_bytes
            task = run_extraction_task.delay(**task_kwargs)
        except Exception as enqueue_err:
            logger.error(f"Failed to enqueue Celery task: {enqueue_err}")
            try:
                crud.fail_job(db, db_job.job_id, "Task queue unavailable, please retry")
            except Exception:
                logger.error("Failed to mark job as FAILED after enqueue failure")
            raise HTTPException(status_code=503, detail="Task queue unavailable, please retry")

        logger.info(f"Celery task enqueued: task_id={task.id}, job_id={db_job.job_id}")

        # Track upload metrics
        file_uploads_total.inc()
        file_upload_bytes.observe(file_size)

        # Audit trail
        log_audit_event(
            db=db,
            action="upload",
            resource_type="file",
            resource_id=db_file.file_id,
            api_key_id=api_key.id,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            details={
                "filename": file.filename,
                "file_size": file_size,
                "job_id": str(db_job.job_id),
            },
            status_code=200,
        )

        return {
            "file_id": str(db_file.file_id),
            "job_id": str(db_job.job_id),
            "s3_key": s3_key,
            "task_id": task.id,
            "status": "processing",
            "message": "Extraction started",
        }

    except HTTPException:
        raise

    except FileStorageError as e:
        logger.error(f"Storage error during file upload: {str(e)}")
        raise HTTPException(500, f"Storage error: {str(e)}")

    except IntegrityError as e:
        db.rollback()
        raise handle_integrity_error(e)

    except DatabaseError as e:
        logger.error(f"Database error during file upload: {str(e)}")
        raise HTTPException(500, f"Database error: {str(e)}")

    except Exception as e:
        logger.error(f"File upload failed: {str(e)}")
        log_exception(logger, e, {"filename": file.filename})
        raise HTTPException(500, f"Upload failed: {str(e)}")


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


@router.get("/{file_id}/download")
async def download_file(
    file_id: UUID,
    db: Session = Depends(get_db),
    _api_key: APIKey = Depends(get_current_api_key),
):
    """Generate a presigned URL for temporary file download."""
    file = crud.get_file(db, file_id)
    if not file:
        raise HTTPException(404, "File not found")

    if not file.s3_key:
        raise HTTPException(
            400, "File is not stored in S3 and cannot be downloaded via presigned URL"
        )

    try:
        s3_client = get_s3_client()
        url = s3_client.generate_presigned_url(file.s3_key, filename=file.filename)
    except FileStorageError as e:
        logger.error(f"Failed to generate presigned URL for file {file_id}: {str(e)}")
        raise HTTPException(500, f"Storage error: {str(e)}")

    return {"download_url": url, "expires_in": 3600, "filename": file.filename}


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
