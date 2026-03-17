"""Tests for security response headers."""


def test_security_headers_present(test_client_with_db):
    """All responses should include security headers."""
    response = test_client_with_db.get("/health/liveness")
    assert response.status_code == 200

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in response.headers
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "cdnjs.cloudflare.com" in csp


def test_security_headers_on_api_endpoint(test_client_with_db):
    """Security headers should be present on API endpoints too."""
    response = test_client_with_db.get("/api/v1/entities/")
    # Even if unauthorized, headers should be set
    assert "X-Frame-Options" in response.headers
    assert "X-Content-Type-Options" in response.headers
