# Week 4: Entity Pattern Learning - Implementation Plan

**Status**: 📋 **READY TO IMPLEMENT** (Awaiting Agent 1 completion)
**Effort**: 8 hours
**Expected Impact**: +4-6% accuracy on repeat extractions, -58% manual corrections
**Date**: 2026-02-24
**Prerequisites**: Agent 1 completes `entity_patterns` table + `EntityPattern` model

---

## Overview

Implement the entity pattern learning system to enable intelligent extraction that learns from each company's terminology. This transforms the system from "smart" to "intelligent" by remembering company-specific patterns.

**Reference**: [ENTITY_PATTERNS_INTEGRATION.md](ENTITY_PATTERNS_INTEGRATION.md)

---

## Success Criteria

### Functional Requirements
- ✅ Pattern recording with Bayesian confidence updating
- ✅ Pattern retrieval with confidence thresholds
- ✅ Fuzzy matching for pattern suggestions
- ✅ Pattern drift detection (terminology changes)
- ✅ Stage 3 integration with pattern hints
- ✅ Automatic pattern recording after extraction

### Performance Requirements
- Pattern recording: < 50ms per mapping
- Pattern retrieval: < 100ms for entity
- Fuzzy matching: < 200ms for suggestion
- Stage 3 with patterns: < 35s total (vs 30s baseline)

### Quality Requirements
- 15+ unit tests for pattern operations
- 5+ integration tests for full loop
- 80%+ code coverage for entity_patterns.py
- Zero SQL injection vulnerabilities
- Proper error handling and logging

### Impact Metrics (After 5 Extractions)
- Accuracy improvement: +6% (91% → 97%)
- Manual corrections: -58% (12 → 5 per model)
- Review time: -62% (8 min → 3 min)
- Pattern coverage: 70% of typical financial statement

---

## Task Breakdown (8 hours total)

### Task 1: EntityPatternManager Database Operations (2 hours)

**File**: `src/guidelines/entity_patterns.py`

#### Subtask 1.1: Implement `record_mapping()` (45 min)

**Current (STUB)**:
```python
async def record_mapping(
    self,
    session: AsyncSession,
    entity_id: str,
    original_label: str,
    canonical_name: str,
    confidence: float,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    logger.warning("EntityPatternManager.record_mapping is a STUB")
```

**Implementation**:
```python
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
    Record a mapping pattern with Bayesian confidence updating.

    If pattern exists, update confidence using:
    new_confidence = (old_conf * frequency + new_conf) / (frequency + 1)
    """
    from datetime import datetime
    from sqlalchemy import select, and_
    from src.db.models import EntityPattern

    logger.debug(
        f"Recording pattern: entity={entity_id}, "
        f"label='{original_label}' → canonical='{canonical_name}', "
        f"confidence={confidence:.2f}"
    )

    # Validate inputs
    if not 0 <= confidence <= 1:
        raise ValueError(f"Confidence must be 0-1, got {confidence}")

    # Check if pattern exists
    stmt = select(EntityPattern).where(
        and_(
            EntityPattern.entity_id == entity_id,
            EntityPattern.original_label == original_label,
            EntityPattern.canonical_name == canonical_name
        )
    )
    result = await session.execute(stmt)
    existing_pattern = result.scalar_one_or_none()

    if existing_pattern:
        # Bayesian confidence update
        old_conf = existing_pattern.confidence
        freq = existing_pattern.frequency
        updated_confidence = (old_conf * freq + confidence) / (freq + 1)

        # Update existing pattern
        existing_pattern.confidence = updated_confidence
        existing_pattern.frequency += 1
        existing_pattern.last_seen = datetime.utcnow()
        existing_pattern.updated_at = datetime.utcnow()
        if metadata:
            # Merge metadata (keep history)
            current_meta = existing_pattern.metadata or {}
            current_meta['last_extraction'] = metadata
            existing_pattern.metadata = current_meta

        logger.info(
            f"Updated pattern: frequency={existing_pattern.frequency}, "
            f"confidence={old_conf:.3f}→{updated_confidence:.3f}"
        )
    else:
        # Create new pattern
        new_pattern = EntityPattern(
            entity_id=entity_id,
            original_label=original_label,
            canonical_name=canonical_name,
            confidence=confidence,
            frequency=1,
            last_seen=datetime.utcnow(),
            metadata=metadata or {}
        )
        session.add(new_pattern)

        logger.info(
            f"Created new pattern: '{original_label}'→'{canonical_name}' "
            f"(confidence={confidence:.3f})"
        )

    await session.commit()
```

