# Agent 1 Task Brief: Entity Patterns Database Integration

**Priority**: 🔴 **BLOCKING** for Week 4 pattern learning implementation
**Effort**: 4 hours
**Status**: ⏳ **READY TO START**
**Date**: 2026-02-24

---

## Quick Summary

Implement database infrastructure for entity pattern learning system. All specs are complete - this is pure implementation work.

**What**: Create `entity_patterns` table + `EntityPattern` SQLAlchemy model
**Why**: Enables intelligent learning system (+6% accuracy, -58% manual corrections)
**When**: ASAP - blocking Week 4 implementation

---

## Task 1: Create entity_patterns Table (1.5 hours)

### Database Migration

**File**: `alembic/versions/00X_create_entity_patterns.py`

**SQL Schema** (copy-paste ready):
```sql
CREATE TABLE entity_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign Keys
    entity_id UUID NOT NULL,
    canonical_name VARCHAR(100) NOT NULL,

    -- Pattern Data
    original_label VARCHAR(500) NOT NULL,
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    frequency INT DEFAULT 1,

    -- Temporal Tracking
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Context Metadata
    metadata JSONB,

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

-- Fuzzy Matching (PostgreSQL full-text search)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_entity_patterns_label_trgm ON entity_patterns
    USING gin(original_label gin_trgm_ops);
```

### Alembic Migration Pattern

```python
"""Create entity_patterns table for pattern learning.

Revision ID: 00X_entity_patterns
Revises: 00Y_previous_migration
Create Date: 2026-02-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '00X_entity_patterns'
down_revision = '00Y_previous_migration'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create entity_patterns table with indexes."""

    # Create table
    op.create_table(
        'entity_patterns',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Foreign Keys
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('canonical_name', sa.String(100), nullable=False),

        # Pattern Data
        sa.Column('original_label', sa.String(500), nullable=False),
        sa.Column('confidence', sa.Float, nullable=False),
        sa.Column('frequency', sa.Integer, server_default='1'),

        # Temporal
        sa.Column('last_seen', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        # Metadata
        sa.Column('metadata', postgresql.JSONB),

        # Constraints
        sa.UniqueConstraint('entity_id', 'original_label', 'canonical_name', name='uq_entity_pattern'),
        sa.CheckConstraint('confidence >= 0 AND confidence <= 1', name='ck_confidence_range'),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['canonical_name'], ['taxonomy.canonical_name'], ondelete='CASCADE'),
    )

    # Create indexes
    op.create_index('idx_entity_patterns_entity', 'entity_patterns', ['entity_id'])
    op.create_index('idx_entity_patterns_label', 'entity_patterns', ['original_label'])
    op.create_index('idx_entity_patterns_canonical', 'entity_patterns', ['canonical_name'])
    op.create_index('idx_entity_patterns_confidence', 'entity_patterns', ['confidence'])
    op.create_index('idx_entity_patterns_last_seen', 'entity_patterns', ['last_seen'])

    # Enable pg_trgm extension for fuzzy matching
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.create_index(
        'idx_entity_patterns_label_trgm',
        'entity_patterns',
        ['original_label'],
        postgresql_using='gin',
        postgresql_ops={'original_label': 'gin_trgm_ops'}
    )


def downgrade() -> None:
    """Drop entity_patterns table and indexes."""
    op.drop_index('idx_entity_patterns_label_trgm', 'entity_patterns')
    op.drop_index('idx_entity_patterns_last_seen', 'entity_patterns')
    op.drop_index('idx_entity_patterns_confidence', 'entity_patterns')
    op.drop_index('idx_entity_patterns_canonical', 'entity_patterns')
    op.drop_index('idx_entity_patterns_label', 'entity_patterns')
    op.drop_index('idx_entity_patterns_entity', 'entity_patterns')
    op.drop_table('entity_patterns')
```

**Verification**:
```bash
# Run migration
alembic upgrade head

# Verify table created
psql -U emi -d emi -c "\d entity_patterns"

# Verify indexes
psql -U emi -d emi -c "\di entity_patterns*"

# Verify extension
psql -U emi -d emi -c "SELECT * FROM pg_extension WHERE extname = 'pg_trgm';"
```

