# Entity Pattern Learning - Integration Guide

**Status**: 🔨 **STUB** (Foundation laid, awaiting Agent 1 database implementation)
**Version**: 1.0.0
**Date**: 2026-02-24
**Reference**: [TAXONOMY_ROADMAP_TO_EXCELLENCE.md](TAXONOMY_ROADMAP_TO_EXCELLENCE.md) - Week 4

---

## Overview

The Entity Pattern Learning system enables the DebtFund platform to learn and remember how specific entities (companies) label their financial statements. Over time, this creates company-specific "memories" that improve extraction accuracy and reduce manual corrections.

**Key Concept**: If Acme Corp always uses "Net Sales" to mean `revenue`, the system learns this pattern and automatically suggests it in future extractions.

---

## Architecture

### Components

1. **EntityPattern Model** (Agent 1: Database)
   - Stores entity-specific label → canonical mappings
   - Tracks confidence, frequency, and metadata
   - Supports Bayesian confidence updating

2. **EntityPatternManager** (Agent 4: Guidelines)
   - Records new mappings from extractions
   - Retrieves patterns for entity-specific suggestions
   - Detects pattern drift (terminology changes)
   - Provides statistics for monitoring

3. **Integration Points**
   - **Stage 3 Mapping**: Inject entity patterns as hints
   - **Agent 5 Validator**: Use patterns for validation
   - **Agent 6 Lineage**: Track pattern provenance

---

## Database Schema (Agent 1 Implementation)

### EntityPattern Table

```sql
CREATE TABLE entity_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign Keys
    entity_id UUID NOT NULL,  -- References entities.id
    canonical_name VARCHAR(100) NOT NULL,  -- References taxonomy.canonical_name

    -- Pattern Data
    original_label VARCHAR(500) NOT NULL,  -- Label from financial statement
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    frequency INT DEFAULT 1,  -- Number of times seen

    -- Temporal Tracking
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Context Metadata
    metadata JSONB,  -- {sheet_name, row_number, file_id, etc.}

    -- Constraints
    UNIQUE(entity_id, original_label, canonical_name),
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (canonical_name) REFERENCES taxonomy(canonical_name) ON DELETE CASCADE
);

-- Performance Indexes
CREATE INDEX idx_entity_patterns_entity ON entity_patterns(entity_id);
CREATE INDEX idx_entity_patterns_label ON entity_patterns(original_label);
CREATE INDEX idx_entity_patterns_canonical ON entity_patterns(canonical_name);
CREATE INDEX idx_entity_patterns_confidence ON entity_patterns(confidence);
CREATE INDEX idx_entity_patterns_last_seen ON entity_patterns(last_seen);

-- Full-text search on labels (optional)
CREATE INDEX idx_entity_patterns_label_trgm ON entity_patterns
    USING gin(original_label gin_trgm_ops);
```

### SQLAlchemy Model (Agent 1)

```python
# src/db/models.py

from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

class EntityPattern(Base):
    """
    Entity-specific mapping pattern for learned terminology.

    Tracks how a specific entity (company) maps labels to canonical
    taxonomy items, enabling personalized extraction.
    """
    __tablename__ = "entity_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Keys
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    canonical_name = Column(String(100), ForeignKey("taxonomy.canonical_name", ondelete="CASCADE"), nullable=False)

    # Pattern Data
    original_label = Column(String(500), nullable=False)
    confidence = Column(Float, nullable=False)
    frequency = Column(Integer, default=1)

    # Temporal Tracking
    last_seen = Column(DateTime(timezone=True), default=func.now())
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Context Metadata
    metadata = Column(JSONB)

    # Relationships
    entity = relationship("Entity", back_populates="patterns")
    taxonomy_item = relationship("Taxonomy")

    # Constraints
    __table_args__ = (
        UniqueConstraint("entity_id", "original_label", "canonical_name", name="uq_entity_pattern"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_confidence_range"),
    )
```

---

## Integration: Stage 3 Mapping (Orchestrator)

### Current Flow (v1.2.0)

