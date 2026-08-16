"""Harmony Finder core music logic — pure Python, no DB/GUI dependencies."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from .key_signature import (
    ParsedKey,
    parse_key_signature,
    is_same_root,
    is_same_mode,
    key_distance_semitones,
    format_key_signature as fmt_key,
)
from .workbench_controller import WorkbenchRow


class HarmonyRelation(Enum):
    """The musical relation between two keys in the Harmony Finder."""

    DIRECT = "direct"
    RELATED = "related"
    TRANSPOSE = "transpose"
    UNCERTAIN = "uncertain"


@dataclass
class HarmonySuggestion:
    """A harmony suggestion with its relation type, scores, and explanation."""

    row: WorkbenchRow
    relation: HarmonyRelation
    harmony_score: float  # 0.0 to 1.0
    bpm_score: float  # 0.0 to 1.0 (0 when BPM missing/invalid)
    total_score: float  # 0.0 to 1.0
    pitch_shift_semitones: Optional[int] = None
    explanation: str = ""


# ── Key Relation Logic ────────────────────────────────────────────────


def _parse_key_from_row(row: WorkbenchRow) -> Optional[ParsedKey]:
    """Parse a WorkbenchRow's key using the canonical parser."""
    if row.key is None:
        return None
    return parse_key_signature(row.key)


def _check_direct(ref_key: ParsedKey, cand_key: ParsedKey) -> bool:
    """Direct: same root AND both modes known AND matching.

    Same root with one or both modes unknown is NOT direct (cautious, UNCERTAIN).
    """
    if ref_key.mode is None or cand_key.mode is None:
        return False
    return is_same_root(ref_key, cand_key) and is_same_mode(ref_key, cand_key)


def _minimal_semitone_distance(ref_key: ParsedKey, cand_key: ParsedKey) -> int:
    """Smallest absolute root interval in semitones (0..6) ignoring direction."""
    dist = key_distance_semitones(ref_key, cand_key)
    return min(abs(dist), 12 - abs(dist))


def _check_related(ref_key: ParsedKey, cand_key: ParsedKey) -> bool:
    """Related: relative major/minor OR fifth/fourth.

    Both modes must be known. Relative major/minor uses opposite modes a minor
    third apart (3 semitones). Fifth/fourth use the same mode at +7/-5 (fifth)
    or +5/-7 (fourth) semitones.
    """
    if ref_key.mode is None or cand_key.mode is None:
        return False

    dist = key_distance_semitones(ref_key, cand_key)

    # Relative major/minor: opposite modes, roots a minor third apart (mod 12)
    if ref_key.mode != cand_key.mode:
        return _minimal_semitone_distance(ref_key, cand_key) == 3

    # Same mode: perfect fifth (+7 / -5) or perfect fourth (+5 / -7)
    return dist in (7, -5, 5, -7)


def _check_transpose(ref_key: ParsedKey, cand_key: ParsedKey) -> bool:
    """Transpose: within ±3 semitones, no direct/related relationship.

    Both modes must be known (otherwise cautious/uncertain).
    """
    if ref_key.mode is None or cand_key.mode is None:
        return False
    d = _minimal_semitone_distance(ref_key, cand_key)
    return 1 <= d <= 3


def _check_uncertain(
    _ref_key: Optional[ParsedKey], _cand_key: Optional[ParsedKey]
) -> bool:
    """Uncertain: missing keys, unknown modes, or unresolvable."""
    return True  # always uncertain when we reach default


