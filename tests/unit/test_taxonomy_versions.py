"""
Tests for taxonomy version snapshots, listing, and diff.
"""

from uuid import uuid4

import pytest

from src.db.models import TaxonomyVersion


def _make_snapshot(version: str, items: list[dict]) -> dict:
    """Build a minimal taxonomy.json-shaped dict for testing."""
    return {
        "version": version,
        "description": "test",
        "categories": {
            "income_statement": items,
        },
    }


def _make_version(db_session, version: str, items: list[dict], applied_by: str = "test") -> TaxonomyVersion:
    """Insert a TaxonomyVersion row with a snapshot and return it."""
    snapshot = _make_snapshot(version, items)
    tv = TaxonomyVersion(
        id=uuid4(),
        version=version,
        item_count=len(items),
        checksum="abc123",
        categories={"income_statement": len(items)},
        snapshot=snapshot,
        applied_by=applied_by,
    )
    db_session.add(tv)
    db_session.commit()
    return tv


class TestListTaxonomyVersions:
    def test_returns_empty_list(self, db_session):
        from src.db.crud import list_taxonomy_versions

        result = list_taxonomy_versions(db_session)
        # May have pre-existing versions from other tests; just check it returns a list
        assert isinstance(result, list)

    def test_returns_summary_fields(self, db_session):
        from src.db.crud import list_taxonomy_versions

        tv = _make_version(db_session, "9.9.0", [{"canonical_name": "revenue"}])
        versions = list_taxonomy_versions(db_session, limit=100)

        ids = [v["id"] for v in versions]
        assert str(tv.id) in ids

        our = next(v for v in versions if v["id"] == str(tv.id))
        assert our["version"] == "9.9.0"
        assert our["item_count"] == 1
        assert our["has_snapshot"] is True
        assert "snapshot" not in our  # full snapshot excluded from list

    def test_no_snapshot_has_snapshot_false(self, db_session):
        from src.db.crud import list_taxonomy_versions

        tv = TaxonomyVersion(
            id=uuid4(),
            version="0.0.1",
            item_count=0,
            checksum="xyz",
            categories={},
            snapshot=None,
            applied_by="test",
        )
        db_session.add(tv)
        db_session.commit()

        versions = list_taxonomy_versions(db_session, limit=100)
        our = next((v for v in versions if v["id"] == str(tv.id)), None)
        assert our is not None
        assert our["has_snapshot"] is False


class TestGetTaxonomyVersionSnapshot:
    def test_returns_full_snapshot(self, db_session):
        from src.db.crud import get_taxonomy_version_snapshot

        tv = _make_version(db_session, "8.0.0", [{"canonical_name": "ebitda"}])
        snap = get_taxonomy_version_snapshot(db_session, str(tv.id))

        assert snap["version"] == "8.0.0"
        items = snap["categories"]["income_statement"]
        assert any(i["canonical_name"] == "ebitda" for i in items)

    def test_raises_for_unknown_id(self, db_session):
        from src.db.crud import get_taxonomy_version_snapshot
        from src.core.exceptions import DatabaseError

        with pytest.raises(DatabaseError, match="not found"):
            get_taxonomy_version_snapshot(db_session, str(uuid4()))

    def test_raises_when_no_snapshot_stored(self, db_session):
        from src.db.crud import get_taxonomy_version_snapshot
        from src.core.exceptions import DatabaseError

        tv = TaxonomyVersion(
            id=uuid4(),
            version="0.0.2",
            item_count=0,
            checksum="xyz",
            categories={},
            snapshot=None,
            applied_by="test",
        )
        db_session.add(tv)
        db_session.commit()

        with pytest.raises(DatabaseError, match="no stored snapshot"):
            get_taxonomy_version_snapshot(db_session, str(tv.id))


