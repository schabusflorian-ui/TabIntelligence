"""
Unit tests for database resilience patterns.

Tests retry logic, circuit breaker, and error classification.
"""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import OperationalError

from src.core.exceptions import DatabaseError
from src.db.resilience import (
    CircuitBreaker,
    CircuitBreakerStats,
    CircuitState,
    RetryConfig,
    calculate_wait_time,
    execute_with_retry,
    is_retryable_error,
    with_retry,
)

# ============================================================================
# RETRY CONFIG
# ============================================================================


class TestRetryConfig:
    def test_default_config(self):
        """Should have sensible defaults."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.min_wait == 1.0
        assert config.max_wait == 10.0
        assert config.exponential_base == 2.0
        assert config.jitter is True

    def test_custom_config(self):
        """Should accept custom values."""
        config = RetryConfig(max_attempts=5, min_wait=0.5, max_wait=30.0)
        assert config.max_attempts == 5
        assert config.min_wait == 0.5
        assert config.max_wait == 30.0


# ============================================================================
# CALCULATE WAIT TIME
# ============================================================================


class TestCalculateWaitTime:
    def test_exponential_backoff_no_jitter(self):
        """Wait time should increase exponentially without jitter."""
        config = RetryConfig(min_wait=1.0, exponential_base=2.0, jitter=False)

        assert calculate_wait_time(0, config) == 1.0
        assert calculate_wait_time(1, config) == 2.0
        assert calculate_wait_time(2, config) == 4.0
        assert calculate_wait_time(3, config) == 8.0

    def test_capped_at_max_wait(self):
        """Wait time should be capped at max_wait."""
        config = RetryConfig(min_wait=1.0, max_wait=5.0, exponential_base=2.0, jitter=False)

        assert calculate_wait_time(10, config) == 5.0

    def test_jitter_varies_wait_time(self):
        """Jitter should add randomness to wait time."""
        config = RetryConfig(min_wait=1.0, exponential_base=2.0, jitter=True)

        # Run multiple times - results should vary
        results = set()
        for _ in range(20):
            results.add(round(calculate_wait_time(0, config), 3))

        # With jitter, we should get multiple different values
        assert len(results) > 1

    def test_jitter_range(self):
        """Jitter should keep wait time between 50% and 150% of base."""
        config = RetryConfig(min_wait=2.0, exponential_base=2.0, jitter=True)

        for _ in range(100):
            wait = calculate_wait_time(0, config)
            assert 1.0 <= wait <= 3.0  # 50%-150% of 2.0


# ============================================================================
# IS RETRYABLE ERROR
# ============================================================================


class TestIsRetryableError:
    def test_connection_errors_are_retryable(self):
        """Connection-related errors should be retryable."""
        assert is_retryable_error(Exception("could not connect to server"))
        assert is_retryable_error(Exception("connection refused"))
        assert is_retryable_error(Exception("connection reset by peer"))

    def test_timeout_errors_are_retryable(self):
        """Timeout errors should be retryable."""
        assert is_retryable_error(Exception("query timeout exceeded"))
        assert is_retryable_error(Exception("lock wait timeout"))

    def test_deadlock_is_retryable(self):
        """Deadlock errors should be retryable."""
        assert is_retryable_error(Exception("deadlock detected"))

    def test_constraint_violations_are_not_retryable(self):
        """Constraint violations should NOT be retryable."""
        assert not is_retryable_error(Exception("unique constraint violated"))
        assert not is_retryable_error(Exception("foreign key constraint"))

    def test_syntax_errors_are_not_retryable(self):
        """SQL syntax errors should NOT be retryable."""
        assert not is_retryable_error(Exception("syntax error at position 42"))

    def test_generic_errors_are_not_retryable(self):
        """Generic errors should NOT be retryable."""
        assert not is_retryable_error(Exception("something went wrong"))


# ============================================================================
# EXECUTE WITH RETRY
# ============================================================================


class TestExecuteWithRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        """Should return result on first successful attempt."""
        operation = AsyncMock(return_value="success")

        result = await execute_with_retry(operation, config=RetryConfig(max_attempts=3))
        assert result == "success"
        assert operation.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_transient_failure(self):
        """Should retry on transient OperationalError."""
        operation = AsyncMock(
            side_effect=[
                OperationalError("", {}, Exception("connection refused")),
                "success",
            ]
        )

        config = RetryConfig(max_attempts=3, min_wait=0.01, jitter=False)
        result = await execute_with_retry(operation, config=config)
        assert result == "success"
        assert operation.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self):
        """Should raise DatabaseError after exhausting retries."""
        error = OperationalError("", {}, Exception("connection refused"))
        operation = AsyncMock(side_effect=error)

        config = RetryConfig(max_attempts=2, min_wait=0.01, jitter=False)
        with pytest.raises(DatabaseError):
            await execute_with_retry(operation, config=config)

        assert operation.call_count == 2

    @pytest.mark.asyncio
    async def test_non_retryable_error_raises_immediately(self):
        """Should not retry non-retryable OperationalErrors."""
        error = OperationalError("", {}, Exception("permission denied"))
        operation = AsyncMock(side_effect=error)

        config = RetryConfig(max_attempts=3, min_wait=0.01)
        with pytest.raises(DatabaseError):
            await execute_with_retry(operation, config=config)

        assert operation.call_count == 1

    @pytest.mark.asyncio
    async def test_non_database_error_raises_immediately(self):
        """Should not retry non-database exceptions."""
        operation = AsyncMock(side_effect=ValueError("bad value"))

        config = RetryConfig(max_attempts=3, min_wait=0.01)
        with pytest.raises(DatabaseError):
            await execute_with_retry(operation, config=config)

        assert operation.call_count == 1


# ============================================================================
# WITH RETRY DECORATOR
# ============================================================================


class TestWithRetryDecorator:
    @pytest.mark.asyncio
    async def test_decorator_wraps_function(self):
        """Decorated function should work normally on success."""

        @with_retry(max_attempts=3, min_wait=0.01)
        async def my_operation():
            return 42

        result = await my_operation()
        assert result == 42

    @pytest.mark.asyncio
    async def test_decorator_retries_on_failure(self):
        """Decorated function should retry on transient errors."""
        call_count = 0

        @with_retry(max_attempts=3, min_wait=0.01)
        async def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OperationalError("", {}, Exception("connection refused"))
            return "recovered"

        result = await flaky_operation()
        assert result == "recovered"
        assert call_count == 2


# ============================================================================
# CIRCUIT BREAKER
# ============================================================================


class TestCircuitBreaker:
    def test_initial_state_is_closed(self):
        """Circuit should start in CLOSED state."""
        breaker = CircuitBreaker()
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_successful_call(self):
        """Successful calls should pass through."""
        breaker = CircuitBreaker()
        operation = AsyncMock(return_value="result")

        result = await breaker.call(operation)
        assert result == "result"
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self):
        """Circuit should open after reaching failure threshold."""
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        operation = AsyncMock(side_effect=Exception("db down"))

        for _ in range(3):
            with pytest.raises(Exception):
                await breaker.call(operation)

        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_rejects_when_open(self):
        """Open circuit should reject calls immediately."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=300)
        operation = AsyncMock(side_effect=Exception("db down"))

        # Open the circuit
        for _ in range(2):
            with pytest.raises(Exception):
                await breaker.call(operation)

        assert breaker.state == CircuitState.OPEN

        # Next call should be rejected without calling the operation
        operation.reset_mock()
        with pytest.raises(DatabaseError, match="Circuit breaker is OPEN"):
            await breaker.call(operation)

        # Operation should NOT have been called
        operation.assert_not_called()

    @pytest.mark.asyncio
    async def test_half_open_after_recovery_timeout(self):
        """Circuit should move to HALF_OPEN after recovery timeout."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0)

        operation = AsyncMock(side_effect=Exception("db down"))
        for _ in range(2):
            with pytest.raises(Exception):
                await breaker.call(operation)

        assert breaker.state == CircuitState.OPEN

        # With recovery_timeout=0, next request should be allowed (HALF_OPEN)
        operation_ok = AsyncMock(return_value="recovered")
        result = await breaker.call(operation_ok)
        assert result == "recovered"

    @pytest.mark.asyncio
    async def test_closes_after_success_threshold(self):
        """Circuit should close after enough successes in HALF_OPEN."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0, success_threshold=2)

        # Open the circuit
        operation = AsyncMock(side_effect=Exception("db down"))
        for _ in range(2):
            with pytest.raises(Exception):
                await breaker.call(operation)

        assert breaker.state == CircuitState.OPEN

        # Succeed twice to close
        ok_op = AsyncMock(return_value="ok")
        await breaker.call(ok_op)
        assert breaker.state == CircuitState.HALF_OPEN  # Still half-open after 1
        await breaker.call(ok_op)
        assert breaker.state == CircuitState.CLOSED  # Closed after 2

    def test_get_stats(self):
        """Should return stats dictionary."""
        breaker = CircuitBreaker()
        stats = breaker.get_stats()

        assert "state" in stats
        assert "consecutive_failures" in stats
        assert "total_requests" in stats
        assert "success_rate" in stats
        assert stats["state"] == "closed"

    def test_reset(self):
        """Manual reset should return to CLOSED state."""
        breaker = CircuitBreaker()
        breaker.consecutive_failures = 10
        breaker.state = CircuitState.OPEN

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.consecutive_failures == 0


class TestCircuitBreakerStats:
    def test_record_success(self):
        """Should track successful requests."""
        stats = CircuitBreakerStats()
        stats.record_success()
        stats.record_success()

        assert stats.total_requests == 2
        assert stats.successful_requests == 2
        assert stats.success_rate == 1.0

    def test_record_failure(self):
        """Should track failed requests."""
        stats = CircuitBreakerStats()
        stats.record_failure()

        assert stats.total_requests == 1
        assert stats.failed_requests == 1
        assert stats.success_rate == 0.0

    def test_success_rate_mixed(self):
        """Should calculate correct success rate."""
        stats = CircuitBreakerStats()
        stats.record_success()
        stats.record_success()
        stats.record_failure()

        assert stats.success_rate == pytest.approx(2 / 3)

    def test_success_rate_empty(self):
        """Should return 1.0 when no requests."""
        stats = CircuitBreakerStats()
        assert stats.success_rate == 1.0

    def test_record_rejection(self):
        """Should track rejected requests separately."""
        stats = CircuitBreakerStats()
        stats.record_rejection()

        assert stats.rejected_requests == 1
        assert stats.total_requests == 0  # Rejections don't count as requests
