"""Tests for the entity learning loop: decay, conflicts, validation feedback, aliases, industry."""

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# ============================================================================
# Confidence Decay Tests
# ============================================================================


class TestConfidenceDecay:
    """Test time-based confidence decay for entity patterns."""

    def test_no_decay_for_recent_pattern(self):
        """Pattern seen today has no decay."""
        from src.db.crud import compute_effective_confidence

        now = datetime.now(timezone.utc)
        result = compute_effective_confidence(0.95, now, "claude")
        assert result == pytest.approx(0.95, abs=0.01)

    def test_decay_after_six_months(self):
        """Pattern seen 6 months ago has ~15% decay."""
        from src.db.crud import compute_effective_confidence

        six_months_ago = datetime.now(timezone.utc) - timedelta(days=182)
        result = compute_effective_confidence(1.0, six_months_ago, "claude")
        # decay_factor = max(0.5, 1.0 - (182/365)*0.3) = max(0.5, 0.8504) = 0.8504
        assert 0.84 < result < 0.86

    def test_decay_after_one_year(self):
        """Pattern seen 1 year ago has 30% decay."""
        from src.db.crud import compute_effective_confidence

        one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)
        result = compute_effective_confidence(1.0, one_year_ago, "claude")
        # decay_factor = max(0.5, 1.0 - 1.0*0.3) = 0.7
        assert result == pytest.approx(0.7, abs=0.01)

    def test_decay_floors_at_50_percent(self):
        """Decay factor never goes below 0.5."""
        from src.db.crud import compute_effective_confidence

        three_years_ago = datetime.now(timezone.utc) - timedelta(days=1095)
        result = compute_effective_confidence(1.0, three_years_ago, "claude")
        # decay_factor = max(0.5, 1.0 - 3.0*0.3) = max(0.5, 0.1) = 0.5
        assert result == pytest.approx(0.5, abs=0.01)

    def test_user_corrections_exempt_from_decay(self):
        """User corrections never decay regardless of age."""
        from src.db.crud import compute_effective_confidence

        two_years_ago = datetime.now(timezone.utc) - timedelta(days=730)
        result = compute_effective_confidence(1.0, two_years_ago, "user_correction")
        assert result == 1.0

    def test_none_last_seen_no_decay(self):
        """If last_seen is None, no decay applied."""
        from src.db.crud import compute_effective_confidence

        result = compute_effective_confidence(0.9, None, "claude")
        assert result == 0.9

    def test_naive_datetime_handled(self):
        """Naive datetime (no timezone) is handled correctly."""
        from src.db.crud import compute_effective_confidence

        six_months_ago = datetime.now() - timedelta(days=182)
        result = compute_effective_confidence(1.0, six_months_ago, "claude")
        assert 0.84 < result < 0.86


# ============================================================================
# Pattern Conflict Resolution Tests
# ============================================================================