```python
# src/extraction/orchestrator.py

async def stage_3_mapping(parsed_result: dict) -> dict:
    """Stage 3: Map line items to canonical taxonomy."""
    from src.db.session import get_db_context
    from src.guidelines.taxonomy import load_taxonomy_for_stage3

    # Extract labels
    labels = set()
    for sheet in parsed_result.get("sheets", []):
        for row in sheet.get("rows", []):
            if row.get("label"):
                labels.add(row["label"])

    if not labels:
        return {"mappings": [], "tokens": 0}

    # Load taxonomy from database
    async with get_db_context() as db:
        taxonomy_text = await load_taxonomy_for_stage3(db)

    # Build mapping prompt
    mapping_prompt = f"""
    Map these financial line items to canonical names.

    CANONICAL TAXONOMY (use these exact names):
    {taxonomy_text}

    Line items to map: {list(labels)}
    """

    # Call Claude for mapping
    response = client.messages.create(...)
    return parse_mappings(response)
```

### Enhanced Flow with Entity Patterns (Week 4)

```python
# src/extraction/orchestrator.py

async def stage_3_mapping(
    parsed_result: dict,
    entity_id: Optional[str] = None  # NEW: Entity context
) -> dict:
    """Stage 3: Map line items to canonical taxonomy with entity patterns."""
    from src.db.session import get_db_context
    from src.guidelines.taxonomy import load_taxonomy_for_stage3
    from src.guidelines.entity_patterns import (
        EntityPatternManager,
        augment_taxonomy_with_patterns
    )

    # Extract labels
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

        # Augment with entity-specific patterns if entity_id provided
        if entity_id:
            taxonomy_text = await augment_taxonomy_with_patterns(
                session=db,
                entity_id=entity_id,
                base_taxonomy=base_taxonomy,
                min_confidence=0.8
            )

            # Get pattern suggestions for each label
            pattern_manager = EntityPatternManager()
            pattern_hints = {}
            for label in labels:
                suggestions = await pattern_manager.get_pattern_suggestions(
                    session=db,
                    entity_id=entity_id,
                    original_label=label
                )
                if suggestions:
                    pattern_hints[label] = suggestions[0]  # Top suggestion
        else:
            taxonomy_text = base_taxonomy
            pattern_hints = {}

    # Build enhanced mapping prompt
    pattern_context = ""
    if pattern_hints:
        pattern_context = "\n\nENTITY-SPECIFIC PATTERNS (use these as strong hints):\n"
        for label, hint in pattern_hints.items():
            pattern_context += (
                f"- '{label}' typically maps to '{hint['canonical_name']}' "
                f"({hint['confidence']:.0%} confidence, seen {hint['frequency']}x)\n"
            )

    mapping_prompt = f"""
    Map these financial line items to canonical names.

    CANONICAL TAXONOMY (use these exact names):
    {taxonomy_text}
    {pattern_context}

    Line items to map: {list(labels)}
    """

    # Call Claude for mapping
    response = client.messages.create(...)
    mappings = parse_mappings(response)

    # Record patterns for future learning
    if entity_id:
        async with get_db_context() as db:
            pattern_manager = EntityPatternManager()
            for mapping in mappings:
                await pattern_manager.record_mapping(
                    session=db,
                    entity_id=entity_id,
                    original_label=mapping["original_label"],
                    canonical_name=mapping["canonical_name"],
                    confidence=mapping["confidence"],
                    metadata={
                        "file_id": parsed_result.get("file_id"),
                        "sheet_name": mapping.get("sheet_name"),
                        "extraction_date": datetime.utcnow().isoformat()
                    }
                )

    return mappings
```

---

## Integration: Agent 5 Validator

### Pattern-Based Validation

