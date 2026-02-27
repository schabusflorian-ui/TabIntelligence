# DebtFund — MVP Agent Prompts

Ordered by deployment priority. Each agent is self-contained and can run independently.

---

## Agent 1: Stabilize & Commit (BLOCKING — do this first)

```
You are working on the DebtFund project at /Users/florianschabus/DebtFund.

GOAL: Commit all uncommitted work and fix the 8 failing tests to stabilize the codebase.

CONTEXT:
- There are ~30 uncommitted files from prior agent sessions (taxonomy enhancements, export endpoint, new tests, linter fixes, archived docs)
- 8 tests are currently failing (pre-existing, not regressions):
  - tests/unit/test_enhanced_mapping_stage.py (7 failures — mock missing entity_id, taxonomy loader issues)
  - tests/unit/test_validation_stage.py::TestDerivationRules::test_balance_sheet_rule_is_critical (1 failure — missing "critical" field)
- Coverage is ~73%, target is 80% (configured in pyproject.toml [tool.coverage.report] fail_under = 80)

TASKS:
1. Run `git status` to see all uncommitted files. Review each one to understand what it does.
2. Fix the 8 failing tests:
   - For test_enhanced_mapping_stage.py: the mock PipelineContext is missing `entity_id` attribute. Add it to the mock setup.
   - For test_balance_sheet_rule_is_critical: either add `"critical": true` to the balance sheet derivation rule in data/taxonomy.json, or fix the test to match the actual schema.
3. Run the full test suite: `pytest tests/ --ignore=tests/e2e -x --no-cov` — all tests must pass.
4. Run with coverage: `pytest tests/ --ignore=tests/e2e` — coverage must be >= 80%. If under 80%, identify the lowest-covered modules and add targeted tests.
5. Commit all changes in logical groups:
   - First commit: test fixes (the 8 failures)
   - Second commit: uncommitted source files (taxonomy endpoints, taxonomy loader, export endpoint, crud enhancements, model updates, stage improvements)
   - Third commit: uncommitted test files
   - Fourth commit: docs, scripts, and cleanup (archived files, deleted stale scripts)
6. Run the full suite one final time to confirm everything passes.

CONSTRAINTS:
- Do NOT modify any passing test's behavior
- Do NOT change the API contract (endpoint signatures, response shapes)
- Use the virtual environment at .venv/bin/python
- Do NOT push to remote
```

---

## Agent 2: Production Docker & Deployment Config

```
You are working on the DebtFund project at /Users/florianschabus/DebtFund.

GOAL: Make the Docker setup production-ready so the app can be deployed to a real environment.

CONTEXT:
- A multi-target Dockerfile exists (targets: base, api, worker, init-db, mock-claude)
- docker-compose.yml has postgres:15, redis:7, minio, jaeger
- docker-compose.e2e.yml is an overlay for E2E testing
- Settings are in src/core/config.py (Pydantic BaseSettings, loads from .env)
- The app has health endpoints: /health/liveness, /health/readiness
- Auth uses API keys stored in the database

TASKS:
1. Harden the Dockerfile:
   - Run as non-root user (add `useradd` and `USER` directive)
   - Add HEALTHCHECK CMD using curl to /health/liveness
   - Pin Python base image to specific digest
   - Add .dockerignore (exclude .git, .venv, tests/, docs/, __pycache__, .env, *.pyc)

2. Create docker-compose.prod.yml:
   - All credentials via environment variables (no hardcoded passwords)
   - Add the `api` and `worker` services
   - PostgreSQL with proper resource limits and backup volume
   - Redis with password and maxmemory policy
   - Remove jaeger and minio console port exposure
   - Add restart policies (unless-stopped)
   - Add logging driver configuration (json-file with max-size)
   - Network isolation: internal network for services, only api exposed

3. Create .env.production.template:
   - List all required env vars with placeholder values and comments
   - Include: DATABASE_URL, REDIS_URL, ANTHROPIC_API_KEY, S3_*, API secret key for signing
   - Document which vars are required vs optional

4. Create scripts/deploy.sh:
   - Build images with proper tags (git sha + latest)
   - Run database migrations (alembic upgrade head)
   - Seed initial API key
   - Start services
   - Wait for health checks to pass
   - Print status summary

5. Update the existing Dockerfile if needed to support the production compose file.

CONSTRAINTS:
- Do NOT remove the existing docker-compose.yml (it's for local dev)
- Do NOT modify source code — only Docker/deployment files
- Ensure docker-compose.prod.yml works standalone (not as overlay)
- Keep MinIO as the S3 backend (the app uses boto3 with S3_ENDPOINT)
```