class TestPatternConflictResolution:
    """Test conflict resolution when multiple patterns map same label."""

    def test_user_correction_wins_over_claude(self, test_client_with_db, test_db):
        """User corrections always win over Claude-generated patterns."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Conflict Corp")
            entity_id = entity.id

            # Create two patterns for same label
            crud.upsert_entity_pattern(
                session,
                entity_id,
                "Net Sales",
                "other_revenue",
                confidence=0.95,
                created_by="claude",
            )
            # Create a second pattern by manually inserting
            from src.db.models import EntityPattern

            p2 = EntityPattern(
                entity_id=entity_id,
                original_label="Net Sales",
                canonical_name="revenue",
                confidence=1.0,
                created_by="user_correction",
                last_seen=datetime.now(timezone.utc),
            )
            session.add(p2)
            session.commit()

            deactivated = crud.resolve_pattern_conflicts(session, entity_id)
            assert deactivated == 1

            # Verify user_correction is active, claude is not
            all_patterns = crud.get_entity_patterns(session, entity_id, active_only=False)
            for p in all_patterns:
                if p.created_by == "user_correction":
                    assert p.is_active is True
                else:
                    assert p.is_active is False
        finally:
            session.close()

    def test_higher_occurrence_wins(self, test_client_with_db, test_db):
        """Higher occurrence_count wins among auto-generated patterns."""
        from src.db import crud
        from src.db.models import EntityPattern

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Occurrence Corp")
            entity_id = entity.id

            p1 = EntityPattern(
                entity_id=entity_id,
                original_label="COGS",
                canonical_name="cogs",
                confidence=Decimal("0.90"),
                occurrence_count=10,
                created_by="claude",
                last_seen=datetime.now(timezone.utc),
            )
            p2 = EntityPattern(
                entity_id=entity_id,
                original_label="COGS",
                canonical_name="cost_of_revenue",
                confidence=Decimal("0.90"),
                occurrence_count=2,
                created_by="claude",
                last_seen=datetime.now(timezone.utc),
            )
            session.add_all([p1, p2])
            session.commit()

            deactivated = crud.resolve_pattern_conflicts(session, entity_id)
            assert deactivated == 1

            active = crud.get_entity_patterns(session, entity_id, active_only=True)
            assert len(active) == 1
            assert active[0].canonical_name == "cogs"
        finally:
            session.close()

    def test_no_conflicts_no_deactivation(self, test_client_with_db, test_db):
        """If no conflicts exist, nothing is deactivated."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Clean Corp")
            entity_id = entity.id

            crud.upsert_entity_pattern(
                session,
                entity_id,
                "Revenue",
                "revenue",
                confidence=0.95,
                created_by="claude",
            )
            crud.upsert_entity_pattern(
                session,
                entity_id,
                "COGS",
                "cogs",
                confidence=0.90,
                created_by="claude",
            )

            deactivated = crud.resolve_pattern_conflicts(session, entity_id)
            assert deactivated == 0
        finally:
            session.close()


# ============================================================================
# Validation Feedback Loop Tests
# ============================================================================


