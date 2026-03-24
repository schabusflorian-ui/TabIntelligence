"""
Tests for S3/MinIO storage client.

Note: boto3 is mocked at the module level in conftest.py, so all S3 operations
use the mock client. No real S3/MinIO connection is needed.
"""

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest


class TestS3ClientInit:
    """Test S3Client initialization."""

    def test_creates_client_with_settings(self):
        """Test S3Client initializes with correct parameters."""
        from src.storage.s3 import S3Client

        client = S3Client(
            endpoint="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="tabintelligence-test",
            verify_ssl=False,
        )

        assert client.endpoint == "http://localhost:9000"
        assert client.bucket_name == "tabintelligence-test"
        assert client.verify_ssl is False
        assert client.s3_client is not None


class TestUploadFile:
    """Test file upload operations."""

    def _make_client(self):
        from src.storage.s3 import S3Client

        return S3Client(
            endpoint="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="tabintelligence-test",
        )

    def test_upload_file_success(self):
        """Test successful file upload returns S3 key."""
        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.put_object.return_value = {"ETag": "mock-etag"}

        result = client.upload_file(
            file_bytes=b"test file content",
            s3_key="uploads/2024/02/file123.xlsx",
        )

        assert result == "uploads/2024/02/file123.xlsx"
        client.s3_client.put_object.assert_called_once()

    def test_upload_file_with_metadata(self):
        """Test upload includes metadata when provided."""
        client = self._make_client()
        client.s3_client = MagicMock()

        client.upload_file(
            file_bytes=b"test",
            s3_key="uploads/test.xlsx",
            metadata={"file_id": "abc-123", "Filename": "test.xlsx"},
        )

        call_kwargs = client.s3_client.put_object.call_args[1]
        assert "Metadata" in call_kwargs
        assert call_kwargs["Metadata"]["file_id"] == "abc-123"
        # Keys should be lowercased
        assert "filename" in call_kwargs["Metadata"]

    def test_upload_raises_on_generic_error(self):
        """Test upload raises FileStorageError on unexpected exception."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.put_object.side_effect = RuntimeError("disk full")

        with pytest.raises(FileStorageError, match="Unexpected storage error"):
            client.upload_file(b"test", "uploads/test.xlsx")


class TestDownloadFile:
    """Test file download operations."""

    def _make_client(self):
        from src.storage.s3 import S3Client

        return S3Client(
            endpoint="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="tabintelligence-test",
        )

    def test_download_file_success(self):
        """Test successful file download returns bytes."""
        client = self._make_client()
        mock_body = MagicMock()
        mock_body.read.return_value = b"file content"
        client.s3_client = MagicMock()
        client.s3_client.get_object.return_value = {"Body": mock_body}

        result = client.download_file("uploads/test.xlsx")

        assert result == b"file content"

    def test_download_raises_on_generic_error(self):
        """Test download raises FileStorageError on unexpected exception."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.get_object.side_effect = RuntimeError("network error")

        with pytest.raises(FileStorageError, match="Unexpected storage error"):
            client.download_file("uploads/test.xlsx")


class TestGenerateS3Key:
    """Test S3 key generation."""

    def _make_client(self):
        from src.storage.s3 import S3Client

        return S3Client(
            endpoint="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="tabintelligence-test",
        )

    def test_generates_key_with_date_partition(self):
        """Test key includes year/month partition."""
        client = self._make_client()
        file_id = UUID("12345678-1234-5678-1234-567812345678")

        key = client.generate_s3_key(file_id, "model.xlsx")

        assert key.startswith("uploads/")
        assert str(file_id) in key
        assert key.endswith("model.xlsx")

    def test_sanitizes_filename(self):
        """Test special characters in filename are sanitized."""
        client = self._make_client()
        file_id = UUID("12345678-1234-5678-1234-567812345678")

        key = client.generate_s3_key(file_id, "my model (v2).xlsx")

        assert "()" not in key
        assert " " not in key

    def test_custom_prefix(self):
        """Test custom prefix is used."""
        client = self._make_client()
        file_id = UUID("12345678-1234-5678-1234-567812345678")

        key = client.generate_s3_key(file_id, "file.xlsx", prefix="archive")

        assert key.startswith("archive/")