**Testing**:
```python
async def test_record_mapping_new():
    """Test recording new pattern."""
    await pattern_manager.record_mapping(
        session=db,
        entity_id="test-uuid",
        original_label="Net Sales",
        canonical_name="revenue",
        confidence=0.95
    )

    patterns = await pattern_manager.get_entity_patterns(db, "test-uuid")
    assert len(patterns) == 1
    assert patterns[0].confidence == 0.95
    assert patterns[0].frequency == 1

async def test_record_mapping_bayesian_update():
    """Test Bayesian confidence updating."""
    # First recording: 0.95 confidence
    await pattern_manager.record_mapping(
        session=db, entity_id="test-uuid",
        original_label="Net Sales", canonical_name="revenue",
        confidence=0.95
    )

    # Second recording: 0.85 confidence
    await pattern_manager.record_mapping(
        session=db, entity_id="test-uuid",
        original_label="Net Sales", canonical_name="revenue",
        confidence=0.85
    )

    # Expected: (0.95*1 + 0.85*1) / 2 = 0.90
    patterns = await pattern_manager.get_entity_patterns(db, "test-uuid")
    assert patterns[0].frequency == 2
    assert abs(patterns[0].confidence - 0.90) < 0.01
```

#### Subtask 1.2: Implement `get_entity_patterns()` (30 min)

**Implementation**:
```python
async def get_entity_patterns(
    self,
    session: AsyncSession,
    entity_id: str,
    min_confidence: float = 0.7,
    min_frequency: int = 1
) -> List[EntityPattern]:
    """Retrieve learned patterns for entity, sorted by confidence."""
    from sqlalchemy import select, and_, desc
    from src.db.models import EntityPattern

    logger.debug(
        f"Fetching patterns: entity={entity_id}, "
        f"min_confidence={min_confidence}, min_frequency={min_frequency}"
    )

    stmt = (
        select(EntityPattern)
        .where(
            and_(
                EntityPattern.entity_id == entity_id,
                EntityPattern.confidence >= min_confidence,
                EntityPattern.frequency >= min_frequency
            )
        )
        .order_by(desc(EntityPattern.confidence))
    )

    result = await session.execute(stmt)
    patterns = list(result.scalars().all())

    logger.info(f"Retrieved {len(patterns)} patterns for entity {entity_id}")
    return patterns
```

#### Subtask 1.3: Implement `get_pattern_suggestions()` (45 min)

