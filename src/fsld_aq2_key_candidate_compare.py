"""Reproducible AQ2 key/mode candidate comparison on the frozen FSLD Human split.

Thin adapters over the current analyzer key path (`extract_features` root +
third-contrast mode evidence). Reuses AQ2 metric helpers from
``fsld_current_analyzer_eval``. Does not change production defaults, invent a
continuous claim score, or touch Harmonic Match.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .analyze import MODE_CONTRAST_MIN
from .export_fl import CONF_KEY_MIN
from .fsld_current_analyzer_eval import (
    DEFAULT_MANIFEST_PATH,
    DEFAULT_SHA256_PATH,
    EVALUATED_RUN_STATUS,
    PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY,
    REPOSITORY_ROOT,
    _analyze_record,
    _canonical_result_bytes,
    _key_confusion_metrics,
    _key_metrics,
    _load_verified_manifest,
    _mode_metrics,
    _path_is_within,
    _record_key,
    _runtime_libraries,
    _tonality_metrics,
)
from .fsld_human_manifest import canonical_manifest_bytes
from .key_signature import format_key_signature


DOCUMENT_TYPE = "sample_brain.fsld_aq2_key_candidate_compare"
SCHEMA_VERSION = "1.0.0"
ANALYZER_ID = "sample_brain.analyze.extract_features"
BASELINE_EVAL_DOCUMENT_TYPE = "sample_brain.fsld_current_analyzer_eval"
AUROC_AUPRC_STATUS = "HOLD"
CALIBRATION_STATUS = "HOLD"


class FsldAq2KeyCandidateCompareError(ValueError):
    """Controlled, fail-closed input or output error for this compare runner."""


@dataclass(frozen=True)
class KeyCandidate:
    candidate_id: str
    mode_contrast_min: float
    key_conf_min: float | None
    description: str
    analyzer_id: str = ANALYZER_ID


KEY_CANDIDATES: tuple[KeyCandidate, ...] = (
    KeyCandidate(
        candidate_id="extract_features.key_v1.mode_contrast.0.30",
        mode_contrast_min=MODE_CONTRAST_MIN,
        key_conf_min=None,
        description=(
            "Current AQ2 baseline path: chroma-peak root + third-contrast mode "
            f"with mode_contrast_min={MODE_CONTRAST_MIN} (no key_conf claim gate)."
        ),
    ),
    KeyCandidate(
        candidate_id="extract_features.key_v1.mode_contrast.0.10",
        mode_contrast_min=0.10,
        key_conf_min=None,
        description=(
            "Thin adapter: same root + third-contrast energies, commit mode when "
            "contrast >= 0.10 (more permissive than frozen MODE_CONTRAST_MIN)."
        ),
    ),
    KeyCandidate(
        candidate_id="extract_features.key_v1.mode_contrast.0.50",
        mode_contrast_min=0.50,
        key_conf_min=None,
        description=(
            "Thin adapter: same root + third-contrast energies, commit mode when "
            "contrast >= 0.50 (more conservative mode abstention)."
        ),
    ),
    KeyCandidate(
        candidate_id="extract_features.key_v1.key_conf_gate.0.55",
        mode_contrast_min=MODE_CONTRAST_MIN,
        key_conf_min=CONF_KEY_MIN,
        description=(
            "Thin claimability adapter: baseline mode_contrast + withhold key "
            f"claim when key_conf < CONF_KEY_MIN ({CONF_KEY_MIN}); relative "
            "prominence only, not calibrated probability."
        ),
    ),
)


def list_key_candidates() -> list[KeyCandidate]:
    return list(KEY_CANDIDATES)


def candidate_by_id(candidate_id: str) -> KeyCandidate:
    for candidate in KEY_CANDIDATES:
        if candidate.candidate_id == candidate_id:
            return candidate
    raise FsldAq2KeyCandidateCompareError(f"unknown key candidate_id: {candidate_id}")


def _partition_role(split: str) -> str:
    if split == "CALIBRATION":
        return "development_calibration"
    if split == "TEST":
        return "test_holdout"
    raise FsldAq2KeyCandidateCompareError("split must be CALIBRATION or TEST")


def _candidate_public(candidate: KeyCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "mode_contrast_min": candidate.mode_contrast_min,
        "key_conf_min": candidate.key_conf_min,
        "analyzer_id": candidate.analyzer_id,
        "description": candidate.description,
    }


def _mode_from_third_contrast(
    evidence: dict[str, Any] | None, *, mode_contrast_min: float
) -> str | None:
    if not isinstance(evidence, dict) or evidence.get("kind") != "third_contrast":
        return None
    major = evidence.get("major_third_energy")
    minor = evidence.get("minor_third_energy")
    if not isinstance(major, (int, float)) or not isinstance(minor, (int, float)):
        return None
    major_f = float(major)
    minor_f = float(minor)
    contrast = abs(major_f - minor_f) / (major_f + minor_f + 1e-9)
    if contrast < mode_contrast_min:
        return None
    return "maj" if major_f >= minor_f else "min"


def apply_key_candidate(
    shared_record: dict[str, Any], candidate: KeyCandidate
) -> dict[str, Any]:
    """Project shared raw key evidence through one frozen candidate adapter."""
    if shared_record.get("status") != "ok":
        return {
            "predicted_key_root": None,
            "predicted_key_mode": None,
            "predicted_key": None,
        }
    root = shared_record.get("raw_predicted_key_root")
    if root is None:
        return {
            "predicted_key_root": None,
            "predicted_key_mode": None,
            "predicted_key": None,
        }
    mode = _mode_from_third_contrast(
        shared_record.get("raw_key_mode_evidence"),
        mode_contrast_min=candidate.mode_contrast_min,
    )
    if candidate.key_conf_min is not None:
        key_conf = shared_record.get("raw_key_conf")
        if not isinstance(key_conf, (int, float)) or float(key_conf) < candidate.key_conf_min:
            return {
                "predicted_key_root": None,
                "predicted_key_mode": None,
                "predicted_key": None,
            }
    return {
        "predicted_key_root": root,
        "predicted_key_mode": mode,
        "predicted_key": format_key_signature(root, mode),
    }


def _aq2_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for tier in ("ma", "sa"):
        tier_records = [record for record in records if record["annotation_tier"] == tier]
        metrics[tier] = {
            "key_root": _key_metrics(tier_records, full_key=False),
            "key_mode": _mode_metrics(tier_records),
            "full_key": _key_metrics(tier_records, full_key=True),
            "key_confusion": _key_confusion_metrics(tier_records),
            "tonality": _tonality_metrics(tier_records),
        }
    return metrics


def _metrics_for_candidate(
    shared_records: list[dict[str, Any]], *, candidate: KeyCandidate
) -> dict[str, Any]:
    adapted = [
        {
            "ground_truth": record["ground_truth"],
            "annotation_tier": record["annotation_tier"],
            **apply_key_candidate(record, candidate),
        }
        for record in shared_records
    ]
    return _aq2_metrics(adapted)


def _shared_record_from_baseline(record: dict[str, Any]) -> dict[str, Any]:
    contract = record.get("key_analysis_contract_version")
    if contract not in {1, None}:
        raise FsldAq2KeyCandidateCompareError(
            "baseline predictions must use key_analysis_contract_version=1"
        )
    mode_min = record.get("mode_contrast_min")
    if mode_min not in {None, MODE_CONTRAST_MIN, 0.3, 0.30}:
        raise FsldAq2KeyCandidateCompareError(
            "baseline predictions must use mode_contrast_min=0.30 for raw scoring"
        )
    status = record.get("status")
    evidence = record.get("native_evidence") if isinstance(record.get("native_evidence"), dict) else {}
    return {
        "public_sample_id": record["public_sample_id"],
        "split": record["split"],
        "annotation_tier": record["annotation_tier"],
        "ground_truth": deepcopy(record["ground_truth"]),
        "analyzer_id": record.get("analyzer_id", ANALYZER_ID),
        "status": status,
        "exclusion_reason": record.get("exclusion_reason"),
        "raw_predicted_key_root": record.get("predicted_key_root") if status == "ok" else None,
        "raw_predicted_key_mode": record.get("predicted_key_mode") if status == "ok" else None,
        "raw_key_conf": evidence.get("key_conf") if status == "ok" else None,
        "raw_key_mode_evidence": (
            deepcopy(evidence.get("key_mode_evidence")) if status == "ok" else None
        ),
        "raw_mode_contrast_min": MODE_CONTRAST_MIN,
    }


def _shared_record_from_live(record: dict[str, Any]) -> dict[str, Any]:
    status = record.get("status")
    evidence = record.get("native_evidence") if isinstance(record.get("native_evidence"), dict) else {}
    return {
        "public_sample_id": record["public_sample_id"],
        "split": record["split"],
        "annotation_tier": record["annotation_tier"],
        "ground_truth": deepcopy(record["ground_truth"]),
        "analyzer_id": record.get("analyzer_id", ANALYZER_ID),
        "status": status,
        "exclusion_reason": record.get("exclusion_reason"),
        "raw_predicted_key_root": record.get("predicted_key_root") if status == "ok" else None,
        "raw_predicted_key_mode": record.get("predicted_key_mode") if status == "ok" else None,
        "raw_key_conf": evidence.get("key_conf") if status == "ok" else None,
        "raw_key_mode_evidence": (
            deepcopy(evidence.get("key_mode_evidence")) if status == "ok" else None
        ),
        "raw_mode_contrast_min": MODE_CONTRAST_MIN,
    }


def _load_baseline_predictions(path: Path, *, split: str, manifest_sha256: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FsldAq2KeyCandidateCompareError(
            "baseline predictions could not be read as UTF-8 JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise FsldAq2KeyCandidateCompareError("baseline predictions root must be an object")
    if payload.get("document_type") != BASELINE_EVAL_DOCUMENT_TYPE:
        raise FsldAq2KeyCandidateCompareError(
            "baseline predictions document_type is not fsld_current_analyzer_eval"
        )
    if payload.get("split") != split:
        raise FsldAq2KeyCandidateCompareError("baseline predictions split does not match --split")
    if payload.get("run_status") != EVALUATED_RUN_STATUS:
        raise FsldAq2KeyCandidateCompareError(
            "baseline predictions run_status must be EVALUATED"
        )
    if payload.get("manifest_sha256") != manifest_sha256:
        raise FsldAq2KeyCandidateCompareError(
            "baseline predictions manifest_sha256 does not match verified manifest"
        )
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise FsldAq2KeyCandidateCompareError("baseline predictions records must be a non-empty list")
    return [_shared_record_from_baseline(record) for record in records]


def evaluate_key_candidates(
    *,
    split: str,
    audio_root: Path | None = None,
    baseline_predictions_path: Path | None = None,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    sha256_path: Path = DEFAULT_SHA256_PATH,
) -> dict[str, Any]:
    """Compare frozen key/mode candidates on one FSLD split without promotion."""
    if split not in {"CALIBRATION", "TEST"}:
        raise FsldAq2KeyCandidateCompareError("split must be CALIBRATION or TEST")
    has_audio = audio_root is not None
    has_baseline = baseline_predictions_path is not None
    if has_audio == has_baseline:
        raise FsldAq2KeyCandidateCompareError(
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
    for candidate in KEY_CANDIDATES:
        entry = _candidate_public(candidate)
        entry["metrics"] = (
            _metrics_for_candidate(shared_records, candidate=candidate)
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
        "auroc_auprc_status": AUROC_AUPRC_STATUS,
        "calibration_status": CALIBRATION_STATUS,
        "candidates": candidates_out,
        "records": shared_records,
    }


def run_key_candidate_comparison(
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
        raise FsldAq2KeyCandidateCompareError("output path must be outside the repository")
    result = evaluate_key_candidates(
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
        raise FsldAq2KeyCandidateCompareError("output could not be written") from exc
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare frozen AQ2 key/mode candidates on a frozen FSLD Human split."
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
        result = run_key_candidate_comparison(
            audio_root=args.audio_root,
            baseline_predictions_path=args.baseline_predictions,
            split=args.split,
            output_path=args.output,
            manifest_path=args.manifest,
            sha256_path=args.sha256,
        )
    except FsldAq2KeyCandidateCompareError as exc:
        parser.error(str(exc))
    if result["run_status"] == PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
