# ADR-004: Transactional Lineage Persistence

## Status
Accepted

## Date
2026-02-24

## Context

The lineage tracking system had two critical issues that violated critical requirements:

1. **Async/Sync Mismatch**: The `save_to_db()` method in `LineageTracker` was declared as `async def` but used synchronous database operations via `get_db_context()`. This created false async semantics - the function was called with `await` but didn't actually perform any async operations.

2. **No Transaction Wrapping**: Lineage events were saved in a loop without transaction boundaries. If a database error occurred mid-loop, some events would be saved while others wouldn't, resulting in partial lineage data.

### Risk Profile

Without transactional saves:
- Partial lineage data could exist in the database
- Lineage completeness validation could pass locally but fail to persist
- Trust in the system would be undermined (critical violation)
- Debugging would become impossible with incomplete event chains

### Prior Implementation

```python
async def save_to_db(self) -> None:
    with get_db_context() as db:  # Sync context in async function
        for event in self.events:
            crud.create_lineage_event(db, ...)  # No rollback on error
    # No explicit commit or rollback
```

## Decision

We made three changes to fix these issues:

### 1. Made save_to_db() Synchronous

Changed from `async def save_to_db()` to `def save_to_db()` to match the synchronous database layer. The function never actually awaited anything, so the async declaration was misleading.

### 2. Added Explicit Transaction Handling

Wrapped all database operations in try/except with explicit `db.commit()` on success and `db.rollback()` on error. This ensures all-or-nothing semantics for lineage persistence.

### 3. Updated Call Sites

Removed `await` from the orchestrator's call to `tracker.save_to_db()` since it's now synchronous.

## Implementation

```python
def save_to_db(self) -> None:
    """
    Persist all lineage events to the database.

    Saves are transactional - either all events save or none.
    This prevents partial lineage data in case of database errors.
    """
    with get_db_context() as db:
        try:
            for event in self.events:
                crud.create_lineage_event(db, ...)

            # Explicit commit for transaction
            db.commit()
            logger.info(f"Saved {len(self.events)} lineage events")

        except Exception as e:
            # Rollback on any error to prevent partial saves
            db.rollback()
            logger.error(f"Failed to save lineage events: {str(e)}")
            raise LineageError(f"Database save failed: {str(e)}")
```

### Files Modified

- `src/lineage/tracker.py` - Changed function signature and added transaction handling
- `src/extraction/orchestrator.py` - Removed await from save_to_db() call

## Consequences

### Positive

- **critical requirement met**: Lineage saves are now atomic (all-or-nothing)
- **Consistent architecture**: Function signature matches actual behavior (synchronous)
- **Proper error handling**: Explicit commit/rollback with comprehensive logging
- **Debugging clarity**: No more confusion about async/sync semantics
- **Data integrity**: Impossible to have partial lineage in database

### Negative

- None - this was a bug fix that improved system correctness

## Testing Considerations

### Unit Tests

Should verify:
- All events save successfully in happy path
- No events persist if any single event fails
- LineageError is raised with correct details on failure
- Rollback is called on database errors

### Integration Tests

Should verify:
- Orchestrator completes without awaiting save_to_db()
- Lineage validation passes and data persists correctly
- Database connection errors trigger proper rollback

## Related ADRs

- ADR-005: Stage Retry Logic (addresses Claude API failures)

## Notes

The async/sync mismatch was particularly insidious because it "worked" in the sense that no errors were raised, but the semantics were incorrect and transaction safety was missing.