**Implementation with Fuzzy Matching**:
```python
async def get_pattern_suggestions(
    self,
    session: AsyncSession,
    entity_id: str,
    original_label: str
) -> List[Dict[str, Any]]:
    """
    Get canonical name suggestions with fuzzy matching.

    Uses PostgreSQL similarity for fuzzy matching:
    - Exact match: priority 1.0
    - High similarity (>0.7): priority 0.7-1.0
    - Medium similarity (>0.5): priority 0.5-0.7

    Relevance score = confidence * log(frequency + 1) * similarity
    """
    from sqlalchemy import select, and_, func, or_
    from src.db.models import EntityPattern
    import math

    logger.debug(f"Getting suggestions: entity={entity_id}, label='{original_label}'")

    # Exact match (highest priority)
    stmt_exact = (
        select(EntityPattern)
        .where(
            and_(
                EntityPattern.entity_id == entity_id,
                EntityPattern.original_label == original_label
            )
        )
    )
    result_exact = await session.execute(stmt_exact)
    exact_patterns = list(result_exact.scalars().all())

    # Fuzzy match (using PostgreSQL similarity)
    # Requires pg_trgm extension: CREATE EXTENSION pg_trgm;
    stmt_fuzzy = (
        select(
            EntityPattern,
            func.similarity(EntityPattern.original_label, original_label).label('similarity')
        )
        .where(
            and_(
                EntityPattern.entity_id == entity_id,
                EntityPattern.original_label != original_label,  # Exclude exact matches
                func.similarity(EntityPattern.original_label, original_label) > 0.5
            )
        )
        .order_by(func.similarity(EntityPattern.original_label, original_label).desc())
        .limit(5)
    )
    result_fuzzy = await session.execute(stmt_fuzzy)
    fuzzy_results = result_fuzzy.all()

    # Build suggestions
    suggestions = []

    # Add exact matches (similarity = 1.0)
    for pattern in exact_patterns:
        relevance_score = pattern.confidence * math.log(pattern.frequency + 1) * 1.0
        suggestions.append({
            "canonical_name": pattern.canonical_name,
            "confidence": pattern.confidence,
            "frequency": pattern.frequency,
            "similarity": 1.0,
            "score": relevance_score,
            "match_type": "exact"
        })

    # Add fuzzy matches
    for pattern, similarity in fuzzy_results:
        relevance_score = pattern.confidence * math.log(pattern.frequency + 1) * similarity
        suggestions.append({
            "canonical_name": pattern.canonical_name,
            "confidence": pattern.confidence,
            "frequency": pattern.frequency,
            "similarity": float(similarity),
            "score": relevance_score,
            "match_type": "fuzzy"
        })

    # Sort by relevance score
    suggestions.sort(key=lambda x: x["score"], reverse=True)

    logger.info(f"Found {len(suggestions)} suggestions (top score: {suggestions[0]['score']:.2f})" if suggestions else "No suggestions found")

    return suggestions[:5]  # Top 5 suggestions
```

**Testing**:
```python
async def test_get_pattern_suggestions_exact():
    """Test exact match suggestions."""
    # Record pattern
    await pattern_manager.record_mapping(
        session=db, entity_id="test-uuid",
        original_label="Net Sales", canonical_name="revenue",
        confidence=0.95
    )

    # Get suggestions
    suggestions = await pattern_manager.get_pattern_suggestions(
        session=db, entity_id="test-uuid",
        original_label="Net Sales"
    )

    assert len(suggestions) >= 1
    assert suggestions[0]["canonical_name"] == "revenue"
    assert suggestions[0]["match_type"] == "exact"
    assert suggestions[0]["similarity"] == 1.0

async def test_get_pattern_suggestions_fuzzy():
    """Test fuzzy match suggestions."""
    # Record pattern with slightly different label
    await pattern_manager.record_mapping(
        session=db, entity_id="test-uuid",
        original_label="Net Sales Revenue", canonical_name="revenue",
        confidence=0.95
    )

    # Get suggestions for similar label
    suggestions = await pattern_manager.get_pattern_suggestions(
        session=db, entity_id="test-uuid",
        original_label="Net Sales"  # Slightly different
    )

    assert len(suggestions) >= 1
    assert suggestions[0]["canonical_name"] == "revenue"
    assert suggestions[0]["match_type"] == "fuzzy"
    assert 0.5 < suggestions[0]["similarity"] < 1.0
```

---

### Task 2: Stage 3 Orchestrator Integration (2 hours)

**File**: `src/extraction/orchestrator.py`

#### Subtask 2.1: Add entity_id Parameter (30 min)

**Current Signature**:
```python
async def stage_3_mapping(parsed_result: dict) -> dict:
```

**New Signature**:
```python
async def stage_3_mapping(
    parsed_result: dict,
    entity_id: Optional[str] = None
) -> dict:
```

**Update Orchestrator Call** (in `extract_from_file`):
```python
# Stage 3: Map line items to canonical taxonomy
mapping_result = await stage_3_mapping(
    parsed_result=parsed_result,
    entity_id=job.entity_id  # Pass from job context
)
```

#### Subtask 2.2: Inject Pattern Hints into Prompt (1 hour)