class TestEnsureBucketExists:
    """Test bucket existence check and creation."""

    def _make_client(self):
        from src.storage.s3 import S3Client

        return S3Client(
            endpoint="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="tabintelligence-test",
        )

    def test_bucket_already_exists(self):
        """Test no error when bucket exists."""
        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.head_bucket.return_value = {}

        # Should not raise
        client.ensure_bucket_exists()
        client.s3_client.head_bucket.assert_called_once()

    def test_raises_on_unexpected_error(self):
        """Test raises FileStorageError on unexpected exception."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.head_bucket.side_effect = RuntimeError("timeout")

        with pytest.raises(FileStorageError, match="Unexpected error"):
            client.ensure_bucket_exists()


class TestFileExists:
    """Test file existence check."""

    def _make_client(self):
        from src.storage.s3 import S3Client

        return S3Client(
            endpoint="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="tabintelligence-test",
        )

    def test_file_exists_returns_true(self):
        """Test returns True when file exists."""
        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.head_object.return_value = {}

        assert client.file_exists("uploads/test.xlsx") is True

    def test_file_not_exists_raises_on_unexpected_error(self):
        """Test raises on unexpected error."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.head_object.side_effect = RuntimeError("fail")

        with pytest.raises(FileStorageError, match="Unexpected error"):
            client.file_exists("uploads/test.xlsx")


class TestDeleteFile:
    """Test file deletion."""

    def _make_client(self):
        from src.storage.s3 import S3Client

        return S3Client(
            endpoint="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="tabintelligence-test",
        )

    def test_delete_existing_file(self):
        """Test successful file deletion."""
        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.head_object.return_value = {}
        client.s3_client.delete_object.return_value = {}

        result = client.delete_file("uploads/test.xlsx")

        assert result is True
        client.s3_client.delete_object.assert_called_once()

    def test_delete_raises_on_unexpected_error(self):
        """Test raises on unexpected error during deletion."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        # file_exists succeeds
        client.s3_client.head_object.return_value = {}
        # but delete raises
        client.s3_client.delete_object.side_effect = RuntimeError("fail")

        with pytest.raises(FileStorageError, match="Unexpected error"):
            client.delete_file("uploads/test.xlsx")


class TestGetFileMetadata:
    """Test file metadata retrieval."""

    def _make_client(self):
        from src.storage.s3 import S3Client

        return S3Client(
            endpoint="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="tabintelligence-test",
        )

    def test_get_metadata_success(self):
        """Test successful metadata retrieval."""
        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.head_object.return_value = {
            "ContentLength": 50000,
            "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "ETag": '"abc123"',
            "Metadata": {"file_id": "test-id"},
        }

        result = client.get_file_metadata("uploads/test.xlsx")

        assert result["size"] == 50000
        assert result["content_type"].startswith("application/")
        assert result["etag"] == "abc123"
        assert result["metadata"]["file_id"] == "test-id"

    def test_get_metadata_raises_on_unexpected_error(self):
        """Test raises on unexpected error."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.head_object.side_effect = RuntimeError("fail")

        with pytest.raises(FileStorageError, match="Unexpected error"):
            client.get_file_metadata("uploads/test.xlsx")


class TestUploadClientError:
    """Test upload with botocore ClientError variants."""

    def _make_client(self):
        from src.storage.s3 import S3Client

        return S3Client(
            endpoint="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="tabintelligence-test",
        )

    def _make_client_error(self, code="Unknown"):
        from botocore.exceptions import ClientError

        return ClientError(
            error_response={"Error": {"Code": code, "Message": "test error"}},
            operation_name="PutObject",
        )

    def test_upload_no_such_bucket(self):
        """Test upload raises on NoSuchBucket."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.put_object.side_effect = self._make_client_error("NoSuchBucket")

        with pytest.raises(FileStorageError, match="not found"):
            client.upload_file(b"data", "uploads/test.xlsx")

    def test_upload_generic_client_error(self):
        """Test upload raises on other ClientError codes."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.put_object.side_effect = self._make_client_error("AccessDenied")

        with pytest.raises(FileStorageError, match="Failed to upload"):
            client.upload_file(b"data", "uploads/test.xlsx")

    def test_upload_no_credentials(self):
        """Test upload raises on NoCredentialsError."""
        from botocore.exceptions import NoCredentialsError

        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.put_object.side_effect = NoCredentialsError()

        with pytest.raises(FileStorageError, match="Invalid S3 credentials"):
            client.upload_file(b"data", "uploads/test.xlsx")

    def test_upload_endpoint_connection_error(self):
        """Test upload raises on EndpointConnectionError."""
        from botocore.exceptions import EndpointConnectionError

        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.put_object.side_effect = EndpointConnectionError()

        with pytest.raises(FileStorageError, match="Cannot connect"):
            client.upload_file(b"data", "uploads/test.xlsx")


