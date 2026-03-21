# API Reference

Base URL: `http://localhost:8000`

Interactive docs: `http://localhost:8000/docs` (Swagger UI)

## Authentication

All endpoints (except health probes and root) require a Bearer token:

```
Authorization: Bearer sk-df-...
```

API keys are SHA-256 hashed and stored in the `api_keys` table. Keys can be:
- **Admin** (`entity_id=NULL`): Access all entities
- **Scoped** (`entity_id=<UUID>`): Access only the linked entity

Rate limits apply per-IP (via slowapi) and per-key (`rate_limit_per_minute` field on APIKey).

## Error Codes

| Code | Meaning |
|------|---------|
| 400 | Bad request (invalid UUID, missing required field) |
| 401 | Missing or invalid API key |
| 403 | API key doesn't have access to this entity |
| 404 | Resource not found |
| 409 | Conflict (wrong job status for this operation) |
| 422 | Validation error (invalid canonical name, Pydantic failure) |
| 429 | Rate limit exceeded |
| 500 | Server error |
| 503 | Service unavailable (database/S3/Celery down) |

---

## File Upload

### POST /api/v1/files/upload

Upload an Excel file for extraction. Returns immediately with a job_id — extraction runs asynchronously via Celery.

**Rate limit:** 100/hour

```bash
curl -X POST http://localhost:8000/api/v1/files/upload \
  -H "Authorization: Bearer $API_KEY" \
  -F "file=@model.xlsx" \
  -F "entity_id=<uuid>"   # optional
```

**Response (201):**
```json
{
  "file_id": "abc123...",
  "job_id": "def456...",
  "filename": "model.xlsx",
  "status": "PENDING",
  "message": "File uploaded, extraction started"
}
```

**Deduplication:** If the same file bytes are uploaded again, returns the existing file_id and job_id (no new extraction).

### GET /api/v1/files/

List uploaded files with pagination.

**Query params:** `limit` (1-200, default 50), `offset` (default 0)

### GET /api/v1/files/{file_id}

Get metadata for a single file.

---

## Job Management

### GET /api/v1/jobs/

List extraction jobs.

**Rate limit:** 500/hour

**Query params:**
- `limit` (1-200, default 50)
- `offset` (default 0)
- `status` — filter: PENDING, PROCESSING, COMPLETED, FAILED, NEEDS_REVIEW

### GET /api/v1/jobs/{job_id}

Get detailed job status including stage progress.

**Response (200):**
```json
{
  "job_id": "...",
  "status": "COMPLETED",
  "current_stage": "enhanced_mapping",
  "stages_completed": 5,
  "stages_total": 5,
  "tokens_used": 12500,
  "cost_usd": 0.037,
  "quality_grade": "B",
  "created_at": "2026-03-12T10:00:00Z",
  "completed_at": "2026-03-12T10:02:30Z"
}
```

### GET /api/v1/jobs/{job_id}/export

Export extraction results as JSON or CSV.

**Query params:**
- `format` — `json` (default) or `csv`
- `min_confidence` — filter items below threshold (0.0-1.0)
- `canonical_name` — filter to specific item
- `sheet` — filter to specific sheet

### POST /api/v1/jobs/{job_id}/retry

Retry a failed job. Creates a new job and resumes from the last completed stage checkpoint.

**Rate limit:** 20/hour

**Response (200):**
```json
{
  "new_job_id": "...",
  "task_id": "...",
  "original_job_id": "...",
  "resume_from_stage": "mapping",
  "message": "Retry started, resuming from mapping"
}
```

### POST /api/v1/jobs/{job_id}/review

Approve or reject a job in NEEDS_REVIEW status.

**Request body:**
```json
{
  "decision": "approve",
  "reason": "Looks correct after manual review"
}
```

### GET /api/v1/jobs/{job_id}/lineage

Get full lineage event chain for a job (all stages, all events).

### GET /api/v1/jobs/{job_id}/lineage/{canonical_name}

Get provenance for a specific canonical item across all periods.

### GET /api/v1/jobs/{job_id}/item-lineage/{canonical_name}

Get the transformation chain for an item (how it was mapped, validated, remapped).

### GET /api/v1/jobs/{job_id}/diff/{other_job_id}

Compare extraction results between two jobs.

**Query params:**
- `canonical_name` — filter to specific item
- `min_change_pct` — minimum change percentage to include

---

## Entities

### GET /api/v1/entities/

List entities. **Rate limit:** 500/hour

### POST /api/v1/entities/

Create an entity.

**Request body:**
```json
{
  "name": "Acme Corp",
  "industry": "Technology"
}
```

**Response (201):** EntityResponse

### GET /api/v1/entities/{entity_id}

Get entity details including pattern and file counts. **Auth:** requires entity scope.

### PATCH /api/v1/entities/{entity_id}

Update entity name or industry. **Auth:** requires entity scope.

**Request body:**
```json
{
  "name": "Acme Corporation"
}
```

### DELETE /api/v1/entities/{entity_id}

Delete an entity. **Status:** 204. **Auth:** requires entity scope.

---

## Corrections

### POST /api/v1/jobs/{job_id}/corrections

Submit user corrections for a job's mappings. Creates entity patterns for future shortcircuiting.

**Request body:**
```json
{
  "corrections": [
    {
      "original_label": "Rev",
      "canonical_name": "revenue"
    }
  ]
}
```

