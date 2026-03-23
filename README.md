# TabIntelligence - Excel Model Intelligence Platform

**Guided Hybrid Extraction Platform for Excel Financial Models**

Extract structured financial data from Excel spreadsheets using Claude AI with full lineage tracking.

---

## Overview

Transforms messy Excel financial models into structured, queryable data with complete provenance tracking. It uses Claude AI guided by domain knowledge to parse, classify, and map financial line items to a canonical taxonomy.

### Key Capabilities

- **5-Stage Extraction Pipeline**: Parse → Triage → Map → Validate → Enhanced Map
- **Claude AI Integration**: Domain-specific prompts with confidence-scored mappings
- **100% Lineage Tracking**: Every data point traceable to source cell
- **Canonical Taxonomy**: 350+ items across 6 categories with alias matching
- **Entity Pattern Learning**: Corrections feed back into future extractions
- **Quality Scoring**: Composite A-F grades with validation feedback loop
- **Analytics API**: Cross-entity comparison, portfolio aggregation, trend analysis
- **50 REST Endpoints**: Full CRUD, corrections, analytics, admin

### Architecture

```
Excel File
    │
    ▼
┌──────────────────────────────────────────────────────┐
│          GUIDED EXTRACTION PIPELINE (5 Stages)       │
│                                                      │
│  ┌─────────┐  ┌─────────┐  ┌──────────┐            │
│  │ 1.Parse │→ │2.Triage │→ │ 3.Map    │→           │
│  │(Claude) │  │(Claude) │  │ (Claude) │            │
│  └─────────┘  └─────────┘  └──────────┘            │
│                                                      │
│  ┌──────────┐  ┌──────────────┐                     │
│  │4.Validate│→ │5.Enhanced Map│                     │
│  │(Claude+) │  │  (Claude)    │                     │
│  └──────────┘  └──────────────┘                     │
│                                                      │
│  Guided by: Taxonomy · Entity Patterns · Prompts    │
│  Tracked by: Lineage system (100% provenance)       │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────┐
│ Structured Data  │
│ + Lineage        │
│ + Quality Score  │
│ + Confidence     │
└──────────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker Desktop (for PostgreSQL, Redis, MinIO)
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com))

### 1. Clone & Install

```bash
git clone <repository-url>
cd DebtFund

python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY at minimum
```

### 3. Start Infrastructure

```bash
docker-compose up -d          # PostgreSQL, Redis, MinIO, Jaeger
docker-compose ps             # Verify all healthy
```

### 4. Run Database Migrations

```bash
alembic upgrade head
```

### 5. Start API Server

```bash
uvicorn src.api.main:app --reload
```

Visit http://localhost:8000 for the web UI, or http://localhost:8000/docs for the OpenAPI explorer.

### 6. Upload & Extract

```bash
# Upload an Excel file
curl -X POST http://localhost:8000/api/v1/files/upload \
  -H "X-API-Key: your-api-key" \
  -F "file=@your-model.xlsx" \
  -F "entity_name=Acme Corp"

# Check job status
curl http://localhost:8000/api/v1/jobs/{job_id} \
  -H "X-API-Key: your-api-key"

# Export results
curl http://localhost:8000/api/v1/jobs/{job_id}/export?format=json \
  -H "X-API-Key: your-api-key"
```

---

## API Endpoints

### Core Workflows

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/files/upload` | Upload Excel file for extraction |
| `GET` | `/api/v1/jobs/{id}` | Check extraction status |
| `GET` | `/api/v1/jobs/{id}/export` | Export results (JSON/CSV) |
| `POST` | `/api/v1/jobs/{id}/corrections/apply` | Apply corrections retroactively |
| `GET` | `/api/v1/analytics/entity/{id}/financials` | Query financial data |
| `GET` | `/api/v1/analytics/compare` | Cross-entity comparison |

### Full Endpoint Map (50 endpoints)

- **Health** (6): Liveness, readiness, database health, circuit breaker, metrics, stale jobs
- **Files** (3): Upload, list, get metadata
- **Jobs** (9): List, status, export, retry, review, lineage, diff, item-lineage
- **Entities** (5): CRUD + detail with pattern/file counts
- **Taxonomy** (5): List, search, stats, hierarchy, get item
- **Corrections** (11): Submit, apply, preview, undo, bulk, history, patterns, aliases
- **Analytics** (7): Financials, compare, portfolio, trends, coverage, costs, facts
- **DLQ Admin** (4): List, detail, replay, delete

See `/docs` on a running instance for full OpenAPI documentation.

---

## Demo & Product Documentation

The `docs/demo/` directory contains a comprehensive documentation package for sharing with potential users:

