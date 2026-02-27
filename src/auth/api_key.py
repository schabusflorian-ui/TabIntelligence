"""
API key generation and verification utilities.
"""

import hashlib
import secrets
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.auth.models import APIKey
from src.core.logging import api_logger as logger


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key and its hash.

    Returns:
        tuple[str, str]: (plain_key, key_hash)
            - plain_key: The actual key to give to the user (show once!)
            - key_hash: SHA256 hash to store in database

    Security:
        - Uses secrets.token_urlsafe for cryptographically secure randomness
        - Key format: emi_{32_char_token}
        - Hash: SHA256 of the key
        - Plain key is NEVER stored, only the hash

    Example:
        >>> key, key_hash = generate_api_key()
        >>> key
        'emi_xJK7n3QmP9R5tY2vZ8wA4bC6dE1fG3hI5jK7lM9'
        >>> len(key_hash)
        64  # SHA256 produces 64 hex chars
    """
    # Generate 32 random bytes, encoded as URL-safe base64 (43 chars)
    token = secrets.token_urlsafe(32)

    # Prefix with 'emi_' for easy identification
    plain_key = f"emi_{token}"

    # Generate SHA256 hash for storage
    key_hash = hashlib.sha256(plain_key.encode()).hexdigest()

    logger.debug(f"Generated API key (hash: {key_hash[:8]}...)")

    return plain_key, key_hash


def verify_api_key(key: str, db: Session) -> Optional[APIKey]:
    """
    Verify an API key and return the associated record.

    Args:
        key: The plain API key provided by the user
        db: Database session

    Returns:
        Optional[APIKey]: The API key record if valid and active, None otherwise

    Security:
        - Hashes the provided key before database lookup
        - Only returns active keys (is_active=True)
        - Constant-time comparison via database lookup (not vulnerable to timing attacks)
    """
    # Hash the provided key
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    # Look up in database (active keys only)
    result = db.execute(
        select(APIKey)
        .where(APIKey.key_hash == key_hash)
        .where(APIKey.is_active == True)
    )

    api_key = result.scalar_one_or_none()

    if api_key:
        logger.debug(
            f"API key verified - name: {api_key.name}, "
            f"entity_id: {api_key.entity_id}, "
            f"last_used: {api_key.last_used_at}"
        )
    else:
        logger.warning(f"API key verification failed (hash: {key_hash[:8]}...)")

    return api_key


def create_api_key(
    db: Session,
    name: str,
    entity_id: Optional[UUID] = None,
    rate_limit_per_minute: int = 60,
) -> tuple[APIKey, str]:
    """
    Create a new API key and store it in the database.

    Args:
        db: Database session
        name: Human-readable name for the key
        entity_id: Optional entity to scope this key to
        rate_limit_per_minute: Max requests per minute for this key

    Returns:
        tuple[APIKey, str]: (api_key_record, plain_key)
            - api_key_record: The database record
            - plain_key: The actual key (show this to the user ONCE!)
    """
    # Generate key and hash
    plain_key, key_hash = generate_api_key()

    # Create database record
    api_key = APIKey(
        name=name,
        key_hash=key_hash,
        entity_id=entity_id,
        rate_limit_per_minute=rate_limit_per_minute,
        is_active=True,
    )

    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    logger.info(
        f"API key created - id: {api_key.id}, name: {name}, entity_id: {entity_id}"
    )

    return api_key, plain_key


def revoke_api_key(db: Session, key_id: UUID) -> bool:
    """
    Revoke (deactivate) an API key.

    Args:
        db: Database session
        key_id: UUID of the key to revoke

    Returns:
        bool: True if key was revoked, False if not found
    """
    result = db.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()

    if not api_key:
        logger.warning(f"API key not found for revocation: {key_id}")
        return False

    api_key.is_active = False
    db.commit()

    logger.info(f"API key revoked - id: {key_id}, name: {api_key.name}")
    return True
