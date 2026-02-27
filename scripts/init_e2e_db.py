"""
Initialize database for E2E testing.

Creates all tables and seeds a deterministic API key so the E2E test
runner knows the key without parsing logs.

Usage:
    python scripts/init_e2e_db.py
"""
import hashlib
import os
import sys
from pathlib import Path
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.base import create_tables
from src.db.session import get_db_sync
from src.db.models import Entity
from src.auth.models import APIKey


# Deterministic key for E2E testing
E2E_API_KEY = os.getenv("E2E_API_KEY", "emi_e2e_test_key_for_integration_testing")


def main():
    print("=== E2E Database Init ===")

    # 1. Create all tables
    print("Creating tables...")
    create_tables()
    print("Tables created.")

    # 2. Seed API key
    print("Seeding API key...")
    key_hash = hashlib.sha256(E2E_API_KEY.encode()).hexdigest()

    with get_db_sync() as db:
        # Create a test entity
        entity = Entity(
            id=uuid4(),
            name="E2E Test Entity",
            industry="Testing",
        )
        db.add(entity)
        db.flush()

        # Create API key with known value
        api_key = APIKey(
            name="E2E Test Key",
            key_hash=key_hash,
            entity_id=entity.id,
            is_active=True,
            rate_limit_per_minute=120,
        )
        db.add(api_key)
        db.commit()

    print(f"API key seeded: {E2E_API_KEY}")
    print("=== Init complete ===")


if __name__ == "__main__":
    main()
