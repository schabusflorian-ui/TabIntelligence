"""
Unit tests for logging utilities and audit middleware.

Tests setup_logging, LogContext, log helpers, and audit event creation.
"""

import logging
from unittest.mock import MagicMock
from uuid import uuid4

from src.api.middleware.audit import get_client_ip, log_audit_event
from src.core.logging import (
    LogContext,
    api_logger,
    database_logger,
    extraction_logger,
    get_logger,
    lineage_logger,
    log_exception,
    log_performance,
    request_id_ctx,
    validation_logger,
)
from src.db.models import AuditLog

# ============================================================================
# MODULE LOGGERS
# ============================================================================


class TestModuleLoggers:
    def test_extraction_logger_exists(self):
        assert extraction_logger.name == "debtfund.extraction"

    def test_api_logger_exists(self):
        assert api_logger.name == "debtfund.api"

    def test_database_logger_exists(self):
        assert database_logger.name == "debtfund.database"

    def test_lineage_logger_exists(self):
        assert lineage_logger.name == "debtfund.lineage"

    def test_validation_logger_exists(self):
        assert validation_logger.name == "debtfund.validation"

    def test_get_logger(self):
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"


# ============================================================================
# LOG CONTEXT
# ============================================================================


class TestLogContext:
    def test_temporarily_changes_level(self):
        """LogContext should change level temporarily."""
        logger = logging.getLogger("test.context")
        logger.setLevel(logging.INFO)

        with LogContext("test.context", "DEBUG") as ctx_logger:
            assert ctx_logger.level == logging.DEBUG

        # Should restore original level
        assert logger.level == logging.INFO

    def test_restores_on_exception(self):
        """LogContext should restore level even on exception."""
        logger = logging.getLogger("test.exception")
        logger.setLevel(logging.WARNING)

        try:
            with LogContext("test.exception", "DEBUG"):
                raise ValueError("test error")
        except ValueError:
            pass

        assert logger.level == logging.WARNING


# ============================================================================
# LOG HELPERS
# ============================================================================


class TestLogException:
    def test_logs_exception_message(self):
        """Should log exception with class name and message."""
        mock_logger = MagicMock()
        exc = ValueError("bad value")

        log_exception(mock_logger, exc)
        mock_logger.exception.assert_called_once()
        call_args = mock_logger.exception.call_args[0][0]
        assert "ValueError" in call_args
        assert "bad value" in call_args

    def test_logs_with_context(self):
        """Should include context in log message."""
        mock_logger = MagicMock()
        exc = RuntimeError("oops")

        log_exception(mock_logger, exc, {"file_id": "123", "stage": "parsing"})
        call_args = mock_logger.exception.call_args[0][0]
        assert "Context:" in call_args
        assert "file_id" in call_args

    def test_logs_without_context(self):
        """Should work without context dict."""
        mock_logger = MagicMock()
        log_exception(mock_logger, Exception("plain"))
        call_args = mock_logger.exception.call_args[0][0]
        assert "Context:" not in call_args


class TestLogPerformance:
    def test_logs_operation_and_duration(self):
        """Should log operation name and duration."""
        mock_logger = MagicMock()
        log_performance(mock_logger, "extraction", 2.5)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "extraction" in call_args
        assert "2.50s" in call_args

    def test_logs_with_details(self):
        """Should include details in log message."""
        mock_logger = MagicMock()
        log_performance(mock_logger, "query", 0.05, {"rows": 100, "table": "files"})

        call_args = mock_logger.info.call_args[0][0]
        assert "rows=100" in call_args
        assert "table=files" in call_args

    def test_logs_without_details(self):
        """Should work without details."""
        mock_logger = MagicMock()
        log_performance(mock_logger, "simple_op", 1.0)
        mock_logger.info.assert_called_once()


# ============================================================================
# REQUEST ID CONTEXT
# ============================================================================


class TestRequestIdContext:
    def test_default_value(self):
        """Default request ID should be 'no-request'."""
        assert request_id_ctx.get() == "no-request"

    def test_set_and_get(self):
        """Should be able to set and get request ID."""
        token = request_id_ctx.set("req-12345")
        assert request_id_ctx.get() == "req-12345"
        request_id_ctx.reset(token)


# ============================================================================
# AUDIT MIDDLEWARE
# ============================================================================


class TestLogAuditEvent:
    def test_creates_audit_entry(self, db_session):
        """Should create an AuditLog record."""
        resource_id = uuid4()
        api_key_id = uuid4()

        entry = log_audit_event(
            db=db_session,
            action="upload",
            resource_type="file",
            resource_id=resource_id,
            api_key_id=api_key_id,
            ip_address="192.168.1.100",
            user_agent="TestClient/1.0",
            details={"filename": "test.xlsx"},
            status_code=200,
        )

        assert isinstance(entry, AuditLog)
        assert entry.action == "upload"
        assert entry.resource_type == "file"
        assert entry.resource_id == resource_id
        assert entry.ip_address == "192.168.1.100"
        assert entry.status_code == 200

    def test_creates_minimal_entry(self, db_session):
        """Should work with only required fields."""
        entry = log_audit_event(
            db=db_session,
            action="view",
            resource_type="job",
        )

        assert entry.action == "view"
        assert entry.resource_id is None
        assert entry.ip_address is None


class TestGetClientIp:
    def test_x_forwarded_for(self):
        """Should extract first IP from X-Forwarded-For."""
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "203.0.113.50, 70.41.3.18, 150.172.238.178"}
        assert get_client_ip(request) == "203.0.113.50"

    def test_x_real_ip(self):
        """Should use X-Real-IP when X-Forwarded-For is absent."""
        request = MagicMock()
        request.headers = {"X-Real-IP": "10.0.0.1"}
        assert get_client_ip(request) == "10.0.0.1"

    def test_direct_connection(self):
        """Should fall back to client host."""
        request = MagicMock()
        request.headers = {}
        request.client.host = "127.0.0.1"
        assert get_client_ip(request) == "127.0.0.1"

    def test_no_client(self):
        """Should return 'unknown' when no client info available."""
        request = MagicMock()
        request.headers = {}
        request.client = None
        assert get_client_ip(request) == "unknown"

    def test_x_forwarded_for_single_ip(self):
        """Should handle single IP in X-Forwarded-For."""
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "192.168.1.1"}
        assert get_client_ip(request) == "192.168.1.1"
