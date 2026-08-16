"""Shared Dur/Moll (major/minor) key-signature parse/format helpers.

Issue #212. A single, small parser used by the analyzer result formatting,
the FL exporter, the search filters, and asset reanalysis so that the three
(old, duplicated and partly incorrect) key-string rules converge on one
canonical representation:

* canonical stored value: ``<ROOT>maj`` | ``<ROOT>min`` | ``<ROOT>`` (root-only)
* accepted legacy inputs: ``C``, ``Am``, ``Amin``, ``A major``, ``C minor``, ``Cm``

This module intentionally owns no analysis logic. Mode decisions live in
``src.analyze.estimate_key_mode``; this module only normalizes the strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_KEY_RE = re.compile(r"^\s*([A-Ga-g])([#b]?)(?:\s*(maj(?:or)?|min(?:or)?|m))?\s*$")

# Flat note names mapped to their sharp equivalents (single pitch class).
_FLAT_TO_SHARP = {
    "CB": "B",
    "DB": "C#",
    "EB": "D#",
    "FB": "E",
    "GB": "F#",
    "AB": "G#",
    "BB": "A#",
}


@dataclass(frozen=True)
class ParsedKey:
    """Parsed key signature.

    ``mode`` is ``"maj"`` | ``"min"`` | ``None`` (root-only, mode unknown).
    """

    root: str
    mode: str | None = None


def parse_key_signature(value: str | None) -> ParsedKey | None:
    """Parse a key string into ``(root, mode)``.

    Returns ``None`` for ``None``, empty, or unparseable input.
    """
    if value is None:
        return None
    normalized = value.strip().casefold()
    if not normalized:
        return None

    match = _KEY_RE.match(normalized)
    if match is None:
        return None

    note = f"{match.group(1).upper()}{match.group(2).upper() or ''}"
    root = _FLAT_TO_SHARP.get(note, note)

    token = match.group(3)
    if token is None:
        mode = None
    elif token.startswith("maj"):
        mode = "maj"
    else:
        mode = "min"

    return ParsedKey(root=root, mode=mode)


def format_key_signature(root: str | None, mode: str | None) -> str | None:
    """Canonical string for a parsed key.

    ``<ROOT>maj`` / ``<ROOT>min`` when mode is known, otherwise ``<ROOT>``.
    Returns ``None`` when root is missing.
    """
    if root is None:
        return None
    if mode == "maj":
        return f"{root}maj"
    if mode == "min":
        return f"{root}min"
    return root


# Chromatic pitch classes for semitone distance (C=0, circular).
_PITCH_CLASS = {
    "C": 0,
    "C#": 1,
    "D": 2,
    "D#": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "G": 7,
    "G#": 8,
    "A": 9,
    "A#": 10,
    "B": 11,
}


def _pitch_class(root: str | None) -> int | None:
    """Return the chromatic pitch class index for a normalized root, or None."""
    if root is None:
        return None
    return _PITCH_CLASS.get(root)


def is_same_root(a: ParsedKey | None, b: ParsedKey | None) -> bool:
    """True when both parsed keys share the same (enharmonic) root."""
    if a is None or b is None:
        return False
    return _pitch_class(a.root) == _pitch_class(b.root)


def is_same_mode(a: ParsedKey | None, b: ParsedKey | None) -> bool:
    """True when both parsed keys share the same mode (including both unknown)."""
    if a is None or b is None:
        return False
    return a.mode == b.mode


def key_distance_semitones(a: ParsedKey | None, b: ParsedKey | None) -> int:
    """Signed chromatic distance from key *a* to key *b* (mod 12, C=0).

    Returns 0 when either key is missing or unparseable.
    """
    pa = _pitch_class(a.root if a is not None else None)
    pb = _pitch_class(b.root if b is not None else None)
    if pa is None or pb is None:
        return 0
    return (pb - pa) % 12


__all__ = [
    "ParsedKey",
    "parse_key_signature",
    "format_key_signature",
    "is_same_root",
    "is_same_mode",
    "key_distance_semitones",
]
