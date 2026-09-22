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

import numpy as np

from .analyze import extract_features
from .key_profile_audio_calibration import extract_harmonic_chroma_evidence
from .key_signature import format_key_signature, parse_key_signature
from .key_profile_analysis import (
    audio_domain_calibration_reference,
    characterize_synthetic_gate,
    characterize_synthetic_margins,
    gate_ranked_key_profile,
    rank_key_profiles,
)


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


def _candidate_from_features(features: Any) -> dict[str, Any]:
    chroma_blob = getattr(features, "chroma_mean", None)
    chroma = np.frombuffer(chroma_blob, dtype=np.float32) if chroma_blob else ()
    ranking = rank_key_profiles(chroma)
    return {
        "status": ranking.status,
        "root": ranking.root,
        "mode": ranking.mode,
        "canonical_key": ranking.canonical_key,
        "best_score": ranking.best_score,
        "runner_up_score": ranking.runner_up_score,
        "score_margin": ranking.margin,
        "next_distinct_root_score": ranking.next_distinct_root_score,
        "next_distinct_root_margin": ranking.next_distinct_root_margin,
        "evidence_kind": ranking.evidence_kind,
        "evidence_version": ranking.evidence_version,
    }


def _gated_candidate_from_features(features: Any) -> dict[str, Any]:
    chroma_mean_blob = getattr(features, "chroma_mean", None)
    chroma_std_blob = getattr(features, "chroma_std", None)
    chroma_mean = np.frombuffer(chroma_mean_blob, dtype=np.float32) if chroma_mean_blob else ()
    chroma_std = np.frombuffer(chroma_std_blob, dtype=np.float32) if chroma_std_blob else ()
    result = gate_ranked_key_profile(chroma_mean, chroma_std)
    evidence = result.evidence
    return {
        "status": result.status,
        "root": result.root,
        "mode": result.mode,
        "canonical_key": result.canonical_key,
        "abstention_reasons": list(result.abstention_reasons),
        "gate_evidence": {
            "best_score": evidence.best_score if evidence is not None else None,
            "runner_up_score": evidence.runner_up_score if evidence is not None else None,
            "margin": evidence.margin if evidence is not None else None,
            "normalized_entropy": evidence.normalized_entropy if evidence is not None else None,
            "dominant_pitch_class_concentration": (
                evidence.dominant_pitch_class_concentration if evidence is not None else None
            ),
            "temporal_stability": evidence.temporal_stability if evidence is not None else None,
            "conditions": dict(evidence.conditions) if evidence is not None else {},
            "gate_name": result.gate_name,
            "gate_version": result.gate_version,
        },
    }


def _harmonic_candidate(path: Path) -> dict[str, Any]:
    evidence = extract_harmonic_chroma_evidence(path)
    ranking = rank_key_profiles(evidence.chroma_mean if evidence.chroma_mean is not None else ())
    return {
        "status": ranking.status, "root": ranking.root, "mode": ranking.mode,
        "canonical_key": ranking.canonical_key, "best_score": ranking.best_score,
        "runner_up_score": ranking.runner_up_score, "margin": ranking.margin,
        "next_distinct_root_margin": ranking.next_distinct_root_margin,
        "harmonic_rms": evidence.harmonic_rms, "percussive_rms": evidence.percussive_rms,
        "harmonic_energy_fraction": evidence.harmonic_energy_fraction,
        "evidence_kind": "hpss_harmonic_" + ranking.evidence_kind,
        "evidence_version": ranking.evidence_version,
    }


def _agreement(count: int, comparable: int) -> dict[str, int | None]:
    return {"agreement_count": count, "comparable_count": comparable}


def _margin_distribution(records: Iterable[dict[str, Any]]) -> dict[str, float | int | None]:
    margins = [
        float(record["candidate"]["score_margin"])
        for record in records
        if record.get("candidate") is not None
        and record["candidate"]["score_margin"] is not None
    ]
    if not margins:
        return {"count": 0, "min": None, "median": None, "p90": None, "max": None}
    values = np.asarray(margins, dtype=np.float64)
    return {
        "count": int(values.size),
        "min": float(np.min(values)),
        "median": float(np.median(values)),
        "p90": float(np.percentile(values, 90)),
        "max": float(np.max(values)),
    }


