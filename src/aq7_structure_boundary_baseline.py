"""AQ7 StructureV1 neutral boundary/segmentation baseline (#1025).

Measures current StructureV1 against frozen #1024 reference boundaries on the
``aq7.boundary`` plane only. No algorithm changes. No role/drop evaluation.
External JSON only.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import soundfile as sf

from .analysis_eval_artifact import (
    AnalysisEvalArtifactError,
    assert_portable_value,
)
from .aq7_structure_role_drop_corpus import (
    CORPUS_ID,
    CORPUS_VERSION,
    assert_work_dir_outside_repo,
    generate_aq7_structure_role_drop_corpus,
)
from .aq7_structure_role_drop_schema import BOUNDARY_MATCH_TOLERANCE_BARS
from .beat_grid import BeatGridResult, BeatGridSeries, BeatGridSource
from .canon_audio import AudioTimebase
from .measurement.stats import percentile
from .structure_v1 import StructureV1Analyzer, StructureV1Config

DOCUMENT_TYPE = "sample-brain.aq7.structure-boundary-baseline.v1"
SCHEMA_VERSION = "1.0.0"
CANDIDATE_ID = "structure_v1.baseline.v1"
EXIT_MEASURED = "AQ7_STRUCTURE_BOUNDARY_BASELINE_MEASURED"
EXIT_PARTIAL_HOLD = "AQ7_STRUCTURE_BOUNDARY_BASELINE_PARTIAL_HOLD"
EXIT_INCOMPLETE = "AQ7_STRUCTURE_BOUNDARY_BASELINE_INCOMPLETE"
STRUCTURE_SURFACE = "src.structure_v1.StructureV1Analyzer.analyze_path"
PLANE_TOKEN = "aq7.boundary"

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]

PARTITION_POLICY = {
    "CALIBRATION": "DEVELOPMENT/CALIBRATION",
    "TEST": "TEST/HOLDOUT",
}

PROVENANCE: dict[str, Any] = {
    "runtime_methodology": {
        "issue": "#958",
        "doc": "docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md",
        "by_reference": True,
    },
    "semantic_determinism": {
        "issue": "#959",
        "doc": "docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md",
        "by_reference": True,
    },
    "kpi_contract": {
        "issue": "#1023",
        "doc": "docs/benchmarks/AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md",
        "by_reference": True,
    },
    "corpus": {
        "issue": "#1024",
        "doc": "docs/benchmarks/AQ7_STRUCTURE_ROLE_DROP_CORPUS.md",
        "by_reference": True,
    },
}

_ELIGIBLE_ANNOTATION = frozenset({"adjudicated", "single_source"})
_PLANE_ELIGIBLE = frozenset({"adjudicated", "single_source", "ambiguous"})
_USABLE_NO_RESULT_REASONS = frozenset({"NO_BOUNDARY_CANDIDATE"})
_UNUSABLE_NO_RESULT_REASONS = frozenset(
    {"DOWNBEATS_UNAVAILABLE", "FEATURES_UNAVAILABLE", "INSUFFICIENT_BARS"}
)


def assert_portable_baseline_payload(payload: Any) -> None:
    try:
        assert_portable_value(payload, field="aq7.structure_boundary_baseline")
    except AnalysisEvalArtifactError as exc:
        raise ValueError(str(exc)) from exc


def reference_boundaries_from_gt(gt: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract reference internal boundaries from corpus GT only."""
    refs: list[dict[str, Any]] = []
    for order, raw in enumerate(gt.get("boundaries") or []):
        if not isinstance(raw, dict):
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
    refs.sort(key=lambda r: (int(r["bar_index"]), int(r["order"]), r["boundary_id"]))
    for i, ref in enumerate(refs):
        ref["order"] = i
    return refs


def track_end_bar_from_gt(gt: dict[str, Any]) -> int:
    sections = gt.get("sections") or []
    if not sections:
        refs = reference_boundaries_from_gt(gt)
        if not refs:
            return 0
        return max(int(r["bar_index"]) for r in refs)
    return max(int(s["end_bar"]) for s in sections if isinstance(s, dict))


def _ignore_masks_from_refs(refs: list[dict[str, Any]]) -> list[dict[str, int]]:
    masks: list[dict[str, int]] = []
    tol = int(BOUNDARY_MATCH_TOLERANCE_BARS)
    for ref in refs:
        if str(ref.get("annotation_status")) != "ambiguous":
            continue
        bar = int(ref["bar_index"])
        masks.append({"lo": bar - tol, "hi": bar + tol, "source_bar": bar})
    return masks