class TestValidationFeedback:
    """Test pattern confidence adjustment from validation results."""

    def test_failed_validation_reduces_confidence(self, test_client_with_db, test_db):
        """Patterns for failed canonical names get confidence reduced by 0.1."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Feedback Corp")
            entity_id = entity.id

            crud.upsert_entity_pattern(
                session,
                entity_id,
                "Revenue",
                "revenue",
                confidence=0.95,
                created_by="claude",
            )

            result = crud.update_pattern_confidence_from_validation(
                session,
                entity_id,
                failed_canonicals={"revenue"},
                passed_canonicals=set(),
            )
            assert result["reduced"] == 1
            assert result["boosted"] == 0

            patterns = crud.get_entity_patterns(session, entity_id)
            assert float(patterns[0].confidence) == pytest.approx(0.85, abs=0.01)
        finally:
            session.close()

    def test_passed_validation_boosts_confidence(self, test_client_with_db, test_db):
        """Patterns for passed canonical names get confidence boosted by 0.02."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Boost Corp")
            entity_id = entity.id

            crud.upsert_entity_pattern(
                session,
                entity_id,
                "Revenue",
                "revenue",
                confidence=0.90,
                created_by="claude",
            )

            result = crud.update_pattern_confidence_from_validation(
                session,
                entity_id,
                failed_canonicals=set(),
                passed_canonicals={"revenue"},
            )
            assert result["reduced"] == 0
            assert result["boosted"] == 1

            patterns = crud.get_entity_patterns(session, entity_id)
            assert float(patterns[0].confidence) == pytest.approx(0.92, abs=0.01)
        finally:
            session.close()

    def test_user_corrections_unaffected(self, test_client_with_db, test_db):
        """User corrections are exempt from validation feedback."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="User Corp")
            entity_id = entity.id

            crud.upsert_entity_pattern(
                session,
                entity_id,
                "Revenue",
                "revenue",
                confidence=1.0,
                created_by="user_correction",
            )

            result = crud.update_pattern_confidence_from_validation(
                session,
                entity_id,
                failed_canonicals={"revenue"},
                passed_canonicals=set(),
            )
            # user_correction patterns are excluded from adjustment
            assert result["reduced"] == 0

            patterns = crud.get_entity_patterns(session, entity_id)
            assert float(patterns[0].confidence) == 1.0
        finally:
            session.close()

    def test_confidence_floor_at_0_1(self, test_client_with_db, test_db):
        """Confidence can't be reduced below 0.1."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Floor Corp")
            entity_id = entity.id

            crud.upsert_entity_pattern(
                session,
                entity_id,
                "Revenue",
                "revenue",
                confidence=0.15,
                created_by="claude",
            )

            crud.update_pattern_confidence_from_validation(
                session,
                entity_id,
                failed_canonicals={"revenue"},
                passed_canonicals=set(),
            )

            patterns = crud.get_entity_patterns(session, entity_id, min_confidence=0.0)
            assert float(patterns[0].confidence) >= 0.1
        finally:
            session.close()

    def test_confidence_cap_at_1_0(self, test_client_with_db, test_db):
        """Confidence can't be boosted above 1.0."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Cap Corp")
            entity_id = entity.id

            crud.upsert_entity_pattern(
                session,
                entity_id,
                "Revenue",
                "revenue",
                confidence=0.99,
                created_by="claude",
            )

            crud.update_pattern_confidence_from_validation(
                session,
                entity_id,
                failed_canonicals=set(),
                passed_canonicals={"revenue"},
            )

            patterns = crud.get_entity_patterns(session, entity_id)
            assert float(patterns[0].confidence) <= 1.0
        finally:
            session.close()


# ============================================================================
# Learned Alias Tests
# ============================================================================


class TestLearnedAliases:
    """Test learned alias recording, counting, and promotion."""

    def test_record_new_alias(self, test_client_with_db, test_db):
        """Recording a new alias creates it with occurrence_count=1."""
        from src.db import crud

        session = test_db()
        try:
            alias = crud.record_learned_alias(session, "revenue", "Total Net Sales", "entity-1")
            assert alias.canonical_name == "revenue"
            assert alias.alias_text == "Total Net Sales"
            assert alias.occurrence_count == 1
            assert alias.source_entities == ["entity-1"]
            assert alias.promoted is False
        finally:
            session.close()

    def test_record_duplicate_increments_count(self, test_client_with_db, test_db):
        """Recording same alias again increments occurrence_count."""
        from src.db import crud

        session = test_db()
        try:
            crud.record_learned_alias(session, "revenue", "Total Net Sales", "entity-1")
            alias = crud.record_learned_alias(session, "revenue", "Total Net Sales", "entity-2")
            assert alias.occurrence_count == 2
            assert "entity-1" in alias.source_entities
            assert "entity-2" in alias.source_entities
        finally:
            session.close()

    def test_same_entity_not_duplicated_in_sources(self, test_client_with_db, test_db):
        """Same entity_id recorded twice doesn't duplicate in source_entities."""
        from src.db import crud

        session = test_db()
        try:
            crud.record_learned_alias(session, "revenue", "Total Net Sales", "entity-1")
            alias = crud.record_learned_alias(session, "revenue", "Total Net Sales", "entity-1")
            assert alias.occurrence_count == 2
            assert alias.source_entities.count("entity-1") == 1
        finally:
            session.close()

    def test_promote_alias(self, test_client_with_db, test_db):
        """Promoting an alias sets promoted=True."""
        from src.db import crud

        session = test_db()
        try:
            alias = crud.record_learned_alias(session, "revenue", "Net Sales Figure", "entity-1")
            promoted = crud.promote_learned_alias(session, alias.id)
            assert promoted is not None
            assert promoted.promoted is True
        finally:
            session.close()

    def test_get_promotable_aliases(self, test_client_with_db, test_db):
        """Only aliases meeting min_occurrences and not yet promoted are returned."""
        from src.db import crud

        session = test_db()
        try:
            # Create an alias with 3 occurrences
            crud.record_learned_alias(session, "revenue", "Net Sales", "e1")
            crud.record_learned_alias(session, "revenue", "Net Sales", "e2")
            crud.record_learned_alias(session, "revenue", "Net Sales", "e3")

            # Create an alias with only 1 occurrence
            crud.record_learned_alias(session, "cogs", "Material Cost", "e1")

            promotable = crud.get_promotable_aliases(session, min_occurrences=3)
            assert len(promotable) == 1
            assert promotable[0].alias_text == "Net Sales"
        finally:
            session.close()

    def test_get_learned_aliases_filter_by_promoted(self, test_client_with_db, test_db):
        """Can filter learned aliases by promoted status."""
        from src.db import crud

        session = test_db()
        try:
            alias = crud.record_learned_alias(session, "revenue", "Net Sales", "e1")
            crud.promote_learned_alias(session, alias.id)

            crud.record_learned_alias(session, "cogs", "Material Cost", "e1")

            unpromoted = crud.get_learned_aliases(session, promoted=False)
            assert len(unpromoted) == 1
            assert unpromoted[0].alias_text == "Material Cost"

            promoted_list = crud.get_learned_aliases(session, promoted=True)
            assert len(promoted_list) == 1
            assert promoted_list[0].alias_text == "Net Sales"
        finally:
            session.close()