---

## Agent 3: Frontend MVP (Upload + Results Viewer)

```
You are working on the DebtFund project at /Users/florianschabus/DebtFund.

GOAL: Build a minimal but polished frontend that lets users upload Excel files and view extraction results. Single-page app, no framework — just HTML/CSS/JS served by FastAPI.

CONTEXT:
- API endpoints (all require X-API-Key header):
  - POST /api/v1/files/upload — multipart form upload, returns {file_id, job_id, status}
  - GET /api/v1/jobs/{job_id} — returns {status, result, error_message, ...}. Status is one of: pending, processing, completed, failed
  - GET /api/v1/jobs/{job_id}/export?format=json — returns extraction result with line_items, sheets, triage, validation
  - GET /api/v1/jobs/{job_id}/export?format=csv — returns CSV download
- The result object contains:
  - sheets: list of sheet names
  - line_items: list of {sheet, original_label, canonical_name, values, confidence, hierarchy_level}
  - triage: list of {sheet_name, tier, decision, rationale}
  - validation: {overall_confidence, ...}
  - tokens_used, cost_usd
- CORS is configured for localhost:3000 in settings (update to also allow same-origin)

TASKS:
1. Create static/index.html — single page with:
   - Header: "DebtFund — Financial Model Extraction"
   - API key input field (stored in localStorage)
   - File upload zone (drag & drop + click to browse, .xlsx/.xls only)
   - Progress section: shows job status with polling (every 2 seconds)
   - Results section (appears when job completes):
     - Summary bar: sheets count, line items count, confidence %, cost, tokens
     - Tabs: "Line Items" | "Triage" | "Validation"
     - Line Items tab: sortable table with columns: Sheet, Label, Canonical Name, Confidence, Values
     - Triage tab: table showing sheet tier assignments with rationale
     - Validation tab: show overall confidence and any flags
     - Export buttons: "Download JSON" and "Download CSV"
   - Error display: show error_message if job fails

2. Create static/styles.css:
   - Clean, professional design (white background, subtle grays, blue accent)
   - Responsive layout (works on desktop and tablet)
   - Confidence badges: green (>0.8), yellow (0.5-0.8), red (<0.5)
   - Drag & drop zone with dashed border, highlight on hover
   - Loading spinner animation for processing state

3. Create static/app.js:
   - API client class with methods for upload, getJobStatus, exportResults
   - Polling logic with exponential backoff (2s → 4s → 8s, max 30s)
   - File drag & drop handler with type validation
   - Table rendering with sort-by-column support
   - localStorage for API key persistence
   - Error handling with user-friendly messages

4. Update src/api/main.py:
   - Mount static files: app.mount("/static", StaticFiles(directory="static"), name="static")
   - Add root route that serves index.html (or redirect / to /static/index.html)
   - Update CORS to allow same-origin requests

5. Test the frontend manually by describing how to:
   - Start the API server
   - Open the browser
   - Enter an API key
   - Upload a file
   - View results

CONSTRAINTS:
- No npm, no build step, no framework — vanilla HTML/CSS/JS only
- Must work when served by FastAPI's StaticFiles
- All API calls go through fetch() with proper headers
- Handle all error states: network error, 401 (bad key), 400 (bad file), 500 (server error)
- Keep it under 500 lines total across all 3 files
- Do NOT add any JavaScript dependencies (no CDN imports)
```

---

## Agent 4: CI/CD Pipeline with Docker Deploy

