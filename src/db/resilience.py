"""
Database resilience patterns for production reliability.

Provides:
- Retry logic with exponential backoff
- Circuit breaker pattern
- Connection validation
- Graceful degradation

These patterns prevent cascading failures and ensure the system can recover
automatically from transient database issues.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import TypeVar, Callable, Any, Optional
from dataclasses import dataclass, field

from sqlalchemy.exc import OperationalError, TimeoutError as SQLTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import DatabaseError

logger = logging.getLogger(__name__)

T = TypeVar('T')


# ============================================================================
# Retry Logic with Exponential Backoff
# ============================================================================

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    min_wait: float = 1.0  # seconds
    max_wait: float = 10.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True  # Add randomness to prevent thundering herd


def calculate_wait_time(attempt: int, config: RetryConfig) -> float:
    """
    Calculate wait time for retry attempt with exponential backoff.

    Args:
        attempt: Current attempt number (0-indexed)
        config: Retry configuration

    Returns:
        Wait time in seconds

    Example:
        attempt=0 -> 1s
        attempt=1 -> 2s
        attempt=2 -> 4s
        attempt=3 -> 8s (capped at max_wait)
    """
    wait = min(
        config.min_wait * (config.exponential_base ** attempt),
        config.max_wait
    )

    # Add jitter to prevent thundering herd
    if config.jitter:
        import random
        wait *= (0.5 + random.random())  # 50-150% of calculated wait

    return wait


def is_retryable_error(error: Exception) -> bool:
    """
    Determine if error is transient and should be retried.

    Args:
        error: Exception to check

    Returns:
        True if error is retryable (transient)

    Retryable errors:
    - Connection errors
    - Timeout errors
    - Lock wait timeout
    - Deadlock detected

    Non-retryable errors:
    - Constraint violations
    - Invalid SQL syntax
    - Permission denied
    """
    retryable_patterns = [
        "could not connect",
        "connection refused",
        "connection reset",
        "timeout",
        "lock wait timeout",
        "deadlock detected",
        "server closed the connection",
        "connection was forcibly closed",
    ]

    error_str = str(error).lower()
    return any(pattern in error_str for pattern in retryable_patterns)


async def execute_with_retry(
    operation: Callable[..., T],
    *args,
    config: Optional[RetryConfig] = None,
    operation_name: str = "database_operation",
    **kwargs
) -> T:
    """
    Execute async operation with automatic retry and exponential backoff.

    Args:
        operation: Async function to execute
        *args: Positional arguments for operation
        config: Retry configuration (uses default if not provided)
        operation_name: Name of operation for logging
        **kwargs: Keyword arguments for operation

    Returns:
        Result from operation

    Raises:
        DatabaseError: If all retry attempts fail

    Example:
        result = await execute_with_retry(
            db.execute,
            select(Job),
            operation_name="get_jobs"
        )
    """
    if config is None:
        config = RetryConfig()

    last_error = None

    for attempt in range(config.max_attempts):
        try:
            logger.debug(
                f"Executing {operation_name} (attempt {attempt + 1}/{config.max_attempts})"
            )
            result = await operation(*args, **kwargs)  # type: ignore[misc]
            logger.debug(f"Successfully executed {operation_name}")
            return result

        except (OperationalError, SQLTimeoutError) as e:
            last_error = e

            # Check if error is retryable
            if not is_retryable_error(e):
                logger.error(f"Non-retryable error in {operation_name}: {e}")
                raise DatabaseError(
                    f"Database operation failed: {e}",
                    operation=operation_name
                )

            # Last attempt - don't retry
            if attempt == config.max_attempts - 1:
                logger.error(
                    f"{operation_name} failed after {config.max_attempts} attempts: {e}"
                )
                break

            # Calculate wait time and retry
            wait_time = calculate_wait_time(attempt, config)
            logger.warning(
                f"{operation_name} failed (attempt {attempt + 1}/{config.max_attempts}), "
                f"retrying in {wait_time:.2f}s: {e}"
            )
            await asyncio.sleep(wait_time)

        except Exception as e:
            # Non-database errors should not be retried
            logger.error(f"Unexpected error in {operation_name}: {e}")
            raise DatabaseError(
                f"Unexpected error in {operation_name}: {e}",
                operation=operation_name
            )

    # All retries exhausted
    raise DatabaseError(
        f"{operation_name} failed after {config.max_attempts} attempts: {last_error}",
        operation=operation_name
    )


def with_retry(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
    operation_name: Optional[str] = None
):
    """
    Decorator to add retry logic to async functions.

    Args:
        max_attempts: Maximum number of retry attempts
        min_wait: Minimum wait time between retries (seconds)
        max_wait: Maximum wait time between retries (seconds)
        operation_name: Name for logging (uses function name if not provided)

    Example:
        @with_retry(max_attempts=3)
        async def get_job(db, job_id):
            result = await db.execute(select(Job).where(Job.id == job_id))
            return result.scalar_one_or_none()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            config = RetryConfig(
                max_attempts=max_attempts,
                min_wait=min_wait,
                max_wait=max_wait,
            )
            op_name = operation_name or func.__name__
            return await execute_with_retry(func, *args, config=config, operation_name=op_name, **kwargs)
        return wrapper  # type: ignore[return-value]
    return decorator


