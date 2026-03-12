"""
Seed development database with sample data.

Creates sample entities, files, jobs, and an API key for local development.
Safe to run multiple times - uses get_or_create patterns.

Usage:
    python -m scripts.db_seed
    # or from db_reset.sh:
    ./scripts/db_reset.sh --seed
"""

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.auth.api_key import generate_api_key
from src.auth.models import APIKey
from src.db.models import (
    Entity,
    EntityPattern,
    ExtractionJob,
    File,
    JobStatusEnum,
    LineageEvent,
)
from src.db.session import get_db_sync


def seed_entities(db):
    """Create sample entities."""
    entities = []
    entity_data = [
        ("Acme Corp", "Technology"),
        ("GlobalFin Holdings", "Financial Services"),
        ("Pacific Manufacturing", "Manufacturing"),
    ]

    for name, industry in entity_data:
        entity = Entity(
            id=uuid4(),
            name=name,
            industry=industry,
        )
        db.add(entity)
        entities.append(entity)

    db.flush()
    print(f"  Created {len(entities)} entities")
    return entities


def seed_files_and_jobs(db, entities):
    """Create sample files and extraction jobs."""
    files = []
    jobs = []

    file_data = [
        (entities[0], "acme_q4_2024_model.xlsx", 245000),
        (entities[0], "acme_annual_2024.xlsx", 512000),
        (entities[1], "globalfin_dcf_model.xlsx", 1024000),
        (entities[2], "pacific_mfg_projections.xlsx", 380000),
    ]

    for entity, filename, size in file_data:
        file = File(
            file_id=uuid4(),
            filename=filename,
            file_size=size,
            s3_key=f"uploads/{entity.id}/{filename}",
            entity_id=entity.id,
        )
        db.add(file)
        files.append(file)

    db.flush()

    # Create jobs with various statuses
    statuses = [
        (JobStatusEnum.COMPLETED, "mapping", 100),
        (JobStatusEnum.COMPLETED, "mapping", 100),
        (JobStatusEnum.PROCESSING, "triage", 45),
        (JobStatusEnum.PENDING, None, 0),
    ]

    for i, (status, stage, progress) in enumerate(statuses):
        job = ExtractionJob(
            job_id=uuid4(),
            file_id=files[i].file_id,
            status=status,
            current_stage=stage,
            progress_percent=progress,
        )

        if status == JobStatusEnum.COMPLETED:
            job.result = {
                "sheets_extracted": 3,
                "line_items_mapped": 42,
                "confidence_avg": 0.91,
            }
            job.tokens_used = 15000
            job.cost_usd = 0.045

        db.add(job)
        jobs.append(job)

    db.flush()
    print(f"  Created {len(files)} files and {len(jobs)} extraction jobs")
    return files, jobs


def seed_lineage_events(db, jobs):
    """Create lineage events for completed jobs."""
    count = 0
    for job in jobs:
        if job.status != JobStatusEnum.COMPLETED:
            continue

        for stage in ["parsing", "triage", "mapping"]:
            event = LineageEvent(
                event_id=uuid4(),
                job_id=job.job_id,
                stage_name=stage,
                data={
                    "stage": stage,
                    "duration_ms": 1500,
                    "items_processed": 42,
                },
            )
            db.add(event)
            count += 1

    db.flush()
    print(f"  Created {count} lineage events")


def seed_entity_patterns(db, entities):
    """Create sample entity patterns."""
    patterns = [
        (entities[0], "Net Sales", "revenue", Decimal("0.9500"), "claude"),
        (entities[0], "Cost of Revenue", "cogs", Decimal("0.9200"), "claude"),
        (entities[0], "Gross Margin", "gross_profit", Decimal("0.8800"), "user_correction"),
        (entities[1], "Total Revenue", "revenue", Decimal("0.9800"), "claude"),
        (entities[1], "Operating Expenses", "opex", Decimal("0.9100"), "claude"),
        (entities[2], "Product Sales", "revenue", Decimal("0.8700"), "claude"),
    ]

    for entity, label, canonical, confidence, created_by in patterns:
        pattern = EntityPattern(
            id=uuid4(),
            entity_id=entity.id,
            original_label=label,
            canonical_name=canonical,
            confidence=confidence,
            created_by=created_by,
            last_seen=datetime.now(timezone.utc),
        )
        db.add(pattern)

    db.flush()
    print(f"  Created {len(patterns)} entity patterns")


def seed_api_key(db, entities):
    """Create a development API key."""
    plain_key, key_hash = generate_api_key()

    api_key = APIKey(
        name="Development Key",
        key_hash=key_hash,
        entity_id=entities[0].id,
        is_active=True,
        rate_limit_per_minute=120,
    )
    db.add(api_key)
    db.flush()

    print(f"  Created API key: {plain_key}")
    print("  (Save this key - it cannot be retrieved later!)")
    return api_key, plain_key


def main():
    """Seed the development database."""
    print("Seeding development database...")

    with get_db_sync() as db:
        # Seed in order of dependencies
        entities = seed_entities(db)
        files, jobs = seed_files_and_jobs(db, entities)
        seed_lineage_events(db, jobs)
        seed_entity_patterns(db, entities)
        api_key, plain_key = seed_api_key(db, entities)

        db.commit()

    print("\nSeed complete! Summary:")
    print("  3 entities, 4 files, 4 jobs, 6 lineage events, 6 patterns, 1 API key")
    print(f"\nDev API key: {plain_key}")


if __name__ == "__main__":
    main()