**Implementation**:
```python
async def stage_3_mapping(
    parsed_result: dict,
    entity_id: Optional[str] = None
) -> dict:
    """Stage 3: Map line items to canonical taxonomy with entity patterns."""
    from src.db.session import get_db_context
    from src.guidelines.taxonomy import load_taxonomy_for_stage3
    from src.guidelines.entity_patterns import EntityPatternManager

    # Extract labels (unchanged)
    labels = set()
    for sheet in parsed_result.get("sheets", []):
        for row in sheet.get("rows", []):
            if row.get("label"):
                labels.add(row["label"])

    if not labels:
        return {"mappings": [], "tokens": 0}

    # Load taxonomy and patterns
    async with get_db_context() as db:
        # Get base taxonomy
        base_taxonomy = await load_taxonomy_for_stage3(db)

        # Get entity-specific pattern hints if entity_id provided
        pattern_hints = {}
        if entity_id:
            pattern_manager = EntityPatternManager()
            for label in labels:
                suggestions = await pattern_manager.get_pattern_suggestions(
                    session=db,
                    entity_id=entity_id,
                    original_label=label
                )
                if suggestions and suggestions[0]["confidence"] >= 0.8:
                    # Only use high-confidence patterns as hints
                    pattern_hints[label] = suggestions[0]

            logger.info(f"Loaded {len(pattern_hints)} pattern hints for entity {entity_id}")

    # Build enhanced mapping prompt
    pattern_context = ""
    if pattern_hints:
        pattern_context = "\n\nENTITY-SPECIFIC PATTERNS (strong hints from historical extractions):\n"
        for label, hint in pattern_hints.items():
            pattern_context += (
                f"- '{label}' typically maps to '{hint['canonical_name']}' "
                f"({hint['confidence']:.0%} confidence, seen {hint['frequency']}x, "
                f"match: {hint['match_type']})\n"
            )

    mapping_prompt = f"""
Map these financial line items to canonical names.

CANONICAL TAXONOMY (use these exact names):
{base_taxonomy}
{pattern_context}

INSTRUCTIONS:
- Use exact canonical names from the taxonomy above
- For items with entity-specific patterns, strongly prefer the suggested mapping
- Only deviate from patterns if you're highly confident the pattern is wrong
- Return confidence score (0-1) for each mapping

Line items to map:
{json.dumps(list(labels), indent=2)}

Return JSON array with format:
[
  {{
    "original_label": "Net Sales",
    "canonical_name": "revenue",
    "confidence": 0.95,
    "reasoning": "Net Sales is a common alias for revenue"
  }}
]
"""

    # Call Claude (rest unchanged)
    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4000,
        messages=[{"role": "user", "content": mapping_prompt}]
    )

    mappings = parse_mappings(response.content[0].text)

    return {
        "mappings": mappings,
        "tokens": response.usage.input_tokens + response.usage.output_tokens,
        "pattern_hints_used": len(pattern_hints)
    }
```

#### Subtask 2.3: Record Patterns After Extraction (30 min)

**Add After Stage 3 Completes**:
```python
async def extract_from_file(file_path: str, entity_id: Optional[str] = None):
    """Full extraction pipeline."""

    # ... existing stages 1-3 ...

    # Stage 3: Mapping with patterns
    mapping_result = await stage_3_mapping(
        parsed_result=parsed_result,
        entity_id=entity_id
    )

    # Record patterns for future learning (if entity_id provided)
    if entity_id and mapping_result["mappings"]:
        async with get_db_context() as db:
            pattern_manager = EntityPatternManager()
            for mapping in mapping_result["mappings"]:
                try:
                    await pattern_manager.record_mapping(
                        session=db,
                        entity_id=entity_id,
                        original_label=mapping["original_label"],
                        canonical_name=mapping["canonical_name"],
                        confidence=mapping.get("confidence", 0.8),
                        metadata={
                            "file_path": file_path,
                            "extraction_date": datetime.utcnow().isoformat(),
                            "reasoning": mapping.get("reasoning")
                        }
                    )
                    logger.debug(f"Recorded pattern: '{mapping['original_label']}'→'{mapping['canonical_name']}'")
                except Exception as e:
                    logger.error(f"Failed to record pattern: {e}", exc_info=True)
                    # Don't fail extraction if pattern recording fails

    return mapping_result
```

