# Lineage Tracking - Quick Start Guide

## Prerequisites
- Docker and Docker Compose installed
- Python 3.11+
- DebtFund codebase

## Quick Verification (5 minutes)

### Step 1: Start Services
```bash
cd /Users/florianschabus/DebtFund
docker-compose up -d postgres redis
```

### Step 2: Install Dependencies
```bash
pip install -e ".[dev]"
```

### Step 3: Initialize Database
```bash
python scripts/init_db.py
```

Expected output:
```
INFO - Database engine created: localhost:5432/emi
INFO - Async session factory created
INFO - Database initialized - all tables created
INFO - Database initialization complete!
```

### Step 4: Run Unit Tests
```bash
pytest tests/unit/test_lineage.py -v
```

Expected: Tests pass (or skip if DB not ready)

### Step 5: Verify Database Schema
```bash
docker exec -it debtfund-postgres-1 psql -U emi -d emi -c "\d lineage_events"
```

Expected: Table structure displayed

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                  Extraction Pipeline                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  File Upload → Parse (S1) → Triage (S2) → Map (S3)     │
│                    ↓            ↓            ↓           │
│              [Lineage Event][Lineage Event][Lineage Event]│
│                    ↓            ↓            ↓           │
│              ┌──────────────────────────────────┐       │
│              │   LineageTracker                 │       │
│              │   • emit()                       │       │
│              │   • validate_completeness()      │       │
│              │   • save_to_db()                 │       │
│              └──────────────────────────────────┘       │
│                           ↓                              │
│              ┌──────────────────────────────────┐       │
│              │   PostgreSQL Database             │       │
│              │   • lineage_events table         │       │
│              │   • Indexed by job_id, stage     │       │
│              └──────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `src/lineage/tracker.py` | LineageTracker implementation |
| `src/models/lineage.py` | Database model |
| `src/extraction/orchestrator.py` | Integration point |
| `scripts/init_db.py` | Database initialization |
| `tests/unit/test_lineage.py` | Unit tests |

## Validation Checklist

- [ ] PostgreSQL is running
- [ ] Database initialized successfully
- [ ] `lineage_events` table exists
- [ ] Unit tests pass
- [ ] Orchestrator imports LineageTracker
- [ ] Orchestrator calls `emit()` 3 times
- [ ] Orchestrator calls `validate_completeness()`
- [ ] Orchestrator calls `save_to_db()`

## Troubleshooting

**Issue**: `ModuleNotFoundError: No module named 'src'`  
**Fix**: Run `pip install -e ".[dev]"` from project root

**Issue**: `ConnectionError: Unable to connect to PostgreSQL`  
**Fix**: Check Docker: `docker-compose ps postgres`

**Issue**: `LineageIncompleteError` during extraction  
**Fix**: This is expected! It means validation is working correctly.

## Success Criteria

✅ All imports work without errors  
✅ Database table created with proper schema  
✅ Tests pass (or skip gracefully if DB unavailable)  
✅ Orchestrator has all lineage integration points  
✅ Error handling includes `LineageIncompleteError`

## Next Steps

1. Run full extraction pipeline test
2. Monitor for `LineageIncompleteError` in logs
3. Add lineage for stages 4-5 (future work)
4. Implement lineage dashboard (future work)

## Support

See full documentation: `LINEAGE_IMPLEMENTATION_SUMMARY.md`
