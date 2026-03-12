# Database Setup Guide

This guide explains how to set up and use the DebtFund database layer.

## Overview

The database layer includes:
- **6 Tables**: entities, entity_patterns, taxonomy, lineage_events, files, extraction_jobs
- **100+ Taxonomy Items**: Canonical financial line items seeded automatically
- **SQLAlchemy 2.0 ORM**: Async models for PostgreSQL 15
- **Alembic Migrations**: Version-controlled schema management

## Prerequisites

1. PostgreSQL 15 running (via Docker or local install)
2. Python 3.11+ virtual environment activated
3. All dependencies installed: `pip install -e ".[dev]"`

## Quick Start

### 1. Start PostgreSQL

```bash
docker compose up -d postgres
```

This starts PostgreSQL on `localhost:5432` with credentials:
- User: `emi`
- Password: `emi_dev`
- Database: `emi`

### 2. Run Migrations

```bash
# Upgrade to latest schema
alembic upgrade head

# Verify current version
alembic current

# Check migration history
alembic history --verbose
```

### 3. Verify Schema

```bash
# Connect to database
docker exec -it debtfund-postgres psql -U emi -d emi

# List tables
\dt

# Check taxonomy count (should be 70+)
SELECT COUNT(*) FROM taxonomy;

# View sample taxonomy items
SELECT canonical_name, category, display_name FROM taxonomy LIMIT 10;

# Exit
\q
```

## Database Schema

### Tables

#### 1. **entities**
Company/asset entities being analyzed.
- `id` (UUID, PK)
- `name` (VARCHAR 255)
- `industry` (VARCHAR 100)
- `created_at` (TIMESTAMP)

#### 2. **taxonomy**
Canonical financial line items (100+ items seeded).
- `id` (UUID, PK)
- `canonical_name` (VARCHAR 100, UNIQUE)
- `category` (VARCHAR 50): income_statement, balance_sheet, cash_flow, etc.
- `display_name` (VARCHAR 255)
- `aliases` (ARRAY TEXT): For fuzzy matching
- `definition` (TEXT)
- `typical_sign` (VARCHAR 10): positive/negative
- `parent_canonical` (VARCHAR 100): Hierarchy support

#### 3. **entity_patterns**
Learned pattern mappings for entity-specific customization.
- `id` (UUID, PK)
- `entity_id` (UUID, FK)
- `original_label` (VARCHAR 500)
- `canonical_name` (VARCHAR 100, FK to taxonomy)
- `confidence` (NUMERIC 5,4): 0.0-1.0
- `occurrence_count` (INT)
- `created_by` (VARCHAR 50): 'claude' or 'user_correction'

#### 4. **files**
Uploaded Excel files.
- `id` (UUID, PK)
- `filename` (VARCHAR 255)
- `file_type` (VARCHAR 50)
- `file_size_bytes` (BIGINT)
- `entity_id` (UUID, FK)
- `s3_path` (VARCHAR 500)
- `status` (VARCHAR 50)

#### 5. **extraction_jobs**
Extraction job tracking (replaces in-memory storage).
- `id` (UUID, PK)
- `file_id` (UUID, FK)
- `job_status` (VARCHAR 50): queued, processing, completed, failed
- `progress_percent` (INT 0-100)
- `current_stage` (VARCHAR 50)
- `result` (JSON)
- `claude_cost_usd` (NUMERIC 10,4)

#### 6. **lineage_events** (EXISTENTIAL)
Full audit trail of every data transformation.
- `id` (UUID, PK)
- `timestamp` (TIMESTAMP)
- `actor_type` (VARCHAR 20): system, claude, user
- `action` (VARCHAR 50): parsed, triaged, mapped, etc.
- `stage` (VARCHAR 50): parsing, triage, mapping, etc.
- `input_snapshot` (JSON)
- `output_snapshot` (JSON)
- `source_file_id` (UUID, FK)
- `confidence` (NUMERIC 5,4)
- `claude_reasoning` (TEXT)

#### 7. **line_items** (NEW)
Individual extracted financial line items with time series values.
- `id` (UUID, PK)
- `job_id` (UUID, FK)
- `file_id` (UUID, FK)
- `sheet_name` (VARCHAR 255): Source sheet name
- `row_index` (INT): Row number in Excel
- `original_label` (VARCHAR 500): Original label from Excel
- `canonical_name` (VARCHAR 100): Mapped canonical name
- `hierarchy_level` (INT 0-5): Indentation level
- `is_subtotal` (BOOL): Whether this is a subtotal row
- `is_formula` (BOOL): Whether this contains formulas
- `values` (JSON): Time series data `{"FY2023": 100, "FY2024": 120}`
- `confidence` (NUMERIC 5,4): Mapping confidence score
- `mapping_reasoning` (TEXT): Why this mapping was chosen
- `created_at` (TIMESTAMP)

## Using the Database in Code

### Import Models

```python
from src.db import Entity, File, ExtractionJob, LineageEvent, Taxonomy, EntityPattern, LineItem
from src.db import get_db, get_db_context
```

### FastAPI Endpoint (Dependency Injection)

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