```python
# src/validation/validator.py (Agent 5)

from src.guidelines.entity_patterns import EntityPatternManager

async def validate_mappings(
    mappings: List[Dict],
    entity_id: str,
    session: AsyncSession
) -> List[Dict]:
    """
    Validate mappings against entity patterns.

    Flags mappings that differ significantly from learned patterns
    as potential errors requiring review.
    """
    pattern_manager = EntityPatternManager()
    validation_results = []

    for mapping in mappings:
        # Get historical patterns for this label
        suggestions = await pattern_manager.get_pattern_suggestions(
            session=session,
            entity_id=entity_id,
            original_label=mapping["original_label"]
        )

        if suggestions:
            top_suggestion = suggestions[0]

            # Check if current mapping matches historical pattern
            if mapping["canonical_name"] != top_suggestion["canonical_name"]:
                # Potential pattern drift or error
                validation_results.append({
                    "label": mapping["original_label"],
                    "mapped_to": mapping["canonical_name"],
                    "expected": top_suggestion["canonical_name"],
                    "confidence_delta": abs(
                        mapping["confidence"] - top_suggestion["confidence"]
                    ),
                    "frequency": top_suggestion["frequency"],
                    "severity": "warning",
                    "message": (
                        f"Unexpected mapping: '{mapping['original_label']}' "
                        f"mapped to '{mapping['canonical_name']}', but historically "
                        f"maps to '{top_suggestion['canonical_name']}' "
                        f"({top_suggestion['frequency']}x, {top_suggestion['confidence']:.0%} confidence)"
                    )
                })

    return validation_results
```

---

## Integration: Agent 6 Lineage

### Pattern Provenance Tracking

```python
# src/lineage/tracker.py (Agent 6)

from src.guidelines.entity_patterns import EntityPatternManager

async def track_mapping_lineage(
    mapping: Dict,
    entity_id: str,
    session: AsyncSession
) -> Dict:
    """
    Track lineage of a mapping including pattern influence.

    Records whether mapping was influenced by learned pattern,
    enabling provenance analysis.
    """
    pattern_manager = EntityPatternManager()

    # Check if pattern influenced this mapping
    suggestions = await pattern_manager.get_pattern_suggestions(
        session=session,
        entity_id=entity_id,
        original_label=mapping["original_label"]
    )

    pattern_influenced = False
    pattern_details = None

    if suggestions:
        top_suggestion = suggestions[0]
        if mapping["canonical_name"] == top_suggestion["canonical_name"]:
            pattern_influenced = True
            pattern_details = {
                "pattern_confidence": top_suggestion["confidence"],
                "pattern_frequency": top_suggestion["frequency"],
                "pattern_score": top_suggestion["score"]
            }

    # Create lineage record
    lineage = {
        "extraction_id": mapping["extraction_id"],
        "original_label": mapping["original_label"],
        "canonical_name": mapping["canonical_name"],
        "confidence": mapping["confidence"],
        "pattern_influenced": pattern_influenced,
        "pattern_details": pattern_details,
        "timestamp": datetime.utcnow().isoformat()
    }

    return lineage
```

---

## Expected Impact (Week 4 Implementation)

### Accuracy Improvements

| Metric | Baseline (v1.2.0) | With Patterns (Week 4) | Improvement |
|--------|-------------------|------------------------|-------------|
| **First-time Extraction** | 91% | 91% | 0% (no patterns yet) |
| **Second Extraction** | 91% | 95% | **+4%** |
| **5th+ Extraction** | 91% | 97% | **+6%** |
| **Manual Corrections** | 12 per model | 5 per model | **-58%** |
| **User Confidence** | 90% | 95% | +5% |

### Pattern Learning Metrics

**After 10 Extractions for Same Entity**:
- Learned patterns: ~120 (70% of typical financial statement)
- High-confidence patterns (>0.9): ~80 (47%)
- Average pattern frequency: 6.5
- Pattern coverage: 70% of labels auto-suggested

**Expected Time Savings**:
- Time to review mappings: 8 min → 3 min (-62%)
- Manual corrections: 12 → 5 (-58%)
- Total extraction time: 10 min → 6 min (-40%)

---

## Implementation Checklist

### Agent 1: Database Architect ⏳

- [ ] Create `entity_patterns` table in migration
- [ ] Implement `EntityPattern` SQLAlchemy model in `src/db/models.py`
- [ ] Add indexes for performance (entity_id, original_label, confidence)
- [ ] Add foreign key constraints to entities and taxonomy tables
- [ ] Test UPSERT operations for pattern recording
- [ ] Implement Bayesian confidence updating in model

