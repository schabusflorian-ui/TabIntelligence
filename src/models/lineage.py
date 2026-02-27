"""
Lineage event model for tracking data provenance.
Stores complete lineage chains across all extraction stages.
"""
from sqlalchemy import Column, String, Integer, JSON, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

from src.models.base import Base


class LineageEvent(Base):
    """
    Lineage event tracking input → output transformations.

    Each stage in the extraction pipeline emits one or more lineage events
    documenting what inputs were consumed and what outputs were produced.
    """
    __tablename__ = "lineage_events"

    # Primary identifiers
    event_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique event identifier"
    )

    job_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Job this event belongs to"
    )

    # Event classification
    event_type = Column(
        String(50),
        nullable=False,
        comment="Type of transformation (parse, triage, map, etc.)"
    )

    stage = Column(
        Integer,
        nullable=False,
        index=True,
        comment="Pipeline stage number (1-5)"
    )

    # Lineage chain
    input_lineage_id = Column(
        UUID(as_uuid=True),
        nullable=True,  # Stage 1 has no input lineage
        comment="Lineage ID of input data"
    )

    output_lineage_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Lineage ID of output data"
    )

    # Metadata
    event_metadata = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Stage-specific metadata (tokens, sheet names, etc.)"
    )

    timestamp = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
        comment="When event was created"
    )

    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_lineage_job_stage', 'job_id', 'stage'),
        Index('idx_lineage_output', 'output_lineage_id'),
        Index('idx_lineage_input', 'input_lineage_id'),
        Index('idx_lineage_timestamp', 'timestamp'),
    )

    def __repr__(self):
        return (
            f"<LineageEvent(event_id={self.event_id}, "
            f"job_id={self.job_id}, stage={self.stage}, "
            f"type={self.event_type})>"
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "event_id": str(self.event_id),
            "job_id": str(self.job_id),
            "event_type": self.event_type,
            "stage": self.stage,
            "input_lineage_id": str(self.input_lineage_id) if self.input_lineage_id else None,
            "output_lineage_id": str(self.output_lineage_id),
            "metadata": self.event_metadata,
            "timestamp": self.timestamp.isoformat()
        }
