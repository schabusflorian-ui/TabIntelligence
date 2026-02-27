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

COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[dev]"

COPY src/ ./src/
COPY data/ ./data/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/
COPY tests/ ./tests/

# --- API server ---
FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- Celery worker ---
FROM base AS worker
CMD ["celery", "-A", "src.jobs.celery_app", "worker", \
     "--loglevel=info", "--concurrency=1", \
     "--max-tasks-per-child=10", "--without-heartbeat"]

# --- Database init (one-shot) ---
FROM base AS init-db
COPY scripts/init_e2e_db.py ./scripts/init_e2e_db.py
CMD ["python", "scripts/init_e2e_db.py"]

# --- Mock Claude API server (minimal image) ---
FROM python:3.11-slim AS mock-claude
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn
COPY tests/e2e/mock_claude_server.py ./mock_claude_server.py
EXPOSE 8080
CMD ["uvicorn", "mock_claude_server:app", "--host", "0.0.0.0", "--port", "8080"]