```
You are working on the DebtFund project at /Users/florianschabus/DebtFund.

GOAL: Extend the existing CI/CD pipeline to build Docker images and deploy to a target environment.

CONTEXT:
- .github/workflows/ci.yml exists with 3 jobs: lint, test, security
- Dockerfile has multi-target builds (api, worker, init-db)
- The app needs: PostgreSQL, Redis, MinIO (S3-compatible), and the API + worker services
- Tests run with pytest, coverage target is 80%
- There may be a docker-compose.prod.yml by the time this agent runs

TASKS:
1. Update .github/workflows/ci.yml to add a `build` job:
   - Runs after lint + test pass
   - Builds Docker images for api, worker, init-db targets
   - Tags with git SHA and "latest"
   - Pushes to GitHub Container Registry (ghcr.io)
   - Only runs on push to main branch (not on PRs)

2. Create .github/workflows/deploy.yml:
   - Triggered manually (workflow_dispatch) with environment input (staging/production)
   - Pulls the latest images from ghcr.io
   - Runs database migrations (alembic upgrade head) via init-db container
   - Deploys api and worker services
   - Runs smoke test: curl health endpoint, verify 200
   - Posts deployment status to GitHub deployment API

3. Update .github/workflows/ci.yml test job:
   - Add the E2E test suite (tests/e2e/test_local_e2e.py) as a separate step
   - Keep tests/e2e/test_real_claude.py excluded (requires real API key + costs money)

4. Create .github/dependabot.yml:
   - Weekly updates for pip dependencies
   - Weekly updates for GitHub Actions

5. Add branch protection rules documentation in a comment in ci.yml:
   - Require lint + test to pass before merge
   - Require PR reviews

CONSTRAINTS:
- Do NOT store secrets in the workflow files — use ${{ secrets.* }} references
- Keep the existing ci.yml jobs intact (lint, test, security)
- Use GitHub Container Registry (ghcr.io), not Docker Hub
- The deploy workflow should be environment-aware (staging vs production)
- Do NOT actually deploy anywhere — just create the pipeline that could deploy
```

---

## Agent 5: Entity Pattern Learning System

```
You are working on the DebtFund project at /Users/florianschabus/DebtFund.

GOAL: Implement the entity pattern learning system so the extraction pipeline improves over time based on corrections and repeated usage.

CONTEXT:
- The EntityPattern model exists in src/db/models.py:
  - Fields: id, entity_id, original_label, canonical_name, confidence, frequency, last_seen_at
  - Foreign key to entities table
- The Entity model exists: id, name, industry, created_at
- The enhanced_mapping stage (Stage 5) already has a _build_entity_context method that queries entity patterns
- The mapping stage (Stage 3) maps original_label → canonical_name with confidence scores
- data/taxonomy.json has 172+ canonical items organized by category

TASKS:
1. Create src/api/corrections.py — API endpoint for submitting corrections:
   - POST /api/v1/jobs/{job_id}/corrections
   - Body: list of {original_label, correct_canonical_name, sheet_name?}
   - For each correction:
     a. Upsert EntityPattern: if pattern exists for this entity+label, update canonical_name and bump confidence/frequency; if new, create with confidence=1.0
     b. Log to audit_logs
   - Return: {corrections_applied: int, patterns_updated: int, patterns_created: int}

2. Create src/extraction/pattern_matcher.py — pattern matching service:
   - Function: get_entity_patterns(entity_id: str, labels: list[str]) -> dict[str, PatternMatch]
   - Queries EntityPattern table for matching labels (case-insensitive, fuzzy threshold 0.85)
   - Returns dict mapping original_label → {canonical_name, confidence, source: "entity_pattern"}
   - Sorts by confidence * frequency for best match

3. Update src/extraction/stages/mapping.py (Stage 3):
   - Before calling Claude for mapping, check entity patterns first
   - If a pattern match exists with confidence >= 0.9, use it directly (skip Claude for that label)
   - If pattern match exists with confidence 0.7-0.9, include it as a hint in the Claude prompt
   - Track which mappings came from patterns vs Claude in the result metadata
   - This reduces API costs and improves speed for repeat entities

4. Update src/extraction/stages/enhanced_mapping.py (Stage 5):
   - After enhanced mapping completes, auto-learn: for any mapping with confidence >= 0.95, upsert an EntityPattern (only if entity_id is provided)
   - This creates a feedback loop: high-confidence extractions become patterns for next time

5. Add CRUD operations to src/db/crud.py:
   - upsert_entity_pattern(db, entity_id, original_label, canonical_name, confidence)
   - get_entity_patterns(db, entity_id, labels=None) — optional label filter
   - get_entity_pattern_stats(db, entity_id) — count, avg confidence, last updated

6. Write tests in tests/unit/test_pattern_learning.py:
   - Test correction submission creates patterns
   - Test pattern matcher returns matches
   - Test mapping stage uses patterns to skip Claude calls
   - Test auto-learning from high-confidence extractions
   - Test pattern confidence increases with repeated corrections

7. Wire the corrections endpoint into src/api/main.py.

CONSTRAINTS:
- Entity patterns are entity-specific — patterns for Entity A do not affect Entity B
- Pattern matching must be fast (< 50ms for 100 labels)
- Do NOT modify the existing mapping stage's Claude prompt format — only add pattern pre-filtering
- Maintain backward compatibility: if no entity_id is provided, skip all pattern logic
- Use the existing get_db() dependency for database access
```

