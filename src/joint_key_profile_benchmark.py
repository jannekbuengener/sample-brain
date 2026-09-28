"""External-input benchmark adapter for the joint 24-key profile prototype.

This module is prototype-only.  It is not imported by the production analyzer,
does not change persistence, and writes reports only to explicit paths outside
the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter_ns
from typing import Any

import librosa
import numpy as np

from .analyze import safe_load
from .config import ANALYZE_HOP_LENGTH
from .fsld_human_manifest import DOCUMENT_TYPE as FSLD_MANIFEST_DOCUMENT_TYPE
from .fsld_human_manifest import canonical_manifest_bytes
from .joint_key_profile import JointKeyProfileError, JointKeyProfileResult, rank_joint_key_profiles
from .key_signature import format_key_signature


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = REPOSITORY_ROOT / "data" / "benchmarks" / "fsld_human_manifest_v1.json"
DEFAULT_SHA256_PATH = REPOSITORY_ROOT / "data" / "benchmarks" / "fsld_human_manifest_v1.sha256"
DOCUMENT_TYPE = "sample_brain.joint_key_profile_benchmark"
SCHEMA_VERSION = "1.0.0"
EVALUATED_RUN_STATUS = "EVALUATED"
PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY = "PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY"


class JointKeyProfileBenchmarkError(ValueError):
    """Controlled failure for invalid external benchmark inputs."""


@dataclass(frozen=True)
class CqtMeanEvidence:
    """The locked #631 representation before joint profile scoring."""

    chroma_mean: np.ndarray


def mean_cqt_chroma(audio_path: Path) -> CqtMeanEvidence:
    """Load external audio and reproduce #631 CQT mean representation exactly.

    ``librosa.feature.chroma_cqt`` receives no tuning override, retaining its
    automatic tuning behavior.  No candidate parameters are exposed here.
    """

    y, sr = safe_load(Path(audio_path))
    if y is None or sr is None:
        raise JointKeyProfileBenchmarkError("audio could not be loaded")
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=ANALYZE_HOP_LENGTH)
    except Exception as exc:
        raise JointKeyProfileBenchmarkError("CQT chroma could not be computed") from exc
    if chroma is None or chroma.size == 0:
        raise JointKeyProfileBenchmarkError("CQT chroma is empty")
    chroma_mean = np.mean(chroma, axis=1, dtype=np.float64)
    try:
        rank_joint_key_profiles(chroma_mean)
    except JointKeyProfileError:
        raise
    return CqtMeanEvidence(chroma_mean=chroma_mean)


def score_audio(audio_path: Path) -> JointKeyProfileResult:
    """Return only raw joint-key evidence for one external audio input."""

    return rank_joint_key_profiles(mean_cqt_chroma(audio_path).chroma_mean)


def _load_verified_manifest(manifest_path: Path, sha256_path: Path) -> dict[str, Any]:
    try:
        raw = Path(manifest_path).read_bytes()
    except OSError as exc:
        raise JointKeyProfileBenchmarkError("manifest could not be read as UTF-8 JSON") from exc
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise JointKeyProfileBenchmarkError("manifest could not be read as UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise JointKeyProfileBenchmarkError("manifest bytes are not canonical")
    try:
        canonical = canonical_manifest_bytes(manifest)
    except ValueError as exc:
        raise JointKeyProfileBenchmarkError("manifest contains non-finite JSON values") from exc
    if raw != canonical:
        raise JointKeyProfileBenchmarkError("manifest bytes are not canonical")
    expected = f"{hashlib.sha256(raw).hexdigest()}  {Path(manifest_path).name}\n".encode("utf-8")
    try:
        sidecar = Path(sha256_path).read_bytes()
    except OSError as exc:
        raise JointKeyProfileBenchmarkError("manifest SHA256 sidecar could not be read") from exc
    if sidecar != expected or manifest.get("document_type") != FSLD_MANIFEST_DOCUMENT_TYPE:
        raise JointKeyProfileBenchmarkError("manifest contract verification failed")
    records = manifest.get("records")
    if not isinstance(records, list):
        raise JointKeyProfileBenchmarkError("manifest records must be a list")
    for index, record in enumerate(records):
        _validate_manifest_record(record, index=index)
    return manifest


def _validate_manifest_record(record: object, *, index: int) -> None:
    if not isinstance(record, dict):
        raise JointKeyProfileBenchmarkError(f"manifest record {index} must be an object")
    sample_id = record.get("public_sample_id")
    if not isinstance(sample_id, str) or not sample_id.isdecimal():
        raise JointKeyProfileBenchmarkError(f"manifest record {index} public_sample_id must be decimal")
    try:
        int(sample_id)
    except ValueError as exc:
        raise JointKeyProfileBenchmarkError(
            f"manifest record {index} public_sample_id must be convertible to integer"
        ) from exc
    if record.get("split") not in {"CALIBRATION", "TEST"}:
        raise JointKeyProfileBenchmarkError(
            f"manifest record {index} split must be CALIBRATION or TEST"
        )
    if record.get("annotation_tier") not in {"ma", "sa"}:
        raise JointKeyProfileBenchmarkError(f"manifest record {index} annotation_tier must be ma or sa")
    if "ground_truth" not in record:
        raise JointKeyProfileBenchmarkError(f"manifest record {index} must include ground_truth")
    if not isinstance(record["ground_truth"], dict):
        raise JointKeyProfileBenchmarkError(f"manifest record {index} ground_truth must be an object")


def _record_key(record: dict[str, Any]) -> int:
    sample_id = record.get("public_sample_id")
    if not isinstance(sample_id, str) or not sample_id.isdecimal():
        raise JointKeyProfileBenchmarkError("manifest public_sample_id must be decimal")
    return int(sample_id)


def _base_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "public_sample_id": record["public_sample_id"],
        "split": record["split"],
        "annotation_tier": record["annotation_tier"],
        "ground_truth": record["ground_truth"],
        "predicted_key_root": None,
        "predicted_key_mode": None,
        "predicted_key": None,
        "raw_score": None,
        "ranking": [],
        "runtime_ms": None,
        "status": None,
        "exclusion_reason": None,
    }


