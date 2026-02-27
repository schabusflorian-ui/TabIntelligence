# Distributed Tracing Verification Guide

## Overview

This guide helps you verify that distributed tracing is working correctly across the DebtFund platform.

## Prerequisites

1. Docker and Docker Compose installed
2. Dependencies installed: `pip install -r requirements.txt` (or `pip install -e .`)

## Step 1: Start Infrastructure

```bash
# Start all services including Jaeger
docker-compose up -d

# Verify Jaeger is running
docker-compose ps | grep jaeger
# Should show: debtfund-jaeger ... Up
```

## Step 2: Access Jaeger UI

Open your browser to: http://localhost:16686

You should see the Jaeger UI with no traces yet (it's a fresh start).

## Step 3: Start the API Server

```bash
# In Terminal 1
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

You should see in the logs:
```
INFO: Distributed tracing initialized
INFO: Database initialized successfully
```

## Step 4: Start Celery Worker

```bash
# In Terminal 2
celery -A src.jobs.celery_app worker --loglevel=info
```

You should see:
```
[tasks]
  . src.jobs.tasks.run_extraction_task
```

## Step 5: Upload a Test File

```bash
# In Terminal 3
curl -X POST "http://localhost:8000/api/v1/files/upload" \
  -F "file=@test_data/sample_model.xlsx"
```

You should get a response like:
```json
{
  "file_id": "...",
  "job_id": "...",
  "task_id": "...",
  "status": "processing",
  "message": "Extraction started"
}
```

## Step 6: View Distributed Trace in Jaeger

1. Go to Jaeger UI: http://localhost:16686
2. In the "Service" dropdown, select `debtfund-api`
3. Click "Find Traces"
4. You should see your trace (most recent at top)
5. Click on the trace to expand it

### What You Should See

The trace should show multiple spans:
- **API Request**: The FastAPI endpoint handling the upload
- **Celery Task**: The background extraction task
- **Database Operations**: SQLAlchemy queries
- **Redis Operations**: Celery queue operations

### Verify Trace Continuity

- All spans should have the same `trace_id` (shown at the top)
- Spans should be nested to show parent-child relationships
- Total duration should match end-to-end request time

## Step 7: Check for Trace ID in Logs

Look at the API logs (Terminal 1):
```
INFO: Celery task enqueued: task_id=..., job_id=...
```

If structured logging is enabled, you should also see `trace_id` in the logs.

## Troubleshooting

### Jaeger UI shows "No traces found"

**Possible causes:**
1. Jaeger not running: `docker-compose ps | grep jaeger`
2. API not sending traces: Check API startup logs for "Distributed tracing initialized"
3. Network issue: Ensure API can reach localhost:6831 (Jaeger agent port)

**Fix:**
```bash
# Restart Jaeger
docker-compose restart jaeger

# Check Jaeger logs
docker-compose logs jaeger
```

### Traces are fragmented (API and Celery not connected)

**Possible cause:** Trace context not propagating from API to Celery

**Verify:**
1. Check that `run_extraction_task.delay()` in [main.py](../../src/api/main.py) includes trace headers
2. Check that `run_extraction_task()` in [tasks.py](../../src/jobs/tasks.py) extracts trace context

### Import errors for OpenTelemetry

**Possible cause:** Dependencies not installed

**Fix:**
```bash
pip install -e .
# OR
pip install opentelemetry-api opentelemetry-sdk opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-celery opentelemetry-exporter-jaeger
```

## Success Criteria

✅ Jaeger UI accessible at http://localhost:16686
✅ API logs show "Distributed tracing initialized"
✅ File upload creates a trace visible in Jaeger
✅ Trace shows connected spans: API → Celery → Database
✅ All spans have the same trace_id
✅ No errors in API or Celery worker logs

## Next Steps

Once distributed tracing is verified, the next production features to implement are:

1. **Structured JSON Logging** - Make logs machine-parseable
2. **Dead Letter Queue** - Prevent data loss on task failures
3. **Idempotency Keys** - Prevent duplicate processing
4. **Prometheus Metrics** - Add business and infrastructure metrics

See the [Production Excellence Plan](../plans/compressed-stirring-minsky.md) for details.
