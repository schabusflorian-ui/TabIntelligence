# Structured JSON Logging Verification Guide

## Overview

This guide helps you verify that structured JSON logging is working correctly with correlation IDs.

## Prerequisites

1. Distributed tracing set up (see [distributed_tracing_verification.md](distributed_tracing_verification.md))
2. Dependencies installed

## Step 1: Enable JSON Logging

```bash
# Set environment variable to enable JSON logging
export LOG_FORMAT=json

# Or for one-time testing:
LOG_FORMAT=json uvicorn src.api.main:app --reload
```

## Step 2: Start the API

```bash
# Terminal 1
LOG_FORMAT=json uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

## Step 3: Make a Test Request

```bash
# Terminal 2
curl -X GET "http://localhost:8000/health/liveness" \
  -H "X-Request-ID: test-request-123"
```

## Step 4: Check Log Output

### Console Output

You should see JSON-formatted logs like:
```json
{
  "timestamp": 1709138400.123,
  "level": "INFO",
  "logger": "debtfund.api",
  "message": "Liveness check",
  "trace_id": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6",
  "request_id": "test-request-123",
  "service": "debtfund",
  "environment": "development"
}
```

### File Output

Check the log file:
```bash
tail -f logs/debtfund.log
```

You should see the same JSON format.

## Step 5: Parse Logs with jq

JSON logs can be easily parsed and filtered:

```bash
# View all logs formatted nicely
tail -f logs/debtfund.log | jq .

# Filter by log level
tail -f logs/debtfund.log | jq 'select(.level == "ERROR")'

# Extract just messages
tail -f logs/debtfund.log | jq -r '.message'

# Find all logs for a specific request
tail -f logs/debtfund.log | jq 'select(.request_id == "test-request-123")'

# Find all logs for a specific trace
tail -f logs/debtfund.log | jq 'select(.trace_id | startswith("a1b2c3"))'
```

## Step 6: Verify Correlation IDs

Make multiple requests and verify correlation:

```bash
# Request 1
curl -X POST "http://localhost:8000/api/v1/files/upload" \
  -H "X-Request-ID: req-001" \
  -F "file=@test_data/sample_model.xlsx"

# Wait a moment, then request 2
curl -X POST "http://localhost:8000/api/v1/files/upload" \
  -H "X-Request-ID: req-002" \
  -F "file=@test_data/sample_model.xlsx"
```

Check logs:
```bash
# All logs for request 1
cat logs/debtfund.log | jq 'select(.request_id == "req-001")'

# Should show: upload → database create → celery enqueue
```

## Step 7: Verify Request ID in Response

```bash
curl -v -X GET "http://localhost:8000/health/liveness"
```

Check response headers:
```
< HTTP/1.1 200 OK
< X-Request-ID: <some-uuid>
```

If you provide a request ID:
```bash
curl -v -X GET "http://localhost:8000/health/liveness" \
  -H "X-Request-ID: my-custom-id"
```

Response should echo it back:
```
< X-Request-ID: my-custom-id
```

## Step 8: Verify Trace ID Integration

With both tracing and logging enabled:

```bash
# Make a request
curl -X POST "http://localhost:8000/api/v1/files/upload" \
  -F "file=@test_data/sample_model.xlsx"

# Check logs for trace_id
tail -n 50 logs/debtfund.log | jq 'select(.trace_id != "no-trace")'
```

You should see the same `trace_id` in:
1. API logs
2. Celery worker logs
3. Jaeger UI (http://localhost:16686)

## Troubleshooting

### Logs are still plain text

**Cause:** LOG_FORMAT environment variable not set

**Fix:**
```bash
export LOG_FORMAT=json
# Or in docker-compose.yml:
environment:
  - LOG_FORMAT=json
```

### JSON parsing errors with jq

**Cause:** Some log lines might not be JSON (e.g., from third-party libraries)

**Fix:** Filter for valid JSON:
```bash
tail -f logs/debtfund.log | jq -R 'fromjson? | select(. != null)'
```

### trace_id shows "no-trace"

**Cause:** Distributed tracing not initialized

**Fix:** Ensure tracing is set up (see [distributed_tracing_verification.md](distributed_tracing_verification.md))

### request_id shows "no-request"

**Cause:** Request ID middleware not active

**Fix:** Verify RequestIDMiddleware is added in [main.py](../../src/api/main.py)

## Comparison: Plain vs JSON Logging

### Plain Text (Development)
```bash
# Start without JSON
uvicorn src.api.main:app --reload
```

Output:
```
2024-02-28 10:30:45 - debtfund.api - INFO - Liveness check
```

### JSON Format (Production)
```bash
# Start with JSON
LOG_FORMAT=json uvicorn src.api.main:app --reload
```

Output:
```json
{"timestamp": 1709138400.123, "level": "INFO", "logger": "debtfund.api", "message": "Liveness check", "trace_id": "abc123", "request_id": "req-001"}
```

**Benefits of JSON:**
- Machine-parseable for log aggregation (Elasticsearch, CloudWatch)
- Easy filtering with jq or log analysis tools
- Correlation IDs for debugging
- Structured fields for alerting

## Success Criteria

✅ Logs output in JSON format when LOG_FORMAT=json
✅ Every log line includes: timestamp, level, logger, message
✅ Correlation IDs present: trace_id, request_id
✅ Request ID returned in response headers (X-Request-ID)
✅ jq can parse logs without errors
✅ Can correlate logs across API and Celery using request_id
✅ Can correlate logs across services using trace_id

## Next Steps

With structured logging complete, the next production features are:

1. **Dead Letter Queue** - Prevent data loss on task failures
2. **Idempotency Keys** - Prevent duplicate processing
3. **Prometheus Metrics** - Add business and infrastructure metrics
4. **Kubernetes Deployment** - Production deployment configs

See the [Production Excellence Plan](../plans/compressed-stirring-minsky.md) for details.
