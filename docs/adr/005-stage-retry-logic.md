# ADR-005: Retry Logic for All Extraction Stages

## Status
Accepted

## Date
2026-02-24

## Context

The extraction pipeline uses Claude API for three critical stages:
1. **Stage 1 (Parsing)**: Parse Excel file structure and extract financial data
2. **Stage 2 (Triage)**: Classify sheets into processing tiers
3. **Stage 3 (Mapping)**: Map line items to canonical taxonomy

### Problem

Only Stage 1 had retry logic with exponential backoff. Stages 2 and 3 would fail immediately on any Claude API error, including:
- Rate limits (429 errors)
- Transient network failures
- Claude API unavailability (529 errors)
- Timeout errors

This created several issues:

1. **Wasted API Costs**: A transient error in Stage 2 or 3 would cause the entire job to fail, even though Stage 1 (the most expensive stage) had already succeeded. The job would need to be restarted from scratch.

2. **Inconsistent Error Handling**: Different stages had different resilience characteristics. This made the system unpredictable under load.

3. **Poor User Experience**: Jobs would fail without exhausting retry attempts, requiring manual intervention.

### Prior Implementation

**Stage 1** (had retry logic):
```python
async def stage_1_parsing(file_bytes: bytes) -> dict:
    max_retries = 3
    retry_count = 0
    backoff_base = 2

    while retry_count < max_retries:
        try:
            # ... Claude API call ...
        except anthropic.RateLimitError:
            # Retry with exponential backoff
```

**Stages 2 & 3** (no retry logic):
```python
async def stage_2_triage(parsed_result: dict) -> dict:
    response = get_claude_client().messages.create(...)
    # No try/except, no retries - immediate failure
```

### Silent JSON Parse Failures

Additionally, the `_extract_json()` helper would silently return an empty dict `{}` on JSON parse errors. This prevented retry logic from working because no exception was raised.

## Decision

We implemented consistent retry logic across all stages and fixed silent failures:

### 1. Created Reusable Retry Decorator

Created `/src/core/retry.py` with a decorator that:
- Supports configurable max attempts and backoff timing
- Uses exponential backoff (2s, 4s, 8s)
- Automatically injects attempt number into functions
- Logs retry attempts with detailed context
- Works with async functions

### 2. Applied Retry Decorator to Stages 2 & 3

Added `@retry(max_attempts=3, backoff_seconds=2)` to both stage functions, matching Stage 1's retry behavior.

### 3. Fixed Silent JSON Parse Failures

Changed `_extract_json()` to raise `ExtractionError` on parse failures instead of returning empty dict. This ensures:
- JSON parse errors trigger retries
- Errors are logged with content preview for debugging
- System doesn't silently proceed with empty data

### 4. Enhanced Error Handling in Stages

Added comprehensive try/except blocks to catch specific exceptions:
- `anthropic.RateLimitError` → raises `RateLimitError`
- `anthropic.APIError` → raises `ClaudeAPIError` with status code
- Generic exceptions → raises `ExtractionError` with stage context

### 5. Added Performance Logging

Each stage now logs:
- Attempt number (1/3, 2/3, 3/3)
- Duration and token usage
- Success/failure with context

## Implementation

### Retry Decorator (`src/core/retry.py`)

```python
def retry(max_attempts: int = 3, backoff_seconds: int = 2):
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            for attempt in range(1, max_attempts + 1):
                try:
                    # Inject attempt number if function accepts it
                    if 'attempt' in func.__code__.co_varnames:
                        kwargs['attempt'] = attempt
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt < max_retries:
                        wait_time = backoff_seconds * (2 ** (attempt - 1))
                        await asyncio.sleep(wait_time)
                    else:
                        raise
            raise last_exception
        return wrapper
    return decorator
```

### Stage 2 with Retry

```python
@retry(max_attempts=3, backoff_seconds=2)
async def stage_2_triage(parsed_result: dict, attempt: int = 1) -> dict:
    logger.info(f"Stage 2: Triage - Attempt {attempt}/3")

    try:
        response = get_claude_client().messages.create(...)
        # ... process response ...

    except anthropic.RateLimitError as e:
        raise RateLimitError("Rate limit exceeded", stage="triage")
    except anthropic.APIError as e:
        raise ClaudeAPIError(str(e), stage="triage", retry_count=attempt)
```

### Fixed JSON Parser

```python
def _extract_json(content: str) -> Union[dict, list]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try markdown code blocks...

    # If all attempts fail, raise error (don't silently return {})
    raise ExtractionError(
        f"Claude returned invalid JSON: {str(e)}",
        stage="json_parsing"
    )
```

### Files Modified

- `src/core/retry.py` - New file with retry decorator
- `src/extraction/orchestrator.py` - Added retry to stages 2 & 3, fixed JSON parser
  - Added `@retry` decorator to `stage_2_triage()`
  - Added `@retry` decorator to `stage_3_mapping()`
  - Modified `_extract_json()` to raise errors instead of returning `{}`
  - Added import for retry decorator

## Consequences

### Positive

1. **Cost Reduction**: Transient failures no longer waste the expensive Stage 1 parsing costs. If Stage 2 or 3 hits a rate limit, they retry instead of failing the entire job.

2. **Improved Reliability**: System can handle temporary Claude API issues (rate limits, brief outages) without manual intervention.

3. **Consistent Architecture**: All stages have identical retry behavior (3 attempts, exponential backoff), making the system predictable.

4. **Better Debugging**:
   - Retry attempts are logged with context
   - JSON parse errors show content preview
   - Clear distinction between transient and permanent failures

5. **EXISTENTIAL Alignment**: Failed jobs can now be attributed to permanent errors (bad data, invalid format) vs. transient errors (rate limits, network blips).

### Negative

1. **Increased Job Duration**: Jobs that encounter transient errors will take longer (2s + 4s + 8s = 14s additional time per stage with all retries exhausted).

2. **Potential for Cascading Delays**: If Claude API is experiencing widespread issues, many jobs will retry simultaneously, potentially amplifying load.

### Mitigations

- **Max Attempts Limited to 3**: Prevents excessive retry loops
- **Exponential Backoff**: Spreads out retry load over time
- **Final Exception Raised**: After 3 attempts, system fails fast and reports error

## Testing Considerations

### Unit Tests

Should verify:
- Retry decorator successfully retries on exceptions
- Attempt number increments correctly (1, 2, 3)
- Exponential backoff waits correct durations (2s, 4s, 8s)
- Final exception is raised after max attempts
- _extract_json() raises ExtractionError on parse failures

### Integration Tests

Should verify:
- Stages 2 and 3 retry on rate limits
- Jobs complete successfully after transient failures
- Retry attempts appear in logs with correct metadata
- JSON parse errors trigger retries (not silent failures)

### Load Testing

Should verify:
- System handles Claude API rate limits gracefully
- Exponential backoff prevents thundering herd
- Jobs eventually succeed under sustained load

## Related ADRs

- ADR-004: Lineage Transactions (addresses lineage persistence safety)

## Notes

This fix was identified during Week 1 audit of the extraction pipeline. The inconsistent retry behavior was particularly problematic during development when Claude API rate limits were frequently hit.

Key insight: The most expensive operation (Stage 1 parsing with document upload) was already protected by retries. Not protecting Stages 2 and 3 meant throwing away that investment on transient failures.

## Future Enhancements

Consider for later:
- Circuit breaker pattern to detect sustained Claude API failures
- Jitter in backoff timing to prevent synchronized retry storms
- Configurable retry parameters per stage based on cost/criticality
- Retry budget tracking to prevent excessive retries across all jobs
