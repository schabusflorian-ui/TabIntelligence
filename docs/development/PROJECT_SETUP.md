# Project Structure & Quick Setup

## Directory Structure

```
excel-model-intelligence/
│
├── README.md                          # Project overview
├── CONTRIBUTING.md                    # Development workflow
├── docker-compose.yml                 # Local development services
├── pyproject.toml                     # Python dependencies
├── alembic.ini                        # Database migrations config
│
├── src/
│   ├── __init__.py
│   │
│   ├── api/                           # Agent 2: API & Infrastructure
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app
│   │   ├── routes/
│   │   │   ├── files.py               # Upload, retrieve
│   │   │   ├── jobs.py                # Job status, SSE
│   │   │   ├── extractions.py         # Results
│   │   │   ├── lineage.py             # Provenance queries
│   │   │   └── review.py              # Corrections
│   │   ├── middleware/
│   │   │   └── auth.py                # JWT auth
│   │   └── deps.py                    # Dependencies
│   │
│   ├── models/                        # Agent 1: Database
│   │   ├── __init__.py
│   │   ├── base.py                    # SQLAlchemy base
│   │   ├── entity.py
│   │   ├── file.py
│   │   ├── job.py
│   │   ├── extraction.py
│   │   ├── taxonomy.py
│   │   ├── pattern.py
│   │   └── lineage.py
│   │
│   ├── extraction/                    # Agent 3: Orchestrator
│   │   ├── __init__.py
│   │   ├── orchestrator.py            # Main pipeline
│   │   ├── stages/
│   │   │   ├── parsing.py             # Stage 1
│   │   │   ├── triage.py              # Stage 2
│   │   │   ├── structure.py           # Stage 3
│   │   │   ├── mapping.py             # Stage 4
│   │   │   └── verification.py        # Stage 5
│   │   └── claude_client.py           # Claude API wrapper
│   │
│   ├── guidelines/                    # Agent 4: Guidelines Manager
│   │   ├── __init__.py
│   │   ├── taxonomy.py                # Canonical taxonomy
│   │   ├── prompts/
│   │   │   ├── parsing.txt
│   │   │   ├── triage.txt
│   │   │   ├── structure.txt
│   │   │   ├── mapping.txt
│   │   │   └── verification.txt
│   │   ├── tiers.py                   # Tier definitions
│   │   └── patterns.py                # Entity pattern manager
│   │
│   ├── validation/                    # Agent 5: Validator
│   │   ├── __init__.py
│   │   ├── deterministic.py           # Rule-based checks
│   │   ├── guided.py                  # Claude reasoning
│   │   └── rules.py                   # Validation rules
│   │
│   ├── lineage/                       # Agent 6: Lineage
│   │   ├── __init__.py
│   │   ├── emitter.py                 # Event emission
│   │   ├── query.py                   # Provenance queries
│   │   └── validator.py               # Completeness check
│   │
│   ├── calibration/                   # Agent 7: Calibrator
│   │   ├── __init__.py
│   │   ├── calibrator.py              # Score calibration
│   │   └── metrics.py                 # ECE calculation
│   │
│   └── core/
│       ├── __init__.py
│       ├── config.py                  # Settings
│       └── storage.py                 # S3 client
│
├── migrations/                        # Alembic migrations
│   ├── env.py
│   └── versions/
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # Fixtures
│   ├── unit/
│   │   ├── test_taxonomy.py
│   │   ├── test_validation.py
│   │   └── test_lineage.py
│   ├── integration/
│   │   ├── test_extraction.py
│   │   └── test_api.py
│   └── fixtures/
│       └── sample_models/             # Test Excel files
│
├── scripts/
│   ├── poc_guided_extraction.py       # POC script
│   ├── seed_taxonomy.py               # Seed database
│   └── test_model_generator.py        # Generate test models
│
├── docs/
│   ├── architecture/
│   │   └── guided_pipeline.md
│   ├── prompts/
│   │   └── prompt_design.md
│   └── api/
│       └── openapi.yaml
│
└── status/
    ├── WEEKLY_STATUS.md
    ├── BLOCKERS.md
    └── COST_TRACKING.md
```

---

## docker-compose.yml

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: emi
      POSTGRES_PASSWORD: emi_dev
      POSTGRES_DB: emi
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U emi"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data

volumes:
  postgres_data:
  minio_data:
```

---

## pyproject.toml

```toml
[project]
name = "excel-model-intelligence"
version = "0.1.0"
description = "Guided hybrid extraction platform for Excel financial models"
requires-python = ">=3.11"

