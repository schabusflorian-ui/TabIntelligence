# ADR-001: API Authentication and Security Hardening

## Status
Accepted

## Date
2026-02-24

## Context

The DebtFund API had critical security vulnerabilities that posed serious production risks:

1. **No Authentication**: Both endpoints (`/api/v1/files/upload` and `/api/v1/jobs/{job_id}`) were completely exposed without authentication, despite having a complete auth infrastructure implemented at `src/auth/`
2. **CORS Wildcard**: The API allowed requests from any origin (`allow_origins=["*"]`), making it vulnerable to CSRF attacks
3. **No File Size Validation**: The API would attempt to read files of any size into memory, risking OOM crashes
4. **No Rate Limiting**: The API had no protection against DoS attacks or abuse

These vulnerabilities could result in:
- Unauthorized access and cost abuse (Claude API costs)
- CSRF attacks from malicious websites
- Server crashes from oversized file uploads
- DoS attacks overwhelming the service

## Decision

We implemented comprehensive API security hardening:

### 1. Authentication Required on All Endpoints

Added authentication to all API endpoints using the existing auth infrastructure:

```python
from src.auth.dependencies import get_current_api_key
from src.auth.models import APIKey

@app.post("/api/v1/files/upload")
async def upload_file(
    file: UploadFile,
    api_key: APIKey = Depends(get_current_api_key),  # Authentication required
    ...
)
```

The authentication system:
- Uses HTTP Bearer token authentication (`Authorization: Bearer <api_key>`)
- Validates API keys against SHA256 hashes stored in the database
- Checks that keys are active (`is_active=True`)
- Updates `last_used_at` timestamp for monitoring
- Returns 401 Unauthorized for invalid or inactive keys

### 2. Restricted CORS Configuration

Changed from wildcard to configured origins:

**Before:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # DANGEROUS
    ...
)
```

**After:**
```python
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # Configured origins only
    allow_credentials=True,  # Required for auth
    ...
)
```

Updated `src/core/config.py`:
```python
cors_origins: list = Field(
    default=["http://localhost:3000"],  # Safe default
    description="CORS allowed origins (comma-separated list for security)"
)
```

### 3. File Size Validation (100MB Limit)

Added file size validation before reading files into memory:

```python
# Define max file size (100MB)
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

# Check file size without loading into memory
file.file.seek(0, 2)  # Seek to end
file_size = file.file.tell()
file.file.seek(0)  # Reset to beginning

if file_size > MAX_FILE_SIZE:
    raise HTTPException(
        status_code=413,
        detail=f"File too large. Maximum size is {MAX_FILE_SIZE / (1024*1024):.0f}MB"
    )

# Now safe to read
file_bytes = await file.read()
```

This prevents OOM crashes from malicious large file uploads.

### 4. Rate Limiting

Implemented rate limiting using `slowapi`:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/api/v1/files/upload")
@limiter.limit("100/hour")  # 100 requests per hour per IP
async def upload_file(...):
    ...

@app.get("/api/v1/jobs/{job_id}")
@limiter.limit("500/hour")  # Higher limit for status checks
async def get_job_status(...):
    ...
```

Rate limits:
- Upload endpoint: 100 requests/hour per IP
- Job status endpoint: 500 requests/hour per IP (higher for polling)
- Returns 429 Too Many Requests when exceeded

## Consequences

### Positive

1. **Security**: API is now protected from unauthorized access, CSRF attacks, DoS attacks, and resource exhaustion
2. **Cost Control**: Authentication prevents cost abuse of Claude API
3. **Reliability**: File size limits and rate limiting protect server resources
4. **Audit Trail**: API key usage is logged with `last_used_at` timestamps
5. **Compliance**: Proper authentication is a requirement for production deployment

### Negative

1. **Client Complexity**: Clients must now manage API keys and include Authorization headers
2. **Development Friction**: Local development requires API key setup
3. **Rate Limit Management**: Legitimate high-volume users may need custom rate limits

### Neutral

1. **Breaking Change**: Existing API clients (if any) will need to add authentication
2. **Migration Required**: API keys must be created before the API can be used

## Implementation Details

### Files Modified