@app.get("/jobs/{job_id}")
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ExtractionJob).where(ExtractionJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    return job
```

### Background Task (Context Manager)

```python
from src.db import get_db_context, ExtractionJob

async def run_extraction(job_id: str):
    async with get_db_context() as db:
        result = await db.execute(
            select(ExtractionJob).where(ExtractionJob.id == job_id)
        )
        job = result.scalar_one()

        # Update job status
        job.job_status = "processing"
        job.progress_percent = 50
        await db.commit()

        # ... extraction logic ...
```

### Query Taxonomy

```python
from src.db import get_db_context, Taxonomy
from sqlalchemy import select

async def get_income_statement_items():
    async with get_db_context() as db:
        result = await db.execute(
            select(Taxonomy).where(Taxonomy.category == "income_statement")
        )
        items = result.scalars().all()
        return items
```

### Create Lineage Event

```python
from src.db import get_db_context, LineageEvent
from uuid import uuid4

async def emit_lineage_event(file_id: str, stage: str, output_data: dict):
    async with get_db_context() as db:
        event = LineageEvent(
            id=uuid4(),
            actor_type="claude",
            actor_id="claude-sonnet-4-20250514",
            action="parsed",
            stage=stage,
            target_type="sheet",
            target_id=uuid4(),
            output_snapshot=output_data,
            source_file_id=file_id,
            confidence=0.95,
        )
        db.add(event)
        await db.commit()
```

## Migration Commands

### Create New Migration

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "description"

# Create empty migration
alembic revision -m "description"
```

### Apply Migrations

```bash
# Upgrade to latest
alembic upgrade head

# Upgrade by 1 version
alembic upgrade +1

# Upgrade to specific revision
alembic upgrade abc123
```

### Rollback Migrations

```bash
# Downgrade by 1 version
alembic downgrade -1

# Downgrade to specific revision
alembic downgrade abc123

# Downgrade all (WARNING: deletes all data)
alembic downgrade base
```

### View Migration Info

```bash
# Current version
alembic current

# Migration history
alembic history

# Show SQL without executing
alembic upgrade head --sql
```

## Configuration

Database URL is configured in [src/core/config.py](src/core/config.py):

```python
database_url: str = "postgresql://emi:emi_dev@localhost:5432/emi"
```

Override via environment variable:

```bash
export DATABASE_URL="postgresql://user:pass@host:port/dbname"
```

## Seeded Taxonomy Categories

The migration seeds 70+ canonical items across these categories:

- **income_statement** (15 items): revenue, cogs, gross_profit, ebitda, ebit, net_income, etc.
- **balance_sheet** (25 items): total_assets, cash, accounts_receivable, inventory, ppe, total_liabilities, total_equity, etc.
- **cash_flow** (7 items): operating_cash_flow, investing_cash_flow, financing_cash_flow, free_cash_flow, capex, etc.
- **working_capital** (6 items): working_capital, change_in_working_capital, DSO, DIO, DPO
- **debt_schedule** (6 items): debt_outstanding, principal_paid, interest_paid, debt_issuance, net_debt
- **metrics** (12 items): gross_margin_percent, ebitda_margin_percent, current_ratio, quick_ratio, debt_to_equity, ROA, ROE, etc.
- **depreciation_amortization** (2 items): accumulated_depreciation, net_ppe

Each item includes:
- Canonical name (unique identifier)
- Display name (human-readable)
- Aliases (for fuzzy matching: ["Sales", "Revenue", "Net Sales"])
- Definition (clear explanation)
- Typical sign (positive/negative)
- Parent (for hierarchy)

## Troubleshooting

### Connection Refused

```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Check logs
docker logs debtfund-postgres

# Restart
docker compose restart postgres
```

### Migration Conflicts

```bash
# Check current state
alembic current

# Show pending migrations
alembic history

# Force to specific version (careful!)
alembic stamp head
```

### Reset Database (Development Only)

```bash
# Downgrade all migrations
alembic downgrade base

# Re-apply all migrations
alembic upgrade head
```

## Performance Notes

- **Pattern Lookups**: <50ms (indexed on entity_id, original_label)
- **Lineage Queries**: <500ms (indexed on source_file_id, stage)
- **Taxonomy Retrieval**: <50ms (indexed on canonical_name, category)
- **Connection Pool**: 5 connections + 10 overflow

## Next Steps

1. ✅ Database schema created
2. ✅ Alembic migrations ready
3. ✅ Taxonomy seeded (70+ items)
4. 🔄 Update [src/api/main.py](src/api/main.py) to use database instead of in-memory dict
5. 🔄 Add lineage event emission to [src/extraction/orchestrator.py](src/extraction/orchestrator.py)
6. 🔄 Create database integration tests
7. 🔄 Add lineage completeness validation

## References

- SQLAlchemy 2.0 Docs: https://docs.sqlalchemy.org/en/20/
- Alembic Docs: https://alembic.sqlalchemy.org/
- asyncpg: https://magicstack.github.io/asyncpg/
- PostgreSQL 15: https://www.postgresql.org/docs/15/
