#!/usr/bin/env bash
# =============================================================================
# DebtFund E2E Test Runner
# =============================================================================
# Usage:
#   ./scripts/e2e.sh          # Mock Claude (free, fast, deterministic)
#   ./scripts/e2e.sh real     # Real Claude (needs ANTHROPIC_API_KEY, ~$0.02)
#   ./scripts/e2e.sh clean    # Tear down containers
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

MODE="${1:-mock}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.e2e.yml"

# Known API key (must match init_e2e_db.py and docker-compose.e2e.yml)
E2E_API_KEY="emi_e2e_test_key_for_integration_testing"
E2E_BASE_URL="http://localhost:8100"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

cleanup() {
    echo ""
    echo "Tearing down..."
    $COMPOSE down -v --remove-orphans 2>/dev/null || true
}

wait_for_health() {
    local url="$1"
    local max_attempts="${2:-30}"
    echo "Waiting for $url ..."
    for i in $(seq 1 "$max_attempts"); do
        if curl -sf "$url" > /dev/null 2>&1; then
            echo "  Healthy!"
            return 0
        fi
        echo "  Attempt $i/$max_attempts..."
        sleep 3
    done
    echo "ERROR: Service at $url did not become healthy."
    $COMPOSE logs app worker init-db mock-claude
    return 1
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

if [ "$MODE" = "clean" ]; then
    cleanup
    echo "Done."
    exit 0
fi

echo "============================================"
echo "DebtFund E2E Tests (mode: $MODE)"
echo "============================================"

# Cleanup on exit
trap cleanup EXIT

# Validate real mode
if [ "$MODE" = "real" ]; then
    if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
        echo "ERROR: ANTHROPIC_API_KEY required for real mode"
        echo "Usage: ANTHROPIC_API_KEY=sk-ant-... ./scripts/e2e.sh real"
        exit 1
    fi
    echo "Using REAL Claude API (cost: ~\$0.02/run)"
    # TODO: override ANTHROPIC_BASE_URL and ANTHROPIC_API_KEY for real mode
fi

# Build and start
echo ""
echo "Building and starting services..."
$COMPOSE up --build -d

# Wait for health
echo ""
wait_for_health "$E2E_BASE_URL/" 30

# Run tests
echo ""
echo "Running E2E tests..."
echo "--------------------------------------------"
E2E_BASE_URL="$E2E_BASE_URL" \
E2E_API_KEY="$E2E_API_KEY" \
    python -m pytest tests/e2e/ -v --no-header --tb=short -p no:cacheprovider

echo ""
echo "============================================"
echo "All E2E tests passed!"
echo "============================================"