| Document | Format | Description |
|----------|--------|-------------|
| [Product Overview](docs/demo/product-overview.html) | HTML | Self-contained product pitch — open in any browser |
| [Architecture Diagrams](docs/demo/architecture-diagrams.md) | Mermaid | System architecture, pipeline, ER diagram, quality scoring, taxonomy |
| [Data Flow Diagrams](docs/demo/data-flow-diagrams.md) | Mermaid | Data lifecycle, entity learning loop, security flow, deployment |
| [Feature Catalog](docs/demo/feature-catalog.md) | Markdown | Features organized by persona (analyst, PM, data team) + full API reference |
| [Roadmap](docs/demo/roadmap.md) | Mermaid Gantt | Product vision: MVP → Phase 4 (2025–2027) |
| [Demo Walkthrough](docs/demo/demo-walkthrough.md) | Markdown | 20-minute guided demo script with talking points |

**Quick start:** Open `docs/demo/product-overview.html` in a browser for the flagship overview.

---

## Development

### Project Structure

```
DebtFund/
├── src/
│   ├── api/               # FastAPI routers (8 routers, 50 endpoints)
│   ├── auth/              # API key authentication
│   ├── core/              # Config, logging, exceptions
│   ├── db/                # SQLAlchemy models, CRUD, migrations
│   ├── extraction/        # 5-stage pipeline + orchestrator
│   │   ├── stages/        # ParsingStage, TriageStage, MappingStage,
│   │   │                  #   ValidationStage, EnhancedMappingStage
│   │   ├── prompts/       # Claude prompt templates
│   │   └── orchestrator.py
│   ├── jobs/              # Celery tasks + DLQ
│   ├── lineage/           # Lineage tracker + cross-extraction differ
│   ├── storage/           # S3/MinIO file storage
│   └── validation/        # Accounting, completeness, quality, lifecycle
├── tests/                 # 1,852 tests (88% coverage)
│   ├── unit/              # Unit tests
│   ├── integration/       # API integration tests
│   └── fixtures/          # Test Excel files + expected JSON
├── data/
│   └── taxonomy.json      # Canonical taxonomy (350+ items)
├── docs/
│   ├── demo/              # Product documentation for users
│   ├── architecture/      # Architecture decisions & briefs
│   ├── adr/               # Architecture Decision Records
│   └── ...                # Developer guides, testing, governance
├── alembic/               # Database migrations
├── static/                # Frontend UI
├── scripts/               # Utilities (benchmarks, fixtures)
├── docker-compose.yml     # Infrastructure services
├── Dockerfile             # Multi-target (api, worker, init-db)
└── pyproject.toml         # Dependencies & config
```

### Run Tests

```bash
# All tests
pytest -v

# With coverage
pytest -v --cov=src --cov-report=html

# Quick unit tests only
pytest tests/unit/ -v

# Specific file
pytest tests/unit/test_orchestrator.py -v
```

### Code Quality

```bash
ruff format src tests
ruff check src tests
ruff check --fix src tests
```

### Docker

```bash
# Build API image
docker build --target api -t debtfund-api .

# Build worker image
docker build --target worker -t debtfund-worker .
```

---

## Database

### Models (10 tables)

| Model | Purpose |
|-------|---------|
| `Entity` | Companies/projects being analyzed |
| `File` | Uploaded Excel files with content hash dedup |
| `ExtractionJob` | Job lifecycle (PENDING → COMPLETED/NEEDS_REVIEW) |
| `ExtractionFact` | Denormalized facts (one row per item × period) |
| `LineageEvent` | Stage-by-stage extraction lineage |
| `EntityPattern` | Learned label→canonical mappings per entity |
| `Taxonomy` | Canonical financial taxonomy items |
| `CorrectionHistory` | Audit trail for user corrections |
| `AuditLog` | API action audit logging |
| `APIKey` | Authentication keys with entity scoping |

### Migrations

```bash
alembic upgrade head      # Apply all migrations
alembic history           # View migration chain
alembic downgrade -1      # Rollback one migration
```

---

## Technology Stack

- **Backend**: Python 3.11+, FastAPI, Pydantic v2
- **AI**: Anthropic Claude API (Sonnet 4.5)
- **Database**: PostgreSQL 15, SQLAlchemy 2.0, Alembic
- **Cache/Queue**: Redis 7, Celery
- **Storage**: S3/MinIO
- **Monitoring**: Prometheus metrics, Jaeger tracing (optional)
- **Testing**: pytest (1,852 tests, 88% coverage)
- **Linting**: Ruff
- **Deployment**: Docker multi-target builds

---

## License

Proprietary and confidential. See [LICENSE](LICENSE) for details.

Copyright 2025 Florian Schabus. All Rights Reserved.
