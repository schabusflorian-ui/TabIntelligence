"""
Extraction Orchestrator - coordinates the extraction pipeline using registered stages.

Uses a Stage Registry pattern so new stages can be added by simply creating
a new ExtractionStage subclass and registering it - no orchestrator changes needed.
"""
import time
import uuid
from typing import Optional
from dataclasses import dataclass, asdict

from src.core.logging import extraction_logger as logger, log_performance, log_exception
from src.core.exceptions import ExtractionError, ClaudeAPIError, LineageIncompleteError
from src.extraction.base import PipelineContext
from src.extraction.registry import registry
from src.api.metrics import (
    extraction_stage_duration_seconds,
    extraction_stage_tokens_total,
    extraction_cost_usd_total,
    extraction_duration_seconds,
    extraction_jobs_total,
)

# Import stages to trigger self-registration
import src.extraction.stages  # noqa: F401


@dataclass
class ExtractionResult:
    """Result of a complete extraction pipeline run."""
    file_id: str
    sheets: list
    triage: list
    line_items: list
    tokens_used: int
    cost_usd: float
    job_id: Optional[str] = None
    validation: Optional[dict] = None
    lineage_summary: Optional[dict] = None
    final_lineage_id: Optional[str] = None

    def to_dict(self):
        return asdict(self)


async def extract(
    file_bytes: bytes,
    file_id: str,
    entity_id: Optional[str] = None,
    job_id: Optional[str] = None,
) -> dict:
    """
    Run the guided extraction pipeline using registered stages.

    Stages are discovered from the global registry and executed in order.
    To add new stages, create an ExtractionStage subclass and register it.

    Args:
        file_bytes: Excel file bytes
        file_id: File UUID
        entity_id: Optional entity UUID
        job_id: Optional job UUID for lineage tracking
    """
    if job_id is None:
        job_id = str(uuid.uuid4())

    logger.info(
        f"Extraction started - file_id: {file_id}, "
        f"entity_id: {entity_id}, job_id: {job_id}"
    )
    pipeline_start = time.time()

    # Create pipeline context (includes lineage tracker)
    context = PipelineContext(
        file_bytes=file_bytes,
        file_id=file_id,
        job_id=job_id,
        entity_id=entity_id,
    )

    # Get pipeline stages from registry (sorted by stage_number)
    pipeline = registry.get_pipeline()
    lineage_ids = {}
    last_lineage_id = None

    try:
        for stage in pipeline:
            logger.info(f"Running {stage.description}...")

            # Execute stage with timing
            stage_start = time.time()
            result = await stage.execute(context)
            stage_duration = time.time() - stage_start
            context.set_result(stage.name, result)

            # Record per-stage metrics
            stage_tokens = result.get("tokens", 0)
            extraction_stage_duration_seconds.labels(stage=stage.name).observe(stage_duration)
            extraction_stage_tokens_total.labels(stage=stage.name).inc(stage_tokens)

            # Emit lineage event
            parent_id = lineage_ids.get(stage.stage_number - 1)
            lineage_metadata = result.get("lineage_metadata", {})
            lineage_metadata["tokens"] = result.get("tokens", 0)

            lineage_id = context.tracker.emit(
                stage=stage.stage_number,
                event_type=stage.name,
                input_lineage_id=parent_id,
                metadata=lineage_metadata,
            )
            lineage_ids[stage.stage_number] = lineage_id
            last_lineage_id = lineage_id

        # Validate lineage completeness for all executed stages
        expected_stages = [s.stage_number for s in pipeline]
        context.tracker.validate_completeness(stages=expected_stages)

        # Persist lineage to database (synchronous, transactional)
        context.tracker.save_to_db()

    except LineageIncompleteError as e:
        logger.error(f"LINEAGE INCOMPLETE for job {job_id}: {str(e)}")
        log_exception(logger, e, {"job_id": job_id, "file_id": file_id})
        raise

    except (ClaudeAPIError, ExtractionError) as e:
        logger.error(f"Extraction failed for file_id {file_id}: {str(e)}")
        raise

    except Exception as e:
        logger.error(f"Unexpected extraction error for file_id {file_id}: {str(e)}")
        error = ExtractionError(f"Extraction failed: {str(e)}", file_id=file_id)
        log_exception(logger, error)
        raise error

    # Build final result from stage outputs
    result = _build_result(context, last_lineage_id, pipeline_start)

    return result.to_dict()


def _build_result(
    context: PipelineContext,
    final_lineage_id: Optional[str],
    pipeline_start: float,
) -> ExtractionResult:
    """Build the final ExtractionResult from pipeline context."""
    total_tokens = context.total_tokens

    # Calculate cost (Claude Sonnet pricing estimate)
    cost = total_tokens * 0.003 / 1000

    # Get stage results (gracefully handle missing stages for forward compatibility)
    parse_result = context.results.get("parsing", {})
    triage_result = context.results.get("triage", {})
    mapping_result = context.results.get("mapping", {})
    validation_result = context.results.get("validation", {})
    enhanced_result = context.results.get("enhanced_mapping", {})

    parsed_data = parse_result.get("parsed", {})
    triage_list = triage_result.get("triage", [])

    # Use enhanced mappings if available, otherwise fall back to basic mappings
    mappings = enhanced_result.get("enhanced_mappings") or mapping_result.get("mappings", [])

    # Build line items with mappings
    mapping_lookup = {m["original_label"]: m for m in mappings}
    line_items = []

    for sheet in parsed_data.get("sheets", []):
        sheet_triage = next(
            (t for t in triage_list if t.get("sheet_name") == sheet.get("sheet_name")),
            {"tier": 4, "decision": "SKIP"},
        )

        if sheet_triage.get("tier", 4) <= 3:  # Process tiers 1-3
            for row in sheet.get("rows", []):
                mapping = mapping_lookup.get(row.get("label", ""), {})
                line_items.append({
                    "sheet": sheet["sheet_name"],
                    "row": row.get("row_index"),
                    "original_label": row.get("label"),
                    "canonical_name": mapping.get("canonical_name", "unmapped"),
                    "values": row.get("values", {}),
                    "confidence": mapping.get("confidence", 0.5),
                    "hierarchy_level": row.get("hierarchy_level", 1),
                })

    result = ExtractionResult(
        file_id=context.file_id,
        sheets=[s["sheet_name"] for s in parsed_data.get("sheets", [])],
        triage=triage_list,
        line_items=line_items,
        tokens_used=total_tokens,
        cost_usd=cost,
        job_id=context.job_id,
        validation=validation_result.get("validation"),
        lineage_summary=context.tracker.get_summary(),
        final_lineage_id=final_lineage_id,
    )

    pipeline_duration = time.time() - pipeline_start

    # Record pipeline-level metrics
    extraction_duration_seconds.observe(pipeline_duration)
    extraction_cost_usd_total.inc(cost)
    extraction_jobs_total.labels(status="completed").inc()

    log_performance(
        logger,
        "full_extraction_pipeline",
        pipeline_duration,
        {
            "total_tokens": total_tokens,
            "cost_usd": cost,
            "sheets": len(result.sheets),
            "line_items": len(line_items),
            "file_id": context.file_id,
        },
    )

    logger.info(
        f"Extraction complete - file_id: {context.file_id}, "
        f"sheets: {len(result.sheets)}, line_items: {len(line_items)}, "
        f"tokens: {total_tokens}, cost: ${cost:.4f}"
    )

    return result
