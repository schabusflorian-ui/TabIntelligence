"""
Unit tests for API key authentication system.

Tests key generation, hashing, verification, and revocation.
"""
import pytest
import hashlib
from uuid import uuid4

from src.auth.api_key import generate_api_key, verify_api_key, create_api_key, revoke_api_key
from src.auth.models import APIKey
from src.db.models import Entity


class TestAPIKeyGeneration:
    """Test API key generation utilities."""

    def test_generate_api_key_returns_tuple(self):
        """Test that generate_api_key returns (key, hash) tuple."""
        key, key_hash = generate_api_key()
        assert isinstance(key, str)
        assert isinstance(key_hash, str)

    def test_generate_api_key_format(self):
        """Test that API key starts with 'emi_' prefix."""
        key, _ = generate_api_key()
        assert key.startswith("emi_")

    def test_generate_api_key_hash_is_sha256(self):
        """Test that hash is SHA256 of the key."""
        key, key_hash = generate_api_key()
        expected_hash = hashlib.sha256(key.encode()).hexdigest()
        assert key_hash == expected_hash

    def test_generate_api_key_hash_length(self):
        """Test that hash is 64 characters (SHA256 hex)."""
        _, key_hash = generate_api_key()
        assert len(key_hash) == 64

    def test_generate_api_key_unique(self):
        """Test that each generated key is unique."""
        keys = set()
        for _ in range(100):
            key, _ = generate_api_key()
            keys.add(key)
        assert len(keys) == 100

    def test_generate_api_key_sufficient_entropy(self):
        """Test that key has sufficient length for security."""
        key, _ = generate_api_key()
        # emi_ prefix (4) + 43 chars (32 bytes base64) = ~47 chars minimum
        assert len(key) >= 40


class TestAPIKeyModel:
    """Test APIKey model creation and defaults."""

    def test_create_api_key_model(self, db_session):
        """Test creating an APIKey model instance."""
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
