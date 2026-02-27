# Week 2 Parallelization Strategy
**Optimized Task Breakdown for Maximum Parallel Execution**

## Executive Summary

**Current Plan**: 6 agents in 3 sequential phases (~15-20 hours with dependencies)
**Optimized Plan**: 13 agents in 3 phases with maximum parallelization (~8-12 hours)

**Key Insight**: Many Week 2 tasks have been artificially bundled into large agents when they can be split into smaller, independent atomic tasks that run in parallel.

---

## Full Project Scope Review

### Agent Deliverables (90+ Total)

From [agent_kickoff_briefs_v3.md](../architecture/agent_kickoff_briefs_v3.md):

| Agent | Total Deliverables | Week 2 Scope | Status |
|-------|-------------------|--------------|--------|
| **1 (Database)** | 8 (D1.1-D1.8) | D1.1-D1.5 (5 deliverables) | TODO |
| **2 (API)** | 10 (D2.1-D2.10) | D2.3-D2.6 (4 deliverables) | D2.1-D2.2 ✅, D2.4 partial |
| **3 (Orchestrator)** | 10 (D3.1-D3.10) | None (Week 4+) | D3.1 ✅ (POC done) |
| **4 (Guidelines)** | 7 (D4.1-D4.7) | D4.2 (taxonomy) | TODO |
| **5 (Validator)** | — | None (Week 4+) | N/A |
| **6 (Lineage)** | — | Full system (EXISTENTIAL) | TODO |
| **7 (Calibrator)** | — | None (Week 6+) | N/A |
| **8 (Add-in)** | — | None (Week 9+) | N/A |
| **9 (Dashboard)** | — | None (Week 9+) | N/A |

**Week 2 Focus**: Agents 1, 2 (partial), 4 (taxonomy), 6 (lineage system)

---

## Current Week 2 Plan Analysis

### Phase 1: Parallel (3 agents)
1. **Database Schema** - Agent 1 work (models, migrations, session)
2. **Lineage System** - Agent 6 work (tracker, validation, integration)
3. **Taxonomy Data** - Agent 4 work (JSON creation, seed migration)

### Phase 2: Sequential (2 agents) - *Waits for Phase 1*
4. **API Integration** - Agent 2 work (replace in-memory with PostgreSQL)
5. **Test Refinement** - Fix 12 failing tests, increase coverage

### Phase 3: Final (1 agent) - *Waits for Phase 2*
6. **Integration & Documentation** - End-to-end test, docs

**Bottleneck**: Phases 2 and 3 wait unnecessarily. Many tasks don't actually depend on full Phase 1 completion.

---

## Dependency Analysis

### True Dependencies (Must be Sequential)

```
Database Models → API DB Integration
Database Models → Database Tests
Lineage Tables → Lineage DB Integration
Lineage Tracker → Orchestrator Integration
Taxonomy Table → Taxonomy Migration
```

### False Dependencies (Can Be Parallel)

```
❌ S3 Integration waiting for Database Models (no dependency!)
❌ Job Queue setup waiting for Database Models (no dependency!)
❌ Mock fixes waiting for Database work (no dependency!)
❌ Documentation waiting for everything (can be parallel!)
❌ Taxonomy JSON creation waiting for table (can be reversed!)
```

---

## Optimized Parallelization Strategy

### Phase 1: Foundation (7 Agents in Parallel) - ~4-6 hours

**No dependencies between these - all can run simultaneously**

| # | Agent | Task | Output | Independent? |
|---|-------|------|--------|--------------|
| **1A** | Database Models | Create all SQLAlchemy models (7 tables) | `src/db/models.py` | ✅ Yes |
| **1B** | Database Session | Create session management + dependency | `src/db/session.py` | ✅ Yes |
| **1C** | Alembic Setup | Initialize Alembic, create initial migration | `alembic/` folder | ✅ Yes |
| **2A** | S3 Integration | MinIO client, upload/download utilities | `src/storage/s3.py` | ✅ Yes |
| **2B** | Job Queue | Redis + Celery setup for background jobs | `src/jobs/` folder | ✅ Yes |
| **4A** | Taxonomy JSON | Create 100+ canonical line items | `data/taxonomy.json` | ✅ Yes |
| **5A** | Mock Fixes | Fix 12 failing tests (mock Claude client) | 26/26 tests passing | ✅ Yes |

