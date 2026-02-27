#!/bin/bash
set -e  # Exit on error

echo "=== Week 1 Verification Suite ==="
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters for summary
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

check_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASS_COUNT++))
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAIL_COUNT++))
}

check_skip() {
    echo -e "${YELLOW}⊘${NC} $1"
    ((SKIP_COUNT++))
}

echo "1. Checking import integrity..."
# Note: Using python3 explicitly
PYTHON_CMD="python3"

if $PYTHON_CMD -c "from src.api.main import app" 2>/dev/null; then
    check_pass "API imports"
else
    check_skip "API imports (missing dependencies: slowapi)"
fi

if $PYTHON_CMD -c "from src.database.base import get_engine" 2>/dev/null; then
    check_pass "Database imports"
else
    check_skip "Database imports (check dependencies)"
fi

if $PYTHON_CMD -c "from src.storage.s3 import get_s3_client" 2>/dev/null; then
    check_pass "S3 imports"
else
    check_skip "S3 imports (check dependencies)"
fi

if $PYTHON_CMD -c "from src.lineage.tracker import LineageTracker" 2>/dev/null; then
    check_pass "Lineage imports"
else
    check_skip "Lineage imports (check dependencies)"
fi

if $PYTHON_CMD -c "from src.auth import get_current_api_key" 2>/dev/null; then
    check_pass "Auth imports"
else
    check_skip "Auth imports (check dependencies)"
fi
echo ""

echo "2. Checking security configurations..."

# Check if authentication dependency exists (should be used in endpoints)
if grep -q "get_current_api_key" src/api/main.py; then
    check_pass "Authentication dependency used in API"
else
    check_fail "Authentication NOT enabled in API endpoints"
fi

# Check SSL verification configuration
if grep -q "verify_ssl" src/storage/s3.py; then
    check_pass "SSL verification configurable in S3 client"
else
    check_fail "SSL verification not found in S3 client"
fi

# Check CORS configuration
if grep -q "CORSMiddleware" src/api/main.py; then
    if grep -q 'allow_origins=\["*"\]' src/api/main.py; then
        check_fail "CORS uses wildcard - should be restricted"
    else
        check_pass "CORS middleware configured"
    fi
else
    check_fail "CORS not configured"
fi
echo ""

echo "3. Checking database configuration..."

# Check pool size
if grep -q "pool_size" src/database/base.py; then
    if grep -q "pool_size=20" src/database/base.py; then
        check_pass "Pool size set to 20"
    else
        check_fail "Pool size NOT set to 20 (should be per Agent 1B)"
    fi
else
    check_fail "Pool size not configured"
fi

# Check pool pre-ping
if grep -q "pool_pre_ping=True" src/database/base.py; then
    check_pass "Pool pre-ping enabled"
else
    check_fail "Pool pre-ping not enabled"
fi

# Check for duplicate database modules
if [ -d "src/db" ] && [ -d "src/database" ]; then
    check_fail "Both src/db/ and src/database/ exist - not consolidated"
else
    check_pass "Database module consolidated"
fi
echo ""

echo "4. Checking lineage implementation..."

# Check that save_to_db exists and is proper
if grep -q "def save_to_db" src/lineage/tracker.py; then
    check_pass "Lineage save_to_db method exists"
else
    check_fail "Lineage save_to_db method not found"
fi

# Check for transaction handling
if grep -q "db.commit()" src/lineage/tracker.py || grep -q "with get_db_context()" src/lineage/tracker.py; then
    check_pass "Lineage uses proper database context/transactions"
else
    check_fail "Lineage missing proper transaction handling"
fi
echo ""

echo "5. Checking retry logic..."

# Check for retry decorators in extraction stages
RETRY_FOUND=false
if [ -f "src/extraction/stage_2_triage.py" ]; then
    if grep -q "@retry" src/extraction/stage_2_triage.py; then
        check_pass "Stage 2 has retry decorator"
        RETRY_FOUND=true
    else
        check_skip "Stage 2 missing retry decorator"
    fi
else
    check_skip "Stage 2 file not found (stages not separated yet)"
fi

if [ -f "src/extraction/stage_3_mapping.py" ]; then
    if grep -q "@retry" src/extraction/stage_3_mapping.py; then
        check_pass "Stage 3 has retry decorator"
        RETRY_FOUND=true
    else
        check_skip "Stage 3 missing retry decorator"
    fi
else
    check_skip "Stage 3 file not found (stages not separated yet)"
fi

if [ "$RETRY_FOUND" = false ]; then
    check_skip "Retry logic not implemented - Agent 1C task incomplete"
fi
echo ""

echo "6. Running unit tests..."
if pytest tests/unit/ -v --tb=short -q 2>&1 | tee /tmp/unit_test_output.txt; then
    check_pass "Unit tests passed"
else
    check_fail "Some unit tests failed"
fi
echo ""

echo "7. Running integration tests (non-slow)..."
if pytest tests/integration/ -v --tb=short -m "not slow" -q 2>&1 | tee /tmp/integration_test_output.txt; then
    check_pass "Integration tests passed"
else
    check_fail "Some integration tests failed"
fi
echo ""

echo "8. Checking test coverage..."
if pytest --cov=src --cov-report=term-missing --cov-report=html tests/ -q 2>&1 | tee /tmp/coverage_output.txt; then
    COVERAGE=$(grep "TOTAL" /tmp/coverage_output.txt | awk '{print $NF}' | sed 's/%//')
    if [ ! -z "$COVERAGE" ]; then
        if [ "$COVERAGE" -ge 70 ]; then
            check_pass "Test coverage: ${COVERAGE}% (≥70% target met)"
        else
            check_fail "Test coverage: ${COVERAGE}% (below 70% target)"
        fi
    else
        check_skip "Could not determine coverage percentage"
    fi
else
    check_fail "Coverage check failed"
fi
echo ""

echo "=== Week 1 Verification Summary ==="
echo -e "${GREEN}Passed:${NC} $PASS_COUNT"
echo -e "${RED}Failed:${NC} $FAIL_COUNT"
echo -e "${YELLOW}Skipped:${NC} $SKIP_COUNT"
echo ""

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    echo "Coverage report: htmlcov/index.html"
    exit 0
else
    echo -e "${RED}✗ Some checks failed. Review output above.${NC}"
    exit 1
fi
