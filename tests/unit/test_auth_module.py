"""
Unit tests for authentication module.

Tests API key generation, verification, creation, and revocation.
"""
import hashlib
import pytest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.auth.api_key import generate_api_key


# ============================================================================
# GENERATE API KEY
# ============================================================================


class TestGenerateApiKey:

    def test_returns_tuple_of_key_and_hash(self):
        """Should return (plain_key, key_hash) tuple."""
        key, key_hash = generate_api_key()
        assert isinstance(key, str)
        assert isinstance(key_hash, str)

    def test_key_has_emi_prefix(self):
        """Key should start with 'emi_' prefix."""
        key, _ = generate_api_key()
        assert key.startswith("emi_")

    def test_hash_is_sha256(self):
        """Hash should be SHA256 of the key."""
        key, key_hash = generate_api_key()
        expected_hash = hashlib.sha256(key.encode()).hexdigest()
        assert key_hash == expected_hash

    def test_hash_length(self):
        """SHA256 hash should be 64 hex characters."""
        _, key_hash = generate_api_key()
        assert len(key_hash) == 64

    def test_keys_are_unique(self):
        """Each call should produce a unique key."""
        keys = set()
        for _ in range(10):
            key, _ = generate_api_key()
            keys.add(key)
        assert len(keys) == 10

    def test_key_is_url_safe(self):
        """Key should only contain URL-safe characters."""
        key, _ = generate_api_key()
        token = key[4:]
        import re
        assert re.match(r'^[a-zA-Z0-9_-]+$', token)


# ============================================================================
# VERIFY API KEY (sync)
# ============================================================================


class TestVerifyApiKey:

    def test_returns_api_key_on_valid_key(self):
        """Should return APIKey record for valid active key."""
        from src.auth.api_key import verify_api_key

        mock_api_key = MagicMock()
        mock_api_key.name = "test-key"
        mock_api_key.entity_id = uuid4()
        mock_api_key.last_used_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_api_key

        mock_db = MagicMock()
        mock_db.execute.return_value = mock_result

        result = verify_api_key("emi_test123", mock_db)
        assert result == mock_api_key
        mock_db.execute.assert_called_once()

    def test_returns_none_on_invalid_key(self):
        """Should return None for invalid key."""
        from src.auth.api_key import verify_api_key

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = MagicMock()
        mock_db.execute.return_value = mock_result

        result = verify_api_key("emi_invalid_key", mock_db)
        assert result is None

    def test_hashes_key_before_lookup(self):
        """Should hash the provided key for database lookup."""
        from src.auth.api_key import verify_api_key

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = MagicMock()
        mock_db.execute.return_value = mock_result

        verify_api_key("emi_test_key_123", mock_db)
        mock_db.execute.assert_called_once()


# ============================================================================
# CREATE API KEY (sync)
# ============================================================================


class TestCreateApiKey:

    def test_creates_key_and_returns_record(self):
        """Should create key record and return (record, plain_key)."""
        from src.auth.api_key import create_api_key

        mock_db = MagicMock()

        api_key_record, plain_key = create_api_key(
            mock_db, name="Test Key"
        )

        assert plain_key.startswith("emi_")
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    def test_creates_key_with_entity_id(self):
        """Should associate key with entity."""
        from src.auth.api_key import create_api_key

        mock_db = MagicMock()
        entity_id = uuid4()

        api_key_record, _ = create_api_key(
            mock_db, name="Entity Key", entity_id=entity_id
        )

        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.entity_id == entity_id

    def test_creates_key_with_custom_rate_limit(self):
        """Should set custom rate limit."""
        from src.auth.api_key import create_api_key

        mock_db = MagicMock()

        api_key_record, _ = create_api_key(
            mock_db, name="Premium Key", rate_limit_per_minute=120
        )

        added_obj = mock_db.add.call_args[0][0]
        assert added_obj.rate_limit_per_minute == 120


# ============================================================================
# REVOKE API KEY (sync)
# ============================================================================


class TestRevokeApiKey:

    def test_revokes_existing_key(self):
        """Should deactivate key and return True."""
        from src.auth.api_key import revoke_api_key

        mock_api_key = MagicMock()
        mock_api_key.is_active = True
        mock_api_key.name = "test-key"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_api_key

        mock_db = MagicMock()
        mock_db.execute.return_value = mock_result

        result = revoke_api_key(mock_db, uuid4())
        assert result is True
        assert mock_api_key.is_active is False
        mock_db.commit.assert_called_once()

    def test_returns_false_for_nonexistent_key(self):
        """Should return False when key not found."""
        from src.auth.api_key import revoke_api_key

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = MagicMock()
        mock_db.execute.return_value = mock_result

        result = revoke_api_key(mock_db, uuid4())
        assert result is False
        mock_db.commit.assert_not_called()


# ============================================================================
# AUTH DEPENDENCIES (sync)
# ============================================================================


