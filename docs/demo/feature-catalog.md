# TabIntelligence — Feature Catalog

> Comprehensive feature list organized by user persona. Each section addresses what that user type cares about most.

---

## For Credit Analysts

### Drag-and-Drop Upload
Upload any Excel financial model (.xlsx / .xls) via drag-and-drop or programmatic API. Content-hash deduplication (SHA-256) prevents re-processing identical files — upload the same model twice and it returns the existing results instantly.

### Automatic Sheet Classification
AI classifies every sheet into four tiers — no manual sheet selection needed:
- **Tier 1** — Core financials (Income Statement, Balance Sheet, Cash Flow) — full extraction
- **Tier 2** — Supporting schedules (debt schedule, working capital) — full extraction
- **Tier 3** — Assumptions, inputs, sensitivity tables — metadata only
- **Tier 4** — Charts, formatting-only sheets — skipped

### Intelligent Label Mapping
Maps every row label to one of **312 canonical financial line items** across 6 categories. Handles variations automatically:
- "Operating Revenue", "Total Revenue", "Net Revenue", "Sales", "Turnover" → `revenue`
- "A/P", "Creditors", "Trade Payables", "Accounts Payable" → `accounts_payable`
- Misspellings, abbreviations, and regional variants resolved with confidence scores

### Inline Review & Correction
Review AI mappings directly in the web interface. Click any canonical name to edit with a **searchable taxonomy dropdown** — type a few characters to filter, navigate with arrow keys, press Enter to confirm. Changes persist as **entity-specific patterns** that improve future extractions.

### Quality Grades (A–F)
Each extraction receives a composite quality score across 5 dimensions:
- **Grade A** (≥90%) — Trustworthy. Data can be used without manual review.
- **Grade B** (≥75%) — Reliable. Spot-check recommended.
- **Grade C** (≥60%) — Needs Review. Manual review of flagged items recommended.
- **Grade D** (≥40%) — Low Confidence. Significant manual intervention required.
- **Grade F** (<40%) — Unreliable. Extraction quality insufficient.

### Data Provenance
Click any data point to trace it back to the exact source:
- Sheet name, row index, column index
- Original label text from the Excel cell
- AI reasoning for the mapping decision
- Confidence score and mapping method (AI, pattern shortcircuit, user correction)
- Full transformation chain through all 5 pipeline stages

### Export
Download structured results as **JSON or CSV** with optional filters:
- Minimum confidence threshold
- Specific canonical names or categories
- Sheet name filter

### Bulk Edit
Select multiple low-confidence items simultaneously and apply corrections in batch. Ideal for fixing systematic mapping errors across an entire extraction.

---

## For Portfolio Managers

### Cross-Entity Comparison
Select entities and metrics, compare side by side in a structured table:
- **Period alignment**: Exact match, normalized to calendar year, or fiscal year alignment
- **FX conversion**: Convert all entities to a common currency (USD, EUR, GBP) using cached Alpha Vantage rates
- **Metadata overlay**: See each entity's currency, fiscal year end, and reporting standard alongside values

### Structured Financial Statements
Income Statement, Balance Sheet, and Cash Flow rendered as **hierarchical statements** — not flat lists:
- Parent-child nesting with indentation (Revenue → Product Revenue, Service Revenue)
- Subtotal emphasis (bold, background highlight)
- Logical ordering (Revenue → COGS → Gross Profit → OpEx → EBITDA → ... → Net Income)
- YoY % change column with sparkline trend charts
- Negative values in parentheses with red color

### Anomaly Detection
Flag statistical outliers across your portfolio:
- **IQR method**: Interquartile range with configurable multiplier (default 1.5x)
- **Z-score method**: Standard deviation threshold (default 2.0)
- Results show: entity, value, direction (above/below), and score
- Visual highlighting of outlier rows

### Quality Trending
Track extraction quality improvement per entity over time:
- Quality grade history chart (A–F on Y axis, time on X)
- Average confidence overlay (secondary axis)
- Points color-coded by grade
- Snapshot table: date, grade, confidence %, facts count, unmapped labels

### Cost Analytics
Monitor Claude AI extraction costs:
- Total cost across all extractions
- Cost breakdown by entity
- Average cost per job
- Daily cost trend chart with area fill

### Portfolio Health Dashboard
At-a-glance portfolio overview:
- Total entities, extractions, facts, and average confidence
- Quality grade distribution bar chart (A–F)
- Recent extraction activity

---

## For Financial Data Teams

### 50+ REST API Endpoints
Full programmatic access via OpenAPI-documented REST API. Interactive Swagger UI at `/docs`. Every operation available in the web app is also available via API.

### API Key Authentication
- **SHA-256 hashed** API keys stored securely
- **Entity scoping**: Keys can be restricted to a single entity — isolated access for external partners
- **Rate limiting**: Configurable per-key and per-IP limits (default 60 req/min per key)
- **Expiration**: Optional `expires_at` timestamp for temporary access
- **Audit logging**: Every API call logged with action, resource, IP, user agent

