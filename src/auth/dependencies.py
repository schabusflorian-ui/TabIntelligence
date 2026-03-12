"""
FastAPI dependencies for authentication and authorization.
"""

import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from src.auth.api_key import verify_api_key
from src.auth.models import APIKey
from src.db.session import get_db
from src.core.logging import api_logger as logger

# HTTP Bearer scheme for Authorization header
security = HTTPBearer()

# In-memory sliding window rate limiter keyed by API key id
# {key_id: [timestamp, timestamp, ...]}
_rate_limit_windows: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(api_key: APIKey) -> None:
    """Enforce per-key rate_limit_per_minute. Raises 429 if exceeded."""
    limit = api_key.rate_limit_per_minute
    if not isinstance(limit, int) or limit <= 0:
        return

    key_id = str(api_key.id) if api_key.id else "unknown"
    now = time.time()
    window_start = now - 60.0

    # Prune old entries
    timestamps = _rate_limit_windows[key_id]
    _rate_limit_windows[key_id] = [t for t in timestamps if t > window_start]
    timestamps = _rate_limit_windows[key_id]

    if len(timestamps) >= limit:
        logger.warning(
            f"Rate limit exceeded for key '{api_key.name}' "
            f"({len(timestamps)}/{limit} per minute)"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded ({limit} requests per minute)",
        )

    timestamps.append(now)


def get_current_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db),
) -> APIKey:
    """
    Validate API key from Authorization header.

    Checks:
    - Key is valid and active
    - Key has not expired
    - Per-key rate limit is not exceeded
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

    # Check expiry
    if isinstance(api_key.expires_at, datetime) and api_key.expires_at <= datetime.now(timezone.utc):
        logger.warning(f"Expired API key used: {api_key.name}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Enforce per-key rate limit
    _check_rate_limit(api_key)

    # Update last_used_at timestamp
    api_key.last_used_at = datetime.now(timezone.utc)
    db.commit()

    logger.debug(
        f"Authentication successful - key: {api_key.name}, entity: {api_key.entity_id}"
    )

    return api_key


def require_entity_scope(
    request: Request,
    api_key: APIKey = Depends(get_current_api_key),
) -> APIKey:
    """Dependency that enforces entity scope on resource access.

    If the API key has an entity_id, the request's entity_id parameter
    (from path or query) must match. Keys with entity_id=None (admin keys)
    can access any entity.
    """
    if not api_key.entity_id:
        # Admin key — no scope restriction
        return api_key

    # Check path params first, then query params
    target_entity = request.path_params.get("entity_id")
    if not target_entity:
        target_entity = request.query_params.get("entity_id")

    if target_entity:
        try:
            target_uuid = UUID(target_entity)
        except ValueError:
            raise HTTPException(400, "Invalid entity_id format")

        if target_uuid != api_key.entity_id:
            logger.warning(
                f"Entity scope violation: key '{api_key.name}' "
                f"(entity={api_key.entity_id}) tried to access entity={target_uuid}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key does not have access to this entity",
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
    """
    if not credentials:
        return None

    # Verify the key (but don't raise exception if invalid)
    api_key = verify_api_key(credentials.credentials, db)

    if api_key:
        # Check expiry silently
        if isinstance(api_key.expires_at, datetime) and api_key.expires_at <= datetime.now(timezone.utc):
            return None

        # Update last_used_at timestamp
        api_key.last_used_at = datetime.now(timezone.utc)
        db.commit()

    return api_key