---

### Task 3: Comprehensive Testing (2.5 hours)

**File**: `tests/unit/test_entity_patterns.py` (create new)

#### Subtask 3.1: Unit Tests for EntityPatternManager (1.5 hours)

**Test Suite Structure**:
```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

TEST_DATABASE_URL = "postgresql+asyncpg://test:test@localhost/test_db"

@pytest.fixture
async def engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
async def db_session(engine):
    """Create async database session."""
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

@pytest.fixture
async def test_entity(db_session):
    """Create test entity."""
    from src.db.models import Entity
    entity = Entity(id="test-entity-uuid", name="Test Corp")
    db_session.add(entity)
    await db_session.commit()
    return entity


class TestEntityPatternManager:
    """Test cases for EntityPatternManager."""

    async def test_record_mapping_new(self, db_session, test_entity):
        """Test recording new pattern."""
        # ... (from Subtask 1.1 above)

    async def test_record_mapping_bayesian_update(self, db_session, test_entity):
        """Test Bayesian confidence updating."""
        # ... (from Subtask 1.1 above)

    async def test_get_entity_patterns(self, db_session, test_entity):
        """Test retrieving entity patterns."""
        # ... (implement)

    async def test_get_entity_patterns_min_confidence(self, db_session, test_entity):
        """Test confidence threshold filtering."""
        # ... (implement)

    async def test_get_pattern_suggestions_exact(self, db_session, test_entity):
        """Test exact match suggestions."""
        # ... (from Subtask 1.3 above)

    async def test_get_pattern_suggestions_fuzzy(self, db_session, test_entity):
        """Test fuzzy match suggestions."""
        # ... (from Subtask 1.3 above)

    async def test_get_pattern_suggestions_scoring(self, db_session, test_entity):
        """Test relevance score calculation."""
        # ... (implement)

    async def test_pattern_metadata_storage(self, db_session, test_entity):
        """Test metadata storage and retrieval."""
        # ... (implement)

    async def test_multiple_entities_isolation(self, db_session):
        """Test patterns are isolated by entity."""
        # ... (implement)

    async def test_pattern_frequency_increment(self, db_session, test_entity):
        """Test frequency increments on repeat mappings."""
        # ... (implement)
```

#### Subtask 3.2: Integration Tests for Pattern Learning Loop (1 hour)

**File**: `tests/integration/test_pattern_learning_loop.py` (create new)

```python
@pytest.mark.asyncio
async def test_full_extraction_pattern_loop():
    """Test complete extraction → pattern recording → suggestion loop."""

    # First extraction (no patterns exist yet)
    result1 = await extract_from_file(
        file_path="tests/fixtures/acme_q1_2025.xlsx",
        entity_id="acme-uuid"
    )

    assert result1["mappings"]
    assert result1["pattern_hints_used"] == 0  # No patterns on first run

    # Verify patterns were recorded
    async with get_db_context() as db:
        pattern_manager = EntityPatternManager()
        patterns = await pattern_manager.get_entity_patterns(
            session=db,
            entity_id="acme-uuid",
            min_confidence=0.7
        )
        assert len(patterns) > 0
        logger.info(f"Recorded {len(patterns)} patterns from first extraction")

    # Second extraction (patterns should be used)
    result2 = await extract_from_file(
        file_path="tests/fixtures/acme_q2_2025.xlsx",
        entity_id="acme-uuid"
    )

    assert result2["pattern_hints_used"] > 0  # Patterns used as hints

    # Verify pattern confidence improved (Bayesian update)
    async with get_db_context() as db:
        pattern_manager = EntityPatternManager()
        patterns_after = await pattern_manager.get_entity_patterns(
            session=db,
            entity_id="acme-uuid"
        )

        # Check that patterns with frequency > 1 exist
        multi_use_patterns = [p for p in patterns_after if p.frequency > 1]
        assert len(multi_use_patterns) > 0

        # Verify Bayesian confidence is reasonable
        for pattern in multi_use_patterns:
            assert 0.7 <= pattern.confidence <= 1.0

@pytest.mark.asyncio
async def test_pattern_accuracy_improvement():
    """Test that patterns improve accuracy on repeat extractions."""

    # Extract same entity 5 times
    accuracies = []
    for i in range(5):
        result = await extract_from_file(
            file_path=f"tests/fixtures/acme_q{i+1}_2025.xlsx",
            entity_id="acme-uuid"
        )

        # Calculate accuracy (compare to ground truth)
        accuracy = calculate_mapping_accuracy(result["mappings"], ground_truth)
        accuracies.append(accuracy)
        logger.info(f"Extraction {i+1}: accuracy={accuracy:.2%}")

    # Verify accuracy improves over time
    assert accuracies[4] > accuracies[0]  # 5th better than 1st
    assert accuracies[4] - accuracies[0] >= 0.04  # At least 4% improvement
```