def _ab_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    resolved = [
        record
        for record in records
        if record["resolution"] == "resolved"
        and record["sample_brain"] is not None
        and record["candidate"] is not None
    ]
    keyed = [record for record in resolved if not record["traktor"]["abstained"]]
    baseline_root = [record["comparison"]["root_match"] for record in keyed]
    candidate_root = [record["candidate_comparison"]["root_match"] for record in keyed]
    baseline_mode = [record["comparison"]["mode_match"] for record in keyed]
    candidate_mode_resolved = [
        record["candidate_comparison"]["mode_match"]
        for record in keyed
        if record["candidate"]["status"] == "resolved"
    ]
    baseline_full = [record["comparison"]["full_key_match"] for record in keyed]
    candidate_full_resolved = [
        record["candidate_comparison"]["full_key_match"]
        for record in keyed
        if record["candidate"]["status"] == "resolved"
    ]
    candidate_ranked_full = [record["candidate_comparison"]["full_key_match"] for record in keyed]
    gated_resolved = [record for record in keyed if record["candidate_gated"]["status"] == "resolved"]
    gated_root = [record["candidate_gated_comparison"]["root_match"] for record in gated_resolved]
    gated_mode = [record["candidate_gated_comparison"]["mode_match"] for record in gated_resolved]
    gated_full = [record["candidate_gated_comparison"]["full_key_match"] for record in gated_resolved]
    baseline_root_count = sum(item is True for item in baseline_root)
    candidate_root_count = sum(item is True for item in candidate_root)
    baseline_full_count = sum(item is True for item in baseline_full)
    candidate_ranked_full_count = sum(item is True for item in candidate_ranked_full)
    negative_controls = [record for record in resolved if record["traktor"]["abstained"]]
    return {
        "baseline": {
            "root_agreement": _agreement(baseline_root_count, len(baseline_root)),
            "mode_agreement": _agreement(sum(item is True for item in baseline_mode), sum(item is not None for item in baseline_mode)),
            "full_key_agreement": _agreement(baseline_full_count, len(baseline_full)),
            "abstention_count": sum(record["sample_brain"]["abstained"] for record in resolved if record["sample_brain"] is not None),
        },
        "candidate": {
            "root_agreement_ranked": _agreement(candidate_root_count, len(candidate_root)),
            "mode_agreement_resolved": _agreement(sum(item is True for item in candidate_mode_resolved), len(candidate_mode_resolved)),
            "full_key_agreement_resolved": _agreement(sum(item is True for item in candidate_full_resolved), len(candidate_full_resolved)),
            "full_key_agreement_ranked": _agreement(candidate_ranked_full_count, len(candidate_ranked_full)),
            "status_counts": {
                "resolved": sum(record["candidate"]["status"] == "resolved" for record in resolved),
                "abstained": sum(record["candidate"]["status"] == "abstained" for record in resolved),
                "ranked_only": sum(record["candidate"]["status"] == "ranked_only" for record in resolved),
            },
        },
        "candidate_gated": {
            "root_agreement_resolved": _agreement(sum(item is True for item in gated_root), len(gated_root)),
            "mode_agreement_resolved": _agreement(
                sum(item is True for item in gated_mode), sum(item is not None for item in gated_mode)
            ),
            "full_key_agreement_resolved": _agreement(sum(item is True for item in gated_full), len(gated_full)),
            "status_counts": {
                "resolved": sum(record["candidate_gated"]["status"] == "resolved" for record in resolved),
                "abstained": sum(record["candidate_gated"]["status"] == "abstained" for record in resolved),
            },
        },
        "delta": {
            "root_agreement_ranked": candidate_root_count - baseline_root_count,
            "full_key_agreement_ranked": candidate_ranked_full_count - baseline_full_count,
            "baseline_correct_to_candidate_wrong_root": sum(
                baseline is True and candidate is False
                for baseline, candidate in zip(baseline_root, candidate_root)
            ),
            "baseline_wrong_to_candidate_correct_root": sum(
                baseline is False and candidate is True
                for baseline, candidate in zip(baseline_root, candidate_root)
            ),
            "baseline_correct_to_gated_wrong_root": sum(
                record["comparison"]["root_match"] is True
                and record["candidate_gated_comparison"]["root_match"] is False
                for record in gated_resolved
            ),
            "baseline_wrong_to_gated_correct_root": sum(
                record["comparison"]["root_match"] is False
                and record["candidate_gated_comparison"]["root_match"] is True
                for record in gated_resolved
            ),
            "baseline_correct_to_gated_abstained": sum(
                record["comparison"]["root_match"] is True
                and record["candidate_gated"]["status"] == "abstained"
                for record in keyed
            ),
        },
        "negative_controls": {
            "resolved_reference_abstentions": len(negative_controls),
            "candidate_resolved_when_reference_abstained": sum(
                record["candidate"]["status"] == "resolved" for record in negative_controls
            ),
            "candidate_ranked_only_when_reference_abstained": sum(
                record["candidate"]["status"] == "ranked_only" for record in negative_controls
            ),
            "candidate_abstained_when_reference_abstained": sum(
                record["candidate"]["status"] == "abstained" for record in negative_controls
            ),
            "candidate_gated_resolved_when_reference_abstained": sum(
                record["candidate_gated"]["status"] == "resolved" for record in negative_controls
            ),
            "candidate_gated_abstained_when_reference_abstained": sum(
                record["candidate_gated"]["status"] == "abstained" for record in negative_controls
            ),
        },
        "candidate_margin_distribution": _margin_distribution(resolved),
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
                "baseline": None,
                "candidate": None,
                "candidate_profile": None,
                "candidate_harmonic_profile": None,
                "candidate_gated": None,
                "bpm": {
                    "sample_brain_bpm": None,
                    "traktor_bpm": reference.traktor_bpm,
                    **best_bpm_relation(None, reference.traktor_bpm),
                },
                "comparison": {"root_match": None, "mode_match": None, "full_key_match": False},
                "candidate_comparison": {"root_match": None, "mode_match": None, "full_key_match": False},
                "candidate_gated_comparison": {"root_match": None, "mode_match": None, "full_key_match": False},
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
                "baseline": None,
                "candidate": None,
                "candidate_profile": None,
                "candidate_harmonic_profile": None,
                "candidate_gated": None,
                "bpm": {
                    "sample_brain_bpm": None,
                    "traktor_bpm": reference.traktor_bpm,
                    **best_bpm_relation(None, reference.traktor_bpm),
                },
                "comparison": {"root_match": None, "mode_match": None, "full_key_match": False},
                "candidate_comparison": {"root_match": None, "mode_match": None, "full_key_match": False},
                "candidate_gated_comparison": {"root_match": None, "mode_match": None, "full_key_match": False},
                "reason": "ANALYSIS_FAILED",
            })
            continue

        parsed = parse_key_signature(features.key)
        canonical_key = (
            format_key_signature(parsed.root, parsed.mode) if parsed is not None else None
        )
        comparison = _comparison(canonical_key, traktor_key)
        baseline = {
            "root": parsed.root if parsed is not None else None,
            "mode": parsed.mode if parsed is not None else None,
            "canonical_key": canonical_key,
            "abstained": parsed is None or parsed.mode is None,
            "key_confidence": features.key_conf,
            "mode_evidence": features.key_mode_evidence,
        }
        candidate = _candidate_from_features(features)
        harmonic_candidate = _harmonic_candidate(item.library_sample.path)
        candidate_gated = _gated_candidate_from_features(features)
        candidate_comparison = _comparison(candidate["canonical_key"], traktor_key)
        candidate_gated_comparison = _comparison(candidate_gated["canonical_key"], traktor_key)
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
            "sample_brain": baseline,
            "baseline": baseline,
            "candidate": candidate,
            "candidate_profile": candidate,
            "candidate_harmonic_profile": harmonic_candidate,
            "candidate_gated": candidate_gated,
            "bpm": {
                "sample_brain_bpm": features.bpm,
                "traktor_bpm": reference.traktor_bpm,
                **best_bpm_relation(features.bpm, reference.traktor_bpm),
            },
            "comparison": comparison,
            "candidate_comparison": candidate_comparison,
            "candidate_gated_comparison": candidate_gated_comparison,
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
        "ab_comparison": {
            "overall": _ab_summary(records),
            "tier_a": _ab_summary([
                record for record in records if (record["reference"].get("tier") or "").casefold() == "a"
            ]),
            "candidate_synthetic_margin_distribution": characterize_synthetic_margins(),
            "candidate_synthetic_gate_characterization": characterize_synthetic_gate(),
            "candidate_audio_domain_gate_characterization": audio_domain_calibration_reference(),
            "real_candidate_margin_distribution": {
                "tier_a": _margin_distribution([
                    record for record in records if (record["reference"].get("tier") or "").casefold() == "a"
                ]),
                "negative_controls": _margin_distribution([
                    record for record in records if record["traktor"]["abstained"]
                ]),
            },
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
            "baseline": record["baseline"],
            "candidate": record["candidate"],
            "candidate_profile": record["candidate_profile"],
            "candidate_harmonic_profile": record["candidate_harmonic_profile"],
            "candidate_gated": record["candidate_gated"],
            "bpm": record["bpm"],
            "comparison": record["comparison"],
            "candidate_comparison": record["candidate_comparison"],
            "candidate_gated_comparison": record["candidate_gated_comparison"],
            "reason": record["reason"],
        })
    return {
        "schema_version": report["schema_version"],
        "selection": report.get("selection", {}),
        "summary": report["summary"],
        "ab_comparison": report.get("ab_comparison", {}),
        "records": sanitized_records,
    }


