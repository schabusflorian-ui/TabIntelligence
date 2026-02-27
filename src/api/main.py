"""
Excel Model Intelligence - API Server
"""
from fastapi import FastAPI, UploadFile, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uuid
from sqlalchemy.orm import Session
from uuid import UUID

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from src.core.logging import setup_logging, api_logger as logger, log_exception
from src.core.exceptions import ExtractionError, ClaudeAPIError, InvalidFileError, DatabaseError, FileStorageError, LineageIncompleteError
from src.core.config import get_settings
# Tracing is optional (Week 3 feature) - don't block if not installed
try:
    from src.core.tracing import setup_tracing, instrument_fastapi
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    logger.warning("OpenTelemetry not installed - tracing disabled (install for Week 3)")
from src.api.middleware import RequestIDMiddleware, log_audit_event, get_client_ip
from src.db.session import get_db, get_db_context
from src.db import crud
from src.db.models import JobStatusEnum
from src.storage.s3 import get_s3_client
from src.jobs.tasks import run_extraction_task
from src.auth.dependencies import get_current_api_key
from src.auth.models import APIKey

# Initialize logging
# Use JSON format in production for machine-parseable logs
import os
use_json_logging = os.getenv("LOG_FORMAT", "plain").lower() == "json"
setup_logging(level="INFO", use_json=use_json_logging)

app = FastAPI(
    title="Excel Model Intelligence",
    version="0.1.0",
    description="Guided hybrid extraction platform"
)

logger.info("DebtFund API server starting...")

# Get settings for CORS configuration
settings = get_settings()

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add request ID middleware for correlation tracking
app.add_middleware(RequestIDMiddleware)


@app.on_event("startup")
async def startup_event():
    """Initialize database and S3 bucket on application startup."""
    from src.db.base import create_tables

    # Initialize distributed tracing (optional - Week 3 feature)
    if TRACING_AVAILABLE:
        setup_tracing(service_name="debtfund-api")
        instrument_fastapi(app)
        logger.info("Distributed tracing initialized")
    else:
        logger.info("Distributed tracing disabled (OpenTelemetry not installed)")

    # Initialize database
    create_tables()
    logger.info("Database initialized successfully")

    # Ensure S3 bucket exists
    try:
        settings = get_settings()
        s3_client = get_s3_client(settings)
        s3_client.ensure_bucket_exists()
        logger.info(f"S3 bucket '{settings.s3_bucket}' ready")
    except FileStorageError as e:
        logger.error(f"S3 bucket initialization failed: {str(e)}")
        logger.warning("Application starting without S3 storage")


# Database models replace in-memory storage (jobs dict removed)


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "DebtFund - Excel Model Intelligence",
        "version": "0.1.0",
        "status": "operational"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    logger.debug("Health check requested")
    return {"status": "healthy", "version": "0.1.0"}


@app.post("/api/v1/files/upload")
@limiter.limit("100/hour")
async def upload_file(
    request: Request,
    file: UploadFile,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_current_api_key),
    entity_id: Optional[str] = None
):
    """Upload Excel file for extraction."""
    logger.info(f"File upload requested: {file.filename}, entity_id: {entity_id}")

    # Validate file type
    if not file.filename.endswith(('.xlsx', '.xls')):
        logger.warning(f"Invalid file type rejected: {file.filename}")
        raise HTTPException(400, "File must be an Excel file (.xlsx or .xls)")

    try:
        # Define max file size (100MB)
        MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

        # Check file size without loading into memory
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Reset to beginning

        if file_size > MAX_FILE_SIZE:
            logger.warning(f"File too large rejected: {file.filename} ({file_size} bytes)")
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE / (1024*1024):.0f}MB"
            )

        # Now safe to read
        file_bytes = await file.read()

        # Create file record in database (without s3_key initially)
        db_file = crud.create_file(
            db,
            filename=file.filename,
            file_size=file_size,
            entity_id=UUID(entity_id) if entity_id else None,
        )

        # Upload to S3/MinIO
        settings = get_settings()
        s3_client = get_s3_client(settings)

        s3_key = s3_client.generate_s3_key(
            file_id=db_file.file_id,
            filename=file.filename
        )

        s3_client.upload_file(
            file_bytes=file_bytes,
            s3_key=s3_key,
            metadata={
                "file_id": str(db_file.file_id),
                "filename": file.filename,
                "entity_id": str(entity_id) if entity_id else ""
            }
        )

        # Update file record with s3_key
        crud.update_file_s3_key(db, db_file.file_id, s3_key)

        # Create extraction job record
        db_job = crud.create_extraction_job(db, file_id=db_file.file_id)

        logger.info(
            f"File uploaded - filename: {file.filename}, file_id: {db_file.file_id}, "
            f"job_id: {db_job.job_id}, size: {file_size} bytes, s3_key: {s3_key}"
        )

        # Enqueue Celery task (replaces background_tasks.add_task)
        task = run_extraction_task.delay(
            job_id=str(db_job.job_id),
            file_bytes=file_bytes,
            entity_id=entity_id
        )

        logger.info(f"Celery task enqueued: task_id={task.id}, job_id={db_job.job_id}")

        # Audit trail
        log_audit_event(
            db=db,
            action="upload",
            resource_type="file",
            resource_id=db_file.file_id,
            api_key_id=api_key.id,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            details={"filename": file.filename, "file_size": file_size, "job_id": str(db_job.job_id)},
            status_code=200,
        )

        return {
            "file_id": str(db_file.file_id),
            "job_id": str(db_job.job_id),
            "s3_key": s3_key,
            "task_id": task.id,
            "status": "processing",
            "message": "Extraction started"
        }

    except FileStorageError as e:
        logger.error(f"Storage error during file upload: {str(e)}")
        # Rollback database if storage fails
        db.rollback()
        raise HTTPException(500, f"Storage error: {str(e)}")

    except DatabaseError as e:
        logger.error(f"Database error during file upload: {str(e)}")
        raise HTTPException(500, f"Database error: {str(e)}")

    except Exception as e:
        logger.error(f"File upload failed: {str(e)}")
        log_exception(logger, e, {"filename": file.filename})
        raise HTTPException(500, f"Upload failed: {str(e)}")


@app.get("/api/v1/jobs/{job_id}")
@limiter.limit("500/hour")
async def get_job_status(
    request: Request,
    job_id: str,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_current_api_key)
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

        # Convert database model to API response format
        return {
            "job_id": str(job.job_id),
            "file_id": str(job.file_id),
            "status": job.status.value,
            "current_stage": job.current_stage,
            "progress_percent": job.progress_percent,
            "result": job.result,
            "error": job.error,
        }

    except DatabaseError as e:
        logger.error(f"Database error retrieving job: {str(e)}")
        raise HTTPException(500, "Database error retrieving job status")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
