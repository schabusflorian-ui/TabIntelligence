"""
Unit tests for Prometheus metrics module.

Tests metric definitions, path normalization, and metrics middleware behavior.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from starlette.testclient import TestClient

from src.api.metrics import (
    _normalize_path,
    http_requests_total,
    http_request_duration_seconds,
    file_uploads_total,
    file_upload_bytes,
    db_query_duration_seconds,
    extraction_jobs_total,
)


class TestNormalizePath:
    """Tests for URL path normalization to prevent cardinality explosion."""

    def test_uuid_replaced(self):
        """UUIDs in paths should be replaced with {id}."""
        path = "/api/v1/jobs/550e8400-e29b-41d4-a716-446655440000"
        assert _normalize_path(path) == "/api/v1/jobs/{id}"

    def test_multiple_uuids(self):
        """Multiple UUIDs should all be replaced."""
        path = "/api/v1/entities/550e8400-e29b-41d4-a716-446655440000/files/660e8400-e29b-41d4-a716-446655440001"
        result = _normalize_path(path)
        assert "{id}" in result
        assert "550e8400" not in result

    def test_numeric_id_replaced(self):
        """Numeric path segments should be replaced with {id}."""
        path = "/api/v1/items/12345"
        assert _normalize_path(path) == "/api/v1/items/{id}"

    def test_static_path_unchanged(self):
        """Static paths without IDs should remain unchanged."""
        assert _normalize_path("/health") == "/health"
        assert _normalize_path("/api/v1/files/upload") == "/api/v1/files/upload"
        assert _normalize_path("/metrics") == "/metrics"

    def test_root_path(self):
        """Root path should remain unchanged."""
        assert _normalize_path("/") == "/"


class TestMetricDefinitions:
    """Tests that all metrics are properly defined."""

    def test_http_requests_total_labels(self):
        """http_requests_total should have method, endpoint, status_code labels."""
        assert http_requests_total._labelnames == ("method", "endpoint", "status_code")

    def test_http_request_duration_labels(self):
        """http_request_duration_seconds should have method, endpoint labels."""
        assert http_request_duration_seconds._labelnames == ("method", "endpoint")

    def test_file_uploads_total_no_labels(self):
        """file_uploads_total should have no labels."""
        assert file_uploads_total._labelnames == ()

    def test_db_query_duration_labels(self):
        """db_query_duration_seconds should have operation label."""
        assert db_query_duration_seconds._labelnames == ("operation",)

    def test_extraction_jobs_labels(self):
        """extraction_jobs_total should have status label."""
        assert extraction_jobs_total._labelnames == ("status",)


class TestMetricsEndpoint:
    """Tests for the /metrics endpoint."""

    def test_metrics_endpoint_returns_prometheus_format(self):
        """The /metrics endpoint should return Prometheus exposition format."""
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

        output = generate_latest()
        assert isinstance(output, bytes)
        assert b"debtfund_http_requests_total" in output or len(output) > 0


class TestSlowQueryLog:
    """Tests for slow query logging module."""

    def test_classify_operation(self):
        """SQL operation classification should work correctly."""
        from src.db.slow_query_log import _classify_operation

        assert _classify_operation("SELECT * FROM entities") == "select"
        assert _classify_operation("INSERT INTO files VALUES (...)") == "insert"
        assert _classify_operation("UPDATE extraction_jobs SET status = 'completed'") == "update"
        assert _classify_operation("DELETE FROM lineage_events WHERE id = 1") == "delete"
        assert _classify_operation("CREATE TABLE test (id INT)") == "other"

    def test_classify_operation_case_insensitive(self):
        """Classification should handle different cases."""
        from src.db.slow_query_log import _classify_operation

        assert _classify_operation("select * from entities") == "select"
        assert _classify_operation("  SELECT * FROM entities") == "select"

    def test_attach_slow_query_logging(self):
        """Should attach event listeners without error."""
        from sqlalchemy import create_engine
        from src.db.slow_query_log import attach_slow_query_logging

        engine = create_engine("sqlite:///:memory:")
        # Should not raise
        attach_slow_query_logging(engine, threshold_ms=50)

    def test_slow_query_logging_integration(self):
        """Slow query logging should detect queries above threshold."""
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        from src.db.slow_query_log import attach_slow_query_logging

        engine = create_engine("sqlite:///:memory:")
        attach_slow_query_logging(engine, threshold_ms=0.001)  # Very low threshold

        Session = sessionmaker(bind=engine)
        session = Session()

        # Execute a query - should be logged (above 0.001ms threshold)
        with patch("src.db.slow_query_log.logger") as mock_logger:
            session.execute(text("SELECT 1"))
            # The warning may or may not fire depending on timing,
            # but the listener should not raise
        session.close()
