"""AQ4 sample_class / pred_type baseline on synthetic corpus (#1032 / #1003).

Measures current duration-derived ``sample_class`` and rule ``pred_type``
against frozen AQ4 KPI on ``sample-brain.aq4.classification.synthetic.v1``.
Taxonomies stay separate. No algorithm changes. External JSON only.
Residual #1003 acceptance aligns candidate_id, PARTIAL_HOLD exit mapping,
and portable provenance without rebuilding the harness.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import soundfile as sf

from .analyze import extract_features
from .aq4_classification_corpus import (
    CORPUS_ID,
    PRED_TYPE_LABELS,
    SAMPLE_CLASS_LABELS,
    assert_work_dir_outside_repo,
    generate_aq4_classification_corpus,
)
from .classify import rule_type

DOCUMENT_TYPE = "sample-brain.aq4.classification-baseline.v1"
SCHEMA_VERSION = "1.0.0"
CANDIDATE_ID = "classification.baseline.v1"
EXIT_MEASURED = "AQ4_CLASSIFICATION_BASELINE_MEASURED"
EXIT_PARTIAL_HOLD = "AQ4_CLASSIFICATION_BASELINE_PARTIAL_HOLD"
EXIT_INCOMPLETE = "AQ4_CLASSIFICATION_BASELINE_INCOMPLETE"
SAMPLE_CLASS_SURFACE = "src.analyze.extract_features.clazz"
PRED_TYPE_RULE_SURFACE = "src.classify.rule_type"
PRED_TYPE_KNN_SURFACE = "src.classify.write_autotype_to_db(use_knn=True)"

# Portable by-reference provenance — no absolute host paths.
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
        "issue": "#1001",
        "doc": "docs/benchmarks/AQ4_CLASSIFICATION_KPI_CONTRACT.md",
        "by_reference": True,
    },
    "corpus": {
        "issue": "#1021",
        "doc": "docs/benchmarks/AQ4_CLASSIFICATION_CORPUS.md",
        "by_reference": True,
    },
}

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]

PARTITION_POLICY = {
    "CALIBRATION": "DEVELOPMENT/CALIBRATION",
    "TEST": "TEST/HOLDOUT",
}

_CLEAR_SAMPLE_CLASS = frozenset({"oneshot", "loop"})
_CLEAR_PRED_TYPE = frozenset(label for label in PRED_TYPE_LABELS if label != "unknown")


def score_multiclass(
    y_true: list[str],
    y_pred: list[str],
    *,
    labels: list[str],
) -> dict[str, Any]:
    """Per-class P/R/F1, macro-F1, balanced accuracy, confusion with denominators."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred length mismatch")

    support = Counter(y_true)
    confusion: dict[str, dict[str, int]] = {
        lab: {col: 0 for col in labels} for lab in labels
    }
    for truth, pred in zip(y_true, y_pred, strict=True):
        if truth in confusion and pred in confusion[truth]:
            confusion[truth][pred] += 1
        elif truth in confusion:
            # Predicted label outside eligible set — still count as miss row.
            confusion[truth].setdefault(pred, 0)
            confusion[truth][pred] += 1

    per_class: dict[str, Any] = {}
    f1_values: list[float] = []
    recall_values: list[float] = []
    for lab in labels:
        tp = sum(
            1
            for t, p in zip(y_true, y_pred, strict=True)
            if t == lab and p == lab
        )
        fp = sum(
            1
            for t, p in zip(y_true, y_pred, strict=True)
            if p == lab and t != lab
        )
        fn = sum(
            1
            for t, p in zip(y_true, y_pred, strict=True)
            if t == lab and p != lab
        )
        precision = (tp / (tp + fp)) if (tp + fp) else 0.0
        recall = (tp / (tp + fn)) if (tp + fn) else 0.0
        f1 = (
            (2.0 * precision * recall / (precision + recall))
            if (precision + recall) > 0.0
            else 0.0
        )
        per_class[lab] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "support": int(support.get(lab, 0)),
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
        f1_values.append(f1)
        recall_values.append(recall)

    macro_f1 = (sum(f1_values) / len(f1_values)) if f1_values else 0.0
    balanced_accuracy = (
        (sum(recall_values) / len(recall_values)) if recall_values else 0.0
    )
    return {
        "n_eligible": len(y_true),
        "labels": list(labels),
        "support": {lab: int(support.get(lab, 0)) for lab in labels},
        "per_class": per_class,
        "macro_f1": macro_f1,
        "balanced_accuracy": balanced_accuracy,
        "confusion": confusion,
    }


def _is_clear_sample_class_eligible(row: dict[str, Any]) -> bool:
    return (
        row.get("label_status") == "clear"
        and row.get("sample_class_label") in _CLEAR_SAMPLE_CLASS
    )


def _is_clear_pred_type_eligible(row: dict[str, Any]) -> bool:
    return (
        row.get("label_status") == "clear"
        and row.get("pred_type_label") in _CLEAR_PRED_TYPE
    )


