#!/usr/bin/env python3
"""
Safe database migration utility with pre-flight checks and backups.

Provides:
- Pre-flight safety checks before migration
- Automatic backup before migration
- Migration validation
- Rollback capability

Usage:
    python scripts/safe_migrate.py --check          # Check pending migrations
    python scripts/safe_migrate.py --upgrade        # Run migrations with safety checks
    python scripts/safe_migrate.py --rollback       # Rollback last migration
    python scripts/safe_migrate.py --backup         # Create backup only
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import settings
from src.core.logging import setup_logging

logger = setup_logging(level="INFO")


# ============================================================================
# Migration Analysis
# ============================================================================


class MigrationSafetyChecker:
    """Analyze migrations for potential safety issues."""

    DANGEROUS_PATTERNS = {
        "DROP TABLE": {
            "severity": "CRITICAL",
            "message": "Drops entire table - DATA LOSS",
            "recommendation": "Export data first, coordinate downtime",
        },
        "DROP COLUMN": {
            "severity": "CRITICAL",
            "message": "Drops column - DATA LOSS",
            "recommendation": "Deprecated column first, remove in next release",
        },
        "ALTER COLUMN.*TYPE": {
            "severity": "HIGH",
            "message": "Changes column type - may require table rewrite",
            "recommendation": "Test on copy of production data, plan downtime",
        },
        "CREATE UNIQUE INDEX": {
            "severity": "MEDIUM",
            "message": "Creates unique index - requires table lock",
            "recommendation": "Use CONCURRENTLY if possible, plan for lock time",
        },
        "ALTER TABLE.*ADD CONSTRAINT.*FOREIGN KEY": {
            "severity": "MEDIUM",
            "message": "Adds foreign key - requires validation scan",
            "recommendation": "Add as NOT VALID first, validate separately",
        },
        "ALTER TABLE.*ADD CONSTRAINT.*CHECK": {
            "severity": "MEDIUM",
            "message": "Adds check constraint - requires validation scan",
            "recommendation": "Add as NOT VALID first, validate separately",
        },
    }

    def analyze_migration(self, migration_path: Path) -> Dict:
        """
        Analyze migration file for safety issues.

        Args:
            migration_path: Path to migration file

        Returns:
            dict: Analysis results with warnings and recommendations
        """
        with open(migration_path) as f:
            content = f.read()

        warnings = []
        severity_levels = []

        for pattern, info in self.DANGEROUS_PATTERNS.items():
            if re.search(pattern, content, re.IGNORECASE):
                warnings.append(
                    {
                        "pattern": pattern,
                        "severity": info["severity"],
                        "message": info["message"],
                        "recommendation": info["recommendation"],
                    }
                )
                severity_levels.append(info["severity"])

        # Determine overall safety
        if "CRITICAL" in severity_levels:
            safety_level = "UNSAFE"
        elif "HIGH" in severity_levels:
            safety_level = "RISKY"
        elif "MEDIUM" in severity_levels:
            safety_level = "CAUTION"
        else:
            safety_level = "SAFE"

        return {
            "file": migration_path.name,
            "safety_level": safety_level,
            "warnings": warnings,
            "requires_downtime": safety_level in ["UNSAFE", "RISKY"],
        }

    def analyze_all_pending(self) -> List[Dict]:
        """Analyze all pending migrations."""
        # Get pending migrations from Alembic
        subprocess.run(["alembic", "heads"], capture_output=True, text=True, check=True)

        # This is simplified - real implementation would parse Alembic output
        migrations_dir = Path("alembic/versions")
        if not migrations_dir.exists():
            return []

        pending_analyses = []
        for migration_file in sorted(migrations_dir.glob("*.py")):
            if migration_file.name == "__init__.py":
                continue
            analysis = self.analyze_migration(migration_file)
            pending_analyses.append(analysis)

        return pending_analyses


# ============================================================================
# Database Backup
# ============================================================================


class DatabaseBackup:
    """Handle database backups before migrations."""

    def __init__(self):
        self.backup_dir = Path("backups")
        self.backup_dir.mkdir(exist_ok=True)

    def create_backup(self, label: str = "pre-migration") -> Path:
        """
        Create PostgreSQL backup.

        Args:
            label: Label for backup file

        Returns:
            Path to backup file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"debtfund_{label}_{timestamp}.sql"

        logger.info(f"Creating database backup: {backup_file}")

        # Extract connection details from DATABASE_URL
        # postgresql://user:pass@host:port/dbname
        import re

        match = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", settings.database_url)
        if not match:
            raise ValueError("Could not parse DATABASE_URL")

        user, password, host, port, dbname = match.groups()

        # Create pg_dump command
        cmd = [
            "pg_dump",
            "-h",
            host,
            "-p",
            port,
            "-U",
            user,
            "-d",
            dbname,
            "-f",
            str(backup_file),
            "--clean",  # Include DROP statements
            "--if-exists",  # Use IF EXISTS
            "--create",  # Include CREATE DATABASE
        ]

        # Set password via environment
        import os

        env = os.environ.copy()
        env["PGPASSWORD"] = password

        try:
            subprocess.run(cmd, check=True, env=env, capture_output=True)
            logger.info(f"✅ Backup created successfully: {backup_file}")
            logger.info(f"   Size: {backup_file.stat().st_size / 1024 / 1024:.2f} MB")
            return backup_file
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Backup failed: {e.stderr.decode()}")
            raise

    def restore_backup(self, backup_file: Path):
        """
        Restore database from backup.

        Args:
            backup_file: Path to backup file
        """
        logger.warning(f"Restoring database from backup: {backup_file}")

        # Extract connection details
        import re

        match = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", settings.database_url)
        if not match:
            raise ValueError("Could not parse DATABASE_URL")

        user, password, host, port, dbname = match.groups()

        # Create psql command
        cmd = [
            "psql",
            "-h",
            host,
            "-p",
            port,
            "-U",
            user,
            "-d",
            dbname,
            "-f",
            str(backup_file),
        ]

        # Set password via environment
        import os

        env = os.environ.copy()
        env["PGPASSWORD"] = password

        try:
            subprocess.run(cmd, check=True, env=env)
            logger.info("✅ Database restored successfully")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Restore failed: {e}")
            raise


