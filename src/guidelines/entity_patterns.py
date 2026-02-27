"""
Entity Pattern Learning - Agent 4: Guidelines Manager

Tracks and learns entity-specific mapping patterns to improve extraction accuracy
over time. Uses the EntityPattern ORM model from src.db.models.

Architecture:
    - EntityPatternManager: Pattern tracking and learning operations
    - augment_taxonomy_with_patterns: Integration helper for Stage 3

Future Enhancements:
    - Confidence calibration (ECE < 0.05)
    - Active learning loop
    - Pattern drift detection
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from math import log

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc

from src.core.logging import get_logger
from src.db.models import EntityPattern

logger = get_logger(__name__)


class EntityPatternManager:
    """
    Agent 4: Guidelines Manager - Entity Pattern Learning.

    Manages entity-specific mapping patterns to improve extraction accuracy
    over time. Learns from historical mappings and provides entity-specific
    taxonomy suggestions.

    Uses the EntityPattern ORM model which has:
        - id (UUID, PK)
        - entity_id (UUID, FK to entities.id)
        - original_label (String 500)
        - canonical_name (String 100)
        - confidence (Numeric 5,4)
        - occurrence_count (Integer, default 1)
        - last_seen (DateTime)
        - created_by (String 50, constrained to 'claude'/'user_correction')
        - created_at (DateTime)
    """

    async def record_mapping(
        self,
        session: AsyncSession,
        entity_id: str,
        original_label: str,
        canonical_name: str,
        confidence: float,
        created_by: str = "claude",
    ) -> EntityPattern:
        """
        Record a mapping pattern for an entity.

        If the pattern already exists, increment occurrence_count and update
        confidence using Bayesian updating.

        Args:
            session: Async database session
            entity_id: UUID of the entity (company)
            original_label: Original label from financial statement
            canonical_name: Mapped canonical taxonomy name
            confidence: Confidence score (0-1) from Claude
            created_by: Source of mapping ('claude' or 'user_correction')

        Returns:
            The created or updated EntityPattern
        """
        logger.debug(
            f"Recording pattern: entity={entity_id}, "
            f"'{original_label}' -> '{canonical_name}', confidence={confidence:.4f}"
        )

        # Check if pattern exists
        stmt = select(EntityPattern).where(
            and_(
                EntityPattern.entity_id == entity_id,
                EntityPattern.original_label == original_label,
                EntityPattern.canonical_name == canonical_name,
            )
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if existing:
            # Bayesian confidence update
            old_conf = float(existing.confidence)
            freq = existing.occurrence_count
            updated_confidence = (old_conf * freq + confidence) / (freq + 1)

            existing.confidence = Decimal(str(round(updated_confidence, 4)))
            existing.occurrence_count = freq + 1
            existing.last_seen = now

            logger.info(
                f"Updated pattern: occurrence_count={existing.occurrence_count}, "
                f"confidence={updated_confidence:.4f}"
            )
            await session.flush()
            return existing
        else:
            # Create new pattern
            pattern = EntityPattern(
                entity_id=entity_id,
                original_label=original_label,
                canonical_name=canonical_name,
                confidence=Decimal(str(round(confidence, 4))),
                occurrence_count=1,
                last_seen=now,
                created_by=created_by,
            )
            session.add(pattern)
            logger.info(f"Created new pattern with confidence={confidence:.4f}")
            await session.flush()
            return pattern

    async def get_entity_patterns(
        self,
        session: AsyncSession,
        entity_id: str,
        min_confidence: float = 0.7,
        min_occurrences: int = 1,
    ) -> List[EntityPattern]:
        """
        Retrieve learned patterns for a specific entity.

        Args:
            session: Async database session
            entity_id: UUID of the entity
            min_confidence: Minimum confidence threshold
            min_occurrences: Minimum occurrence count threshold

        Returns:
            List of EntityPattern objects sorted by confidence descending
        """
        logger.debug(
            f"Fetching patterns: entity={entity_id}, "
            f"min_confidence={min_confidence}, min_occurrences={min_occurrences}"
        )

        stmt = (
            select(EntityPattern)
            .where(
                and_(
                    EntityPattern.entity_id == entity_id,
                    EntityPattern.confidence >= Decimal(str(min_confidence)),
                    EntityPattern.occurrence_count >= min_occurrences,
                )
            )
            .order_by(desc(EntityPattern.confidence))
        )
        result = await session.execute(stmt)
        patterns = list(result.scalars().all())

        logger.info(f"Retrieved {len(patterns)} patterns for entity {entity_id}")
        return patterns

    async def get_pattern_suggestions(
        self,
        session: AsyncSession,
        entity_id: str,
        original_label: str,
    ) -> List[Dict[str, Any]]:
        """
        Get canonical name suggestions for a label based on entity history.

        Returns suggestions ranked by a relevance score combining confidence
        and occurrence frequency.

        Args:
            session: Async database session
            entity_id: UUID of the entity
            original_label: Label to find suggestions for

        Returns:
            List of suggestions with canonical_name, confidence, occurrence_count, score
        """
        logger.debug(f"Getting suggestions: entity={entity_id}, label='{original_label}'")

        # Exact match lookup
        stmt = (
            select(EntityPattern)
            .where(
                and_(
                    EntityPattern.entity_id == entity_id,
                    EntityPattern.original_label == original_label,
                )
            )
            .order_by(desc(EntityPattern.confidence))
        )
        result = await session.execute(stmt)
        patterns = list(result.scalars().all())

        suggestions = []
        for pattern in patterns:
            conf = float(pattern.confidence)
            freq = pattern.occurrence_count
            relevance_score = conf * log(freq + 1)
            suggestions.append({
                "canonical_name": pattern.canonical_name,
                "confidence": conf,
                "occurrence_count": freq,
                "score": round(relevance_score, 4),
                "created_by": pattern.created_by,
            })

        suggestions.sort(key=lambda x: x["score"], reverse=True)
        return suggestions[:5]

    async def detect_pattern_drift(
        self,
        session: AsyncSession,
        entity_id: str,
        lookback_days: int = 90,
    ) -> List[Dict[str, Any]]:
        """
        Detect pattern drift - when an entity changes terminology.

        Identifies labels that have multiple canonical name mappings with
        recent activity, suggesting a terminology change.

        Args:
            session: Async database session
            entity_id: UUID of the entity
            lookback_days: Days to look back for drift detection

        Returns:
            List of drift alerts with conflicting mappings
        """
        logger.debug(f"Detecting drift: entity={entity_id}, lookback={lookback_days}d")

        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        # Find labels with multiple canonical names where at least one was seen recently
        stmt = (
            select(EntityPattern)
            .where(
                and_(
                    EntityPattern.entity_id == entity_id,
                    EntityPattern.last_seen >= cutoff,
                )
            )
            .order_by(EntityPattern.original_label, desc(EntityPattern.last_seen))
        )
        result = await session.execute(stmt)
        recent_patterns = list(result.scalars().all())

        # Group by original_label
        by_label: Dict[str, List[EntityPattern]] = {}
        for p in recent_patterns:
            by_label.setdefault(p.original_label, []).append(p)

        drift_alerts = []
        for label, patterns in by_label.items():
            if len(patterns) > 1:
                # Multiple canonical names for same label = potential drift
                drift_alerts.append({
                    "original_label": label,
                    "mappings": [
                        {
                            "canonical_name": p.canonical_name,
                            "confidence": float(p.confidence),
                            "occurrence_count": p.occurrence_count,
                            "last_seen": p.last_seen.isoformat() if p.last_seen else None,
                        }
                        for p in patterns
                    ],
                })

        logger.info(f"Found {len(drift_alerts)} potential drift alerts")
        return drift_alerts

    async def get_pattern_statistics(
        self,
        session: AsyncSession,
        entity_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get statistics about pattern learning.

        Args:
            session: Async database session
            entity_id: Optional specific entity (if None, returns global stats)

        Returns:
            Dictionary with pattern statistics
        """
        logger.debug(f"Calculating statistics: entity={entity_id or 'global'}")

        base_filter = []
        if entity_id:
            base_filter.append(EntityPattern.entity_id == entity_id)

        # Total patterns
        total_stmt = select(func.count(EntityPattern.id)).where(*base_filter)
        total = (await session.execute(total_stmt)).scalar() or 0

        if total == 0:
            return {
                "total_patterns": 0,
                "unique_labels": 0,
                "avg_confidence": 0.0,
                "high_confidence_patterns": 0,
                "low_confidence_patterns": 0,
                "avg_occurrence_count": 0.0,
            }

        # Unique labels
        labels_stmt = select(
            func.count(func.distinct(EntityPattern.original_label))
        ).where(*base_filter)
        unique_labels = (await session.execute(labels_stmt)).scalar() or 0

        # Average confidence
        avg_conf_stmt = select(
            func.avg(EntityPattern.confidence)
        ).where(*base_filter)
        avg_conf = float((await session.execute(avg_conf_stmt)).scalar() or 0)

        # High confidence (>= 0.9)
        high_stmt = select(func.count(EntityPattern.id)).where(
            *base_filter, EntityPattern.confidence >= Decimal("0.9")
        )
        high_conf = (await session.execute(high_stmt)).scalar() or 0

        # Low confidence (< 0.7)
        low_stmt = select(func.count(EntityPattern.id)).where(
            *base_filter, EntityPattern.confidence < Decimal("0.7")
        )
        low_conf = (await session.execute(low_stmt)).scalar() or 0

        # Average occurrence count
        avg_freq_stmt = select(
            func.avg(EntityPattern.occurrence_count)
        ).where(*base_filter)
        avg_freq = float((await session.execute(avg_freq_stmt)).scalar() or 0)

        return {
            "total_patterns": total,
            "unique_labels": unique_labels,
            "avg_confidence": round(avg_conf, 4),
            "high_confidence_patterns": high_conf,
            "low_confidence_patterns": low_conf,
            "avg_occurrence_count": round(avg_freq, 2),
        }