def aggregate_sample_class(clip_rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [r for r in clip_rows if _is_clear_sample_class_eligible(r)]
    uncertain = [
        r
        for r in clip_rows
        if r.get("label_status") in {"ambiguous", "unknown"}
        or r.get("sample_class_label") in {"ambiguous", "unknown"}
    ]
    labels_present = sorted(
        {
            str(r["sample_class_label"])
            for r in eligible
            if r.get("sample_class_label") in _CLEAR_SAMPLE_CLASS
        }
    )
    # Always report both structural labels when any clear eligibility exists;
    # otherwise keep empty metrics with explicit zeros.
    labels = labels_present or ["oneshot", "loop"]
    if eligible:
        metrics = score_multiclass(
            [str(r["sample_class_label"]) for r in eligible],
            [str(r["sample_class_pred"]) for r in eligible],
            labels=labels,
        )
    else:
        metrics = score_multiclass([], [], labels=labels)

    # Coverage: current surface always emits loop/oneshot (never abstains).
    predicted_n = sum(1 for r in clip_rows if r.get("sample_class_pred") is not None)
    return {
        "clip_count": len(clip_rows),
        "n_clear_eligible": len(eligible),
        "n_uncertain": len(uncertain),
        "uncertain_clip_ids": [r["clip_id"] for r in uncertain],
        "coverage_rate": (predicted_n / len(clip_rows)) if clip_rows else None,
        "abstention_rate": (
            (len(clip_rows) - predicted_n) / len(clip_rows) if clip_rows else None
        ),
        "metrics": metrics,
    }


def aggregate_pred_type_rule(clip_rows: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [r for r in clip_rows if _is_clear_pred_type_eligible(r)]
    uncertain = [
        r
        for r in clip_rows
        if r.get("label_status") in {"ambiguous", "unknown"}
        or r.get("pred_type_label") == "unknown"
    ]
    labels = sorted(
        {
            str(r["pred_type_label"])
            for r in eligible
            if r.get("pred_type_label") in _CLEAR_PRED_TYPE
        }
    )
    if eligible and labels:
        metrics = score_multiclass(
            [str(r["pred_type_label"]) for r in eligible],
            [str(r["pred_type_rule_pred"]) for r in eligible],
            labels=labels,
        )
    else:
        metrics = score_multiclass([], [], labels=labels or ["FX"])

    predicted_n = sum(1 for r in clip_rows if r.get("pred_type_rule_pred") is not None)
    return {
        "clip_count": len(clip_rows),
        "n_clear_eligible": len(eligible),
        "n_uncertain": len(uncertain),
        "uncertain_clip_ids": [r["clip_id"] for r in uncertain],
        "coverage_rate": (predicted_n / len(clip_rows)) if clip_rows else None,
        "abstention_rate": (
            (len(clip_rows) - predicted_n) / len(clip_rows) if clip_rows else None
        ),
        "metrics": metrics,
    }


def _wav_duration_sec(path: Path) -> float:
    info = sf.info(str(path))
    if info.samplerate <= 0:
        raise ValueError(f"invalid samplerate for {path.name}")
    return float(info.frames) / float(info.samplerate)


def _predict_clip(audio_path: Path, gt: dict[str, Any]) -> dict[str, Any]:
    duration = _wav_duration_sec(audio_path)
    feats = extract_features(audio_path, duration)
    if feats is None:
        return {
            "clip_id": gt["clip_id"],
            "split": gt["split"],
            "label_status": gt.get("label_status"),
            "sample_class_label": gt.get("sample_class"),
            "sample_class_pred": None,
            "pred_type_label": gt.get("pred_type"),
            "pred_type_rule_pred": None,
            "duration_sec": duration,
            "analyze_status": "extract_features_failed",
        }

    tags = rule_type(
        duration,
        feats.loudness,
        feats.brightness,
        feats.mfcc_mean,
        feats.clazz,
    )
    pred = tags[0] if tags else None
    return {
        "clip_id": gt["clip_id"],
        "split": gt["split"],
        "label_status": gt.get("label_status"),
        "sample_class_label": gt.get("sample_class"),
        "sample_class_pred": feats.clazz,
        "pred_type_label": gt.get("pred_type"),
        "pred_type_rule_pred": pred,
        "duration_sec": duration,
        "loudness": feats.loudness,
        "brightness": feats.brightness,
        "analyze_status": "ok",
    }


def _load_gt(gt_path: Path) -> dict[str, Any]:
    return json.loads(gt_path.read_text(encoding="utf-8"))


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


def _plane_measurable_across_splits(
    splits: dict[str, Any],
    plane_key: str,
) -> bool:
    """True when a mandatory plane scores on both CALIBRATION and TEST."""
    for split_name in ("CALIBRATION", "TEST"):
        split = splits.get(split_name) or {}
        plane = split.get(plane_key) or {}
        if "metrics" not in plane:
            return False
        if plane.get("n_clear_eligible", 0) < 1:
            return False
        if "macro_f1" not in (plane.get("metrics") or {}):
            return False
    return True


def resolve_exit_status(
    *,
    splits: dict[str, Any],
    clip_rows: list[dict[str, Any]],
) -> str:
    """Map mandatory-plane measurability to MEASURED / PARTIAL_HOLD / INCOMPLETE.

    Optional kNN HOLD is intentionally ignored: it must not degrade MEASURED
    when both ``aq4.sample_class`` and ``aq4.pred_type_rule`` are measurable.
    """
    if len(clip_rows) < 8:
        return EXIT_INCOMPLETE
    sample_class_ok = _plane_measurable_across_splits(splits, "aq4.sample_class")
    pred_type_ok = _plane_measurable_across_splits(splits, "aq4.pred_type_rule")
    if sample_class_ok and pred_type_ok:
        return EXIT_MEASURED
    if sample_class_ok != pred_type_ok:
        return EXIT_PARTIAL_HOLD
    return EXIT_INCOMPLETE


def _is_measured(splits: dict[str, Any], clip_rows: list[dict[str, Any]]) -> bool:
    """Compatibility shim for candidate-compare (#1034): both mandatory planes ok."""
    return (
        resolve_exit_status(splits=splits, clip_rows=clip_rows) == EXIT_MEASURED
    )


def run_aq4_classification_baseline(
    *,
    work_dir: Path | str,
    output_path: Path | str,
    repo_root: Path | str | None = None,
    regenerate_corpus: bool = True,
) -> dict[str, Any]:
    """Generate (optional) corpus, score current classifiers, write external JSON."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    work = Path(work_dir)
    out = Path(output_path)

    assert_work_dir_outside_repo(work, root)
    _assert_output_outside_repo(out, root)

    if regenerate_corpus or not (work / "manifest.json").is_file():
        generate_aq4_classification_corpus(work, repo_root=root)

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
            "aq4.sample_class": aggregate_sample_class(rows),
            "aq4.pred_type_rule": aggregate_pred_type_rule(rows),
        }

    knn_hold = {
        "status": "HOLD",
        "reason": (
            "optional kNN override path not measured on synthetic corpus without "
            "seed embeddings / private library paths; report rule-only separately"
        ),
        "surface": PRED_TYPE_KNN_SURFACE,
    }

    exit_status = resolve_exit_status(splits=splits, clip_rows=clip_rows)
    result: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "candidate_id": CANDIDATE_ID,
        "corpus_id": CORPUS_ID,
        "corpus_version": manifest.get("corpus_version"),
        "generator_seed": manifest.get("generator_seed"),
        "sample_class_labels": list(SAMPLE_CLASS_LABELS),
        "pred_type_labels": list(PRED_TYPE_LABELS),
        "surfaces": {
            "aq4.sample_class": SAMPLE_CLASS_SURFACE,
            "aq4.pred_type_rule": PRED_TYPE_RULE_SURFACE,
            "aq4.pred_type_knn": PRED_TYPE_KNN_SURFACE,
        },
        "plane_identities": {
            "aq4.sample_class": CANDIDATE_ID,
            "aq4.pred_type_rule": CANDIDATE_ID,
        },
        "partition_policy": dict(PARTITION_POLICY),
        "no_tuning_on_test": True,
        "exit_status": exit_status,
        "clip_count": len(clip_rows),
        "dataset_health": {
            "support_counts": manifest.get("support_counts") or {},
            "hold_notes": list(manifest.get("hold_notes") or []),
            "uncertain_label_policy": (
                "ambiguous/unknown retained as explicit uncertain; excluded from "
                "clear-label correctness denominators"
            ),
        },
        "provenance": dict(PROVENANCE),
        "aq4.pred_type_knn": knn_hold,
        "splits": splits,
        "clips": clip_rows,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Measure AQ4 sample_class / pred_type baseline on synthetic "
            "classification corpus."
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
    result = run_aq4_classification_baseline(
        work_dir=args.work_dir,
        output_path=args.output,
        repo_root=args.repo_root,
        regenerate_corpus=not args.no_regenerate,
    )
    print(
        json.dumps(
            {
                "exit_status": result["exit_status"],
                "clip_count": result["clip_count"],
            }
        )
    )
    return 0 if result["exit_status"] == EXIT_MEASURED else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CANDIDATE_ID",
    "CORPUS_ID",
    "DOCUMENT_TYPE",
    "EXIT_INCOMPLETE",
    "EXIT_MEASURED",
    "EXIT_PARTIAL_HOLD",
    "PRED_TYPE_KNN_SURFACE",
    "PRED_TYPE_RULE_SURFACE",
    "PROVENANCE",
    "SAMPLE_CLASS_SURFACE",
    "SCHEMA_VERSION",
    "aggregate_pred_type_rule",
    "aggregate_sample_class",
    "resolve_exit_status",
    "run_aq4_classification_baseline",
    "score_multiclass",
]
