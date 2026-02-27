"""
Entity Pattern Learning - Agent 4: Guidelines Manager

Tracks and learns entity-specific mapping patterns to improve extraction accuracy
over time. This module provides the foundation for intelligent learning where the
system remembers how specific companies map their financial statements.

Architecture:
    - EntityPattern: Database model (stub for Agent 1 implementation)
    - EntityPatternManager: Pattern tracking and learning operations
    - Integration points with Stage 3 mapping

Future Enhancements (from TAXONOMY_ROADMAP_TO_EXCELLENCE.md):
    - Confidence calibration (ECE < 0.05)
    - Active learning loop
    - Pattern drift detection
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from dataclasses import dataclass

from src.core.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# STUB: EntityPattern Model
# ============================================================================
# NOTE: This is a STUB for Agent 1 to implement in src/db/models.py
#
# Recommended schema for PostgreSQL:
#
# CREATE TABLE entity_patterns (
#     id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
#     entity_id UUID NOT NULL,  -- References entities table
#     original_label VARCHAR(500) NOT NULL,
#     canonical_name VARCHAR(100) NOT NULL,  -- References taxonomy.canonical_name
#     confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
#     frequency INT DEFAULT 1,
#     last_seen TIMESTAMPTZ DEFAULT NOW(),
#     created_at TIMESTAMPTZ DEFAULT NOW(),
#     updated_at TIMESTAMPTZ DEFAULT NOW(),
#     metadata JSONB,  -- Stores additional context (sheet_name, row_number, etc.)
#
#     UNIQUE(entity_id, original_label, canonical_name),
#     FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
#     FOREIGN KEY (canonical_name) REFERENCES taxonomy(canonical_name) ON DELETE CASCADE
# );
#
# CREATE INDEX idx_entity_patterns_entity ON entity_patterns(entity_id);
# CREATE INDEX idx_entity_patterns_label ON entity_patterns(original_label);
# CREATE INDEX idx_entity_patterns_canonical ON entity_patterns(canonical_name);
# CREATE INDEX idx_entity_patterns_confidence ON entity_patterns(confidence);
#
# ============================================================================


@dataclass
class EntityPattern:
    """
    STUB: Entity-specific mapping pattern.

    Represents a learned pattern where a specific entity (company) uses
    a particular label to mean a canonical taxonomy item.

    This is a STUB. Agent 1 should implement this as a SQLAlchemy model
    in src/db/models.py following the schema above.

    Example:
        Company "Acme Corp" always uses "Net Sales" to mean "revenue"
        → Pattern: entity_id=acme_uuid, original_label="Net Sales",
                   canonical_name="revenue", confidence=0.98, frequency=24
    """
    id: str
    entity_id: str
    original_label: str
    canonical_name: str
    confidence: float
    frequency: int
    last_seen: datetime
    created_at: datetime
    updated_at: datetime
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Validate pattern data."""
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"Confidence must be between 0 and 1, got {self.confidence}")
        if self.frequency < 1:
            raise ValueError(f"Frequency must be >= 1, got {self.frequency}")