# ============================================================================
# Industry Pattern Tests
# ============================================================================


class TestIndustryPatterns:
    """Test cross-entity industry pattern sharing."""

    def test_get_industry_patterns_excludes_self(self, test_client_with_db, test_db):
        """Industry patterns exclude the requesting entity."""
        from src.db import crud

        session = test_db()
        try:
            e1 = crud.create_entity(session, name="SaaS Co 1", industry="SaaS")
            e2 = crud.create_entity(session, name="SaaS Co 2", industry="SaaS")

            crud.upsert_entity_pattern(
                session, e1.id, "MRR", "mrr", confidence=0.95, created_by="claude"
            )
            crud.upsert_entity_pattern(
                session, e2.id, "ARR", "arr", confidence=0.90, created_by="claude"
            )

            # Request industry patterns for e2 — should only get e1's patterns
            patterns = crud.get_industry_patterns(session, "SaaS", e2.id, min_confidence=0.8)
            assert len(patterns) == 1
            assert patterns[0].original_label == "MRR"
        finally:
            session.close()

    def test_get_industry_patterns_filters_by_confidence(self, test_client_with_db, test_db):
        """Industry patterns respect min_confidence threshold."""
        from src.db import crud

        session = test_db()
        try:
            e1 = crud.create_entity(session, name="Fin Co 1", industry="Finance")
            e2 = crud.create_entity(session, name="Fin Co 2", industry="Finance")

            crud.upsert_entity_pattern(session, e1.id, "Revenue", "revenue", confidence=0.95)
            crud.upsert_entity_pattern(session, e1.id, "Misc Item", "opex", confidence=0.60)

            patterns = crud.get_industry_patterns(session, "Finance", e2.id, min_confidence=0.8)
            assert len(patterns) == 1
            assert patterns[0].canonical_name == "revenue"
        finally:
            session.close()

    def test_different_industry_not_returned(self, test_client_with_db, test_db):
        """Patterns from a different industry are not returned."""
        from src.db import crud

        session = test_db()
        try:
            e1 = crud.create_entity(session, name="SaaS Co", industry="SaaS")
            e2 = crud.create_entity(session, name="Bank Co", industry="Banking")

            crud.upsert_entity_pattern(session, e1.id, "MRR", "mrr", confidence=0.95)

            patterns = crud.get_industry_patterns(session, "Banking", e2.id, min_confidence=0.8)
            assert len(patterns) == 0
        finally:
            session.close()


# ============================================================================
# Pattern Stats API Tests
# ============================================================================