# ============================================================================
# Circuit Breaker Pattern
# ============================================================================

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Failures detected, blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker monitoring."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0  # Rejected due to open circuit
    last_state_change: Optional[datetime] = None
    state_changes: list = field(default_factory=list)

    def record_success(self):
        """Record successful request."""
        self.total_requests += 1
        self.successful_requests += 1

    def record_failure(self):
        """Record failed request."""
        self.total_requests += 1
        self.failed_requests += 1

    def record_rejection(self):
        """Record rejected request."""
        self.rejected_requests += 1

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0-1)."""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests are rejected immediately
    - HALF_OPEN: Testing if service recovered, limited requests allowed

    Args:
        failure_threshold: Number of failures before opening circuit
        recovery_timeout: Seconds before trying to recover (OPEN -> HALF_OPEN)
        success_threshold: Successful requests needed to close circuit
        timeout: Request timeout in seconds

    Example:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

        async def get_data():
            return await breaker.call(db_operation)
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
        timeout: float = 30.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.timeout = timeout

        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.last_failure_time: Optional[datetime] = None
        self.stats = CircuitBreakerStats()

        logger.info(
            f"Circuit breaker initialized: "
            f"failure_threshold={failure_threshold}, "
            f"recovery_timeout={recovery_timeout}s"
        )

    def _change_state(self, new_state: CircuitState):
        """Change circuit state and log transition."""
        old_state = self.state
        self.state = new_state
        self.stats.last_state_change = datetime.now()
        self.stats.state_changes.append({
            'from': old_state.value,
            'to': new_state.value,
            'timestamp': self.stats.last_state_change,
        })

        logger.warning(
            f"Circuit breaker state change: {old_state.value} -> {new_state.value} "
            f"(failures={self.consecutive_failures}, "
            f"success_rate={self.stats.success_rate:.2%})"
        )

    def _should_allow_request(self) -> bool:
        """Determine if request should be allowed."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.HALF_OPEN:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self.last_failure_time:
                time_since_failure = (datetime.now() - self.last_failure_time).total_seconds()
                if time_since_failure >= self.recovery_timeout:
                    logger.info("Circuit breaker: recovery timeout elapsed, entering HALF_OPEN state")
                    self._change_state(CircuitState.HALF_OPEN)
                    return True

            return False

        return False

    def _on_success(self):
        """Handle successful request."""
        self.stats.record_success()
        self.consecutive_failures = 0

        if self.state == CircuitState.HALF_OPEN:
            self.consecutive_successes += 1
            if self.consecutive_successes >= self.success_threshold:
                logger.info(
                    f"Circuit breaker: {self.consecutive_successes} consecutive successes, "
                    "service recovered, entering CLOSED state"
                )
                self._change_state(CircuitState.CLOSED)
                self.consecutive_successes = 0

    def _on_failure(self):
        """Handle failed request."""
        self.stats.record_failure()
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.last_failure_time = datetime.now()

        if self.state == CircuitState.HALF_OPEN:
            logger.warning("Circuit breaker: failure in HALF_OPEN state, reopening circuit")
            self._change_state(CircuitState.OPEN)

        elif self.state == CircuitState.CLOSED:
            if self.consecutive_failures >= self.failure_threshold:
                logger.error(
                    f"Circuit breaker: {self.consecutive_failures} consecutive failures, "
                    "opening circuit"
                )
                self._change_state(CircuitState.OPEN)

    async def call(self, operation: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute operation with circuit breaker protection.

        Args:
            operation: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result from operation

        Raises:
            DatabaseError: If circuit is open or operation fails
        """
        if not self._should_allow_request():
            self.stats.record_rejection()
            raise DatabaseError(
                f"Circuit breaker is OPEN - database unavailable "
                f"(will retry in {self.recovery_timeout}s)",
                operation="circuit_breaker"
            )

        try:
            # Execute with timeout
            result: Any = await asyncio.wait_for(
                operation(*args, **kwargs),  # type: ignore[arg-type]
                timeout=self.timeout
            )
            self._on_success()
            return result

        except asyncio.TimeoutError:
            logger.error(f"Operation timeout after {self.timeout}s")
            self._on_failure()
            raise DatabaseError(
                f"Operation timeout after {self.timeout}s",
                operation="circuit_breaker"
            )

        except Exception as e:
            logger.error(f"Operation failed: {e}")
            self._on_failure()
            raise

    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        return {
            'state': self.state.value,
            'consecutive_failures': self.consecutive_failures,
            'consecutive_successes': self.consecutive_successes,
            'total_requests': self.stats.total_requests,
            'successful_requests': self.stats.successful_requests,
            'failed_requests': self.stats.failed_requests,
            'rejected_requests': self.stats.rejected_requests,
            'success_rate': self.stats.success_rate,
            'last_state_change': self.stats.last_state_change.isoformat() if self.stats.last_state_change else None,
        }

    def reset(self):
        """Reset circuit breaker to initial state."""
        logger.info("Circuit breaker manually reset")
        self._change_state(CircuitState.CLOSED)
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.last_failure_time = None


# ============================================================================
# Global Circuit Breaker Instance
# ============================================================================

# Singleton circuit breaker for database operations
db_circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60,
    success_threshold=2,
    timeout=30.0,
)


# ============================================================================
# Enhanced Session with Resilience
# ============================================================================

async def resilient_execute(
    session: AsyncSession,
    statement: Any,
    *,
    use_circuit_breaker: bool = True,
    retry_config: Optional[RetryConfig] = None
) -> Any:
    """
    Execute database statement with resilience patterns.

    Combines retry logic and circuit breaker for maximum reliability.

    Args:
        session: Database session
        statement: SQL statement to execute
        use_circuit_breaker: Whether to use circuit breaker
        retry_config: Retry configuration (uses default if not provided)

    Returns:
        Result from query

    Example:
        result = await resilient_execute(
            session,
            select(Job).where(Job.id == job_id)
        )
    """
    async def execute_operation():
        return await session.execute(statement)

    if use_circuit_breaker:
        # Execute with both circuit breaker and retry
        return await execute_with_retry(
            db_circuit_breaker.call,
            execute_operation,
            config=retry_config,
            operation_name="resilient_execute"
        )
    else:
        # Execute with retry only
        return await execute_with_retry(
            execute_operation,
            config=retry_config,
            operation_name="resilient_execute"
        )