class EntityPatternManager:
    """
    Agent 4: Guidelines Manager - Entity Pattern Learning.

    Manages entity-specific mapping patterns to improve extraction accuracy
    over time. Learns from historical mappings and provides entity-specific
    taxonomy suggestions.

    Key Features:
        - Track entity-specific label → canonical mappings
        - Learn from extraction history
        - Provide confidence-weighted suggestions
        - Detect pattern changes (drift)
        - Support active learning (low-confidence flagging)

    Integration Points:
        - Stage 3 Mapping: Inject entity patterns into taxonomy prompt
        - Agent 5 Validator: Use patterns for validation
        - Agent 6 Lineage: Track pattern provenance
    """

    async def record_mapping(
        self,
        session: AsyncSession,
        entity_id: str,
        original_label: str,
        canonical_name: str,
        confidence: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record a mapping pattern for an entity.

        If the pattern already exists, increment frequency and update confidence.
        Uses Bayesian updating to combine historical and new confidence.

        Args:
            session: Async database session
            entity_id: UUID of the entity (company)
            original_label: Original label from financial statement
            canonical_name: Mapped canonical taxonomy name
            confidence: Confidence score (0-1) from Claude
            metadata: Optional context (sheet_name, row_number, etc.)

        Example:
            await pattern_manager.record_mapping(
                session=db,
                entity_id="acme-uuid",
                original_label="Net Sales",
                canonical_name="revenue",
                confidence=0.95,
                metadata={"sheet_name": "Income Statement", "row": 5}
            )

        Future Enhancement:
            Implement Bayesian confidence updating:
            new_confidence = (old_conf * frequency + new_conf) / (frequency + 1)
        """
        logger.debug(
            f"Recording pattern: entity={entity_id}, "
            f"label='{original_label}' → canonical='{canonical_name}', "
            f"confidence={confidence:.2f}"
        )

        # NOTE: This is a STUB implementation
        # Agent 1 should implement database operations using SQLAlchemy ORM

        # Pseudo-code for future implementation:
        #
        # # Check if pattern exists
        # stmt = select(EntityPattern).where(
        #     and_(
        #         EntityPattern.entity_id == entity_id,
        #         EntityPattern.original_label == original_label,
        #         EntityPattern.canonical_name == canonical_name
        #     )
        # )
        # result = await session.execute(stmt)
        # existing_pattern = result.scalar_one_or_none()
        #
        # if existing_pattern:
        #     # Update existing pattern (Bayesian update)
        #     updated_confidence = (
        #         (existing_pattern.confidence * existing_pattern.frequency + confidence)
        #         / (existing_pattern.frequency + 1)
        #     )
        #     existing_pattern.confidence = updated_confidence
        #     existing_pattern.frequency += 1
        #     existing_pattern.last_seen = datetime.utcnow()
        #     existing_pattern.updated_at = datetime.utcnow()
        #     logger.info(
        #         f"Updated pattern frequency={existing_pattern.frequency}, "
        #         f"confidence={updated_confidence:.3f}"
        #     )
        # else:
        #     # Create new pattern
        #     new_pattern = EntityPattern(
        #         entity_id=entity_id,
        #         original_label=original_label,
        #         canonical_name=canonical_name,
        #         confidence=confidence,
        #         frequency=1,
        #         metadata=metadata or {}
        #     )
        #     session.add(new_pattern)
        #     logger.info(f"Created new pattern with confidence={confidence:.3f}")
        #
        # await session.commit()

        logger.warning("EntityPatternManager.record_mapping is a STUB - awaiting Agent 1 implementation")

    async def get_entity_patterns(
        self,
        session: AsyncSession,
        entity_id: str,
        min_confidence: float = 0.7,
        min_frequency: int = 1
    ) -> List[EntityPattern]:
        """
        Retrieve learned patterns for a specific entity.

        Returns patterns sorted by confidence (descending) for use in
        entity-specific taxonomy augmentation.

        Args:
            session: Async database session
            entity_id: UUID of the entity
            min_confidence: Minimum confidence threshold (default 0.7)
            min_frequency: Minimum frequency threshold (default 1)

        Returns:
            List of EntityPattern objects sorted by confidence descending

        Example:
            patterns = await pattern_manager.get_entity_patterns(
                session=db,
                entity_id="acme-uuid",
                min_confidence=0.8
            )
            for pattern in patterns:
                print(f"{pattern.original_label} → {pattern.canonical_name} "
                      f"(conf={pattern.confidence:.2f}, freq={pattern.frequency})")
        """
        logger.debug(
            f"Fetching patterns for entity={entity_id}, "
            f"min_confidence={min_confidence}, min_frequency={min_frequency}"
        )

        # NOTE: This is a STUB implementation
        # Agent 1 should implement database query

        # Pseudo-code for future implementation:
        #
        # stmt = (
        #     select(EntityPattern)
        #     .where(
        #         and_(
        #             EntityPattern.entity_id == entity_id,
        #             EntityPattern.confidence >= min_confidence,
        #             EntityPattern.frequency >= min_frequency
        #         )
        #     )
        #     .order_by(desc(EntityPattern.confidence))
        # )
        # result = await session.execute(stmt)
        # patterns = list(result.scalars().all())
        #
        # logger.info(f"Retrieved {len(patterns)} patterns for entity {entity_id}")
        # return patterns

        logger.warning("EntityPatternManager.get_entity_patterns is a STUB - returning empty list")
        return []

    async def get_pattern_suggestions(
        self,
        session: AsyncSession,
        entity_id: str,
        original_label: str
    ) -> List[Dict[str, Any]]:
        """
        Get canonical name suggestions for a label based on entity history.

        Returns top suggestions ranked by confidence and frequency for use
        in Stage 3 mapping as hints.

        Args:
            session: Async database session
            entity_id: UUID of the entity
            original_label: Label to find suggestions for

        Returns:
            List of suggestions with canonical_name, confidence, frequency
            Sorted by confidence * log(frequency) (relevance score)

        Example:
            suggestions = await pattern_manager.get_pattern_suggestions(
                session=db,
                entity_id="acme-uuid",
                original_label="Net Sales"
            )
            # Returns: [
            #   {"canonical_name": "revenue", "confidence": 0.95, "frequency": 24, "score": 2.95},
            #   {"canonical_name": "product_revenue", "confidence": 0.65, "frequency": 2, "score": 0.45}
            # ]

        Integration with Stage 3:
            Use suggestions as hints in Claude prompt:
            "For this entity, 'Net Sales' has historically mapped to 'revenue'
            (95% confidence, 24 times seen). Consider this pattern."
        """
        logger.debug(f"Getting suggestions for entity={entity_id}, label='{original_label}'")

        # NOTE: This is a STUB implementation
        # Agent 1 should implement fuzzy matching and scoring

        # Pseudo-code for future implementation:
        #
        # # Exact match
        # stmt_exact = (
        #     select(EntityPattern)
        #     .where(
        #         and_(
        #             EntityPattern.entity_id == entity_id,
        #             EntityPattern.original_label == original_label
        #         )
        #     )
        # )
        #
        # # Fuzzy match (using PostgreSQL similarity)
        # stmt_fuzzy = (
        #     select(EntityPattern)
        #     .where(
        #         and_(
        #             EntityPattern.entity_id == entity_id,
        #             func.similarity(EntityPattern.original_label, original_label) > 0.6
        #         )
        #     )
        # )
        #
        # # Combine results and score
        # suggestions = []
        # for pattern in patterns:
        #     relevance_score = pattern.confidence * log(pattern.frequency + 1)
        #     suggestions.append({
        #         "canonical_name": pattern.canonical_name,
        #         "confidence": pattern.confidence,
        #         "frequency": pattern.frequency,
        #         "score": relevance_score
        #     })
        #
        # # Sort by relevance score descending
        # suggestions.sort(key=lambda x: x["score"], reverse=True)
        # return suggestions[:5]  # Top 5 suggestions

        logger.warning("EntityPatternManager.get_pattern_suggestions is a STUB - returning empty list")
        return []

    async def detect_pattern_drift(
        self,
        session: AsyncSession,
        entity_id: str,
        lookback_days: int = 90
    ) -> List[Dict[str, Any]]:
        """
        Detect pattern drift - when an entity changes terminology.

        Identifies cases where a label that previously mapped to one canonical
        name now maps to a different one (terminology change).

        Args:
            session: Async database session
            entity_id: UUID of the entity
            lookback_days: Days to look back for drift detection

        Returns:
            List of drift alerts with old/new mappings and confidence delta

        Example:
            drift_alerts = await pattern_manager.detect_pattern_drift(
                session=db,
                entity_id="acme-uuid",
                lookback_days=90
            )
            # Returns: [
            #   {
            #       "original_label": "Operating Profit",
            #       "old_canonical": "ebit",
            #       "new_canonical": "ebitda",
            #       "confidence_delta": 0.25,
            #       "last_old_seen": "2025-11-01",
            #       "first_new_seen": "2026-01-15"
            #   }
            # ]

        Use Case:
            Alert user when company changes terminology to verify mapping.
            Supports regulatory changes (e.g., IFRS → GAAP transition).
        """
        logger.debug(f"Detecting pattern drift for entity={entity_id}, lookback={lookback_days} days")

        # NOTE: This is a STUB implementation
        # Agent 1 should implement temporal analysis

        logger.warning("EntityPatternManager.detect_pattern_drift is a STUB - returning empty list")
        return []

    async def get_pattern_statistics(
        self,
        session: AsyncSession,
        entity_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get statistics about pattern learning.

        Provides insights into pattern coverage, confidence distribution,
        and learning progress for monitoring.

        Args:
            session: Async database session
            entity_id: Optional specific entity (if None, returns global stats)

        Returns:
            Dictionary with pattern statistics

        Example:
            stats = await pattern_manager.get_pattern_statistics(
                session=db,
                entity_id="acme-uuid"
            )
            # Returns: {
            #     "total_patterns": 145,
            #     "unique_labels": 89,
            #     "avg_confidence": 0.87,
            #     "high_confidence_patterns": 112,  # confidence >= 0.9
            #     "low_confidence_patterns": 8,     # confidence < 0.7
            #     "avg_frequency": 3.2,
            #     "coverage_pct": 0.76  # % of taxonomy covered
            # }
        """
        logger.debug(f"Calculating pattern statistics for entity={entity_id or 'global'}")

        # NOTE: This is a STUB implementation
        # Agent 1 should implement aggregation queries

        logger.warning("EntityPatternManager.get_pattern_statistics is a STUB - returning empty dict")
        return {
            "total_patterns": 0,
            "unique_labels": 0,
            "avg_confidence": 0.0,
            "high_confidence_patterns": 0,
            "low_confidence_patterns": 0,
            "avg_frequency": 0.0,
            "coverage_pct": 0.0
        }


# ============================================================================
# Integration Helper Functions
# ============================================================================

async def augment_taxonomy_with_patterns(
    session: AsyncSession,
    entity_id: str,
    base_taxonomy: str,
    min_confidence: float = 0.8
) -> str:
    """
    Augment base taxonomy with entity-specific patterns for Stage 3 mapping.

    Takes the standard taxonomy and adds entity-specific hints based on
    learned patterns. This personalizes the extraction for each company.

    Args:
        session: Async database session
        entity_id: UUID of the entity
        base_taxonomy: Base taxonomy text (from load_taxonomy_for_stage3)
        min_confidence: Minimum confidence for patterns to include

    Returns:
        Augmented taxonomy text with entity-specific hints

    Example:
        from src.guidelines.taxonomy import load_taxonomy_for_stage3
        from src.guidelines.entity_patterns import augment_taxonomy_with_patterns

        async with get_db_context() as db:
            # Get base taxonomy
            base_tax = await load_taxonomy_for_stage3(db)

            # Augment with entity patterns
            augmented_tax = await augment_taxonomy_with_patterns(
                session=db,
                entity_id="acme-uuid",
                base_taxonomy=base_tax,
                min_confidence=0.8
            )

            # Use in Stage 3 prompt
            prompt = f'''
            CANONICAL TAXONOMY:
            {augmented_tax}

            ENTITY-SPECIFIC HINTS:
            This company typically uses "Net Sales" for revenue (95% confidence).
            '''

    Future Enhancement (Week 4):
        Implement full augmentation with pattern hints injected into prompt.
    """
    logger.debug(f"Augmenting taxonomy with patterns for entity={entity_id}")

    # NOTE: This is a STUB implementation
    # Future: Inject high-confidence patterns as hints

    pattern_manager = EntityPatternManager()
    patterns = await pattern_manager.get_entity_patterns(
        session=session,
        entity_id=entity_id,
        min_confidence=min_confidence
    )

    if not patterns:
        logger.info("No high-confidence patterns found, returning base taxonomy")
        return base_taxonomy

    # Future: Format patterns as hints and append to taxonomy
    # Example augmentation:
    # augmented = base_taxonomy + "\n\nENTITY-SPECIFIC PATTERNS:\n"
    # for pattern in patterns:
    #     augmented += f"- '{pattern.original_label}' → '{pattern.canonical_name}' "
    #     augmented += f"({pattern.confidence:.0%} confidence, seen {pattern.frequency}x)\n"

    logger.warning("augment_taxonomy_with_patterns is a STUB - returning base taxonomy")
    return base_taxonomy
