"""
Audit trail middleware for compliance logging.

Logs all API requests with relevant context for regulatory compliance.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.db.models import AuditLog
from src.core.logging import api_logger as logger


def log_audit_event(
    db: Session,
    action: str,
    resource_type: str,
    resource_id: Optional[UUID] = None,
    api_key_id: Optional[UUID] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[dict] = None,
    status_code: Optional[int] = None,
) -> AuditLog:
    """
    Log an audit event for compliance tracking.

    Args:
        db: Database session
        action: Action performed (e.g., "upload", "extract", "view")
        resource_type: Type of resource (e.g., "file", "job", "api_key")
        resource_id: UUID of the affected resource
        api_key_id: UUID of the API key used
        ip_address: Client IP address
        user_agent: Client user-agent string
        details: Additional context dict
        status_code: HTTP response status code

    Returns:
        AuditLog: The created audit log record
    """
    audit_entry = AuditLog(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        api_key_id=api_key_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details,
        status_code=status_code,
    )

    db.add(audit_entry)

    logger.info(
        f"Audit: action={action} resource_type={resource_type} "
        f"resource_id={resource_id} api_key_id={api_key_id} "
        f"ip={ip_address} status={status_code}"
    )

    return audit_entry


def get_client_ip(request) -> str:
    """
    Extract client IP from request, accounting for proxies.

    Args:
        request: FastAPI Request object

    Returns:
        str: Client IP address
    """
    # Check X-Forwarded-For header (reverse proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # First IP in the chain is the original client
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header (nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct connection
    if request.client:
        return request.client.host

    return "unknown"