def determine_relation(
    ref_parsed: Optional[ParsedKey],
    cand_parsed: Optional[ParsedKey],
) -> Tuple[HarmonyRelation, str]:
    """Determine the musical relation between two keys.

    Returns (relation, explanation).
    """
    # If either key cannot be parsed, uncertain
    if ref_parsed is None or cand_parsed is None:
        return HarmonyRelation.UNCERTAIN, "Key fehlt – Harmonie nicht sicher bewertbar"

    # Same root + same known mode → DIRECT
    if _check_direct(ref_parsed, cand_parsed):
        return HarmonyRelation.DIRECT, "Direkt passend"

    # Related: relative major/minor OR fifth/fourth with same mode
    if _check_related(ref_parsed, cand_parsed):
        return HarmonyRelation.RELATED, _build_related_explanation(
            ref_parsed, cand_parsed
        )

    # Transpose within ±3 semitones
    if _check_transpose(ref_parsed, cand_parsed):
        return HarmonyRelation.TRANSPOSE, _build_transpose_explanation(
            ref_parsed, cand_parsed
        )

    # Cautious fallback. Same root but unknown mode → explicitly cautious.
    if is_same_root(ref_parsed, cand_parsed):
        return (
            HarmonyRelation.UNCERTAIN,
            "Gleicher Grundton, Modus unbekannt – vorsichtig bewertet",
        )

    # Default: uncertain
    return HarmonyRelation.UNCERTAIN, "Modus unbekannt – vorsichtig bewertet"


def _build_related_explanation(ref_parsed: ParsedKey, cand_parsed: ParsedKey) -> str:
    """Build a human-readable explanation for related keys."""
    ref_name = fmt_key(ref_parsed.root, ref_parsed.mode)
    cand_name = fmt_key(cand_parsed.root, cand_parsed.mode)

    # Relative major/minor (opposite modes)
    if (
        ref_parsed.mode is not None
        and cand_parsed.mode is not None
        and ref_parsed.mode != cand_parsed.mode
    ):
        return f"Relative Tonart: {ref_name} ↔ {cand_name}"

    # Fifth/fourth with same mode
    dist = key_distance_semitones(ref_parsed, cand_parsed)
    if dist in (7, -5):
        return f"Quinte, gleicher Modus: {ref_name} ↔ {cand_name}"
    if dist in (5, -7):
        return f"Quarte, gleicher Modus: {ref_name} ↔ {cand_name}"

    return "Tonart verwandt"


def _build_transpose_explanation(ref_parsed: ParsedKey, cand_parsed: ParsedKey) -> str:
    """Build explanation for transpose relationship (minimal signed shift)."""
    dist = _minimal_signed_shift(ref_parsed, cand_parsed)
    if dist >= 0:
        return f"Mit +{dist} Halbton{'en' if dist > 1 else ''} passend"
    else:
        return f"Mit {dist} Halbton{'n' if dist < -1 else ''} passend"


def _minimal_signed_shift(ref_key: ParsedKey, cand_key: ParsedKey) -> int:
    """Smallest signed root shift (range -6..+6) to align candidate to reference."""
    dist = key_distance_semitones(ref_key, cand_key)
    if dist > 6:
        dist -= 12
    elif dist < -6:
        dist += 12
    return dist


# ── Scoring Logic ─────────────────────────────────────────────────────


def _bpm_score_from_row(
    reference: WorkbenchRow, candidate: WorkbenchRow
) -> Tuple[float, str]:
    """Calculate BPM score using existing matching logic (linear decay)."""
    from .matching import _score_bpm_details

    if reference.bpm is None or candidate.bpm is None:
        return 0.0, "bpm missing"

    from .matching import DEFAULT_BPM_TOLERANCE

    bpm_details = _score_bpm_details(
        candidate.bpm, reference.bpm, DEFAULT_BPM_TOLERANCE
    )
    return bpm_details.score, bpm_details.reason


def _key_score_from_relation(relation: HarmonyRelation) -> float:
    """Return harmony score weight based on relation type."""
    if relation == HarmonyRelation.DIRECT:
        return 1.0
    if relation == HarmonyRelation.RELATED:
        return 0.7
    if relation == HarmonyRelation.TRANSPOSE:
        return 0.5
    return 0.0  # UNCERTAIN


# ── Candidate Rating ───────────────────────────────────────────────────


