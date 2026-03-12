"""Tests for file management API endpoints."""

from uuid import uuid4

from src.db import crud


class TestListFiles:
    """Test GET /api/v1/files/ endpoint."""

    def test_list_files_empty(self, test_client_with_db):
        resp = test_client_with_db.get("/api/v1/files/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["items"] == []

    def test_list_files_with_data(self, test_client_with_db, db_session):
        crud.create_file(db_session, filename="a.xlsx", file_size=1024)
        crud.create_file(db_session, filename="b.xlsx", file_size=2048)

        resp = test_client_with_db.get("/api/v1/files/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert all("filename" in item for item in data["items"])

    def test_list_files_pagination(self, test_client_with_db, db_session):
        for i in range(5):
            crud.create_file(db_session, filename=f"file{i}.xlsx", file_size=100)

        resp = test_client_with_db.get("/api/v1/files/?limit=2&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert data["limit"] == 2
        assert data["offset"] == 0

    def test_list_files_offset(self, test_client_with_db, db_session):
        for i in range(5):
            crud.create_file(db_session, filename=f"file{i}.xlsx", file_size=100)

        resp = test_client_with_db.get("/api/v1/files/?limit=10&offset=3")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2  # 5 total - 3 offset = 2 remaining


class TestGetFile:
    """Test GET /api/v1/files/{file_id} endpoint."""

    def test_get_file_not_found(self, test_client_with_db):
        fake_id = str(uuid4())
        resp = test_client_with_db.get(f"/api/v1/files/{fake_id}")
        assert resp.status_code == 404

    def test_get_file_invalid_uuid(self, test_client_with_db):
        resp = test_client_with_db.get("/api/v1/files/not-a-uuid")
        assert resp.status_code == 400

    def test_get_file_success(self, test_client_with_db, db_session):
        file = crud.create_file(db_session, filename="test.xlsx", file_size=1024)
        file_id = str(file.file_id)

        resp = test_client_with_db.get(f"/api/v1/files/{file_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "test.xlsx"
        assert data["file_size"] == 1024
        assert data["file_id"] == file_id

    def test_get_file_has_all_fields(self, test_client_with_db, db_session):
        file = crud.create_file(
            db_session,
            filename="model.xlsx",
            file_size=4096,
            content_hash="abc123",
        )

        resp = test_client_with_db.get(f"/api/v1/files/{file.file_id}")
        assert resp.status_code == 200
        data = resp.json()
        expected_keys = {
            "file_id",
            "filename",
            "file_size",
            "s3_key",
            "content_hash",
            "entity_id",
            "uploaded_at",
        }
        assert set(data.keys()) == expected_keys


class TestDownloadFile:
    """Test GET /api/v1/files/{file_id}/download endpoint."""

    def test_download_not_found(self, test_client_with_db):
        fake_id = str(uuid4())
        resp = test_client_with_db.get(f"/api/v1/files/{fake_id}/download")
        assert resp.status_code == 404

    def test_download_no_s3_key(self, test_client_with_db, db_session):
        file = crud.create_file(db_session, filename="test.xlsx", file_size=1024)
        resp = test_client_with_db.get(f"/api/v1/files/{file.file_id}/download")
        # File has no s3_key → 400
        assert resp.status_code == 400

    def test_download_success(self, test_client_with_db, db_session):
        from unittest.mock import MagicMock, patch

        file = crud.create_file(db_session, filename="test.xlsx", file_size=1024)
        file.s3_key = "uploads/2026/03/test.xlsx"
        db_session.commit()

        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://s3/presigned-url"

        with patch("src.api.files.get_s3_client", return_value=mock_s3):
            resp = test_client_with_db.get(f"/api/v1/files/{file.file_id}/download")

        assert resp.status_code == 200
        data = resp.json()
        assert data["download_url"] == "https://s3/presigned-url"
        assert data["expires_in"] == 3600
        assert data["filename"] == "test.xlsx"


class TestListFilesCRUD:
    """Test list_files CRUD function directly."""

    def test_list_files_empty(self, db_session):
        files = crud.list_files(db_session)
        assert files == []

    def test_list_files_with_data(self, db_session):
        crud.create_file(db_session, filename="a.xlsx", file_size=100)
        crud.create_file(db_session, filename="b.xlsx", file_size=200)
        files = crud.list_files(db_session)
        assert len(files) == 2

    def test_list_files_pagination(self, db_session):
        for i in range(5):
            crud.create_file(db_session, filename=f"file{i}.xlsx", file_size=100)
        files = crud.list_files(db_session, limit=2, offset=0)
        assert len(files) == 2
        files2 = crud.list_files(db_session, limit=2, offset=2)
        assert len(files2) == 2