---

### Task 4: Pattern Drift Detection (1 hour)

**File**: `src/guidelines/entity_patterns.py`

#### Implement `detect_pattern_drift()`

```python
async def detect_pattern_drift(
    self,
    session: AsyncSession,
    entity_id: str,
    lookback_days: int = 90
) -> List[Dict[str, Any]]:
    """
    Detect pattern drift - when entity changes terminology.

    Identifies labels that previously mapped to one canonical name
    but now map to a different one (with high confidence).
    """
    from sqlalchemy import select, and_, func
    from src.db.models import EntityPattern
    from datetime import datetime, timedelta

    logger.debug(f"Detecting drift: entity={entity_id}, lookback={lookback_days} days")

    cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)

    # Get all patterns for entity
    stmt = select(EntityPattern).where(EntityPattern.entity_id == entity_id)
    result = await session.execute(stmt)
    all_patterns = result.scalars().all()

    # Group by original_label
    label_patterns = {}
    for pattern in all_patterns:
        label = pattern.original_label
        if label not in label_patterns:
            label_patterns[label] = []
        label_patterns[label].append(pattern)

    # Detect drift: label maps to multiple canonical names
    drift_alerts = []
    for label, patterns in label_patterns.items():
        if len(patterns) < 2:
            continue  # No drift if only one canonical name

        # Sort by last_seen (most recent first)
        patterns_sorted = sorted(patterns, key=lambda p: p.last_seen, reverse=True)

        # Check if recent pattern differs from historical
        recent_pattern = patterns_sorted[0]
        historical_patterns = [p for p in patterns_sorted[1:] if p.last_seen < cutoff_date]

        if not historical_patterns:
            continue  # No historical data to compare

        # Most common historical canonical name
        historical_canonical = max(
            set(p.canonical_name for p in historical_patterns),
            key=lambda c: sum(1 for p in historical_patterns if p.canonical_name == c)
        )

        if recent_pattern.canonical_name != historical_canonical:
            # Drift detected!
            drift_alerts.append({
                "original_label": label,
                "old_canonical": historical_canonical,
                "new_canonical": recent_pattern.canonical_name,
                "confidence_delta": recent_pattern.confidence - max(
                    p.confidence for p in historical_patterns
                ),
                "last_old_seen": max(p.last_seen for p in historical_patterns).isoformat(),
                "first_new_seen": recent_pattern.created_at.isoformat(),
                "severity": "warning" if recent_pattern.confidence >= 0.8 else "info"
            })

            logger.warning(
                f"Drift detected: '{label}' changed from '{historical_canonical}' "
                f"to '{recent_pattern.canonical_name}'"
            )

    return drift_alerts
```

---

### Task 5: Monitoring & Statistics (30 min)

#### Implement `get_pattern_statistics()`