class TestDownloadClientError:
    """Test download with botocore ClientError variants."""

    def _make_client(self):
        from src.storage.s3 import S3Client

        return S3Client(
            endpoint="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="tabintelligence-test",
        )

    def _make_client_error(self, code="Unknown"):
        from botocore.exceptions import ClientError

        return ClientError(
            error_response={"Error": {"Code": code, "Message": "test error"}},
            operation_name="GetObject",
        )

    def test_download_no_such_key(self):
        """Test download raises on NoSuchKey."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.get_object.side_effect = self._make_client_error("NoSuchKey")

        with pytest.raises(FileStorageError, match="File not found"):
            client.download_file("uploads/missing.xlsx")

    def test_download_no_such_bucket(self):
        """Test download raises on NoSuchBucket."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.get_object.side_effect = self._make_client_error("NoSuchBucket")

        with pytest.raises(FileStorageError, match="not found"):
            client.download_file("uploads/test.xlsx")

    def test_download_generic_client_error(self):
        """Test download raises on other ClientError codes."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.get_object.side_effect = self._make_client_error("InternalError")

        with pytest.raises(FileStorageError, match="Failed to download"):
            client.download_file("uploads/test.xlsx")

    def test_download_no_credentials(self):
        """Test download raises on NoCredentialsError."""
        from botocore.exceptions import NoCredentialsError

        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.get_object.side_effect = NoCredentialsError()

        with pytest.raises(FileStorageError, match="Invalid S3 credentials"):
            client.download_file("uploads/test.xlsx")

    def test_download_endpoint_connection_error(self):
        """Test download raises on EndpointConnectionError."""
        from botocore.exceptions import EndpointConnectionError

        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.get_object.side_effect = EndpointConnectionError()

        with pytest.raises(FileStorageError, match="Cannot connect"):
            client.download_file("uploads/test.xlsx")


class TestEnsureBucketClientError:
    """Test ensure_bucket_exists with ClientError variants."""

    def _make_client(self):
        from src.storage.s3 import S3Client

        return S3Client(
            endpoint="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="tabintelligence-test",
        )

    def _make_client_error(self, code="Unknown"):
        from botocore.exceptions import ClientError

        return ClientError(
            error_response={"Error": {"Code": code, "Message": "test error"}},
            operation_name="HeadBucket",
        )

    def test_creates_bucket_when_not_found(self):
        """Test bucket is created when 404 received."""
        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.head_bucket.side_effect = self._make_client_error("404")
        client.s3_client.create_bucket.return_value = {}

        # Should not raise
        client.ensure_bucket_exists()
        client.s3_client.create_bucket.assert_called_once()

    def test_raises_when_bucket_creation_fails(self):
        """Test raises when bucket creation itself fails."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.head_bucket.side_effect = self._make_client_error("404")
        client.s3_client.create_bucket.side_effect = self._make_client_error("AccessDenied")

        with pytest.raises(FileStorageError, match="Failed to create bucket"):
            client.ensure_bucket_exists()

    def test_raises_on_other_client_error(self):
        """Test raises on non-404 ClientError."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.head_bucket.side_effect = self._make_client_error("Forbidden")

        with pytest.raises(FileStorageError, match="Failed to check bucket"):
            client.ensure_bucket_exists()


class TestFileExistsClientError:
    """Test file_exists with ClientError variants."""

    def _make_client(self):
        from src.storage.s3 import S3Client

        return S3Client(
            endpoint="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="tabintelligence-test",
        )

    def _make_client_error(self, code="Unknown"):
        from botocore.exceptions import ClientError

        return ClientError(
            error_response={"Error": {"Code": code, "Message": "test error"}},
            operation_name="HeadObject",
        )

    def test_returns_false_on_404(self):
        """Test returns False when file not found (404)."""
        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.head_object.side_effect = self._make_client_error("404")

        assert client.file_exists("uploads/missing.xlsx") is False

    def test_raises_on_other_client_error(self):
        """Test raises on non-404 ClientError."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.head_object.side_effect = self._make_client_error("Forbidden")

        with pytest.raises(FileStorageError, match="Failed to check if file exists"):
            client.file_exists("uploads/test.xlsx")