---

## Agent 6: API Documentation & OpenAPI Polish

```
You are working on the DebtFund project at /Users/florianschabus/DebtFund.

GOAL: Ensure the API is fully documented via OpenAPI/Swagger so integrators can use it without reading source code.

CONTEXT:
- FastAPI auto-generates OpenAPI at /docs (Swagger UI) and /redoc
- Endpoints exist: upload, job status, export, taxonomy search, health checks
- Auth is via X-API-Key header (HTTPBearer)
- Response models are not explicitly defined (endpoints return dicts)

TASKS:
1. Create Pydantic response models in src/api/schemas.py:
   - UploadResponse: file_id, job_id, status, message
   - JobStatusResponse: job_id, status, created_at, completed_at, result (optional), error_message (optional)
   - ExportResponse: file_id, sheets, triage, line_items, validation, tokens_used, cost_usd
   - LineItemSchema: sheet, row, original_label, canonical_name, values, confidence, hierarchy_level
   - TriageEntrySchema: sheet_name, tier, decision, rationale
   - ValidationSchema: overall_confidence, flags, period_results
   - ErrorResponse: detail, status_code
   - HealthResponse: status, database, s3, version

2. Update all endpoints in src/api/main.py to use these response models:
   - Add response_model parameter to each route decorator
   - Add summary and description to each route
   - Add response examples using openapi_examples
   - Add proper status code documentation (responses={200: ..., 400: ..., 401: ...})

3. Add API metadata to the FastAPI app:
   - title: "DebtFund API"
   - description: Multi-line markdown explaining the platform
   - version: from pyproject.toml
   - contact, license info
   - Tag descriptions for grouping: "Extraction", "Taxonomy", "Health"

4. Group endpoints with tags:
   - Extraction: upload, job status, export, corrections
   - Taxonomy: search, browse
   - Health: liveness, readiness, database, metrics

5. Test that /docs renders correctly and all endpoints show examples.

CONSTRAINTS:
- Do NOT change endpoint behavior — only add type annotations and documentation
- Response models should match the actual response shapes exactly
- Keep backward compatibility (don't break existing clients)
- Use Pydantic v2 syntax (model_config, field_validator)
```

---

## Execution Order

| Priority | Agent | Why | Depends On |
|----------|-------|-----|------------|
| 1 | **Agent 1: Stabilize & Commit** | Everything else builds on clean, passing code | Nothing |
| 2 | **Agent 3: Frontend MVP** | Users need a way to interact with the product | Agent 1 |
| 3 | **Agent 2: Production Docker** | Can't deploy without proper containers | Agent 1 |
| 4 | **Agent 6: API Documentation** | Integrators need docs, Swagger UI is free UX | Agent 1 |
| 5 | **Agent 5: Entity Pattern Learning** | Core product differentiator, but not launch-blocking | Agent 1 |
| 6 | **Agent 4: CI/CD Pipeline** | Automates deployment, but manual deploy works for MVP | Agents 1, 2 |

**Estimated effort**: Agents 1-3 get you to a deployable MVP with a UI. Agents 4-6 add polish and intelligence.
