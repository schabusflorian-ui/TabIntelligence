"""
Simplified Lineage Tracker using synchronous database.

Tracks data provenance throughout the extraction pipeline.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.core.exceptions import LineageError, LineageIncompleteError
from src.core.logging import lineage_logger as logger
from src.db import crud
from src.db.session import get_db_context


class LineageTracker:
    """
    Tracks data lineage throughout the extraction pipeline.

    Simplified version using synchronous database operations.
    """

    def __init__(self, job_id: str):
        """
        Initialize lineage tracker for a job.

        Args:
            job_id: UUID string of the extraction job
        """
        self.job_id = job_id
        self.events: List[Dict] = []
        self.lineage_chain: Dict[str, Optional[str]] = {}  # Maps lineage_id -> parent_lineage_id
        self.item_lineage: Dict[str, List[Dict]] = {}  # canonical_name -> transformations

    def emit(
        self,
        stage: int,
        event_type: str,
        input_lineage_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Emit a lineage event.

        Args:
            stage: Stage number (1, 2, 3, etc.)
            event_type: Event type (parse, triage, map, etc.)
            input_lineage_id: Parent lineage ID (None for first stage)
            metadata: Additional metadata dict

        Returns:
            str: Lineage ID for this event
        """
        lineage_id = str(uuid.uuid4())

        event = {
            "lineage_id": lineage_id,
            "stage": stage,
            "event_type": event_type,
            "input_lineage_id": input_lineage_id,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self.events.append(event)
        self.lineage_chain[lineage_id] = input_lineage_id

        logger.debug(
            f"Lineage event emitted: job={self.job_id}, stage={stage}, "
            f"type={event_type}, lineage_id={lineage_id[:8]}..."
        )

        return lineage_id

    def validate_completeness(self, stages: List[int]) -> None:
        """
        Validate that all required stages have lineage events.

        Args:
            stages: List of required stage numbers

        Raises:
            LineageIncompleteError: If any stages are missing
        """
        emitted_stages = {event["stage"] for event in self.events}
        missing_stages = [stage for stage in stages if stage not in emitted_stages]

        if missing_stages:
            error_msg = f"Missing lineage for stages: {missing_stages}"
            logger.error(f"Lineage validation failed for job {self.job_id}: {error_msg}")
            raise LineageIncompleteError(
                missing_events=[f"stage_{s}" for s in missing_stages], job_id=self.job_id
            )

        logger.info(
            f"Lineage validation passed for job {self.job_id}: all {len(stages)} stages complete"
        )

    def save_to_db(self) -> None:
        """
        Persist all lineage events to the database.

        Saves are transactional - either all events save or none.
        This prevents partial lineage data in case of database errors.
        """
        if not self.events:
            logger.debug(f"No lineage events to save for job {self.job_id}")
            return

        logger.debug(f"Saving {len(self.events)} lineage events to database for job {self.job_id}")

        try:
            from uuid import UUID

            with get_db_context() as db:
                try:
                    for event in self.events:
                        # Convert lineage event to database format
                        stage_name = f"stage_{event['stage']}_{event['event_type']}"

                        crud.create_lineage_event(
                            db,
                            job_id=UUID(self.job_id),
                            stage_name=stage_name,
                            data={
                                "lineage_id": event["lineage_id"],
                                "stage": event["stage"],
                                "event_type": event["event_type"],
                                "input_lineage_id": event["input_lineage_id"],
                                "metadata": event["metadata"],
                                "timestamp": event["timestamp"],
                            },
                        )

                    # Explicit commit for transaction - all or nothing
                    db.commit()
                    logger.info(
                        f"Saved {len(self.events)} lineage events to database for job {self.job_id}"
                    )

                except Exception as e:
                    # Rollback on any error to prevent partial saves
                    db.rollback()
                    logger.error(f"Database error during lineage save, rolled back: {str(e)}")
                    raise

        except Exception as e:
            logger.error(f"Failed to save lineage to database for job {self.job_id}: {str(e)}")
            raise LineageError(f"Failed to persist lineage: {str(e)}", job_id=self.job_id)

    def emit_item_transformation(
        self,
        canonical_name: str,
        original_label: str,
        stage: str,
        action: str,
        details: Optional[Dict] = None,
    ) -> None:
        """Record a transformation for a specific line item."""
        self.item_lineage.setdefault(canonical_name, []).append(
            {
                "stage": stage,
                "action": action,
                "original_label": original_label,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **(details or {}),
            }
        )

    def get_item_lineage(self, canonical_name: str) -> List[Dict]:
        """Get transformation chain for a specific item."""
        return self.item_lineage.get(canonical_name, [])

    def get_all_item_lineage(self) -> Dict[str, List[Dict]]:
        """Get all item lineage for persistence."""
        return dict(self.item_lineage)

    def get_summary(self) -> Dict:
        """
        Get a summary of lineage events.

        Returns:
            Dict with event count and stage information
        """
        return {
            "total_events": len(self.events),
            "stages": list({event["stage"] for event in self.events}),
            "event_types": list({event["event_type"] for event in self.events}),
        }
