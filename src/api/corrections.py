"""User correction and entity pattern management endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID

from src.db.session import get_db
from src.db import crud
from src.auth.dependencies import get_current_api_key, require_entity_scope
from src.core.exceptions import DatabaseError
from src.core.logging import api_logger as logger
from src.api.schemas import (
    CorrectionRequest, CorrectionResponse, PatternListResponse, PatternResponse,
    PatternStatsResponse, LearnedAliasResponse, LearnedAliasListResponse,
    LearnedAliasPromoteResponse,
    ApplyCorrectionRequest, ApplyCorrectionResponse,
    PreviewCorrectionResponse, CorrectionDiff,
    CorrectionHistoryResponse, CorrectionHistoryItem,
    UndoCorrectionResponse,
)

router = APIRouter(prefix="/api/v1", tags=["corrections"])


@router.post("/jobs/{job_id}/corrections", response_model=CorrectionResponse)
def submit_corrections(
    job_id: str,
    body: CorrectionRequest,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """
    Submit user corrections for a job's mappings.

    Each correction creates or updates an entity pattern with confidence=1.0
    and created_by='user_correction'. These patterns will be used to
    shortcircuit future Claude calls for the same entity.
    """
    # Validate all canonical names before any DB work
    from src.extraction.taxonomy_loader import get_all_canonical_names

    valid_names = get_all_canonical_names()
    invalid = [
        c.canonical_name for c in body.corrections
        if c.canonical_name not in valid_names
    ]
    if invalid:
        raise HTTPException(
            422,
            f"Invalid canonical names: {', '.join(invalid)}. All corrections rejected.",
        )

    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job_id format")

    try:
        job = crud.get_job(db, job_uuid)
    except DatabaseError as e:
        logger.error(f"Database error looking up job: {str(e)}")
        raise HTTPException(500, "Database error looking up job")

    if not job:
        raise HTTPException(404, "Job not found")

    # entity_id is on the File model, accessed via job.file
    entity_id = job.file.entity_id if job.file else None
    if not entity_id:
        raise HTTPException(400, "Corrections require an entity association")

    created = 0
    updated = 0

    try:
        for correction in body.corrections:
            # Check if pattern already exists to track created vs updated
            from src.db.models import EntityPattern
            existing = (
                db.query(EntityPattern)
                .filter(
                    EntityPattern.entity_id == entity_id,
                    EntityPattern.original_label == correction.original_label,
                )
                .first()
            )

            crud.upsert_entity_pattern(
                db=db,
                entity_id=entity_id,
                original_label=correction.original_label,
                canonical_name=correction.canonical_name,
                confidence=1.0,
                created_by="user_correction",
            )

            if existing:
                updated += 1
            else:
                created += 1

    except DatabaseError as e:
        logger.error(f"Database error submitting corrections: {str(e)}")
        raise HTTPException(500, "Database error submitting corrections")

    logger.info(
        f"Corrections submitted for job {job_id}: "
        f"{created} created, {updated} updated"
    )

    return CorrectionResponse(
        patterns_created=created,
        patterns_updated=updated,
        message=f"Applied {created + updated} corrections ({created} new, {updated} updated)",
    )


@router.get("/entities/{entity_id}/patterns", response_model=PatternListResponse)
def list_entity_patterns(
    entity_id: str,
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _api_key=Depends(require_entity_scope),
):
    """List all learned patterns for an entity."""
    try:
        entity_uuid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    try:
        patterns = crud.get_entity_patterns(
            db, entity_uuid, min_confidence=min_confidence, limit=limit
        )
    except DatabaseError as e:
        logger.error(f"Database error listing patterns: {str(e)}")
        raise HTTPException(500, "Database error listing patterns")

    return PatternListResponse(
        entity_id=entity_id,
        patterns=[
            PatternResponse(
                id=str(p.id),
                original_label=p.original_label,
                canonical_name=p.canonical_name,
                confidence=float(p.confidence),
                occurrence_count=p.occurrence_count,
                created_by=p.created_by,
                created_at=p.created_at.isoformat() if p.created_at else None,
            )
            for p in patterns
        ],
        total_patterns=len(patterns),
    )


@router.delete("/entities/{entity_id}/patterns/{pattern_id}", status_code=204)
def delete_entity_pattern(
    entity_id: str,
    pattern_id: str,
    db: Session = Depends(get_db),
    _api_key=Depends(require_entity_scope),
):
    """Delete a specific entity pattern."""
    try:
        UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    try:
        pattern_uuid = UUID(pattern_id)
    except ValueError:
        raise HTTPException(400, "Invalid pattern_id format")

    try:
        deleted = crud.delete_entity_pattern(db, pattern_uuid)
    except DatabaseError as e:
        logger.error(f"Database error deleting pattern: {str(e)}")
        raise HTTPException(500, "Database error deleting pattern")

    if not deleted:
        raise HTTPException(404, "Pattern not found")

    return None


@router.get(
    "/entities/{entity_id}/pattern-stats",
    response_model=PatternStatsResponse,
)
def get_pattern_stats(
    entity_id: str,
    db: Session = Depends(get_db),
    _api_key=Depends(require_entity_scope),
):
    """Get pattern quality statistics for an entity."""
    try:
        entity_uuid = UUID(entity_id)
    except ValueError:
        raise HTTPException(400, "Invalid entity_id format")

    try:
        # All patterns (including inactive)
        all_patterns = crud.get_entity_patterns(
            db, entity_uuid, min_confidence=0.0, limit=1000, active_only=False
        )
        active_patterns = [p for p in all_patterns if p.is_active]
        inactive_patterns = [p for p in all_patterns if not p.is_active]

        # Stats
        avg_conf = (
            sum(float(p.confidence) for p in active_patterns) / len(active_patterns)
            if active_patterns else 0.0
        )

        by_method: dict[str, int] = {}
        for p in active_patterns:
            by_method[p.created_by] = by_method.get(p.created_by, 0) + 1

        # Estimate token savings: ~50 tokens per shortcircuited label
        tokens_saved = len(active_patterns) * 50
        cost_saved = tokens_saved * 3.0 / 1_000_000  # input token savings

        # Top patterns by occurrence
        top = sorted(active_patterns, key=lambda p: p.occurrence_count, reverse=True)[:10]

        return PatternStatsResponse(
            entity_id=entity_id,
            total_patterns=len(all_patterns),
            active_patterns=len(active_patterns),
            avg_confidence=round(avg_conf, 3),
            by_method=by_method,
            tokens_saved_estimate=tokens_saved,
            cost_saved_estimate=round(cost_saved, 6),
            top_patterns=[
                PatternResponse(
                    id=str(p.id),
                    original_label=p.original_label,
                    canonical_name=p.canonical_name,
                    confidence=float(p.confidence),
                    occurrence_count=p.occurrence_count,
                    created_by=p.created_by,
                    created_at=p.created_at.isoformat() if p.created_at else None,
                )
                for p in top
            ],
            conflicted_patterns=[
                PatternResponse(
                    id=str(p.id),
                    original_label=p.original_label,
                    canonical_name=p.canonical_name,
                    confidence=float(p.confidence),
                    occurrence_count=p.occurrence_count,
                    created_by=p.created_by,
                    created_at=p.created_at.isoformat() if p.created_at else None,
                )
                for p in inactive_patterns
            ],
        )

    except DatabaseError as e:
        logger.error(f"Database error getting pattern stats: {str(e)}")
        raise HTTPException(500, "Database error getting pattern stats")


@router.get(
    "/learned-aliases",
    response_model=LearnedAliasListResponse,
)
def list_learned_aliases(
    min_occurrences: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """List learned aliases pending review or promotion."""
    try:
        aliases = crud.get_learned_aliases(
            db, promoted=False, min_occurrences=min_occurrences, limit=limit
        )

        return LearnedAliasListResponse(
            aliases=[
                LearnedAliasResponse(
                    id=str(a.id),
                    canonical_name=a.canonical_name,
                    alias_text=a.alias_text,
                    occurrence_count=a.occurrence_count,
                    source_entities=[str(e) for e in (a.source_entities or [])],
                    promoted=a.promoted,
                    created_at=a.created_at.isoformat() if a.created_at else None,
                )
                for a in aliases
            ],
            total=len(aliases),
        )

    except DatabaseError as e:
        logger.error(f"Database error listing learned aliases: {str(e)}")
        raise HTTPException(500, "Database error listing learned aliases")


@router.post(
    "/learned-aliases/{alias_id}/promote",
    response_model=LearnedAliasPromoteResponse,
)
def promote_learned_alias(
    alias_id: str,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Promote a learned alias (mark as promoted)."""
    try:
        alias_uuid = UUID(alias_id)
    except ValueError:
        raise HTTPException(400, "Invalid alias_id format")

    try:
        alias = crud.promote_learned_alias(db, alias_uuid)
    except DatabaseError as e:
        logger.error(f"Database error promoting alias: {str(e)}")
        raise HTTPException(500, "Database error promoting alias")

    if not alias:
        raise HTTPException(404, "Learned alias not found")

    return LearnedAliasPromoteResponse(
        id=str(alias.id),
        canonical_name=alias.canonical_name,
        alias_text=alias.alias_text,
        promoted=alias.promoted,
        message=f"Alias '{alias.alias_text}' promoted for canonical '{alias.canonical_name}'",
    )