def _bar_in_masks(bar: int, masks: list[dict[str, int]]) -> bool:
    return any(int(m["lo"]) <= bar <= int(m["hi"]) for m in masks)


def match_boundaries_1bar(
    refs: list[dict[str, Any]],
    preds: list[dict[str, Any]],
    *,
    tolerance_bars: int = BOUNDARY_MATCH_TOLERANCE_BARS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Order-preserving one-to-one matching within ±tolerance bars (#1023)."""
    refs_s = sorted(
        refs, key=lambda r: (int(r["bar_index"]), int(r.get("order", 0)), r.get("boundary_id", ""))
    )
    preds_s = sorted(
        preds, key=lambda p: (int(p["bar_index"]), int(p.get("order", 0)), p.get("pred_id", ""))
    )
    n, m = len(refs_s), len(preds_s)
    # dp[i][j] = (match_count, -total_abs_error) using first i refs and j preds
    neg_inf = -10**9
    dp: list[list[tuple[int, int]]] = [
        [(neg_inf, 0) for _ in range(m + 1)] for _ in range(n + 1)
    ]
    prev: list[list[tuple[str, int, int] | None]] = [
        [None for _ in range(m + 1)] for _ in range(n + 1)
    ]
    dp[0][0] = (0, 0)
    for i in range(n + 1):
        for j in range(m + 1):
            cur = dp[i][j]
            if cur[0] == neg_inf and not (i == 0 and j == 0):
                continue
            if i < n:
                skip = cur
                if skip > dp[i + 1][j]:
                    dp[i + 1][j] = skip
                    prev[i + 1][j] = ("skip_ref", i, j)
            if j < m:
                skip = cur
                if skip > dp[i][j + 1]:
                    dp[i][j + 1] = skip
                    prev[i][j + 1] = ("skip_pred", i, j)
            if i < n and j < m:
                err = abs(int(preds_s[j]["bar_index"]) - int(refs_s[i]["bar_index"]))
                if err <= tolerance_bars:
                    cand = (cur[0] + 1, cur[1] - err)
                    if cand > dp[i + 1][j + 1]:
                        dp[i + 1][j + 1] = cand
                        prev[i + 1][j + 1] = ("match", i, j)

    # Reconstruct
    i, j = n, m
    matched_idx: list[tuple[int, int]] = []
    used_refs: set[int] = set()
    used_preds: set[int] = set()
    while i > 0 or j > 0:
        step = prev[i][j]
        if step is None:
            if i > 0:
                i -= 1
            elif j > 0:
                j -= 1
            else:
                break
            continue
        kind, pi, pj = step
        if kind == "match":
            matched_idx.append((pi, pj))
            used_refs.add(pi)
            used_preds.add(pj)
            i, j = pi, pj
        elif kind == "skip_ref":
            i, j = pi, pj
        else:
            i, j = pi, pj

    matched: list[dict[str, Any]] = []
    for ri, pj in sorted(matched_idx, key=lambda t: t[0]):
        ref = refs_s[ri]
        pred = preds_s[pj]
        signed = int(pred["bar_index"]) - int(ref["bar_index"])
        matched.append(
            {
                "ref_id": ref["boundary_id"],
                "pred_id": pred["pred_id"],
                "ref_bar": int(ref["bar_index"]),
                "pred_bar": int(pred["bar_index"]),
                "abs_error_bars": abs(signed),
                "signed_error_bars": signed,
            }
        )
    missed = [refs_s[k] for k in range(n) if k not in used_refs]
    extras = [preds_s[k] for k in range(m) if k not in used_preds]
    return matched, missed, extras


def _sections_from_internal_bars(
    internal_bars: list[int], track_end_bar: int
) -> list[tuple[int, int]]:
    bars = sorted({int(b) for b in internal_bars if 0 < int(b) < track_end_bar})
    edges = [0, *bars, int(track_end_bar)]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1) if edges[i + 1] > edges[i]]


def _interval_iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    lo = max(a[0], b[0])
    hi = min(a[1], b[1])
    inter = max(0, hi - lo)
    if inter <= 0:
        return 0.0
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    if union <= 0:
        return 0.0
    return inter / union


