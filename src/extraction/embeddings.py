"""Embedding-based pre-filter for taxonomy mapping.

Computes semantic embeddings for all taxonomy canonical names and aliases,
then scores incoming labels against them. Used in Stage 3 (Mapping) to:
  - Confidently match labels (similarity > 0.92) without calling Claude
  - Provide candidate hints to Claude (similarity 0.80-0.92) for better accuracy
"""

import functools
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.core.logging import extraction_logger as logger
from src.extraction.taxonomy_loader import get_all_taxonomy_items, load_taxonomy_json

# Thresholds for embedding-based matching
CONFIDENT_THRESHOLD = 0.92  # Skip Claude entirely
HINT_THRESHOLD = 0.80  # Pass as candidate hints to Claude

# Model name - small, fast, good for short phrases
_MODEL_NAME = "all-MiniLM-L6-v2"

# Module-level caches
_model = None
_taxonomy_index: Optional[Dict] = None


def _get_model():
    """Lazy-load the sentence-transformer model (once per process)."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading embedding model: {_MODEL_NAME}")
            _model = SentenceTransformer(_MODEL_NAME)
            logger.info("Embedding model loaded")
        except Exception as e:
            logger.warning(f"Failed to load embedding model: {e}")
            raise
    return _model


def _normalize_text(text: str) -> str:
    """Normalize text for embedding: lowercase, collapse whitespace."""
    return " ".join(text.lower().strip().replace("_", " ").replace("-", " ").split())


def _build_taxonomy_index() -> Dict:
    """Build the taxonomy embedding index.

    Returns a dict with:
      - embeddings: np.ndarray of shape (N, dim)
      - labels: list of normalized text strings
      - canonical_names: list of canonical_name for each embedding row
      - categories: list of category for each embedding row
    """
    global _taxonomy_index
    if _taxonomy_index is not None:
        return _taxonomy_index

    model = _get_model()
    data = load_taxonomy_json()

    texts = []
    canonical_names = []
    categories = []

    for category, items in data.get("categories", {}).items():
        for item in items:
            cn = item["canonical_name"]

            # Index the canonical name itself
            texts.append(_normalize_text(cn))
            canonical_names.append(cn)
            categories.append(category)

            # Index the display name
            display = item.get("display_name", "")
            if display:
                texts.append(_normalize_text(display))
                canonical_names.append(cn)
                categories.append(category)

            # Index all aliases
            for alias in item.get("aliases", []):
                if isinstance(alias, dict):
                    alias_text = alias.get("text", "")
                else:
                    alias_text = str(alias)
                if alias_text:
                    texts.append(_normalize_text(alias_text))
                    canonical_names.append(cn)
                    categories.append(category)

    logger.info(f"Computing embeddings for {len(texts)} taxonomy terms")
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

    _taxonomy_index = {
        "embeddings": embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True),
        "labels": texts,
        "canonical_names": canonical_names,
        "categories": categories,
    }
    logger.info(
        f"Taxonomy embedding index built: {len(texts)} vectors, "
        f"dim={embeddings.shape[1]}"
    )
    return _taxonomy_index


def invalidate_taxonomy_index():
    """Clear the cached taxonomy index (e.g., after taxonomy update)."""
    global _taxonomy_index
    _taxonomy_index = None


def score_labels(
    labels: List[str],
    category_filter: Optional[set] = None,
) -> Dict[str, List[Tuple[str, str, float]]]:
    """Score labels against taxonomy embeddings.

    Args:
        labels: List of raw label strings to match.
        category_filter: Optional set of category names to restrict matches to.

    Returns:
        Dict mapping each label to a list of (canonical_name, category, score)
        tuples, sorted by score descending. Only includes matches above
        HINT_THRESHOLD.
    """
    if not labels:
        return {}

    try:
        model = _get_model()
        index = _build_taxonomy_index()
    except Exception as e:
        logger.warning(f"Embedding pre-filter unavailable: {e}")
        return {}

    # Encode input labels
    normalized = [_normalize_text(label) for label in labels]
    label_embeddings = model.encode(normalized, convert_to_numpy=True, show_progress_bar=False)
    label_embeddings = label_embeddings / np.linalg.norm(
        label_embeddings, axis=1, keepdims=True
    )

    # Cosine similarity (dot product of normalized vectors)
    similarities = label_embeddings @ index["embeddings"].T  # (n_labels, n_index)

    results: Dict[str, List[Tuple[str, str, float]]] = {}

    for i, label in enumerate(labels):
        scores = similarities[i]

        # Collect best score per canonical_name (may have multiple alias hits)
        best_per_canonical: Dict[str, Tuple[str, float]] = {}
        for j, score in enumerate(scores):
            if score < HINT_THRESHOLD:
                continue
            cn = index["canonical_names"][j]
            cat = index["categories"][j]
            if category_filter and cat not in category_filter:
                continue
            if cn not in best_per_canonical or score > best_per_canonical[cn][1]:
                best_per_canonical[cn] = (cat, float(score))

        # Sort by score descending
        candidates = [
            (cn, cat, score)
            for cn, (cat, score) in best_per_canonical.items()
        ]
        candidates.sort(key=lambda x: x[2], reverse=True)

        if candidates:
            results[label] = candidates

    return results


def filter_remaining_labels(
    remaining_labels: set,
    category_filter: Optional[set] = None,
) -> Tuple[Dict[str, dict], set, Dict[str, List[Tuple[str, str, float]]]]:
    """Pre-filter labels using embeddings before Claude mapping.

    Args:
        remaining_labels: Set of label strings not yet matched by patterns.
        category_filter: Optional set of category names to restrict matches.

    Returns:
        Tuple of:
          - confident_matches: Dict[label -> mapping dict] for high-confidence matches
          - still_remaining: Set of labels that still need Claude
          - hints: Dict[label -> candidate list] for medium-confidence matches
    """
    if not remaining_labels:
        return {}, set(), {}

    scores = score_labels(list(remaining_labels), category_filter)

    confident_matches: Dict[str, dict] = {}
    hints: Dict[str, List[Tuple[str, str, float]]] = {}
    still_remaining: set = set()

    for label in remaining_labels:
        candidates = scores.get(label, [])

        if candidates and candidates[0][2] >= CONFIDENT_THRESHOLD:
            # High confidence - skip Claude for this label
            best_cn, best_cat, best_score = candidates[0]
            confident_matches[label] = {
                "original_label": label,
                "canonical_name": best_cn,
                "confidence": round(best_score, 4),
                "reasoning": f"Embedding match (score={best_score:.3f})",
                "method": "embedding",
                "taxonomy_category": best_cat,
            }
        elif candidates:
            # Medium confidence - pass as hints to Claude
            hints[label] = candidates[:5]  # Top 5 candidates
            still_remaining.add(label)
        else:
            # No match above threshold
            still_remaining.add(label)

    if confident_matches:
        logger.info(
            f"Embedding pre-filter: {len(confident_matches)} confident matches, "
            f"{len(hints)} with hints, {len(still_remaining) - len(hints)} no match"
        )

    return confident_matches, still_remaining, hints
