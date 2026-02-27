# Contributing to DebtFund

## The Four Laws

These principles guide all development work on DebtFund:

1. **End-to-end or nothing** - Every change must be tested end-to-end before merging
2. **Test what matters** - Write tests that validate business value, not implementation details
3. **Proactive communication** - Document decisions, blockers, and progress openly
4. **Honest status reporting** - Report actual status, not aspirational status

## Development Workflow

### 1. Branch Strategy

Create feature branches from `main` using this naming convention:

```
agent-N/DX.Y-description
```

Examples:
- `agent-1/D1.1-entity-table-migration`
- `agent-3/D3.3-stage4-structure-extraction`
- `infrastructure/ci-cd-pipeline`

### 2. Before You Code

1. **Check the plan** - Review [agent_kickoff_briefs_v3.md](docs/architecture/agent_kickoff_briefs_v3.md) for deliverable requirements
2. **Check dependencies** - Verify all dependent deliverables are complete
3. **Write tests FIRST** - Define success criteria via tests before implementation

### 3. Development Process

```bash
# Create branch
git checkout -b agent-3/D3.2-implement-triage

# Write tests first (RED)
# Edit tests/unit/test_triage.py

# Implement feature (GREEN)
# Edit src/agents/agent_03_orchestrator.py

# Refactor (REFACTOR)
# Clean up code while keeping tests green

# Run tests locally
pytest -v

# Check linting
ruff check src tests

# Ensure pre-commit passes
pre-commit run --all-files
```

### 4. Commit Message Format

```
[Agent N] Brief description

Longer explanation if needed. Reference deliverable IDs.

Deliverable: DX.Y
```

Examples:
```
[Agent 1] Add entity_patterns table migration

Creates the entity_patterns table with columns for pattern matching.
Includes seed data for common financial terms.

Deliverable: D1.2
```

```
[Agent 3] Implement stage 4 structure extraction

Adds the structure extraction stage that identifies hierarchical
relationships between line items.

Deliverable: D3.3
```

```
[Infrastructure] Add CI/CD pipeline

Sets up GitHub Actions for linting, testing, and security checks.
```

### 5. Pull Request Process

1. **Open PR** using the PR template
2. **Fill in all sections** - Don't skip the checklist
3. **Ensure CI passes** - Green checks required
4. **Self-review** - Check your own diff before requesting review
5. **Lineage check** - If PR modifies data transformation, verify lineage events are emitted
6. **Merge** - Once approved and CI passes

### 6. Merge to Main

After merge:
1. **Delete branch** - Keep repo clean
2. **Update status** - Mark deliverable as complete in tracking
3. **Document learnings** - Add any insights to relevant docs

## Code Standards

### Python Style

- **Formatter**: Ruff (configured in `pyproject.toml`)
- **Line length**: 100 characters
- **Type hints**: Use them for public APIs
- **Docstrings**: Required for all public functions/classes

### Testing Standards

#### Test Structure

```python
def test_function_scenario_expected_outcome():
    """Test that function does X when Y happens"""
    # Arrange
    setup_data = ...

    # Act
    result = function_under_test(setup_data)

    # Assert
    assert result == expected_value
```

#### Coverage Requirements

- **Unit tests**: 80% minimum coverage
- **Critical paths**: 100% coverage required
  - Lineage emission
  - Validation logic
  - Mapping transformations

#### Test Organization

```
tests/
├── unit/              # Fast, isolated tests
│   ├── test_orchestrator.py
│   ├── test_lineage.py
│   └── test_validation.py
├── integration/       # API and database tests
│   ├── test_api_endpoints.py
│   └── test_extraction_pipeline.py
└── fixtures/          # Test data
    ├── sample_model.xlsx
    └── mock_responses.json
```

### Lineage Requirements (EXISTENTIAL)

**Every data transformation MUST emit lineage events.**

If your code:
- Parses Excel sheets
- Transforms data structures
- Maps to canonical taxonomy
- Validates line items
- Calibrates confidence scores

Then it **MUST** use the `LineageTracker`:

```python
from src.agents.agent_06_lineage import LineageTracker

lineage = LineageTracker(job_id=job_id)
output_id = lineage.emit(
    event_type="parse",
    stage=1,
    metadata={"sheets_found": len(sheets)}
)
```

**Lineage tests are required** for all data transformation PRs:
- Test that events are emitted
- Test chain integrity (input → output links)
- Test completeness validation

## Project Structure

```
DebtFund/
├── src/                    # Source code
│   ├── agents/            # Agent modules (1-9)
│   ├── api/               # FastAPI endpoints
│   ├── core/              # Config, logging, exceptions
│   ├── db/                # Models, migrations, session
│   └── extraction/        # Orchestrator (Agent 3)
├── tests/                 # Test suite
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/                  # Documentation
│   ├── architecture/
│   ├── governance/
│   └── development/
├── scripts/               # Utility scripts
└── alembic/              # Database migrations
```

## Definition of Done

A deliverable is considered "done" when:

- [ ] Code implemented and follows style guide
- [ ] Unit tests written and passing (80%+ coverage)
- [ ] Integration tests passing
- [ ] Lineage events emitted (if data transformation)
- [ ] Lineage tests added (if applicable)
- [ ] CI pipeline green (lint, test, security)
- [ ] PR approved and merged
- [ ] Documentation updated
- [ ] Manually tested end-to-end
- [ ] No known bugs or blockers

## Common Tasks

### Run the Application

```bash
# Start services
docker-compose up -d

# Run API server
uvicorn src.api.main:app --reload

# Run a script
python scripts/poc_guided_extraction.py
```

### Run Tests

```bash
# All tests
pytest -v

# Specific test file
pytest tests/unit/test_orchestrator.py -v

# With coverage
pytest -v --cov=src --cov-report=html

# Integration tests only
pytest tests/integration/ -v
```

### Database Migrations

```bash
# Create migration
alembic revision -m "Add new table"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Code Quality

```bash
# Format code
ruff format src tests

# Lint code
ruff check src tests

# Fix auto-fixable issues
ruff check --fix src tests

# Run pre-commit hooks
pre-commit run --all-files
```

## Getting Help

### Documentation

- [Getting Started](docs/development/GETTING_STARTED.md) - Initial setup
- [Agent Briefs](docs/architecture/agent_kickoff_briefs_v3.md) - Agent deliverables
- [Governance](docs/governance/project_governance_v3.md) - Project rules

### Questions

For questions or issues:
1. Check documentation first
2. Search existing GitHub issues
3. Create new issue with `question` label

## Agent Ownership

Each agent has an owner responsible for deliverables:

| Agent | Responsibility | Files |
|-------|---------------|-------|
| Agent 1 | Database schema & ORM | `src/db/` |
| Agent 2 | API endpoints | `src/api/` |
| Agent 3 | Extraction orchestrator | `src/extraction/`, `src/agents/agent_03_*.py` |
| Agent 4 | Guidelines & taxonomy | `src/agents/agent_04_*.py` |
| Agent 5 | Validation engine | `src/agents/agent_05_*.py` |
| Agent 6 | Lineage & provenance | `src/agents/agent_06_*.py` |
| Agent 7 | Calibration | `src/agents/agent_07_*.py` |
| Agent 8 | Excel Add-in | Separate repo (future) |
| Agent 9 | Review Dashboard | Separate repo (future) |

## License

This project is proprietary. See [LICENSE](LICENSE) for details.
