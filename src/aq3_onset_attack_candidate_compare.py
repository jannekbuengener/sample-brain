"""AQ3 onset/attack candidate comparison on synthetic corpus (#997).

Frozen ≤4 thin config adapters over current gesture/attack surfaces.
Reuses baseline scoring helpers. No production switch / no TEST tuning.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .aq3_onset_attack_baseline import (
    ATTACK_SURFACE,
    DOCUMENT_TYPE as BASELINE_DOCUMENT_TYPE,
    ONSET_SURFACE,
    PARTITION_POLICY,
    _aggregate_attack,
    _aggregate_gesture,
    _aggregate_onset,
    _by_bucket,
    _is_measured,
)
from .aq3_timing_corpus import (
    CORPUS_ID,
    HOLD_BUCKETS,
    TOLERANCE_CANDIDATES_MS,
    assert_work_dir_outside_repo,
    generate_aq3_timing_corpus,
)
from .gesture_analysis import (
    _MIN_ONSET_GAP_SEC,
    _ONSET_DELTA,
    _ONSET_WAIT_FRAMES,
    analyze_gesture_audio,
)
from .workbench_attack_suggest import (
    _ENERGY_RATIO_THRESHOLD,
    _FRAME_MS,
    _PEAK_FRACTION_THRESHOLD,
    suggest_attack_ms,
)

DOCUMENT_TYPE = "sample-brain.aq3.onset-attack-candidate-compare.v1"
SCHEMA_VERSION = "1.0.0"
EXIT_REPRODUCIBLE = "AQ3_ONSET_ATTACK_CANDIDATE_COMPARE_REPRODUCIBLE"
EXIT_INCOMPLETE = "AQ3_ONSET_ATTACK_CANDIDATE_COMPARE_INCOMPLETE"

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]


class Aq3OnsetAttackCandidateCompareError(ValueError):
    """Controlled, fail-closed input or identity error for this compare runner."""


@dataclass(frozen=True)
class OnsetAttackCandidate:
    candidate_id: str
    onset_delta: float
    onset_wait_frames: int
    min_onset_gap_sec: float
    attack_energy_ratio: float
    attack_peak_fraction: float
    attack_frame_ms: int
    description: str


ONSET_ATTACK_CANDIDATES: tuple[OnsetAttackCandidate, ...] = (
    OnsetAttackCandidate(
        candidate_id="gesture_attack.baseline.v1",
        onset_delta=_ONSET_DELTA,
        onset_wait_frames=_ONSET_WAIT_FRAMES,
        min_onset_gap_sec=_MIN_ONSET_GAP_SEC,
        attack_energy_ratio=_ENERGY_RATIO_THRESHOLD,
        attack_peak_fraction=_PEAK_FRACTION_THRESHOLD,
        attack_frame_ms=_FRAME_MS,
        description=(
            "Current AQ3 baseline path: gesture onset_delta/wait/gap and attack "
            "energy/peak/frame constants unchanged (matches #995 surfaces)."
        ),
    ),
    OnsetAttackCandidate(
        candidate_id="gesture.onset_delta.0.04",
        onset_delta=0.04,
        onset_wait_frames=_ONSET_WAIT_FRAMES,
        min_onset_gap_sec=_MIN_ONSET_GAP_SEC,
        attack_energy_ratio=_ENERGY_RATIO_THRESHOLD,
        attack_peak_fraction=_PEAK_FRACTION_THRESHOLD,
        attack_frame_ms=_FRAME_MS,
        description=(
            "Thin adapter: more sensitive librosa onset_detect delta=0.04 "
            "(baseline wait/gap and attack path unchanged)."
        ),
    ),
    OnsetAttackCandidate(
        candidate_id="gesture.onset_gap.0.08",
        onset_delta=_ONSET_DELTA,
        onset_wait_frames=_ONSET_WAIT_FRAMES,
        min_onset_gap_sec=0.08,
        attack_energy_ratio=_ENERGY_RATIO_THRESHOLD,
        attack_peak_fraction=_PEAK_FRACTION_THRESHOLD,
        attack_frame_ms=_FRAME_MS,
        description=(
            "Thin adapter: tighter post-filter min onset gap=0.08 s "
            "(baseline delta/wait and attack path unchanged)."
        ),
    ),
    OnsetAttackCandidate(
        candidate_id="attack.energy_ratio.0.10",
        onset_delta=_ONSET_DELTA,
        onset_wait_frames=_ONSET_WAIT_FRAMES,
        min_onset_gap_sec=_MIN_ONSET_GAP_SEC,
        attack_energy_ratio=0.10,
        attack_peak_fraction=_PEAK_FRACTION_THRESHOLD,
        attack_frame_ms=_FRAME_MS,
        description=(
            "Thin adapter: more sensitive attack energy_ratio_threshold=0.10 "
            "(baseline onset path and peak/frame unchanged)."
        ),
    ),
)


def list_onset_attack_candidates() -> list[OnsetAttackCandidate]:
    return list(ONSET_ATTACK_CANDIDATES)


def candidate_by_id(candidate_id: str) -> OnsetAttackCandidate:
    for candidate in ONSET_ATTACK_CANDIDATES:
        if candidate.candidate_id == candidate_id:
            return candidate
    raise Aq3OnsetAttackCandidateCompareError(
        f"unknown onset/attack candidate_id: {candidate_id}"
    )


def candidate_public(candidate: OnsetAttackCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "onset_delta": candidate.onset_delta,
        "onset_wait_frames": candidate.onset_wait_frames,
        "min_onset_gap_sec": candidate.min_onset_gap_sec,
        "attack_energy_ratio": candidate.attack_energy_ratio,
        "attack_peak_fraction": candidate.attack_peak_fraction,
        "attack_frame_ms": candidate.attack_frame_ms,
        "description": candidate.description,
    }


def predict_clip_for_candidate(
    audio_path: Path,
    gt: dict[str, Any],
    candidate: OnsetAttackCandidate,
) -> dict[str, Any]:
    """Score one corpus clip through a declared candidate config adapter."""
    gesture = analyze_gesture_audio(
        audio_path,
        onset_delta=candidate.onset_delta,
        onset_wait_frames=candidate.onset_wait_frames,
        min_onset_gap_sec=candidate.min_onset_gap_sec,
    )
    onset_pred_ms = [
        round(float(ev.onset_time_sec) * 1000.0, 6) for ev in gesture.events
    ]
    attack = suggest_attack_ms(
        audio_path,
        frame_ms=candidate.attack_frame_ms,
        energy_ratio_threshold=candidate.attack_energy_ratio,
        peak_fraction_threshold=candidate.attack_peak_fraction,
    )
    attack_pred = None if attack is None else float(attack.attack_ms)
    attack_confidence = None if attack is None else attack.confidence
    return {
        "candidate_id": candidate.candidate_id,
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


def _assert_output_outside_repo(out: Path, root: Path) -> None:
    assert_work_dir_outside_repo(out.parent if out.parent != out else out, root)
    try:
        out.resolve().relative_to(root.resolve())
    except ValueError:
        return
    raise ValueError(f"output path must be outside repo: {out.resolve()}")


def run_aq3_onset_attack_candidate_compare(
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
        generate_aq3_timing_corpus(work, repo_root=root)

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

    for candidate in ONSET_ATTACK_CANDIDATES:
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
                "aq3.onset": _aggregate_onset(rows),
                "aq3.attack": _aggregate_attack(rows),
                "aq3.gesture": _aggregate_gesture(rows),
                "by_bucket": _by_bucket(rows),
            }
        if not _is_measured(splits, clip_rows):
            measured_ok = False
        candidate_entries.append(
            {
                **candidate_public(candidate),
                "splits": splits,
            }
        )

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
        "baseline_document_type": BASELINE_DOCUMENT_TYPE,
        "partition_policy": dict(PARTITION_POLICY),
        "no_tuning_on_test": True,
        "exit_status": EXIT_REPRODUCIBLE if measured_ok else EXIT_INCOMPLETE,
        "candidate_count": len(candidate_entries),
        "clip_count": len(gt_by_id),
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
            "Compare frozen AQ3 onset/attack config candidates on synthetic "
            "timing corpus."
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
    result = run_aq3_onset_attack_candidate_compare(
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
    "ATTACK_SURFACE",
    "BASELINE_DOCUMENT_TYPE",
    "CORPUS_ID",
    "DOCUMENT_TYPE",
    "EXIT_INCOMPLETE",
    "EXIT_REPRODUCIBLE",
    "ONSET_ATTACK_CANDIDATES",
    "ONSET_SURFACE",
    "SCHEMA_VERSION",
    "TOLERANCE_CANDIDATES_MS",
    "Aq3OnsetAttackCandidateCompareError",
    "OnsetAttackCandidate",
    "candidate_by_id",
    "candidate_public",
    "list_onset_attack_candidates",
    "predict_clip_for_candidate",
    "run_aq3_onset_attack_candidate_compare",
]
