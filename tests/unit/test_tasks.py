"""
Tests for Celery task execution flow.
Tests async_extraction_wrapper directly (run_extraction_task is Celery-decorated
and cannot be tested directly due to module-level Celery mock in conftest).
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _mock_s3_client(file_bytes=b"fake-bytes"):
    """Create a mock S3 client that returns the given file bytes on download."""
    mock = MagicMock()
    mock.download_file.return_value = file_bytes
    return mock


class TestAsyncExtractionWrapper:
    """Test the async extraction wrapper (not Celery-decorated)."""

    @pytest.mark.asyncio
    async def test_wrapper_runs_extraction_and_completes_job(self):
        """Test wrapper updates job status through full lifecycle."""
        from src.jobs.tasks import async_extraction_wrapper

        job_id = str(uuid4())
        s3_key = "uploads/2024/01/fake-file.xlsx"

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

        with (
            patch("src.jobs.tasks.get_db_context") as mock_db_ctx,
            patch("src.jobs.tasks.crud") as mock_crud,
            patch("src.extraction.orchestrator.extract", new_callable=AsyncMock) as mock_extract,
            patch("src.storage.s3.get_s3_client", return_value=_mock_s3_client()),
        ):
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_crud.get_job.return_value = mock_job
            mock_extract.return_value = mock_result

            result = await async_extraction_wrapper(job_id, s3_key, None)

        assert result == mock_result
        mock_crud.update_job_status.assert_called()
        mock_crud.complete_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_wrapper_handles_extraction_error(self):
        """Test wrapper raises ExtractionError on extraction failure."""
        from src.core.exceptions import ExtractionError
        from src.jobs.tasks import async_extraction_wrapper

        job_id = str(uuid4())
        mock_db = MagicMock()
        mock_job = MagicMock()
        mock_job.file_id = uuid4()

        with (
            patch("src.jobs.tasks.get_db_context") as mock_db_ctx,
            patch("src.jobs.tasks.crud") as mock_crud,
            patch("src.extraction.orchestrator.extract", new_callable=AsyncMock) as mock_extract,
            patch("src.storage.s3.get_s3_client", return_value=_mock_s3_client()),
        ):
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_crud.get_job.return_value = mock_job
            mock_extract.side_effect = ExtractionError("parsing failed")

            with pytest.raises(ExtractionError):
                await async_extraction_wrapper(job_id, "uploads/test.xlsx", None)

    @pytest.mark.asyncio
    async def test_wrapper_handles_claude_api_error(self):
        """Test wrapper raises ClaudeAPIError."""
        from src.core.exceptions import ClaudeAPIError
        from src.jobs.tasks import async_extraction_wrapper

        job_id = str(uuid4())
        mock_db = MagicMock()
        mock_job = MagicMock()
        mock_job.file_id = uuid4()

        with (
            patch("src.jobs.tasks.get_db_context") as mock_db_ctx,
            patch("src.jobs.tasks.crud") as mock_crud,
            patch("src.extraction.orchestrator.extract", new_callable=AsyncMock) as mock_extract,
            patch("src.storage.s3.get_s3_client", return_value=_mock_s3_client()),
        ):
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_crud.get_job.return_value = mock_job
            mock_extract.side_effect = ClaudeAPIError("rate limited", stage="parsing")

            with pytest.raises(ClaudeAPIError):
                await async_extraction_wrapper(job_id, "uploads/test.xlsx", None)

    @pytest.mark.asyncio
    async def test_wrapper_handles_lineage_incomplete_error(self):
        """Test wrapper raises LineageIncompleteError as critical."""
        from src.core.exceptions import LineageIncompleteError
        from src.jobs.tasks import async_extraction_wrapper

        job_id = str(uuid4())
        mock_db = MagicMock()
        mock_job = MagicMock()
        mock_job.file_id = uuid4()

        with (
            patch("src.jobs.tasks.get_db_context") as mock_db_ctx,
            patch("src.jobs.tasks.crud") as mock_crud,
            patch("src.extraction.orchestrator.extract", new_callable=AsyncMock) as mock_extract,
            patch("src.storage.s3.get_s3_client", return_value=_mock_s3_client()),
        ):
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_crud.get_job.return_value = mock_job
            mock_extract.side_effect = LineageIncompleteError(
                missing_events=["stage_3"], job_id=job_id
            )

            with pytest.raises(LineageIncompleteError):
                await async_extraction_wrapper(job_id, "uploads/test.xlsx", None)

    @pytest.mark.asyncio
    async def test_wrapper_handles_unexpected_error(self):
        """Test wrapper raises unexpected exceptions."""
        from src.jobs.tasks import async_extraction_wrapper

        job_id = str(uuid4())
        mock_db = MagicMock()
        mock_job = MagicMock()
        mock_job.file_id = uuid4()

        with (
            patch("src.jobs.tasks.get_db_context") as mock_db_ctx,
            patch("src.jobs.tasks.crud") as mock_crud,
            patch("src.extraction.orchestrator.extract", new_callable=AsyncMock) as mock_extract,
            patch("src.storage.s3.get_s3_client", return_value=_mock_s3_client()),
        ):
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_crud.get_job.return_value = mock_job
            mock_extract.side_effect = RuntimeError("disk full")

            with pytest.raises(RuntimeError, match="disk full"):
                await async_extraction_wrapper(job_id, "uploads/test.xlsx", None)

    @pytest.mark.asyncio
    async def test_wrapper_downloads_from_s3(self):
        """Test that the wrapper downloads file bytes from S3 using the key."""
        from src.jobs.tasks import async_extraction_wrapper

        job_id = str(uuid4())
        s3_key = "uploads/2024/01/test-file.xlsx"

        mock_db = MagicMock()
        mock_job = MagicMock()
        mock_job.file_id = uuid4()

        mock_s3 = _mock_s3_client(b"s3-file-content")

        mock_result = {
            "file_id": str(mock_job.file_id),
            "sheets": [],
            "line_items": [],
            "tokens_used": 50,
            "cost_usd": 0.001,
        }

        with (
            patch("src.jobs.tasks.get_db_context") as mock_db_ctx,
            patch("src.jobs.tasks.crud") as mock_crud,
            patch("src.extraction.orchestrator.extract", new_callable=AsyncMock) as mock_extract,
            patch("src.storage.s3.get_s3_client", return_value=mock_s3),
        ):
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_crud.get_job.return_value = mock_job
            mock_extract.return_value = mock_result

            await async_extraction_wrapper(job_id, s3_key, None)

        # Verify S3 download was called with the correct key
        mock_s3.download_file.assert_called_once_with(s3_key)

    @pytest.mark.asyncio
    async def test_wrapper_passes_progress_callback_to_extract(self):
        """Test that wrapper creates and passes a progress callback to extract()."""
        from src.jobs.tasks import async_extraction_wrapper

        job_id = str(uuid4())
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

        with (
            patch("src.jobs.tasks.get_db_context") as mock_db_ctx,
            patch("src.jobs.tasks.crud") as mock_crud,
            patch("src.extraction.orchestrator.extract", new_callable=AsyncMock) as mock_extract,
            patch("src.storage.s3.get_s3_client", return_value=_mock_s3_client()),
        ):
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            mock_crud.get_job.return_value = mock_job
            mock_extract.return_value = mock_result

            await async_extraction_wrapper(job_id, "uploads/test.xlsx", None)

            # Verify extract was called with a progress_callback kwarg
            mock_extract.assert_called_once()
            call_kwargs = mock_extract.call_args
            assert "progress_callback" in call_kwargs.kwargs
            assert callable(call_kwargs.kwargs["progress_callback"])


class TestAutoretryConfiguration:
    """Test that autoretry_for is narrowed to transient exceptions only."""

    def test_autoretry_excludes_code_bugs(self):
        """Verify autoretry_for does NOT include generic Exception or code bugs."""
        from src.core.exceptions import ClaudeAPIError, RateLimitError
        from src.jobs.tasks import _TRANSIENT_EXCEPTIONS

        # Should include transient errors
        assert ClaudeAPIError in _TRANSIENT_EXCEPTIONS
        assert RateLimitError in _TRANSIENT_EXCEPTIONS
        assert ConnectionError in _TRANSIENT_EXCEPTIONS
        assert TimeoutError in _TRANSIENT_EXCEPTIONS

        # Should NOT include generic Exception or code bugs
        assert Exception not in _TRANSIENT_EXCEPTIONS
        assert KeyError not in _TRANSIENT_EXCEPTIONS
        assert TypeError not in _TRANSIENT_EXCEPTIONS
        assert ValueError not in _TRANSIENT_EXCEPTIONS
        assert AttributeError not in _TRANSIENT_EXCEPTIONS
