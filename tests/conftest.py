"""
Pytest configuration and shared fixtures.
"""
# Mock boto3 and celery BEFORE any imports that might use them
import sys
from unittest.mock import MagicMock

# Create a mock boto3 module
mock_boto3_module = MagicMock()
mock_s3_client = MagicMock()
mock_s3_client.put_object.return_value = {"ETag": "mock-etag"}
mock_s3_client.get_object.return_value = {"Body": MagicMock(read=lambda: b"mock file content")}
mock_s3_client.head_bucket.return_value = {}
mock_s3_client.create_bucket.return_value = {}
mock_boto3_module.client.return_value = mock_s3_client
sys.modules['boto3'] = mock_boto3_module
sys.modules['botocore'] = MagicMock()
sys.modules['botocore.config'] = MagicMock()
sys.modules['botocore.exceptions'] = MagicMock()

# Create a mock celery module
mock_celery_module = MagicMock()
mock_celery_app = MagicMock()
mock_celery_module.Celery.return_value = mock_celery_app
sys.modules['celery'] = mock_celery_module
sys.modules['celery.result'] = MagicMock()
sys.modules['celery.exceptions'] = MagicMock()
sys.modules['redis'] = MagicMock()
sys.modules['kombu'] = MagicMock()
sys.modules['kombu.serialization'] = MagicMock()

# Now safe to import other modules
import pytest
import uuid
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from src.db.base import Base


@pytest.fixture
def mock_celery_task():
    """Mock Celery task execution for tests - executes synchronously."""
    from src.jobs.tasks import run_extraction_task

    # Store original function
    original_func = run_extraction_task

    def sync_execution(job_id, file_bytes, entity_id=None):
        """Execute the task synchronously for testing."""
        # Call the actual task function directly (not via Celery)
        return original_func(job_id, file_bytes, entity_id)

    # Patch where it's imported (in main.py), not where it's defined
    with patch("src.api.main.run_extraction_task") as mock_task:
        # Mock the delay method to execute synchronously
        mock_result = MagicMock()
        mock_result.id = "mock-task-id-12345"

        # When delay() is called, execute synchronously
        def delay_side_effect(job_id, file_bytes, entity_id=None):
            sync_execution(job_id, file_bytes, entity_id)
            return mock_result

        mock_task.delay = delay_side_effect
        yield mock_task


@pytest.fixture
def mock_api_key():
    """Mock API key for authenticated test requests."""
    from src.auth.models import APIKey
    key = Mock(spec=APIKey)
    key.id = None  # None avoids FK violations on audit_logs.api_key_id
    key.name = "test-key"
    key.key_hash = "testhash"
    key.entity_id = None
    key.is_active = True
    key.rate_limit_per_minute = 60
    key.last_used_at = None
    return key


@pytest.fixture
def test_client(mock_celery_task, mock_api_key):
    """FastAPI test client for API testing (with auth bypass)."""
    from src.api.main import app
    from src.auth.dependencies import get_current_api_key

    app.dependency_overrides[get_current_api_key] = lambda: mock_api_key
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_current_api_key, None)


@pytest.fixture
def unauthenticated_client(mock_celery_task, test_db):
    """FastAPI test client WITHOUT auth bypass — for testing 401 responses."""
    from src.api.main import app
    from src.db.session import get_db

    def override_get_db():
        db = test_db()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_xlsx():
    """Load sample Excel file for testing."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_model.xlsx"
    if not fixture_path.exists():
        pytest.skip(f"Test fixture not found: {fixture_path}")

    with open(fixture_path, "rb") as f:
        return f.read()


@pytest.fixture
def sample_xlsx_path():
    """Path to sample Excel file."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_model.xlsx"
    if not fixture_path.exists():
        pytest.skip(f"Test fixture not found: {fixture_path}")
    return str(fixture_path)