class TestPatternStatsAPI:
    """Test GET /api/v1/entities/{entity_id}/pattern-stats endpoint."""

    def test_pattern_stats_response_structure(self, test_client_with_db, test_db):
        """Pattern stats endpoint returns correct structure."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Stats Corp", industry="Tech")
            entity_id = str(entity.id)

            crud.upsert_entity_pattern(
                session,
                entity.id,
                "Revenue",
                "revenue",
                confidence=0.95,
                created_by="claude",
            )
            crud.upsert_entity_pattern(
                session,
                entity.id,
                "COGS",
                "cogs",
                confidence=0.90,
                created_by="user_correction",
            )
        finally:
            session.close()

        resp = test_client_with_db.get(f"/api/v1/entities/{entity_id}/pattern-stats")
        assert resp.status_code == 200
        data = resp.json()

        assert data["entity_id"] == entity_id
        assert data["total_patterns"] == 2
        assert data["active_patterns"] == 2
        assert data["avg_confidence"] > 0
        assert "claude" in data["by_method"]
        assert "user_correction" in data["by_method"]
        assert data["tokens_saved_estimate"] > 0
        assert data["cost_saved_estimate"] > 0
        assert isinstance(data["top_patterns"], list)
        assert isinstance(data["conflicted_patterns"], list)

    def test_pattern_stats_empty_entity(self, test_client_with_db, test_db):
        """Pattern stats for entity with no patterns returns zeros."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Empty Corp")
            entity_id = str(entity.id)
        finally:
            session.close()

        resp = test_client_with_db.get(f"/api/v1/entities/{entity_id}/pattern-stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_patterns"] == 0
        assert data["active_patterns"] == 0
        assert data["avg_confidence"] == 0.0


# ============================================================================
# Learned Alias API Tests
# ============================================================================


class TestLearnedAliasAPI:
    """Test learned alias API endpoints."""

    def test_list_learned_aliases(self, test_client_with_db, test_db):
        """GET /api/v1/learned-aliases returns aliases."""
        from src.db import crud

        session = test_db()
        try:
            crud.record_learned_alias(session, "revenue", "Net Sales", "e1")
            crud.record_learned_alias(session, "revenue", "Net Sales", "e2")
        finally:
            session.close()

        resp = test_client_with_db.get("/api/v1/learned-aliases")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        alias = data["aliases"][0]
        assert alias["canonical_name"] == "revenue"
        assert alias["alias_text"] == "Net Sales"
        assert alias["occurrence_count"] == 2

    def test_promote_learned_alias_endpoint(self, test_client_with_db, test_db):
        """POST /api/v1/learned-aliases/{id}/promote marks as promoted."""
        from src.db import crud

        session = test_db()
        try:
            alias = crud.record_learned_alias(session, "revenue", "Net Sales", "e1")
            alias_id = str(alias.id)
        finally:
            session.close()

        resp = test_client_with_db.post(f"/api/v1/learned-aliases/{alias_id}/promote")
        assert resp.status_code == 200
        data = resp.json()
        assert data["promoted"] is True

    def test_promote_nonexistent_alias_404(self, test_client_with_db):
        """Promoting a nonexistent alias returns 404."""
        fake_id = str(uuid4())
        resp = test_client_with_db.post(f"/api/v1/learned-aliases/{fake_id}/promote")
        assert resp.status_code == 404


# ============================================================================
# Active-Only Pattern Filtering Tests
# ============================================================================


class TestActiveOnlyFiltering:
    """Test that active_only filtering works in get_entity_patterns."""

    def test_active_only_default(self, test_client_with_db, test_db):
        """Default get_entity_patterns returns only active patterns."""
        from src.db import crud

        session = test_db()
        try:
            entity = crud.create_entity(session, name="Active Corp")

            p1 = crud.upsert_entity_pattern(
                session,
                entity.id,
                "Revenue",
                "revenue",
                confidence=0.95,
                created_by="claude",
            )

            # Manually deactivate
            p1.is_active = False
            session.commit()

            crud.upsert_entity_pattern(
                session,
                entity.id,
                "COGS",
                "cogs",
                confidence=0.90,
                created_by="claude",
            )

            active = crud.get_entity_patterns(session, entity.id)
            assert len(active) == 1
            assert active[0].canonical_name == "cogs"

            all_patterns = crud.get_entity_patterns(session, entity.id, active_only=False)
            assert len(all_patterns) == 2
        finally:
            session.close()


# ============================================================================
# Orchestrator Validation Feedback Integration
# ============================================================================