class TestGetMetadataClientError:
    """Test get_file_metadata with ClientError variants."""

    def _make_client(self):
        from src.storage.s3 import S3Client

        return S3Client(
            endpoint="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="tabintelligence-test",
        )

    def _make_client_error(self, code="Unknown"):
        from botocore.exceptions import ClientError

        return ClientError(
            error_response={"Error": {"Code": code, "Message": "test error"}},
            operation_name="HeadObject",
        )

    def test_raises_on_not_found(self):
        """Test raises FileStorageError when file not found."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.head_object.side_effect = self._make_client_error("404")

        with pytest.raises(FileStorageError, match="File not found"):
            client.get_file_metadata("uploads/missing.xlsx")

    def test_raises_on_other_client_error(self):
        """Test raises on non-404 ClientError."""
        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.head_object.side_effect = self._make_client_error("InternalError")

        with pytest.raises(FileStorageError, match="Failed to get file metadata"):
            client.get_file_metadata("uploads/test.xlsx")


class TestPresignedUrl:
    """Test generate_presigned_url method."""

    def _make_client(self):
        from src.storage.s3 import S3Client

        return S3Client(
            endpoint="http://localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="tabintelligence-test",
        )

    def test_presigned_url_success(self):
        """Test successful presigned URL generation."""
        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.generate_presigned_url.return_value = "https://s3/presigned-url"

        url = client.generate_presigned_url("uploads/test.xlsx")

        assert url == "https://s3/presigned-url"
        client.s3_client.generate_presigned_url.assert_called_once()
        call_kwargs = client.s3_client.generate_presigned_url.call_args
        assert call_kwargs[0][0] == "get_object"
        assert call_kwargs[1]["ExpiresIn"] == 3600

    def test_presigned_url_with_filename(self):
        """Test presigned URL includes Content-Disposition when filename given."""
        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.generate_presigned_url.return_value = "https://s3/url"

        client.generate_presigned_url("uploads/test.xlsx", filename="model.xlsx")

        call_kwargs = client.s3_client.generate_presigned_url.call_args
        params = call_kwargs[1]["Params"]
        assert "ResponseContentDisposition" in params
        assert "model.xlsx" in params["ResponseContentDisposition"]

    def test_presigned_url_clamps_expiry(self):
        """Test expires_in is clamped to 7 days max."""
        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.generate_presigned_url.return_value = "https://s3/url"

        client.generate_presigned_url("uploads/test.xlsx", expires_in=999999)

        call_kwargs = client.s3_client.generate_presigned_url.call_args
        assert call_kwargs[1]["ExpiresIn"] == 604800

    def test_presigned_url_client_error(self):
        """Test raises FileStorageError on ClientError."""
        from botocore.exceptions import ClientError

        from src.core.exceptions import FileStorageError

        client = self._make_client()
        client.s3_client = MagicMock()
        client.s3_client.generate_presigned_url.side_effect = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "denied"}},
            operation_name="GeneratePresignedUrl",
        )

        with pytest.raises(FileStorageError):
            client.generate_presigned_url("uploads/test.xlsx")


class TestGetS3ClientFactory:
    """Test the get_s3_client factory function."""

    def test_creates_client_from_settings(self):
        """Test factory creates client with settings values."""
        from src.storage.s3 import get_s3_client

        mock_settings = MagicMock()
        mock_settings.s3_endpoint = "http://localhost:9000"
        mock_settings.s3_access_key = "minioadmin"
        mock_settings.s3_secret_key = "minioadmin"
        mock_settings.s3_bucket = "tabintelligence"
        mock_settings.s3_verify_ssl = False

        client = get_s3_client(mock_settings)

        assert client.endpoint == "http://localhost:9000"
        assert client.bucket_name == "tabintelligence"

    def test_creates_client_with_default_settings(self):
        """Test factory uses get_settings() when no settings provided."""
        from src.storage.s3 import get_s3_client

        mock_settings = MagicMock()
        mock_settings.s3_endpoint = "http://localhost:9000"
        mock_settings.s3_access_key = "key"
        mock_settings.s3_secret_key = "secret"
        mock_settings.s3_bucket = "bucket"
        mock_settings.s3_verify_ssl = True

        # get_settings is imported inside get_s3_client body
        with patch("src.core.config.get_settings", return_value=mock_settings):
            client = get_s3_client()

        assert client.bucket_name == "bucket"
