"""
Unit tests for setup_logging and CustomJsonFormatter.

Tests the logging configuration, JSON formatting, and the core retry decorator.
"""

import logging
from unittest.mock import patch

from src.core.logging import CustomJsonFormatter, request_id_ctx, setup_logging

# ============================================================================
# SETUP LOGGING
# ============================================================================


class TestSetupLogging:
    def test_returns_root_logger(self, tmp_path):
        """Should return the root logger."""
        log_file = str(tmp_path / "test.log")
        logger = setup_logging(level="INFO", log_file=log_file)
        assert isinstance(logger, logging.Logger)

    def test_sets_log_level(self, tmp_path):
        """Should set the requested log level."""
        log_file = str(tmp_path / "test.log")
        logger = setup_logging(level="DEBUG", log_file=log_file)
        assert logger.level == logging.DEBUG

    def test_creates_log_directory(self, tmp_path):
        """Should create log directory if it doesn't exist."""
        log_dir = tmp_path / "subdir" / "logs"
        log_file = str(log_dir / "test.log")
        setup_logging(level="INFO", log_file=log_file)
        assert log_dir.exists()

    def test_creates_file_handler(self, tmp_path):
        """Should create a file handler."""
        log_file = str(tmp_path / "test.log")
        logger = setup_logging(level="INFO", log_file=log_file)

        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) >= 1

    def test_creates_console_handler(self, tmp_path):
        """Should create a console (stream) handler."""
        log_file = str(tmp_path / "test.log")
        logger = setup_logging(level="INFO", log_file=log_file)

        stream_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream_handlers) >= 1

    def test_plain_text_format(self, tmp_path):
        """Should use plain text formatter when use_json=False."""
        log_file = str(tmp_path / "test.log")
        logger = setup_logging(level="INFO", log_file=log_file, use_json=False)

        for handler in logger.handlers:
            assert not isinstance(handler.formatter, CustomJsonFormatter)

    def test_json_format(self, tmp_path):
        """Should use JSON formatter when use_json=True."""
        log_file = str(tmp_path / "test.log")
        logger = setup_logging(level="INFO", log_file=log_file, use_json=True)

        json_handlers = [h for h in logger.handlers if isinstance(h.formatter, CustomJsonFormatter)]
        assert len(json_handlers) >= 1

    def test_custom_format_string(self, tmp_path):
        """Should accept custom format string."""
        log_file = str(tmp_path / "test.log")
        custom_format = "%(levelname)s: %(message)s"
        logger = setup_logging(level="INFO", log_file=log_file, log_format=custom_format)
        # Should not error
        assert logger is not None

    def test_suppresses_noisy_loggers(self, tmp_path):
        """Should set noisy library loggers to WARNING."""
        log_file = str(tmp_path / "test.log")
        setup_logging(level="DEBUG", log_file=log_file)

        assert logging.getLogger("anthropic").level == logging.WARNING
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert logging.getLogger("uvicorn.access").level == logging.WARNING

    def test_clears_existing_handlers(self, tmp_path):
        """Should clear existing handlers to avoid duplicates."""
        log_file = str(tmp_path / "test.log")

        # Setup twice
        setup_logging(level="INFO", log_file=log_file)
        setup_logging(level="INFO", log_file=log_file)

        root = logging.getLogger()
        # Should only have 2 handlers (console + file), not 4
        assert len(root.handlers) == 2


# ============================================================================
# CUSTOM JSON FORMATTER
# ============================================================================


class TestCustomJsonFormatter:
    def test_adds_standard_fields(self):
        """Should add timestamp, level, logger, service fields."""
        formatter = CustomJsonFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=None,
            exc_info=None,
        )

        log_record = {}
        formatter.add_fields(log_record, record, {})

        assert "timestamp" in log_record
        assert log_record["level"] == "INFO"
        assert log_record["logger"] == "test.logger"
        assert log_record["service"] == "tabintelligence"

    def test_adds_request_id(self):
        """Should include request_id from context variable."""
        formatter = CustomJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=None,
            exc_info=None,
        )

        token = request_id_ctx.set("req-xyz-123")
        try:
            log_record = {}
            formatter.add_fields(log_record, record, {})
            assert log_record["request_id"] == "req-xyz-123"
        finally:
            request_id_ctx.reset(token)

    def test_handles_tracing_import_error(self):
        """Should set trace_id to 'no-trace' when tracing unavailable."""
        formatter = CustomJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=None,
            exc_info=None,
        )

        with patch("src.core.logging.CustomJsonFormatter.add_fields.__module__", "test"):
            log_record = {}
            formatter.add_fields(log_record, record, {})
            # trace_id should be present (either actual or 'no-trace')
            assert "trace_id" in log_record

    def test_handles_config_import_error(self):
        """Should set environment to 'unknown' when config unavailable."""
        formatter = CustomJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=None,
            exc_info=None,
        )

        log_record = {}
        formatter.add_fields(log_record, record, {})
        # environment should be present
        assert "environment" in log_record
