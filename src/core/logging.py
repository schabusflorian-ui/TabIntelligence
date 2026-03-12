"""
Centralized logging configuration for DebtFund.

Provides structured logging with:
- Console output (stdout)
- File output (logs/debtfund.log)
- JSON format support for production
- Correlation IDs (trace_id, request_id)
- Module-specific loggers
- Suppression of noisy libraries
"""

import logging
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

from pythonjsonlogger import jsonlogger

# Context variables for request tracking
request_id_ctx = ContextVar("request_id", default="no-request")


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    JSON formatter with trace context and correlation IDs.

    Adds standardized fields to every log record:
    - timestamp: ISO 8601 timestamp
    - level: Log level (INFO, WARNING, etc.)
    - logger: Logger name
    - message: Log message
    - trace_id: Distributed tracing ID
    - request_id: Request correlation ID
    - service: Service name
    - environment: production/development
    """

    def add_fields(self, log_record, record, message_dict):
        """Add custom fields to log record."""
        super().add_fields(log_record, record, message_dict)

        # Add standard fields
        log_record["timestamp"] = record.created
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["service"] = "debtfund"

        # Add trace context
        try:
            from src.core.tracing import get_current_trace_id

            log_record["trace_id"] = get_current_trace_id()
        except Exception:
            log_record["trace_id"] = "no-trace"

        log_record["request_id"] = request_id_ctx.get()

        # Add environment
        try:
            from src.core.config import get_settings

            settings = get_settings()
            log_record["environment"] = "production" if not settings.debug else "development"
        except Exception:
            log_record["environment"] = "unknown"


def setup_logging(
    level: str = "INFO",
    log_file: str = "logs/debtfund.log",
    log_format: Optional[str] = None,
    use_json: bool = False,
) -> logging.Logger:
    """
    Configure structured logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (relative to project root)
        log_format: Custom log format (uses default if None, ignored if use_json=True)
        use_json: Use JSON formatting (recommended for production)

    Returns:
        Root logger instance

    Example:
        >>> setup_logging(level="DEBUG", use_json=True)
        >>> logger = logging.getLogger("debtfund.extraction")
        >>> logger.info("Starting extraction")
    """
    # Create logs directory if it doesn't exist
    log_path = Path(log_file)
    log_path.parent.mkdir(exist_ok=True, parents=True)

    # Create formatters
    formatter: logging.Formatter
    if use_json:
        # JSON formatter for production
        formatter = CustomJsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(message)s",
            rename_fields={
                "levelname": "level",
                "name": "logger",
            },
        )
    else:
        # Plain text formatter for development
        if log_format is None:
            log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        formatter = logging.Formatter(log_format, datefmt="%Y-%m-%d %H:%M:%S")

    # Console handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_handler.setFormatter(formatter)

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(getattr(logging, level.upper()))
    file_handler.setFormatter(formatter)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Add handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Suppress noisy libraries
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    root_logger.info(f"Logging initialized - Level: {level}, File: {log_file}")

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    Args:
        name: Logger name (typically module name)

    Returns:
        Logger instance

    Example:
        >>> logger = get_logger("debtfund.extraction")
        >>> logger.info("Extraction started")
    """
    return logging.getLogger(name)


# Create module-specific loggers for common use
extraction_logger = logging.getLogger("debtfund.extraction")
api_logger = logging.getLogger("debtfund.api")
database_logger = logging.getLogger("debtfund.database")
lineage_logger = logging.getLogger("debtfund.lineage")
validation_logger = logging.getLogger("debtfund.validation")


class LogContext:
    """
    Context manager for temporary log level changes.

    Useful for debugging specific sections without changing global level.

    Example:
        >>> with LogContext("debtfund.extraction", "DEBUG"):
        ...     logger.debug("Detailed debugging info")
    """

    def __init__(self, logger_name: str, level: str):
        self.logger = logging.getLogger(logger_name)
        self.original_level = self.logger.level
        self.new_level = getattr(logging, level.upper())

    def __enter__(self):
        self.logger.setLevel(self.new_level)
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.setLevel(self.original_level)


def log_exception(logger: logging.Logger, exc: Exception, context: Optional[dict] = None):
    """
    Log an exception with additional context.

    Args:
        logger: Logger instance
        exc: Exception to log
        context: Additional context dictionary

    Example:
        >>> try:
        ...     risky_operation()
        ... except Exception as e:
        ...     log_exception(logger, e, {"file_id": "123", "stage": "parsing"})
    """
    error_msg = f"{exc.__class__.__name__}: {str(exc)}"

    if context:
        error_msg += f" | Context: {context}"

    # Log with traceback
    logger.exception(error_msg)


def log_performance(
    logger: logging.Logger, operation: str, duration: float, details: Optional[dict] = None
):
    """
    Log performance metrics for operations.

    Args:
        logger: Logger instance
        operation: Operation name
        duration: Duration in seconds
        details: Additional details (tokens, cost, etc.)

    Example:
        >>> import time
        >>> start = time.time()
        >>> result = extraction_function()
        >>> duration = time.time() - start
        >>> log_performance(logger, "extraction", duration, {"tokens": 1000})
    """
    msg = f"Performance | {operation}: {duration:.2f}s"

    if details:
        detail_str = ", ".join([f"{k}={v}" for k, v in details.items()])
        msg += f" | {detail_str}"

    logger.info(msg)
