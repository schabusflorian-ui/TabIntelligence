# DebtFund - Excel Model Intelligence Platform

**Guided Hybrid Extraction Platform for Excel Financial Models**

Extract structured financial data from Excel spreadsheets using Claude AI with full lineage tracking.

---

## Overview

DebtFund is an intelligent extraction platform that transforms messy Excel financial models into structured, queryable data with complete provenance tracking. It uses Claude AI guided by domain knowledge to parse, classify, and map financial line items to a canonical taxonomy.

### Key Features

- **5-Stage Extraction Pipeline**: Parse → Triage → Structure → Validate → Calibrate
- **Claude AI Integration**: Leverages Claude's reasoning capabilities with domain-specific prompts
- **Lineage Tracking**: 100% provenance - every data point traceable to source
- **Canonical Taxonomy**: Maps diverse Excel formats to standardized financial terminology
- **RESTful API**: Upload files, track jobs, query results
- **Confidence Scoring**: ML-powered confidence calibration for mappings

### Architecture

```
┌─────────────────┐
│   Excel File    │
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────────────────┐
│     GUIDED EXTRACTION PIPELINE (5 Stages)    │
│                                              │
│  ┌─────────┐  ┌─────────┐  ┌──────────┐    │
│  │  Parse  │→ │ Triage  │→ │Structure │→   │
│  │(Claude) │  │(Claude) │  │ (Claude) │    │
│  └─────────┘  └─────────┘  └──────────┘    │
│                                              │
│  ┌──────────┐  ┌────────────┐               │
│  │ Validate │→ │ Calibrate  │               │
│  │(Claude+) │  │   (ML)     │               │
│  └──────────┘  └────────────┘               │
│                                              │
│  Guided by: Taxonomy, Patterns, Prompts     │
│  Tracked by: Lineage system (EXISTENTIAL)   │
└──────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  Structured     │
│  Extraction     │
│  + Lineage      │
│  + Confidence   │
└─────────────────┘
```

For detailed architecture, see [docs/architecture/](docs/architecture/).

---

## Project Status

**Version**: `0.1.0` (Initial POC)
**Status**: Infrastructure Setup Phase
**Stage Completion**: 3/5 stages implemented (Parse, Triage, Map)

### Current Capabilities
✅ 3-stage extraction pipeline working
✅ Claude API integration
✅ Basic FastAPI endpoints
✅ Docker Compose development environment
✅ VS Code workspace configured

### In Progress
🚧 CI/CD pipeline (Week 1)
🚧 Testing infrastructure (Week 1)
🚧 Database models & migrations (Week 2)
🚧 Lineage system (Week 2, EXISTENTIAL)

