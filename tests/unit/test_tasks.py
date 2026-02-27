"""
Tests for Celery task execution flow.
Tests async_extraction_wrapper directly (run_extraction_task is Celery-decorated
and cannot be tested directly due to module-level Celery mock in conftest).
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4


class TestAsyncExtractionWrapper:
    """Test the async extraction wrapper (not Celery-decorated)."""

    @pytest.mark.asyncio
    async def test_wrapper_runs_extraction_and_completes_job(self):
        """Test wrapper updates job status through full lifecycle."""
        from src.jobs.tasks import async_extraction_wrapper

        job_id = str(uuid4())
        file_bytes = b"fake-bytes"

        mock_db = MagicMock()
        mock_job = MagicMock()
        mock_job.file_id = uuid4()

        mock_result = {
            "file_id": str(mock_job.file_id),
            "sheets": ["IS"],
            "triage": [],
            "line_items": [],
            "tokens_used": 100,
            "cost_usd": 0.003,
        }

        with patch("src.jobs.tasks.get_db_context") as mock_db_ctx, \
             patch("src.jobs.tasks.crud") as mock_crud, \
             patch("src.extraction.orchestrator.extract", new_callable=AsyncMock) as mock_extract:

            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_crud.get_job.return_value = mock_job
            mock_extract.return_value = mock_result

            result = await async_extraction_wrapper(job_id, file_bytes, None)

        assert result == mock_result
        mock_crud.update_job_status.assert_called_once()
        mock_crud.complete_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_wrapper_handles_extraction_error(self):
        """Test wrapper raises ExtractionError on extraction failure."""
        from src.jobs.tasks import async_extraction_wrapper
        from src.core.exceptions import ExtractionError

        job_id = str(uuid4())
        mock_db = MagicMock()
        mock_job = MagicMock()
        mock_job.file_id = uuid4()

        with patch("src.jobs.tasks.get_db_context") as mock_db_ctx, \
             patch("src.jobs.tasks.crud") as mock_crud, \
             patch("src.extraction.orchestrator.extract", new_callable=AsyncMock) as mock_extract:

            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_crud.get_job.return_value = mock_job
            mock_extract.side_effect = ExtractionError("parsing failed")

            with pytest.raises(ExtractionError):
                await async_extraction_wrapper(job_id, b"bytes", None)

    @pytest.mark.asyncio
    async def test_wrapper_handles_claude_api_error(self):
        """Test wrapper raises ClaudeAPIError."""
        from src.jobs.tasks import async_extraction_wrapper
        from src.core.exceptions import ClaudeAPIError

        job_id = str(uuid4())
        mock_db = MagicMock()
        mock_job = MagicMock()
        mock_job.file_id = uuid4()

        with patch("src.jobs.tasks.get_db_context") as mock_db_ctx, \
             patch("src.jobs.tasks.crud") as mock_crud, \
             patch("src.extraction.orchestrator.extract", new_callable=AsyncMock) as mock_extract:

            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_crud.get_job.return_value = mock_job
            mock_extract.side_effect = ClaudeAPIError("rate limited", stage="parsing")

            with pytest.raises(ClaudeAPIError):
                await async_extraction_wrapper(job_id, b"bytes", None)

    @pytest.mark.asyncio
    async def test_wrapper_handles_lineage_incomplete_error(self):
        """Test wrapper raises LineageIncompleteError as critical."""
        from src.jobs.tasks import async_extraction_wrapper
        from src.core.exceptions import LineageIncompleteError

        job_id = str(uuid4())
        mock_db = MagicMock()
        mock_job = MagicMock()
        mock_job.file_id = uuid4()

        with patch("src.jobs.tasks.get_db_context") as mock_db_ctx, \
             patch("src.jobs.tasks.crud") as mock_crud, \
             patch("src.extraction.orchestrator.extract", new_callable=AsyncMock) as mock_extract:

            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_crud.get_job.return_value = mock_job
            mock_extract.side_effect = LineageIncompleteError(
                missing_events=["stage_3"], job_id=job_id
            )

            with pytest.raises(LineageIncompleteError):
                await async_extraction_wrapper(job_id, b"bytes", None)

    @pytest.mark.asyncio
    async def test_wrapper_handles_unexpected_error(self):
        """Test wrapper raises unexpected exceptions."""
        from src.jobs.tasks import async_extraction_wrapper

        job_id = str(uuid4())
        mock_db = MagicMock()
        mock_job = MagicMock()
        mock_job.file_id = uuid4()

        with patch("src.jobs.tasks.get_db_context") as mock_db_ctx, \
             patch("src.jobs.tasks.crud") as mock_crud, \
             patch("src.extraction.orchestrator.extract", new_callable=AsyncMock) as mock_extract:

            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_crud.get_job.return_value = mock_job
            mock_extract.side_effect = RuntimeError("disk full")

            with pytest.raises(RuntimeError, match="disk full"):
                await async_extraction_wrapper(job_id, b"bytes", None)
