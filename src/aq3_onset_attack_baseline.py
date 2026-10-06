"""AQ3 onset/attack timing baseline on synthetic corpus (#995).

Measures current detector surfaces against frozen corpus GT.
No algorithm changes. External JSON only.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

from .aq3_timing_corpus import (
    CORPUS_ID,
    HOLD_BUCKETS,
    TOLERANCE_CANDIDATES_MS,
    assert_work_dir_outside_repo,
    generate_aq3_timing_corpus,
)
from .gesture_analysis import analyze_gesture_audio
from .workbench_attack_suggest import suggest_attack_ms

DOCUMENT_TYPE = "sample-brain.aq3.onset-attack-baseline.v1"
SCHEMA_VERSION = "1.0.0"
EXIT_MEASURED = "AQ3_ONSET_ATTACK_BASELINE_MEASURED"
EXIT_INCOMPLETE = "AQ3_ONSET_ATTACK_BASELINE_INCOMPLETE"
ONSET_SURFACE = "src.gesture_analysis.analyze_gesture_audio"
ATTACK_SURFACE = "src.workbench_attack_suggest.suggest_attack_ms"

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]

PARTITION_POLICY = {
    "CALIBRATION": "DEVELOPMENT/CALIBRATION",
    "TEST": "TEST/HOLDOUT",
}


def match_onsets(
    predicted_ms: list[float],
    label_ms: list[float],
    *,
    tolerance_ms: float,
) -> tuple[list[tuple[float, float]], list[float], list[float]]:
    """Greedy 1:1 nearest matching within *tolerance_ms*.

    Returns ``(matched_pairs, missed_labels, unmatched_predictions)``.
    Each matched pair is ``(pred_ms, label_ms)``.
    """
    preds = sorted(float(x) for x in predicted_ms)
    labels = sorted(float(x) for x in label_ms)
    used_pred: set[int] = set()
    matched: list[tuple[float, float]] = []
    missed: list[float] = []

    for label in labels:
        best_i: int | None = None
        best_err = float("inf")
        for i, pred in enumerate(preds):
            if i in used_pred:
                continue
            err = abs(pred - label)
            if err <= tolerance_ms and err < best_err:
                best_err = err
                best_i = i
        if best_i is None:
            missed.append(label)
            continue
        used_pred.add(best_i)
        matched.append((preds[best_i], label))

    extras = [pred for i, pred in enumerate(preds) if i not in used_pred]
    return matched, missed, extras


def score_onset_metrics(
    predicted_ms: list[float],
    label_ms: list[float],
    *,
    tolerance_ms: int | float,
) -> dict[str, Any]:
    matched, missed, extras = match_onsets(
        predicted_ms, label_ms, tolerance_ms=float(tolerance_ms)
    )
    label_count = len(label_ms)
    pred_count = len(predicted_ms)
    matched_n = len(matched)
    precision = (matched_n / pred_count) if pred_count else 0.0
    recall = (matched_n / label_count) if label_count else 0.0
    if precision + recall > 0.0:
        f1 = 2.0 * precision * recall / (precision + recall)
    else:
        f1 = 0.0
    abs_errors = [abs(p - l) for p, l in matched]
    return {
        "tolerance_ms": int(tolerance_ms),
        "label_count": label_count,
        "pred_count": pred_count,
        "matched": matched_n,
        "missed": len(missed),
        "duplicates": len(extras),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "missed_onset_rate": (len(missed) / label_count) if label_count else 0.0,
        "duplicate_onset_rate": (len(extras) / pred_count) if pred_count else 0.0,
        "abs_error_ms": _error_summary(abs_errors),
    }


def score_attack_metrics(
    *,
    predicted_ms: float | None,
    label_ms: float | None,
    tolerances_ms: tuple[int, ...] = TOLERANCE_CANDIDATES_MS,
) -> dict[str, Any]:
    if label_ms is None:
        return {
            "eligible": False,
            "predicted": False,
            "abs_error_ms": None,
            "signed_error_ms": None,
            "within_tolerance": {str(t): None for t in tolerances_ms},
            "early": False,
            "late": False,
        }
    if predicted_ms is None:
        return {
            "eligible": True,
            "predicted": False,
            "abs_error_ms": None,
            "signed_error_ms": None,
            "within_tolerance": {str(t): False for t in tolerances_ms},
            "early": False,
            "late": False,
        }
    signed = float(predicted_ms) - float(label_ms)
    abs_err = abs(signed)
    return {
        "eligible": True,
        "predicted": True,
        "abs_error_ms": abs_err,
        "signed_error_ms": signed,
        "within_tolerance": {str(t): abs_err <= float(t) for t in tolerances_ms},
        "early": signed < 0.0,
        "late": signed > 0.0,
    }


def _error_summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "median": None, "p95": None, "n": 0}
    ordered = sorted(values)
    n = len(ordered)
    # Nearest-rank p95 (inclusive).
    p95_index = min(n - 1, max(0, int(math.ceil(0.95 * n) - 1)))
    return {
        "mean": float(statistics.fmean(ordered)),
        "median": float(statistics.median(ordered)),
        "p95": float(ordered[p95_index]),
        "n": n,
    }


def _safe_rate(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return num / den


def _aggregate_onset(
    clip_rows: list[dict[str, Any]],
    *,
    tolerances_ms: tuple[int, ...] = TOLERANCE_CANDIDATES_MS,
) -> dict[str, Any]:
    usable_clips = 0
    empty_clips = 0
    for row in clip_rows:
        preds = list(row["onset_times_ms_pred"])
        status = row.get("gesture_status")
        if status in {"empty", "too_short", "unreadable"} and not preds:
            empty_clips += 1
        else:
            usable_clips += 1

    by_tol: dict[str, Any] = {}
    for tol in tolerances_ms:
        # Micro-average across clips: pool matched/missed/extras.
        matched_n = 0
        missed_n = 0
        dup_n = 0
        label_n = 0
        pred_n = 0
        abs_errors: list[float] = []
        event_count_abs: list[float] = []
        for row in clip_rows:
            labels = list(row["onset_times_ms_label"])
            preds = list(row["onset_times_ms_pred"])
            block = score_onset_metrics(preds, labels, tolerance_ms=tol)
            matched_n += int(block["matched"])
            missed_n += int(block["missed"])
            dup_n += int(block["duplicates"])
            label_n += int(block["label_count"])
            pred_n += int(block["pred_count"])
            pairs, _, _ = match_onsets(preds, labels, tolerance_ms=float(tol))
            abs_errors.extend(abs(p - l) for p, l in pairs)
            event_count_abs.append(abs(len(preds) - len(labels)))
        precision = (matched_n / pred_n) if pred_n else 0.0
        recall = (matched_n / label_n) if label_n else 0.0
        f1 = (
            (2.0 * precision * recall / (precision + recall))
            if (precision + recall) > 0.0
            else 0.0
        )
        by_tol[str(tol)] = {
            "tolerance_ms": tol,
            "label_count": label_n,
            "pred_count": pred_n,
            "matched": matched_n,
            "missed": missed_n,
            "duplicates": dup_n,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "missed_onset_rate": (missed_n / label_n) if label_n else 0.0,
            "duplicate_onset_rate": (dup_n / pred_n) if pred_n else 0.0,
            "abs_error_ms": _error_summary(abs_errors),
            "event_count_abs_error": _error_summary(event_count_abs),
        }
    clip_n = len(clip_rows)
    return {
        "clip_count": clip_n,
        "usable_detection_clips": usable_clips,
        "no_result_clip_count": empty_clips,
        "no_result_rate": _safe_rate(empty_clips, clip_n),
        "by_tolerance": by_tol,
    }


def _aggregate_attack(
    clip_rows: list[dict[str, Any]],
    *,
    tolerances_ms: tuple[int, ...] = TOLERANCE_CANDIDATES_MS,
) -> dict[str, Any]:
    eligible = 0
    predicted = 0
    early_n = 0
    late_n = 0
    abs_errors: list[float] = []
    within_hits = {str(t): 0 for t in tolerances_ms}
    for row in clip_rows:
        metrics = score_attack_metrics(
            predicted_ms=row.get("attack_ms_pred"),
            label_ms=row.get("attack_marker_ms_label"),
            tolerances_ms=tolerances_ms,
        )
        if not metrics["eligible"]:
            continue
        eligible += 1
        if metrics["predicted"]:
            predicted += 1
            abs_errors.append(float(metrics["abs_error_ms"]))
            if metrics["early"]:
                early_n += 1
            if metrics["late"]:
                late_n += 1
            for t in tolerances_ms:
                if metrics["within_tolerance"][str(t)]:
                    within_hits[str(t)] += 1
    return {
        "eligible": eligible,
        "predicted": predicted,
        "coverage_rate": _safe_rate(predicted, eligible),
        "abstention_rate": _safe_rate(eligible - predicted, eligible),
        "within_tolerance_rates": {
            str(t): _safe_rate(within_hits[str(t)], eligible) for t in tolerances_ms
        },
        "early_rate": _safe_rate(early_n, predicted),
        "late_rate": _safe_rate(late_n, predicted),
        "abs_error_ms": _error_summary(abs_errors),
    }


def _aggregate_gesture(
    clip_rows: list[dict[str, Any]],
    *,
    tolerances_ms: tuple[int, ...] = TOLERANCE_CANDIDATES_MS,
) -> dict[str, Any]:
    """Partial gesture plane: IOI error on multi-onset clips when present."""
    multi = [
        row
        for row in clip_rows
        if len(row.get("onset_times_ms_label") or []) >= 2
    ]
    if not multi:
        return {
            "status": "HOLD",
            "reason": "no multi-onset clips in this split",
            "multi_onset_clip_count": 0,
            "by_tolerance": {},
        }

    by_tol: dict[str, Any] = {}
    for tol in tolerances_ms:
        ioi_abs: list[float] = []
        order_breaks = 0
        comparable_intervals = 0
        for row in multi:
            labels = list(row["onset_times_ms_label"])
            preds = list(row["onset_times_ms_pred"])
            matched, _, _ = match_onsets(preds, labels, tolerance_ms=float(tol))
            # Order preservation on matched label sequence vs prediction order.
            matched_sorted_by_label = sorted(matched, key=lambda pair: pair[1])
            pred_order = [p for p, _ in matched_sorted_by_label]
            if pred_order != sorted(pred_order):
                order_breaks += 1
            if len(matched_sorted_by_label) < 2:
                continue
            label_ioi = [
                matched_sorted_by_label[i + 1][1] - matched_sorted_by_label[i][1]
                for i in range(len(matched_sorted_by_label) - 1)
            ]
            pred_ioi = [
                matched_sorted_by_label[i + 1][0] - matched_sorted_by_label[i][0]
                for i in range(len(matched_sorted_by_label) - 1)
            ]
            for li, pi in zip(label_ioi, pred_ioi, strict=True):
                comparable_intervals += 1
                ioi_abs.append(abs(pi - li))
        by_tol[str(tol)] = {
            "tolerance_ms": tol,
            "comparable_intervals": comparable_intervals,
            "ioi_abs_error_ms": _error_summary(ioi_abs),
            "order_break_clips": order_breaks,
            "order_break_rate": _safe_rate(order_breaks, len(multi)),
        }

    status = "PARTIAL" if len(multi) < 2 else "MEASURED"
    return {
        "status": status,
        "reason": (
            "thin multi-onset coverage; IOI/order reported where matched"
            if status == "PARTIAL"
            else "multi-onset IOI/order measured"
        ),
        "multi_onset_clip_count": len(multi),
        "by_tolerance": by_tol,
    }


def _predict_clip(audio_path: Path, gt: dict[str, Any]) -> dict[str, Any]:
    gesture = analyze_gesture_audio(audio_path)
    onset_pred_ms = [
        round(float(ev.onset_time_sec) * 1000.0, 6) for ev in gesture.events
    ]
    attack = suggest_attack_ms(audio_path)
    attack_pred = None if attack is None else float(attack.attack_ms)
    attack_confidence = None if attack is None else attack.confidence
    return {
        "clip_id": gt["clip_id"],
        "split": gt["split"],
        "buckets": list(gt.get("buckets") or []),
        "onset_times_ms_label": [float(x) for x in gt.get("onset_times_ms") or []],
        "onset_times_ms_pred": onset_pred_ms,
        "attack_marker_ms_label": (
            None
            if gt.get("attack_marker_ms") is None
            else float(gt["attack_marker_ms"])
        ),
        "attack_ms_pred": attack_pred,
        "attack_confidence": attack_confidence,
        "gesture_status": gesture.status,
        "gesture_event_count": len(gesture.events),
        "duration_ms_label": float(gt.get("duration_ms") or 0.0),
    }


def _load_gt(gt_path: Path) -> dict[str, Any]:
    return json.loads(gt_path.read_text(encoding="utf-8"))


def run_aq3_onset_attack_baseline(
    *,
    work_dir: Path | str,
    output_path: Path | str,
    repo_root: Path | str | None = None,
    regenerate_corpus: bool = True,
) -> dict[str, Any]:
    """Generate (optional) corpus, score current detectors, write external JSON."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    work = Path(work_dir)
    out = Path(output_path)

    assert_work_dir_outside_repo(work, root)
    assert_work_dir_outside_repo(out.parent if out.parent != out else out, root)
    # Also reject the output file itself when it resolves under the repo.
    try:
        out.resolve().relative_to(root.resolve())
    except ValueError:
        pass
    else:
        raise ValueError(f"output path must be outside repo: {out.resolve()}")

    if regenerate_corpus or not (work / "manifest.json").is_file():
        generate_aq3_timing_corpus(work, repo_root=root)

    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    clip_rows: list[dict[str, Any]] = []
    for clip in manifest["clips"]:
        clip_id = clip["clip_id"]
        gt = _load_gt(work / "gt" / f"{clip_id}.json")
        audio_path = work / "audio" / f"{clip_id}.wav"
        clip_rows.append(_predict_clip(audio_path, gt))

    splits: dict[str, Any] = {}
    for split_name in ("CALIBRATION", "TEST"):
        rows = [r for r in clip_rows if r["split"] == split_name]
        splits[split_name] = {
            "clip_count": len(rows),
            "aq3.onset": _aggregate_onset(rows),
            "aq3.attack": _aggregate_attack(rows),
            "aq3.gesture": _aggregate_gesture(rows),
            "by_bucket": _by_bucket(rows),
        }

    measured = _is_measured(splits, clip_rows)
    result: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "corpus_id": CORPUS_ID,
        "corpus_version": manifest.get("corpus_version"),
        "generator_seed": manifest.get("generator_seed"),
        "tolerance_candidates_ms": list(TOLERANCE_CANDIDATES_MS),
        "hold_buckets": list(HOLD_BUCKETS),
        "surfaces": {
            "aq3.onset": ONSET_SURFACE,
            "aq3.attack": ATTACK_SURFACE,
            "aq3.gesture": ONSET_SURFACE,
        },
        "partition_policy": dict(PARTITION_POLICY),
        "no_tuning_on_test": True,
        "exit_status": EXIT_MEASURED if measured else EXIT_INCOMPLETE,
        "clip_count": len(clip_rows),
        "splits": splits,
        "clips": clip_rows,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def _by_bucket(clip_rows: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in clip_rows:
        for bucket in row.get("buckets") or []:
            buckets.setdefault(str(bucket), []).append(row)
    out: dict[str, Any] = {}
    for name, rows in sorted(buckets.items()):
        out[name] = {
            "clip_count": len(rows),
            "aq3.onset": _aggregate_onset(rows),
            "aq3.attack": _aggregate_attack(rows),
        }
    # HOLD stubs remain documented even when empty.
    for hold in HOLD_BUCKETS:
        out.setdefault(
            hold,
            {
                "clip_count": 0,
                "status": "HOLD",
                "reason": "no synthetic GT clip in corpus v1",
            },
        )
    return out


def _is_measured(splits: dict[str, Any], clip_rows: list[dict[str, Any]]) -> bool:
    if len(clip_rows) < 4:
        return False
    for split_name in ("CALIBRATION", "TEST"):
        split = splits.get(split_name) or {}
        onset = split.get("aq3.onset") or {}
        by_tol = onset.get("by_tolerance") or {}
        if not by_tol:
            return False
        attack = split.get("aq3.attack") or {}
        if "within_tolerance_rates" not in attack:
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure AQ3 onset/attack baseline on synthetic timing corpus."
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
    result = run_aq3_onset_attack_baseline(
        work_dir=args.work_dir,
        output_path=args.output,
        repo_root=args.repo_root,
        regenerate_corpus=not args.no_regenerate,
    )
    print(json.dumps({"exit_status": result["exit_status"], "clip_count": result["clip_count"]}))
    return 0 if result["exit_status"] == EXIT_MEASURED else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ATTACK_SURFACE",
    "CORPUS_ID",
    "DOCUMENT_TYPE",
    "EXIT_INCOMPLETE",
    "EXIT_MEASURED",
    "ONSET_SURFACE",
    "SCHEMA_VERSION",
    "TOLERANCE_CANDIDATES_MS",
    "match_onsets",
    "run_aq3_onset_attack_baseline",
    "score_attack_metrics",
    "score_onset_metrics",
]