### POST /api/v1/jobs/{job_id}/corrections/preview

Preview what corrections would change without persisting. Returns diffs and warnings.

**Request body:** Same as `/apply`

### POST /api/v1/jobs/{job_id}/corrections/apply

Apply corrections retroactively. Updates job result JSON, creates patterns, updates facts. **Lenient mode:** skips labels not found.

**Request body:**
```json
{
  "corrections": [
    {
      "original_label": "Rev",
      "new_canonical_name": "revenue",
      "sheet": "Income Statement"
    }
  ]
}
```

### POST /api/v1/jobs/{job_id}/corrections/bulk

Apply corrections transactionally — all-or-nothing. All labels must exist AND all canonical names must be valid.

### POST /api/v1/corrections/{correction_id}/undo

Undo a specific correction, restoring original values. Returns 409 if overlapping corrections exist.

### GET /api/v1/jobs/{job_id}/corrections/history

List correction history for a job. **Query param:** `include_reverted` (default true).

---

## Entity Patterns

### GET /api/v1/entities/{entity_id}/patterns

List learned patterns for an entity. **Auth:** entity scope.

**Query params:** `min_confidence` (0.0-1.0), `limit` (1-1000, default 200)

### DELETE /api/v1/entities/{entity_id}/patterns/{pattern_id}

Delete a specific pattern. **Auth:** entity scope. **Status:** 204.

### GET /api/v1/entities/{entity_id}/pattern-stats

Pattern quality statistics: total, active, average confidence, by creation method, top patterns, conflicted patterns.

---

## Learned Aliases

### GET /api/v1/learned-aliases

List learned aliases pending review or promotion.

**Query params:** `min_occurrences` (default 1), `limit` (1-500, default 100)

### POST /api/v1/learned-aliases/{alias_id}/promote

Promote a learned alias (adds to taxonomy lookup).

---

## Taxonomy

### GET /api/v1/taxonomy/

List all taxonomy items. **Query param:** `category` (filter by category).

### GET /api/v1/taxonomy/search

Search taxonomy. **Query param:** `q` (required, min 1 char).

### GET /api/v1/taxonomy/hierarchy

Get taxonomy as a hierarchical tree. **Query param:** `category`.

### GET /api/v1/taxonomy/stats

Get taxonomy statistics (item counts, category breakdown).

### GET /api/v1/taxonomy/{canonical_name}

Get a single taxonomy item by canonical name.

---

## Extraction Facts

### GET /api/v1/facts

Query decomposed extraction facts (one row per canonical_name + period + job).

**Query params:**
- `entity_id` — filter by entity (UUID)
- `canonical_name` — filter by canonical name
- `period` — filter by period
- `job_id` — filter by job (UUID)
- `min_confidence` — minimum confidence threshold
- `limit` (default 100), `offset` (default 0)

---

## Analytics

### GET /api/v1/analytics/entity/{entity_id}/financials

Get financial data for an entity across jobs and periods.

### GET /api/v1/analytics/compare

Cross-entity comparison.

**Query params:** `entity_ids` (comma-separated), `canonical_names` (comma-separated), `period` (required)

### GET /api/v1/analytics/portfolio/summary

Portfolio-level summary across entities.

### GET /api/v1/analytics/entity/{entity_id}/trends

Time-series trends for a canonical item with YoY change.

**Query param:** `canonical_name` (required)

### GET /api/v1/analytics/taxonomy/coverage

Taxonomy coverage analysis (which items are mapped, which are never mapped).

### GET /api/v1/analytics/costs

Claude API cost analytics. **Query params:** `entity_id`, `date_from`, `date_to`.

---

## Health Probes

### GET /health/liveness

Always returns 200. Use for Kubernetes liveness probe. **No auth required.**

### GET /health/readiness

Returns 200 if database is reachable, 503 otherwise. **No auth required.**

### GET /health

Comprehensive health check with component status (database, S3). Returns 200 or 503. **No auth required.**

### GET /health/database

Database pool and circuit breaker stats. **Auth required.**

### GET /health/circuit-breaker

Circuit breaker state and statistics. **Auth required.**

### GET /health/stale-jobs

Detect stale jobs (PENDING > 10min, PROCESSING > 30min). **Auth required.**

---

## DLQ Admin

### GET /api/v1/admin/dlq/

List dead-letter queue entries. **Query params:** `limit`, `offset`, `only_unreplayed`.

### GET /api/v1/admin/dlq/{dlq_id}

Get DLQ entry details including traceback and task args.

### POST /api/v1/admin/dlq/{dlq_id}/replay

Replay a failed DLQ entry. **Rate limit:** 20/hour.

### DELETE /api/v1/admin/dlq/{dlq_id}

Delete a DLQ entry. **Status:** 204.

---

## Metrics

### GET /metrics

Prometheus-compatible metrics. Not in OpenAPI schema. No auth in dev (use network-level protection in production).

---

## See Also

- [Feature Catalog](demo/feature-catalog.md) — Complete endpoint reference table with rate limits, organized by router
- [Product Overview](demo/product-overview.html) — Visual product pitch with platform capabilities
- [Architecture Diagrams](demo/architecture-diagrams.md) — System architecture, pipeline sequence diagram, database ER diagram
