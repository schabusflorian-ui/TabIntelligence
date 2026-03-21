# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added - MVP Demo Documentation Package
- **Product overview** (`docs/demo/product-overview.html`) — Self-contained HTML pitch page with Meridian design system styling
- **Architecture diagrams** (`docs/demo/architecture-diagrams.md`) — 5 Mermaid diagrams: system architecture, extraction pipeline, database ER (17 tables), quality scoring, taxonomy hierarchy
- **Data flow diagrams** (`docs/demo/data-flow-diagrams.md`) — 4 Mermaid diagrams: data lifecycle, entity learning loop, security/auth flow, deployment topology
- **Feature catalog** (`docs/demo/feature-catalog.md`) — Features by persona (analyst, PM, data team) with complete 50+ endpoint reference
- **Product roadmap** (`docs/demo/roadmap.md`) — Gantt chart: MVP (done) → Phase 2 (integration) → Phase 3 (intelligence) → Phase 4 (scale)
- **Demo walkthrough** (`docs/demo/demo-walkthrough.md`) — 20-minute guided demo script with 6 acts, talking points, and Q&A

### Added - Phase 3: Analytics Intelligence
- Cross-entity comparison with FX conversion (Alpha Vantage integration)
- Taxonomy governance: AI suggestions, deprecation workflow, changelog, learned alias lifecycle
- Quality trending per entity over time
- Structured financial statement hierarchy with STATEMENT_DISPLAY_ORDER sorting
- Frontend: analytics page with 6 intelligence modules, comparison page, taxonomy browser with tabs

### Added - Error Handling & Logging (Week 1, Days 4-5)
- **Exception hierarchy** (`src/core/exceptions.py`)
  - Base `DebtFundError` exception class
  - Specialized exceptions: `ClaudeAPIError`, `ExtractionError`, `ValidationError`, `LineageError`, `DatabaseError`
  - `LineageIncompleteError` for EXISTENTIAL lineage tracking failures
  - `RateLimitError` with retry-after tracking
  - Detailed exception context with metadata

- **Structured logging** (`src/core/logging.py`)
  - Console and file output (`logs/debtfund.log`)
  - Module-specific loggers (extraction, API, database, lineage, validation)
  - Performance logging utility (`log_performance()`)
  - Exception logging with context (`log_exception()`)
  - Log level context manager for debugging
  - Suppression of noisy libraries (httpx, anthropic)

- **Error handling in extraction pipeline**
  - Retry logic with exponential backoff for Claude API rate limits
  - Maximum 3 retries with configurable backoff
  - Graceful handling of API errors, network failures, invalid responses
  - Performance timing for all stages
  - Comprehensive error logging with context

- **API logging**
  - Request/response logging for all endpoints
  - File upload tracking (filename, size, job_id)
  - Job status queries logged
  - Background task execution logging
  - Structured error logging for failures

- **Configuration management** (`src/core/config.py`)
  - Pydantic Settings for type-safe configuration
  - Environment variable validation
  - API key format validation
  - Database URL validation
  - Computed properties (is_development, is_production, max_file_size_bytes)
  - Sensitive value masking in print output
  - Comprehensive `.env.example` with all configuration options

### Added - Infrastructure (Week 1, Days 1-3)
- Professional project structure reorganization
  - Moved from `/project` subfolder to clean root structure
  - Organized planning docs into `docs/` folder with architecture, governance, and development subfolders
  - Created proper folder hierarchy: `src/`, `tests/`, `scripts/`, `.github/`

- Essential documentation
  - `LICENSE`: Proprietary/closed source license
  - `CONTRIBUTING.md`: Development workflow, The Four Laws, agent ownership
  - Enhanced `README.md`: Comprehensive project overview, architecture, roadmap
  - `CHANGELOG.md`: Version tracking (this file)

- CI/CD pipeline (`.github/workflows/ci.yml`)
  - Automated linting with Ruff
  - Test execution with pytest
  - Coverage reporting with Codecov
  - Security scanning with Safety
  - PostgreSQL and Redis services for integration tests

- Pre-commit hooks (`.pre-commit-config.yaml`)
  - Automatic code formatting with Ruff
  - Trailing whitespace and EOF fixes
  - YAML/JSON syntax validation
  - Large file detection
  - Private key detection
  - Custom hooks to block .env files and API keys

- GitHub templates
  - Issue templates: Agent Deliverable, Bug Report, Feature Request
  - Pull Request template with comprehensive checklist

- Testing infrastructure
  - `tests/conftest.py`: Pytest fixtures for FastAPI client, sample Excel files, mock Claude responses
  - `tests/unit/test_orchestrator.py`: 14 unit tests for extraction pipeline
  - `tests/integration/test_api_endpoints.py`: 12 integration tests for API endpoints
  - Total: 26 tests (14 passing, 12 need mock fixes)

- Configuration files
  - `pyproject.toml`: Python 3.11+, dependencies, Ruff config, pytest config
  - `docker-compose.yml`: PostgreSQL 15, Redis 7, MinIO S3 services
  - `.env.example`: Environment variable template
  - `.gitignore`: Comprehensive exclusions for Python, IDEs, secrets
  - `excel-model-intelligence.code-workspace`: VS Code configuration

### Changed
- Reorganized project structure from `/project` to root
- Updated all import paths in scripts and source code
- Enhanced README with comprehensive project information

### Fixed
- Import paths corrected for new root structure
- Python 3.11+ virtual environment setup

## [0.1.0] - 2025-02-XX - Initial POC

### Added
- 3-stage extraction pipeline (Parse, Triage, Map)
- Claude API integration with Anthropic SDK
- Basic FastAPI endpoint (`/api/v1/files/upload`)
- Job status tracking (in-memory)
- Docker Compose development environment
  - PostgreSQL 15
  - Redis 7
  - MinIO (S3-compatible storage)
- VS Code workspace with debuggers and tasks
- Sample Excel model generator script
- POC extraction script

### Known Issues
- Stages 4-5 (Structure, Validation) not yet implemented
- No database persistence (in-memory job storage)
- No authentication/authorization
- Test mocking needs fixes for Claude API
- No lineage tracking system yet (EXISTENTIAL - planned for Week 2)

---

## Roadmap

### Week 2 (In Progress)
- [ ] Database models (SQLAlchemy)
- [ ] Alembic migrations
- [ ] Lineage system (Agent 6 - EXISTENTIAL)
- [ ] Error handling and logging
- [ ] Configuration management

### Week 3-4
- [ ] Complete Agent 1 (Database)
- [ ] Complete Agent 2 (API)
- [ ] Stage 4: Structure extraction
- [ ] Stage 5: Validation

### Future
- [ ] Agent 4: Guidelines & taxonomy
- [ ] Agent 5: Validation engine
- [ ] Agent 7: Confidence calibration
- [ ] Agent 8: Excel Add-in
- [ ] Agent 9: Review Dashboard
- [ ] Authentication & authorization
- [ ] Production deployment

---

**The Four Laws**: End-to-end or nothing | Test what matters | Proactive communication | Honest status reporting