def _score_record(record: dict[str, Any], audio_root: Path) -> dict[str, Any]:
    output = _base_record(record)
    audio_path = Path(audio_root) / f"{output['public_sample_id']}.wav"
    if not audio_path.is_file():
        output["status"] = "missing_audio"
        output["exclusion_reason"] = "audio_missing"
        return output
    started = perf_counter_ns()
    try:
        result = score_audio(audio_path)
    except (JointKeyProfileBenchmarkError, JointKeyProfileError):
        output["runtime_ms"] = (perf_counter_ns() - started) / 1_000_000
        output["status"] = "analysis_failed"
        output["exclusion_reason"] = "joint_profile_failed"
        return output
    output["runtime_ms"] = (perf_counter_ns() - started) / 1_000_000
    output["predicted_key_root"] = result.root
    output["predicted_key_mode"] = result.mode
    output["predicted_key"] = format_key_signature(result.root, result.mode)
    output["raw_score"] = result.raw_score
    output["ranking"] = [
        {"root": item.root, "mode": item.mode, "raw_score": item.score} for item in result.ranking
    ]
    output["status"] = "ok"
    return output


def _key_metrics(records: list[dict[str, Any]], *, full_key: bool) -> dict[str, int | float | None]:
    eligible = predicted = correct = 0
    for record in records:
        truth = record["ground_truth"]
        if truth.get("tonality") != "tonal" or truth.get("root_evidence") != "known":
            continue
        if full_key and truth.get("mode_evidence") != "known":
            continue
        eligible += 1
        root = record["predicted_key_root"]
        mode = record["predicted_key_mode"]
        if root is None or (full_key and mode is None):
            continue
        predicted += 1
        if root == truth.get("key_root") and (not full_key or mode == truth.get("key_mode")):
            correct += 1
    return {
        "eligible": eligible,
        "predicted": predicted,
        "correct": correct,
        "accuracy": correct / eligible if eligible else None,
    }


def _metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        tier: {
            "root": _key_metrics([record for record in records if record["annotation_tier"] == tier], full_key=False),
            "full_key": _key_metrics([record for record in records if record["annotation_tier"] == tier], full_key=True),
        }
        for tier in ("ma", "sa")
    }


def evaluate_joint_key_profiles(
    *,
    audio_root: Path,
    split: str,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    sha256_path: Path = DEFAULT_SHA256_PATH,
) -> dict[str, Any]:
    """Evaluate the locked prototype over one frozen public manifest split."""

    if split not in {"CALIBRATION", "TEST"}:
        raise JointKeyProfileBenchmarkError("split must be CALIBRATION or TEST")
    manifest = _load_verified_manifest(Path(manifest_path), Path(sha256_path))
    records = [record for record in manifest["records"] if record.get("split") == split]
    records.sort(key=_record_key)
    scored = [_score_record(record, Path(audio_root)) for record in records]
    evaluated = any(record["status"] == "ok" for record in scored)
    return {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "split": split,
        "run_status": EVALUATED_RUN_STATUS if evaluated else PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY,
        "manifest_sha256": hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest(),
        "records": scored,
        "metrics": _metrics(scored) if evaluated else None,
    }


def _canonical_result_bytes(result: dict[str, Any]) -> bytes:
    return (json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def run_joint_key_profile_evaluation(
    *,
    audio_root: Path,
    split: str,
    output_path: Path,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    sha256_path: Path = DEFAULT_SHA256_PATH,
) -> dict[str, Any]:
    """Write one canonical report only to an explicit path outside the repo."""

    output_path = Path(output_path)
    try:
        output_path.resolve(strict=False).relative_to(REPOSITORY_ROOT)
    except ValueError:
        pass
    else:
        raise JointKeyProfileBenchmarkError("output path must be outside the repository")
    result = evaluate_joint_key_profiles(
        audio_root=audio_root,
        split=split,
        manifest_path=manifest_path,
        sha256_path=sha256_path,
    )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(_canonical_result_bytes(result))
    except OSError as exc:
        raise JointKeyProfileBenchmarkError("output could not be written") from exc
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the joint 24-key profile prototype.")
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--split", choices=("CALIBRATION", "TEST"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--sha256", type=Path, default=DEFAULT_SHA256_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = run_joint_key_profile_evaluation(
            audio_root=args.audio_root,
            split=args.split,
            output_path=args.output,
            manifest_path=args.manifest,
            sha256_path=args.sha256,
        )
    except JointKeyProfileBenchmarkError as exc:
        _parser().error(str(exc))
    return 0 if result["run_status"] == EVALUATED_RUN_STATUS else 3


if __name__ == "__main__":
    raise SystemExit(main())
