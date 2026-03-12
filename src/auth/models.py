"""
Authentication models for API key management.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.db.base import Base


class APIKey(Base):
    """
    API key for authentication.

    Security:
    - Keys are stored as SHA256 hashes (never plaintext)
    - Each key can be associated with an entity for scope limiting
    - Keys can be deactivated without deletion (audit trail)
    - Last used timestamp for activity monitoring
    - Configurable rate limits per key
    """

    __tablename__ = "api_keys"

    # Primary key
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Security fields
    key_hash: Mapped[str] = mapped_column(
        String(64),  # SHA256 produces 64 hex characters
        unique=True,
        nullable=False,
        comment="SHA256 hash of the API key (never store plaintext)",
    )

    # Metadata
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Human-readable name for this key"
    )

    # Optional entity scope
    entity_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=True,
        comment="Optional entity scope for this key",
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="Whether key is active"
    )

    # Rate limiting
    rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer, default=60, nullable=False, comment="Max requests per minute"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When this key was created",
    )

    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time this key was used successfully",
    )

    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this key expires (null = never)",
    )

    # Relationships
    entity = relationship("Entity", back_populates="api_keys")

    # Table arguments
    __table_args__ = (
        Index("ix_api_keys_key_hash", "key_hash"),
        Index("ix_api_keys_is_active", "is_active"),
        Index("ix_api_keys_entity_id", "entity_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<APIKey(id={self.id}, name='{self.name}', "
            f"active={self.is_active}, entity_id={self.entity_id})>"
        )
