# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- MVP demo documentation package (`docs/demo/`)
  - Self-contained product overview HTML page
  - Architecture and data flow diagrams (Mermaid)
  - Feature catalog organized by persona
  - Product roadmap (Gantt chart)
  - 20-minute guided demo walkthrough
- Stage 6 Derivation Engine: gap-fill, consistency checks, covenant flags
- Cross-entity comparison with FX conversion (Alpha Vantage integration)
- Taxonomy governance: AI suggestions, deprecation workflow, changelog, learned alias lifecycle
- Quality trending per entity over time
- Structured financial statement hierarchy with display ordering
- Frontend analytics page, comparison module, and taxonomy browser

## [0.2.0] - Extraction Pipeline & Infrastructure

### Added

#### Extraction Pipeline
- 5-stage guided extraction pipeline (Parse, Triage, Map, Validate, Enhanced Map)
- Claude AI integration with domain-specific prompts and confidence-scored mappings
- Entity pattern learning: corrections feed back into future extractions
- Benchmark framework with regression tracking and accuracy baselines
- 100% lineage tracking: every data point traceable to source cell

#### API & Backend
- FastAPI REST API with 50 endpoints across 8 routers
- API key authentication with entity scoping
- Celery task queue for async extraction with dead letter queue
- S3/MinIO file storage with content-hash deduplication
- Correction workflow: submit, apply, preview, undo, bulk operations
- Analytics: cross-entity comparison, portfolio aggregation, trend analysis

#### Database
- PostgreSQL persistence with 10 tables (SQLAlchemy 2.0)
- Alembic migration chain with safe migration tooling
- Canonical financial taxonomy (350+ items, 6 categories)
- Quality scoring engine (composite A-F grades)

#### Infrastructure
- Docker multi-target builds (API, worker, init-db)
- CI/CD pipeline: linting, type checking, tests, security scanning, regression checks
- Pre-commit hooks: Ruff formatting, API key detection, taxonomy validation
- Prometheus metrics + Grafana dashboards
- Optional Jaeger distributed tracing (OpenTelemetry)

#### Developer Experience
- Pydantic Settings configuration with environment variable validation
- Structured logging with module-specific loggers
- Exception hierarchy with specialized error types
- Retry logic with exponential backoff for Claude API
- Comprehensive test suite with benchmarking framework

## [0.1.0] - Initial Proof of Concept

### Added
- 3-stage extraction pipeline (Parse, Triage, Map)
- Claude API integration with Anthropic SDK
- Basic FastAPI upload endpoint
- Docker Compose development environment (PostgreSQL, Redis, MinIO)
- Sample Excel model generator script

---

## License

Proprietary and confidential. See [LICENSE](LICENSE) for details.
