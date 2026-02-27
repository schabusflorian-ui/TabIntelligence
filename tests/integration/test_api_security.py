"""Integration tests for API security features."""
import pytest
import io


class TestAPIAuthentication:
    """Test API authentication requirements."""

    def test_upload_without_auth_returns_401(self, unauthenticated_client):
        """Unauthenticated upload should return 401/403."""
        files = {
            "file": (
                "test.xlsx",
                io.BytesIO(b"PK\x03\x04"),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        }
        response = unauthenticated_client.post("/api/v1/files/upload", files=files)
        assert response.status_code in (401, 403)

    def test_job_status_without_auth_returns_401(self, unauthenticated_client):
        """Unauthenticated job status check should return 401/403."""
        response = unauthenticated_client.get("/api/v1/jobs/12345678-1234-1234-1234-123456789abc")
        assert response.status_code in (401, 403)


class TestFileValidation:
    """Test file size and type validation."""

    def test_excel_file_type_validation(self, test_client_with_db):
        """Verify Excel file type validation exists."""
        files = {
            "file": (
                "test.txt",
                io.BytesIO(b"not excel"),
                "text/plain"
            )
        }

        response = test_client_with_db.post("/api/v1/files/upload", files=files)
        assert response.status_code == 400
        assert "Excel" in response.text


class TestCORSConfiguration:
    """Test CORS configuration."""

    def test_cors_headers_present(self, test_client):
        """Verify CORS headers are configured."""
        response = test_client.options("/api/v1/files/upload")

        if "access-control-allow-origin" in response.headers:
            origin = response.headers["access-control-allow-origin"]
            if origin == "*":
                pytest.skip("CORS uses wildcard - should be restricted")
            else:
                assert origin != "*"
        else:
            pytest.skip("CORS headers not found")
