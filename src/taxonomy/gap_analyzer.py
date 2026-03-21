"""Automated taxonomy gap detection and clustering.

Analyzes UnmappedLabelAggregate records to identify:
- alias_candidate: unmapped labels similar to existing taxonomy items (>0.80)
- new_item_candidate: unmapped labels with no close taxonomy match (<0.60)
- ambiguous: labels in the middle range (0.60-0.80)

Clusters related unmapped labels using embedding similarity.
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy.orm import Session

from src.core.logging import extraction_logger as logger
from src.db.models import UnmappedLabelAggregate
from sqlalchemy import func as sa_func


# Classification thresholds
ALIAS_THRESHOLD = 0.80  # Above this → alias_candidate
AMBIGUOUS_THRESHOLD = 0.60  # Below this → new_item_candidate
CLUSTER_THRESHOLD = 0.75  # Minimum similarity for clustering together


def _get_frequent_unmapped(
    db: Session,
    min_occurrences: int = 2,
    min_entities: int = 2,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Fetch frequently occurring unmapped labels from the database."""
    rows = (
        db.query(
            UnmappedLabelAggregate.label_normalized,
            sa_func.sum(UnmappedLabelAggregate.occurrence_count).label("total_occurrences"),
            sa_func.count(sa_func.distinct(UnmappedLabelAggregate.entity_id)).label("entity_count"),
        )
        .group_by(UnmappedLabelAggregate.label_normalized)
        .having(sa_func.sum(UnmappedLabelAggregate.occurrence_count) >= min_occurrences)
        .having(sa_func.count(sa_func.distinct(UnmappedLabelAggregate.entity_id)) >= min_entities)
        .order_by(sa_func.sum(UnmappedLabelAggregate.occurrence_count).desc())
        .limit(limit)
        .all()
    )

    results = []
    for row in rows:
        detail_rows = (
            db.query(UnmappedLabelAggregate)
            .filter(UnmappedLabelAggregate.label_normalized == row[0])
            .all()
        )
        all_variants = []
        all_sheets = []
        category_hint = None
        for d in detail_rows:
            all_variants.extend(d.original_labels or [])
            all_sheets.extend(d.sheet_names or [])
            if d.taxonomy_category_hint:
                category_hint = d.taxonomy_category_hint

        results.append({
            "label_normalized": row[0],
            "total_occurrences": int(row[1]),
            "entity_count": int(row[2]),
            "variants": list(set(all_variants)),
            "sheet_names": list(set(all_sheets)),
            "category_hint": category_hint,
        })

    return results


def analyze_gaps(
    db: Session,
    min_occurrences: int = 2,
    min_entities: int = 2,
    limit: int = 200,
) -> Dict[str, Any]:
    """Analyze taxonomy gaps by scoring unmapped labels against taxonomy embeddings.

    Returns a dict with:
      - alias_candidates: labels that look like aliases for existing items
      - new_item_candidates: labels that don't match anything in taxonomy
      - ambiguous: labels in the middle range
      - summary: counts and totals
    """
    unmapped = _get_frequent_unmapped(db, min_occurrences, min_entities, limit)

    if not unmapped:
        return {
            "alias_candidates": [],
            "new_item_candidates": [],
            "ambiguous": [],
            "summary": {"total_analyzed": 0, "alias_candidates": 0,
                        "new_item_candidates": 0, "ambiguous": 0},
        }

    # Score against taxonomy embeddings
    try:
        from src.extraction.embeddings import score_labels

        labels = [u["label_normalized"] for u in unmapped]
        scores = score_labels(labels)
    except Exception as e:
        logger.warning(f"Gap analysis embedding scoring failed: {e}")
        scores = {}

    alias_candidates = []
    new_item_candidates = []
    ambiguous = []

    for item in unmapped:
        label = item["label_normalized"]
        candidates = scores.get(label, [])

        if candidates:
            best_cn, best_cat, best_score = candidates[0]
            top_matches = [
                {"canonical_name": cn, "category": cat, "score": round(s, 4)}
                for cn, cat, s in candidates[:3]
            ]
        else:
            best_score = 0.0
            top_matches = []

        entry = {
            "label": label,
            "total_occurrences": item["total_occurrences"],
            "entity_count": item["entity_count"],
            "variants": item["variants"][:5],
            "sheet_names": item["sheet_names"][:3],
            "category_hint": item["category_hint"],
            "best_score": round(best_score, 4),
            "top_matches": top_matches,
        }

        if best_score >= ALIAS_THRESHOLD:
            entry["classification"] = "alias_candidate"
            entry["suggested_canonical"] = top_matches[0]["canonical_name"] if top_matches else None
            alias_candidates.append(entry)
        elif best_score < AMBIGUOUS_THRESHOLD:
            entry["classification"] = "new_item_candidate"
            new_item_candidates.append(entry)
        else:
            entry["classification"] = "ambiguous"
            ambiguous.append(entry)

    return {
        "alias_candidates": alias_candidates,
        "new_item_candidates": new_item_candidates,
        "ambiguous": ambiguous,
        "summary": {
            "total_analyzed": len(unmapped),
            "alias_candidates": len(alias_candidates),
            "new_item_candidates": len(new_item_candidates),
            "ambiguous": len(ambiguous),
        },
    }