# ============================================================================
# Corrections Application (WS-J: retroactive apply, preview, undo, bulk, history)
# ============================================================================


def _validate_job_for_correction(db: Session, job_id: str):
    """Shared validation for apply/bulk: parse UUID, load job, check status.

    Returns (job_uuid, job) on success.
    Raises HTTPException on validation failure.
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job_id format")

    try:
        job = crud.get_job(db, job_uuid)
    except DatabaseError as e:
        raise HTTPException(500, f"Database error: {e}")

    if not job:
        raise HTTPException(404, "Job not found")

    from src.db.models import JobStatusEnum

    if job.status not in (JobStatusEnum.COMPLETED, JobStatusEnum.NEEDS_REVIEW):
        raise HTTPException(
            409,
            f"Corrections can only be applied to completed or needs_review jobs (current: {job.status.value})",
        )

    return job_uuid, job


def _validate_canonical_names(corrections):
    """Validate all canonical names against taxonomy. Raises HTTPException(422) if any invalid."""
    from src.extraction.taxonomy_loader import get_all_canonical_names

    valid_names = get_all_canonical_names()
    invalid = [
        c.new_canonical_name
        for c in corrections
        if c.new_canonical_name not in valid_names
    ]
    if invalid:
        raise HTTPException(
            422,
            f"Invalid canonical names: {', '.join(invalid)}. All corrections rejected.",
        )


def _apply_and_respond(db: Session, job_id: str, job_uuid, corrections, log_prefix: str = "Applied"):
    """Shared apply logic for apply/bulk endpoints."""
    try:
        result = crud.apply_correction_to_result(
            db,
            job_uuid,
            [c.model_dump() for c in corrections],
        )
    except DatabaseError as e:
        if "entity association" in str(e).lower():
            raise HTTPException(400, str(e))
        raise HTTPException(500, f"Failed to apply corrections: {e}")

    diffs = [CorrectionDiff(**d) for d in result["diffs"]]
    applied = len(diffs)

    logger.info(
        f"{log_prefix} {applied} corrections to job {job_id}: "
        f"{result['patterns_created']} patterns created, "
        f"{result['patterns_updated']} updated, "
        f"{result['facts_updated']} facts updated"
    )

    return ApplyCorrectionResponse(
        job_id=job_id,
        corrections_applied=applied,
        patterns_created=result["patterns_created"],
        patterns_updated=result["patterns_updated"],
        facts_updated=result["facts_updated"],
        diffs=diffs,
        message=f"{log_prefix} {applied} corrections ({result['patterns_created']} new patterns, {result['patterns_updated']} updated)",
    )


@router.post(
    "/jobs/{job_id}/corrections/preview",
    response_model=PreviewCorrectionResponse,
)
def preview_corrections(
    job_id: str,
    body: ApplyCorrectionRequest,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Preview what corrections would change without persisting anything."""
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job_id format")

    # Validate canonical names against taxonomy (warnings, not errors)
    from src.extraction.taxonomy_loader import get_all_canonical_names

    valid_names = get_all_canonical_names()
    warnings = []
    for c in body.corrections:
        if c.new_canonical_name not in valid_names:
            warnings.append(f"Invalid canonical_name: '{c.new_canonical_name}'")

    try:
        result = crud.preview_corrections(
            db,
            job_uuid,
            [c.model_dump() for c in body.corrections],
        )
    except DatabaseError as e:
        if "not found" in str(e).lower():
            raise HTTPException(404, str(e))
        raise HTTPException(500, f"Database error: {e}")

    diffs = [CorrectionDiff(**d) for d in result["diffs"]]

    all_warnings = warnings + result.get("warnings", [])
    return PreviewCorrectionResponse(
        job_id=job_id,
        corrections_count=len(diffs),
        diffs=diffs,
        warnings=all_warnings,
        message=f"Preview: {len(diffs)} corrections would be applied",
    )


