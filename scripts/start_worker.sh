#!/bin/bash
# Start Celery worker for TabIntelligence extraction queue

set -e

echo "Starting Celery worker for TabIntelligence..."

# Start worker with logging
celery -A src.jobs.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --hostname=worker-extraction@%h \
    --max-tasks-per-child=50 \
    --time-limit=600 \
    --soft-time-limit=300 \
    --logfile=logs/celery-worker.log

echo "Celery worker stopped"
