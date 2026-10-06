"""Fail-closed portable projection helpers for analyzer evidence (#960).

Shared seam for AQ8 baseline protection and #956 mapping inventory.
Rejects non-finite numbers and non-JSON-safe runtime objects. Does not coerce
missing analyzer results to numeric zero.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PORTABLE_PROJECTION_DOCUMENT_TYPE = "sample_brain.portable_analyzer_projection"
PORTABLE_PROJECTION_VERSION = "1.0.0"

# Stable surface ids for #956 inventory (docs/benchmarks/ANALYZER_PORTABLE_OUTPUT_BASELINE.md).
ANALYZER_PORTABLE_SURFACE_IDS: tuple[str, ...] = (
    "bpm_beatgrid",
    "key_mode_tonality",
    "onset_gesture",
    "classification_type_tags",
    "search_ranking",
    "harmonic_match",
    "structure_arrangement",
    "loudness_brightness_mfcc_chroma",
)

# Reject every absolute filesystem path / file URI — not a curated prefix allowlist.
_PRIVATE_PATH = re.compile(
    r"(?:^[A-Za-z]:[\\/]|^\\\\|^/|^file://)",
    re.IGNORECASE,
)


class PortableProjectionError(ValueError):
    """Raised when a value cannot enter a portable analyzer evidence artifact."""


def is_finite_number(value: object) -> bool:
    """True for non-bool ints/floats that are finite."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def ensure_portable_number(value: object, *, field: str) -> float | int:
    """Return a JSON-safe finite number or raise."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PortableProjectionError(f"{field}: expected finite number, got {type(value).__name__}")
    if not math.isfinite(value):
        raise PortableProjectionError(f"{field}: non-finite number is not portable")
    return value


def ensure_finite_float_vector(
    values: Sequence[object],
    *,
    field: str,
    expected_len: int | None = None,
) -> list[float]:
    """Decode a portable float vector; reject wrong shapes and non-finite entries."""
    if expected_len is not None and len(values) != expected_len:
        raise PortableProjectionError(
            f"{field}: expected length {expected_len}, got {len(values)}"
        )
    out: list[float] = []
    for index, item in enumerate(values):
        number = ensure_portable_number(item, field=f"{field}[{index}]")
        out.append(float(number))
    return out


def project_portable_value(value: Any, *, field: str = "root") -> Any:
    """Project a nested value into JSON-safe portable form.

    Allowed: None, bool, str, finite int/float, list/tuple, dict with str keys.
    Rejected: NaN/Inf, Path, bytes/bytearray, set, and other runtime objects.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return ensure_portable_number(value, field=field)
    if isinstance(value, Mapping):
        projected: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise PortableProjectionError(f"{field}: mapping keys must be str")
            projected[key] = project_portable_value(child, field=f"{field}.{key}")
        return projected
    if isinstance(value, (list, tuple)):
        return [
            project_portable_value(child, field=f"{field}[{index}]")
            for index, child in enumerate(value)
        ]
    if isinstance(value, (Path, bytes, bytearray, set, frozenset)):
        raise PortableProjectionError(
            f"{field}: {type(value).__name__} is not a portable analyzer evidence type"
        )
    raise PortableProjectionError(
        f"{field}: unsupported runtime type {type(value).__name__}"
    )


def dumps_portable_evidence(payload: Mapping[str, Any]) -> str:
    """Canonical JSON for portable analyzer evidence (sorted, NaN/Inf rejected)."""
    projected = project_portable_value(dict(payload), field="root")
    if not isinstance(projected, dict):
        raise PortableProjectionError("portable evidence root must be an object")
    return json.dumps(
        projected,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def iter_privacy_leak_strings(payload: Any) -> Iterable[str]:
    """Yield string values that look like absolute/private filesystem paths."""
    if isinstance(payload, Mapping):
        for child in payload.values():
            yield from iter_privacy_leak_strings(child)
    elif isinstance(payload, (list, tuple)):
        for child in payload:
            yield from iter_privacy_leak_strings(child)
    elif isinstance(payload, str) and _PRIVATE_PATH.search(payload):
        yield payload


def assert_no_privacy_leaks(payload: Any, *, field: str = "root") -> None:
    """Fail closed when portable evidence embeds absolute/private path strings."""
    leaks = list(iter_privacy_leak_strings(payload))
    if leaks:
        raise PortableProjectionError(
            f"{field}: absolute/private path values are not portable ({leaks[0]!r})"
        )
