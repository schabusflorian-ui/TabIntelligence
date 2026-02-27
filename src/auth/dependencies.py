"""
FastAPI dependencies for authentication.
"""

from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.api_key import verify_api_key
from src.auth.models import APIKey
from src.db.session import get_db_dependency
from src.core.logging import api_logger as logger

# HTTP Bearer scheme for Authorization header
security = HTTPBearer()


async def get_current_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db_dependency),
) -> APIKey:
    """
    Validate API key from Authorization header.

    Usage in FastAPI endpoint:
        ```python
        @app.post("/api/v1/files/upload")
        async def upload_file(
            file: UploadFile,
            api_key: APIKey = Depends(get_current_api_key),  # Requires auth
            db: AsyncSession = Depends(get_db),
        ):
            # api_key is guaranteed to be valid and active
            entity_id = api_key.entity_id
            # ...
        ```

    Args:
        credentials: HTTP Authorization credentials from header
        db: Database session

    Returns:
        APIKey: Valid and active API key record

    Raises:
        HTTPException 401: If key is invalid or inactive

    Security:
        - Requires Authorization: Bearer <key> header
        - Verifies key against database
        - Only allows active keys
        - Updates last_used_at timestamp
    """
    # Verify the key
    api_key = await verify_api_key(credentials.credentials, db)

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
    await db.commit()

    logger.debug(
        f"Authentication successful - key: {api_key.name}, entity: {api_key.entity_id}"
    )

    return api_key


async def get_optional_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(
        HTTPBearer(auto_error=False)
    ),
    db: AsyncSession = Depends(get_db_dependency),
) -> Optional[APIKey]:
    """
    Optional API key authentication (for endpoints that work both with/without auth).

    Usage:
        ```python
        @app.get("/api/v1/public-data")
        async def get_public_data(
            api_key: Optional[APIKey] = Depends(get_optional_api_key),
        ):
            if api_key:
                # Return premium data for authenticated users
                return get_premium_data(api_key.entity_id)
            else:
                # Return public data for anonymous users
                return get_public_data()
        ```

    Args:
        credentials: Optional HTTP Authorization credentials
        db: Database session

    Returns:
        Optional[APIKey]: API key if provided and valid, None otherwise

    Note:
        Does not raise 401 if no credentials provided, just returns None
    """
    if not credentials:
        return None

    # Verify the key (but don't raise exception if invalid)
    api_key = await verify_api_key(credentials.credentials, db)

    if api_key:
        # Update last_used_at timestamp
        api_key.last_used_at = datetime.utcnow()
        await db.commit()

    return api_key
