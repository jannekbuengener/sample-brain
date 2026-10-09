"""AQ7 ArrangementClassifier role/drop baseline harness (#1026).

Measures current ArrangementClassifier roles and drop events on frozen #1024
reference sections/boundaries. The module is consume-only: no analyzer tuning,
no production defaults, no committed runtime artifacts.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import soundfile as sf

from .analysis_eval_artifact import (
    AnalysisEvalArtifactError,
    assert_portable_value,
)
from .aq7_structure_boundary_baseline import match_boundaries_1bar
from .aq7_structure_role_drop_corpus import (
    CORPUS_ID,
    CORPUS_VERSION,
    GENERATOR_SEED,
    assert_work_dir_outside_repo,
    generate_aq7_structure_role_drop_corpus,
)
from .aq7_structure_role_drop_schema import (
    BOUNDARY_MATCH_TOLERANCE_BARS,
    ROLE_VOCABULARY,
    load_aq7_corpus_manifest,
    load_aq7_fixture_gt,
)
from .arrangement_classifier import ArrangementClassifier
from .beat_grid import BeatGridResult, BeatGridSeries, BeatGridSource
from .canon_audio import AudioTimebase
from .measurement.stats import percentile
from .section_signals import SectionSignalsAssembler
from .structure_v1 import (
    StructureBoundary,
    StructureSection,
    StructureV1Analyzer,
    StructureV1Config,
    StructureV1Result,
    StructureV1Source,
)

DOCUMENT_TYPE = "sample-brain.aq7.structure-role-drop-baseline.v1"
SCHEMA_VERSION = "1.0.0"
CANDIDATE_ID = "arrangement_classifier.baseline.v1"
BOUNDARY_CONTEXT_CANDIDATE_ID = "structure_v1.baseline.v1"
BOUNDARY_CONTEXT_DOCUMENT_TYPE = "sample-brain.aq7.structure-boundary-baseline.v1"
ROLE_PLANE_TOKEN = "aq7.role"
DROP_PLANE_TOKEN = "aq7.drop_event"
ARRANGEMENT_SURFACE = (
    "src.arrangement_classifier.ArrangementClassifier.classify_track"
)
SECTION_SIGNAL_SURFACE = "src.section_signals.SectionSignalsAssembler"
STRUCTURE_SURFACE = "src.structure_v1.StructureV1Analyzer.analyze_path"
FEATURE_TOGGLE = "N/A"
PRODUCTION_DEFAULTS_CHANGED = False
PROTECTED_ANALYZER_FILES = (
    "src/arrangement_classifier.py",
    "src/section_signals.py",
    "src/structure_v1.py",
)
PROTECTED_ANALYZER_FILES_CHANGED = False
CONCRETE_ROLE_VOCABULARY = (
    "intro",
    "groove",
    "build",
    "drop",
    "breakdown",
    "outro",
)
EXIT_MEASURED = "AQ7_ROLE_DROP_BASELINE_MEASURED"
EXIT_PARTIAL_HOLD = "AQ7_ROLE_DROP_BASELINE_PARTIAL_HOLD"
EXIT_INCOMPLETE = "AQ7_ROLE_DROP_BASELINE_INCOMPLETE"

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]
_ELIGIBLE_ANNOTATION = frozenset({"adjudicated", "single_source"})
_CORE_SIGNAL_KEYS = (
    "bar_energy_rms",
    "bar_loudness_delta",
    "low_end_share",
    "onset_density",
    "rhythm_stability",
    "timbre_delta",
    "spectral_delta",
    "self_similarity",
    "recurrence",
    "novelty",
    "neighbor_delta",
    "multi_bar_trend",
)
PARTITION_POLICY = {
    "CALIBRATION": "DEVELOPMENT/CALIBRATION",
    "TEST": "TEST/HOLDOUT",
}


def assert_portable_baseline_payload(payload: Any) -> None:
    try:
        assert_portable_value(payload, field="aq7.role_drop_baseline")
    except AnalysisEvalArtifactError as exc:
        raise ValueError(str(exc)) from exc


def _safe_div(num: int | float, den: int | float) -> float | None:
    if den <= 0:
        return None
    return float(num) / float(den)


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    if precision + recall <= 0:
        return 0.0
    return 2.0 * precision * recall / (precision + recall)


def reference_boundaries_from_gt(gt: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for order, raw in enumerate(gt.get("boundaries") or []):
        if not isinstance(raw, Mapping):
            continue
        refs.append(
            {
                "boundary_id": str(raw["boundary_id"]),
                "bar_index": int(raw["bar_index"]),
                "order": order,
                "annotation_status": str(
                    raw.get("annotation_status") or "single_source"
                ),
                "time_sec": raw.get("time_sec"),
            }
        )
    refs.sort(key=lambda r: (int(r["bar_index"]), int(r["order"])))
    for index, item in enumerate(refs):
        item["order"] = index
    return refs


def frozen_reference_sections_from_gt(gt: Mapping[str, Any]) -> list[dict[str, Any]]:
    ambiguous_bars = {
        int(item["bar_index"])
        for item in gt.get("boundaries", [])
        if isinstance(item, Mapping)
        and str(item.get("annotation_status")) == "ambiguous"
    }
    refs: list[dict[str, Any]] = []
    for order, raw in enumerate(gt.get("sections") or []):
        if not isinstance(raw, Mapping):
            continue
        start_bar = int(raw["start_bar"])
        end_bar = int(raw["end_bar"])
        refs.append(
            {
                "section_id": str(raw["section_id"]),
                "start_bar": start_bar,
                "end_bar": end_bar,
                "role": str(raw["role"]),
                "annotation_status": str(
                    raw.get("annotation_status") or "single_source"
                ),
                "excluded_by_ambiguous_boundary": (
                    start_bar in ambiguous_bars or end_bar in ambiguous_bars
                ),
                "order": order,
            }
        )
    refs.sort(key=lambda s: (int(s["start_bar"]), int(s["end_bar"]), s["section_id"]))
    return refs


def track_end_bar_from_gt(gt: Mapping[str, Any]) -> int:
    sections = frozen_reference_sections_from_gt(gt)
    if sections:
        return max(int(s["end_bar"]) for s in sections)
    boundaries = reference_boundaries_from_gt(gt)
    return max((int(b["bar_index"]) for b in boundaries), default=0)


def build_frozen_geometry_classifier_input(
    gt: Mapping[str, Any],
    *,
    bar_features: list[dict[str, Any]] | Mapping[str, Any] | None = None,
    feature_status: str = "ok",
) -> dict[str, Any]:
    """Expose benchmark geometry and analyzer features without role/drop labels."""
    feature_inputs = {
        "bar_features": bar_features or [],
        "feature_status": feature_status,
    }
    return {
        "sections": frozen_reference_sections_from_gt(gt),
        "boundaries": reference_boundaries_from_gt(gt),
        "feature_inputs": feature_inputs,
        "manual_overrides": None,
        "gt_labels_visible_to_prediction_path": False,
    }


def _prediction_role(raw: Mapping[str, Any]) -> str:
    automatic = raw.get("automatic_result") or {}
    if isinstance(automatic, Mapping) and automatic.get("role") is not None:
        return str(automatic["role"])
    if raw.get("role") is not None:
        return str(raw["role"])
    return "unknown"


def _empty_role_metrics(
    *,
    prediction_usable: bool,
    prediction_status: str,
    eligible_concrete_count: int,
) -> dict[str, Any]:
    return {
        "plane": ROLE_PLANE_TOKEN,
        "prediction_usable": prediction_usable,
        "prediction_status": prediction_status,
        "evidence_status": "unknown" if not prediction_usable else "measured",
        "support": eligible_concrete_count,
        "coverage": 0.0 if eligible_concrete_count else None,
        "abstention_rate": 1.0 if not prediction_usable and eligible_concrete_count else 0.0,
        "unknown_rate": None,
        "unknown_reference_recall": None,
        "bar_weighted_accuracy": None,
        "bar_weighted_accuracy_kind": "diagnostic",
        "macro_f1": None,
        "per_role": {role: _blank_prf() for role in CONCRETE_ROLE_VOCABULARY},
        "confusion_matrix": {},
        "excluded_section_count": 0,
        "role_items": [],
    }


def _blank_prf() -> dict[str, Any]:
    return {
        "precision": None,
        "recall": None,
        "f1": None,
        "support": 0,
        "predicted": 0,
    }


def score_roles(
    reference_sections: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    *,
    prediction_usable: bool = True,
    prediction_status: str = "ok",
    manual_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    del manual_overrides  # manual/effective values are intentionally ignored.
    eligible = [
        s
        for s in reference_sections
        if str(s.get("annotation_status")) in _ELIGIBLE_ANNOTATION
        and not bool(s.get("excluded_by_ambiguous_boundary"))
    ]
    excluded_count = len(reference_sections) - len(eligible)
    eligible_concrete_count = sum(
        1 for s in eligible if str(s.get("role")) in CONCRETE_ROLE_VOCABULARY
    )
    if not prediction_usable:
        out = _empty_role_metrics(
            prediction_usable=False,
            prediction_status=prediction_status,
            eligible_concrete_count=eligible_concrete_count,
        )
        out["excluded_section_count"] = excluded_count
        return out

    all_section_ids = {str(s["section_id"]) for s in reference_sections}
    by_section = {str(s["section_id"]): s for s in eligible}
    pred_map: dict[str, str] = {}
    for raw in predictions:
        section_id = str(raw.get("section_id"))
        if section_id not in by_section:
            if section_id in all_section_ids:
                continue
            raise ValueError(f"unknown section in role prediction: {section_id}")
        pred_map[section_id] = _prediction_role(raw)

    roles = sorted(set(ROLE_VOCABULARY) | set(pred_map.values()))
    confusion: dict[str, dict[str, int]] = {role: {} for role in roles}
    role_items: list[dict[str, Any]] = []
    correct_bars = 0
    total_bars = 0
    explicit_pred_count = 0
    explicit_unknown_count = 0
    unknown_ref_count = 0
    unknown_ref_hit = 0
    coverage_n = 0
    coverage_d = 0

    for section in eligible:
        ref_role = str(section["role"])
        pred_role = pred_map.get(str(section["section_id"]))
        length = int(section["end_bar"]) - int(section["start_bar"])
        if ref_role in CONCRETE_ROLE_VOCABULARY:
            coverage_d += 1
            total_bars += max(0, length)
        if ref_role == "unknown":
            unknown_ref_count += 1
        item = {
            "section_id": section["section_id"],
            "ref_role": ref_role,
            "pred_role": pred_role,
            "start_bar": section["start_bar"],
            "end_bar": section["end_bar"],
            "status": "scored" if pred_role is not None else "uncovered",
        }
        role_items.append(item)
        if pred_role is None:
            continue
        explicit_pred_count += 1
        if pred_role == "unknown":
            explicit_unknown_count += 1
        if ref_role == "unknown" and pred_role == "unknown":
            unknown_ref_hit += 1
        if ref_role in CONCRETE_ROLE_VOCABULARY and pred_role != "unknown":
            coverage_n += 1
        if ref_role in CONCRETE_ROLE_VOCABULARY and pred_role == ref_role:
            correct_bars += max(0, length)
        confusion.setdefault(ref_role, {})
        confusion[ref_role][pred_role] = confusion[ref_role].get(pred_role, 0) + 1

    per_role: dict[str, dict[str, Any]] = {}
    macro_values: list[float] = []
    for role in CONCRETE_ROLE_VOCABULARY:
        support = sum(sum(row.values()) for ref, row in confusion.items() if ref == role)
        predicted = sum(row.get(role, 0) for row in confusion.values())
        true_pos = confusion.get(role, {}).get(role, 0)
        precision = _safe_div(true_pos, predicted)
        recall = _safe_div(true_pos, support)
        f1 = _f1(precision, recall)
        if support > 0 and predicted == 0:
            f1 = 0.0
        if support == 0 and predicted > 0:
            f1 = 0.0
        if support > 0 or predicted > 0:
            macro_values.append(float(f1 or 0.0))
        per_role[role] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
            "predicted": predicted,
        }

    return {
        "plane": ROLE_PLANE_TOKEN,
        "prediction_usable": True,
        "prediction_status": prediction_status,
        "evidence_status": "measured",
        "support": eligible_concrete_count,
        "coverage": _safe_div(coverage_n, coverage_d),
        "abstention_rate": 0.0,
        "unknown_rate": _safe_div(explicit_unknown_count, explicit_pred_count),
        "unknown_reference_recall": _safe_div(unknown_ref_hit, unknown_ref_count),
        "bar_weighted_accuracy": _safe_div(correct_bars, total_bars),
        "bar_weighted_accuracy_kind": "diagnostic",
        "macro_f1": statistics.fmean(macro_values) if macro_values else None,
        "per_role": per_role,
        "confusion_matrix": {
            ref: dict(sorted(row.items()))
            for ref, row in sorted(confusion.items())
            if row
        },
        "excluded_section_count": excluded_count,
        "role_items": role_items,
    }


def _normalize_reference_events(
    reference_boundaries: list[dict[str, Any]],
    reference_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    boundary_ids = {str(b["boundary_id"]): int(b["bar_index"]) for b in reference_boundaries}
    refs: list[dict[str, Any]] = []
    for order, raw in enumerate(reference_events):
        boundary_id = str(raw["boundary_id"])
        if boundary_id not in boundary_ids:
            raise ValueError(f"drop event references unknown boundary: {boundary_id}")
        refs.append(
            {
                "boundary_id": str(raw.get("event_id") or f"ref-{order}"),
                "event_id": str(raw.get("event_id") or f"ref-{order}"),
                "anchor_boundary_id": boundary_id,
                "bar_index": int(raw.get("bar_index", boundary_ids[boundary_id])),
                "order": order,
            }
        )
    return refs


def _normalize_predicted_events(
    reference_boundaries: list[dict[str, Any]], predicted_events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    boundary_ids = {str(b["boundary_id"]) for b in reference_boundaries}
    preds: list[dict[str, Any]] = []
    for order, raw in enumerate(predicted_events):
        boundary_id = str(raw["boundary_id"])
        if boundary_id not in boundary_ids:
            raise ValueError(f"predicted drop references unknown boundary: {boundary_id}")
        preds.append(
            {
                "pred_id": str(raw.get("event_id") or f"pred-{order}"),
                "boundary_id": boundary_id,
                "bar_index": int(raw["bar_index"]),
                "order": order,
            }
        )
    return preds


def _drop_ignore_masks(reference_boundaries: list[dict[str, Any]]) -> list[dict[str, int]]:
    masks: list[dict[str, int]] = []
    tol = int(BOUNDARY_MATCH_TOLERANCE_BARS)
    for boundary in reference_boundaries:
        if str(boundary.get("annotation_status")) != "ambiguous":
            continue
        bar = int(boundary["bar_index"])
        masks.append({"lo": bar - tol, "hi": bar + tol, "source_bar": bar})
    return masks


def _bar_in_masks(bar_index: int, masks: list[dict[str, int]]) -> bool:
    return any(int(mask["lo"]) <= bar_index <= int(mask["hi"]) for mask in masks)


def score_drops(
    reference_boundaries: list[dict[str, Any]],
    reference_events: list[dict[str, Any]],
    predicted_events: list[dict[str, Any]],
    *,
    prediction_usable: bool = True,
    prediction_status: str = "ok",
    beatgrid_status: str = "authored_synthetic",
) -> dict[str, Any]:
    if not prediction_usable or beatgrid_status in {"missing", "insufficient"}:
        return {
            "plane": DROP_PLANE_TOKEN,
            "event_eligible": beatgrid_status not in {"missing", "insufficient"},
            "prediction_usable": False,
            "prediction_status": prediction_status,
            "evidence_status": "unknown",
            "support": len(reference_events),
            "matched_count": None,
            "false_positive_count": None,
            "missed_count": None,
            "precision_1bar": None,
            "recall_1bar": None,
            "f1_1bar": None,
            "false_rate": None,
            "miss_rate": None,
            "coverage": 0.0,
            "abs_error_bars_median": None,
            "abs_error_bars_p95": None,
            "matched_pairs": [],
        }
    boundary_status = {
        str(item["boundary_id"]): str(item.get("annotation_status") or "single_source")
        for item in reference_boundaries
    }
    masks = _drop_ignore_masks(reference_boundaries)
    refs = [
        item
        for item in _normalize_reference_events(reference_boundaries, reference_events)
        if boundary_status.get(str(item["anchor_boundary_id"])) in _ELIGIBLE_ANNOTATION
        and not _bar_in_masks(int(item["bar_index"]), masks)
    ]
    preds = [
        item
        for item in _normalize_predicted_events(reference_boundaries, predicted_events)
        if not _bar_in_masks(int(item["bar_index"]), masks)
    ]
    matched, missed, extras = match_boundaries_1bar(refs, preds)
    errors = [float(item["abs_error_bars"]) for item in matched]
    precision = _safe_div(len(matched), len(preds))
    recall = _safe_div(len(matched), len(refs))
    return {
        "plane": DROP_PLANE_TOKEN,
        "event_eligible": True,
        "prediction_usable": True,
        "prediction_status": prediction_status,
        "evidence_status": "measured",
        "support": len(refs),
        "matched_count": len(matched),
        "false_positive_count": len(extras),
        "missed_count": len(missed),
        "precision_1bar": precision,
        "recall_1bar": recall,
        "f1_1bar": _f1(precision, recall),
        "false_rate": _safe_div(len(extras), len(preds)),
        "miss_rate": _safe_div(len(missed), len(refs)),
        "coverage": 1.0,
        "abs_error_bars_median": statistics.median(errors) if errors else None,
        "abs_error_bars_p95": percentile(errors, 95) if errors else None,
        "matched_pairs": matched,
        "predicted_events": preds,
        "reference_events": refs,
        "ignore_masks": masks,
    }


def assert_boundary_geometry_preserved(
    input_boundaries: list[dict[str, Any]],
    output_boundaries: list[dict[str, Any]],
    input_sections: list[dict[str, Any]],
    output_sections: list[dict[str, Any]],
) -> None:
    in_b = [(b["boundary_id"], int(b["bar_index"])) for b in input_boundaries]
    out_b = [(b["boundary_id"], int(b["bar_index"])) for b in output_boundaries]
    if in_b != out_b:
        raise ValueError("boundary geometry changed")
    in_s = [(s["section_id"], int(s["start_bar"]), int(s["end_bar"])) for s in input_sections]
    out_s = [
        (s["section_id"], int(s["start_bar"]), int(s["end_bar"]))
        for s in output_sections
    ]
    if in_s != out_s:
        raise ValueError("section geometry changed")


def evaluate_beatgrid_hold(
    *,
    fixture_id: str,
    beatgrid_status: str,
    role_eligible: bool,
    drop_eligible: bool,
) -> dict[str, Any]:
    hold = beatgrid_status in {"missing", "insufficient"}
    status = "unknown" if hold else "measured"
    return {
        "fixture_id": fixture_id,
        "hold_kind": "BEATGRID_PROVENANCE_LIMITATION" if hold else None,
        "role": {
            "eligible": bool(role_eligible),
            "evidence_status": status,
        },
        "drop_event": {
            "eligible": bool(drop_eligible),
            "evidence_status": status,
        },
    }


def optional_signal_provenance(
    measured: Mapping[str, str] | None = None,
    *,
    optional_backends: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    out = dict(measured or {})
    for name, value in (optional_backends or {}).items():
        if value is None:
            out[name] = "not_applicable"
        elif isinstance(value, str):
            out[name] = value
        else:
            out[name] = "measured"
    out.setdefault("clap", "not_applicable")
    out.setdefault("stems", "not_applicable")
    return out


def prediction_surface_state(*, role_status: str, drop_status: str) -> dict[str, Any]:
    return {
        "role_status": role_status,
        "drop_status": drop_status,
        "visible": True,
    }


def aggregate_splits(fixture_rows: list[dict[str, Any]]) -> dict[str, Any]:
    splits: dict[str, Any] = {}
    for split in ("CALIBRATION", "TEST"):
        rows = [row for row in fixture_rows if row.get("split") == split]
        role_support = sum(
            int((row.get("role") or row.get("aq7.role") or {}).get("support") or 0)
            for row in rows
        )
        drop_support = sum(
            int(
                (row.get("drop_event") or row.get("aq7.drop_event") or {}).get(
                    "support"
                )
                or 0
            )
            for row in rows
        )
        splits[split] = {
            "role": {"support": role_support},
            "drop_event": {"support": drop_support},
        }
    return splits


def _authored_eval_beatgrid(
    *,
    sample_rate: int,
    n_samples: int,
    track_end_bar: int,
    bpm: float,
) -> BeatGridResult:
    bars = max(1, int(track_end_bar))
    beat_count = bars * 4
    downbeats = tuple(
        min(n_samples - 1, int(round((index / bars) * n_samples)))
        for index in range(bars)
    )
    beats = tuple(
        min(n_samples - 1, int(round((index / beat_count) * n_samples)))
        for index in range(beat_count)
    )
    source = BeatGridSource(
        component="beat_grid",
        backend="aq7_authored_synthetic_eval",
        backend_version="1",
        checkpoint=None,
        config={
            "provenance": "authored_synthetic",
            "note": "evaluation grid from audio duration + track_end_bar",
        },
    )
    return BeatGridResult(
        status="ok",
        bpm=float(bpm),
        beats=BeatGridSeries(
            status="ok",
            sample_indices=beats,
            times_sec=tuple(s / sample_rate for s in beats),
        ),
        downbeats=BeatGridSeries(
            status="ok",
            sample_indices=downbeats,
            times_sec=tuple(s / sample_rate for s in downbeats),
        ),
        source=source,
    )


def _infer_bpm(n_samples: int, sample_rate: int, track_end_bar: int) -> float:
    duration = n_samples / float(sample_rate)
    if track_end_bar <= 0 or duration <= 0:
        return 120.0
    return (float(track_end_bar) * 4.0 * 60.0) / duration


def _bar_sample(n_samples: int, track_end_bar: int, bar_index: int) -> int:
    if track_end_bar <= 0:
        return 0
    if bar_index >= track_end_bar:
        return n_samples
    return int(round((bar_index / float(track_end_bar)) * n_samples))


def _patch_structure_geometry(
    *,
    gt: Mapping[str, Any],
    analyzed: StructureV1Result,
    sample_rate: int,
    n_samples: int,
) -> tuple[StructureV1Result, dict[str, str]]:
    track_end = track_end_bar_from_gt(gt)
    boundaries = []
    for ref in reference_boundaries_from_gt(gt):
        sample_index = _bar_sample(n_samples, track_end, int(ref["bar_index"]))
        boundaries.append(
            StructureBoundary(
                sample_index=sample_index,
                time_sec=sample_index / float(sample_rate),
                bar_index=int(ref["bar_index"]),
                downbeat_index=int(ref["bar_index"]),
                score=1.0,
                contributing_signals=("frozen_reference_geometry",),
            )
        )
    sections = []
    for section in frozen_reference_sections_from_gt(gt):
        start_sample = _bar_sample(n_samples, track_end, int(section["start_bar"]))
        end_sample = _bar_sample(n_samples, track_end, int(section["end_bar"]))
        sections.append(
            StructureSection(
                id=str(section["section_id"]),
                start_sample=start_sample,
                end_sample=end_sample,
                start_sec=start_sample / float(sample_rate),
                end_sec=end_sample / float(sample_rate),
                start_bar=int(section["start_bar"]),
                end_bar=int(section["end_bar"]),
            )
        )
    source = StructureV1Source(
        backend=analyzed.source.backend,
        backend_version=analyzed.source.backend_version,
        config={
            **dict(analyzed.source.config),
            "geometry_source": "aq7_frozen_reference_sections",
            "boundary_reference": BOUNDARY_CONTEXT_CANDIDATE_ID,
        },
    )
    status = "partial" if analyzed.status == "partial" else "ok"
    patched = StructureV1Result(
        status=status,
        boundaries=tuple(boundaries),
        sections=tuple(sections),
        feature_status=dict(analyzed.feature_status),
        notes=tuple(analyzed.notes),
        source=source,
        reason_code=None,
        bar_features=dict(analyzed.bar_features),
    )
    id_by_bar = {str(b["bar_index"]): str(b["boundary_id"]) for b in reference_boundaries_from_gt(gt)}
    return patched, id_by_bar


def _predicted_role_rows(arrangement: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in arrangement.sections:
        rows.append(
            {
                "section_id": section.section_id,
                "automatic_result": {
                    "role": section.automatic_result.role,
                    "status": section.automatic_result.status,
                },
                "effective_result": {
                    "role": section.effective_value.role,
                    "source": section.effective_value.source,
                },
            }
        )
    return rows


def _predicted_drop_rows(arrangement: Any, id_by_bar: Mapping[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, event in enumerate(arrangement.events):
        boundary_id = id_by_bar.get(str(event.bar_index))
        if boundary_id is None:
            boundary_id = f"unknown-bar-{event.bar_index}"
        rows.append(
            {
                "event_id": f"pred-{index}",
                "event_type": event.event,
                "boundary_id": boundary_id,
                "bar_index": int(event.bar_index),
                "status": event.status,
            }
        )
    return rows


def _fixture_hold_row(gt: Mapping[str, Any], *, hold_kind: str) -> dict[str, Any]:
    refs = frozen_reference_sections_from_gt(gt)
    role = score_roles(refs, [], prediction_usable=False, prediction_status="hold")
    drops = score_drops(
        reference_boundaries_from_gt(gt),
        list(gt.get("drop_events") or []),
        [],
        prediction_usable=False,
        prediction_status="hold",
        beatgrid_status=str((gt.get("beatgrid_provenance") or {}).get("status") or "missing"),
    )
    return {
        "fixture_id": gt["fixture_id"],
        "split": gt["split"],
        "family": gt.get("family"),
        "beatgrid_status": (gt.get("beatgrid_provenance") or {}).get("status"),
        "hold_kind": hold_kind,
        "role": role,
        "drop_event": drops,
        "signal_provenance": optional_signal_provenance(),
        "prediction_surface": prediction_surface_state(
            role_status="hold", drop_status="hold"
        ),
        "runtime_sec": None,
    }


def _predict_fixture(
    *,
    audio_path: Path,
    gt: Mapping[str, Any],
    analyzer: StructureV1Analyzer,
    classifier: ArrangementClassifier | None = None,
) -> dict[str, Any]:
    beatgrid_status = str((gt.get("beatgrid_provenance") or {}).get("status") or "missing")
    if beatgrid_status in {"missing", "insufficient"}:
        return _fixture_hold_row(gt, hold_kind="BEATGRID_PROVENANCE_LIMITATION")

    info = sf.info(str(audio_path))
    sample_rate = int(info.samplerate)
    n_samples = int(info.frames)
    timebase = AudioTimebase(sample_rate=sample_rate, n_samples=n_samples)
    track_end = track_end_bar_from_gt(gt)
    grid = _authored_eval_beatgrid(
        sample_rate=sample_rate,
        n_samples=n_samples,
        track_end_bar=track_end,
        bpm=_infer_bpm(n_samples, sample_rate, track_end),
    )
    t0 = time.perf_counter()
    analyzed = analyzer.analyze_path(audio_path, timebase, grid)
    runtime_sec = time.perf_counter() - t0
    if analyzed.status in {"failed", "no_result"} or not analyzed.bar_features:
        row = _fixture_hold_row(gt, hold_kind="ANALYZER_FEATURE_LIMITATION")
        row["runtime_sec"] = runtime_sec
        return row

    try:
        patched, id_by_bar = _patch_structure_geometry(
            gt=gt,
            analyzed=analyzed,
            sample_rate=sample_rate,
            n_samples=n_samples,
        )
        signals = SectionSignalsAssembler().assemble(patched)
        arrangement = (classifier or ArrangementClassifier()).classify_track(
            patched, signals, manual_overrides=None
        )
        role_preds = _predicted_role_rows(arrangement)
        drop_preds = _predicted_drop_rows(arrangement, id_by_bar)
        role_metrics = score_roles(
            frozen_reference_sections_from_gt(gt),
            role_preds,
            prediction_usable=arrangement.status not in {"failed", "unavailable"},
            prediction_status=arrangement.status,
        )
        drop_metrics = score_drops(
            reference_boundaries_from_gt(gt),
            list(gt.get("drop_events") or []),
            drop_preds,
            prediction_usable=arrangement.status not in {"failed", "unavailable"},
            prediction_status=arrangement.status,
            beatgrid_status=beatgrid_status,
        )
        signal_states: dict[str, str] = {}
        if signals:
            available = set().union(*(set(s.available_signals) for s in signals))
            missing = set().union(*(set(s.missing_signals) for s in signals))
            signal_states.update({name: "measured" for name in sorted(available)})
            signal_states.update({name: "missing" for name in sorted(missing)})
        return {
            "fixture_id": gt["fixture_id"],
            "split": gt["split"],
            "family": gt.get("family"),
            "beatgrid_status": beatgrid_status,
            "hold_kind": None,
            "structure_status": analyzed.status,
            "arrangement_status": arrangement.status,
            "role": role_metrics,
            "drop_event": drop_metrics,
            "signal_provenance": optional_signal_provenance(signal_states),
            "prediction_surface": prediction_surface_state(
                role_status=arrangement.status, drop_status=arrangement.status
            ),
            "runtime_sec": runtime_sec,
        }
    except Exception as exc:
        row = _fixture_hold_row(gt, hold_kind="CONTROLLED_HARNESS_FAILURE")
        row["controlled_failure"] = str(exc)
        row["runtime_sec"] = runtime_sec
        return row


def _aggregate_role(rows: list[dict[str, Any]]) -> dict[str, Any]:
    role_items: list[dict[str, Any]] = []
    confusion: dict[str, dict[str, int]] = {}
    support = 0
    eligible_concrete = 0
    coverage_n = 0
    correct_bars = 0
    total_bars = 0
    unknown_pred = 0
    pred_count = 0
    unknown_ref = 0
    unknown_ref_hit = 0
    held = 0
    for row in rows:
        role = row.get("role") or {}
        if not role.get("prediction_usable"):
            held += 1
            # Held rows keep concrete support in the coverage denominator only.
            eligible_concrete += int(role.get("support") or 0)
            continue
        for item in role.get("role_items") or []:
            role_items.append(dict(item))
            ref = item.get("ref_role")
            pred = item.get("pred_role")
            if ref in CONCRETE_ROLE_VOCABULARY:
                support += 1
                eligible_concrete += 1
                total_bars += max(0, int(item["end_bar"]) - int(item["start_bar"]))
            if ref == "unknown":
                unknown_ref += 1
            if pred is None:
                continue
            pred_count += 1
            if pred == "unknown":
                unknown_pred += 1
            if ref == "unknown" and pred == "unknown":
                unknown_ref_hit += 1
            if ref in CONCRETE_ROLE_VOCABULARY and pred != "unknown":
                coverage_n += 1
            if ref in CONCRETE_ROLE_VOCABULARY and pred == ref:
                correct_bars += max(0, int(item["end_bar"]) - int(item["start_bar"]))
            confusion.setdefault(str(ref), {})
            confusion[str(ref)][str(pred)] = confusion[str(ref)].get(str(pred), 0) + 1

    per_role: dict[str, dict[str, Any]] = {}
    macro_values: list[float] = []
    for role in CONCRETE_ROLE_VOCABULARY:
        role_support = sum(sum(v.values()) for k, v in confusion.items() if k == role)
        predicted = sum(v.get(role, 0) for v in confusion.values())
        tp = confusion.get(role, {}).get(role, 0)
        precision = _safe_div(tp, predicted)
        recall = _safe_div(tp, role_support)
        f1 = _f1(precision, recall)
        if role_support > 0 and predicted == 0:
            f1 = 0.0
        if role_support == 0 and predicted > 0:
            f1 = 0.0
        if role_support > 0 or predicted > 0:
            macro_values.append(float(f1 or 0.0))
        per_role[role] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": role_support,
            "predicted": predicted,
        }
    return {
        "support": support,
        "coverage": _safe_div(coverage_n, eligible_concrete),
        "macro_f1": statistics.fmean(macro_values) if macro_values else None,
        "unknown_rate": _safe_div(unknown_pred, pred_count),
        "unknown_reference_recall": _safe_div(unknown_ref_hit, unknown_ref),
        "abstention_count": held,
        "bar_weighted_accuracy": _safe_div(correct_bars, total_bars),
        "bar_weighted_accuracy_kind": "diagnostic",
        "per_role": per_role,
        "confusion_matrix": {
            key: dict(sorted(value.items())) for key, value in sorted(confusion.items())
        },
        "role_items": role_items,
    }


def _aggregate_drop(rows: list[dict[str, Any]]) -> dict[str, Any]:
    support = matched = false_positive = missed = usable = 0
    eligible_records = 0
    errors: list[float] = []
    for row in rows:
        drop = row.get("drop_event") or {}
        if drop.get("event_eligible", True):
            eligible_records += 1
        if not drop.get("prediction_usable"):
            continue
        usable += 1
        support += int(drop.get("support") or 0)
        matched += int(drop.get("matched_count") or 0)
        false_positive += int(drop.get("false_positive_count") or 0)
        missed += int(drop.get("missed_count") or 0)
        for pair in drop.get("matched_pairs") or []:
            errors.append(float(pair["abs_error_bars"]))
    pred_count = matched + false_positive
    precision = _safe_div(matched, pred_count)
    recall = _safe_div(matched, support)
    return {
        "support": support,
        "matched_count": matched,
        "false_positive_count": false_positive,
        "missed_count": missed,
        "precision_1bar": precision,
        "recall_1bar": recall,
        "f1_1bar": _f1(precision, recall),
        "false_rate": _safe_div(false_positive, pred_count),
        "miss_rate": _safe_div(missed, support),
        "coverage": _safe_div(usable, eligible_records),
        "abs_error_bars_median": statistics.median(errors) if errors else None,
        "abs_error_bars_p95": percentile(errors, 95) if errors else None,
    }


def aggregate_role_drop_splits(fixture_rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for split in ("CALIBRATION", "TEST"):
        rows = [row for row in fixture_rows if row.get("split") == split]
        out[split] = {
            ROLE_PLANE_TOKEN: _aggregate_role(rows),
            DROP_PLANE_TOKEN: _aggregate_drop(rows),
            "n_fixtures": len(rows),
            "n_beatgrid_hold": sum(
                1
                for row in rows
                if row.get("hold_kind") == "BEATGRID_PROVENANCE_LIMITATION"
            ),
        }
    return out


def resolve_exit_status(fixture_rows: list[dict[str, Any]], splits: Mapping[str, Any]) -> str:
    if len(fixture_rows) < 10:
        return EXIT_INCOMPLETE
    if any(
        row.get("hold_kind") not in {None, "BEATGRID_PROVENANCE_LIMITATION"}
        for row in fixture_rows
    ):
        return EXIT_INCOMPLETE
    if any(row.get("hold_kind") == "BEATGRID_PROVENANCE_LIMITATION" for row in fixture_rows):
        return EXIT_PARTIAL_HOLD
    for split in ("CALIBRATION", "TEST"):
        if int((splits.get(split) or {}).get("n_fixtures") or 0) == 0:
            return EXIT_INCOMPLETE
    return EXIT_MEASURED


def semantic_projection(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "document_type": result.get("document_type"),
        "schema_version": result.get("schema_version"),
        "candidate_id": result.get("candidate_id"),
        "corpus_id": result.get("corpus_id"),
        "corpus_version": result.get("corpus_version"),
        "boundary_reference": result.get("boundary_reference"),
        "exit_status": result.get("exit_status"),
        "splits": result.get("splits"),
        "fixtures": [
            {
                "fixture_id": row.get("fixture_id"),
                "split": row.get("split"),
                "hold_kind": row.get("hold_kind"),
                "role_items": (row.get("role") or {}).get("role_items"),
                "roles": row.get("roles"),
                "drop_matched": (row.get("drop_event") or {}).get("matched_pairs"),
                "drop_predicted": (row.get("drop_event") or {}).get("predicted_events"),
                "drop_reference": (row.get("drop_event") or {}).get("reference_events"),
                "drops": row.get("drops"),
                "prediction_surface": row.get("prediction_surface"),
            }
            for row in result.get("fixtures", [])
        ],
    }


def compare_semantic(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return dict(left) == dict(right)


def _assert_output_outside_repo(output_path: Path, root: Path) -> None:
    assert_work_dir_outside_repo(output_path.parent, root)
    try:
        output_path.resolve().relative_to(root.resolve())
    except ValueError:
        return
    raise ValueError(f"output path must be outside repo: {output_path.resolve()}")


def run_aq7_structure_role_drop_baseline(
    *,
    work_dir: Path | str,
    output_path: Path | str,
    repo_root: Path | str | None = None,
    prior_semantic: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    work = Path(work_dir)
    out = Path(output_path)
    assert_work_dir_outside_repo(work, root)
    _assert_output_outside_repo(out, root)

    generate_aq7_structure_role_drop_corpus(work, repo_root=root)
    manifest = load_aq7_corpus_manifest(work / "manifest.json")
    analyzer = StructureV1Analyzer(StructureV1Config())
    fixture_rows: list[dict[str, Any]] = []
    for item in manifest["fixtures"]:
        fixture_id = str(item["fixture_id"])
        gt = load_aq7_fixture_gt(work / "gt" / f"{fixture_id}.json")
        fixture_rows.append(
            _predict_fixture(
                audio_path=work / "audio" / f"{fixture_id}.wav",
                gt=gt,
                analyzer=analyzer,
            )
        )

    splits = aggregate_role_drop_splits(fixture_rows)
    runtimes = [float(row["runtime_sec"]) for row in fixture_rows if row.get("runtime_sec") is not None]
    runtime = {
        "methodology": "docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md",
        "by_reference": True,
        "methodology_v1_compliant": False,
        "diagnostic_only": True,
        "track_length_buckets": "HOLD",
        "track_length_buckets_reason": "synthetic pack too small for #958 buckets",
        "per_fixture_runtime_sec_median_diagnostic": (
            statistics.median(runtimes) if runtimes else None
        ),
        "per_fixture_runtime_sec_p95_diagnostic": (
            percentile(runtimes, 95) if runtimes else None
        ),
    }
    result: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "candidate_id": CANDIDATE_ID,
        "corpus_id": CORPUS_ID,
        "corpus_version": CORPUS_VERSION,
        "generator_seed": GENERATOR_SEED,
        "boundary_reference": BOUNDARY_CONTEXT_CANDIDATE_ID,
        "boundary_reference_document_type": BOUNDARY_CONTEXT_DOCUMENT_TYPE,
        "surfaces": {
            ROLE_PLANE_TOKEN: ARRANGEMENT_SURFACE,
            DROP_PLANE_TOKEN: ARRANGEMENT_SURFACE,
            "section_signals": SECTION_SIGNAL_SURFACE,
            "structure_features": STRUCTURE_SURFACE,
        },
        "classifier": {
            "candidate_id": CANDIDATE_ID,
            "manual_overrides": None,
            "automatic_only": True,
        },
        "algorithm_changed": False,
        "production_defaults_changed": False,
        "feature_toggle": FEATURE_TOGGLE,
        "partition_policy": dict(PARTITION_POLICY),
        "matching": {
            "tolerance_bars": BOUNDARY_MATCH_TOLERANCE_BARS,
            "policy": "one_to_one_order_preserving_max_matches_then_min_abs_error",
        },
        "runtime": runtime,
        "splits": splits,
        "fixtures": fixture_rows,
    }
    result["exit_status"] = resolve_exit_status(fixture_rows, splits)
    semantic = semantic_projection(result)
    result["determinism"] = {
        "methodology": "docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md",
        "by_reference": True,
        "status": "measured" if prior_semantic is not None else "not_measured",
        "semantic_equal": (
            compare_semantic(semantic, prior_semantic)
            if prior_semantic is not None
            else None
        ),
        "semantic_projection_keys": sorted(semantic.keys()),
    }
    assert_portable_baseline_payload(result)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def load_role_drop_baseline_artifact(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to load role/drop baseline artifact: {path}") from exc
    assert_portable_baseline_payload(payload)
    if payload.get("document_type") != DOCUMENT_TYPE:
        raise ValueError("document_type mismatch")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("schema_version mismatch")
    if payload.get("candidate_id") != CANDIDATE_ID:
        raise ValueError("candidate_id mismatch")
    if payload.get("corpus_id") != CORPUS_ID:
        raise ValueError("corpus_id mismatch")
    if payload.get("corpus_version") != CORPUS_VERSION:
        raise ValueError("corpus_version mismatch")
    if payload.get("boundary_reference") != BOUNDARY_CONTEXT_CANDIDATE_ID:
        raise ValueError("boundary_reference mismatch")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure AQ7 role/drop baseline on frozen synthetic corpus."
    )
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--prior-semantic", default=None)
    args = parser.parse_args(argv)
    prior = None
    if args.prior_semantic:
        prior_payload = load_role_drop_baseline_artifact(args.prior_semantic)
        prior = semantic_projection(prior_payload)
    result = run_aq7_structure_role_drop_baseline(
        work_dir=args.work_dir,
        output_path=args.output,
        repo_root=args.repo_root,
        prior_semantic=prior,
    )
    print(
        json.dumps(
            {
                "exit_status": result["exit_status"],
                "fixture_count": len(result["fixtures"]),
                "candidate_id": result["candidate_id"],
                "semantic_equal": result["determinism"]["semantic_equal"],
            }
        )
    )
    return 0 if result["exit_status"] in {EXIT_MEASURED, EXIT_PARTIAL_HOLD} else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARRANGEMENT_SURFACE",
    "BOUNDARY_CONTEXT_CANDIDATE_ID",
    "BOUNDARY_CONTEXT_DOCUMENT_TYPE",
    "BOUNDARY_MATCH_TOLERANCE_BARS",
    "CANDIDATE_ID",
    "CONCRETE_ROLE_VOCABULARY",
    "CORPUS_ID",
    "CORPUS_VERSION",
    "DOCUMENT_TYPE",
    "DROP_PLANE_TOKEN",
    "EXIT_INCOMPLETE",
    "EXIT_MEASURED",
    "EXIT_PARTIAL_HOLD",
    "FEATURE_TOGGLE",
    "GENERATOR_SEED",
    "PRODUCTION_DEFAULTS_CHANGED",
    "PROTECTED_ANALYZER_FILES",
    "PROTECTED_ANALYZER_FILES_CHANGED",
    "ROLE_PLANE_TOKEN",
    "ROLE_VOCABULARY",
    "SCHEMA_VERSION",
    "aggregate_role_drop_splits",
    "aggregate_splits",
    "assert_boundary_geometry_preserved",
    "assert_portable_baseline_payload",
    "build_frozen_geometry_classifier_input",
    "compare_semantic",
    "evaluate_beatgrid_hold",
    "frozen_reference_sections_from_gt",
    "load_role_drop_baseline_artifact",
    "optional_signal_provenance",
    "prediction_surface_state",
    "reference_boundaries_from_gt",
    "resolve_exit_status",
    "run_aq7_structure_role_drop_baseline",
    "score_drops",
    "score_roles",
    "semantic_projection",
]
