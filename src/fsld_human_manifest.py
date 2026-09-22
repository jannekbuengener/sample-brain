"""Build and verify the public FSLD Human benchmark manifest (Issue #595).

This module deliberately consumes only the small public ``annotations.zip``.
It never reads FSL10K automatic-analysis payloads as ground truth and it never
serializes local paths or public uploader names.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import zipfile

from .key_signature import parse_key_signature


DOCUMENT_TYPE = "sample_brain.fsld_human_manifest"
SCHEMA_VERSION = "1.0.0"
SELECTION_NAMESPACE = "sample-brain/fsld-human-manifest/v1"
EXPECTED_ANNOTATIONS_MD5 = "3920ee437802cf047a990b2968fa066c"
MAX_PER_TONALITY = 250
CALIBRATION_FRACTION = 0.20

_ROOT_VALUES = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"}
_MODE_VALUES = {"maj", "min"}


@dataclass(frozen=True)
class Annotation:
    sample_id: str
    annotator_id: str
    key: str | None
    mode: str | None
    bpm: str | None
    defined_tempo: bool | None
    discard: bool


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    return normalized or None


def _defined_tempo(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    return None


def _discard(value: object) -> bool:
    return value is True or (isinstance(value, str) and value.strip().casefold() == "true")


def _annotation_from_json(sample_id: str, annotator_id: str, payload: object) -> Annotation:
    if not isinstance(payload, dict):
        raise ValueError(f"annotation {sample_id!r} from annotator {annotator_id!r} is not an object")
    return Annotation(
        sample_id=sample_id,
        annotator_id=annotator_id,
        key=_text(payload.get("key")),
        mode=_text(payload.get("mode")),
        bpm=_text(payload.get("bpm")),
        defined_tempo=_defined_tempo(payload.get("defined_tempo")),
        discard=_discard(payload.get("discard")),
    )


def load_human_annotations(annotations_zip: Path) -> tuple[dict[str, list[Annotation]], int]:
    """Load only numeric annotator paths from FSLD's public annotations archive."""
    grouped: dict[str, list[Annotation]] = defaultdict(list)
    ignored = 0
    with zipfile.ZipFile(annotations_zip) as archive:
        for info in archive.infolist():
            parts = info.filename.split("/")
            if len(parts) != 3 or parts[0] != "annotations" or not parts[2].endswith(".json"):
                continue
            annotator_id = parts[1]
            stem = parts[2][:-5]
            if not annotator_id.isdecimal() or not stem.startswith("sound-") or not stem[6:].isdecimal():
                ignored += 1
                continue
            sample_id = stem[6:]
            try:
                payload = json.loads(archive.read(info).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid human annotation JSON: {info.filename}") from exc
            grouped[sample_id].append(_annotation_from_json(sample_id, annotator_id, payload))
    return dict(grouped), ignored


def _root_value(value: str | None) -> str | None:
    if value in {None, "none", "unknown"}:
        return None
    parsed = parse_key_signature(value)
    if parsed is None or parsed.mode is not None or parsed.root not in _ROOT_VALUES:
        return None
    return parsed.root


def _mode_value(value: str | None) -> str | None:
    return value if value in _MODE_VALUES else None


def _tonality(annotation: Annotation) -> str | None:
    if annotation.key == "none" and annotation.mode == "none":
        return "no_key"
    if annotation.key is not None or annotation.mode is not None:
        return "tonal"
    return None


def _field_evidence(values: Iterable[str | None], *, no_key: bool) -> tuple[str, str | None]:
    """Apply the fixed evidence priority to one root or mode field."""
    if no_key:
        return "not_applicable", None
    raw = list(values)
    concrete = {value for value in raw if value not in {None, "unknown", "missing"}}
    unknown_present = any(value == "unknown" for value in raw)
    missing_present = any(value == "missing" for value in raw)
    if len(concrete) >= 2:
        return "conflicting", None
    if unknown_present:
        return "unknown", None
    if missing_present:
        return "missing", None
    if len(concrete) == 1:
        return "known", next(iter(concrete))
    return "missing", None


def _root_observation(annotation: Annotation) -> str | None:
    if annotation.key == "unknown":
        return "unknown"
    root = _root_value(annotation.key)
    return root if root is not None else "missing"


def _mode_observation(annotation: Annotation) -> str | None:
    if annotation.mode == "unknown":
        return "unknown"
    mode = _mode_value(annotation.mode)
    return mode if mode is not None else "missing"


def _numeric_bpm(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _bpm_evidence(annotations: list[Annotation], tier: str) -> tuple[str, float | None]:
    values = [_numeric_bpm(annotation.bpm) for annotation in annotations]
    if any(annotation.defined_tempo is not True for annotation in annotations) or any(value is None for value in values):
        return "missing", None
    concrete = {float(value) for value in values if value is not None}
    if tier == "sa":
        return "known", next(iter(concrete))
    if len(concrete) == 1:
        return "known", next(iter(concrete))
    return "conflicting", None


def _build_record(sample_id: str, all_annotations: list[Annotation]) -> tuple[dict[str, Any] | None, str | None]:
    tier = "ma" if len(all_annotations) >= 2 else "sa"
    valid = [annotation for annotation in all_annotations if not annotation.discard]
    if tier == "ma" and len(valid) < 2:
        return None, "ma_degraded_below_two_valid"
    if tier == "sa" and len(valid) != 1:
        return None, "sa_discarded_or_missing"

    tonalities = {_tonality(annotation) for annotation in valid}
    if tonalities == {"no_key"}:
        tonality = "no_key"
    elif tonalities == {"tonal"}:
        tonality = "tonal"
    elif "no_key" in tonalities and "tonal" in tonalities:
        return None, "tonality_conflicting"
    else:
        return None, "tonality_missing"
    no_key = tonality == "no_key"
    root_evidence, root = _field_evidence(
        (_root_observation(annotation) for annotation in valid), no_key=no_key
    )
    mode_evidence, mode = _field_evidence(
        (_mode_observation(annotation) for annotation in valid), no_key=no_key
    )
    bpm_evidence, bpm = _bpm_evidence(valid, tier)
    return {
        "public_sample_id": sample_id,
        "annotation_tier": tier,
        "ground_truth_tonality": tonality,
        "ground_truth_key_root": root,
        "root_evidence": root_evidence,
        "ground_truth_key_mode": mode,
        "mode_evidence": mode_evidence,
        "ground_truth_bpm": bpm,
        "bpm_evidence": bpm_evidence,
        "source_group_id": None,
    }, None


def _rank(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{SELECTION_NAMESPACE}/{namespace}/{value}".encode("utf-8")).hexdigest()


def _stratum(record: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(record["annotation_tier"]),
        str(record["ground_truth_tonality"]),
        str(record["root_evidence"]),
        str(record["mode_evidence"]),
        str(record["ground_truth_key_root"] or ""),
        str(record["ground_truth_key_mode"] or ""),
    )


def _select_bucket(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(records) <= limit:
        return list(records)
    by_stratum: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_stratum[_stratum(record)].append(record)
    selected: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    stratum_representatives: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = []
    for key in sorted(by_stratum):
        ordered = sorted(by_stratum[key], key=lambda record: _rank("select", record["public_sample_id"]))
        stratum_key = "\x1f".join(key)
        stratum_representatives.append((_rank("select-stratum", stratum_key), ordered[0], ordered[1:]))
    for _, representative, leftovers in sorted(stratum_representatives)[:limit]:
        selected.append(representative)
        remaining.extend(leftovers)
    needed = max(0, limit - len(selected))
    selected.extend(sorted(remaining, key=lambda record: _rank("select", record["public_sample_id"]))[:needed])
    return selected


def calibration_target(total: int) -> int:
    if total <= 1:
        return 0
    return max(1, math.floor(total * CALIBRATION_FRACTION + 0.5))


def _allocate_ungrouped(records: list[dict[str, Any]], target: int) -> set[str]:
    by_stratum: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_stratum[_stratum(record)].append(record)
    allocations: dict[tuple[str, ...], int] = {}
    remainders: list[tuple[float, tuple[str, ...]]] = []
    total = len(records)
    for key, values in by_stratum.items():
        quota = len(values) * target / total
        allocations[key] = math.floor(quota)
        remainders.append((quota - allocations[key], key))
    for _, key in sorted(
        remainders,
        key=lambda item: (-item[0], _rank("split-stratum", "\x1f".join(item[1]))),
    )[: target - sum(allocations.values())]:
        allocations[key] += 1
    calibration: set[str] = set()
    for key, values in by_stratum.items():
        ordered = sorted(values, key=lambda record: _rank("split", record["public_sample_id"]))
        calibration.update(record["public_sample_id"] for record in ordered[: allocations[key]])
    return calibration


def _group_token(username: str) -> str:
    digest = hashlib.sha256(f"fsld-uploader-v1/{username}".encode("utf-8")).hexdigest()
    return f"fsld-uploader-sha256:{digest}"


def _apply_metadata_groups(records: list[dict[str, Any]], metadata: object | None) -> bool:
    if not isinstance(metadata, dict):
        return False
    group_tokens: dict[str, str] = {}
    for record in records:
        row = metadata.get(record["public_sample_id"])
        username = row.get("username") if isinstance(row, dict) else None
        if not isinstance(username, str) or not username.strip():
            return False
        group_tokens[record["public_sample_id"]] = _group_token(username.strip())
    for record in records:
        record["source_group_id"] = group_tokens[record["public_sample_id"]]
    return bool(records)


def _allocate_grouped(records: list[dict[str, Any]], target: int) -> set[str]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        group = record["source_group_id"] or f"sample:{record['public_sample_id']}"
        groups[group].append(record)
    ordered_groups = sorted(groups, key=lambda group: _rank("group", group))
    paths: dict[int, tuple[str, ...]] = {0: ()}
    for group in ordered_groups:
        size = len(groups[group])
        for count, path in sorted(list(paths.items()), reverse=True):
            candidate = count + size
            if candidate not in paths:
                paths[candidate] = path + (group,)
    best_count = min(
        paths,
        key=lambda count: (
            abs(count - target),
            tuple(_rank("group", group) for group in paths[count]),
        ),
    )
    selected_groups = set(paths[best_count])
    return {
        record["public_sample_id"]
        for group in selected_groups
        for record in groups[group]
    }


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def build_manifest(
    annotations_zip: Path,
    *,
    expected_md5: str = EXPECTED_ANNOTATIONS_MD5,
    metadata: object | None = None,
) -> dict[str, Any]:
    actual_md5 = hashlib.md5(Path(annotations_zip).read_bytes()).hexdigest()
    if actual_md5.casefold() != expected_md5.casefold():
        raise ValueError("annotations archive MD5 does not match the pinned FSLD source")
    annotations, ignored_paths = load_human_annotations(Path(annotations_zip))
    exclusions: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []
    tier_counts: Counter[str] = Counter()
    for sample_id in sorted(annotations, key=lambda value: int(value)):
        original = annotations[sample_id]
        tier_counts["ma" if len(original) >= 2 else "sa"] += 1
        record, exclusion = _build_record(sample_id, original)
        if record is None:
            exclusions[exclusion or "unknown"] += 1
        else:
            candidates.append(record)

    no_key = _select_bucket([record for record in candidates if record["ground_truth_tonality"] == "no_key"], MAX_PER_TONALITY)
    tonal = _select_bucket([record for record in candidates if record["ground_truth_tonality"] == "tonal"], MAX_PER_TONALITY)
    records = no_key + tonal
    grouping_enabled = _apply_metadata_groups(records, metadata)
    target = calibration_target(len(records))
    calibration = _allocate_grouped(records, target) if grouping_enabled else _allocate_ungrouped(records, target)
    for record in records:
        record["split"] = "CALIBRATION" if record["public_sample_id"] in calibration else "TEST"
    records.sort(key=lambda record: int(record["public_sample_id"]))
    split_summary = dict(sorted(Counter(record["split"] for record in records).items()))
    return {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "subset_kind": "balanced_stratified_benchmark_subset",
        "provenance": {
            "dataset": "Freesound Loop Dataset",
            "zenodo_record": "3967852",
            "doi": "10.5281/zenodo.3967852",
            "dataset_version": "1.0",
            "annotations_file": "annotations.zip",
            "annotations_md5": EXPECTED_ANNOTATIONS_MD5,
            "automatic_annotations_imported": False,
            "source_grouping": "metadata_username_sha256_v1" if grouping_enabled else "unavailable_annotations_only",
        },
        "selection": {
            "max_total_records": MAX_PER_TONALITY * 2,
            "max_records_per_tonality": MAX_PER_TONALITY,
            "calibration_fraction": CALIBRATION_FRACTION,
            "calibration_target": target,
            "ungrouped_split_is_exact": not grouping_enabled,
            "selection_namespace": SELECTION_NAMESPACE,
        },
        "source_summary": {
            "human_samples_by_original_tier": dict(sorted(tier_counts.items())),
            "eligible_candidates_by_tonality": {
                "no_key": sum(record["ground_truth_tonality"] == "no_key" for record in candidates),
                "tonal": sum(record["ground_truth_tonality"] == "tonal" for record in candidates),
            },
            "exclusions": dict(sorted(exclusions.items())),
            "ignored_non_human_annotation_paths": ignored_paths,
        },
        "split_summary": split_summary,
        "records": [_serialize_record(record) for record in records],
    }


def _serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return the compact public record form; input details never escape."""
    serialized = {
        "annotation_tier": record["annotation_tier"],
        "ground_truth": {
            "bpm": record["ground_truth_bpm"],
            "bpm_evidence": record["bpm_evidence"],
            "key_mode": record["ground_truth_key_mode"],
            "key_root": record["ground_truth_key_root"],
            "mode_evidence": record["mode_evidence"],
            "root_evidence": record["root_evidence"],
            "tonality": record["ground_truth_tonality"],
        },
        "public_sample_id": record["public_sample_id"],
        "source_group_id": record["source_group_id"],
        "split": record["split"],
    }
    return serialized


def write_manifest_files(manifest: dict[str, Any], manifest_path: Path, sha256_path: Path) -> None:
    payload = canonical_manifest_bytes(manifest)
    digest = hashlib.sha256(payload).hexdigest()
    Path(manifest_path).write_bytes(payload)
    Path(sha256_path).write_text(f"{digest}  {Path(manifest_path).name}\n", encoding="utf-8", newline="\n")


def verify_manifest_files(manifest: dict[str, Any], manifest_path: Path, sha256_path: Path) -> None:
    expected = canonical_manifest_bytes(manifest)
    actual = Path(manifest_path).read_bytes()
    if actual != expected:
        raise ValueError("manifest bytes are not canonical or do not match the supplied annotations")
    expected_sidecar = f"{hashlib.sha256(actual).hexdigest()}  {Path(manifest_path).name}\n".encode("utf-8")
    if Path(sha256_path).read_bytes() != expected_sidecar:
        raise ValueError("manifest SHA256 sidecar does not match canonical manifest bytes")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or verify the public FSLD Human benchmark manifest.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "verify"):
        command = subcommands.add_parser(name)
        command.add_argument("--annotations-zip", type=Path, required=True)
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--sha256", type=Path, required=True)
        command.add_argument("--metadata-json", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    metadata = json.loads(args.metadata_json.read_text(encoding="utf-8")) if args.metadata_json else None
    manifest = build_manifest(args.annotations_zip, metadata=metadata)
    if args.command == "build":
        write_manifest_files(manifest, args.manifest, args.sha256)
    else:
        verify_manifest_files(manifest, args.manifest, args.sha256)
    print(json.dumps({"split_summary": manifest["split_summary"], "source_summary": manifest["source_summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