```python
async def get_pattern_statistics(
    self,
    session: AsyncSession,
    entity_id: Optional[str] = None
) -> Dict[str, Any]:
    """Get statistics about pattern learning progress."""
    from sqlalchemy import select, func
    from src.db.models import EntityPattern, Taxonomy

    logger.debug(f"Calculating statistics for entity={entity_id or 'global'}")

    # Build base query
    if entity_id:
        base_stmt = select(EntityPattern).where(EntityPattern.entity_id == entity_id)
    else:
        base_stmt = select(EntityPattern)

    # Total patterns
    total_result = await session.execute(
        select(func.count()).select_from(base_stmt.subquery())
    )
    total_patterns = total_result.scalar()

    # Get all patterns for detailed stats
    result = await session.execute(base_stmt)
    patterns = result.scalars().all()

    if not patterns:
        return {
            "total_patterns": 0,
            "unique_labels": 0,
            "avg_confidence": 0.0,
            "high_confidence_patterns": 0,
            "low_confidence_patterns": 0,
            "avg_frequency": 0.0,
            "coverage_pct": 0.0
        }

    # Calculate statistics
    confidences = [p.confidence for p in patterns]
    frequencies = [p.frequency for p in patterns]
    unique_labels = len(set(p.original_label for p in patterns))
    high_confidence = sum(1 for p in patterns if p.confidence >= 0.9)
    low_confidence = sum(1 for p in patterns if p.confidence < 0.7)

    # Calculate taxonomy coverage
    taxonomy_result = await session.execute(select(func.count()).select_from(Taxonomy))
    total_taxonomy_items = taxonomy_result.scalar()
    unique_canonical = len(set(p.canonical_name for p in patterns))
    coverage_pct = unique_canonical / total_taxonomy_items if total_taxonomy_items > 0 else 0.0

    stats = {
        "total_patterns": total_patterns,
        "unique_labels": unique_labels,
        "unique_canonical_names": unique_canonical,
        "avg_confidence": sum(confidences) / len(confidences),
        "high_confidence_patterns": high_confidence,
        "low_confidence_patterns": low_confidence,
        "avg_frequency": sum(frequencies) / len(frequencies),
        "max_frequency": max(frequencies),
        "coverage_pct": coverage_pct,
        "confidence_distribution": {
            "0.9-1.0": sum(1 for c in confidences if 0.9 <= c <= 1.0),
            "0.8-0.9": sum(1 for c in confidences if 0.8 <= c < 0.9),
            "0.7-0.8": sum(1 for c in confidences if 0.7 <= c < 0.8),
            "<0.7": sum(1 for c in confidences if c < 0.7),
        }
    }

    logger.info(f"Pattern statistics: {stats['total_patterns']} patterns, {stats['coverage_pct']:.1%} coverage")
    return stats
```

---

### Task 6: Documentation & Polish (1 hour)

#### Subtask 6.1: Update README (15 min)

Add section on entity pattern learning to main README.

#### Subtask 6.2: Add Logging (15 min)

Ensure all operations have appropriate logging:
- DEBUG: Individual pattern operations
- INFO: Pattern recording, suggestions, drift detection
- WARNING: Drift alerts, low confidence patterns
- ERROR: Database failures, validation errors

#### Subtask 6.3: Error Handling (15 min)

Add comprehensive error handling:
- Database connection failures
- Invalid confidence values
- Missing entity_id
- Concurrent pattern recording

#### Subtask 6.4: Performance Optimization (15 min)

- Add database indexes (if not already in Agent 1)
- Batch pattern recording for multiple mappings
- Cache frequently used patterns (optional)

---

## Testing Checklist

### Unit Tests (15 tests minimum)
- [ ] test_record_mapping_new
- [ ] test_record_mapping_bayesian_update
- [ ] test_record_mapping_invalid_confidence
- [ ] test_get_entity_patterns
- [ ] test_get_entity_patterns_min_confidence
- [ ] test_get_entity_patterns_min_frequency
- [ ] test_get_pattern_suggestions_exact
- [ ] test_get_pattern_suggestions_fuzzy
- [ ] test_get_pattern_suggestions_scoring
- [ ] test_pattern_metadata_storage
- [ ] test_multiple_entities_isolation
- [ ] test_pattern_frequency_increment
- [ ] test_detect_pattern_drift
- [ ] test_get_pattern_statistics
- [ ] test_error_handling_database_failure