def _match_sections(
    refs: list[tuple[int, int]], preds: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Order-preserving section matching maximizing overlap count then length."""
    n, m = len(refs), len(preds)
    neg_inf = -10**9
    # key: (overlap_count, total_overlap, -endpoint_l1)
    dp: list[list[tuple[int, int, int]]] = [
        [(neg_inf, 0, 0) for _ in range(m + 1)] for _ in range(n + 1)
    ]
    prev: list[list[tuple[str, int, int] | None]] = [
        [None for _ in range(m + 1)] for _ in range(n + 1)
    ]
    dp[0][0] = (0, 0, 0)
    for i in range(n + 1):
        for j in range(m + 1):
            cur = dp[i][j]
            if cur[0] == neg_inf and not (i == 0 and j == 0):
                continue
            if i < n and cur > dp[i + 1][j]:
                dp[i + 1][j] = cur
                prev[i + 1][j] = ("skip_ref", i, j)
            if j < m and cur > dp[i][j + 1]:
                dp[i][j + 1] = cur
                prev[i][j + 1] = ("skip_pred", i, j)
            if i < n and j < m:
                a, b = refs[i], preds[j]
                lo = max(a[0], b[0])
                hi = min(a[1], b[1])
                overlap = max(0, hi - lo)
                if overlap > 0:
                    l1 = abs(a[0] - b[0]) + abs(a[1] - b[1])
                    cand = (cur[0] + 1, cur[1] + overlap, cur[2] - l1)
                    if cand > dp[i + 1][j + 1]:
                        dp[i + 1][j + 1] = cand
                        prev[i + 1][j + 1] = ("match", i, j)
    i, j = n, m
    pairs: list[tuple[int, int]] = []
    while i > 0 or j > 0:
        step = prev[i][j]
        if step is None:
            if i > 0:
                i -= 1
            elif j > 0:
                j -= 1
            else:
                break
            continue
        kind, pi, pj = step
        if kind == "match":
            pairs.append((pi, pj))
            i, j = pi, pj
        else:
            i, j = pi, pj
    return pairs


def _segment_iou_weighted(
    ref_bars: list[int], pred_bars: list[int], track_end_bar: int
) -> tuple[float | None, float, float]:
    ref_secs = _sections_from_internal_bars(ref_bars, track_end_bar)
    pred_secs = _sections_from_internal_bars(pred_bars, track_end_bar)
    if not ref_secs:
        return None, 0.0, 0.0
    pairs = _match_sections(ref_secs, pred_secs)
    matched_pred = {pj for _, pj in pairs}
    numer = 0.0
    denom = 0.0
    pair_map = {ri: pj for ri, pj in pairs}
    for ri, ref in enumerate(ref_secs):
        weight = float(ref[1] - ref[0])
        denom += weight
        if ri in pair_map:
            numer += _interval_iou(ref, pred_secs[pair_map[ri]]) * weight
        else:
            numer += 0.0 * weight
    del matched_pred  # explicit: unmatched refs already contribute 0
    if denom <= 0:
        return None, 0.0, 0.0
    return numer / denom, numer, denom


def score_fixture_boundaries(
    refs: list[dict[str, Any]],
    preds: list[dict[str, Any]],
    *,
    track_end_bar: int,
    plane_status: str,
    prediction_usable: bool = True,
    prediction_status: str = "ok",
    reason_code: str | None = None,
) -> dict[str, Any]:
    masks = _ignore_masks_from_refs(refs)
    eligible_refs = [
        r for r in refs if str(r.get("annotation_status")) in _ELIGIBLE_ANNOTATION
    ]
    unmasked_preds = [
        p for p in preds if not _bar_in_masks(int(p["bar_index"]), masks)
    ]

    boundary_eligible = plane_status in _PLANE_ELIGIBLE or (
        plane_status == "unavailable" and False
    )
    # Unavailable plane is not boundary-eligible.
    if plane_status == "unavailable":
        boundary_eligible = False

    if not prediction_usable:
        return {
            "plane": PLANE_TOKEN,
            "boundary_eligible": boundary_eligible,
            "prediction_usable": False,
            "prediction_status": prediction_status,
            "reason_code": reason_code,
            "evidence_status": "unknown",
            "eligible_ref_count": len(eligible_refs) if boundary_eligible else 0,
            "pred_count_unmasked": None,
            "matched_count": None,
            "false_positive_count": None,
            "missed_count": None,
            "exact_match_count": None,
            "precision_1bar": None,
            "recall_1bar": None,
            "f1_1bar": None,
            "abs_errors_bars": [],
            "ignore_masks": masks,
            "segmentation": {
                "over_segmentation": None,
                "under_segmentation": None,
                "section_count_abs_error": None,
                "segment_iou_weighted": None,
            },
        }

    matched, missed, extras = match_boundaries_1bar(eligible_refs, unmasked_preds)
    matched_n = len(matched)
    pred_n = len(unmasked_preds)
    ref_n = len(eligible_refs)
    precision = (matched_n / pred_n) if pred_n else None
    recall = (matched_n / ref_n) if ref_n else None
    if precision is not None and recall is not None:
        f1 = (
            2.0 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
    else:
        f1 = None

    ref_section_count = 1 + ref_n
    pred_section_count = 1 + pred_n
    section_err = abs(pred_section_count - ref_section_count)
    over = pred_section_count > ref_section_count
    under = pred_section_count < ref_section_count
    iou, iou_numer, iou_denom = _segment_iou_weighted(
        [int(r["bar_index"]) for r in eligible_refs],
        [int(p["bar_index"]) for p in unmasked_preds],
        track_end_bar,
    )

    return {
        "plane": PLANE_TOKEN,
        "boundary_eligible": boundary_eligible,
        "prediction_usable": True,
        "prediction_status": prediction_status,
        "reason_code": reason_code,
        "evidence_status": "measured",
        "eligible_ref_count": ref_n,
        "pred_count_unmasked": pred_n,
        "matched_count": matched_n,
        "false_positive_count": len(extras),
        "missed_count": len(missed),
        "exact_match_count": sum(1 for m in matched if m["abs_error_bars"] == 0),
        "precision_1bar": precision,
        "recall_1bar": recall,
        "f1_1bar": f1,
        "abs_errors_bars": [float(m["abs_error_bars"]) for m in matched],
        "matched_pairs": matched,
        "ignore_masks": masks,
        "segmentation": {
            "over_segmentation": over,
            "under_segmentation": under,
            "section_count_abs_error": section_err,
            "ref_section_count": ref_section_count,
            "pred_section_count": pred_section_count,
            "segment_iou_weighted": iou,
            "segment_iou_weighted_numer": iou_numer,
            "segment_iou_weight_sum": iou_denom,
        },
    }


def evaluate_prediction_surface(
    *,
    structure_status: str | None,
    reason_code: str | None,
    beatgrid_status: str,
    analyzer_ran: bool,
) -> dict[str, Any]:
    if beatgrid_status in {"missing", "insufficient"}:
        return {
            "prediction_usable": False,
            "hold_kind": "BEATGRID_PROVENANCE_LIMITATION",
            "evidence_status": "unknown",
            "prediction_status": "hold",
            "reason_code": f"BEATGRID_{beatgrid_status.upper()}",
        }
    if not analyzer_ran or structure_status is None:
        return {
            "prediction_usable": False,
            "hold_kind": "ANALYZER_FAILURE",
            "evidence_status": "unknown",
            "prediction_status": "failed",
            "reason_code": reason_code or "ANALYZER_NOT_RUN",
        }
    if structure_status in {"ok", "partial"}:
        return {
            "prediction_usable": True,
            "hold_kind": None,
            "evidence_status": "measured",
            "prediction_status": structure_status,
            "reason_code": reason_code,
        }
    if structure_status == "no_result":
        code = reason_code or ""
        if code in _USABLE_NO_RESULT_REASONS:
            return {
                "prediction_usable": True,
                "hold_kind": None,
                "evidence_status": "measured",
                "prediction_status": "no_result",
                "reason_code": code,
            }
        return {
            "prediction_usable": False,
            "hold_kind": "ANALYZER_FAILURE",
            "evidence_status": "unknown",
            "prediction_status": "no_result",
            "reason_code": code or "NO_RESULT_UNUSABLE",
        }
    return {
        "prediction_usable": False,
        "hold_kind": "ANALYZER_FAILURE",
        "evidence_status": "unknown",
        "prediction_status": structure_status,
        "reason_code": reason_code or "FAILED",
    }


def error_summary_bars(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "median": None,
            "p95": None,
            "mean": None,
            "n": 0,
            "status": "not_applicable",
        }
    return {
        "median": float(statistics.median(values)),
        "p95": percentile(values, 95),
        "mean": float(statistics.fmean(values)),
        "n": len(values),
        "status": "measured",
    }


def _safe_div(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return num / den


def aggregate_boundary_splits(fixture_rows: list[dict[str, Any]]) -> dict[str, Any]:
    splits: dict[str, Any] = {}
    for split_name in ("CALIBRATION", "TEST"):
        rows = [r for r in fixture_rows if r.get("split") == split_name]
        eligible = [r for r in rows if r.get("boundary_eligible")]
        usable = [r for r in eligible if r.get("prediction_usable")]
        beatgrid_holds = [
            r
            for r in rows
            if r.get("hold_kind") == "BEATGRID_PROVENANCE_LIMITATION"
        ]
        matched = sum(int(r.get("matched_count") or 0) for r in usable)
        ref_n = sum(int(r.get("eligible_ref_count") or 0) for r in usable)
        pred_n = sum(int(r.get("pred_count_unmasked") or 0) for r in usable)
        fp = sum(int(r.get("false_positive_count") or 0) for r in usable)
        fn = sum(int(r.get("missed_count") or 0) for r in usable)
        exact = sum(int(r.get("exact_match_count") or 0) for r in usable)
        abs_errors: list[float] = []
        for r in usable:
            abs_errors.extend(float(x) for x in (r.get("abs_errors_bars") or []))
        err = error_summary_bars(abs_errors)
        precision = _safe_div(matched, pred_n)
        recall = _safe_div(matched, ref_n)
        if precision is not None and recall is not None:
            f1 = (
                2.0 * precision * recall / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )
        else:
            f1 = None
        section_errors = [
            int(r["section_count_abs_error"])
            for r in usable
            if r.get("section_count_abs_error") is not None
        ]
        section_mean = (
            float(statistics.fmean(section_errors)) if section_errors else None
        )
        over_n = sum(1 for r in usable if r.get("over_segmentation") is True)
        under_n = sum(1 for r in usable if r.get("under_segmentation") is True)
        iou_numer = sum(float(r.get("segment_iou_weighted_numer") or 0.0) for r in usable)
        iou_denom = sum(float(r.get("segment_iou_weight_sum") or 0.0) for r in usable)
        iou = (iou_numer / iou_denom) if iou_denom > 0 else None
        coverage = _safe_div(len(usable), len(eligible)) if eligible else None
        splits[split_name] = {
            "fixture_count": len(rows),
            "aq7.boundary": {
                "n_boundary_eligible": len(eligible),
                "n_usable": len(usable),
                "n_no_result": sum(
                    1
                    for r in eligible
                    if r.get("prediction_status") == "no_result"
                    and r.get("prediction_usable")
                ),
                "n_partial": sum(
                    1 for r in usable if r.get("prediction_status") == "partial"
                ),
                "n_beatgrid_hold": len(beatgrid_holds),
                "n_analyzer_failure": sum(
                    1 for r in rows if r.get("hold_kind") == "ANALYZER_FAILURE"
                ),
                "coverage": coverage,
                "metrics": {
                    "precision_1bar": precision,
                    "recall_1bar": recall,
                    "f1_1bar": f1,
                    "support": ref_n,
                    "matched_count": matched,
                    "false_positive_count": fp,
                    "missed_count": fn,
                    "exact_hit_rate": _safe_div(exact, matched),
                    "miss_rate": _safe_div(fn, ref_n),
                    "extra_rate": _safe_div(fp, pred_n),
                    "abs_error_bars_median": err["median"],
                    "abs_error_bars_p95": err["p95"],
                    "abs_error_bars_status": err["status"],
                    "section_count_abs_error": section_mean,
                    "over_segmentation_rate": _safe_div(over_n, len(usable)),
                    "under_segmentation_rate": _safe_div(under_n, len(usable)),
                    "segment_iou_weighted": iou,
                },
            },
        }
    return splits


def resolve_exit_status(
    *,
    splits: dict[str, Any],
    fixture_rows: list[dict[str, Any]],
    has_beatgrid_hold: bool,
) -> str:
    if len(fixture_rows) < 10:
        return EXIT_INCOMPLETE
    measurable = True
    for split_name in ("CALIBRATION", "TEST"):
        plane = (splits.get(split_name) or {}).get("aq7.boundary") or {}
        if int(plane.get("n_usable") or 0) < 1:
            measurable = False
            break
        metrics = plane.get("metrics") or {}
        if "f1_1bar" not in metrics and metrics.get("support", 0) == 0:
            # empty-support usable still counts if precision/recall policy applied
            if plane.get("n_usable", 0) < 1:
                measurable = False
                break
    if not measurable:
        # Partial if at least one split usable
        any_usable = any(
            int(((splits.get(s) or {}).get("aq7.boundary") or {}).get("n_usable") or 0) > 0
            for s in ("CALIBRATION", "TEST")
        )
        return EXIT_PARTIAL_HOLD if any_usable else EXIT_INCOMPLETE
    if has_beatgrid_hold:
        return EXIT_PARTIAL_HOLD
    # Also partial if any eligible record lacked usable surface
    for split_name in ("CALIBRATION", "TEST"):
        plane = (splits.get(split_name) or {}).get("aq7.boundary") or {}
        eligible = int(plane.get("n_boundary_eligible") or 0)
        usable = int(plane.get("n_usable") or 0)
        if eligible > usable:
            return EXIT_PARTIAL_HOLD
    return EXIT_MEASURED


def _authored_eval_beatgrid(
    *,
    sample_rate: int,
    n_samples: int,
    track_end_bar: int,
    bpm: float,
) -> BeatGridResult:
    """Evaluation-only synthetic grid from authored tempo (not GT boundaries)."""
    bar_samples = max(1, int(round(n_samples / max(1, track_end_bar))))
    beat_samples = max(1, bar_samples // 4)
    downbeats = tuple(range(0, n_samples, bar_samples))
    if downbeats and downbeats[-1] >= n_samples:
        downbeats = downbeats[:-1]
    if not downbeats or downbeats[0] != 0:
        downbeats = (0, *downbeats)
    beats = tuple(range(0, n_samples, beat_samples))
    if not beats or beats[0] != 0:
        beats = (0, *beats)
    source = BeatGridSource(
        component="beat_grid",
        backend="aq7_authored_synthetic_eval",
        backend_version="1",
        checkpoint=None,
        config={
            "provenance": "authored_synthetic",
            "note": "evaluation adapter grid from audio duration + track_end_bar; not analyzer BeatGrid GT",
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
    # bars * (4 beats/bar) * 60 / duration
    return (float(track_end_bar) * 4.0 * 60.0) / duration


def _predict_fixture(
    *,
    audio_path: Path,
    gt: dict[str, Any],
    analyzer: StructureV1Analyzer,
) -> dict[str, Any]:
    fixture_id = str(gt["fixture_id"])
    split = str(gt["split"])
    family = str(gt.get("family") or "")
    plane_status = str((gt.get("plane_status") or {}).get(PLANE_TOKEN) or "unavailable")
    beatgrid_status = str((gt.get("beatgrid_provenance") or {}).get("status") or "missing")
    refs = reference_boundaries_from_gt(gt)
    track_end = track_end_bar_from_gt(gt)

    surface = evaluate_prediction_surface(
        structure_status=None,
        reason_code=None,
        beatgrid_status=beatgrid_status,
        analyzer_ran=False,
    )
    runtime_sec: float | None = None
    pred_bars: list[dict[str, Any]] = []
    structure_status: str | None = None
    reason_code: str | None = None
    structure_notes: tuple[str, ...] = ()

    if surface["prediction_usable"] or beatgrid_status == "authored_synthetic":
        info = sf.info(str(audio_path))
        sample_rate = int(info.samplerate)
        n_samples = int(info.frames)
        timebase = AudioTimebase(sample_rate=sample_rate, n_samples=n_samples)
        bpm = _infer_bpm(n_samples, sample_rate, track_end)
        grid = _authored_eval_beatgrid(
            sample_rate=sample_rate,
            n_samples=n_samples,
            track_end_bar=track_end,
            bpm=bpm,
        )
        t0 = time.perf_counter()
        result = analyzer.analyze_path(audio_path, timebase, grid)
        runtime_sec = time.perf_counter() - t0
        structure_status = str(result.status)
        reason_code = result.reason_code
        structure_notes = tuple(result.notes)
        surface = evaluate_prediction_surface(
            structure_status=structure_status,
            reason_code=reason_code,
            beatgrid_status=beatgrid_status,
            analyzer_ran=True,
        )
        if surface["prediction_usable"]:
            pred_bars = [
                {
                    "pred_id": f"p{i}",
                    "bar_index": int(b.bar_index),
                    "order": i,
                    "time_sec": float(b.time_sec),
                }
                for i, b in enumerate(result.boundaries)
            ]

    scored = score_fixture_boundaries(
        refs,
        pred_bars,
        track_end_bar=track_end,
        plane_status=plane_status,
        prediction_usable=bool(surface["prediction_usable"]),
        prediction_status=str(surface.get("prediction_status") or "hold"),
        reason_code=surface.get("reason_code"),
    )

    seg = scored.get("segmentation") or {}
    row: dict[str, Any] = {
        "fixture_id": fixture_id,
        "split": split,
        "family": family,
        "plane_status": plane_status,
        "beatgrid_status": beatgrid_status,
        "boundary_eligible": bool(scored.get("boundary_eligible")),
        "prediction_usable": bool(scored.get("prediction_usable")),
        "prediction_status": scored.get("prediction_status"),
        "reason_code": scored.get("reason_code"),
        "hold_kind": surface.get("hold_kind"),
        "evidence_status": scored.get("evidence_status"),
        "structure_status": structure_status,
        "structure_notes": list(structure_notes),
        "eligible_ref_count": scored.get("eligible_ref_count"),
        "pred_count_unmasked": scored.get("pred_count_unmasked"),
        "matched_count": scored.get("matched_count"),
        "false_positive_count": scored.get("false_positive_count"),
        "missed_count": scored.get("missed_count"),
        "exact_match_count": scored.get("exact_match_count"),
        "precision_1bar": scored.get("precision_1bar"),
        "recall_1bar": scored.get("recall_1bar"),
        "f1_1bar": scored.get("f1_1bar"),
        "abs_errors_bars": list(scored.get("abs_errors_bars") or []),
        "section_count_abs_error": seg.get("section_count_abs_error"),
        "over_segmentation": seg.get("over_segmentation"),
        "under_segmentation": seg.get("under_segmentation"),
        "segment_iou_weighted": seg.get("segment_iou_weighted"),
        "segment_iou_weighted_numer": seg.get("segment_iou_weighted_numer"),
        "segment_iou_weight_sum": seg.get("segment_iou_weight_sum"),
        "ignore_masks": scored.get("ignore_masks") or [],
        "runtime_sec": runtime_sec,
        "predicted_bars": [int(p["bar_index"]) for p in pred_bars],
        "reference_bars": [
            int(r["bar_index"])
            for r in refs
            if str(r.get("annotation_status")) in _ELIGIBLE_ANNOTATION
        ],
    }
    return row


def _assert_output_outside_repo(output_path: Path, root: Path) -> None:
    assert_work_dir_outside_repo(
        output_path.parent if output_path.parent != output_path else output_path,
        root,
    )
    try:
        output_path.resolve().relative_to(root.resolve())
    except ValueError:
        return
    raise ValueError(f"output path must be outside repo: {output_path.resolve()}")


def semantic_projection(result: dict[str, Any]) -> dict[str, Any]:
    """Stable semantic view for #959-style equality (runtime excluded)."""
    return {
        "exit_status": result.get("exit_status"),
        "candidate_id": result.get("candidate_id"),
        "corpus_id": result.get("corpus_id"),
        "corpus_version": result.get("corpus_version"),
        "splits": {
            split: {
                "aq7.boundary": {
                    "n_usable": (block.get("aq7.boundary") or {}).get("n_usable"),
                    "metrics": (block.get("aq7.boundary") or {}).get("metrics"),
                }
            }
            for split, block in (result.get("splits") or {}).items()
        },
        "fixtures": [
            {
                "fixture_id": f.get("fixture_id"),
                "matched_count": f.get("matched_count"),
                "missed_count": f.get("missed_count"),
                "false_positive_count": f.get("false_positive_count"),
                "predicted_bars": f.get("predicted_bars"),
                "reference_bars": f.get("reference_bars"),
                "hold_kind": f.get("hold_kind"),
                "evidence_status": f.get("evidence_status"),
            }
            for f in (result.get("fixtures") or [])
        ],
    }


def run_aq7_structure_boundary_baseline(
    *,
    work_dir: Path | str,
    output_path: Path | str,
    repo_root: Path | str | None = None,
    regenerate_corpus: bool = True,
    prior_semantic: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    work = Path(work_dir)
    out = Path(output_path)

    assert_work_dir_outside_repo(work, root)
    _assert_output_outside_repo(out, root)

    if regenerate_corpus or not (work / "manifest.json").is_file():
        generate_aq7_structure_role_drop_corpus(work, repo_root=root)

    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("corpus_id") != CORPUS_ID:
        raise ValueError("corpus_id mismatch against frozen #1024 identity")
    if manifest.get("corpus_version") != CORPUS_VERSION:
        raise ValueError("corpus_version mismatch against frozen #1024 identity")

    analyzer = StructureV1Analyzer(StructureV1Config())  # default — no retuning
    fixture_rows: list[dict[str, Any]] = []
    for row in manifest["fixtures"]:
        fixture_id = str(row["fixture_id"])
        gt = json.loads((work / "gt" / f"{fixture_id}.json").read_text(encoding="utf-8"))
        audio_path = work / "audio" / f"{fixture_id}.wav"
        fixture_rows.append(
            _predict_fixture(audio_path=audio_path, gt=gt, analyzer=analyzer)
        )

    splits = aggregate_boundary_splits(fixture_rows)
    has_beatgrid_hold = any(
        r.get("hold_kind") == "BEATGRID_PROVENANCE_LIMITATION" for r in fixture_rows
    )
    exit_status = resolve_exit_status(
        splits=splits,
        fixture_rows=fixture_rows,
        has_beatgrid_hold=has_beatgrid_hold,
    )

    runtimes = [float(r["runtime_sec"]) for r in fixture_rows if r.get("runtime_sec") is not None]
    runtime_block = {
        "methodology": "docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md",
        "by_reference": True,
        "track_length_buckets": "HOLD",
        "track_length_buckets_reason": (
            "synthetic 10-fixture pack is too small for meaningful #958 "
            "track-length bucket p95 claims"
        ),
        "per_fixture_runtime_sec_median": (
            float(statistics.median(runtimes)) if runtimes else None
        ),
        "per_fixture_runtime_sec_p95": percentile(runtimes, 95) if runtimes else None,
        "n_timed_fixtures": len(runtimes),
    }

    families: dict[str, list[str]] = {}
    for r in fixture_rows:
        families.setdefault(str(r.get("family") or "unknown"), []).append(
            str(r["fixture_id"])
        )

    result: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "candidate_id": CANDIDATE_ID,
        "analyzer_id": CANDIDATE_ID,
        "corpus_id": CORPUS_ID,
        "corpus_version": CORPUS_VERSION,
        "generator_seed": manifest.get("generator_seed"),
        "plane": PLANE_TOKEN,
        "surfaces": {PLANE_TOKEN: STRUCTURE_SURFACE},
        "structure_v1": {
            "surface": STRUCTURE_SURFACE,
            "config": asdict(StructureV1Config()),
            "algorithm_changed": False,
        },
        "algorithm_changed": False,
        "matching": {
            "tolerance_bars": BOUNDARY_MATCH_TOLERANCE_BARS,
            "policy": "one_to_one_order_preserving_max_matches_then_min_abs_error",
        },
        "partition_policy": dict(PARTITION_POLICY),
        "no_tuning_on_test": True,
        "exit_status": exit_status,
        "fixture_count": len(fixture_rows),
        "families": {k: sorted(v) for k, v in sorted(families.items())},
        "provenance": dict(PROVENANCE),
        "runtime": runtime_block,
        "splits": splits,
        "fixtures": fixture_rows,
    }

    semantic = semantic_projection(result)
    semantic_equal = True if prior_semantic is None else semantic == prior_semantic
    result["determinism"] = {
        "methodology": "docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md",
        "by_reference": True,
        "semantic_equal": semantic_equal,
        "semantic_projection_keys": sorted(semantic.keys()),
    }

    assert_portable_baseline_payload(result)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Measure AQ7 StructureV1 neutral boundary baseline on synthetic "
            "structure/role/drop corpus."
        )
    )
    parser.add_argument(
        "--work-dir",
        required=True,
        help="External directory for generated corpus audio/GT (outside repo).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="External JSON output path (outside repo).",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root used for outside-repo checks (default: package root).",
    )
    parser.add_argument(
        "--no-regenerate",
        action="store_true",
        help="Reuse existing corpus under --work-dir when manifest.json exists.",
    )
    args = parser.parse_args(argv)
    result = run_aq7_structure_boundary_baseline(
        work_dir=args.work_dir,
        output_path=args.output,
        repo_root=args.repo_root,
        regenerate_corpus=not args.no_regenerate,
    )
    print(
        json.dumps(
            {
                "exit_status": result["exit_status"],
                "fixture_count": result["fixture_count"],
                "candidate_id": result["candidate_id"],
            }
        )
    )
    return 0 if result["exit_status"] in {EXIT_MEASURED, EXIT_PARTIAL_HOLD} else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BOUNDARY_MATCH_TOLERANCE_BARS",
    "CANDIDATE_ID",
    "CORPUS_ID",
    "DOCUMENT_TYPE",
    "EXIT_INCOMPLETE",
    "EXIT_MEASURED",
    "EXIT_PARTIAL_HOLD",
    "PLANE_TOKEN",
    "PROVENANCE",
    "SCHEMA_VERSION",
    "STRUCTURE_SURFACE",
    "aggregate_boundary_splits",
    "assert_portable_baseline_payload",
    "error_summary_bars",
    "evaluate_prediction_surface",
    "match_boundaries_1bar",
    "reference_boundaries_from_gt",
    "resolve_exit_status",
    "run_aq7_structure_boundary_baseline",
    "score_fixture_boundaries",
    "semantic_projection",
]
