"""
Query helpers for common database patterns.

Provides high-level database operations for frequently used queries,
batch operations, and complex joins.
"""

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, func, insert, select, update
from sqlalchemy.orm import Session, joinedload

from src.core.logging import database_logger as logger
from src.db.models import (
    AuditLog,
    Entity,
    EntityPattern,
    ExtractionJob,
    JobStatusEnum,
    LineageEvent,
)

# ============================================================================
# ENTITY QUERIES
# ============================================================================


def get_entity_with_files(db: Session, entity_id: UUID) -> Optional[Entity]:
    """
    Get entity with all related files eagerly loaded.

    Args:
        db: Database session
        entity_id: UUID of the entity

    Returns:
        Entity with files loaded, or None if not found
    """
    result = db.execute(
        select(Entity).options(joinedload(Entity.entity_patterns)).where(Entity.id == entity_id)
    )
    return result.unique().scalar_one_or_none()


def get_or_create_entity(db: Session, name: str, industry: Optional[str] = None) -> Entity:
    """
    Get existing entity by name or create new one.

    Args:
        db: Database session
        name: Entity name
        industry: Industry classification

    Returns:
        Existing or newly created Entity
    """
    result = db.execute(select(Entity).where(Entity.name == name))
    entity = result.scalar_one_or_none()

    if entity:
        logger.debug(f"Found existing entity: {entity.id}")
        return entity

    entity = Entity(name=name, industry=industry)
    db.add(entity)
    db.commit()
    db.refresh(entity)
    logger.info(f"Created new entity: {entity.id}, name={name}")
    return entity


# ============================================================================
# JOB QUERIES
# ============================================================================


def get_job_with_lineage(db: Session, job_id: UUID) -> Optional[ExtractionJob]:
    """
    Get extraction job with all lineage events eagerly loaded.

    Args:
        db: Database session
        job_id: UUID of the job

    Returns:
        ExtractionJob with lineage events, or None if not found
    """
    result = db.execute(
        select(ExtractionJob)
        .options(joinedload(ExtractionJob.lineage_events))
        .where(ExtractionJob.job_id == job_id)
    )
    return result.unique().scalar_one_or_none()