class TestDiffTaxonomyVersions:
    def test_no_changes(self, db_session):
        from src.db.crud import diff_taxonomy_versions

        items = [{"canonical_name": "revenue", "aliases": ["Sales"], "display_name": "Revenue"}]
        v1 = _make_version(db_session, "1.0.0", items)
        v2 = _make_version(db_session, "1.0.1", items)

        diff = diff_taxonomy_versions(db_session, str(v1.id), str(v2.id))

        assert diff["items_added"] == []
        assert diff["items_removed"] == []
        assert diff["aliases_changed"] == []
        assert diff["summary"]["items_added"] == 0

    def test_item_added(self, db_session):
        from src.db.crud import diff_taxonomy_versions

        v1 = _make_version(db_session, "2.0.0", [{"canonical_name": "revenue", "aliases": []}])
        v2 = _make_version(
            db_session,
            "2.1.0",
            [
                {"canonical_name": "revenue", "aliases": []},
                {"canonical_name": "ebitda", "aliases": []},
            ],
        )

        diff = diff_taxonomy_versions(db_session, str(v1.id), str(v2.id))

        assert "ebitda" in diff["items_added"]
        assert diff["items_removed"] == []
        assert diff["summary"]["items_added"] == 1

    def test_item_removed(self, db_session):
        from src.db.crud import diff_taxonomy_versions

        v1 = _make_version(
            db_session,
            "3.0.0",
            [{"canonical_name": "revenue", "aliases": []}, {"canonical_name": "old_item", "aliases": []}],
        )
        v2 = _make_version(db_session, "3.1.0", [{"canonical_name": "revenue", "aliases": []}])

        diff = diff_taxonomy_versions(db_session, str(v1.id), str(v2.id))

        assert "old_item" in diff["items_removed"]
        assert diff["items_added"] == []

    def test_alias_added(self, db_session):
        from src.db.crud import diff_taxonomy_versions

        v1 = _make_version(
            db_session, "4.0.0", [{"canonical_name": "revenue", "aliases": ["Sales"]}]
        )
        v2 = _make_version(
            db_session, "4.1.0", [{"canonical_name": "revenue", "aliases": ["Sales", "Net Revenue"]}]
        )

        diff = diff_taxonomy_versions(db_session, str(v1.id), str(v2.id))

        assert len(diff["aliases_changed"]) == 1
        change = diff["aliases_changed"][0]
        assert change["canonical_name"] == "revenue"
        assert "Net Revenue" in change["added_aliases"]
        assert change["removed_aliases"] == []

    def test_alias_removed(self, db_session):
        from src.db.crud import diff_taxonomy_versions

        v1 = _make_version(
            db_session, "5.0.0", [{"canonical_name": "revenue", "aliases": ["Sales", "Turnover"]}]
        )
        v2 = _make_version(
            db_session, "5.1.0", [{"canonical_name": "revenue", "aliases": ["Sales"]}]
        )

        diff = diff_taxonomy_versions(db_session, str(v1.id), str(v2.id))

        change = diff["aliases_changed"][0]
        assert "Turnover" in change["removed_aliases"]
        assert change["added_aliases"] == []

    def test_dict_aliases_handled(self, db_session):
        """Dict-format aliases {text: ..., priority: ...} should be handled."""
        from src.db.crud import diff_taxonomy_versions

        v1 = _make_version(
            db_session, "6.0.0", [{"canonical_name": "revenue", "aliases": [{"text": "Sales", "priority": 1}]}]
        )
        v2 = _make_version(
            db_session,
            "6.1.0",
            [
                {
                    "canonical_name": "revenue",
                    "aliases": [{"text": "Sales", "priority": 1}, {"text": "Net Revenue", "priority": 1}],
                }
            ],
        )

        diff = diff_taxonomy_versions(db_session, str(v1.id), str(v2.id))

        assert len(diff["aliases_changed"]) == 1
        assert "Net Revenue" in diff["aliases_changed"][0]["added_aliases"]

    def test_raises_for_missing_snapshot(self, db_session):
        from src.db.crud import diff_taxonomy_versions
        from src.core.exceptions import DatabaseError

        v1 = _make_version(db_session, "7.0.0", [])
        with pytest.raises(DatabaseError):
            diff_taxonomy_versions(db_session, str(v1.id), str(uuid4()))

    def test_version_strings_in_result(self, db_session):
        from src.db.crud import diff_taxonomy_versions

        v1 = _make_version(db_session, "10.0.0", [])
        v2 = _make_version(db_session, "10.1.0", [])

        diff = diff_taxonomy_versions(db_session, str(v1.id), str(v2.id))

        assert diff["from_version"] == "10.0.0"
        assert diff["to_version"] == "10.1.0"