# ============================================================================
# Safe Migration Executor
# ============================================================================


class SafeMigration:
    """Execute migrations with safety checks and backups."""

    def __init__(self):
        self.checker = MigrationSafetyChecker()
        self.backup = DatabaseBackup()

    def check_migrations(self):
        """Check pending migrations for safety issues."""
        logger.info("=" * 60)
        logger.info("CHECKING PENDING MIGRATIONS")
        logger.info("=" * 60)

        analyses = self.checker.analyze_all_pending()

        if not analyses:
            logger.info("✅ No pending migrations")
            return

        for analysis in analyses:
            logger.info(f"\nMigration: {analysis['file']}")
            logger.info(f"Safety Level: {analysis['safety_level']}")

            if analysis["warnings"]:
                logger.warning(f"Found {len(analysis['warnings'])} warnings:")
                for warning in analysis["warnings"]:
                    logger.warning(f"  [{warning['severity']}] {warning['message']}")
                    logger.warning(f"    Recommendation: {warning['recommendation']}")

            if analysis["requires_downtime"]:
                logger.warning("  ⚠️  This migration may require downtime")

    def upgrade(self, auto_backup: bool = True, force: bool = False):
        """
        Run migrations with safety checks.

        Args:
            auto_backup: Create backup before migration
            force: Skip safety checks and run anyway
        """
        logger.info("=" * 60)
        logger.info("SAFE MIGRATION UPGRADE")
        logger.info("=" * 60)

        # Check migrations for safety
        if not force:
            self.check_migrations()

            # Ask for confirmation
            response = input("\nProceed with migration? (yes/no): ")
            if response.lower() != "yes":
                logger.info("Migration cancelled")
                return

        # Create backup
        if auto_backup:
            try:
                backup_file = self.backup.create_backup()
                logger.info(f"Backup created: {backup_file}")
            except Exception as e:
                logger.error(f"Backup failed: {e}")
                if not force:
                    logger.error("Aborting migration due to backup failure")
                    return
                logger.warning("Proceeding without backup (forced)")

        # Run migration
        logger.info("\nRunning Alembic upgrade...")
        try:
            result = subprocess.run(
                ["alembic", "upgrade", "head"], check=True, capture_output=True, text=True
            )
            logger.info(result.stdout)
            logger.info("✅ Migration completed successfully")

        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Migration failed: {e.stderr}")

            if auto_backup:
                logger.error("\nRolling back to backup...")
                try:
                    self.backup.restore_backup(backup_file)
                    logger.info("✅ Rollback completed")
                except Exception as restore_error:
                    logger.error(f"❌ Rollback failed: {restore_error}")
                    logger.error("MANUAL INTERVENTION REQUIRED")

            raise

    def rollback(self):
        """Rollback last migration."""
        logger.info("=" * 60)
        logger.info("ROLLBACK LAST MIGRATION")
        logger.info("=" * 60)

        # Create backup before rollback
        self.backup.create_backup(label="pre-rollback")

        # Rollback
        logger.info("\nRunning Alembic downgrade...")
        try:
            result = subprocess.run(
                ["alembic", "downgrade", "-1"], check=True, capture_output=True, text=True
            )
            logger.info(result.stdout)
            logger.info("✅ Rollback completed successfully")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Rollback failed: {e.stderr}")
            raise


# ============================================================================
# CLI
# ============================================================================


def main():
    parser = argparse.ArgumentParser(description="Safe database migration utility")
    parser.add_argument("--check", action="store_true", help="Check pending migrations")
    parser.add_argument("--upgrade", action="store_true", help="Run migrations")
    parser.add_argument("--rollback", action="store_true", help="Rollback last migration")
    parser.add_argument("--backup", action="store_true", help="Create backup only")
    parser.add_argument("--force", action="store_true", help="Skip safety checks")
    parser.add_argument("--no-backup", action="store_true", help="Skip automatic backup")

    args = parser.parse_args()

    migrator = SafeMigration()

    if args.check:
        migrator.check_migrations()

    elif args.upgrade:
        migrator.upgrade(auto_backup=not args.no_backup, force=args.force)

    elif args.rollback:
        migrator.rollback()

    elif args.backup:
        backup_file = migrator.backup.create_backup()
        logger.info(f"Backup created: {backup_file}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
