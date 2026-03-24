"""Shared rate limiter instance for all API endpoints."""

import logging
import os

from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger("tabintelligence.api.rate_limit")


def _create_limiter() -> Limiter:
    """Create rate limiter with Redis backend if available, else in-memory."""
    redis_url = os.getenv("REDIS_URL", "")
    if redis_url:
        try:
            storage_uri = redis_url
            limiter = Limiter(
                key_func=get_remote_address,
                storage_uri=storage_uri,
            )
            logger.info("Rate limiter using Redis backend")
            return limiter
        except Exception as e:
            logger.warning(f"Redis rate limiter init failed, using in-memory: {e}")

    logger.info("Rate limiter using in-memory backend")
    return Limiter(key_func=get_remote_address)


limiter = _create_limiter()