async def augment_taxonomy_with_patterns(
    session: AsyncSession,
    entity_id: str,
    base_taxonomy: str,
    min_confidence: float = 0.8,
) -> str:
    """
    Augment base taxonomy with entity-specific patterns for Stage 3 mapping.

    Takes the standard taxonomy and appends entity-specific hints based on
    learned patterns. This personalizes the extraction for each company.

    Args:
        session: Async database session
        entity_id: UUID of the entity
        base_taxonomy: Base taxonomy text (from TaxonomyManager.format_for_prompt)
        min_confidence: Minimum confidence for patterns to include

    Returns:
        Augmented taxonomy text with entity-specific hints appended
    """
    logger.debug(f"Augmenting taxonomy with patterns for entity={entity_id}")

    manager = EntityPatternManager()
    patterns = await manager.get_entity_patterns(
        session=session,
        entity_id=entity_id,
        min_confidence=min_confidence,
    )

    if not patterns:
        logger.info("No high-confidence patterns found, returning base taxonomy")
        return base_taxonomy

    # Format patterns as hints
    hints = ["\nENTITY-SPECIFIC PATTERNS (high-confidence historical mappings):"]
    for p in patterns[:20]:  # Limit to top 20 to control prompt size
        hints.append(
            f"- '{p.original_label}' -> '{p.canonical_name}' "
            f"({float(p.confidence):.0%} confidence, seen {p.occurrence_count}x)"
        )

    augmented = base_taxonomy + "\n".join(hints)
    logger.info(f"Augmented taxonomy with {len(patterns)} entity patterns")
    return augmented
