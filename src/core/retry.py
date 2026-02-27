"""Retry decorator with exponential backoff for async functions."""
import asyncio
import functools
from typing import Callable, Any
from src.core.logging import get_logger

logger = get_logger(__name__)


def retry(max_attempts: int = 3, backoff_seconds: int = 2):
    """
    Retry decorator with exponential backoff for async functions.

    Args:
        max_attempts: Maximum number of attempts (default 3)
        backoff_seconds: Initial backoff in seconds (doubles each retry)

    Usage:
        @retry(max_attempts=3, backoff_seconds=2)
        async def my_function(arg1, arg2, attempt=1):
            # attempt parameter will be automatically injected
            logger.info(f"Attempt {attempt}/{max_attempts}")
            # ... rest of function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    # Pass attempt number if function accepts it
                    if 'attempt' in func.__code__.co_varnames:
                        kwargs['attempt'] = attempt

                    return await func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    if attempt < max_attempts:
                        wait_time = backoff_seconds * (2 ** (attempt - 1))
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt}/{max_attempts}). "
                            f"Retrying in {wait_time}s. Error: {str(e)}"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts. "
                            f"Final error: {str(e)}"
                        )

            # All attempts exhausted - raise the last exception
            raise last_exception

        return wrapper
    return decorator
