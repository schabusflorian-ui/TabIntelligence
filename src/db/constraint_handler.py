"""
Constraint violation handler for converting SQLAlchemy exceptions to HTTP responses.

Maps database integrity errors to appropriate HTTP status codes
and user-friendly error messages.
"""
import re
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from src.core.logging import database_logger as logger


def handle_integrity_error(e: IntegrityError) -> HTTPException:
    """
    Convert SQLAlchemy IntegrityError to appropriate HTTP exception.

    Args:
        e: The IntegrityError from SQLAlchemy

    Returns:
        HTTPException with appropriate status code and detail message

    Mappings:
        - Unique constraint violation -> 409 Conflict
        - Foreign key violation -> 400 Bad Request
        - Check constraint violation -> 422 Unprocessable Entity
        - Not-null violation -> 422 Unprocessable Entity
        - Other -> 400 Bad Request
    """
    error_detail = str(e.orig).lower() if e.orig else str(e).lower()

    # Unique constraint violation
    if "unique" in error_detail or "duplicate" in error_detail:
        # Try to extract the constraint/column name
        constraint_name = _extract_constraint_name(error_detail)
        logger.warning(f"Unique constraint violation: {constraint_name or 'unknown'}")
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Resource already exists{f': {constraint_name}' if constraint_name else ''}",
        )

    # Foreign key violation
    if "foreign key" in error_detail or "fk_" in error_detail:
        logger.warning(f"Foreign key violation: {error_detail[:200]}")
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Referenced resource not found",
        )

    # Check constraint violation
    if "check" in error_detail or "ck_" in error_detail:
        constraint_name = _extract_constraint_name(error_detail)
        logger.warning(f"Check constraint violation: {constraint_name or 'unknown'}")
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Validation failed{f': {constraint_name}' if constraint_name else ''}",
        )

    # Not-null violation
    if "not null" in error_detail or "not-null" in error_detail or "notnull" in error_detail:
        column_name = _extract_column_name(error_detail)
        logger.warning(f"Not-null violation: {column_name or 'unknown'}")
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Required field missing{f': {column_name}' if column_name else ''}",
        )

    # Generic integrity error
    logger.error(f"Unhandled integrity error: {error_detail[:200]}")
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Data integrity error",
    )


def _extract_constraint_name(error_detail: str) -> Optional[str]:
    """Extract constraint name from error message if possible."""
    # PostgreSQL format: 'violates ... constraint "constraint_name"'
    match = re.search(r'constraint "([^"]+)"', error_detail)
    if match:
        return match.group(1)

    # SQLite format: 'UNIQUE constraint failed: table.column'
    match = re.search(r"constraint failed: (\S+)", error_detail)
    if match:
        return match.group(1)

    return None


def _extract_column_name(error_detail: str) -> Optional[str]:
    """Extract column name from not-null violation message."""
    # PostgreSQL: 'null value in column "col" violates not-null constraint'
    match = re.search(r'column "([^"]+)"', error_detail)
    if match:
        return match.group(1)

    # SQLite: 'NOT NULL constraint failed: table.column'
    match = re.search(r"constraint failed: \w+\.(\w+)", error_detail)
    if match:
        return match.group(1)

    return None
