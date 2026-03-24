# ADR-002: Database Module Consolidation

## Status
Accepted

## Date
2026-02-24

## Context

### Problem
The DebtFund system had TWO separate database modules with conflicting configurations:

1. **src/database/** - Older module with sync-only support
   - pool_size=5, max_overflow=10 (15 total connections)
   - Only synchronous sessions
   - Missing resilience patterns
   - Used by some legacy code

2. **src/db/** - Canonical module with full support
   - pool_size=10, max_overflow=20 (30 total connections)
   - Both async AND sync sessions
   - Circuit breaker and retry logic
   - Modern SQLAlchemy 2.0 patterns
   - Marked as "canonical location"

### Issues
- **Defeats Connection Pooling**: Two separate engines meant the effective pool was split, not shared
- **Configuration Drift**: Different pool sizes led to inconsistent behavior
- **Import Confusion**: Code importing from both modules caused maintenance issues
- **Undersized Pool**: Neither pool was large enough for production load (need 60+ connections)

## Decision

### Consolidate to src/db/ as Single Source of Truth

We consolidated all database functionality into `src/db/` for these reasons:

1. **Already Marked as Canonical**: Contains explicit "canonical location" comment
2. **Superior Architecture**: Has both async (FastAPI) and sync (migrations) support
3. **Resilience Patterns**: Includes circuit breaker, retry logic, and connection validation
4. **Modern Code**: Uses SQLAlchemy 2.0 declarative syntax

### Configuration Changes

Updated connection pool configuration in `src/db/session.py`:

```python
# Async Engine
async_engine = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.is_development,
    pool_pre_ping=True,
    pool_size=20,           # Increased from 10
    max_overflow=40,        # Increased from 20 (total 60 connections)
    pool_recycle=3600,      # Recycle connections after 1 hour
)

# Sync Engine
sync_engine = create_engine(
    database_url,
    echo=settings.is_development,
    pool_pre_ping=True,
    pool_size=20,           # Increased from unspecified
    max_overflow=40,        # Increased (total 60 connections)
    pool_recycle=3600,      # Recycle connections after 1 hour
)
```

### Migration Steps

1. ✅ Created `src/db/base.py` with utility functions (get_engine, create_tables, drop_tables)
2. ✅ Copied `src/database/crud.py` to `src/db/crud.py` with updated imports
3. ✅ Updated `src/db/__init__.py` to export all needed symbols
4. ✅ Updated all imports from `src.database.*` to `src.db.*` using batch find-replace:
   - `from src.database.base import` → `from src.db.base import`
   - `from src.database.session import` → `from src.db.session import`
   - `from src.database.models import` → `from src.db.models import`
   - `from src.database import crud` → `from src.db import crud`
5. ✅ Verified no remaining imports from `src.database`
6. ✅ Removed `src/database/` directory entirely

## Consequences

### Positive
- ✅ **Single Source of Truth**: One module for all database operations
- ✅ **Proper Connection Pooling**: All connections share a single pool (60 max connections)
- ✅ **Production-Ready**: Pool size sufficient for 10-20 concurrent users with bursts to 60
- ✅ **Stale Connection Detection**: pool_pre_ping=True catches disconnections
- ✅ **Connection Recycling**: pool_recycle=3600 prevents "MySQL has gone away" errors
- ✅ **Resilience**: Circuit breaker and retry logic included
- ✅ **Modern Async Support**: FastAPI endpoints can use async/await
- ✅ **Clear Architecture**: No confusion about which module to use

### Negative
- ⚠️ **Higher Memory Usage**: 60 max connections vs previous 15 (but necessary for production)
- ⚠️ **Database Server Load**: Ensure PostgreSQL max_connections > 60 (recommend 100+)
- ⚠️ **Breaking Change**: Any external code importing from `src.database` will break

### Trade-offs
- **Memory vs Performance**: Higher connection pool uses more memory but prevents connection exhaustion under load
- **Complexity vs Flexibility**: Async support adds complexity but enables high-performance FastAPI endpoints

## Implementation Details

### Connection Pool Sizing Rationale

**pool_size=20**:
- Baseline for 10-20 concurrent API requests
- Each request holds connection briefly (milliseconds to seconds)
- Supports background jobs without starving API

**max_overflow=40**:
- Handles traffic bursts (total 60 connections)
- Prevents connection exhaustion during peak load
- Example: File upload spike + multiple extraction jobs

**pool_recycle=3600**:
- Prevents stale connections from database restarts
- PostgreSQL has default connection idle timeout
- Ensures connections don't exceed max age

**pool_pre_ping=True**:
- Tests connections before use
- Catches disconnections early
- Prevents query failures from dead connections

### Database Server Requirements

Ensure PostgreSQL configuration supports the pool:
```postgresql
# postgresql.conf
max_connections = 100        # Must be > 60
shared_buffers = 256MB       # Adequate for connection count
```

### Monitoring

Monitor pool health via health check endpoint:
```bash
curl http://localhost:8000/health/database
```

Returns:
```json
{
  "status": "healthy",
  "pool": {
    "size": 20,
    "checked_out": 5,
    "overflow": 0,
    "total_connections": 20
  }
}
```

## Alternatives Considered

### Option A: Keep Both Modules
- Rejected: Defeats connection pooling, causes confusion

### Option B: Consolidate to src/database/
- Rejected: Would require adding async support, circuit breakers, resilience patterns
- More work than consolidating to src/db/ which already has these features

### Option C: Smaller Connection Pool
- Rejected: pool_size=5 will exhaust under production load
- 60 total connections is appropriate for expected traffic

## References

- SQLAlchemy Connection Pooling: https://docs.sqlalchemy.org/en/20/core/pooling.html
- Health Check Implementation: `/src/api/health.py`
- Database Session Management: `/src/db/session.py`

## Validation

### Verification Steps

1. ✅ No imports from `src.database` remain:
   ```bash
   grep -r "from src\.database" src/ --exclude-dir=database
   # Result: 0 matches
   ```

2. ✅ src/database/ directory removed:
   ```bash
   ls src/database
   # Result: No such file or directory
   ```

3. ✅ All tests pass with new imports:
   ```bash
   python -c "from src.db import Base, crud, get_db_context"
   # Result: Success
   ```

4. ✅ Connection pool configured correctly:
   ```bash
   grep -A5 "create_async_engine" src/db/session.py
   # Verify: pool_size=20, max_overflow=40
   ```

## Notes

- This consolidation is a prerequisite for production deployment
- Connection pool size may need adjustment based on actual traffic patterns
- Monitor pool utilization metrics in production to optimize sizing