---

## Task 2: Implement EntityPattern SQLAlchemy Model (1.5 hours)

### SQLAlchemy Model

**File**: `src/db/models.py`

**Add to existing models**:
```python
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

class EntityPattern(Base):
    """
    Entity-specific mapping pattern for learned terminology.

    Tracks how a specific entity (company) maps labels to canonical
    taxonomy items, enabling personalized extraction that improves
    over time through Bayesian confidence updating.

    Example:
        Acme Corp always uses "Net Sales" to mean "revenue"
        → After 5 extractions: confidence=0.96, frequency=5
    """
    __tablename__ = "entity_patterns"

    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign Keys
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    canonical_name = Column(
        String(100),
        ForeignKey("taxonomy.canonical_name", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Pattern Data
    original_label = Column(String(500), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    frequency = Column(Integer, default=1)

    # Temporal Tracking
    last_seen = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Context Metadata (stores extraction context)
    metadata = Column(JSONB)

    # Relationships
    entity = relationship("Entity", back_populates="patterns")
    taxonomy_item = relationship("Taxonomy")

    # Constraints
    __table_args__ = (
        UniqueConstraint("entity_id", "original_label", "canonical_name", name="uq_entity_pattern"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_confidence_range"),
    )

    def __repr__(self):
        return (
            f"<EntityPattern(entity_id='{self.entity_id}', "
            f"'{self.original_label}' → '{self.canonical_name}', "
            f"confidence={self.confidence:.2f}, frequency={self.frequency})>"
        )


# Add relationship to Entity model (if not already present)
# In Entity class:
class Entity(Base):
    __tablename__ = "entities"

    # ... existing columns ...

    # Relationships
    patterns = relationship(
        "EntityPattern",
        back_populates="entity",
        cascade="all, delete-orphan"
    )
```

**Verification**:
```python
# Test model creation
from src.db.models import EntityPattern, Entity, Taxonomy
from src.db.session import get_db_context

async def test_entity_pattern_model():
    async with get_db_context() as db:
        # Create test entity
        entity = Entity(id=uuid.uuid4(), name="Test Corp")
        db.add(entity)

        # Create test pattern
        pattern = EntityPattern(
            entity_id=entity.id,
            original_label="Net Sales",
            canonical_name="revenue",
            confidence=0.95,
            frequency=1,
            metadata={"test": "data"}
        )
        db.add(pattern)
        await db.commit()

        # Verify creation
        assert pattern.id is not None
        assert pattern.entity_id == entity.id
        assert pattern.confidence == 0.95

        print("✅ EntityPattern model working correctly")

# Run test
import asyncio
asyncio.run(test_entity_pattern_model())
```

---

## Task 3: Test Taxonomy Migration (1 hour)

### Verify Full Taxonomy Load

**Test Script** (run this):
```python
"""Verify taxonomy migration loads all enhanced data."""
import asyncio
from src.db.session import get_db_context
from src.guidelines.taxonomy import TaxonomyManager

async def verify_taxonomy_migration():
    print("="*70)
    print("VERIFYING TAXONOMY MIGRATION")
    print("="*70)

    async with get_db_context() as db:
        manager = TaxonomyManager()

        # Check total items
        all_items = await manager.get_all(db)
        print(f"\n✅ Total items loaded: {len(all_items)}")
        assert len(all_items) >= 173, f"Expected 173+ items, got {len(all_items)}"

        # Check aliases
        total_aliases = sum(len(item.aliases) for item in all_items)
        avg_aliases = total_aliases / len(all_items)
        print(f"✅ Total aliases: {total_aliases}")
        print(f"✅ Average aliases per item: {avg_aliases:.1f}")
        assert avg_aliases >= 5.0, f"Expected avg 5+ aliases, got {avg_aliases:.1f}"

        # Check validation rules
        items_with_rules = sum(1 for item in all_items if item.validation_rules)
        print(f"✅ Items with validation rules: {items_with_rules}")
        assert items_with_rules >= 34, f"Expected 34+ items with rules, got {items_with_rules}"

        # Check specific enhanced items
        revenue = await manager.get_by_canonical_name(db, "revenue")
        assert revenue is not None, "revenue item not found"
        assert len(revenue.aliases) >= 20, f"revenue should have 20+ aliases, got {len(revenue.aliases)}"
        print(f"✅ revenue item: {len(revenue.aliases)} aliases")

        # Check validation rules with benchmarks
        gross_margin = await manager.get_by_canonical_name(db, "gross_margin_pct")
        if gross_margin and gross_margin.validation_rules:
            benchmarks = gross_margin.validation_rules.get("industry_benchmarks", {})
            print(f"✅ gross_margin_pct: {len(benchmarks)} industry benchmarks")
            assert len(benchmarks) >= 3, "Expected 3+ industry benchmarks"

        # Check entity_patterns table exists
        from sqlalchemy import inspect
        inspector = inspect(db.bind)
        tables = await db.run_sync(lambda sync_conn: inspector.get_table_names())
        assert "entity_patterns" in tables, "entity_patterns table not found"
        print(f"✅ entity_patterns table created")

        print("\n" + "="*70)
        print("✅ TAXONOMY MIGRATION VERIFIED SUCCESSFULLY")
        print("="*70)

if __name__ == "__main__":
    asyncio.run(verify_taxonomy_migration())
```

