"""Backfill period_normalized on extraction_facts from job result metadata.

Reads detected_periods from ExtractionJob.result['period_metadata'],
builds raw_value -> normalized lookup, and updates matching facts.

Revision ID: k5l6m7n8o9p0
Revises: j4k5l6m7n8o9
Create Date: 2026-03-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k5l6m7n8o9p0"
down_revision: Union[str, Sequence[str], None] = "j4k5l6m7n8o9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Fetch all jobs that have period_metadata in their result
    jobs = conn.execute(
        sa.text(
            "SELECT job_id, result FROM extraction_jobs "
            "WHERE result IS NOT NULL"
        )
    )

    updated_total = 0
    for row in jobs:
        job_id = row[0]
        result = row[1]
        if not isinstance(result, dict):
            continue

        period_metadata = result.get("period_metadata")
        if not period_metadata or not isinstance(period_metadata, dict):
            continue

        # Build raw_value -> normalized lookup from all sheets
        lookup: dict[str, str] = {}
        for _sheet_name, detection in period_metadata.items():
            if not isinstance(detection, dict):
                continue
            for p in detection.get("periods", []):
                if not isinstance(p, dict):
                    continue
                raw = p.get("raw_value", "")
                norm = p.get("normalized", "")
                if raw and norm:
                    lookup[raw] = norm

        if not lookup:
            continue

        # Update facts for this job where period_normalized is NULL
        for raw_val, norm_val in lookup.items():
            result = conn.execute(
                sa.text(
                    "UPDATE extraction_facts "
                    "SET period_normalized = :norm "
                    "WHERE job_id = :job_id AND period = :period "
                    "AND period_normalized IS NULL"
                ),
                {"norm": norm_val, "job_id": str(job_id), "period": raw_val},
            )
            updated_total += result.rowcount

    if updated_total > 0:
        print(f"Backfilled period_normalized for {updated_total} extraction facts")


def downgrade() -> None:
    # Set period_normalized back to NULL (data-only migration)
    op.execute("UPDATE extraction_facts SET period_normalized = NULL")
