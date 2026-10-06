"""AQ6 Harmonic Match theory truth table — frozen regression authority (#1015).

Plane: music-theoretic compatibility only. Not ranking, not audio similarity,
not preference. Mirrors current product rules in ``workbench_harmony`` /
``docs/product/02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md`` §9 as executable GT.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .key_signature import (
    ParsedKey,
    format_key_signature,
    is_same_mode,
    is_same_root,
    key_distance_semitones,
    parse_key_signature,
)

TRUTH_TABLE_ID = "sample-brain.aq6.harmonic-theory.truth-table.v1"
DOCUMENT_TYPE = "sample-brain.aq6.harmonic-theory-kpi.v1"
TRUTH_TABLE_VERSION = "1.0.0"
DOMAIN_TOKEN = "aq6.theory"

ROOTS: tuple[str, ...] = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)
MODES: tuple[str, ...] = ("maj", "min")
RELATIONS: tuple[str, ...] = ("direct", "related", "transpose", "uncertain")
COMPATIBILITIES: tuple[str, ...] = ("compatible", "incompatible", "uncertain")

_PITCH_CLASS = {root: idx for idx, root in enumerate(ROOTS)}
_ROOT_BY_PC = {idx: root for idx, root in enumerate(ROOTS)}

FIXTURE_RELPATH = Path("tests/fixtures/aq6_harmonic_theory/truth_table_v1.json")


def _pc(root: str) -> int:
    return _PITCH_CLASS[root]


def rotate_root(root: str, semitones: int) -> str:
    """Sharp-normalized root rotation by ``semitones`` mod 12."""
    return _ROOT_BY_PC[(_pc(root) + semitones) % 12]


def _minimal_semitone_distance(ref: ParsedKey, cand: ParsedKey) -> int:
    dist = key_distance_semitones(ref, cand)
    return min(abs(dist), 12 - abs(dist))


def _minimal_signed_shift(ref: ParsedKey, cand: ParsedKey) -> int:
    dist = key_distance_semitones(ref, cand)
    if dist > 6:
        dist -= 12
    elif dist < -6:
        dist += 12
    return dist


def _check_direct(ref: ParsedKey, cand: ParsedKey) -> bool:
    if ref.mode is None or cand.mode is None:
        return False
    return is_same_root(ref, cand) and is_same_mode(ref, cand)


def _check_related(ref: ParsedKey, cand: ParsedKey) -> bool:
    if ref.mode is None or cand.mode is None:
        return False
    dist = key_distance_semitones(ref, cand)
    if ref.mode != cand.mode:
        return _minimal_semitone_distance(ref, cand) == 3
    return dist in (7, -5, 5, -7)


def _check_transpose(ref: ParsedKey, cand: ParsedKey) -> bool:
    if ref.mode is None or cand.mode is None:
        return False
    d = _minimal_semitone_distance(ref, cand)
    return 1 <= d <= 3


def classify_theory_pair(
    source_key: str | None,
    target_key: str | None,
) -> dict[str, Any]:
    """Classify one ordered source→target pair under the frozen theory rules."""
    source_parsed = parse_key_signature(source_key) if source_key is not None else None
    target_parsed = parse_key_signature(target_key) if target_key is not None else None

    if source_key is not None and source_parsed is None:
        evidence_state = "unparseable"
    elif target_key is not None and target_parsed is None:
        evidence_state = "unparseable"
    elif source_parsed is None or target_parsed is None:
        evidence_state = "missing_key"
    elif source_parsed.mode is None or target_parsed.mode is None:
        evidence_state = "missing_mode"
    else:
        evidence_state = "modeful"

    if evidence_state != "modeful":
        return {
            "source_key": source_key,
            "target_key": target_key,
            "source_root": None if source_parsed is None else source_parsed.root,
            "source_mode": None if source_parsed is None else source_parsed.mode,
            "target_root": None if target_parsed is None else target_parsed.root,
            "target_mode": None if target_parsed is None else target_parsed.mode,
            "relation": "uncertain",
            "compatibility": "uncertain",
            "evidence_state": evidence_state,
            "pitch_shift_semitones": None,
        }

    assert source_parsed is not None and target_parsed is not None
    if _check_direct(source_parsed, target_parsed):
        relation = "direct"
    elif _check_related(source_parsed, target_parsed):
        relation = "related"
    elif _check_transpose(source_parsed, target_parsed):
        relation = "transpose"
    else:
        relation = "uncertain"

    if relation in {"direct", "related", "transpose"}:
        compatibility = "compatible"
    else:
        # Modeful but no allowed relation → known-incompatible (runtime still
        # surfaces relation=uncertain).
        compatibility = "incompatible"

    pitch_shift: int | None = None
    if relation == "transpose":
        pitch_shift = _minimal_signed_shift(source_parsed, target_parsed)
        if pitch_shift > 3:
            pitch_shift = 3
        elif pitch_shift < -3:
            pitch_shift = -3

    return {
        "source_key": format_key_signature(source_parsed.root, source_parsed.mode),
        "target_key": format_key_signature(target_parsed.root, target_parsed.mode),
        "source_root": source_parsed.root,
        "source_mode": source_parsed.mode,
        "target_root": target_parsed.root,
        "target_mode": target_parsed.mode,
        "relation": relation,
        "compatibility": compatibility,
        "evidence_state": evidence_state,
        "pitch_shift_semitones": pitch_shift,
    }


def _modeful_keys() -> list[str]:
    return [
        format_key_signature(root, mode)  # type: ignore[arg-type]
        for root in ROOTS
        for mode in MODES
    ]


def _evidence_edge_cases() -> list[tuple[str | None, str | None, str]]:
    """Required fail-closed evidence cells (source, target, cell_id suffix)."""
    return [
        (None, "Cmaj", "missing_source_key"),
        ("Cmaj", None, "missing_target_key"),
        (None, None, "missing_both_keys"),
        ("C", "Cmaj", "missing_source_mode"),
        ("Cmaj", "G", "missing_target_mode"),
        ("C", "G", "missing_both_modes"),
        ("!!!", "Cmaj", "unparseable_source"),
        ("Cmaj", "not-a-key", "unparseable_target"),
    ]


def build_truth_table_cells() -> list[dict[str, Any]]:
    """Build the exhaustive ordered truth-table cells (deterministic order)."""
    cells: list[dict[str, Any]] = []
    keys = _modeful_keys()
    for source_key in keys:
        for target_key in keys:
            cell = classify_theory_pair(source_key, target_key)
            swap = classify_theory_pair(target_key, source_key)
            cell["cell_id"] = f"modeful:{source_key}->{target_key}"
            cell["relation_symmetric_with_swap"] = cell["relation"] == swap["relation"]
            if cell["relation"] == "transpose" and swap["relation"] == "transpose":
                cell["pitch_shift_antisymmetric_with_swap"] = (
                    cell["pitch_shift_semitones"] == -(swap["pitch_shift_semitones"] or 0)
                )
            else:
                cell["pitch_shift_antisymmetric_with_swap"] = None
            cells.append(cell)

    for source_key, target_key, suffix in _evidence_edge_cases():
        cell = classify_theory_pair(source_key, target_key)
        cell["cell_id"] = f"evidence:{suffix}"
        cell["relation_symmetric_with_swap"] = None
        cell["pitch_shift_antisymmetric_with_swap"] = None
        cells.append(cell)

    return cells


def build_truth_table_document() -> dict[str, Any]:
    cells = build_truth_table_cells()
    counts = {
        "cells_total": len(cells),
        "modeful_pairs": 12 * 2 * 12 * 2,
        "evidence_edge_cases": len(_evidence_edge_cases()),
        "by_relation": {rel: 0 for rel in RELATIONS},
        "by_compatibility": {comp: 0 for comp in COMPATIBILITIES},
    }
    for cell in cells:
        counts["by_relation"][cell["relation"]] += 1
        counts["by_compatibility"][cell["compatibility"]] += 1

    return {
        "document_type": DOCUMENT_TYPE,
        "truth_table_id": TRUTH_TABLE_ID,
        "truth_table_version": TRUTH_TABLE_VERSION,
        "domain": DOMAIN_TOKEN,
        "roots": list(ROOTS),
        "modes": list(MODES),
        "relations": list(RELATIONS),
        "compatibilities": list(COMPATIBILITIES),
        "counts": counts,
        "cells": cells,
    }


def truth_table_json_bytes(document: Mapping[str, Any] | None = None) -> bytes:
    """Canonical UTF-8 JSON bytes (stable separators, trailing newline)."""
    doc = build_truth_table_document() if document is None else document
    payload = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=False)
    return (payload + "\n").encode("utf-8")


def write_truth_table_fixture(path: Path) -> dict[str, Any]:
    """Write the frozen fixture JSON to ``path`` and return the document."""
    document = build_truth_table_document()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(truth_table_json_bytes(document))
    return document


def load_truth_table_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_modeful_cells(document: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    for cell in document["cells"]:
        if cell.get("evidence_state") == "modeful":
            yield cell


def transposition_invariance_violations(
    document: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return golden-table violations of +k root rotation invariance."""
    doc = build_truth_table_document() if document is None else document
    return predicted_transposition_invariance_violations(
        [c for c in doc["cells"] if c.get("evidence_state") == "modeful"],
        {
            c["cell_id"]: {
                "relation": c["relation"],
                "compatibility": c["compatibility"],
                "pitch_shift_semitones": c["pitch_shift_semitones"],
            }
            for c in doc["cells"]
            if c.get("evidence_state") == "modeful"
        },
    )


