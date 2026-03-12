"""Cross-extraction diff engine.

Compares two extraction jobs to surface added, removed, and changed
line items, including per-period value deltas.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from uuid import UUID

from sqlalchemy.orm import Session

from src.db import crud
from src.db.models import ExtractionFact
from src.core.logging import lineage_logger as logger


@dataclass
class DiffItem:
    """A single difference between two extractions."""
    canonical_name: str
    change_type: str  # "added", "removed", "mapping_changed", "value_changed", "confidence_changed"
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractionDiff:
    """Full diff between two extraction jobs."""
    job_a_id: str
    job_b_id: str
    added_items: List[DiffItem] = field(default_factory=list)
    removed_items: List[DiffItem] = field(default_factory=list)
    changed_items: List[DiffItem] = field(default_factory=list)
    unchanged_count: int = 0
    value_changes: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "job_a_id": self.job_a_id,
            "job_b_id": self.job_b_id,
            "summary": {
                "added": len(self.added_items),
                "removed": len(self.removed_items),
                "changed": len(self.changed_items),
                "unchanged": self.unchanged_count,
            },
            "added_items": [i.to_dict() for i in self.added_items],
            "removed_items": [i.to_dict() for i in self.removed_items],
            "changed_items": [i.to_dict() for i in self.changed_items],
            "value_changes": self.value_changes,
        }
        if self.warnings:
            d["warnings"] = self.warnings
        if self.metadata:
            d["metadata"] = self.metadata
        return d


class ExtractionDiffer:
    """Compare two extraction jobs to produce a diff."""

    def diff(
        self,
        db: Session,
        job_a_id: str,
        job_b_id: str,
        canonical_name: Optional[str] = None,
        min_change_pct: Optional[float] = None,
    ) -> ExtractionDiff:
        """Compare two extraction jobs.

        Tries fact table first (efficient structured query, no row limit).
        Falls back to JSON result comparison if facts unavailable.
        """
        facts_a = self._load_all_facts(db, UUID(job_a_id))
        facts_b = self._load_all_facts(db, UUID(job_b_id))

        if facts_a or facts_b:
            return self._diff_from_facts(
                job_a_id, job_b_id, facts_a, facts_b,
                canonical_name=canonical_name,
                min_change_pct=min_change_pct,
            )

        return self._diff_from_results(
            db, job_a_id, job_b_id,
            canonical_name=canonical_name,
            min_change_pct=min_change_pct,
        )

    @staticmethod
    def _load_all_facts(db: Session, job_id: UUID) -> List:
        """Load all extraction facts for a job without row limit."""
        return (
            db.query(ExtractionFact)
            .filter(ExtractionFact.job_id == job_id)
            .all()
        )

    def _diff_from_facts(
        self,
        job_a_id: str,
        job_b_id: str,
        facts_a: list,
        facts_b: list,
        canonical_name: Optional[str] = None,
        min_change_pct: Optional[float] = None,
    ) -> ExtractionDiff:
        """Diff using the extraction_facts table."""
        # Build lookup: original_label -> {canonical_name, confidence, values: {period: value}}
        lookup_a = self._facts_to_lookup(facts_a, canonical_name)
        lookup_b = self._facts_to_lookup(facts_b, canonical_name)
        return self._compare_lookups(job_a_id, job_b_id, lookup_a, lookup_b, min_change_pct)

    def _diff_from_results(
        self,
        db: Session,
        job_a_id: str,
        job_b_id: str,
        canonical_name: Optional[str] = None,
        min_change_pct: Optional[float] = None,
    ) -> ExtractionDiff:
        """Diff using job.result JSON fallback."""
        job_a = crud.get_job(db, UUID(job_a_id))
        job_b = crud.get_job(db, UUID(job_b_id))

        items_a = (job_a.result or {}).get("line_items", []) if job_a else []
        items_b = (job_b.result or {}).get("line_items", []) if job_b else []

        lookup_a = self._items_to_lookup(items_a, canonical_name)
        lookup_b = self._items_to_lookup(items_b, canonical_name)
        return self._compare_lookups(job_a_id, job_b_id, lookup_a, lookup_b, min_change_pct)

    @staticmethod
    def _facts_to_lookup(
        facts: list, canonical_name: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Group facts by original_label into a comparison lookup."""
        lookup: Dict[str, Dict[str, Any]] = {}
        for fact in facts:
            if canonical_name and fact.canonical_name != canonical_name:
                continue
            label = fact.original_label or fact.canonical_name
            if label not in lookup:
                lookup[label] = {
                    "canonical_name": fact.canonical_name,
                    "confidence": fact.confidence,
                    "values": {},
                }
            if fact.period and fact.value is not None:
                lookup[label]["values"][fact.period] = float(fact.value)
        return lookup

    @staticmethod
    def _items_to_lookup(
        items: list, canonical_name: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Group line_items by original_label into a comparison lookup."""
        lookup: Dict[str, Dict[str, Any]] = {}
        for item in items:
            cn = item.get("canonical_name", "unmapped")
            if canonical_name and cn != canonical_name:
                continue
            label = item.get("original_label", cn)
            lookup[label] = {
                "canonical_name": cn,
                "confidence": item.get("confidence"),
                "values": {
                    k: float(v) for k, v in (item.get("values") or {}).items()
                    if v is not None
                },
            }
        return lookup

    def _compare_lookups(
        self,
        job_a_id: str,
        job_b_id: str,
        lookup_a: Dict[str, Dict[str, Any]],
        lookup_b: Dict[str, Dict[str, Any]],
        min_change_pct: Optional[float] = None,
    ) -> ExtractionDiff:
        """Core comparison logic between two lookups."""
        diff = ExtractionDiff(job_a_id=job_a_id, job_b_id=job_b_id)

        labels_a = set(lookup_a.keys())
        labels_b = set(lookup_b.keys())

        # Removed items (in A, not in B)
        for label in labels_a - labels_b:
            diff.removed_items.append(DiffItem(
                canonical_name=lookup_a[label]["canonical_name"],
                change_type="removed",
                details={"original_label": label},
            ))

        # Added items (in B, not in A)
        for label in labels_b - labels_a:
            diff.added_items.append(DiffItem(
                canonical_name=lookup_b[label]["canonical_name"],
                change_type="added",
                details={"original_label": label},
            ))

        # Common items — check for changes
        for label in labels_a & labels_b:
            item_a = lookup_a[label]
            item_b = lookup_b[label]
            changed = False

            # Mapping changed
            if item_a["canonical_name"] != item_b["canonical_name"]:
                diff.changed_items.append(DiffItem(
                    canonical_name=item_b["canonical_name"],
                    change_type="mapping_changed",
                    details={
                        "original_label": label,
                        "old_canonical": item_a["canonical_name"],
                        "new_canonical": item_b["canonical_name"],
                    },
                ))
                changed = True

            # Confidence changed
            conf_a = item_a.get("confidence")
            conf_b = item_b.get("confidence")
            if conf_a is not None and conf_b is not None and abs(conf_a - conf_b) > 0.001:
                diff.changed_items.append(DiffItem(
                    canonical_name=item_b["canonical_name"],
                    change_type="confidence_changed",
                    details={
                        "original_label": label,
                        "old_confidence": conf_a,
                        "new_confidence": conf_b,
                    },
                ))
                changed = True

            # Value changes per period
            vals_a = item_a.get("values", {})
            vals_b = item_b.get("values", {})
            all_periods = set(vals_a.keys()) | set(vals_b.keys())

            for period in sorted(all_periods):
                va = vals_a.get(period)
                vb = vals_b.get(period)
                if va is None and vb is None:
                    continue
                if va is None or vb is None or abs(va - vb) > 0.0001:
                    pct = None
                    if va is not None and vb is not None and va != 0:
                        pct = round((vb - va) / abs(va) * 100, 2)

                    if min_change_pct is not None and pct is not None and abs(pct) < min_change_pct:
                        continue

                    diff.value_changes.append({
                        "canonical_name": item_b["canonical_name"],
                        "original_label": label,
                        "period": period,
                        "old_value": va,
                        "new_value": vb,
                        "pct_change": pct,
                    })
                    if not changed:
                        diff.changed_items.append(DiffItem(
                            canonical_name=item_b["canonical_name"],
                            change_type="value_changed",
                            details={"original_label": label},
                        ))
                        changed = True

            if not changed:
                diff.unchanged_count += 1

        logger.info(
            f"Diff {job_a_id[:8]}..{job_b_id[:8]}: "
            f"+{len(diff.added_items)} -{len(diff.removed_items)} "
            f"~{len(diff.changed_items)} ={diff.unchanged_count}"
        )
        return diff
