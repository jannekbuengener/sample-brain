"""AQ5 relevance labels / hard-negatives / query-set freeze (#1009).

Adopts existing ADR-0005 Tier-A/Tier-B synthetic golden suites under a named
benchmark identity with CALIBRATION/TEST query roles and leak audits.
Does not change search algorithms or invent graded relevance labels.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from src.search_quality_contract import (
    SearchQualityContractError,
    is_private_absolute_path,
    validate_search_quality_suite,
)

BENCHMARK_ID = "sample-brain.aq5.relevance.adr0005-golden.v1"
DOCUMENT_TYPE = "sample-brain.aq5.relevance-benchmark.v1"
BENCHMARK_VERSION = "1.0.0"
LABEL_SOURCE = "adr0005_synthetic_binary"
SPLITS: frozenset[str] = frozenset({"CALIBRATION", "TEST"})

TIER_A_SUITE_RELPATH = Path("tests/fixtures/search_quality/golden_v1.yaml")
TIER_B_SUITE_RELPATH = Path("tests/fixtures/search_quality/golden_v2_clap.yaml")
EXCLUDED_SPIKE_SUITE_RELPATH = Path(
    "tests/fixtures/search_quality/golden_v2_clap_vocal_proxy_spike.yaml"
)
PARTITION_OVERLAY_RELPATH = Path(
    "tests/fixtures/search_quality/aq5_relevance_benchmark_v1.yaml"
)

TIER_B_QUERY_FAMILIES: tuple[str, ...] = (
    "kick_snare_perc",
    "pad_texture",
    "riser_impact",
    "dry_wet",
    "vocal_no_vocal",
    "genre_mood",
)

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]

_HOLD_STUBS: tuple[dict[str, str], ...] = (
    {"item": "graded_relevance_ndcg", "status": "HOLD"},
    {"item": "vocal_no_vocal_production_claim", "status": "HOLD"},
    {"item": "genre_mood_production_claim", "status": "HOLD"},
    {"item": "vocal_proxy_spike_suite", "status": "HOLD"},
    {"item": "private_producer_reality_check_queries", "status": "HOLD"},
)


class Aq5RelevanceBenchmarkError(ValueError):
    """Raised when the AQ5 relevance freeze mapping or suites are invalid."""


def assert_work_dir_outside_repo(path: Path, repo_root: Path) -> None:
    """Reject writes inside the repository tree."""
    target = path.resolve()
    root = repo_root.resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return
    raise ValueError(f"work_dir must be outside repo: {target}")


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _fingerprint(payload: Any) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _load_suite(repo_root: Path, suite_rel: Path) -> dict[str, Any]:
    suite_path = repo_root / suite_rel
    if not suite_path.is_file():
        raise Aq5RelevanceBenchmarkError(f"missing suite: {suite_rel.as_posix()}")
    suite = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
    if not isinstance(suite, dict):
        raise Aq5RelevanceBenchmarkError(f"suite must be a mapping: {suite_rel}")
    try:
        validate_search_quality_suite(suite)
    except SearchQualityContractError as exc:
        raise Aq5RelevanceBenchmarkError(f"{suite_rel.as_posix()}: {exc}") from exc
    return suite


def _collect_private_paths(suite: dict[str, Any], *, suite_name: str) -> list[str]:
    findings: list[str] = []
    catalog = suite.get("catalog") or {}
    for sample in catalog.get("samples") or []:
        path = sample.get("path")
        if path and is_private_absolute_path(str(path)):
            findings.append(f"{suite_name}:catalog:{sample.get('id')}:{path}")
    for query in suite.get("queries") or []:
        for field in ("query_audio", "path"):
            value = query.get(field)
            if value and is_private_absolute_path(str(value)):
                findings.append(f"{suite_name}:query:{query.get('id')}:{field}:{value}")
    return findings


def _load_partition_overlay(
    repo_root: Path,
    overlay_path: Path | None,
) -> dict[str, dict[str, list[str]]]:
    path = overlay_path if overlay_path is not None else repo_root / PARTITION_OVERLAY_RELPATH
    if not path.is_file():
        raise Aq5RelevanceBenchmarkError(f"missing partition overlay: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise Aq5RelevanceBenchmarkError("partition overlay must be a mapping")
    if payload.get("benchmark_id") != BENCHMARK_ID:
        raise Aq5RelevanceBenchmarkError(
            f"partition overlay benchmark_id mismatch: {payload.get('benchmark_id')!r}"
        )
    partitions = payload.get("partitions")
    if not isinstance(partitions, dict):
        raise Aq5RelevanceBenchmarkError("partition overlay requires partitions mapping")

    normalized: dict[str, dict[str, list[str]]] = {}
    for suite_key in ("tier_a", "tier_b"):
        block = partitions.get(suite_key)
        if not isinstance(block, dict):
            raise Aq5RelevanceBenchmarkError(
                f"partition overlay missing suite block: {suite_key}"
            )
        suite_map: dict[str, list[str]] = {}
        for split in ("CALIBRATION", "TEST"):
            raw_ids = block.get(split)
            if not isinstance(raw_ids, list):
                raise Aq5RelevanceBenchmarkError(
                    f"partition overlay {suite_key}.{split} must be a list"
                )
            ids = [str(item) for item in raw_ids]
            if len(ids) != len(set(ids)):
                raise Aq5RelevanceBenchmarkError(
                    f"partition overlay {suite_key}.{split} has duplicate query ids"
                )
            suite_map[split] = ids
        overlap = set(suite_map["CALIBRATION"]) & set(suite_map["TEST"])
        if overlap:
            raise Aq5RelevanceBenchmarkError(
                f"partition overlay {suite_key} CALIBRATION/TEST overlap: "
                f"{sorted(overlap)}"
            )
        normalized[suite_key] = suite_map
    return normalized


def _split_for_query(
    partitions: dict[str, dict[str, list[str]]],
    *,
    suite_key: str,
    query_id: str,
) -> str:
    for split, ids in partitions[suite_key].items():
        if query_id in ids:
            return split
    raise Aq5RelevanceBenchmarkError(
        f"partition coverage incomplete for {suite_key}:{query_id}"
    )


def _query_rows_for_suite(
    *,
    suite_key: str,
    suite: dict[str, Any],
    partitions: dict[str, dict[str, list[str]]],
) -> list[dict[str, Any]]:
    suite_ids = {str(q["id"]) for q in suite.get("queries") or []}
    mapped_ids = set(partitions[suite_key]["CALIBRATION"]) | set(
        partitions[suite_key]["TEST"]
    )
    if mapped_ids != suite_ids:
        missing = sorted(suite_ids - mapped_ids)
        extra = sorted(mapped_ids - suite_ids)
        raise Aq5RelevanceBenchmarkError(
            f"partition coverage mismatch for {suite_key} "
            f"(missing={missing}, extra={extra})"
        )

    rows: list[dict[str, Any]] = []
    for raw in suite.get("queries") or []:
        query_id = str(raw["id"])
        split = _split_for_query(partitions, suite_key=suite_key, query_id=query_id)
        relevant = [int(x) for x in (raw.get("relevant_sample_ids") or [])]
        negatives = [int(x) for x in (raw.get("negative_sample_ids") or [])]
        if not relevant:
            raise Aq5RelevanceBenchmarkError(
                f"{suite_key}:{query_id}: relevant_sample_ids must be non-empty"
            )
        if suite_key == "tier_b" and not negatives:
            raise Aq5RelevanceBenchmarkError(
                f"{suite_key}:{query_id}: Tier-B freeze requires hard negatives"
            )
        if raw.get("relevance_grades") or raw.get("graded_relevance"):
            raise Aq5RelevanceBenchmarkError(
                f"{suite_key}:{query_id}: graded labels are HOLD and must be absent"
            )
        family = str(raw.get("query_class") or "tier_a")
        row: dict[str, Any] = {
            "query_key": f"{suite_key}:{query_id}",
            "query_id": query_id,
            "suite": suite_key,
            "mode": str(raw.get("mode")),
            "query_family": family,
            "split": split,
            "relevance_scheme": "binary",
            "graded_labels": None,
            "relevant_sample_ids": relevant,
            "negative_sample_ids": negatives,
            "label_source": LABEL_SOURCE,
            "join_key": {
                "analysis_eval_record_id": f"{suite_key}:{query_id}",
                "note": "query_key is the portable #956 record_id join key; no host paths",
            },
        }
        if raw.get("query_audio_fixture"):
            row["query_audio_fixture"] = str(raw["query_audio_fixture"])
        if raw.get("query_style"):
            row["query_style"] = str(raw["query_style"])
        if raw.get("text"):
            # Keep text only for leakage audit fingerprinting; never require private
            # producer strings. Public synthetic suite text is already committed.
            row["query_text"] = str(raw["text"])
        rows.append(row)
    return rows


def _leakage_audit(rows: list[dict[str, Any]], private_paths: list[str]) -> dict[str, Any]:
    keys = [r["query_key"] for r in rows]
    duplicate_query_keys = sorted(
        key for key, count in Counter(keys).items() if count > 1
    )

    relevant_negative_overlap: list[str] = []
    for row in rows:
        overlap = set(row["relevant_sample_ids"]) & set(row["negative_sample_ids"])
        if overlap:
            relevant_negative_overlap.append(
                f"{row['query_key']}:{sorted(overlap)}"
            )

    text_by_split: dict[str, set[str]] = {"CALIBRATION": set(), "TEST": set()}
    audio_by_split: dict[str, set[str]] = {"CALIBRATION": set(), "TEST": set()}
    for row in rows:
        text = row.get("query_text")
        if text:
            text_by_split[row["split"]].add(str(text).strip().lower())
        fixture = row.get("query_audio_fixture")
        if fixture:
            audio_by_split[row["split"]].add(str(fixture))

    cross_split_query_text_collisions = sorted(
        text_by_split["CALIBRATION"] & text_by_split["TEST"]
    )
    cross_split_audio_fixture_collisions = sorted(
        audio_by_split["CALIBRATION"] & audio_by_split["TEST"]
    )

    return {
        "duplicate_query_keys": duplicate_query_keys,
        "relevant_negative_overlap": relevant_negative_overlap,
        "private_absolute_paths": private_paths,
        "cross_split_query_text_collisions": cross_split_query_text_collisions,
        "cross_split_audio_fixture_collisions": cross_split_audio_fixture_collisions,
        "partition_coverage_ok": not duplicate_query_keys
        and not relevant_negative_overlap
        and not private_paths
        and not cross_split_query_text_collisions
        and not cross_split_audio_fixture_collisions,
    }


def build_aq5_relevance_benchmark_manifest(
    *,
    repo_root: Path | str | None = None,
    partition_overlay_path: Path | str | None = None,
) -> dict[str, Any]:
    """Validate suites + partition overlay and return the frozen audit manifest."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    overlay = (
        Path(partition_overlay_path) if partition_overlay_path is not None else None
    )
    partitions = _load_partition_overlay(root, overlay)

    tier_a = _load_suite(root, TIER_A_SUITE_RELPATH)
    tier_b = _load_suite(root, TIER_B_SUITE_RELPATH)
    private_paths = _collect_private_paths(tier_a, suite_name="tier_a") + _collect_private_paths(
        tier_b, suite_name="tier_b"
    )

    rows = _query_rows_for_suite(
        suite_key="tier_a", suite=tier_a, partitions=partitions
    ) + _query_rows_for_suite(suite_key="tier_b", suite=tier_b, partitions=partitions)

    support = {
        "split": dict(Counter(r["split"] for r in rows)),
        "suite": dict(Counter(r["suite"] for r in rows)),
        "mode": dict(Counter(r["mode"] for r in rows)),
        "query_family": dict(Counter(r["query_family"] for r in rows)),
    }
    for family in TIER_B_QUERY_FAMILIES:
        if support["query_family"].get(family, 0) < 1:
            raise Aq5RelevanceBenchmarkError(
                f"query family {family} has zero support in freeze"
            )

    leakage = _leakage_audit(rows, private_paths)
    if not leakage["partition_coverage_ok"]:
        raise Aq5RelevanceBenchmarkError(
            f"leakage audit failed: {json.dumps(leakage, sort_keys=True)}"
        )

    # Portable manifest omits raw query_text (kept only for audit collisions).
    portable_rows: list[dict[str, Any]] = []
    for row in rows:
        portable = dict(row)
        portable.pop("query_text", None)
        portable_rows.append(portable)

    return {
        "document_type": DOCUMENT_TYPE,
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "label_source": LABEL_SOURCE,
        "status": "AQ5_RELEVANCE_BENCHMARK_FROZEN",
        "graded_relevance": {"status": "HOLD"},
        "ndcg_eligibility": "HOLD",
        "partition_policy": {
            "CALIBRATION": "DEVELOPMENT/CALIBRATION",
            "TEST": "TEST/HOLDOUT",
            "catalog_scope": (
                "shared candidate inventory per suite; split applies to queries only"
            ),
        },
        "hold_stubs": [dict(item) for item in _HOLD_STUBS],
        "excluded_surfaces": [
            {
                "suite": "vocal_proxy_spike",
                "status": "HOLD",
                "suite_path": EXCLUDED_SPIKE_SUITE_RELPATH.as_posix(),
                "reason": "HOLD_VOCAL_PROXY_FAILED historical spike; not AQ5 freeze truth",
            }
        ],
        "support_counts": support,
        "leakage_audit": leakage,
        "queries": portable_rows,
    }