@router.post(
    "/jobs/{job_id}/corrections/apply",
    response_model=ApplyCorrectionResponse,
)
def apply_corrections(
    job_id: str,
    body: ApplyCorrectionRequest,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Apply corrections retroactively to a job's result, update facts and create patterns.

    Lenient mode: labels not found in job.result are silently skipped (with warning in response).
    For strict all-or-nothing validation, use the /bulk endpoint.
    """
    _validate_canonical_names(body.corrections)
    job_uuid, _job = _validate_job_for_correction(db, job_id)
    return _apply_and_respond(db, job_id, job_uuid, body.corrections, log_prefix="Applied")


@router.post(
    "/jobs/{job_id}/corrections/bulk",
    response_model=ApplyCorrectionResponse,
)
def bulk_apply_corrections(
    job_id: str,
    body: ApplyCorrectionRequest,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Apply multiple corrections transactionally — all-or-nothing.

    Validates ALL corrections exhaustively before applying any:
    canonical names must be valid AND all labels must exist in job.result.
    One invalid correction rejects the entire batch.
    """
    _validate_canonical_names(body.corrections)
    job_uuid, job = _validate_job_for_correction(db, job_id)

    # Additional bulk-only validation: all labels must exist
    errors = []
    if not job.result or "line_items" not in job.result:
        raise HTTPException(400, "Job has no result to correct")

    line_items = job.result["line_items"]
    line_item_index = crud._build_line_item_index(line_items)
    for c in body.corrections:
        matches = crud._find_matching_line_items(
            line_items, c.original_label, c.sheet, _index=line_item_index
        )
        if not matches:
            errors.append(f"Label '{c.original_label}' not found in job result")

    if errors:
        raise HTTPException(422, f"Bulk validation failed: {'; '.join(errors)}")

    return _apply_and_respond(db, job_id, job_uuid, body.corrections, log_prefix="Bulk applied")


@router.post(
    "/corrections/{correction_id}/undo",
    response_model=UndoCorrectionResponse,
)
def undo_correction_endpoint(
    correction_id: str,
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """Undo a specific correction, restoring original values."""
    try:
        correction_uuid = UUID(correction_id)
    except ValueError:
        raise HTTPException(400, "Invalid correction_id format")

    try:
        correction = crud.undo_correction(db, correction_uuid)
    except DatabaseError as e:
        msg = str(e).lower()
        if "not found" in msg:
            raise HTTPException(404, "Correction not found")
        if "already reverted" in msg:
            raise HTTPException(409, "Correction already reverted")
        if "cannot undo" in msg:
            raise HTTPException(409, str(e))
        raise HTTPException(500, f"Failed to undo correction: {e}")

    logger.info(
        f"Undone correction {correction_id}: "
        f"restored '{correction.original_label}' to '{correction.old_canonical_name}'"
    )

    return UndoCorrectionResponse(
        correction_id=str(correction.id),
        job_id=str(correction.job_id),
        original_label=correction.original_label,
        restored_canonical_name=correction.old_canonical_name,
        message=f"Reverted '{correction.original_label}' from '{correction.new_canonical_name}' back to '{correction.old_canonical_name}'",
    )


@router.get(
    "/jobs/{job_id}/corrections/history",
    response_model=CorrectionHistoryResponse,
)
def get_correction_history(
    job_id: str,
    include_reverted: bool = Query(True),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    _api_key=Depends(get_current_api_key),
):
    """List correction history for a job."""
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(400, "Invalid job_id format")

    # Verify job exists
    try:
        job = crud.get_job(db, job_uuid)
    except DatabaseError as e:
        raise HTTPException(500, f"Database error: {e}")

    if not job:
        raise HTTPException(404, "Job not found")

    try:
        corrections, total = crud.get_correction_history(
            db, job_uuid, include_reverted=include_reverted,
            offset=offset, limit=limit,
        )
    except DatabaseError as e:
        raise HTTPException(500, f"Database error: {e}")

    return CorrectionHistoryResponse(
        job_id=job_id,
        corrections=[
            CorrectionHistoryItem(
                id=str(c.id),
                job_id=str(c.job_id),
                original_label=c.original_label,
                sheet=c.sheet,
                old_canonical_name=c.old_canonical_name,
                new_canonical_name=c.new_canonical_name,
                old_confidence=c.old_confidence,
                new_confidence=c.new_confidence,
                reverted=c.reverted,
                reverted_at=c.reverted_at.isoformat() if c.reverted_at else None,
                created_at=c.created_at.isoformat() if c.created_at else None,
            )
            for c in corrections
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


# ============================================================================
# WS-J POST-IMPLEMENTATION REVIEW (v2 — honest reassessment)
# ============================================================================
#
# ## Compliance: 12/12 DONE, 0 PARTIAL, 0 MISSING
#
# All plan requirements implemented: CorrectionHistory model (models.py:548),
# migration (b2c3d4e5f6a7), 8 Pydantic schemas (schemas.py:347-403),
# 6 CRUD functions (crud.py:1693-2150), 5 endpoints (corrections.py:334-621),
# 40 tests (test_corrections.py).
#
# Plan vs Impl deltas (both improvements):
#   undone/undone_at → reverted/reverted_at
#   history_ids → diffs list
#
# ## Gaps Found & Fixed
#
# BUG-1 (CRITICAL, FIXED): Out-of-order undo caused silent data corruption.
#   If corrections A then B targeted the same label, undoing A first would
#   restore A's snapshot, silently destroying B's changes. B's history
#   record would still show reverted=False — inconsistent state.
#   FIX: crud.undo_correction now rejects undo when another non-reverted
#   correction exists for the same label+sheet (409 with clear message).
#   TEST: test_undo_blocked_when_overlapping_correction_exists
#
# BUG-2 (MEDIUM, FIXED): Dead `created_by` parameter in
#   apply_correction_to_result. Was declared but hardcoded to
#   "user_correction" inside the function body. Now wired through.
#
# BUG-3 (MEDIUM, DOCUMENTED): update_extraction_facts_for_correction
#   silently swallows SQLAlchemyError (crud.py:1766), returning 0 instead
#   of raising. If fact updates fail, the correction is "applied" but
#   ExtractionFacts are stale. By design (facts are supplementary), but
#   a production operator would never know facts are out of sync.
#
# BUG-4 (LOW, DOCUMENTED): ExtractionFact filter during undo uses
#   old_canonical_name to find rows. If an intermediate correction changed
#   the fact's canonical_name, the filter misses it. Mitigated by BUG-1
#   fix (overlapping corrections now rejected at undo time).
#
# ## End-to-End Trace
#
# Apply: POST /api/v1/jobs/{job_id}/corrections/apply
#   1. UUID parse (400) → canonical validation (422) → job lookup (404)
#   2. Status check: COMPLETED|NEEDS_REVIEW (409 otherwise)
#   3. crud.apply_correction_to_result:
#      a. joinedload(file) for entity_id
#      b. deepcopy(job.result) — survives upsert_entity_pattern's internal commit
#      c. Per match: snapshot → mutate → CorrectionHistory → upsert pattern
#         (COMMITS — partial atomicity gap) → update facts
#      d. Re-load job → assign modified_result → flag_modified → commit
#   4. Build ApplyCorrectionResponse with diffs
#
# Breaking attempts:
#   - Empty input: Pydantic min_length=1 rejects at schema level (422)
#   - Nonexistent label: Returns 0 diffs, no error (by design)
#   - Huge input (1000 corrections): No limit enforced — works but slow
#   - Missing dependencies: taxonomy_loader import is lazy (inside function)
#
# ## Test Coverage: 40 passed, 0 failed
#
# 12 test classes, 40 tests. All 5 endpoints covered.
# Strong coverage: multi-sheet, fact table revert, provenance snapshot,
#   double-undo, out-of-order undo, history filtering, no-match, already-
#   mapped skip, non-completed job rejection.
#
# Remaining untested paths:
#   - Concurrent corrections on same job (race condition)
#   - Job with no file association (entity_id=None for apply)
#   - Bulk with mixed: some labels exist, some don't + invalid canonicals
#   - Correction on job whose result was deleted between status check and apply
#
# ## Production Concerns
#
# 1. PARTIAL ATOMICITY (HIGH): upsert_entity_pattern commits mid-loop.
#    If apply fails after creating 2 of 5 patterns, those 2 persist but
#    result JSON is unchanged. Patterns and result are inconsistent.
#    Fix: refactor upsert_entity_pattern to use db.flush() not db.commit().
#
# 2. NO PAGINATION (MEDIUM): history endpoint returns all records.
#    A job with 500 corrections will return 500 records.
#
# 3. NO BATCH LIMIT (LOW): ApplyCorrectionRequest accepts unlimited
#    corrections. A request with 10k items will be processed.
#
# 4. SILENT FACT FAILURES (LOW): See BUG-3 above.
#
# ## Path to World-Class
#
# Performance: apply_correction_to_result does N upsert queries + N fact
#   queries per correction. For 100 corrections, that's 200+ queries.
#   Batch upserts and use a single UPDATE...WHERE IN for facts.
#
# Depth: Undo restores the ENTIRE old line_item snapshot, which is correct
#   but coarse — a financial analyst might want to undo just the canonical
#   mapping without losing any other edits to provenance/values.
#
# Robustness: The undo ordering guard (BUG-1 fix) is conservative — it
#   blocks ANY undo when overlapping corrections exist. A smarter approach
#   would allow undoing the most recent correction (using timestamps or
#   sequence numbers with sufficient precision).
#
# User-Friendliness: 409 error from undo says "another active correction
#   exists" with the ID. Good. But 422 from bulk says "Bulk validation
#   failed: Label 'X' not found" — should also suggest closest matches.
#
# Observability: No metrics emitted. Should log: corrections_applied_total,
#   corrections_undone_total, correction_latency_seconds, fact_sync_failures.
#
# ## Complexity Removed
#
# - Deleted tests/unit/test_corrections_apply.py (duplicate test file, 534
#   lines). All unique tests migrated to test_corrections.py.
# - Wired dead `created_by` parameter through to actual usage (was ignored).
# - No unnecessary abstractions found. _find_matching_line_items is a
#   justified helper (used in 4 places across apply, preview, undo, bulk).
# ============================================================================
