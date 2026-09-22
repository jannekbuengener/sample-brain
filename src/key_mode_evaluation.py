"""Private-local evaluation of analyzer output against a Traktor reference.

This module deliberately has no default library database, reference file, or
output location.  Callers must pass all three explicit paths so real-library
evidence remains local and cannot accidentally become a repository artifact.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path, PurePath
from typing import Any, Iterable

from .analyze import extract_features
from .key_signature import format_key_signature, parse_key_signature


_OPEN_KEY_TO_CANONICAL = {
    "1d": "Cmaj", "2d": "Gmaj", "3d": "Dmaj", "4d": "Amaj",
    "5d": "Emaj", "6d": "Bmaj", "7d": "F#maj", "8d": "C#maj",
    "9d": "G#maj", "10d": "D#maj", "11d": "A#maj", "12d": "Fmaj",
    "1m": "Amin", "2m": "Emin", "3m": "Bmin", "4m": "F#min",
    "5m": "C#min", "6m": "G#min", "7m": "D#min", "8m": "A#min",
    "9m": "Fmin", "10m": "Cmin", "11m": "Gmin", "12m": "Dmin",
}


@dataclass(frozen=True)
class ReferenceSample:
    """One private Traktor reference row, loaded only from an external file."""

    name: str
    traktor_bpm: float | None
    open_key: str | None
    tier: str | None = None
    size_bytes: int | None = None


@dataclass(frozen=True)
class LibrarySample:
    """One already-registered Workbench file, read from the local cache only."""

    path: Path
    display_name: str
    size_bytes: int | None = None


@dataclass(frozen=True)
class ResolvedReference:
    reference: ReferenceSample
    library_sample: LibrarySample | None
    reason: str | None = None


def select_references(
    references: Iterable[ReferenceSample],
    *,
    tier_a_only: bool = False,
    reference_names: Iterable[str] = (),
) -> list[ReferenceSample]:
    """Select an explicit evaluation subset without changing the oracle data."""
    requested_names = {name.casefold() for name in reference_names}
    selected = [
        reference
        for reference in references
        if (not tier_a_only or (reference.tier or "").casefold() == "a")
        and (not requested_names or reference.name.casefold() in requested_names)
    ]
    if not selected:
        raise ValueError("the requested reference selection is empty")
    return selected


def normalize_open_key(value: str | None) -> str | None:
    """Convert a Traktor Open Key token to Sample Brain's canonical key form."""
    if value is None:
        return None
    token = value.strip().casefold()
    if not token or token == "none":
        return None
    canonical = _OPEN_KEY_TO_CANONICAL.get(token)
    if canonical is None:
        raise ValueError(f"unsupported Traktor Open Key token: {value!r}")
    parsed = parse_key_signature(canonical)
    if parsed is None or parsed.mode is None:  # defensive: table is contract data.
        raise ValueError(f"invalid canonical Open Key mapping: {canonical!r}")
    return format_key_signature(parsed.root, parsed.mode)


def _normalized_name(value: str) -> str:
    stem = PurePath(value.strip()).stem
    text = stem.replace("_", " ").replace("-", " ")
    return " ".join(text.casefold().split())