def get_jobs_by_status(db: Session, status: JobStatusEnum, limit: int = 50) -> List[ExtractionJob]:
    """
    Get extraction jobs filtered by status.

    Args:
        db: Database session
        status: Job status to filter by
        limit: Maximum number of results

    Returns:
        List of matching ExtractionJob records
    """
    result = db.execute(
        select(ExtractionJob)
        .where(ExtractionJob.status == status)
        .order_by(ExtractionJob.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


def get_recent_jobs(db: Session, limit: int = 20) -> List[ExtractionJob]:
    """
    Get most recent extraction jobs.

    Args:
        db: Database session
        limit: Maximum number of results

    Returns:
        List of recent ExtractionJob records
    """
    result = db.execute(
        select(ExtractionJob).order_by(ExtractionJob.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


# ============================================================================
# LINEAGE QUERIES
# ============================================================================


def get_lineage_chain(db: Session, job_id: UUID) -> List[LineageEvent]:
    """
    Get complete lineage chain for a job, ordered by timestamp.

    Args:
        db: Database session
        job_id: UUID of the job

    Returns:
        List of lineage events in chronological order
    """
    result = db.execute(
        select(LineageEvent).where(LineageEvent.job_id == job_id).order_by(LineageEvent.timestamp)
    )
    return list(result.scalars().all())


def validate_lineage_completeness(
    db: Session, job_id: UUID, required_stages: Optional[List[str]] = None
) -> bool:
    """
    Validate that all required lineage stages are present for a job.

    Args:
        db: Database session
        job_id: UUID of the job
        required_stages: List of required stage names (default: parsing, triage, mapping)

    Returns:
        True if all stages present, False otherwise
    """
    if required_stages is None:
        required_stages = ["parsing", "triage", "mapping"]

    events = get_lineage_chain(db, job_id)
    present_stages = {event.stage_name for event in events}

    missing = set(required_stages) - present_stages
    if missing:
        logger.warning(f"Lineage incomplete for job {job_id}: missing stages {missing}")
        return False

    return True


# ============================================================================
# PATTERN QUERIES
# ============================================================================


def get_patterns_by_confidence(
    db: Session,
    entity_id: UUID,
    min_confidence: Decimal = Decimal("0.8"),
) -> List[EntityPattern]:
    """
    Get high-confidence patterns for an entity.

    Args:
        db: Database session
        entity_id: UUID of the entity
        min_confidence: Minimum confidence threshold (default 0.8)

    Returns:
        List of high-confidence EntityPattern records
    """
    result = db.execute(
        select(EntityPattern)
        .where(
            and_(
                EntityPattern.entity_id == entity_id,
                EntityPattern.confidence >= min_confidence,
            )
        )
        .order_by(EntityPattern.confidence.desc())
    )
    return list(result.scalars().all())


def find_pattern_match(
    db: Session,
    original_label: str,
    entity_id: Optional[UUID] = None,
) -> Optional[EntityPattern]:
    """
    Find best matching pattern for a label, optionally scoped to an entity.

    Args:
        db: Database session
        original_label: The label to find a pattern for
        entity_id: Optional entity scope for entity-specific patterns

    Returns:
        Best matching pattern (highest confidence), or None
    """
    conditions = [EntityPattern.original_label == original_label]
    if entity_id:
        conditions.append(EntityPattern.entity_id == entity_id)

    result = db.execute(
        select(EntityPattern)
        .where(and_(*conditions))
        .order_by(EntityPattern.confidence.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ============================================================================
# BATCH OPERATIONS
# ============================================================================


def bulk_create_lineage_events(db: Session, events: List[dict]) -> None:
    """
    Bulk insert lineage events for better performance.

    Args:
        db: Database session
        events: List of dicts with lineage event data

    Example:
        events = [
            {"job_id": uuid, "stage_name": "parsing", "data": {...}},
            {"job_id": uuid, "stage_name": "triage", "data": {...}},
        ]
        bulk_create_lineage_events(db, events)
    """
    if not events:
        return

    stmt = insert(LineageEvent).values(events)
    db.execute(stmt)
    db.commit()
    logger.info(f"Bulk inserted {len(events)} lineage events")


def bulk_update_pattern_confidence(
    db: Session,
    updates: List[dict],
) -> int:
    """
    Bulk update pattern confidence scores.

    Args:
        db: Database session
        updates: List of dicts with {pattern_id, new_confidence}

    Returns:
        Number of rows updated
    """
    count = 0
    for update_data in updates:
        result = db.execute(
            update(EntityPattern)
            .where(EntityPattern.id == update_data["pattern_id"])
            .values(confidence=update_data["new_confidence"])
        )
        count += result.rowcount  # type: ignore[attr-defined]

    db.commit()
    logger.info(f"Bulk updated {count} pattern confidence scores")
    return count


# ============================================================================
# AUDIT QUERIES
# ============================================================================


def get_audit_log(
    db: Session,
    resource_type: Optional[str] = None,
    resource_id: Optional[UUID] = None,
    action: Optional[str] = None,
    limit: int = 100,
) -> List[AuditLog]:
    """
    Query audit logs with optional filters.

    Args:
        db: Database session
        resource_type: Filter by resource type (e.g., "file", "job")
        resource_id: Filter by specific resource
        action: Filter by action (e.g., "upload", "view")
        limit: Maximum number of results

    Returns:
        List of matching AuditLog records
    """
    stmt = select(AuditLog)

    conditions = []
    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)
    if resource_id:
        conditions.append(AuditLog.resource_id == resource_id)
    if action:
        conditions.append(AuditLog.action == action)

    if conditions:
        stmt = stmt.where(and_(*conditions))

    stmt = stmt.order_by(AuditLog.timestamp.desc()).limit(limit)
    result = db.execute(stmt)
    return list(result.scalars().all())


# ============================================================================
# STATISTICS
# ============================================================================


def get_job_statistics(db: Session) -> dict:
    """
    Get job processing statistics.

    Returns:
        Dict with counts by status and total jobs
    """
    stats = {}
    for status in JobStatusEnum:
        result = db.execute(
            select(func.count(ExtractionJob.job_id)).where(ExtractionJob.status == status)
        )
        stats[status.value] = result.scalar() or 0

    stats["total"] = sum(stats.values())
    return stats