**Why This Works:**
- Database models don't need session management to be written
- Alembic can be initialized without models (migration created after models exist)
- S3 integration has zero database dependency
- Job queue only needs Redis (already running)
- Taxonomy JSON is just data creation (doesn't need table yet)
- Mock fixes are isolated to test code

**Execution**:
```bash
# Launch all 7 agents in parallel
claude agent 1A  # Database models
claude agent 1B  # Session management
claude agent 1C  # Alembic setup
claude agent 2A  # S3 integration
claude agent 2B  # Job queue
claude agent 4A  # Taxonomy JSON
claude agent 5A  # Mock fixes
```

**Exit Criteria**: All 7 agents complete successfully

---

### Phase 2: Integration (4 Agents in Parallel) - ~3-5 hours

**Depends on: Phase 1 complete (models exist, Alembic ready)**

| # | Agent | Task | Depends On | Can Parallel? |
|---|-------|------|------------|---------------|
| **1D** | Database Migration | Apply migration, verify tables created | 1A, 1C | With 6A |
| **4B** | Taxonomy Migration | Create + apply taxonomy seed migration | 4A, 1D | With 6A |
| **6A** | Lineage System Core | LineageTracker class, event emission | 1A (lineage table) | With 1D, 4B |
| **2C** | API Database Integration | Replace in-memory job dict with PostgreSQL | 1A, 1B, 1D | After 1D done |

**Why This Works:**
- 1D (migration), 4B (taxonomy seed), and 6A (lineage tracker) all just need models to exist
- These 3 can run in parallel (different parts of system)
- 2C (API integration) needs database running, so waits for 1D

**Execution**:
```bash
# Wait for Phase 1 to complete, then launch:
claude agent 1D & claude agent 4B & claude agent 6A  # Parallel
# Wait for 1D to finish (database running)
claude agent 2C  # Sequential after 1D
```

**Exit Criteria**: Database running with data, API uses PostgreSQL, lineage tracker exists

---

### Phase 3: Completion (2 Agents Sequential) - ~2-3 hours

**Depends on: Phase 2 complete (everything integrated)**

| # | Agent | Task | Depends On |
|---|-------|------|------------|
| **6B** | Lineage Integration | Add lineage to orchestrator, validate completeness | 6A, 2C |
| **INT** | Integration & Docs | End-to-end tests, documentation, Week 2 summary | 6B |

**Why Sequential**:
- 6B needs lineage tracker (6A) and updated API (2C) to integrate
- INT needs everything working to test end-to-end

**Execution**:
```bash
claude agent 6B  # Lineage orchestrator integration
# After 6B completes
claude agent INT  # Final integration and docs
```

**Exit Criteria**: All lineage events emit, end-to-end test passes, Week 2 docs complete

---

## Detailed Task Breakdown

### Phase 1A: Database Models (~1 hour)

**Files to Create**:
- `src/db/models.py` (400-500 lines)

**Tables** (from Agent 1 brief D1.1-D1.5):
1. `entities` - Companies/assets being tracked
2. `entity_patterns` - Learned mappings per entity
3. `files` - Uploaded Excel files (S3 metadata)
4. `extraction_jobs` - Job status, results, costs
5. `lineage_events` - Full audit trail (EXISTENTIAL)
6. `taxonomy` - Canonical line items
7. `line_items` - Extracted values (for Week 3+)

**SQLAlchemy Models**:
```python
from sqlalchemy import Column, String, Integer, UUID, TIMESTAMP, JSON, DECIMAL
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
import uuid

Base = declarative_base()

class Entity(Base):
    __tablename__ = 'entities'
    entity_id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_name = Column(String(255), nullable=False)
    # ... more fields

# ... 6 more models
```

**Success Criteria**:
- [ ] 7 table classes created
- [ ] All relationships defined
- [ ] UUIDs used for all IDs
- [ ] JSON columns for flexible data
- [ ] No migration yet (just models)

---

### Phase 1B: Database Session (~30 minutes)

**Files to Create**:
- `src/db/session.py` (50-100 lines)
- `src/db/__init__.py`

**Components**:
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.core.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**Success Criteria**:
- [ ] Engine created with config
- [ ] SessionLocal factory created
- [ ] `get_db()` dependency for FastAPI
- [ ] Connection pooling configured

---

### Phase 1C: Alembic Setup (~30 minutes)

**Commands**:
```bash
alembic init alembic
```

**Files to Create/Modify**:
- `alembic/env.py` - Configure to use our models
- `alembic.ini` - Database URL configuration

**Migration Creation** (after models exist):
```bash
alembic revision -m "Initial schema: 7 core tables"
```

**Success Criteria**:
- [ ] Alembic initialized
- [ ] `env.py` configured with Base
- [ ] `alembic.ini` uses settings.database_url
- [ ] Initial migration file created (empty for now)

---

### Phase 1D: S3 Integration (~1-2 hours)

**Files to Create**:
- `src/storage/s3.py` (150-200 lines)
- `src/storage/__init__.py`

**Components**:
```python
import boto3
from src.core.config import settings
from src.core.logging import api_logger as logger

class S3Client:
    """MinIO/S3 client for file storage."""

    def __init__(self):
        self.client = boto3.client(
            's3',
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key
        )

    def upload_file(self, file_bytes: bytes, file_id: str, filename: str) -> str:
        """Upload file to S3, return S3 key."""
        s3_key = f"uploads/{file_id}/{filename}"
        self.client.put_object(
            Bucket=settings.s3_bucket,
            Key=s3_key,
            Body=file_bytes
        )
        logger.info(f"Uploaded file to S3: {s3_key}")
        return s3_key

    def download_file(self, s3_key: str) -> bytes:
        """Download file from S3."""
        response = self.client.get_object(
            Bucket=settings.s3_bucket,
            Key=s3_key
        )
        return response['Body'].read()
```

**Success Criteria**:
- [ ] S3Client class created
- [ ] `upload_file()` working with MinIO
- [ ] `download_file()` working
- [ ] Bucket creation if not exists
- [ ] Error handling for S3 failures
- [ ] Tests for S3 operations

---

### Phase 1E: Job Queue Setup (~1-2 hours)

**Files to Create**:
- `src/jobs/celery_app.py` (100-150 lines)
- `src/jobs/tasks.py` (50-100 lines)
- `src/jobs/__init__.py`

**Components**:
```python
from celery import Celery
from src.core.config import settings

celery_app = Celery(
    'debtfund',
    broker=settings.redis_url,
    backend=settings.redis_url
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

@celery_app.task
def run_extraction_task(job_id: str, file_bytes: bytes, entity_id: str = None):
    """Background task for extraction pipeline."""
    from src.extraction.orchestrator import extract
    result = await extract(file_bytes, job_id, entity_id)
    return result
```

**Update** `pyproject.toml`:
```toml
dependencies = [
    # ... existing
    "celery[redis]>=5.3.0",
]
```

**Success Criteria**:
- [ ] Celery app configured with Redis
- [ ] `run_extraction_task` defined
- [ ] Worker can be started: `celery -A src.jobs.celery_app worker`
- [ ] Task execution logged

---

### Phase 1F: Taxonomy JSON (~2-3 hours)

**Files to Create**:
- `data/taxonomy.json` (100+ line items, ~500-800 lines JSON)

**Structure**:
```json
{
  "version": "1.0.0",
  "categories": {
    "income_statement": [
      {
        "canonical_name": "revenue",
        "display_name": "Revenue",
        "aliases": ["Sales", "Net Sales", "Turnover", "Total Revenue", "Net Revenue"],
        "definition": "Total income from primary business activities",
        "typical_sign": "positive",
        "parent": null,
        "category": "income_statement"
      },
      {
        "canonical_name": "cogs",
        "display_name": "Cost of Goods Sold",
        "aliases": ["Cost of Sales", "COS", "Direct Costs", "Cost of Revenue"],
        "definition": "Direct costs attributable to goods/services sold",
        "typical_sign": "positive",
        "parent": null
      },
      {
        "canonical_name": "gross_profit",
        "display_name": "Gross Profit",
        "aliases": ["Gross Margin", "GP"],
        "definition": "Revenue minus COGS",
        "typical_sign": "positive",
        "derivation": "revenue - cogs"
      }
      // ... 22 more income statement items
    ],
    "balance_sheet": [
      // ... 25+ items
    ],
    "cash_flow": [
      // ... 20+ items
    ],
    "debt_schedule": [
      // ... 15+ items
    ],
    "other": [
      // ... 15+ items
    ]
  }
}
```

**Categories to Cover** (from Agent 4 brief):
1. **Income Statement** (25+ items): revenue, cogs, gross_profit, opex, sg&a, r&d, ebitda, depreciation, amortization, ebit, interest_expense, interest_income, ebt, taxes, net_income, etc.
2. **Balance Sheet** (25+ items): cash, accounts_receivable, inventory, current_assets, ppe, intangibles, total_assets, accounts_payable, current_liabilities, long_term_debt, equity, retained_earnings, etc.
3. **Cash Flow** (20+ items): operating_cf, investing_cf, financing_cf, capex, dividends, etc.
4. **Debt Schedule** (15+ items): principal, interest, debt_balance, maturity, etc.
5. **Other** (15+ items): ratios, metrics, KPIs

**Success Criteria**:
- [ ] 100+ unique canonical items
- [ ] Each item has 2-5 aliases minimum
- [ ] Definitions clear and concise
- [ ] Hierarchy defined (parent relationships)
- [ ] Derivation formulas for calculated items
- [ ] JSON validates

---

### Phase 1G: Mock Fixes (~2-3 hours)

**Problem**: 12/26 tests failing due to mock not patching module-level Claude client

**Root Cause**:
```python
# In src/extraction/orchestrator.py
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))  # Module-level

# Mock in tests doesn't patch this
```

**Solution Options**:

**Option 1: Refactor to Dependency Injection** (Recommended)
```python
# orchestrator.py
async def extract(file_bytes: bytes, file_id: str, entity_id: str = None,
                  claude_client=None):
    """Extract with optional client injection for testing."""
    if claude_client is None:
        claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Use claude_client instead of global client
```

**Option 2: Mock at Module Import Level**
```python
# conftest.py
@pytest.fixture(autouse=True)
def mock_anthropic_module(monkeypatch, mock_claude_client):
    """Patch anthropic.Anthropic globally."""
    monkeypatch.setattr("anthropic.Anthropic", lambda api_key: mock_claude_client)
```

**Files to Update**:
- `src/extraction/orchestrator.py` - Add client parameter
- `tests/conftest.py` - Improve mock fixtures
- `tests/unit/test_orchestrator.py` - Pass mock client
- `tests/integration/test_api_endpoints.py` - Update for new signature

**Success Criteria**:
- [ ] All 26/26 tests passing
- [ ] No real Claude API calls during tests
- [ ] Mock responses realistic
- [ ] Coverage > 70%

---

### Phase 2A: Database Migration (~30 minutes)

**Depends On**: Phase 1A (models), 1C (Alembic)

**Commands**:
```bash
# Update migration with actual schema
alembic revision --autogenerate -m "Initial schema: 7 core tables"

# Apply migration
alembic upgrade head

# Verify tables created
psql $DATABASE_URL -c "\dt"
```

**Success Criteria**:
- [ ] Migration file has CREATE TABLE statements
- [ ] All 7 tables created in database
- [ ] Primary keys, foreign keys, indexes correct
- [ ] UUIDs working
- [ ] No errors on `alembic upgrade head`

---

### Phase 2B: Taxonomy Migration (~30 minutes)

**Depends On**: Phase 1F (taxonomy JSON), 2A (database running)

**Files to Create**:
- `alembic/versions/XXXX_seed_taxonomy.py`

**Migration Code**:
```python
"""Seed canonical taxonomy

Revision ID: XXXX
Revises: YYYY
Create Date: 2026-02-24
"""
from alembic import op
import json
from pathlib import Path

def upgrade():
    # Load taxonomy JSON
    taxonomy_path = Path(__file__).parent.parent.parent / 'data' / 'taxonomy.json'
    with open(taxonomy_path) as f:
        taxonomy = json.load(f)

    # Insert into taxonomy table
    conn = op.get_bind()
    for category, items in taxonomy['categories'].items():
        for item in items:
            conn.execute(
                "INSERT INTO taxonomy (canonical_name, display_name, category, aliases, definition, typical_sign, parent) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (item['canonical_name'], item['display_name'], category,
                 item['aliases'], item['definition'], item['typical_sign'], item.get('parent'))
            )

def downgrade():
    op.execute("DELETE FROM taxonomy")
```

**Commands**:
```bash
alembic revision -m "Seed canonical taxonomy"
# Edit migration file with above code
alembic upgrade head
```

**Success Criteria**:
- [ ] Migration created
- [ ] 100+ rows inserted into taxonomy table
- [ ] `SELECT * FROM taxonomy` shows all items
- [ ] Downgrade removes seed data

---

### Phase 2C: Lineage System Core (~2-3 hours)

**Depends On**: Phase 2A (lineage_events table exists)

**Files to Create**:
- `src/agents/agent_06_lineage.py` (200-300 lines)
- `src/agents/__init__.py`

**Components**:
```python
"""Agent 6: Lineage & Provenance Tracker - EXISTENTIAL"""
import logging
import uuid
from datetime import datetime
from src.db.models import LineageEvent
from src.db.session import get_db
from src.core.exceptions import LineageIncompleteError

logger = logging.getLogger("debtfund.lineage")

class LineageTracker:
    """Centralized lineage event emission."""

    def __init__(self, job_id: uuid.UUID):
        self.job_id = job_id
        self.events = []

    def emit(self, event_type: str, stage: int, input_lineage_id: uuid.UUID = None,
             metadata: dict = None) -> uuid.UUID:
        """Emit a lineage event."""
        output_lineage_id = uuid.uuid4()

        event = LineageEvent(
            job_id=self.job_id,
            event_type=event_type,
            stage=stage,
            input_lineage_id=input_lineage_id,
            output_lineage_id=output_lineage_id,
            metadata=metadata or {},
            timestamp=datetime.utcnow()
        )

        self.events.append(event)
        logger.info(f"Lineage event: {event_type} (stage {stage}) -> {output_lineage_id}")
        return output_lineage_id

    def save_to_db(self, db_session):
        """Persist all events to database."""
        for event in self.events:
            db_session.add(event)
        db_session.commit()
        logger.info(f"Saved {len(self.events)} lineage events for job {self.job_id}")

    def validate_completeness(self, required_stages: set = {1, 2, 3}):
        """Ensure every required stage emitted lineage - EXISTENTIAL check."""
        emitted_stages = {event.stage for event in self.events}
        missing_stages = required_stages - emitted_stages

        if missing_stages:
            raise LineageIncompleteError(
                missing_events=list(missing_stages),
                job_id=str(self.job_id)
            )

        logger.info("Lineage completeness check: PASSED")
        return True
```

**Tests to Create**:
- `tests/unit/test_lineage.py` (100-150 lines)

**Success Criteria**:
- [ ] LineageTracker class created
- [ ] `emit()` method works
- [ ] `validate_completeness()` raises error on missing stages
- [ ] `save_to_db()` persists events
- [ ] 10+ tests for lineage system
- [ ] All lineage tests passing

---

### Phase 2D: API Database Integration (~2-3 hours)

**Depends On**: Phase 2A (database running), 1B (session management)

**Files to Update**:
- `src/api/main.py` - Replace in-memory dict with database

**Current Code**:
```python
# In-memory store for Week 1 (replace with DB later)
jobs = {}

@app.post("/api/v1/files/upload")
async def upload_file(file: UploadFile, background_tasks: BackgroundTasks, entity_id: Optional[str] = None):
    job_id = str(uuid.uuid4())

    # Create job in memory
    jobs[job_id] = JobStatus(job_id=job_id, file_id=file_id, status="pending")

    return {"job_id": job_id, "status": "processing"}

@app.get("/api/v1/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return jobs[job_id]
```

**Updated Code**:
```python
from src.db.session import get_db
from src.db.models import File, ExtractionJob
from src.storage.s3 import S3Client
from sqlalchemy.orm import Session

s3_client = S3Client()

@app.post("/api/v1/files/upload")
async def upload_file(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    entity_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    file_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    file_bytes = await file.read()

    # Upload to S3
    s3_key = s3_client.upload_file(file_bytes, file_id, file.filename)

    # Save file metadata to database
    db_file = File(
        file_id=file_id,
        filename=file.filename,
        s3_key=s3_key,
        file_size=len(file_bytes),
        user_id=None  # TODO: Add auth
    )
    db.add(db_file)

    # Create extraction job in database
    db_job = ExtractionJob(
        job_id=job_id,
        file_id=file_id,
        status="pending",
        current_stage=0,
        progress_percent=0
    )
    db.add(db_job)
    db.commit()

    # Start extraction in background
    background_tasks.add_task(run_extraction, job_id, file_id, entity_id, db)

    return {"file_id": file_id, "job_id": job_id, "status": "processing"}

@app.get("/api/v1/jobs/{job_id}")
async def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(ExtractionJob).filter(ExtractionJob.job_id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return job
```

**Success Criteria**:
- [ ] In-memory `jobs` dict removed
- [ ] File upload saves to S3 and database
- [ ] Job status queries database
- [ ] Background task updates job in database
- [ ] All API integration tests passing

---

### Phase 3A: Lineage Orchestrator Integration (~1-2 hours)

**Depends On**: Phase 2C (LineageTracker), 2D (API using database)

**Files to Update**:
- `src/extraction/orchestrator.py`

**Current Code**:
```python
async def orchestrator_stages_1_to_3(file_bytes, filename):
    """POC orchestrator - no lineage."""

    parsing_result = await stage_1_parsing(file_bytes)
    triage_result = await stage_2_triage(parsing_result, filename)
    mapping_result = await stage_3_mapping(triage_result, filename)

    return {
        "parsing": parsing_result,
        "triage": triage_result,
        "mapping": mapping_result
    }
```

**Updated Code**:
```python
from src.agents.agent_06_lineage import LineageTracker
from src.db.session import get_db

async def orchestrator_stages_1_to_3(file_bytes, filename, job_id):
    """Enhanced orchestrator with lineage tracking."""

    # Initialize lineage tracker
    lineage = LineageTracker(job_id=job_id)

    # Stage 1: Parsing
    logger.info("Stage 1: Parsing started")
    parsing_result = await stage_1_parsing(file_bytes)
    parsing_lineage_id = lineage.emit(
        event_type="parse",
        stage=1,
        metadata={"sheets_found": len(parsing_result.get("sheets", []))}
    )

    # Stage 2: Triage
    logger.info("Stage 2: Triage started")
    triage_result = await stage_2_triage(parsing_result, filename)
    triage_lineage_id = lineage.emit(
        event_type="triage",
        stage=2,
        input_lineage_id=parsing_lineage_id,
        metadata={"sheets_triaged": len(triage_result.get("sheets", []))}
    )

    # Stage 3: Mapping
    logger.info("Stage 3: Mapping started")
    mapping_result = await stage_3_mapping(triage_result, filename)
    mapping_lineage_id = lineage.emit(
        event_type="map",
        stage=3,
        input_lineage_id=triage_lineage_id,
        metadata={"items_mapped": len(mapping_result.get("line_items", []))}
    )

    # EXISTENTIAL: Validate lineage completeness
    lineage.validate_completeness(required_stages={1, 2, 3})

    # Save lineage to database
    db = next(get_db())
    lineage.save_to_db(db)
    logger.info(f"Lineage saved for job {job_id}")

    return {
        "parsing": parsing_result,
        "triage": triage_result,
        "mapping": mapping_result,
        "lineage_id": mapping_lineage_id  # Final output lineage ID
    }
```

**Success Criteria**:
- [ ] Lineage events emitted at each stage
- [ ] Lineage chain integrity (stage 1 → 2 → 3)
- [ ] Completeness validation working
- [ ] Events saved to database
- [ ] Integration test: upload → extract → verify lineage

---

### Phase 3B: Integration & Documentation (~2-3 hours)

**Depends On**: Phase 3A (everything working)

**Tasks**:

1. **End-to-End Integration Test** (~1 hour)
   - Create `tests/integration/test_end_to_end.py`
   - Test: Upload file → Extract → Verify lineage saved → Query job status
   - Verify all components work together

2. **Documentation Updates** (~1-2 hours)
   - Create `docs/development/TESTING_MANIFEST.md`
   - Create `docs/architecture/DATABASE_SCHEMA.md` with ER diagram
   - Create `docs/architecture/LINEAGE_GUIDE.md`
   - Update `CHANGELOG.md` with Week 2 additions
   - Create `docs/WEEK2_COMPLETION_SUMMARY.md`

3. **Coverage Report**
   ```bash
   pytest -v --cov=src --cov-report=term-missing --cov-report=html
   # Target: 80% coverage
   ```

**Success Criteria**:
- [ ] End-to-end test passes
- [ ] Coverage ≥ 80%
- [ ] All Week 2 documentation complete
- [ ] CHANGELOG updated
- [ ] Week 2 summary created

---

## Execution Timeline

### Optimized: 8-12 hours (vs. Current: 15-20 hours)

| Phase | Agents | Parallel | Duration | Cumulative |
|-------|--------|----------|----------|------------|
| **Phase 1** | 7 | ✅ Yes | 4-6 hours | 4-6 hours |
| **Phase 2** | 4 | ⚠️ Partial (3 parallel, 1 sequential) | 3-5 hours | 7-11 hours |
| **Phase 3** | 2 | ❌ Sequential | 2-3 hours | 9-14 hours |

**Time Savings**: 40-50% reduction by maximizing parallelization

---

## Agent Launch Commands

### Phase 1 (Launch All 7 Simultaneously)

```bash
# Open 7 terminal windows/tabs

# Terminal 1
claude chat --new --prompt "You are Agent 1A: Database Models. Create src/db/models.py with 7 SQLAlchemy tables: entities, entity_patterns, files, extraction_jobs, lineage_events, taxonomy, line_items. Use UUIDs, JSON columns, proper relationships. Reference: docs/architecture/agent_kickoff_briefs_v3.md Agent 1 D1.1-D1.5"

# Terminal 2
claude chat --new --prompt "You are Agent 1B: Database Session. Create src/db/session.py with SQLAlchemy engine, SessionLocal factory, and get_db() FastAPI dependency. Use settings from src/core/config.py"

# Terminal 3
claude chat --new --prompt "You are Agent 1C: Alembic Setup. Initialize Alembic, configure env.py to use models from src/db/models.py, create initial migration structure"

# Terminal 4
claude chat --new --prompt "You are Agent 2A: S3 Integration. Create src/storage/s3.py with S3Client class for MinIO. Implement upload_file() and download_file(). Add boto3 to dependencies. Use settings from src/core/config.py"

# Terminal 5
claude chat --new --prompt "You are Agent 2B: Job Queue. Create src/jobs/celery_app.py and tasks.py. Configure Celery with Redis backend. Add celery[redis] to dependencies. Create run_extraction_task()"

# Terminal 6
claude chat --new --prompt "You are Agent 4A: Taxonomy JSON. Create data/taxonomy.json with 100+ canonical line items across 5 categories: income_statement (25+), balance_sheet (25+), cash_flow (20+), debt_schedule (15+), other (15+). Each item needs: canonical_name, display_name, aliases (2-5), definition, typical_sign, parent, derivation. Reference: docs/architecture/agent_kickoff_briefs_v3.md Agent 4 D4.2"

# Terminal 7
claude chat --new --prompt "You are Agent 5A: Mock Fixes. Fix 12 failing tests in tests/unit/test_orchestrator.py and tests/integration/test_api_endpoints.py. Problem: mock not patching module-level Claude client. Solution: Refactor orchestrator.py to use dependency injection OR patch at import level. Get all 26/26 tests passing"
```

### Phase 2 (After Phase 1 Complete)

```bash
# Wait for all Phase 1 agents to complete

# Terminal 8, 9, 10 (parallel)
claude chat --new --prompt "You are Agent 1D: Database Migration. Fill in the Alembic migration with actual schema from models, run 'alembic upgrade head', verify all 7 tables created in PostgreSQL"

claude chat --new --prompt "You are Agent 4B: Taxonomy Migration. Create Alembic migration to seed taxonomy table from data/taxonomy.json. Insert 100+ rows. Test upgrade and downgrade"

claude chat --new --prompt "You are Agent 6A: Lineage System Core. Create src/agents/agent_06_lineage.py with LineageTracker class. Implement emit(), validate_completeness(), save_to_db(). Create tests/unit/test_lineage.py with 10+ tests. Reference: docs/architecture/agent_kickoff_briefs_v3.md Agent 6"

# Terminal 11 (after 1D completes)
claude chat --new --prompt "You are Agent 2C: API Database Integration. Update src/api/main.py to replace in-memory jobs dict with PostgreSQL. Use File and ExtractionJob models. Integrate S3Client for file uploads. Use database session dependency"
```

### Phase 3 (After Phase 2 Complete)

```bash
# Terminal 12 (after 2C completes)
claude chat --new --prompt "You are Agent 6B: Lineage Integration. Update src/extraction/orchestrator.py to use LineageTracker. Emit events at each stage (parse, triage, map). Validate completeness. Save events to database. Test end-to-end"

# Terminal 13 (after 6B completes)
claude chat --new --prompt "You are Agent INT: Integration & Documentation. Create tests/integration/test_end_to_end.py. Run full coverage report (target 80%). Create docs: TESTING_MANIFEST.md, DATABASE_SCHEMA.md, LINEAGE_GUIDE.md. Update CHANGELOG.md. Create WEEK2_COMPLETION_SUMMARY.md"
```

---

## Risk Mitigation

### Potential Issues

| Risk | Mitigation |
|------|------------|
| Agents complete at different rates | Use checkpoints: verify Phase 1 complete before Phase 2 |
| Database migration conflicts | 1D must complete before 4B and 2C |
| S3 integration breaks tests | Mock S3Client in tests |
| Celery adds complexity | Keep Celery optional for Week 2 (use BackgroundTasks fallback) |
| Taxonomy JSON incomplete | Provide structured template with 25 example items |
| Mock fixes break existing tests | Run full test suite after each change |

### Checkpoints

**After Phase 1**:
```bash
# Verify all components exist
ls src/db/models.py src/db/session.py alembic/env.py src/storage/s3.py src/jobs/celery_app.py data/taxonomy.json
pytest -v  # Should show 26/26 passing
```

**After Phase 2**:
```bash
# Verify database running
psql $DATABASE_URL -c "SELECT COUNT(*) FROM taxonomy"  # Should show 100+
pytest tests/unit/test_lineage.py -v  # Should pass
```

**After Phase 3**:
```bash
# Verify end-to-end
pytest tests/integration/test_end_to_end.py -v  # Should pass
pytest --cov=src --cov-report=term  # Should show ≥80%
```

---

## Success Metrics

| Metric | Target | Actual (To Fill) |
|--------|--------|------------------|
| Time to complete Week 2 | 8-12 hours | ___ hours |
| Parallel agents in Phase 1 | 7 | ___ |
| Tests passing | 26/26 + new tests | ___/___ |
| Coverage | ≥ 80% | ___% |
| Database tables created | 7 | ___ |
| Taxonomy items seeded | 100+ | ___ |
| Lineage events emitted | 3 per job | ___ |
| Documentation files created | 5 | ___ |

---

## Conclusion

**Key Improvements Over Original Plan**:

1. **Phase 1 Parallelization**: 7 agents instead of 3 (133% increase)
2. **Eliminated False Dependencies**: S3, job queue, taxonomy JSON, mock fixes don't wait for database
3. **Granular Task Breakdown**: Each agent has 1 clear atomic task
4. **Time Reduction**: ~40-50% faster by removing sequential bottlenecks
5. **Clear Exit Criteria**: Each phase has verification steps

**Next Steps**:
1. Review this strategy
2. Launch Phase 1 (all 7 agents in parallel)
3. Monitor progress, verify completion
4. Proceed to Phase 2
5. Complete with Phase 3 integration

**Estimated Completion**: Week 2 can be done in 2-3 focused work sessions instead of 5-6 sessions.

---

*Parallelization Strategy - Created February 24, 2026*