class TestOrchestratorValidationFeedback:
    """Test _apply_validation_feedback in orchestrator."""

    def test_apply_validation_feedback_reduces_and_boosts(self):
        """Validation feedback correctly reduces failed and boosts passed patterns."""
        from src.extraction.orchestrator import _apply_validation_feedback

        context = MagicMock()
        context.entity_id = "00000000-0000-0000-0000-000000000001"
        context.get_result.side_effect = lambda name: {
            "validation": {
                "validation": {
                    "flags": [
                        {"severity": "error", "item": "revenue", "period": "2025"},
                    ],
                },
            },
            "mapping": {
                "mappings": [
                    {
                        "original_label": "Revenue",
                        "canonical_name": "revenue",
                        "method": "entity_pattern",
                        "confidence": 0.95,
                    },
                    {
                        "original_label": "COGS",
                        "canonical_name": "cogs",
                        "method": "entity_pattern",
                        "confidence": 0.90,
                    },
                ],
            },
        }[name]

        mock_result = {"reduced": 1, "boosted": 1}

        with (
            patch("src.db.session.get_db_sync"),
            patch("src.db.crud.update_pattern_confidence_from_validation") as mock_update,
        ):
            mock_update.return_value = mock_result

            _apply_validation_feedback(context)

            mock_update.assert_called_once()
            call_args = mock_update.call_args
            # Check positional or keyword args
            if call_args.kwargs:
                assert "revenue" in call_args.kwargs.get("failed_canonicals", set())
            else:
                assert "revenue" in call_args[0][2]

    def test_apply_validation_feedback_no_entity_id(self):
        """No feedback applied when entity_id is missing."""
        from src.extraction.orchestrator import _apply_validation_feedback

        context = MagicMock()
        context.entity_id = None

        # Should return without error
        _apply_validation_feedback(context)

    def test_apply_validation_feedback_graceful_on_error(self):
        """Validation feedback errors are logged but don't crash."""
        from src.extraction.orchestrator import _apply_validation_feedback

        context = MagicMock()
        context.entity_id = "00000000-0000-0000-0000-000000000001"
        context.get_result.side_effect = KeyError("validation")

        # Should not raise
        _apply_validation_feedback(context)


# ============================================================================
# Mapping Stage Decay Integration Tests
# ============================================================================


class TestMappingDecayIntegration:
    """Test that mapping stage uses effective confidence for shortcircuiting."""

    def _make_pattern(self, label, canonical, confidence, last_seen, created_by="claude"):
        p = MagicMock()
        p.original_label = label
        p.canonical_name = canonical
        p.confidence = Decimal(str(confidence))
        p.occurrence_count = 5
        p.last_seen = last_seen
        p.created_by = created_by
        p.is_active = True
        return p

    @pytest.mark.asyncio
    async def test_old_pattern_not_shortcircuited(self):
        """Pattern with high stored confidence but old last_seen is not shortcircuited."""
        from src.extraction.stages.mapping import MappingStage

        stage = MappingStage()
        context = MagicMock()
        context.entity_id = "00000000-0000-0000-0000-000000000001"

        two_years_ago = datetime.now(timezone.utc) - timedelta(days=730)
        patterns = [
            self._make_pattern("Revenue", "revenue", 0.98, two_years_ago),
        ]

        with (
            patch("src.db.session.get_db_sync"),
            patch("src.db.crud.get_entity_patterns", return_value=patterns),
            patch("src.db.crud.compute_effective_confidence", return_value=0.49),
        ):
            pre_mapped, remaining = stage._lookup_patterns(context, {"Revenue"})

            assert len(pre_mapped) == 0
            assert "Revenue" in remaining

    @pytest.mark.asyncio
    async def test_recent_pattern_shortcircuited(self):
        """Pattern with high confidence and recent last_seen is shortcircuited."""
        from src.extraction.stages.mapping import MappingStage

        stage = MappingStage()
        context = MagicMock()
        context.entity_id = "00000000-0000-0000-0000-000000000001"

        now = datetime.now(timezone.utc)
        patterns = [
            self._make_pattern("Revenue", "revenue", 0.98, now),
        ]

        with (
            patch("src.db.session.get_db_sync"),
            patch("src.db.crud.get_entity_patterns", return_value=patterns),
            patch("src.db.crud.compute_effective_confidence", return_value=0.98),
        ):
            pre_mapped, remaining = stage._lookup_patterns(context, {"Revenue"})

            assert len(pre_mapped) == 1
            assert "Revenue" in pre_mapped
            assert len(remaining) == 0


