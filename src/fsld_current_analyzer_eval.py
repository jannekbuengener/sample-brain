"""Run the current Sample Brain analyzer against the frozen FSLD Human manifest.

This evaluation runner is deliberately DB-free. It maps an explicitly supplied
FSL10K audio root to the frozen public manifest and emits scalar-only evidence
outside the repository; it neither changes nor reimplements analyzer behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from copy import deepcopy
from importlib import metadata
from pathlib import Path
from time import perf_counter_ns
from typing import Any

import soundfile as sf

from .analyze import (
    KEY_ANALYSIS_CONTRACT_VERSION,
    MODE_CONTRAST_MIN,
    extract_features,
)
from .bpm_evidence import classify_bpm_error
from .fsld_human_manifest import DOCUMENT_TYPE as FSLD_MANIFEST_DOCUMENT_TYPE
from .fsld_human_manifest import canonical_manifest_bytes
from .key_signature import parse_key_signature


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = REPOSITORY_ROOT / "data" / "benchmarks" / "fsld_human_manifest_v1.json"
DEFAULT_SHA256_PATH = REPOSITORY_ROOT / "data" / "benchmarks" / "fsld_human_manifest_v1.sha256"
DOCUMENT_TYPE = "sample_brain.fsld_current_analyzer_eval"
SCHEMA_VERSION = "1.0.0"
ANALYZER_ID = "sample_brain.analyze.extract_features"
EVALUATED_RUN_STATUS = "EVALUATED"
PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY = "PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY"
RUNTIME_DISTRIBUTIONS = ("librosa", "numpy", "soundfile")
RELATION_CLASSES = ("correct", "half", "double", "ambiguous", "outlier")


class FsldCurrentAnalyzerEvalError(ValueError):
    """Controlled, fail-closed input or output error for this runner."""


def _canonical_result_bytes(result: dict[str, Any]) -> bytes:
    return (
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
    except ValueError:
        return False
    return True


def _load_verified_manifest(manifest_path: Path, sha256_path: Path) -> dict[str, Any]:
    try:
        raw = Path(manifest_path).read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FsldCurrentAnalyzerEvalError("manifest could not be read as UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise FsldCurrentAnalyzerEvalError("manifest root must be an object")
    if raw != canonical_manifest_bytes(manifest):
        raise FsldCurrentAnalyzerEvalError("manifest bytes are not canonical")

    expected_sidecar = (
        f"{hashlib.sha256(raw).hexdigest()}  {Path(manifest_path).name}\n"
    ).encode("utf-8")
    try:
        sidecar = Path(sha256_path).read_bytes()
    except OSError as exc:
        raise FsldCurrentAnalyzerEvalError("manifest SHA256 sidecar could not be read") from exc
    if sidecar != expected_sidecar:
        raise FsldCurrentAnalyzerEvalError("manifest SHA256 sidecar does not match canonical manifest bytes")
    if manifest.get("document_type") != FSLD_MANIFEST_DOCUMENT_TYPE:
        raise FsldCurrentAnalyzerEvalError("manifest document type is not the FSLD Human contract")
    if not isinstance(manifest.get("records"), list):
        raise FsldCurrentAnalyzerEvalError("manifest records must be a list")
    return manifest


def _runtime_libraries() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in RUNTIME_DISTRIBUTIONS:
        try:
            versions[distribution] = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            versions[distribution] = "unknown"
    return versions


def _audio_duration(path: Path) -> float | None:
    """Read only lightweight container metadata; unknown duration is valid."""
    try:
        duration = float(sf.info(str(path)).duration)
    except Exception:
        return None
    return duration if math.isfinite(duration) and duration >= 0 else None


def _record_key(record: dict[str, Any]) -> int:
    value = record.get("public_sample_id")
    if not isinstance(value, str) or not value.isdecimal():
        raise FsldCurrentAnalyzerEvalError("manifest public_sample_id must be a decimal string")
    return int(value)


def _base_output_record(record: dict[str, Any], libraries: dict[str, str]) -> dict[str, Any]:
    sample_id = record.get("public_sample_id")
    split = record.get("split")
    tier = record.get("annotation_tier")
    ground_truth = record.get("ground_truth")
    if not isinstance(sample_id, str) or not isinstance(split, str) or tier not in {"ma", "sa"}:
        raise FsldCurrentAnalyzerEvalError("manifest record has an invalid identity, split, or annotation tier")
    if not isinstance(ground_truth, dict):
        raise FsldCurrentAnalyzerEvalError("manifest record ground_truth must be an object")
    return {
        "public_sample_id": sample_id,
        "split": split,
        "annotation_tier": tier,
        "ground_truth": deepcopy(ground_truth),
        "analyzer_id": ANALYZER_ID,
        "key_analysis_contract_version": KEY_ANALYSIS_CONTRACT_VERSION,
        "mode_contrast_min": MODE_CONTRAST_MIN,
        "bpm_normalization": "none",
        "runtime_libraries": libraries,
        "predicted_key_root": None,
        "predicted_key_mode": None,
        "predicted_key": None,
        "predicted_bpm": None,
        "native_evidence": {
            "key_conf": None,
            "key_mode_evidence": None,
            "quality_note": None,
        },
        "runtime_ms": None,
        "status": None,
        "exclusion_reason": None,
    }


def _analyze_record(record: dict[str, Any], audio_root: Path, libraries: dict[str, str]) -> dict[str, Any]:
    output = _base_output_record(record, libraries)
    audio_path = audio_root / f"{output['public_sample_id']}.wav"
    if not audio_path.is_file():
        output["status"] = "missing_audio"
        output["exclusion_reason"] = "audio_missing"
        return output

    started = perf_counter_ns()
    try:
        features = extract_features(
            audio_path,
            _audio_duration(audio_path),
            bpm_normalization="none",
        )
    except Exception:
        output["runtime_ms"] = (perf_counter_ns() - started) / 1_000_000
        output["status"] = "analysis_failed"
        output["exclusion_reason"] = "extract_features_failed"
        return output
    output["runtime_ms"] = (perf_counter_ns() - started) / 1_000_000
    if features is None:
        output["status"] = "no_features"
        output["exclusion_reason"] = "extract_features_returned_none"
        return output

    parsed_key = parse_key_signature(features.key)
    output["predicted_key_root"] = parsed_key.root if parsed_key is not None else None
    output["predicted_key_mode"] = features.key_mode
    output["predicted_key"] = features.key
    output["predicted_bpm"] = features.bpm
    output["native_evidence"] = {
        "key_conf": features.key_conf,
        "key_mode_evidence": features.key_mode_evidence,
        "quality_note": features.quality_note,
    }
    output["status"] = "ok"
    return output


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _summary(values: list[float]) -> dict[str, int | float | None]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "p95": None}
    ordered = sorted(values)
    index = (len(ordered) - 1) * 0.95
    lower = math.floor(index)
    upper = math.ceil(index)
    p95 = ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)
    return {
        "count": len(ordered),
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p95": p95,
    }


def _key_metrics(records: list[dict[str, Any]], *, full_key: bool) -> dict[str, int | float | None]:
    eligible = 0
    predicted = 0
    exact = 0
    for record in records:
        ground_truth = record["ground_truth"]
        if ground_truth.get("tonality") != "tonal" or ground_truth.get("root_evidence") != "known":
            continue
        if full_key and ground_truth.get("mode_evidence") != "known":
            continue
        eligible += 1
        root = record["predicted_key_root"]
        mode = record["predicted_key_mode"]
        if root is None or (full_key and mode is None):
            continue
        predicted += 1
        if root != ground_truth.get("key_root"):
            continue
        if not full_key or mode == ground_truth.get("key_mode"):
            exact += 1
    return {"eligible": eligible, "predicted": predicted, "exact": exact, "exact_rate": _rate(exact, eligible)}


def _tempo_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = 0
    predicted = 0
    absolute_errors: list[float] = []
    relative_errors: list[float] = []
    counts = {relation: 0 for relation in RELATION_CLASSES}
    for record in records:
        ground_truth = record["ground_truth"]
        if ground_truth.get("bpm_evidence") != "known":
            continue
        label_bpm = ground_truth.get("bpm")
        if not isinstance(label_bpm, (int, float)) or not math.isfinite(label_bpm) or label_bpm <= 0:
            continue
        eligible += 1
        predicted_bpm = record["predicted_bpm"]
        if isinstance(predicted_bpm, (int, float)) and math.isfinite(predicted_bpm) and predicted_bpm > 0:
            predicted += 1
            absolute_errors.append(abs(float(predicted_bpm) - float(label_bpm)))
            relative_errors.append(abs(float(predicted_bpm) - float(label_bpm)) / float(label_bpm))
        relation = classify_bpm_error(predicted_bpm, float(label_bpm))
        counts[relation] += 1
    return {
        "eligible": eligible,
        "predicted": predicted,
        "absolute_bpm_error": _summary(absolute_errors),
        "relative_bpm_error": _summary(relative_errors),
        "relation_counts": counts,
        "relation_rates": {relation: _rate(counts[relation], eligible) for relation in RELATION_CLASSES},
    }


def _metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for tier in ("ma", "sa"):
        tier_records = [record for record in records if record["annotation_tier"] == tier]
        metrics[tier] = {
            "key_root": _key_metrics(tier_records, full_key=False),
            "full_key": _key_metrics(tier_records, full_key=True),
            "tempo": _tempo_metrics(tier_records),
        }
    return metrics


def evaluate_current_analyzer(
    *,
    audio_root: Path,
    split: str,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    sha256_path: Path = DEFAULT_SHA256_PATH,
) -> dict[str, Any]:
    """Evaluate one frozen FSLD split without output or catalog mutation."""
    if split not in {"CALIBRATION", "TEST"}:
        raise FsldCurrentAnalyzerEvalError("split must be CALIBRATION or TEST")
    manifest = _load_verified_manifest(Path(manifest_path), Path(sha256_path))
    selected = [record for record in manifest["records"] if record.get("split") == split]
    selected.sort(key=_record_key)
    libraries = _runtime_libraries()
    records = [_analyze_record(record, Path(audio_root), libraries) for record in selected]
    has_successful_analysis = any(record["status"] == "ok" for record in records)
    return {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "split": split,
        "run_status": (
            EVALUATED_RUN_STATUS
            if has_successful_analysis
            else PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY
        ),
        "manifest_sha256": hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest(),
        "records": records,
        "metrics": _metrics(records) if has_successful_analysis else None,
    }


def run_current_analyzer_evaluation(
    *,
    audio_root: Path,
    split: str,
    output_path: Path,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    sha256_path: Path = DEFAULT_SHA256_PATH,
) -> dict[str, Any]:
    """Evaluate one split and write only a canonical external JSON artifact."""
    output_path = Path(output_path)
    if _path_is_within(output_path, REPOSITORY_ROOT):
        raise FsldCurrentAnalyzerEvalError("output path must be outside the repository")
    result = evaluate_current_analyzer(
        audio_root=audio_root,
        split=split,
        manifest_path=manifest_path,
        sha256_path=sha256_path,
    )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(_canonical_result_bytes(result))
    except OSError as exc:
        raise FsldCurrentAnalyzerEvalError("output could not be written") from exc
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the current analyzer on a frozen FSLD Human split.")
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--split", choices=("CALIBRATION", "TEST"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--sha256", type=Path, default=DEFAULT_SHA256_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = run_current_analyzer_evaluation(
            audio_root=args.audio_root,
            split=args.split,
            output_path=args.output,
            manifest_path=args.manifest,
            sha256_path=args.sha256,
        )
    except FsldCurrentAnalyzerEvalError as exc:
        parser.error(str(exc))
    if result["run_status"] == PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