def cluster_gaps(
    db: Session,
    min_occurrences: int = 2,
    min_entities: int = 2,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Cluster related unmapped labels by embedding similarity.

    Groups semantically similar unmapped labels together so reviewers
    can address related gaps as a batch.

    Returns a list of clusters, each with:
      - representative: the most frequent label in the cluster
      - labels: list of all labels in the cluster
      - total_occurrences: sum of all occurrences across the cluster
      - suggested_action: "add_alias" or "add_new_item"
    """
    unmapped = _get_frequent_unmapped(db, min_occurrences, min_entities, limit)

    if not unmapped:
        return []

    labels = [u["label_normalized"] for u in unmapped]

    # Compute pairwise similarity using embeddings
    try:
        from src.extraction.embeddings import _get_model, _normalize_text

        model = _get_model()
        normalized = [_normalize_text(label) for label in labels]
        embeddings = model.encode(normalized, convert_to_numpy=True, show_progress_bar=False)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)  # Avoid division by zero
        embeddings = embeddings / norms
        similarity_matrix = embeddings @ embeddings.T
    except Exception as e:
        logger.warning(f"Gap clustering embedding failed: {e}")
        # Fallback: each label is its own cluster
        return [
            {
                "representative": u["label_normalized"],
                "labels": [u["label_normalized"]],
                "total_occurrences": u["total_occurrences"],
                "entity_count": u["entity_count"],
            }
            for u in unmapped[:20]
        ]

    # Simple greedy clustering
    n = len(labels)
    assigned = [False] * n
    clusters = []

    # Sort by occurrence count descending (most frequent becomes representative)
    indices = sorted(range(n), key=lambda i: unmapped[i]["total_occurrences"], reverse=True)

    for i in indices:
        if assigned[i]:
            continue

        cluster_indices = [i]
        assigned[i] = True

        for j in indices:
            if assigned[j]:
                continue
            if similarity_matrix[i][j] >= CLUSTER_THRESHOLD:
                cluster_indices.append(j)
                assigned[j] = True

        cluster_labels = [labels[idx] for idx in cluster_indices]
        total_occ = sum(unmapped[idx]["total_occurrences"] for idx in cluster_indices)
        total_entities = len(set(
            eid
            for idx in cluster_indices
            for eid in range(unmapped[idx]["entity_count"])
        ))

        # Score the representative against taxonomy
        try:
            from src.extraction.embeddings import score_labels as _score

            rep_scores = _score([labels[i]])
            rep_candidates = rep_scores.get(labels[i], [])
            best_score = rep_candidates[0][2] if rep_candidates else 0.0
        except Exception:
            best_score = 0.0

        cluster = {
            "representative": labels[i],
            "labels": cluster_labels,
            "total_occurrences": total_occ,
            "entity_count": total_entities,
            "cluster_size": len(cluster_labels),
            "best_taxonomy_score": round(best_score, 4),
            "suggested_action": "add_alias" if best_score >= ALIAS_THRESHOLD else "add_new_item",
        }

        if best_score >= ALIAS_THRESHOLD and rep_candidates:
            cluster["suggested_canonical"] = rep_candidates[0][0]

        clusters.append(cluster)

    # Sort by total occurrences descending
    clusters.sort(key=lambda c: c["total_occurrences"], reverse=True)

    return clusters