def format_ab_handoff(report: dict[str, Any]) -> str:
    """Format aggregate-only A/B evidence for the Codex handoff."""
    overall = report["ab_comparison"]["overall"]
    tier_a = report["ab_comparison"]["tier_a"]

    def agreement(value: dict[str, int | None]) -> str:
        return f"{value['agreement_count']}/{value['comparable_count']}"

    return "\n".join([
        "KEY_PROFILE_AB_HANDOFF_V1",
        f"reference_count={report['summary']['reference_count']}",
        f"resolved_count={report['summary']['resolved_count']}",
        f"baseline_root_agreement={agreement(overall['baseline']['root_agreement'])}",
        f"candidate_ranked_root_agreement={agreement(overall['candidate']['root_agreement_ranked'])}",
        f"ranked_root_agreement_delta={overall['delta']['root_agreement_ranked']}",
        f"tier_a_baseline_root_agreement={agreement(tier_a['baseline']['root_agreement'])}",
        f"tier_a_candidate_ranked_root_agreement={agreement(tier_a['candidate']['root_agreement_ranked'])}",
        f"candidate_status_counts={json.dumps(overall['candidate']['status_counts'], sort_keys=True)}",
        f"gated_status_counts={json.dumps(overall['candidate_gated']['status_counts'], sort_keys=True)}",
        f"gated_root_agreement={agreement(overall['candidate_gated']['root_agreement_resolved'])}",
        f"tier_a_gated_root_agreement={agreement(tier_a['candidate_gated']['root_agreement_resolved'])}",
        f"negative_controls={json.dumps(overall['negative_controls'], sort_keys=True)}",
        f"synthetic_margins={json.dumps(report['ab_comparison']['candidate_synthetic_margin_distribution'], sort_keys=True)}",
        f"synthetic_gate={json.dumps(report['ab_comparison']['candidate_synthetic_gate_characterization']['gate_candidates'], sort_keys=True)}",
        f"audio_domain_gate={json.dumps(report['ab_comparison']['candidate_audio_domain_gate_characterization'], sort_keys=True)}",
        f"real_tier_a_margins={json.dumps(report['ab_comparison']['real_candidate_margin_distribution']['tier_a'], sort_keys=True)}",
        "candidate_is_evaluation_only=ranked_only_is_not_a_production_key_claim",
        "",
    ])


def run_local_evaluation(
    *,
    reference_json: Path,
    workbench_db: Path,
    output_json: Path,
    sanitized_output_json: Path | None = None,
    handoff_text: Path | None = None,
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
    if handoff_text is not None:
        paths.append(("handoff text", handoff_text))
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
    if handoff_text is not None:
        handoff_text.write_text(format_ab_handoff(report), encoding="utf-8")
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
    parser.add_argument(
        "--handoff-text",
        type=Path,
        help="Optional aggregate-only, path-free text summary for the Codex handoff.",
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
        handoff_text=args.handoff_text,
        tier_a_only=args.tier_a_only,
        reference_names=args.reference_name,
    )
    print(json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