1. **src/api/main.py**:
   - Added authentication dependencies to endpoints
   - Fixed CORS configuration
   - Added file size validation
   - Implemented rate limiting

2. **src/core/config.py**:
   - Changed `cors_origins` default from `["*"]` to `["http://localhost:3000"]`

3. **pyproject.toml**:
   - Added `slowapi>=0.1.9` dependency

4. **.env.example**:
   - Updated CORS_ORIGINS documentation with secure examples

### Dependencies Added

- `slowapi>=0.1.9` - Rate limiting middleware for FastAPI

## Alternatives Considered

### 1. Optional Authentication
**Rejected**: Would not solve the cost abuse problem. Authentication must be required for production.

### 2. Higher File Size Limits
**Rejected**: 100MB is sufficient for Excel files. Larger limits increase OOM risk.

### 3. Per-API-Key Rate Limits
**Future Enhancement**: Current implementation uses IP-based rate limiting. Future versions could implement per-API-key rate limits using the `APIKey.rate_limit_per_minute` field that already exists in the database model.

### 4. JWT Tokens
**Rejected**: API keys are simpler and more appropriate for machine-to-machine authentication. The existing system uses SHA256-hashed API keys which are secure and performant.

## Verification

To verify the implementation:

1. **Authentication works**:
   ```bash
   # Without API key (should fail with 401)
   curl -X POST http://localhost:8000/api/v1/files/upload -F "file=@test.xlsx"

   # With API key (should succeed)
   curl -X POST http://localhost:8000/api/v1/files/upload \
     -H "Authorization: Bearer <api_key>" \
     -F "file=@test.xlsx"
   ```

2. **File size validation works**:
   ```bash
   # Create 150MB file
   dd if=/dev/zero of=large.xlsx bs=1M count=150

   # Should return 413 Request Entity Too Large
   curl -X POST http://localhost:8000/api/v1/files/upload \
     -H "Authorization: Bearer <api_key>" \
     -F "file=@large.xlsx"
   ```

3. **Rate limiting works**:
   ```bash
   # Make 101 requests rapidly
   for i in {1..101}; do
     curl -X POST http://localhost:8000/api/v1/files/upload \
       -H "Authorization: Bearer <api_key>" \
       -F "file=@test.xlsx"
   done
   # Last request should return 429 Too Many Requests
   ```

4. **CORS restriction works**:
   - Access API from unauthorized origin (should fail)
   - Access API from configured origin (should succeed)

## Migration Guide

### For API Users

1. **Obtain API Key**:
   - Contact system administrator to create an API key
   - Store key securely (environment variable, secrets manager)

2. **Update API Calls**:
   ```python
   # Before
   response = requests.post(
       "http://localhost:8000/api/v1/files/upload",
       files={"file": open("data.xlsx", "rb")}
   )

   # After
   response = requests.post(
       "http://localhost:8000/api/v1/files/upload",
       headers={"Authorization": f"Bearer {api_key}"},
       files={"file": open("data.xlsx", "rb")}
   )
   ```

3. **Handle Rate Limits**:
   - Implement exponential backoff for 429 responses
   - Monitor rate limit headers if implemented

### For Administrators

1. **Configure CORS**:
   ```bash
   # In .env file
   CORS_ORIGINS=["http://localhost:3000","https://app.debtfund.com"]
   ```

2. **Create API Keys**:
   ```python
   # Using the existing API key creation system
   from src.auth.api_key import create_api_key

   api_key_str = create_api_key(
       db=db,
       name="Production Client",
       entity_id=entity_id,
       rate_limit_per_minute=60
   )
   ```

3. **Monitor Usage**:
   - Check `api_keys.last_used_at` for inactive keys
   - Monitor rate limit violations in logs
   - Review authentication failures

## References

- FastAPI Security: https://fastapi.tiangolo.com/tutorial/security/
- SlowAPI Documentation: https://slowapi.readthedocs.io/
- OWASP API Security: https://owasp.org/www-project-api-security/

## Notes

- The auth infrastructure (`src/auth/`) was already fully implemented but unused
- This ADR focuses on wiring up existing auth, not designing new auth
- Rate limits are per-IP, not per-API-key (future enhancement opportunity)
- File size limit (100MB) is separate from the `MAX_FILE_SIZE_MB` config setting