### Async Extraction
Upload triggers a background Celery task:
- Poll for progress with adaptive intervals (2–15 second exponential backoff)
- 5-stage progress tracking with percentage and stage name
- 10-minute timeout with graceful failure handling
- Checkpoint/resume from any stage on retry

### Taxonomy Management API
- Browse 312 items by category with parent-child hierarchy
- Full-text search across canonical names and aliases
- **Suggestion engine**: AI proposes new aliases, new items, or conflict fixes based on extraction patterns
- **Deprecation workflow**: Mark items deprecated with optional redirect to replacement
- **Changelog**: Field-level audit trail of all taxonomy changes

### Learned Alias Lifecycle
AI discovers high-confidence aliases across extractions:
1. Claude maps a label with high confidence (≥0.9)
2. Label recorded as LearnedAlias with source entities
3. After **5+ occurrences** from **3+ distinct entities** → auto-promoted to canonical taxonomy aliases
4. Full audit trail: created, promoted, or archived with reason

### Dead Letter Queue
Failed extractions captured with full diagnostic information:
- Task ID, name, arguments
- Error message and full stack trace
- One-click replay from the admin UI
- Delete entries after investigation

### Health Monitoring
Production-grade system observability:
- **Database health**: Connection pool utilization, query latency, circuit breaker state
- **Stale job detection**: Jobs stuck in PENDING or PROCESSING for too long
- **K8s health probes**: `/health/live` (liveness), `/health/ready` (readiness), `/health/db` (deep check)
- **Circuit breaker**: Auto-opens on database failures, half-open for recovery testing

### Observability Stack
- **18 Prometheus metrics**: HTTP requests, extraction duration, token usage, file uploads, quality scores, database query latency
- **Grafana dashboards**: Pre-built API and extraction dashboards
- **Jaeger distributed tracing**: End-to-end request tracing across API, database, and Claude calls
- **Structured JSON logging**: Request ID correlation, log levels, file + console output

---

## Platform Security

| Feature | Description |
|---------|-------------|
| API key authentication | SHA-256 hashed keys with Bearer token scheme |
| Entity-scoped access | Keys restricted to specific entities for data isolation |
| Per-key rate limiting | Configurable requests per minute per API key |
| Per-IP rate limiting | Endpoint-specific limits (20–500/hour) |
| Audit logging | Action, resource, API key, IP, user agent, status code |
| Security headers | HSTS, X-Content-Type-Options, X-Frame-Options, CSP |
| Content deduplication | SHA-256 content hash prevents duplicate processing |
| Request ID correlation | X-Request-ID header for end-to-end tracing |
| Key expiration | Optional `expires_at` for temporary access grants |

---

## Complete API Endpoint Reference

### Files (4 endpoints)

| Method | Path | Description | Rate |
|--------|------|-------------|------|
| POST | `/api/v1/files/upload` | Upload Excel file (.xlsx/.xls) | 100/hr |
| GET | `/api/v1/files/` | List uploaded files | 500/hr |
| GET | `/api/v1/files/{file_id}` | Get file metadata | 500/hr |
| GET | `/api/v1/files/{file_id}/download` | Generate presigned download URL | 500/hr |

### Jobs (10 endpoints)

| Method | Path | Description | Rate |
|--------|------|-------------|------|
| GET | `/api/v1/jobs/` | List extraction jobs (filterable by status) | 500/hr |
| GET | `/api/v1/jobs/{job_id}` | Get job status, results, quality | 500/hr |
| GET | `/api/v1/jobs/{job_id}/export` | Export line items as JSON or CSV | 500/hr |
| POST | `/api/v1/jobs/{job_id}/retry` | Re-extract failed/completed job | 20/hr |
| POST | `/api/v1/jobs/{job_id}/review` | Approve or reject NEEDS_REVIEW job | 100/hr |
| GET | `/api/v1/jobs/{job_id}/lineage` | Full extraction audit trail | 500/hr |
| GET | `/api/v1/jobs/{job_id}/lineage/{canonical_name}` | Provenance for specific item | 500/hr |
| GET | `/api/v1/jobs/{job_id}/diff/{other_job_id}` | Compare two extraction jobs | 500/hr |
| GET | `/api/v1/jobs/{job_id}/item-lineage/{canonical_name}` | Transformation chain | 500/hr |
| GET | `/api/v1/jobs/{job_id}/review-suggestions` | AI-ranked review recommendations | 500/hr |

### Entities (5 endpoints)

| Method | Path | Description | Rate |
|--------|------|-------------|------|
| GET | `/api/v1/entities/` | List all entities with stats | 500/hr |
| POST | `/api/v1/entities/` | Create new entity | 100/hr |
| GET | `/api/v1/entities/{entity_id}` | Get entity detail | 500/hr |
| PATCH | `/api/v1/entities/{entity_id}` | Update entity metadata | 100/hr |
| DELETE | `/api/v1/entities/{entity_id}` | Delete entity (cascade) | 100/hr |