def predicted_transposition_invariance_violations(
    expected_cells: Sequence[Mapping[str, Any]],
    predicted_by_cell_id: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Return +k rotation invariance violations on *candidate predictions*.

    Compares predicted relation/compatibility/pitch-shift for each modeful
    cell against the prediction for the simultaneously rotated pair. Missing
    predictions are skipped (not counted as violations).
    """
    modeful = [
        c
        for c in expected_cells
        if c.get("evidence_state") == "modeful"
        and c.get("source_root") is not None
        and c.get("target_root") is not None
    ]
    by_keys = {(c["source_key"], c["target_key"]): c for c in modeful}
    violations: list[str] = []
    for cell in modeful:
        pred = predicted_by_cell_id.get(cell["cell_id"])
        if pred is None:
            continue
        src_root = cell["source_root"]
        tgt_root = cell["target_root"]
        src_mode = cell["source_mode"]
        tgt_mode = cell["target_mode"]
        for k in range(12):
            rot_src = format_key_signature(rotate_root(src_root, k), src_mode)
            rot_tgt = format_key_signature(rotate_root(tgt_root, k), tgt_mode)
            rotated_cell = by_keys.get((rot_src, rot_tgt))
            if rotated_cell is None:
                continue
            rotated_pred = predicted_by_cell_id.get(rotated_cell["cell_id"])
            if rotated_pred is None:
                continue
            if (
                rotated_pred.get("relation") != pred.get("relation")
                or rotated_pred.get("compatibility") != pred.get("compatibility")
                or rotated_pred.get("pitch_shift_semitones")
                != pred.get("pitch_shift_semitones")
            ):
                violations.append(
                    f"{cell['cell_id']} +{k} -> {rotated_cell['cell_id']}: "
                    f"{pred.get('relation')}/{pred.get('compatibility')}/"
                    f"{pred.get('pitch_shift_semitones')} != "
                    f"{rotated_pred.get('relation')}/"
                    f"{rotated_pred.get('compatibility')}/"
                    f"{rotated_pred.get('pitch_shift_semitones')}"
                )
                break
    return violations


def score_theory_predictions(
    expected_cells: Sequence[Mapping[str, Any]],
    predicted_by_cell_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Compute theory KPIs for predicted relation/compatibility/shift maps.

    Each prediction mapping should provide ``relation``, ``compatibility``,
    and ``pitch_shift_semitones`` keyed by ``cell_id``.

    ``pitch_shift_suggestion_correctness`` uses the **transpose-only**
    denominator (contract KPI). Non-transpose cells must still predict
    ``null``; failures are counted in ``non_transpose_shift_null_failures``.
    ``transposition_invariance_violations`` is evaluated on the candidate
    predictions, not by regenerating the golden table alone.
    """
    n = 0
    relation_ok = 0
    incompatible = 0
    incompatible_fp = 0
    compatible = 0
    compatible_fn = 0
    transpose = 0
    pitch_ok = 0
    non_transpose = 0
    non_transpose_null_ok = 0
    evidence = 0
    evidence_fail_closed = 0

    for expected in expected_cells:
        cell_id = expected["cell_id"]
        pred = predicted_by_cell_id.get(cell_id)
        if pred is None:
            continue
        n += 1
        if pred.get("relation") == expected["relation"]:
            relation_ok += 1

        if expected["compatibility"] == "incompatible":
            incompatible += 1
            if pred.get("compatibility") == "compatible":
                incompatible_fp += 1
        if expected["compatibility"] == "compatible":
            compatible += 1
            if pred.get("compatibility") != "compatible":
                compatible_fn += 1

        if expected["relation"] == "transpose":
            transpose += 1
            if pred.get("pitch_shift_semitones") == expected["pitch_shift_semitones"]:
                pitch_ok += 1
        else:
            non_transpose += 1
            if pred.get("pitch_shift_semitones") is None:
                non_transpose_null_ok += 1

        if expected["compatibility"] == "uncertain":
            evidence += 1
            if (
                pred.get("relation") == "uncertain"
                and pred.get("compatibility") == "uncertain"
                and pred.get("pitch_shift_semitones") is None
            ):
                evidence_fail_closed += 1

    def _rate(num: int, den: int) -> float | None:
        if den == 0:
            return None
        return num / den

    invariance_violations = predicted_transposition_invariance_violations(
        expected_cells, predicted_by_cell_id
    )

    return {
        "domain": DOMAIN_TOKEN,
        "cells_scored": n,
        "relation_classification_accuracy": _rate(relation_ok, n),
        "incompatible_false_positive_rate": _rate(incompatible_fp, incompatible),
        "compatible_false_negative_rate": _rate(compatible_fn, compatible),
        "pitch_shift_suggestion_correctness": _rate(pitch_ok, transpose),
        "evidence_fail_closed_rate": _rate(evidence_fail_closed, evidence),
        "transposition_invariance_violations": len(invariance_violations),
        "counts": {
            "relation_ok": relation_ok,
            "incompatible": incompatible,
            "incompatible_fp": incompatible_fp,
            "compatible": compatible,
            "compatible_fn": compatible_fn,
            "transpose": transpose,
            "pitch_ok_transpose_only": pitch_ok,
            "non_transpose": non_transpose,
            "non_transpose_null_ok": non_transpose_null_ok,
            "non_transpose_shift_null_failures": non_transpose - non_transpose_null_ok,
            "evidence": evidence,
            "evidence_fail_closed": evidence_fail_closed,
        },
    }


__all__ = [
    "COMPATIBILITIES",
    "DOCUMENT_TYPE",
    "DOMAIN_TOKEN",
    "FIXTURE_RELPATH",
    "MODES",
    "RELATIONS",
    "ROOTS",
    "TRUTH_TABLE_ID",
    "TRUTH_TABLE_VERSION",
    "build_truth_table_cells",
    "build_truth_table_document",
    "classify_theory_pair",
    "iter_modeful_cells",
    "load_truth_table_fixture",
    "predicted_transposition_invariance_violations",
    "rotate_root",
    "score_theory_predictions",
    "transposition_invariance_violations",
    "truth_table_json_bytes",
    "write_truth_table_fixture",
]