### Coming Soon
⏳ Stages 4-5 (Structure, Validate, Calibrate)
⏳ Authentication & authorization
⏳ Excel Add-in
⏳ Review Dashboard

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker Desktop
- VS Code (recommended)
- Anthropic API key ([Get one here](https://console.anthropic.com))

### 1. Clone & Open

```bash
git clone <repository-url>
cd DebtFund
code excel-model-intelligence.code-workspace
```

### 2. Install Dependencies

```bash
# Create virtual environment
python -m venv .venv

# Activate it
source .venv/bin/activate  # Mac/Linux
# or: .venv\Scripts\activate  # Windows

# Install with dev dependencies
pip install -e ".[dev]"
```

### 3. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your Anthropic API key
ANTHROPIC_API_KEY=sk-ant-api03-xxxxx
```

### 4. Start Services

```bash
# Start PostgreSQL, Redis, MinIO
docker-compose up -d

# Verify services are running
docker-compose ps
```

### 5. Run the POC

```bash
# Generate test Excel file
python scripts/create_test_model.py

# Run extraction POC
python scripts/poc_guided_extraction.py tests/fixtures/sample_model.xlsx
```

**Expected output:**
```
Testing guided extraction on: tests/fixtures/sample_model.xlsx
==============================================================
Stage 1: Parsing...
  Found 4 sheets
Stage 2: Triaging...
  Tier 1 sheets: 3
Stage 3: Mapping...
  Mapped 25 items

EXTRACTION RESULTS
==============================================================
Sheets found: 4
  - Income Statement (Tier 1)
  - Balance Sheet (Tier 1)
  - Cash Flow (Tier 1)
  - Scratch - Working (Tier 4, skipped)

Sample mappings:
  Revenue                        → revenue              (95%)
  Cost of Goods Sold             → cogs                 (95%)
  Gross Profit                   → gross_profit         (95%)

COST SUMMARY
==============================================================
Tokens used: 12,345
Estimated cost: $0.0370
```

### 6. Start API Server

```bash
# Run with auto-reload
uvicorn src.api.main:app --reload

# Or press F5 in VS Code (debug mode)
```

Test the API:
```bash
curl http://localhost:8000/
# {"message": "Excel Model Intelligence API v0.1.0"}
```

---

## Development

### Project Structure

```
DebtFund/
├── src/                          # Source code
│   ├── agents/                  # Agent modules (1-9)
│   ├── api/                     # FastAPI endpoints
│   │   └── main.py             # API entry point
│   ├── core/                    # Config, logging, exceptions
│   ├── db/                      # Models, migrations, session
│   └── extraction/              # Orchestrator (Agent 3)
│       └── orchestrator.py     # 5-stage pipeline
├── tests/                       # Test suite
│   ├── unit/                   # Unit tests
│   ├── integration/            # Integration tests
│   └── fixtures/               # Test data
│       └── sample_model.xlsx
├── docs/                        # Documentation
│   ├── architecture/           # Agent briefs, diagrams
│   ├── governance/             # Project rules
│   └── development/            # Setup guides
├── scripts/                     # Utility scripts
│   ├── poc_guided_extraction.py
│   └── create_test_model.py
├── alembic/                     # Database migrations (coming)
├── .github/                     # CI/CD workflows (coming)
├── pyproject.toml              # Dependencies & config
├── docker-compose.yml          # Development services
└── README.md                   # This file
```

### Run Tests

```bash
# All tests
pytest -v

# With coverage
pytest -v --cov=src --cov-report=html

# Specific test file
pytest tests/unit/test_orchestrator.py -v
```

### Code Quality

```bash
# Format code
ruff format src tests

# Lint code
ruff check src tests

# Auto-fix issues
ruff check --fix src tests
```

### VS Code Features

**Debug Configurations (F5)**:
- FastAPI Server (with breakpoints)
- Claude POC script
- Create Test Model script
- Pytest (current file)

**Tasks (Ctrl+Shift+P → Tasks)**:
- Start Services
- Stop Services
- Run Tests

**Keyboard Shortcuts**:
- `F5`: Start debugging
- `Ctrl+Shift+P`: Command palette
- `Ctrl+``: Toggle terminal

---

## Documentation

- **[Getting Started Guide](docs/development/GETTING_STARTED.md)** - Detailed setup and first steps
- **[Contributing Guide](CONTRIBUTING.md)** - Development workflow and standards
- **[Agent Briefs](docs/architecture/agent_kickoff_briefs_v3.md)** - 9-agent architecture and deliverables
- **[Governance](docs/governance/project_governance_v3.md)** - The Four Laws and quality gates
- **[Project Setup](docs/development/PROJECT_SETUP.md)** - Technical architecture details

---

## The Four Laws

Development on DebtFund follows these core principles:

1. **End-to-end or nothing** — If you can't demo it, it doesn't work
2. **Test what matters** — Features without tests are not done
3. **Proactive communication** — Bad news early beats bad news late
4. **Honest status reporting** — "Almost done" is not a status

Read more in [project_governance_v3.md](docs/governance/project_governance_v3.md).

---

## 9-Agent Architecture

DebtFund is organized into 9 specialized agents:

| Agent | Responsibility | Status |
|-------|---------------|--------|
| **Agent 1** | Database Schema & ORM | 🚧 In Progress |
| **Agent 2** | API Endpoints & SSE | 🚧 In Progress |
| **Agent 3** | Extraction Orchestrator | ✅ Stages 1-3 Complete |
| **Agent 4** | Guidelines & Taxonomy | ⏳ Planned |
| **Agent 5** | Validation Engine | ⏳ Planned |
| **Agent 6** | Lineage & Provenance | 🚧 In Progress (EXISTENTIAL) |
| **Agent 7** | Confidence Calibration | ⏳ Planned |
| **Agent 8** | Excel Add-in | ⏳ Planned |
| **Agent 9** | Review Dashboard | ⏳ Planned |

See [agent_organization_v3.md](docs/architecture/agent_organization_v3.md) for details.

---

## API Endpoints (v0.1.0)

### Current Endpoints

```bash
GET  /                    # Health check
POST /extract             # Upload and extract file
GET  /jobs/{job_id}       # Check job status
```

### Coming Soon

```bash
GET  /api/v1/files                    # List files
GET  /api/v1/jobs/{id}/lineage        # Get extraction lineage
GET  /api/v1/taxonomy                 # Get canonical taxonomy
POST /api/v1/review/corrections       # Submit human corrections
```

Full API documentation: [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) (coming soon)

---

## Lineage System (EXISTENTIAL)

**Every extraction must have 100% lineage tracking.**

The lineage system tracks:
- Source file and sheet
- Extraction stage (1-5)
- Input → Output transformations
- Claude prompt used
- Confidence scores
- Human corrections

Without complete lineage, there is no trust. Without trust, there is no product.

Learn more: [docs/LINEAGE_GUIDE.md](docs/LINEAGE_GUIDE.md) (coming soon)

---

## Roadmap

### Week 1-2: Infrastructure Foundation ✅ In Progress
- [x] Project structure reorganization
- [x] LICENSE, CONTRIBUTING, documentation
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Pre-commit hooks
- [ ] Testing infrastructure
- [ ] Error handling & logging
- [ ] Database models
- [ ] Lineage system

### Week 3-4: Core Features
- [ ] Complete Agent 1 (Database)
- [ ] Complete Agent 2 (API)
- [ ] Complete Agent 6 (Lineage)
- [ ] Stage 4: Structure extraction
- [ ] Stage 5: Validation

### Week 5-8: Enhancement & Calibration
- [ ] Agent 4: Guidelines & taxonomy management
- [ ] Agent 5: Validation engine
- [ ] Agent 7: Confidence calibration
- [ ] Comprehensive integration tests

### Week 9+: User Interfaces
- [ ] Agent 8: Excel Add-in
- [ ] Agent 9: Review Dashboard
- [ ] Authentication & authorization
- [ ] Production deployment

---

## Technology Stack

- **Backend**: Python 3.11+, FastAPI
- **AI**: Anthropic Claude API (Sonnet 4.5)
- **Database**: PostgreSQL 15, SQLAlchemy 2.0
- **Cache**: Redis 7
- **Storage**: S3/MinIO
- **Queue**: Redis (background tasks)
- **Testing**: pytest, pytest-asyncio
- **Linting**: Ruff
- **Deployment**: Docker, Docker Compose

---

## Cost Estimation

**Development Phase** (per extraction):
- Parse stage: ~3,000 tokens ($0.009)
- Triage stage: ~2,000 tokens ($0.006)
- Mapping stage: ~4,000 tokens ($0.012)
- **Total per file**: ~$0.027

**Production** (with caching and optimization):
- Estimated: $0.01-0.02 per file

Token usage is tracked and logged for every extraction.

---

## License

This project is proprietary and confidential. See [LICENSE](LICENSE) for details.

Copyright © 2025 Florian Schabus. All Rights Reserved.

---

## Support & Contact

- **Issues**: Use GitHub Issues for bug reports and feature requests
- **Documentation**: See [docs/](docs/) folder
- **Contributing**: Read [CONTRIBUTING.md](CONTRIBUTING.md)

---

## Acknowledgments

Built with:
- [Anthropic Claude](https://www.anthropic.com/) - AI-powered extraction
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) - Python SQL toolkit
- [openpyxl](https://openpyxl.readthedocs.io/) - Excel file handling

---

**Status**: Infrastructure setup in progress. POC working. Production-ready coming Week 3.

For detailed setup instructions, see [docs/development/GETTING_STARTED.md](docs/development/GETTING_STARTED.md).