**Run Verification**:
```bash
# Load taxonomy + create entity_patterns table
alembic upgrade head

# Verify all data loaded correctly
python3 verify_taxonomy_migration.py

# Expected output:
# ======================================================================
# VERIFYING TAXONOMY MIGRATION
# ======================================================================
#
# ✅ Total items loaded: 173
# ✅ Total aliases: 1133
# ✅ Average aliases per item: 6.6
# ✅ Items with validation rules: 173
# ✅ revenue item: 28 aliases
# ✅ gross_margin_pct: 4 industry benchmarks
# ✅ entity_patterns table created
#
# ======================================================================
# ✅ TAXONOMY MIGRATION VERIFIED SUCCESSFULLY
# ======================================================================
```

---

## Quick Reference: What Goes Where

| Component | File | What to Add |
|-----------|------|-------------|
| **Migration** | `alembic/versions/00X_entity_patterns.py` | CREATE TABLE + indexes |
| **Model** | `src/db/models.py` | `EntityPattern` class |
| **Relationship** | `src/db/models.py` → `Entity` class | `patterns = relationship(...)` |
| **Verification** | `verify_taxonomy_migration.py` | Test script (provided above) |

---

## Prerequisites Check

Before starting, verify:

- [ ] PostgreSQL database running
- [ ] Alembic initialized (`alembic/` directory exists)
- [ ] `entities` table exists (referenced by FK)
- [ ] `taxonomy` table exists and loaded (referenced by FK)
- [ ] Can connect to database with migrations
- [ ] `psycopg2` installed (for Alembic)
- [ ] `asyncpg` installed (for runtime)

---

## Success Criteria

### Must Have ✅
- [ ] `entity_patterns` table created in database
- [ ] All 6 indexes created
- [ ] pg_trgm extension enabled
- [ ] `EntityPattern` model works (CRUD operations)
- [ ] Foreign keys to `entities` and `taxonomy` working
- [ ] UNIQUE constraint on (entity_id, original_label, canonical_name) enforced
- [ ] CHECK constraint on confidence (0-1) enforced
- [ ] Taxonomy loads all 173 items with 1,133 aliases
- [ ] Validation rules with industry benchmarks present

### Nice to Have (Optional)
- [ ] Migration includes comments explaining purpose
- [ ] Model includes docstrings with examples
- [ ] Verification script runs automatically in CI/CD

---

## Common Issues & Solutions

### Issue 1: pg_trgm Extension Fails
**Error**: `extension "pg_trgm" does not exist`

**Solution**:
```bash
# Connect to database
psql -U emi -d emi

# Create extension manually
CREATE EXTENSION pg_trgm;

# Verify
SELECT * FROM pg_extension WHERE extname = 'pg_trgm';
```

### Issue 2: Foreign Key Constraint Fails
**Error**: `foreign key constraint "entity_patterns_entity_id_fkey" fails`