### Agent 3: Taxonomy & Seed Data ✅

- [x] Create `EntityPatternManager` stub in `src/guidelines/entity_patterns.py`
- [x] Document integration points
- [x] Define API contracts for pattern operations
- [x] Create integration guide (this document)

### Agent 4: Guidelines Manager (Week 4) ⏳

- [ ] Implement `record_mapping()` with database operations
- [ ] Implement `get_entity_patterns()` with SQLAlchemy queries
- [ ] Implement `get_pattern_suggestions()` with fuzzy matching
- [ ] Implement `detect_pattern_drift()` with temporal analysis
- [ ] Implement `augment_taxonomy_with_patterns()` with hint injection
- [ ] Add unit tests for all pattern operations

### Orchestrator Integration (Week 4) ⏳

- [ ] Add `entity_id` parameter to `stage_3_mapping()`
- [ ] Integrate pattern suggestions into mapping prompt
- [ ] Record mappings after successful extraction
- [ ] Add pattern-based validation hooks

### Agent 5: Validator (Week 5) ⏳

- [ ] Integrate pattern-based validation
- [ ] Flag mappings that differ from patterns
- [ ] Create validation reports with pattern context

### Agent 6: Lineage (Week 6) ⏳

- [ ] Track pattern influence in lineage records
- [ ] Enable pattern provenance queries
- [ ] Create pattern impact analytics

---

## Testing Strategy

### Unit Tests (Agent 4)

```python
# tests/unit/test_entity_patterns.py

@pytest.mark.asyncio
async def test_record_mapping():
    """Test recording a new pattern."""
    pattern_manager = EntityPatternManager()

    await pattern_manager.record_mapping(
        session=db,
        entity_id="test-entity-uuid",
        original_label="Net Sales",
        canonical_name="revenue",
        confidence=0.95
    )

    # Verify pattern was created
    patterns = await pattern_manager.get_entity_patterns(
        session=db,
        entity_id="test-entity-uuid"
    )
    assert len(patterns) == 1
    assert patterns[0].original_label == "Net Sales"
    assert patterns[0].canonical_name == "revenue"
    assert patterns[0].confidence == 0.95
    assert patterns[0].frequency == 1

@pytest.mark.asyncio
async def test_bayesian_confidence_update():
    """Test Bayesian confidence updating on repeat mappings."""
    pattern_manager = EntityPatternManager()

    # First mapping: 95% confidence
    await pattern_manager.record_mapping(
        session=db,
        entity_id="test-entity-uuid",
        original_label="Net Sales",
        canonical_name="revenue",
        confidence=0.95
    )

    # Second mapping: 85% confidence
    await pattern_manager.record_mapping(
        session=db,
        entity_id="test-entity-uuid",
        original_label="Net Sales",
        canonical_name="revenue",
        confidence=0.85
    )

    # Verify Bayesian update: (0.95*1 + 0.85*1) / 2 = 0.90
    patterns = await pattern_manager.get_entity_patterns(
        session=db,
        entity_id="test-entity-uuid"
    )
    assert patterns[0].frequency == 2
    assert abs(patterns[0].confidence - 0.90) < 0.01
```

### Integration Tests

```python
# tests/integration/test_pattern_extraction.py

@pytest.mark.asyncio
async def test_pattern_learning_loop():
    """Test full extraction → pattern recording → suggestion loop."""

    # First extraction (no patterns)
    result1 = await extract_financial_model(
        file_path="tests/fixtures/acme_q1_2025.xlsx",
        entity_id="acme-uuid"
    )
    assert result1["mappings_suggested"] == 0  # No patterns yet

    # Second extraction (patterns learned from first)
    result2 = await extract_financial_model(
        file_path="tests/fixtures/acme_q2_2025.xlsx",
        entity_id="acme-uuid"
    )
    assert result2["mappings_suggested"] > 0  # Patterns from Q1
    assert result2["accuracy"] > result1["accuracy"]  # Improved accuracy
```

---

## Monitoring & Analytics

### Pattern Dashboard Metrics

