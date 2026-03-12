# =============================================================================
# DebtFund Multi-Target Dockerfile
# =============================================================================
# Targets: api, worker, init-db, mock-claude
# Build:   docker build --target api -t debtfund-api .
# =============================================================================

# --- Base stage: shared dependencies + source ---
FROM python:3.11-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home appuser

COPY pyproject.toml ./

# --- Production base: only production dependencies ---
FROM base AS prod-base
RUN pip install --no-cache-dir .

COPY src/ ./src/
COPY data/ ./data/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/

# Ensure appuser owns the app directory
RUN chown -R appuser:appuser /app

# --- Dev base: includes dev/test dependencies ---
FROM base AS dev-base
RUN pip install --no-cache-dir ".[dev]"

COPY src/ ./src/
COPY data/ ./data/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/
COPY tests/ ./tests/

# --- API server ---
FROM prod-base AS api
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.api.main:app --host 0.0.0.0 --port 8000"]

# --- Celery worker ---
FROM prod-base AS worker
USER appuser
CMD ["sh", "-c", "alembic upgrade head && celery -A src.jobs.celery_app worker --loglevel=info --concurrency=1 --max-tasks-per-child=10 --without-heartbeat"]

# --- Database init (one-shot) ---
FROM prod-base AS init-db
COPY scripts/init_e2e_db.py ./scripts/init_e2e_db.py
USER appuser
CMD ["python", "scripts/init_e2e_db.py"]

# --- Mock Claude API server (minimal image, dev only) ---
FROM python:3.11-slim AS mock-claude
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn
COPY tests/e2e/mock_claude_server.py ./mock_claude_server.py
EXPOSE 8080
CMD ["uvicorn", "mock_claude_server:app", "--host", "0.0.0.0", "--port", "8080"]