### Taxonomy (10 endpoints)

| Method | Path | Description | Rate |
|--------|------|-------------|------|
| GET | `/api/v1/taxonomy/` | List all taxonomy items | 500/hr |
| GET | `/api/v1/taxonomy/stats` | Category statistics | 500/hr |
| GET | `/api/v1/taxonomy/search` | Search canonical names & aliases | 500/hr |
| GET | `/api/v1/taxonomy/hierarchy` | Parent-child hierarchy tree | 500/hr |
| GET | `/api/v1/taxonomy/{canonical_name}` | Single item detail | 500/hr |
| GET | `/api/v1/taxonomy/suggestions` | List improvement suggestions | 500/hr |
| POST | `/api/v1/taxonomy/suggestions/{id}/accept` | Accept a suggestion | 100/hr |
| POST | `/api/v1/taxonomy/suggestions/{id}/reject` | Reject a suggestion | 100/hr |
| POST | `/api/v1/taxonomy/{canonical_name}/deprecate` | Deprecate with redirect | 100/hr |
| GET | `/api/v1/taxonomy/changelog` | Field-level audit trail | 500/hr |

### Analytics (15 endpoints)

| Method | Path | Description | Rate |
|--------|------|-------------|------|
| GET | `/api/v1/analytics/entity/{id}/financials` | Entity financial data | 500/hr |
| GET | `/api/v1/analytics/entity/{id}/statement` | Structured statement by category | 500/hr |
| GET | `/api/v1/analytics/entity/{id}/trends` | Time-series trends | 500/hr |
| GET | `/api/v1/analytics/entity/{id}/multi-period` | Multi-period comparison | 500/hr |
| GET | `/api/v1/analytics/entity/{id}/quality-trend` | Quality grade history | 500/hr |
| GET | `/api/v1/analytics/entity/{id}/compare-periods` | Period deltas | 500/hr |
| GET | `/api/v1/analytics/compare` | Cross-entity comparison | 500/hr |
| GET | `/api/v1/analytics/portfolio/summary` | Portfolio overview stats | 500/hr |
| GET | `/api/v1/analytics/coverage` | Taxonomy coverage analysis | 500/hr |
| GET | `/api/v1/analytics/costs` | Cost analytics by entity/day | 500/hr |
| GET | `/api/v1/analytics/facts` | Raw extraction facts query | 500/hr |
| GET | `/api/v1/analytics/anomalies` | Anomaly detection (IQR/Z-score) | 500/hr |
| GET | `/api/v1/analytics/confidence-calibration` | Calibration statistics | 500/hr |
| GET | `/api/v1/analytics/unmapped` | Unmapped label aggregation | 500/hr |
| GET | `/api/v1/analytics/quality/trends` | Quality trending across entities | 500/hr |

### Corrections (8 endpoints)

| Method | Path | Description | Rate |
|--------|------|-------------|------|
| POST | `/api/v1/jobs/{id}/corrections` | Submit corrections | 200/hr |
| GET | `/api/v1/jobs/{id}/corrections` | Get correction history | 200/hr |
| POST | `/api/v1/jobs/{id}/corrections/{cid}/undo` | Undo a correction | 200/hr |
| GET | `/api/v1/jobs/{id}/corrections/preview` | Preview correction impact | 200/hr |
| GET | `/api/v1/entities/{id}/patterns` | List entity patterns | 500/hr |
| GET | `/api/v1/entities/{id}/patterns/stats` | Pattern statistics | 500/hr |
| GET | `/api/v1/entities/{id}/learned-aliases` | Learned aliases | 500/hr |
| POST | `/api/v1/entities/{id}/learned-aliases/{aid}/promote` | Promote alias | 100/hr |

### Health (5 endpoints)

| Method | Path | Description | Rate |
|--------|------|-------------|------|
| GET | `/health` | Full health check | — |
| GET | `/health/live` | Liveness probe (K8s) | — |
| GET | `/health/ready` | Readiness probe (K8s) | — |
| GET | `/health/db` | Database health + circuit breaker | — |
| GET | `/health/db/stale-jobs` | Stale job detection | — |

### Admin — Dead Letter Queue (4 endpoints)

| Method | Path | Description | Rate |
|--------|------|-------------|------|
| GET | `/api/v1/admin/dlq/` | List DLQ entries | 500/hr |
| GET | `/api/v1/admin/dlq/{id}` | DLQ entry detail + traceback | 500/hr |
| POST | `/api/v1/admin/dlq/{id}/replay` | Replay failed task | 20/hr |
| DELETE | `/api/v1/admin/dlq/{id}` | Delete DLQ entry | 20/hr |

---

*Document generated for the TabIntelligence Excel Model Intelligence Platform documentation package.*
