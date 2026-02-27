"""
FastAPI dependencies for authentication.
"""

from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.auth.api_key import verify_api_key
from src.auth.models import APIKey
from src.db.session import get_db
from src.core.logging import api_logger as logger

# HTTP Bearer scheme for Authorization header
security = HTTPBearer()


def get_current_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db),
) -> APIKey:
    """
    Validate API key from Authorization header.

    Args:
        credentials: HTTP Authorization credentials from header
        db: Database session (sync)

    Returns:
        APIKey: Valid and active API key record

    Raises:
        HTTPException 401: If key is invalid or inactive
    """
    # Verify the key
    api_key = verify_api_key(credentials.credentials, db)

    if not api_key:
        logger.warning(
            "Authentication failed - invalid or inactive API key",
            extra={"key_prefix": credentials.credentials[:10] + "..."},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Update last_used_at timestamp
    api_key.last_used_at = datetime.utcnow()
    db.commit()

    logger.debug(
        f"Authentication successful - key: {api_key.name}, entity: {api_key.entity_id}"
    )

    return api_key


def get_optional_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(
        HTTPBearer(auto_error=False)
    ),
    db: Session = Depends(get_db),
) -> Optional[APIKey]:
    """
    Optional API key authentication (for endpoints that work both with/without auth).

    Args:
        credentials: Optional HTTP Authorization credentials
        db: Database session (sync)

    Returns:
        Optional[APIKey]: API key if provided and valid, None otherwise
    """
    if not credentials:
        return None

    # Verify the key (but don't raise exception if invalid)
    api_key = verify_api_key(credentials.credentials, db)

    if api_key:
        # Update last_used_at timestamp
        api_key.last_used_at = datetime.utcnow()
        db.commit()

    return api_key
