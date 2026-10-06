"""AQ4 sample_class / pred_type candidate comparison on synthetic corpus (#1034).

Frozen ≤4 thin config adapters over current duration class + rule_type surfaces.
Reuses baseline scoring helpers. No production switch / no TEST tuning / no ML.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import soundfile as sf

from .analyze import extract_features
from .aq4_classification_baseline import (
    DOCUMENT_TYPE as BASELINE_DOCUMENT_TYPE,
    PARTITION_POLICY,
    PRED_TYPE_KNN_SURFACE,
    PRED_TYPE_RULE_SURFACE,
    SAMPLE_CLASS_SURFACE,
    _is_measured,
    aggregate_pred_type_rule,
    aggregate_sample_class,
)
from .aq4_classification_corpus import (
    CORPUS_ID,
    PRED_TYPE_LABELS,
    SAMPLE_CLASS_LABELS,
    assert_work_dir_outside_repo,
    generate_aq4_classification_corpus,
)
from .classify import (
    _RULE_BRIGHT_MIN,
    _RULE_DARK_MAX,
    _RULE_LONG_MIN_SEC,
    _RULE_MID_MAX_SEC,
    _RULE_PUNCHY_MIN_LOUDNESS,
    _RULE_SHORT_MAX_SEC,
    rule_type,
)

DOCUMENT_TYPE = "sample-brain.aq4.classification-candidate-compare.v1"
SCHEMA_VERSION = "1.0.0"
EXIT_REPRODUCIBLE = "AQ4_CLASSIFICATION_CANDIDATE_COMPARE_REPRODUCIBLE"
EXIT_INCOMPLETE = "AQ4_CLASSIFICATION_CANDIDATE_COMPARE_INCOMPLETE"

# Mirrors src.analyze._duration_class production boundary (oneshot if <= 1.2 s).
BASELINE_ONESHOT_MAX_DURATION_SEC = 1.2
BASELINE_SHORT_MAX_SEC = _RULE_SHORT_MAX_SEC
BASELINE_MID_MAX_SEC = _RULE_MID_MAX_SEC
BASELINE_LONG_MIN_SEC = _RULE_LONG_MIN_SEC
BASELINE_BRIGHT_MIN = _RULE_BRIGHT_MIN
BASELINE_DARK_MAX = _RULE_DARK_MAX
BASELINE_PUNCHY_MIN_LOUDNESS = _RULE_PUNCHY_MIN_LOUDNESS

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]


class Aq4ClassificationCandidateCompareError(ValueError):
    """Controlled, fail-closed input or identity error for this compare runner."""


@dataclass(frozen=True)
class ClassificationCandidate:
    candidate_id: str
    oneshot_max_duration_sec: float
    short_max_sec: float
    mid_max_sec: float
    long_min_sec: float
    bright_min: float
    dark_max: float
    punchy_min_loudness: float
    description: str


CLASSIFICATION_CANDIDATES: tuple[ClassificationCandidate, ...] = (
    ClassificationCandidate(
        candidate_id="classification.baseline.v1",
        oneshot_max_duration_sec=BASELINE_ONESHOT_MAX_DURATION_SEC,
        short_max_sec=BASELINE_SHORT_MAX_SEC,
        mid_max_sec=BASELINE_MID_MAX_SEC,
        long_min_sec=BASELINE_LONG_MIN_SEC,
        bright_min=BASELINE_BRIGHT_MIN,
        dark_max=BASELINE_DARK_MAX,
        punchy_min_loudness=BASELINE_PUNCHY_MIN_LOUDNESS,
        description=(
            "Current AQ4 baseline path: duration oneshot_max=1.2 s and production "
            "rule_type thresholds unchanged (matches #1032 surfaces)."
        ),
    ),
    ClassificationCandidate(
        candidate_id="sample_class.oneshot_max.1.0",
        oneshot_max_duration_sec=1.0,
        short_max_sec=BASELINE_SHORT_MAX_SEC,
        mid_max_sec=BASELINE_MID_MAX_SEC,
        long_min_sec=BASELINE_LONG_MIN_SEC,
        bright_min=BASELINE_BRIGHT_MIN,
        dark_max=BASELINE_DARK_MAX,
        punchy_min_loudness=BASELINE_PUNCHY_MIN_LOUDNESS,
        description=(
            "Thin adapter: shorter sample_class oneshot/loop boundary at 1.0 s "
            "(baseline rule_type thresholds unchanged)."
        ),
    ),
    ClassificationCandidate(
        candidate_id="sample_class.oneshot_max.1.5",
        oneshot_max_duration_sec=1.5,
        short_max_sec=BASELINE_SHORT_MAX_SEC,
        mid_max_sec=BASELINE_MID_MAX_SEC,
        long_min_sec=BASELINE_LONG_MIN_SEC,
        bright_min=BASELINE_BRIGHT_MIN,
        dark_max=BASELINE_DARK_MAX,
        punchy_min_loudness=BASELINE_PUNCHY_MIN_LOUDNESS,
        description=(
            "Thin adapter: longer sample_class oneshot/loop boundary at 1.5 s "
            "(baseline rule_type thresholds unchanged)."
        ),
    ),
    ClassificationCandidate(
        candidate_id="pred_type.bright_min.4000",
        oneshot_max_duration_sec=BASELINE_ONESHOT_MAX_DURATION_SEC,
        short_max_sec=BASELINE_SHORT_MAX_SEC,
        mid_max_sec=BASELINE_MID_MAX_SEC,
        long_min_sec=BASELINE_LONG_MIN_SEC,
        bright_min=4000.0,
        dark_max=BASELINE_DARK_MAX,
        punchy_min_loudness=BASELINE_PUNCHY_MIN_LOUDNESS,
        description=(
            "Thin adapter: more sensitive rule_type bright_min=4000 "
            "(baseline sample_class duration and other rule thresholds unchanged)."
        ),
    ),
)


def list_classification_candidates() -> list[ClassificationCandidate]:
    return list(CLASSIFICATION_CANDIDATES)


def candidate_by_id(candidate_id: str) -> ClassificationCandidate:
    for candidate in CLASSIFICATION_CANDIDATES:
        if candidate.candidate_id == candidate_id:
            return candidate
    raise Aq4ClassificationCandidateCompareError(
        f"unknown classification candidate_id: {candidate_id}"
    )


def candidate_public(candidate: ClassificationCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "oneshot_max_duration_sec": candidate.oneshot_max_duration_sec,
        "short_max_sec": candidate.short_max_sec,
        "mid_max_sec": candidate.mid_max_sec,
        "long_min_sec": candidate.long_min_sec,
        "bright_min": candidate.bright_min,
        "dark_max": candidate.dark_max,
        "punchy_min_loudness": candidate.punchy_min_loudness,
        "description": candidate.description,
    }


def duration_class_for_candidate(
    duration: float | None,
    *,
    oneshot_max_duration_sec: float,
) -> str | None:
    """Thin sample_class adapter mirroring analyze._duration_class with a knob."""
    if duration is None:
        return None
    return "oneshot" if duration <= oneshot_max_duration_sec else "loop"


def _wav_duration_sec(path: Path) -> float:
    info = sf.info(str(path))
    if info.samplerate <= 0:
        raise ValueError(f"invalid samplerate for {path.name}")
    return float(info.frames) / float(info.samplerate)


def predict_clip_for_candidate(
    audio_path: Path,
    gt: dict[str, Any],
    candidate: ClassificationCandidate,
) -> dict[str, Any]:
    """Score one corpus clip through a declared candidate config adapter."""
    duration = _wav_duration_sec(audio_path)
    feats = extract_features(audio_path, duration)
    if feats is None:
        return {
            "candidate_id": candidate.candidate_id,
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

    # Baseline candidate uses extract_features.clazz so aggregates match #1032.
    if (
        candidate.oneshot_max_duration_sec
        == BASELINE_ONESHOT_MAX_DURATION_SEC
    ):
        sample_class_pred = feats.clazz
    else:
        sample_class_pred = duration_class_for_candidate(
            duration,
            oneshot_max_duration_sec=candidate.oneshot_max_duration_sec,
        )

    tags = rule_type(
        duration,
        feats.loudness,
        feats.brightness,
        feats.mfcc_mean,
        sample_class_pred,
        short_max_sec=candidate.short_max_sec,
        mid_max_sec=candidate.mid_max_sec,
        long_min_sec=candidate.long_min_sec,
        bright_min=candidate.bright_min,
        dark_max=candidate.dark_max,
        punchy_min_loudness=candidate.punchy_min_loudness,
    )
    pred = tags[0] if tags else None
    return {
        "candidate_id": candidate.candidate_id,
        "clip_id": gt["clip_id"],
        "split": gt["split"],
        "label_status": gt.get("label_status"),
        "sample_class_label": gt.get("sample_class"),
        "sample_class_pred": sample_class_pred,
        "pred_type_label": gt.get("pred_type"),
        "pred_type_rule_pred": pred,
        "duration_sec": duration,
        "loudness": feats.loudness,
        "brightness": feats.brightness,
        "analyze_status": "ok",
    }


def _load_gt(gt_path: Path) -> dict[str, Any]:
    return json.loads(gt_path.read_text(encoding="utf-8"))


def _assert_output_outside_repo(out: Path, root: Path) -> None:
    assert_work_dir_outside_repo(out.parent if out.parent != out else out, root)
    try:
        out.resolve().relative_to(root.resolve())
    except ValueError:
        return
    raise ValueError(f"output path must be outside repo: {out.resolve()}")


def run_aq4_classification_candidate_compare(
    *,
    work_dir: Path | str,
    output_path: Path | str,
    repo_root: Path | str | None = None,
    regenerate_corpus: bool = True,
) -> dict[str, Any]:
    """Generate (optional) corpus, score frozen candidates, write external JSON."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    work = Path(work_dir)
    out = Path(output_path)

    assert_work_dir_outside_repo(work, root)
    _assert_output_outside_repo(out, root)

    if regenerate_corpus or not (work / "manifest.json").is_file():
        generate_aq4_classification_corpus(work, repo_root=root)

    manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
    gt_by_id: dict[str, dict[str, Any]] = {}
    audio_by_id: dict[str, Path] = {}
    for clip in manifest["clips"]:
        clip_id = clip["clip_id"]
        gt_by_id[clip_id] = _load_gt(work / "gt" / f"{clip_id}.json")
        audio_by_id[clip_id] = work / "audio" / f"{clip_id}.wav"

    candidate_entries: list[dict[str, Any]] = []
    all_clip_rows: list[dict[str, Any]] = []
    measured_ok = True

    for candidate in CLASSIFICATION_CANDIDATES:
        clip_rows = [
            predict_clip_for_candidate(audio_by_id[clip_id], gt, candidate)
            for clip_id, gt in gt_by_id.items()
        ]
        all_clip_rows.extend(clip_rows)
        splits: dict[str, Any] = {}
        for split_name in ("CALIBRATION", "TEST"):
            rows = [r for r in clip_rows if r["split"] == split_name]
            splits[split_name] = {
                "clip_count": len(rows),
                "aq4.sample_class": aggregate_sample_class(rows),
                "aq4.pred_type_rule": aggregate_pred_type_rule(rows),
            }
        if not _is_measured(splits, clip_rows):
            measured_ok = False
        candidate_entries.append(
            {
                **candidate_public(candidate),
                "splits": splits,
            }
        )

    knn_hold = {
        "status": "HOLD",
        "reason": (
            "optional kNN override path not measured on synthetic corpus without "
            "seed embeddings / private library paths; report rule-only separately"
        ),
        "surface": PRED_TYPE_KNN_SURFACE,
    }

    result: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
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
        "baseline_document_type": BASELINE_DOCUMENT_TYPE,
        "partition_policy": dict(PARTITION_POLICY),
        "no_tuning_on_test": True,
        "exit_status": EXIT_REPRODUCIBLE if measured_ok else EXIT_INCOMPLETE,
        "candidate_count": len(candidate_entries),
        "clip_count": len(gt_by_id),
        "dataset_health": {
            "support_counts": manifest.get("support_counts") or {},
            "hold_notes": list(manifest.get("hold_notes") or []),
            "uncertain_label_policy": (
                "ambiguous/unknown retained as explicit uncertain; excluded from "
                "clear-label correctness denominators"
            ),
        },
        "aq4.pred_type_knn": knn_hold,
        "candidates": candidate_entries,
        # Per-candidate clip rows stay join-keyed; no host paths.
        "clips": all_clip_rows,
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
            "Compare frozen AQ4 sample_class / pred_type config candidates on "
            "synthetic classification corpus."
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
    result = run_aq4_classification_candidate_compare(
        work_dir=args.work_dir,
        output_path=args.output,
        repo_root=args.repo_root,
        regenerate_corpus=not args.no_regenerate,
    )
    print(
        json.dumps(
            {
                "exit_status": result["exit_status"],
                "candidate_count": result["candidate_count"],
                "clip_count": result["clip_count"],
            }
        )
    )
    return 0 if result["exit_status"] == EXIT_REPRODUCIBLE else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BASELINE_BRIGHT_MIN",
    "BASELINE_DARK_MAX",
    "BASELINE_DOCUMENT_TYPE",
    "BASELINE_LONG_MIN_SEC",
    "BASELINE_MID_MAX_SEC",
    "BASELINE_ONESHOT_MAX_DURATION_SEC",
    "BASELINE_PUNCHY_MIN_LOUDNESS",
    "BASELINE_SHORT_MAX_SEC",
    "CLASSIFICATION_CANDIDATES",
    "CORPUS_ID",
    "DOCUMENT_TYPE",
    "EXIT_INCOMPLETE",
    "EXIT_REPRODUCIBLE",
    "PRED_TYPE_KNN_SURFACE",
    "PRED_TYPE_RULE_SURFACE",
    "SAMPLE_CLASS_SURFACE",
    "SCHEMA_VERSION",
    "Aq4ClassificationCandidateCompareError",
    "ClassificationCandidate",
    "candidate_by_id",
    "candidate_public",
    "duration_class_for_candidate",
    "list_classification_candidates",
    "predict_clip_for_candidate",
    "run_aq4_classification_candidate_compare",
]
