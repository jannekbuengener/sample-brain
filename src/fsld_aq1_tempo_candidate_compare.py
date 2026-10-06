"""Reproducible AQ1 tempo candidate comparison on the frozen FSLD Human split.

Thin adapters over the current analyzer BPM path (`extract_features` +
`normalize_bpm`). Reuses ``_tempo_metrics`` from ``fsld_current_analyzer_eval``.
Does not change production defaults or invent promotion thresholds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .analyze import normalize_bpm
from .fsld_current_analyzer_eval import (
    DEFAULT_MANIFEST_PATH,
    DEFAULT_SHA256_PATH,
    EVALUATED_RUN_STATUS,
    PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY,
    REPOSITORY_ROOT,
    _analyze_record,
    _canonical_result_bytes,
    _load_verified_manifest,
    _path_is_within,
    _record_key,
    _runtime_libraries,
    _tempo_metrics,
)
from .fsld_human_manifest import canonical_manifest_bytes


DOCUMENT_TYPE = "sample_brain.fsld_aq1_tempo_candidate_compare"
SCHEMA_VERSION = "1.0.0"
ANALYZER_ID = "sample_brain.analyze.extract_features"
BEAT_GRID_STATUS = "HOLD"
BASELINE_EVAL_DOCUMENT_TYPE = "sample_brain.fsld_current_analyzer_eval"


class FsldAq1TempoCandidateCompareError(ValueError):
    """Controlled, fail-closed input or output error for this compare runner."""


@dataclass(frozen=True)
class TempoCandidate:
    candidate_id: str
    bpm_normalization: str
    description: str
    analyzer_id: str = ANALYZER_ID


TEMPO_CANDIDATES: tuple[TempoCandidate, ...] = (
    TempoCandidate(
        candidate_id="extract_features.bpm_normalization.none",
        bpm_normalization="none",
        description=(
            "Current AQ1 baseline path: raw librosa beat_track BPM with "
            "bpm_normalization=none (half/double visible via classify_bpm_error)."
        ),
    ),
    TempoCandidate(
        candidate_id="extract_features.bpm_normalization.heuristic",
        bpm_normalization="heuristic",
        description=(
            "Thin adapter: same raw BPM, then analyze.normalize_bpm mode=heuristic."
        ),
    ),
    TempoCandidate(
        candidate_id="extract_features.bpm_normalization.domain_110_170",
        bpm_normalization="domain_110_170",
        description=(
            "Thin adapter: same raw BPM, then analyze.normalize_bpm "
            "mode=domain_110_170 (#872)."
        ),
    ),
)


def list_tempo_candidates() -> list[TempoCandidate]:
    return list(TEMPO_CANDIDATES)


def candidate_by_id(candidate_id: str) -> TempoCandidate:
    for candidate in TEMPO_CANDIDATES:
        if candidate.candidate_id == candidate_id:
            return candidate
    raise FsldAq1TempoCandidateCompareError(f"unknown tempo candidate_id: {candidate_id}")


def _partition_role(split: str) -> str:
    if split == "CALIBRATION":
        return "development_calibration"
    if split == "TEST":
        return "test_holdout"
    raise FsldAq1TempoCandidateCompareError("split must be CALIBRATION or TEST")


def _candidate_public(candidate: TempoCandidate) -> dict[str, str]:
    return {
        "candidate_id": candidate.candidate_id,
        "bpm_normalization": candidate.bpm_normalization,
        "analyzer_id": candidate.analyzer_id,
        "description": candidate.description,
    }


def _shared_record_from_baseline(record: dict[str, Any]) -> dict[str, Any]:
    bpm_norm = record.get("bpm_normalization")
    if bpm_norm != "none":
        raise FsldAq1TempoCandidateCompareError(
            "baseline predictions must use bpm_normalization=none for raw scoring"
        )
    status = record.get("status")
    raw_bpm = record.get("predicted_bpm") if status == "ok" else None
    return {
        "public_sample_id": record["public_sample_id"],
        "split": record["split"],
        "annotation_tier": record["annotation_tier"],
        "ground_truth": deepcopy(record["ground_truth"]),
        "analyzer_id": record.get("analyzer_id", ANALYZER_ID),
        "status": status,
        "exclusion_reason": record.get("exclusion_reason"),
        "raw_predicted_bpm": raw_bpm,
        "raw_bpm_normalization": "none",
    }


def _shared_record_from_live(record: dict[str, Any]) -> dict[str, Any]:
    raw_bpm = record.get("predicted_bpm") if record.get("status") == "ok" else None
    return {
        "public_sample_id": record["public_sample_id"],
        "split": record["split"],
        "annotation_tier": record["annotation_tier"],
        "ground_truth": deepcopy(record["ground_truth"]),
        "analyzer_id": record.get("analyzer_id", ANALYZER_ID),
        "status": record.get("status"),
        "exclusion_reason": record.get("exclusion_reason"),
        "raw_predicted_bpm": raw_bpm,
        "raw_bpm_normalization": "none",
    }


def _metrics_for_candidate(
    shared_records: list[dict[str, Any]], *, bpm_normalization: str
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for tier in ("ma", "sa"):
        tier_records = [
            {
                "ground_truth": record["ground_truth"],
                "predicted_bpm": (
                    normalize_bpm(record["raw_predicted_bpm"], mode=bpm_normalization)
                    if record.get("status") == "ok"
                    else None
                ),
                "annotation_tier": record["annotation_tier"],
            }
            for record in shared_records
            if record["annotation_tier"] == tier
        ]
        metrics[tier] = {"tempo": _tempo_metrics(tier_records)}
    return metrics


def _load_baseline_predictions(path: Path, *, split: str, manifest_sha256: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FsldAq1TempoCandidateCompareError(
            "baseline predictions could not be read as UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise FsldAq1TempoCandidateCompareError("baseline predictions root must be an object")
    if payload.get("document_type") != BASELINE_EVAL_DOCUMENT_TYPE:
        raise FsldAq1TempoCandidateCompareError(
            "baseline predictions document_type is not fsld_current_analyzer_eval"
        )
    if payload.get("split") != split:
        raise FsldAq1TempoCandidateCompareError("baseline predictions split does not match --split")
    if payload.get("run_status") != EVALUATED_RUN_STATUS:
        raise FsldAq1TempoCandidateCompareError(
            "baseline predictions run_status must be EVALUATED"
        )
    if payload.get("manifest_sha256") != manifest_sha256:
        raise FsldAq1TempoCandidateCompareError(
            "baseline predictions manifest_sha256 does not match verified manifest"
        )
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise FsldAq1TempoCandidateCompareError("baseline predictions records must be a non-empty list")
    return [_shared_record_from_baseline(record) for record in records]


def evaluate_tempo_candidates(
    *,
    split: str,
    audio_root: Path | None = None,
    baseline_predictions_path: Path | None = None,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    sha256_path: Path = DEFAULT_SHA256_PATH,
) -> dict[str, Any]:
    """Compare frozen tempo candidates on one FSLD split without promotion."""
    if split not in {"CALIBRATION", "TEST"}:
        raise FsldAq1TempoCandidateCompareError("split must be CALIBRATION or TEST")
    has_audio = audio_root is not None
    has_baseline = baseline_predictions_path is not None
    if has_audio == has_baseline:
        raise FsldAq1TempoCandidateCompareError(
            "provide exactly one of --audio-root or --baseline-predictions"
        )

    manifest = _load_verified_manifest(Path(manifest_path), Path(sha256_path))
    manifest_sha256 = hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()

    if has_baseline:
        shared_records = _load_baseline_predictions(
            Path(baseline_predictions_path),
            split=split,
            manifest_sha256=manifest_sha256,
        )
        raw_source = "baseline_predictions"
        has_successful = any(record["status"] == "ok" for record in shared_records)
    else:
        selected = [record for record in manifest["records"] if record.get("split") == split]
        selected.sort(key=_record_key)
        libraries = _runtime_libraries()
        live_records = [
            _analyze_record(record, Path(audio_root), libraries) for record in selected
        ]
        shared_records = [_shared_record_from_live(record) for record in live_records]
        raw_source = "live_extract_features"
        has_successful = any(record["status"] == "ok" for record in shared_records)

    run_status = (
        EVALUATED_RUN_STATUS if has_successful else PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY
    )
    candidates_out: list[dict[str, Any]] = []
    for candidate in TEMPO_CANDIDATES:
        entry = _candidate_public(candidate)
        entry["metrics"] = (
            _metrics_for_candidate(
                shared_records, bpm_normalization=candidate.bpm_normalization
            )
            if has_successful
            else None
        )
        candidates_out.append(entry)

    return {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "split": split,
        "partition_role": _partition_role(split),
        "run_status": run_status,
        "manifest_sha256": manifest_sha256,
        "raw_source": raw_source,
        "beat_grid_status": BEAT_GRID_STATUS,
        "candidates": candidates_out,
        "records": shared_records,
    }


def run_tempo_candidate_comparison(
    *,
    split: str,
    output_path: Path,
    audio_root: Path | None = None,
    baseline_predictions_path: Path | None = None,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    sha256_path: Path = DEFAULT_SHA256_PATH,
) -> dict[str, Any]:
    """Evaluate candidates and write a canonical JSON artifact outside the repo."""
    output_path = Path(output_path)
    if _path_is_within(output_path, REPOSITORY_ROOT):
        raise FsldAq1TempoCandidateCompareError("output path must be outside the repository")
    result = evaluate_tempo_candidates(
        audio_root=audio_root,
        baseline_predictions_path=baseline_predictions_path,
        split=split,
        manifest_path=manifest_path,
        sha256_path=sha256_path,
    )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(_canonical_result_bytes(result))
    except OSError as exc:
        raise FsldAq1TempoCandidateCompareError("output could not be written") from exc
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare frozen AQ1 tempo candidates on a frozen FSLD Human split."
    )
    parser.add_argument("--audio-root", type=Path, default=None)
    parser.add_argument("--baseline-predictions", type=Path, default=None)
    parser.add_argument("--split", choices=("CALIBRATION", "TEST"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--sha256", type=Path, default=DEFAULT_SHA256_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = run_tempo_candidate_comparison(
            audio_root=args.audio_root,
            baseline_predictions_path=args.baseline_predictions,
            split=args.split,
            output_path=args.output,
            manifest_path=args.manifest,
            sha256_path=args.sha256,
        )
    except FsldAq1TempoCandidateCompareError as exc:
        parser.error(str(exc))
    if result["run_status"] == PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
