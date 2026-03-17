"""Tests for Stage 3 entity pattern hints integration."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from src.extraction.base import PipelineContext
from src.extraction.stages.mapping import MappingStage


class TestBuildEntityHints:
    """Test _build_entity_hints on MappingStage."""

    def setup_method(self):
        self.stage = MappingStage()

    def test_no_entity_id_returns_empty(self):
        """No entity_id means no hints."""
        ctx = MagicMock(spec=PipelineContext)
        ctx.entity_id = None
        assert self.stage._build_entity_hints(ctx) == ""

    def test_missing_entity_id_attr_returns_empty(self):
        """Mock without entity_id attribute returns empty."""
        ctx = MagicMock(spec=[])
        assert self.stage._build_entity_hints(ctx) == ""

    def test_entity_with_patterns_returns_hints(self):
        """Should format DB patterns as hint string."""
        ctx = MagicMock(spec=PipelineContext)
        ctx.entity_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        mock_pattern = MagicMock()
        mock_pattern.original_label = "Net Sales"
        mock_pattern.canonical_name = "revenue"
        mock_pattern.confidence = Decimal("0.9500")
        mock_pattern.occurrence_count = 3
        mock_pattern.last_seen = datetime.now(timezone.utc)
        mock_pattern.created_by = "claude"

        with (
            patch("src.db.session.get_db_sync") as mock_db,
            patch("src.db.crud.get_entity_patterns") as mock_get,
        ):
            mock_session = MagicMock()
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)
            mock_get.return_value = [mock_pattern]

            result = self.stage._build_entity_hints(ctx)

        assert "Net Sales" in result
        assert "revenue" in result
        assert "Known patterns" in result

    def test_db_failure_returns_empty(self):
        """DB errors should be caught gracefully."""
        ctx = MagicMock(spec=PipelineContext)
        ctx.entity_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        with patch("src.db.session.get_db_sync", side_effect=Exception("DB down")):
            result = self.stage._build_entity_hints(ctx)

        assert result == ""

    def test_no_patterns_returns_empty(self):
        """Entity with no patterns and no industry returns empty string."""
        ctx = MagicMock(spec=PipelineContext)
        ctx.entity_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        with (
            patch("src.db.session.get_db_sync") as mock_db,
            patch("src.db.crud.get_entity_patterns") as mock_get,
            patch("src.db.crud.get_entity") as mock_get_entity,
        ):
            mock_session = MagicMock()
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)
            mock_get.return_value = []
            mock_get_entity.return_value = MagicMock(industry=None)

            result = self.stage._build_entity_hints(ctx)

        assert result == ""

    def test_multiple_patterns_formatted_correctly(self):
        """Multiple patterns should all appear in hints."""
        ctx = MagicMock(spec=PipelineContext)
        ctx.entity_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        patterns = []
        for label, name, conf in [
            ("Total Revenue", "revenue", "0.95"),
            ("Cost of Goods Sold", "cogs", "0.90"),
            ("Operating Expenses", "opex", "0.85"),
        ]:
            p = MagicMock()
            p.original_label = label
            p.canonical_name = name
            p.confidence = Decimal(conf)
            p.occurrence_count = 2
            p.last_seen = datetime.now(timezone.utc)
            p.created_by = "claude"
            patterns.append(p)

        with (
            patch("src.db.session.get_db_sync") as mock_db,
            patch("src.db.crud.get_entity_patterns") as mock_get,
        ):
            mock_session = MagicMock()
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)
            mock_get.return_value = patterns

            result = self.stage._build_entity_hints(ctx)

        assert "Total Revenue" in result
        assert "Cost of Goods Sold" in result
        assert "Operating Expenses" in result
        assert "revenue" in result
        assert "cogs" in result
        assert "opex" in result