@pytest.fixture
def mock_claude_parsing_response():
    """Mock Claude API response for Stage 1: Parsing."""
    return {
        "sheets": [
            {
                "sheet_name": "Income Statement",
                "sheet_type": "income_statement",
                "layout": "time_across_columns",
                "periods": ["FY2022", "FY2023", "FY2024E"],
                "rows": [
                    {
                        "row_index": 2,
                        "label": "Revenue",
                        "hierarchy_level": 1,
                        "values": {"FY2022": 100000, "FY2023": 115000, "FY2024E": 132000},
                        "is_formula": False,
                        "is_subtotal": False
                    },
                    {
                        "row_index": 4,
                        "label": "Cost of Goods Sold",
                        "hierarchy_level": 1,
                        "values": {"FY2022": 40000, "FY2023": 46000, "FY2024E": 53000},
                        "is_formula": False,
                        "is_subtotal": False
                    },
                    {
                        "row_index": 5,
                        "label": "Gross Profit",
                        "hierarchy_level": 1,
                        "values": {"FY2022": 60000, "FY2023": 69000, "FY2024E": 79000},
                        "is_formula": True,
                        "is_subtotal": True
                    }
                ]
            },
            {
                "sheet_name": "Balance Sheet",
                "sheet_type": "balance_sheet",
                "layout": "time_across_columns",
                "periods": ["FY2022", "FY2023", "FY2024E"],
                "rows": []
            }
        ]
    }


@pytest.fixture
def mock_claude_triage_response():
    """Mock Claude API response for Stage 2: Triage."""
    return [
        {
            "sheet_name": "Income Statement",
            "tier": 1,
            "decision": "PROCESS_HIGH",
            "confidence": 0.95,
            "reasoning": "Standard income statement with revenue, costs, and profitability"
        },
        {
            "sheet_name": "Balance Sheet",
            "tier": 1,
            "decision": "PROCESS_HIGH",
            "confidence": 0.95,
            "reasoning": "Standard balance sheet with assets, liabilities, and equity"
        },
        {
            "sheet_name": "Scratch - Working",
            "tier": 4,
            "decision": "SKIP",
            "confidence": 0.99,
            "reasoning": "Scratch sheet with notes, should be skipped"
        }
    ]


@pytest.fixture
def mock_claude_mapping_response():
    """Mock Claude API response for Stage 3: Mapping."""
    return [
        {
            "original_label": "Revenue",
            "canonical_name": "revenue",
            "confidence": 0.95,
            "reasoning": "Direct match for revenue"
        },
        {
            "original_label": "Cost of Goods Sold",
            "canonical_name": "cogs",
            "confidence": 0.95,
            "reasoning": "Standard abbreviation for Cost of Goods Sold"
        },
        {
            "original_label": "Gross Profit",
            "canonical_name": "gross_profit",
            "confidence": 0.95,
            "reasoning": "Standard gross profit calculation"
        }
    ]


@pytest.fixture
def mock_claude_client(mock_claude_parsing_response, mock_claude_triage_response, mock_claude_mapping_response):
    """
    Mock Anthropic Claude client for testing without API calls.

    This fixture returns a mock client that simulates Claude's responses
    for the 3-stage extraction pipeline.
    """
    mock_client = MagicMock()

    # Track which stage we're on based on the prompt content
    def create_mock_response(model, max_tokens, messages):
        """Determine which stage based on prompt content and return appropriate mock."""
        prompt_text = ""
        for msg in messages:
            if isinstance(msg.get("content"), str):
                prompt_text = msg["content"]
            elif isinstance(msg.get("content"), list):
                for item in msg["content"]:
                    if isinstance(item, dict) and item.get("type") == "text":
                        prompt_text = item.get("text", "")

        # Determine stage from prompt
        if "parsing" in prompt_text.lower() or "extract all data" in prompt_text.lower():
            response_data = mock_claude_parsing_response
        elif "triage" in prompt_text.lower() or "classify each sheet" in prompt_text.lower():
            response_data = mock_claude_triage_response
        elif "validation flags" in prompt_text.lower():
            # Stage 4: Validation reasoning
            response_data = [
                {"flag_index": 0, "assessment": "acceptable", "confidence": 0.8,
                 "reasoning": "Variation within tolerance", "suggested_fix": None}
            ]
        elif "hierarchy context" in prompt_text.lower() or "items to map" in prompt_text.lower():
            # Stage 5: Enhanced mapping
            response_data = mock_claude_mapping_response
        elif "mapping" in prompt_text.lower() or "canonical" in prompt_text.lower():
            response_data = mock_claude_mapping_response
        else:
            response_data = {"error": "Unknown stage"}

        # Create mock response object
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(response_data))]
        mock_response.usage = MagicMock(input_tokens=500, output_tokens=300)

        return mock_response

    mock_client.messages.create = MagicMock(side_effect=create_mock_response)

    return mock_client


