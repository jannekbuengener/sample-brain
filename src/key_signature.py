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


__all__ = ["ParsedKey", "parse_key_signature", "format_key_signature"]
