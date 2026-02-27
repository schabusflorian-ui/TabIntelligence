#!/bin/bash
# Reset database to clean state using Alembic migrations.
#
# Usage:
#   ./scripts/db_reset.sh          # Reset and re-apply all migrations
#   ./scripts/db_reset.sh --seed   # Reset, migrate, and seed with sample data
#
# WARNING: This will destroy ALL data in the database.
# Only use in development or testing environments.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== DebtFund Database Reset ===${NC}"

# Safety check: refuse to run if DATABASE_URL looks like production
if [[ "${DATABASE_URL:-}" == *"rds.amazonaws.com"* ]] || [[ "${DATABASE_URL:-}" == *"production"* ]]; then
    echo -e "${RED}ERROR: Refusing to reset what looks like a production database!${NC}"
    echo "DATABASE_URL: ${DATABASE_URL}"
    exit 1
fi

echo -e "${YELLOW}WARNING: This will destroy ALL data in the database.${NC}"
echo -n "Are you sure? (y/N): "
read -r confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

# Step 1: Downgrade all migrations
echo -e "\n${YELLOW}Step 1: Downgrading all migrations...${NC}"
if alembic downgrade base 2>&1; then
    echo -e "${GREEN}All migrations downgraded successfully${NC}"
else
    echo -e "${YELLOW}Downgrade failed (database may already be empty), continuing...${NC}"
fi

# Step 2: Upgrade to latest
echo -e "\n${YELLOW}Step 2: Applying all migrations...${NC}"
alembic upgrade head
echo -e "${GREEN}All migrations applied successfully${NC}"

# Step 3: Show current state
echo -e "\n${YELLOW}Step 3: Current migration state:${NC}"
alembic current

# Step 4: Optional seed
if [[ "${1:-}" == "--seed" ]]; then
    echo -e "\n${YELLOW}Step 4: Seeding database with sample data...${NC}"
    python -m scripts.db_seed
    echo -e "${GREEN}Database seeded successfully${NC}"
fi

echo -e "\n${GREEN}=== Database reset complete ===${NC}"