class TestGetCurrentApiKey:

    def test_returns_api_key_on_valid_credentials(self):
        """Should return APIKey when credentials are valid."""
        from src.auth.dependencies import get_current_api_key

        mock_api_key = MagicMock()
        mock_api_key.name = "valid-key"
        mock_api_key.entity_id = uuid4()

        mock_credentials = MagicMock()
        mock_credentials.credentials = "emi_valid_key"

        mock_db = MagicMock()

        with patch("src.auth.dependencies.verify_api_key", return_value=mock_api_key):
            result = get_current_api_key(
                credentials=mock_credentials, db=mock_db
            )

        assert result == mock_api_key
        mock_db.commit.assert_called_once()

    def test_raises_401_on_invalid_credentials(self):
        """Should raise HTTPException 401 when key is invalid."""
        from fastapi import HTTPException
        from src.auth.dependencies import get_current_api_key

        mock_credentials = MagicMock()
        mock_credentials.credentials = "emi_invalid_key"

        mock_db = MagicMock()

        with patch("src.auth.dependencies.verify_api_key", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                get_current_api_key(
                    credentials=mock_credentials, db=mock_db
                )

            assert exc_info.value.status_code == 401


class TestGetOptionalApiKey:

    def test_returns_none_when_no_credentials(self):
        """Should return None when no credentials provided."""
        from src.auth.dependencies import get_optional_api_key

        mock_db = MagicMock()

        result = get_optional_api_key(credentials=None, db=mock_db)
        assert result is None

    def test_returns_api_key_when_credentials_valid(self):
        """Should return APIKey when valid credentials provided."""
        from src.auth.dependencies import get_optional_api_key

        mock_api_key = MagicMock()
        mock_api_key.name = "optional-key"

        mock_credentials = MagicMock()
        mock_credentials.credentials = "emi_optional_key"

        mock_db = MagicMock()

        with patch("src.auth.dependencies.verify_api_key", return_value=mock_api_key):
            result = get_optional_api_key(
                credentials=mock_credentials, db=mock_db
            )

        assert result == mock_api_key
        mock_db.commit.assert_called_once()

    def test_returns_none_when_credentials_invalid(self):
        """Should return None when credentials are invalid (no exception)."""
        from src.auth.dependencies import get_optional_api_key

        mock_credentials = MagicMock()
        mock_credentials.credentials = "emi_bad_key"

        mock_db = MagicMock()

        with patch("src.auth.dependencies.verify_api_key", return_value=None):
            result = get_optional_api_key(
                credentials=mock_credentials, db=mock_db
            )

        assert result is None


# ============================================================================
# MODEL INTEGRATION TESTS (with DB session)
# ============================================================================


class TestAPIKeyModel:
    """Test APIKey model creation and defaults."""

    def test_create_api_key_model(self, db_session):
        """Test creating an APIKey model instance."""
        from src.auth.models import APIKey
        _, key_hash = generate_api_key()

        api_key = APIKey(
            name="Test Key",
            key_hash=key_hash,
            is_active=True,
            rate_limit_per_minute=60,
        )
        db_session.add(api_key)
        db_session.commit()

        assert api_key.id is not None
        assert api_key.name == "Test Key"
        assert api_key.key_hash == key_hash
        assert api_key.is_active is True
        assert api_key.rate_limit_per_minute == 60

    def test_api_key_with_entity(self, db_session):
        """Test creating APIKey associated with an entity."""
        from src.auth.models import APIKey
        from src.db.models import Entity

        entity = Entity(name="Test Corp", industry="Technology")
        db_session.add(entity)
        db_session.commit()

        _, key_hash = generate_api_key()
        api_key = APIKey(
            name="Entity Scoped Key",
            key_hash=key_hash,
            entity_id=entity.id,
            is_active=True,
        )
        db_session.add(api_key)
        db_session.commit()

        assert api_key.entity_id == entity.id

    def test_api_key_default_rate_limit(self, db_session):
        """Test that default rate limit is set."""
        from src.auth.models import APIKey
        _, key_hash = generate_api_key()

        api_key = APIKey(
            name="Default Rate Limit Key",
            key_hash=key_hash,
        )
        db_session.add(api_key)
        db_session.commit()

        assert api_key.rate_limit_per_minute == 60

    def test_api_key_repr(self, db_session):
        """Test APIKey string representation."""
        from src.auth.models import APIKey
        _, key_hash = generate_api_key()

        api_key = APIKey(
            name="Repr Test",
            key_hash=key_hash,
        )
        db_session.add(api_key)
        db_session.commit()

        repr_str = repr(api_key)
        assert "APIKey" in repr_str
        assert "Repr Test" in repr_str


class TestAuditLogModel:
    """Test AuditLog model creation."""

    def test_create_audit_log(self, db_session):
        """Test creating an audit log entry."""
        from uuid import uuid4
        from src.db.models import AuditLog

        log = AuditLog(
            action="upload",
            resource_type="file",
            resource_id=uuid4(),
            ip_address="127.0.0.1",
            details={"filename": "test.xlsx"},
            status_code=200,
        )
        db_session.add(log)
        db_session.commit()

        assert log.id is not None
        assert log.action == "upload"
        assert log.resource_type == "file"
        assert log.ip_address == "127.0.0.1"
        assert log.details["filename"] == "test.xlsx"
        assert log.status_code == 200

    def test_audit_log_repr(self, db_session):
        """Test AuditLog string representation."""
        from uuid import uuid4
        from src.db.models import AuditLog

        resource_id = uuid4()
        log = AuditLog(
            action="view",
            resource_type="job",
            resource_id=resource_id,
        )
        db_session.add(log)
        db_session.commit()

        repr_str = repr(log)
        assert "AuditLog" in repr_str
        assert "view" in repr_str
