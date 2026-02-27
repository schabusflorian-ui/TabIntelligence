"""
Initialize database schema.
Run this script to create all tables.
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.base import init_db
from src.core.logging import setup_logging, database_logger as logger


async def main():
    """Initialize database."""
    setup_logging(level="INFO")

    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialization complete!")


if __name__ == "__main__":
    asyncio.run(main())