def _finite_positive(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


def best_bpm_relation(sample_brain_bpm: float | None, traktor_bpm: float | None) -> dict[str, float | str | None]:
    """Return the closest musically meaningful BPM relation.

    Relation describes Sample Brain relative to Traktor: a 156 BPM result against
    a 78 BPM reference is ``double_time``.  Errors are computed after applying
    that relation, never by raw numerical equality alone.
    """
    if not _finite_positive(sample_brain_bpm) or not _finite_positive(traktor_bpm):
        return {"relation": "no_result", "absolute_error": None, "relative_error": None}

    candidates = (("direct", 1.0), ("half_time", 0.5), ("double_time", 2.0))
    relation, factor = min(
        candidates,
        key=lambda item: abs(float(sample_brain_bpm) - float(traktor_bpm) * item[1]),
    )
    absolute_error = abs(float(sample_brain_bpm) - float(traktor_bpm) * factor)
    return {
        "relation": relation,
        "absolute_error": round(absolute_error, 6),
        "relative_error": round(absolute_error / (float(traktor_bpm) * factor), 6),
    }


def resolve_reference_samples(
    references: Iterable[ReferenceSample], library_samples: Iterable[LibrarySample]
) -> list[ResolvedReference]:
    """Resolve references by normalized basename and refuse ambiguous matches."""
    by_name: dict[str, list[LibrarySample]] = {}
    for sample in library_samples:
        by_name.setdefault(_normalized_name(sample.display_name or sample.path.name), []).append(sample)

    resolved: list[ResolvedReference] = []
    for reference in references:
        candidates = by_name.get(_normalized_name(reference.name), [])
        if reference.size_bytes is not None and len(candidates) > 1:
            candidates = [item for item in candidates if item.size_bytes == reference.size_bytes]
        if not candidates:
            resolved.append(ResolvedReference(reference, None, "UNRESOLVED_NAME_MATCH"))
        elif len(candidates) == 1:
            resolved.append(ResolvedReference(reference, candidates[0]))
        else:
            resolved.append(ResolvedReference(reference, None, "AMBIGUOUS_NAME_MATCH"))
    return resolved


def _comparison(sample_brain_key: str | None, traktor_key: str | None) -> dict[str, bool | None]:
    sample_brain = parse_key_signature(sample_brain_key)
    traktor = parse_key_signature(traktor_key)
    if sample_brain is None or traktor is None:
        return {"root_match": None, "mode_match": None, "full_key_match": False}
    root_match = sample_brain.root == traktor.root
    mode_match = sample_brain.mode == traktor.mode if (
        sample_brain.mode is not None and traktor.mode is not None
    ) else None
    return {
        "root_match": root_match,
        "mode_match": mode_match,
        "full_key_match": root_match and mode_match is True,
    }


def evaluate_reference_library(
    references: Iterable[ReferenceSample], library_samples: Iterable[LibrarySample]
) -> dict[str, Any]:
    """Analyze unambiguous local files and return a JSON-serializable report."""
    records: list[dict[str, Any]] = []
    for item in resolve_reference_samples(references, library_samples):
        reference = item.reference
        traktor_key = normalize_open_key(reference.open_key)
        if item.library_sample is None:
            records.append({
                "reference": asdict(reference),
                "file_identity": None,
                "resolution": item.reason,
                "traktor": {"canonical_key": traktor_key, "abstained": traktor_key is None},
                "sample_brain": None,
                "bpm": {
                    "sample_brain_bpm": None,
                    "traktor_bpm": reference.traktor_bpm,
                    **best_bpm_relation(None, reference.traktor_bpm),
                },
                "comparison": {"root_match": None, "mode_match": None, "full_key_match": False},
                "reason": item.reason,
            })
            continue

        features = extract_features(item.library_sample.path, duration=None)
        if features is None:
            records.append({
                "reference": asdict(reference),
                "file_identity": item.library_sample.path.name,
                "resolution": "resolved",
                "traktor": {"canonical_key": traktor_key, "abstained": traktor_key is None},
                "sample_brain": None,
                "bpm": {
                    "sample_brain_bpm": None,
                    "traktor_bpm": reference.traktor_bpm,
                    **best_bpm_relation(None, reference.traktor_bpm),
                },
                "comparison": {"root_match": None, "mode_match": None, "full_key_match": False},
                "reason": "ANALYSIS_FAILED",
            })
            continue

        parsed = parse_key_signature(features.key)
        canonical_key = (
            format_key_signature(parsed.root, parsed.mode) if parsed is not None else None
        )
        comparison = _comparison(canonical_key, traktor_key)
        abstained = parsed is None or parsed.mode is None
        reason = (
            "TRAKTOR_ABSTAINED" if traktor_key is None else
            "MODE_UNRESOLVED" if abstained else
            "FULL_KEY_MATCH" if comparison["full_key_match"] else
            "ROOT_MISMATCH" if comparison["root_match"] is False else
            "MODE_MISMATCH"
        )
        records.append({
            "reference": asdict(reference),
            "file_identity": item.library_sample.path.name,
            "resolution": "resolved",
            "traktor": {"canonical_key": traktor_key, "abstained": traktor_key is None},
            "sample_brain": {
                "root": parsed.root if parsed is not None else None,
                "mode": parsed.mode if parsed is not None else None,
                "canonical_key": canonical_key,
                "abstained": abstained,
                "key_confidence": features.key_conf,
                "mode_evidence": features.key_mode_evidence,
            },
            "bpm": {
                "sample_brain_bpm": features.bpm,
                "traktor_bpm": reference.traktor_bpm,
                **best_bpm_relation(features.bpm, reference.traktor_bpm),
            },
            "comparison": comparison,
            "reason": reason,
        })

    return {
        "schema_version": 1,
        "records": records,
        "summary": {
            "reference_count": len(records),
            "resolved_count": sum(record["resolution"] == "resolved" for record in records),
            "unresolved_count": sum(record["resolution"] != "resolved" for record in records),
            "sample_brain_mode_abstained_count": sum(
                record["sample_brain"] is not None and record["sample_brain"]["abstained"]
                for record in records
            ),
            "full_key_match_count": sum(record["comparison"]["full_key_match"] for record in records),
        },
    }


def load_reference_samples(path: Path) -> list[ReferenceSample]:
    """Load a caller-owned JSON oracle without copying it into the repository."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("records") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("reference JSON must be a list or an object with a records list")
    samples: list[ReferenceSample] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip():
            raise ValueError("every reference record needs a non-empty name")
        samples.append(ReferenceSample(
            name=row["name"],
            traktor_bpm=float(row["traktor_bpm"]) if row.get("traktor_bpm") is not None else None,
            open_key=row.get("open_key"),
            tier=row.get("tier"),
            size_bytes=int(row["size_bytes"]) if row.get("size_bytes") is not None else None,
        ))
    return samples


def load_workbench_library_samples(path: Path) -> list[LibrarySample]:
    """Read registered Workbench samples from an explicit SQLite path, read-only."""
    if not path.is_file():
        raise ValueError(f"Workbench library database does not exist: {path}")
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        rows = conn.execute(
            "SELECT original_path, display_name, size_bytes FROM samples ORDER BY original_path"
        ).fetchall()
    samples = []
    for original_path, display_name, size_bytes in rows:
        sample_path = Path(original_path)
        if sample_path.is_file():
            samples.append(LibrarySample(
                path=sample_path,
                display_name=display_name or sample_path.name,
                size_bytes=size_bytes,
            ))
    return samples


def _outside_checkout(path: Path, checkout: Path) -> bool:
    return not path.resolve().is_relative_to(checkout)


def sanitize_report(report: dict[str, Any]) -> dict[str, Any]:
    """Remove local file identities before a report leaves the operator host."""
    sanitized_records: list[dict[str, Any]] = []
    for index, record in enumerate(report["records"], start=1):
        reference = record["reference"]
        sanitized_records.append({
            "sample_alias": f"sample_{index:03d}",
            "reference": {
                "traktor_bpm": reference["traktor_bpm"],
                "open_key": reference["open_key"],
                "tier": reference["tier"],
            },
            "resolution": record["resolution"],
            "traktor": record["traktor"],
            "sample_brain": record["sample_brain"],
            "bpm": record["bpm"],
            "comparison": record["comparison"],
            "reason": record["reason"],
        })
    return {
        "schema_version": report["schema_version"],
        "selection": report.get("selection", {}),
        "summary": report["summary"],
        "records": sanitized_records,
    }


def run_local_evaluation(
    *,
    reference_json: Path,
    workbench_db: Path,
    output_json: Path,
    sanitized_output_json: Path | None = None,
    tier_a_only: bool = False,
    reference_names: Iterable[str] = (),
) -> dict[str, Any]:
    """Run the evaluation using only explicit external local paths."""
    selected_names = tuple(reference_names)
    checkout = Path.cwd().resolve()
    paths = [
        ("reference JSON", reference_json),
        ("Workbench library database", workbench_db),
        ("output JSON", output_json),
    ]
    if sanitized_output_json is not None:
        paths.append(("sanitized output JSON", sanitized_output_json))
    for label, path in paths:
        if not _outside_checkout(path, checkout):
            raise ValueError(f"{label} must be outside the repository checkout")
    selected = select_references(
        load_reference_samples(reference_json),
        tier_a_only=tier_a_only,
        reference_names=selected_names,
    )
    report = evaluate_reference_library(selected, load_workbench_library_samples(workbench_db))
    report["selection"] = {
        "tier_a_only": tier_a_only,
        "reference_names": sorted({name.casefold() for name in selected_names}),
    }
    output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if sanitized_output_json is not None:
        sanitized_output_json.write_text(
            json.dumps(sanitize_report(report), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate private local Traktor references against Workbench audio.")
    parser.add_argument("--reference-json", type=Path, required=True)
    parser.add_argument("--workbench-db", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument(
        "--sanitized-output-json",
        type=Path,
        help="Optional path for a report without local sample identities; safe to return to Codex.",
    )
    parser.add_argument("--tier-a-only", action="store_true")
    parser.add_argument(
        "--reference-name",
        action="append",
        default=[],
        help="Exact reference name to include; repeatable and combined with --tier-a-only.",
    )
    args = parser.parse_args(argv)
    report = run_local_evaluation(
        reference_json=args.reference_json,
        workbench_db=args.workbench_db,
        output_json=args.output_json,
        sanitized_output_json=args.sanitized_output_json,
        tier_a_only=args.tier_a_only,
        reference_names=args.reference_name,
    )
    print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