dependencies = [
    # API
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "python-multipart>=0.0.6",
    "sse-starlette>=1.8.0",
    
    # Database
    "sqlalchemy>=2.0.0",
    "alembic>=1.13.0",
    "asyncpg>=0.29.0",
    "psycopg2-binary>=2.9.0",
    
    # Claude
    "anthropic>=0.18.0",
    
    # Storage
    "boto3>=1.34.0",
    
    # Utils
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    
    # Excel (for validation/testing)
    "openpyxl>=3.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.26.0",
    "ruff>=0.1.0",
    "mypy>=1.8.0",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

## .env.example

```bash
# Database
DATABASE_URL=postgresql+asyncpg://emi:emi_dev@localhost:5432/emi

# Redis
REDIS_URL=redis://localhost:6379

# S3/MinIO
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=emi-files

# Claude
ANTHROPIC_API_KEY=your-api-key-here

# Auth
JWT_SECRET=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# App
DEBUG=true
LOG_LEVEL=INFO
```

---

## Quick Start Commands

```bash
# 1. Clone and setup
git clone <repo>
cd excel-model-intelligence
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# 2. Start services
docker-compose up -d

# 3. Python environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -e ".[dev]"

# 4. Run migrations
alembic upgrade head

# 5. Seed taxonomy
python scripts/seed_taxonomy.py

# 6. Start API
uvicorn src.api.main:app --reload

# 7. Test Claude POC
python scripts/poc_guided_extraction.py sample.xlsx

# 8. Run tests
pytest

# 9. Check health
curl http://localhost:8000/health
```

---

## First Migration

```python
# migrations/versions/001_initial.py
"""Initial schema

Revision ID: 001
Create Date: 2026-02-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '001'
down_revision = None

def upgrade():
    # Entities
    op.create_table(
        'entities',
        sa.Column('id', UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('industry', sa.String(100)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'))
    )
    
    # Files
    op.create_table(
        'files',
        sa.Column('id', UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('entity_id', UUID, sa.ForeignKey('entities.id')),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('s3_key', sa.String(500), nullable=False),
        sa.Column('file_hash', sa.String(64)),
        sa.Column('file_size_bytes', sa.BigInteger),
        sa.Column('status', sa.String(50), server_default='uploaded'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'))
    )
    
    # Jobs
    op.create_table(
        'jobs',
        sa.Column('id', UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('file_id', UUID, sa.ForeignKey('files.id')),
        sa.Column('status', sa.String(50), server_default='pending'),
        sa.Column('current_stage', sa.String(50)),
        sa.Column('progress_percent', sa.Integer, server_default='0'),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('error_message', sa.Text),
        sa.Column('tokens_used', sa.Integer),
        sa.Column('cost_usd', sa.Numeric(10, 4))
    )
    
    # Taxonomy
    op.create_table(
        'taxonomy',
        sa.Column('id', UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('canonical_name', sa.String(100), unique=True, nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('display_name', sa.String(255)),
        sa.Column('aliases', sa.ARRAY(sa.Text)),
        sa.Column('definition', sa.Text),
        sa.Column('typical_sign', sa.String(10)),
        sa.Column('parent_canonical', sa.String(100)),
        sa.Column('derivation', sa.String(255))
    )
    
    # Entity patterns
    op.create_table(
        'entity_patterns',
        sa.Column('id', UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('entity_id', UUID, sa.ForeignKey('entities.id')),
        sa.Column('original_label', sa.String(500), nullable=False),
        sa.Column('canonical_name', sa.String(100), nullable=False),
        sa.Column('confidence', sa.Numeric(5, 4), server_default='0.8'),
        sa.Column('occurrence_count', sa.Integer, server_default='1'),
        sa.Column('source', sa.String(50)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('last_seen', sa.DateTime(timezone=True), server_default=sa.text('NOW()'))
    )
    op.create_unique_constraint('uq_entity_label', 'entity_patterns', ['entity_id', 'original_label'])
    
    # Lineage events
    op.create_table(
        'lineage_events',
        sa.Column('id', UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('actor_type', sa.String(20), nullable=False),
        sa.Column('actor_id', sa.String(100), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('stage', sa.String(50), nullable=False),
        sa.Column('target_type', sa.String(50), nullable=False),
        sa.Column('target_id', UUID, nullable=False),
        sa.Column('input_snapshot', JSONB),
        sa.Column('output_snapshot', JSONB),
        sa.Column('source_file_id', UUID),
        sa.Column('source_sheet', sa.String(255)),
        sa.Column('source_cell', sa.String(20)),
        sa.Column('confidence', sa.Numeric(5, 4)),
        sa.Column('claude_reasoning', sa.Text)
    )
    op.create_index('idx_lineage_target', 'lineage_events', ['target_id'])
    op.create_index('idx_lineage_file', 'lineage_events', ['source_file_id'])

def downgrade():
    op.drop_table('lineage_events')
    op.drop_table('entity_patterns')
    op.drop_table('taxonomy')
    op.drop_table('jobs')
    op.drop_table('files')
    op.drop_table('entities')
```

---

## Week 1 Task Board

```
TO DO                    IN PROGRESS              DONE
─────────────────────────────────────────────────────────
[ ] Seed taxonomy        [ ] Core tables          [x] Repo created
[ ] S3 integration       [ ] API scaffold         [x] Docker setup
[ ] Job queue            [ ] Claude POC           
[ ] Stage 1 parsing                               
[ ] Stage 2 triage                                
[ ] E2E test                                      
```

---

*Ready to start. Let's build.*