@pytest.fixture
def mock_anthropic(monkeypatch, mock_claude_client):
    """
    Monkeypatch the Anthropic client getter to use mock responses.

    Use this fixture in tests to avoid making real API calls.
    """
    def mock_get_claude_client():
        return mock_claude_client

    # Mock the LineageTracker save_to_db to avoid database calls
    def mock_save_to_db(self):
        """Mock save_to_db to do nothing (sync - matches actual implementation)."""
        pass

    monkeypatch.setattr(
        "src.extraction.claude_client.get_claude_client",
        mock_get_claude_client
    )
    monkeypatch.setattr(
        "src.extraction.stages.parsing.get_claude_client",
        mock_get_claude_client
    )
    monkeypatch.setattr(
        "src.extraction.stages.triage.get_claude_client",
        mock_get_claude_client
    )
    monkeypatch.setattr(
        "src.extraction.stages.mapping.get_claude_client",
        mock_get_claude_client
    )
    monkeypatch.setattr(
        "src.extraction.stages.validation.get_claude_client",
        mock_get_claude_client
    )
    monkeypatch.setattr(
        "src.extraction.stages.enhanced_mapping.get_claude_client",
        mock_get_claude_client
    )
    monkeypatch.setattr(
        "src.lineage.tracker.LineageTracker.save_to_db",
        mock_save_to_db
    )
    return mock_claude_client


# ============================================================================
# Database Test Fixtures
# ============================================================================

@pytest.fixture(scope="function")
def test_db():
    """
    Create an in-memory SQLite database for testing.

    Uses SQLite instead of PostgreSQL for faster, isolated tests.
    The database is created fresh for each test function.
    """
    # Use SQLite in-memory for fast tests
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create session factory
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    yield TestingSessionLocal

    # Cleanup
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(test_db):
    """
    Provide a database session for tests.

    The session is automatically closed after the test completes.
    """
    session = test_db()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_client_with_db(test_db, mock_api_key):
    """
    FastAPI test client with test database override and auth bypass.

    This fixture overrides the get_db dependency to use the test database
    instead of the production database. Use this instead of test_client
    for tests that interact with the database.
    """
    from src.api.main import app
    from src.db.session import get_db
    from src.auth.dependencies import get_current_api_key

    def override_get_db():
        db = test_db()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_api_key] = lambda: mock_api_key

    client = TestClient(app)

    yield client

    # Cleanup
    app.dependency_overrides.clear()


@pytest.fixture
def sample_file(db_session):
    """
    Create a sample file record in the test database.

    Useful for tests that need a file to work with.
    """
    from src.db import crud

    file = crud.create_file(
        db_session,
        filename="test_model.xlsx",
        file_size=1024 * 50,  # 50 KB
    )
    return file


@pytest.fixture
def sample_job(db_session, sample_file):
    """
    Create a sample extraction job in the test database.

    Useful for tests that need a job to work with.
    """
    from src.db import crud

    job = crud.create_extraction_job(
        db_session,
        file_id=sample_file.file_id,
    )
    return job


# ============================================================================
# NOTE: Async database fixtures removed - not in Week 2 scope
# Using synchronous database only. Will add async support in Week 4+ if needed.
# ============================================================================