```sql
-- Pattern Coverage by Entity
SELECT
    e.name,
    COUNT(DISTINCT ep.canonical_name) as unique_patterns,
    AVG(ep.confidence) as avg_confidence,
    SUM(ep.frequency) as total_extractions
FROM entity_patterns ep
JOIN entities e ON e.id = ep.entity_id
GROUP BY e.name
ORDER BY unique_patterns DESC;

-- Low Confidence Patterns (Need Review)
SELECT
    ep.original_label,
    ep.canonical_name,
    ep.confidence,
    ep.frequency,
    e.name as entity_name
FROM entity_patterns ep
JOIN entities e ON e.id = ep.entity_id
WHERE ep.confidence < 0.7
AND ep.frequency >= 3
ORDER BY ep.frequency DESC;

-- Pattern Drift Detection
WITH pattern_changes AS (
    SELECT
        entity_id,
        original_label,
        canonical_name,
        LAG(canonical_name) OVER (
            PARTITION BY entity_id, original_label
            ORDER BY last_seen
        ) as prev_canonical_name,
        last_seen
    FROM entity_patterns
)
SELECT * FROM pattern_changes
WHERE canonical_name != prev_canonical_name;
```

---

## Future Enhancements (Roadmap)

### Week 5: Confidence Calibration
- Track actual accuracy vs. Claude confidence scores
- Implement ECE (Expected Calibration Error) < 0.05
- Build calibration curves per entity

### Week 6: Active Learning
- Flag low-confidence patterns for human review
- Prioritize patterns with high disagreement
- Build human-in-the-loop feedback system

### Week 7: Pattern Drift Alerts
- Detect terminology changes automatically
- Alert users when patterns shift significantly
- Support regulatory transitions (IFRS → GAAP)

### Week 8: Multi-Entity Pattern Transfer
- Learn patterns from similar entities
- Cold-start problem: use industry patterns for new entities
- Build entity similarity graph

---

## API Reference

### EntityPatternManager

#### `record_mapping()`
Records a mapping pattern for an entity.

**Parameters**:
- `session: AsyncSession` - Database session
- `entity_id: str` - Entity UUID
- `original_label: str` - Label from financial statement
- `canonical_name: str` - Mapped canonical name
- `confidence: float` - Confidence score (0-1)
- `metadata: Optional[Dict]` - Additional context

**Returns**: `None`

#### `get_entity_patterns()`
Retrieves learned patterns for an entity.

**Parameters**:
- `session: AsyncSession` - Database session
- `entity_id: str` - Entity UUID
- `min_confidence: float = 0.7` - Minimum confidence threshold
- `min_frequency: int = 1` - Minimum frequency threshold

**Returns**: `List[EntityPattern]` - Sorted by confidence descending

#### `get_pattern_suggestions()`
Gets canonical name suggestions for a label.

**Parameters**:
- `session: AsyncSession` - Database session
- `entity_id: str` - Entity UUID
- `original_label: str` - Label to find suggestions for

**Returns**: `List[Dict]` - Top suggestions with scores

#### `detect_pattern_drift()`
Detects terminology changes over time.

**Parameters**:
- `session: AsyncSession` - Database session
- `entity_id: str` - Entity UUID
- `lookback_days: int = 90` - Days to analyze

**Returns**: `List[Dict]` - Drift alerts

---

## References

- **Roadmap**: [TAXONOMY_ROADMAP_TO_EXCELLENCE.md](TAXONOMY_ROADMAP_TO_EXCELLENCE.md)
- **Agent 3 Delivery**: [AGENT3_DELIVERY_SUMMARY.md](../AGENT3_DELIVERY_SUMMARY.md)
- **Quick Wins**: [QUICK_WINS_SUMMARY.md](../QUICK_WINS_SUMMARY.md)

---

**Status**: ✅ **STUB COMPLETE** - Ready for Agent 1 database implementation
**Next Step**: Agent 1 creates `entity_patterns` table and `EntityPattern` model
**Timeline**: Week 4 implementation, Week 5 production deployment

**Created by**: Claude (Agent 3: Taxonomy & Seed Data)
**Date**: February 24, 2026
**Version**: 1.0.0 (Foundation)