def rate_harmony(
    reference: WorkbenchRow,
    candidate: WorkbenchRow,
    key_override: Optional[str] = None,
) -> HarmonySuggestion:
    """Rate a single candidate against a reference row.

    Pure function: no side effects, no DB access, pure music logic.
    `key_override` (if given) replaces the reference's key for comparison only
    and never mutates `reference`.
    """
    ref_key = (
        parse_key_signature(key_override)
        if key_override is not None
        else _parse_key_from_row(reference)
    )
    cand_key = _parse_key_from_row(candidate)

    relation, explanation = determine_relation(ref_key, cand_key)

    # BPM score
    bpm_score, bpm_reason = _bpm_score_from_row(reference, candidate)

    # Harmony score from relation
    harmony_score = _key_score_from_relation(relation)

    # Total score: 0.75 harmony + 0.25 BPM
    # Only dimensions with active targets participate in denominator
    total_score = (0.75 * harmony_score + 0.25 * bpm_score) / max(0.75 + 0.25, 1e-10)

    # Pitch shift for transpose candidates
    pitch_shift: Optional[int] = None
    if (
        relation == HarmonyRelation.TRANSPOSE
        and ref_key is not None
        and cand_key is not None
    ):
        pitch_shift = _minimal_signed_shift(ref_key, cand_key)
        # Clamp to ±3 (defensive; transpose band is already within ±3)
        if pitch_shift > 3:
            pitch_shift = 3
        elif pitch_shift < -3:
            pitch_shift = -3

    return HarmonySuggestion(
        row=candidate,
        relation=relation,
        harmony_score=harmony_score,
        bpm_score=bpm_score,
        total_score=total_score,
        pitch_shift_semitones=pitch_shift,
        explanation=explanation,
    )


# ── Service Entry Point ───────────────────────────────────────────────


def find_harmony_matches(
    reference: WorkbenchRow,
    candidates: list[WorkbenchRow],
    *,
    query: str = "",
    key_override: Optional[str] = None,
    limit: Optional[int] = None,
) -> Tuple[list[HarmonySuggestion], Optional[str]]:
    """Find harmony matches for a reference row against a list of candidates.

    Args:
        reference: The reference WorkbenchRow (must have BPM > 0).
        candidates: List of candidate WorkbenchRows (already loaded).
        query: Optional text filter applied to candidate display names.
        key_override: Optional in-memory key override for the reference only.
            Does NOT modify the reference row's key field.
        limit: Maximum number of results to return.

    Returns:
        Tuple of (list of HarmonySuggestion, error message or None).
    """
    # Validate reference has BPM usable for matching
    if reference.bpm is None or reference.bpm <= 0:
        return [], "Ähnliche Samples benötigen ein analysiertes BPM."

    # Apply key override in-memory (not persisted to reference row)
    results: list[HarmonySuggestion] = []

    # Filter candidates via existing workbench text query logic
    # Simple case-insensitive substring match on display_name + path + key + pred_type
    needle = query.strip().casefold()
    if needle:
        filtered_candidates = []
        for cand in candidates:
            display_match = (
                needle in cand.display_name.casefold()
                or needle in str(cand.relative_path).casefold()
                or needle in (cand.key or "").casefold()
                or needle in (cand.pred_type or "").casefold()
            )
            if display_match:
                filtered_candidates.append(cand)
        candidates = filtered_candidates
    # Empty query → all candidates included

    # Exclude reference itself
    candidates = [c for c in candidates if c.path != reference.path]

    if not candidates:
        return [], "Keine weiteren geladenen Samples zum Vergleichen."

    for candidate in candidates:
        suggestion = rate_harmony(reference, candidate, key_override=key_override)
        results.append(suggestion)

    # Sort: primary by relation priority (direct > related > transpose > uncertain),
    # then by total_score descending, then deterministic tie-breakers
    relation_priority = {
        HarmonyRelation.DIRECT: 0,
        HarmonyRelation.RELATED: 1,
        HarmonyRelation.TRANSPOSE: 2,
        HarmonyRelation.UNCERTAIN: 3,
    }

    results.sort(
        key=lambda s: (
            relation_priority.get(s.relation, 99),
            -s.total_score,
            abs(s.pitch_shift_semitones) if s.pitch_shift_semitones is not None else 99,
            s.row.display_name.casefold(),
            s.row.path.casefold(),
        )
    )

    # Apply limit
    if limit is not None:
        results = results[:limit]

    return results, None