def audit_aq5_relevance_benchmark(
    *,
    repo_root: Path | str | None = None,
    partition_overlay_path: Path | str | None = None,
) -> dict[str, Any]:
    """Return reproducible fingerprints for the frozen query/partition identity."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    overlay = (
        Path(partition_overlay_path) if partition_overlay_path is not None else None
    )
    partitions = _load_partition_overlay(root, overlay)
    manifest = build_aq5_relevance_benchmark_manifest(
        repo_root=root,
        partition_overlay_path=overlay,
    )
    query_identity = [
        {
            "query_key": q["query_key"],
            "split": q["split"],
            "suite": q["suite"],
            "mode": q["mode"],
            "query_family": q["query_family"],
            "relevant_sample_ids": q["relevant_sample_ids"],
            "negative_sample_ids": q["negative_sample_ids"],
        }
        for q in manifest["queries"]
    ]
    return {
        "benchmark_id": BENCHMARK_ID,
        "status": manifest["status"],
        "partition_fingerprint": _fingerprint(partitions),
        "query_set_fingerprint": _fingerprint(query_identity),
        "leakage_audit": manifest["leakage_audit"],
        "support_counts": manifest["support_counts"],
    }


def write_aq5_relevance_benchmark_manifest(
    output_path: Path | str,
    *,
    repo_root: Path | str | None = None,
    work_dir_guard_root: Path | str | None = None,
    partition_overlay_path: Path | str | None = None,
) -> dict[str, Any]:
    """Write the frozen manifest JSON outside the repository tree."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    guard = (
        Path(work_dir_guard_root) if work_dir_guard_root is not None else root
    )
    target = Path(output_path)
    assert_work_dir_outside_repo(target, guard)
    manifest = build_aq5_relevance_benchmark_manifest(
        repo_root=root,
        partition_overlay_path=partition_overlay_path,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_canonical_json(manifest), encoding="utf-8")
    return manifest


__all__ = [
    "BENCHMARK_ID",
    "BENCHMARK_VERSION",
    "DOCUMENT_TYPE",
    "EXCLUDED_SPIKE_SUITE_RELPATH",
    "LABEL_SOURCE",
    "PARTITION_OVERLAY_RELPATH",
    "SPLITS",
    "TIER_A_SUITE_RELPATH",
    "TIER_B_QUERY_FAMILIES",
    "TIER_B_SUITE_RELPATH",
    "Aq5RelevanceBenchmarkError",
    "assert_work_dir_outside_repo",
    "audit_aq5_relevance_benchmark",
    "build_aq5_relevance_benchmark_manifest",
    "write_aq5_relevance_benchmark_manifest",
]