# ============================================================================
# Promoted Alias Merge Tests (WS-G)
# ============================================================================


class TestPromotedAliasMerge:
    """Test promoted alias TTL cache and merge into taxonomy lookup."""

    def setup_method(self):
        import src.extraction.taxonomy_loader as tl

        self._tl = tl
        # Reset cache before each test
        tl._promoted_cache = {}
        tl._promoted_cache_time = 0.0

    def test_invalidate_promoted_cache(self):
        """invalidate_promoted_cache clears the cache state."""
        self._tl._promoted_cache = {"some_alias": [("revenue", "income_statement")]}
        self._tl._promoted_cache_time = 9999999.0
        self._tl.invalidate_promoted_cache()
        assert self._tl._promoted_cache == {}
        assert self._tl._promoted_cache_time == 0.0

    def test_cache_ttl_returns_cached(self):
        """Within TTL window, cached data is returned without DB hit."""
        self._tl._promoted_cache = {"test alias": [("revenue", "income_statement")]}
        self._tl._promoted_cache_time = time.time()

        # _load_promoted_aliases should return cache without touching DB
        result = self._tl._load_promoted_aliases()
        assert "test alias" in result

    def test_cache_expired_reloads(self):
        """Expired cache triggers DB reload."""
        self._tl._promoted_cache = {"stale": [("old", "old_cat")]}
        self._tl._promoted_cache_time = time.time() - 600  # expired

        mock_aliases = [
            {"alias_text": "Total Rev", "canonical_name": "revenue"},
        ]

        mock_db = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_db)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        with (
            patch("src.db.session.get_db_sync", return_value=mock_ctx),
            patch("src.db.crud.get_promoted_aliases_for_lookup", return_value=mock_aliases),
        ):
            result = self._tl._load_promoted_aliases()

        assert "total rev" in result
        assert result["total rev"][0][0] == "revenue"

    def test_merge_promoted_with_taxonomy(self):
        """Promoted aliases appear in merged lookup."""
        self._tl._promoted_cache = {"custom label": [("revenue", "income_statement")]}
        self._tl._promoted_cache_time = time.time()

        result = self._tl.get_alias_to_canonicals_with_promoted()
        assert "custom label" in result
        assert ("revenue", "income_statement") in result["custom label"]

    def test_taxonomy_takes_precedence(self):
        """Existing taxonomy alias is not duplicated by promoted alias."""
        # "revenue" is a canonical_name that exists in the base taxonomy
        base = self._tl.get_alias_to_canonicals()

        # Find an existing key to test with
        test_key = None
        for key, entries in base.items():
            if entries:
                test_key = key
                break

        if test_key:
            existing_entry = base[test_key][0]
            # Set promoted cache with same entry
            self._tl._promoted_cache = {test_key: [existing_entry]}
            self._tl._promoted_cache_time = time.time()

            result = self._tl.get_alias_to_canonicals_with_promoted()
            # Should not duplicate
            count = result[test_key].count(existing_entry)
            assert count == 1

    def test_graceful_db_failure_returns_stale(self):
        """On DB error, stale cache is returned."""
        self._tl._promoted_cache = {"stale_alias": [("revenue", "income_statement")]}
        self._tl._promoted_cache_time = 0.0  # expired

        with patch("src.db.session.get_db_sync", side_effect=Exception("DB down")):
            result = self._tl._load_promoted_aliases()

        # Returns stale cache
        assert "stale_alias" in result

    def test_empty_promoted_returns_base(self):
        """No promoted aliases → returns base taxonomy unchanged."""
        self._tl._promoted_cache = {}
        self._tl._promoted_cache_time = time.time()

        result = self._tl.get_alias_to_canonicals_with_promoted()
        base = self._tl.get_alias_to_canonicals()
        assert set(result.keys()) == set(base.keys())
