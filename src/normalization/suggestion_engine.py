"""Taxonomy gap suggestion engine.

Suggests canonical mappings for unmapped labels using fuzzy matching
against existing EntityPatterns, Taxonomy aliases, and LearnedAliases.
Uses difflib.SequenceMatcher from stdlib — no external ML dependencies.
"""

from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from src.db.models import EntityPattern, LearnedAlias, Taxonomy


def suggest_for_label(
    db: Session,
    label_normalized: str,
    *,
    limit: int = 5,
    min_confidence: float = 0.3,
) -> list[dict]:
    """Generate ranked canonical mapping suggestions for an unmapped label.

    Strategy (priority order):
    1. EntityPattern: if any entity has mapped a similar label, suggest that canonical
    2. Taxonomy alias: fuzzy match against Taxonomy.aliases
    3. LearnedAlias: check learned_aliases table for fuzzy matches

    Returns list of {canonical_name, confidence, reason, source} dicts, max `limit`.
    """
    label_lower = label_normalized.lower().strip()
    if not label_lower:
        return []

    seen_canonicals: set[str] = set()
    suggestions: list[dict] = []

    # Strategy 1: EntityPattern fuzzy match
    _add_pattern_suggestions(db, label_lower, suggestions, seen_canonicals)

    # Strategy 2: Taxonomy alias fuzzy match
    _add_alias_suggestions(db, label_lower, suggestions, seen_canonicals)

    # Strategy 3: LearnedAlias fuzzy match
    _add_learned_alias_suggestions(db, label_lower, suggestions, seen_canonicals)

    # Filter by min confidence and sort by confidence descending
    suggestions = [s for s in suggestions if s["confidence"] >= min_confidence]
    suggestions.sort(key=lambda s: s["confidence"], reverse=True)

    return suggestions[:limit]


def _similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two strings using SequenceMatcher."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _add_pattern_suggestions(
    db: Session,
    label_lower: str,
    suggestions: list[dict],
    seen: set[str],
) -> None:
    """Check EntityPattern for labels that fuzzy-match the unmapped label."""
    # Query active patterns — limit to reasonable set
    patterns = (
        db.query(EntityPattern)
        .filter(EntityPattern.is_active.is_(True))
        .limit(500)
        .all()
    )

    for pattern in patterns:
        if pattern.canonical_name in seen:
            continue

        sim = _similarity(label_lower, pattern.original_label)
        if sim >= 0.6:
            confidence = round(sim * float(pattern.confidence) * 0.95, 3)
            seen.add(pattern.canonical_name)
            suggestions.append({
                "canonical_name": pattern.canonical_name,
                "confidence": confidence,
                "reason": f"Similar to entity pattern '{pattern.original_label}' (similarity: {sim:.0%})",
                "source": "entity_pattern",
            })


def _add_alias_suggestions(
    db: Session,
    label_lower: str,
    suggestions: list[dict],
    seen: set[str],
) -> None:
    """Check Taxonomy.aliases for fuzzy matches."""
    items = db.query(Taxonomy).all()

    for item in items:
        if item.canonical_name in seen:
            continue

        # Check against canonical name itself
        sim = _similarity(label_lower, item.canonical_name.replace("_", " "))
        best_sim = sim
        best_match = item.canonical_name.replace("_", " ")

        # Check against aliases
        aliases = item.aliases or []
        if isinstance(aliases, list):
            for alias in aliases:
                if isinstance(alias, str):
                    alias_sim = _similarity(label_lower, alias)
                    if alias_sim > best_sim:
                        best_sim = alias_sim
                        best_match = alias

        if best_sim >= 0.6:
            confidence = round(best_sim * 0.9, 3)
            seen.add(item.canonical_name)
            suggestions.append({
                "canonical_name": item.canonical_name,
                "confidence": confidence,
                "reason": f"Matches taxonomy alias '{best_match}' (similarity: {best_sim:.0%})",
                "source": "taxonomy_alias",
            })


def _add_learned_alias_suggestions(
    db: Session,
    label_lower: str,
    suggestions: list[dict],
    seen: set[str],
) -> None:
    """Check LearnedAlias table for fuzzy matches."""
    aliases = db.query(LearnedAlias).limit(500).all()

    for alias in aliases:
        if alias.canonical_name in seen:
            continue

        sim = _similarity(label_lower, alias.alias_text)
        if sim >= 0.6:
            confidence = round(sim * 0.85, 3)
            seen.add(alias.canonical_name)
            suggestions.append({
                "canonical_name": alias.canonical_name,
                "confidence": confidence,
                "reason": f"Matches learned alias '{alias.alias_text}' (similarity: {sim:.0%})",
                "source": "learned_alias",
            })