### Integration Tests (5 tests minimum)
- [ ] test_full_extraction_pattern_loop
- [ ] test_pattern_accuracy_improvement
- [ ] test_pattern_hints_in_stage3
- [ ] test_pattern_drift_detection_workflow
- [ ] test_multiple_entities_parallel_extraction

### Performance Tests
- [ ] Pattern recording: < 50ms per mapping
- [ ] Pattern retrieval: < 100ms for entity
- [ ] Fuzzy matching: < 200ms
- [ ] Stage 3 with patterns: < 35s total

### Manual Testing
- [ ] Extract same entity 5 times, verify accuracy improves
- [ ] Verify pattern hints appear in Claude prompt
- [ ] Verify Bayesian confidence updates correctly
- [ ] Test drift detection with terminology change
- [ ] Test with multiple entities simultaneously

---

## Deployment Checklist

### Pre-Deployment
- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] Performance benchmarks met
- [ ] Code review completed
- [ ] Documentation updated

### Database
- [ ] PostgreSQL pg_trgm extension enabled
- [ ] entity_patterns table created
- [ ] Indexes created and verified
- [ ] Foreign keys working correctly

### Monitoring
- [ ] Pattern recording metrics tracked
- [ ] Pattern usage metrics tracked
- [ ] Drift alerts configured
- [ ] Error rate monitoring

### Rollout Strategy
1. **Phase 1**: Deploy with pattern recording only (no hints)
2. **Phase 2**: Enable pattern hints for 10% of extractions
3. **Phase 3**: Enable for 50% of extractions
4. **Phase 4**: Full rollout to 100%

---

## Success Metrics (After 1 Week)

### Accuracy Metrics
- [ ] 2nd extraction: +4% accuracy improvement
- [ ] 5th extraction: +6% accuracy improvement
- [ ] Manual corrections: -58% reduction (12 → 5)
- [ ] User satisfaction: +10% improvement

### Pattern Learning Metrics
- [ ] Average patterns per entity: 80-120
- [ ] High-confidence patterns (>0.9): 50-70
- [ ] Taxonomy coverage: 60-70%
- [ ] Average pattern frequency: 4-6x

### Performance Metrics
- [ ] Pattern recording: < 50ms/mapping
- [ ] Pattern retrieval: < 100ms
- [ ] Stage 3 with patterns: < 35s
- [ ] Zero database timeout errors

---

## Rollback Plan

If issues arise:

1. **Immediate**: Disable pattern hints in Stage 3 (keep recording)
2. **Investigation**: Check logs, pattern statistics, accuracy metrics
3. **Fix**: Address specific issue (confidence thresholds, fuzzy matching, etc.)
4. **Gradual Re-enable**: Start with 10%, monitor closely

**Rollback Command**:
```python
# In orchestrator.py, temporarily disable pattern hints
ENABLE_PATTERN_HINTS = False  # Emergency rollback flag

if ENABLE_PATTERN_HINTS and entity_id:
    # Load patterns
    ...
```

---

## References

- **Integration Guide**: [ENTITY_PATTERNS_INTEGRATION.md](ENTITY_PATTERNS_INTEGRATION.md)
- **Database Schema**: ENTITY_PATTERNS_INTEGRATION.md lines 27-66
- **Roadmap**: [TAXONOMY_ROADMAP_TO_EXCELLENCE.md](TAXONOMY_ROADMAP_TO_EXCELLENCE.md)
- **Agent 3 Delivery**: [AGENT3_DELIVERY_SUMMARY.md](../AGENT3_DELIVERY_SUMMARY.md)

---

**Status**: 📋 **READY TO IMPLEMENT**
**Next Action**: Wait for Agent 1 completion, then proceed with Task 1

**Created by**: Claude (Agent 3: Taxonomy & Seed Data)
**Date**: February 24, 2026
**Version**: 1.0.0 (Implementation Plan)