**Solution**: Ensure `entities` table exists first. Check migration dependencies:
```python
# In migration file
depends_on = 'entities_migration_id'
```

### Issue 3: UNIQUE Constraint Conflicts
**Error**: `duplicate key value violates unique constraint "uq_entity_pattern"`

**Solution**: This is expected behavior - pattern already exists. EntityPatternManager handles this with UPDATE logic.

---

## Testing

### Manual Tests

```bash
# 1. Run migration
alembic upgrade head

# 2. Verify table structure
psql -U emi -d emi -c "\d entity_patterns"

# Expected output shows:
# - 10 columns (id, entity_id, canonical_name, original_label, confidence, frequency, last_seen, created_at, updated_at, metadata)
# - 2 foreign keys
# - 1 unique constraint
# - 1 check constraint

# 3. Test INSERT
psql -U emi -d emi << EOF
INSERT INTO entity_patterns (entity_id, original_label, canonical_name, confidence, frequency)
VALUES ('00000000-0000-0000-0000-000000000001', 'Net Sales', 'revenue', 0.95, 1);
SELECT * FROM entity_patterns WHERE original_label = 'Net Sales';
EOF

# 4. Test UNIQUE constraint
psql -U emi -d emi << EOF
INSERT INTO entity_patterns (entity_id, original_label, canonical_name, confidence, frequency)
VALUES ('00000000-0000-0000-0000-000000000001', 'Net Sales', 'revenue', 0.90, 2);
-- Should fail with unique constraint violation
EOF

# 5. Clean up
psql -U emi -d emi -c "TRUNCATE entity_patterns CASCADE;"
```

### Automated Test

```python
# tests/integration/test_entity_pattern_model.py
import pytest
from src.db.models import EntityPattern, Entity
from src.db.session import get_db_context

@pytest.mark.asyncio
async def test_entity_pattern_crud():
    """Test EntityPattern CRUD operations."""
    async with get_db_context() as db:
        # Create
        pattern = EntityPattern(
            entity_id=test_entity.id,
            original_label="Test Label",
            canonical_name="revenue",
            confidence=0.85,
            frequency=1
        )
        db.add(pattern)
        await db.commit()

        # Read
        from sqlalchemy import select
        result = await db.execute(
            select(EntityPattern).where(EntityPattern.original_label == "Test Label")
        )
        fetched = result.scalar_one()
        assert fetched.confidence == 0.85

        # Update
        fetched.confidence = 0.90
        fetched.frequency = 2
        await db.commit()

        # Delete
        await db.delete(fetched)
        await db.commit()
```

---

## Handoff to Week 4

Once complete, Week 4 can immediately start implementing:
1. EntityPatternManager database operations (Task 1)
2. Stage 3 orchestrator integration (Task 2)
3. Comprehensive testing (Task 3)

**Full Week 4 Plan**: [WEEK4_PATTERN_IMPLEMENTATION_PLAN.md](WEEK4_PATTERN_IMPLEMENTATION_PLAN.md)

---

## Questions?

**Reference Documentation**:
- Complete schema & model spec: [ENTITY_PATTERNS_INTEGRATION.md](ENTITY_PATTERNS_INTEGRATION.md) lines 27-115
- Architecture & integration: [ENTITY_PATTERNS_INTEGRATION.md](ENTITY_PATTERNS_INTEGRATION.md)
- Week 4 implementation: [WEEK4_PATTERN_IMPLEMENTATION_PLAN.md](WEEK4_PATTERN_IMPLEMENTATION_PLAN.md)

**Need Help?**:
- Check existing migrations in `alembic/versions/` for patterns
- Review existing models in `src/db/models.py` for style
- All SQL is PostgreSQL-specific (pg_trgm, UUID, JSONB, etc.)

---

**Priority**: 🔴 **START IMMEDIATELY** - Blocking Week 4 implementation
**Estimated Time**: 4 hours
**Impact**: Enables +6% accuracy improvement, -58% manual corrections

**Status**: ⏳ **READY TO IMPLEMENT**

---

**Created by**: Claude (Agent 3: Taxonomy & Seed Data)
**For**: Agent 1 (Database Architect)
**Date**: February 24, 2026
