"""AQ6 Harmonic Match relation/weight candidate comparison (#1019).

Frozen ≤4 thin ranking adapters over the current Harmonic Match surface.
Reuses #1016 labels + #1018 scoring helpers. Theory plane (#1015/#1017) is a
hard gate that ranking metrics cannot average away. No production switch.
CALIBRATION may narrate exploration; TEST/HOLDOUT stay frozen evidence only.
External JSON evidence only.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .aq6_harmonic_ranking_baseline import (
    DOCUMENT_TYPE as BASELINE_DOCUMENT_TYPE,
    SURFACE as BASELINE_SURFACE,
    UPSTREAM_STATES,
    WEIGHTS as BASELINE_WEIGHTS,
    aggregate_query_metrics,
    prove_missing_evidence_not_forced_certainty,
    row_from_fixture_item,
    score_ranked_query,
)
from .aq6_harmonic_ranking_relevance import (
    BENCHMARK_ID,
    BENCHMARK_VERSION,
    DOMAIN_TOKEN as RANKING_DOMAIN_TOKEN,
    FIXTURE_RELPATH,
    load_relevance_benchmark_fixture,
)
from .aq6_harmonic_theory_baseline import (
    DOMAIN_TOKEN as THEORY_DOMAIN_TOKEN,
    SURFACE as THEORY_SURFACE,
    product_prediction as theory_product_prediction,
)
from .aq6_harmonic_theory_truth_table import (
    FIXTURE_RELPATH as THEORY_FIXTURE_RELPATH,
    TRUTH_TABLE_ID,
    load_truth_table_fixture,
    score_theory_predictions,
)
from .key_signature import parse_key_signature
from .workbench_controller import WorkbenchRow
from .workbench_harmony import (
    HarmonyRelation,
    HarmonySuggestion,
    _bpm_score_from_row,
    _key_score_from_relation,
    _minimal_signed_shift,
    _parse_key_from_row,
    determine_relation,
    find_harmony_matches,
    harmonic_match_key_for_row,
)

DOCUMENT_TYPE = "sample-brain.aq6.harmonic-ranking-candidate-compare.v1"
SCHEMA_VERSION = "1.0.0"
DOMAIN_TOKEN = RANKING_DOMAIN_TOKEN
EXIT_REPRODUCIBLE = "AQ6_HARMONIC_CANDIDATE_COMPARE_REPRODUCIBLE"
EXIT_NO_JUSTIFIED = "AQ6_HARMONIC_NO_JUSTIFIED_CANDIDATE"
EXIT_INCOMPLETE = "AQ6_HARMONIC_CANDIDATE_COMPARE_INCOMPLETE"

PARTITION_POLICY = {
    "CALIBRATION": {
        "role": "DEVELOPMENT_CALIBRATION",
        "allowed_use": "exploration_narrative_only",
    },
    "TEST": {
        "role": "TEST",
        "allowed_use": "frozen_evidence_report_once_no_tuning",
    },
    "HOLDOUT": {
        "role": "HOLDOUT",
        "allowed_use": "frozen_evidence_report_once_no_tuning",
    },
}

BASELINE_RELATION_SCORES = {
    "direct": 1.0,
    "related": 0.7,
    "transpose": 0.5,
    "uncertain": 0.0,
}

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]


class Aq6HarmonicCandidateCompareError(ValueError):
    """Controlled, fail-closed input or identity error for this compare runner."""


@dataclass(frozen=True)
class HarmonicRankingCandidate:
    candidate_id: str
    harmony_weight: float
    bpm_weight: float
    relation_scores: Mapping[str, float]
    drop_uncertain: bool
    description: str
    derived_from: str


HARMONIC_RANKING_CANDIDATES: tuple[HarmonicRankingCandidate, ...] = (
    HarmonicRankingCandidate(
        candidate_id="harmonic.baseline.v1",
        harmony_weight=float(BASELINE_WEIGHTS["harmony"]),
        bpm_weight=float(BASELINE_WEIGHTS["bpm"]),
        relation_scores=dict(BASELINE_RELATION_SCORES),
        drop_uncertain=False,
        description=(
            "Current #1018 path: relation-priority sort, harmony 0.75 / BPM 0.25, "
            "relation scores direct=1.0 related=0.7 transpose=0.5; no filter."
        ),
        derived_from="#1018 as_labeled baseline anchor",
    ),
    HarmonicRankingCandidate(
        candidate_id="harmonic.weights.harmony_0.90_bpm_0.10",
        harmony_weight=0.90,
        bpm_weight=0.10,
        relation_scores=dict(BASELINE_RELATION_SCORES),
        drop_uncertain=False,
        description=(
            "Thin weight adapter: harmony-heavier 0.90/0.10. Derived from #1018 "
            "BPM-secondary / upstream-sensitivity narrative — reduce BPM pull "
            "inside a relation band without changing relation rules."
        ),
        derived_from="#1018 BPM secondary + Top-K soft spot",
    ),
    HarmonicRankingCandidate(
        candidate_id="harmonic.weights.harmony_1.00_bpm_0.00",
        harmony_weight=1.00,
        bpm_weight=0.00,
        relation_scores=dict(BASELINE_RELATION_SCORES),
        drop_uncertain=False,
        description=(
            "Thin weight adapter: harmony-only total_score (BPM score still "
            "computed/visible but weight 0). Extreme secondary-BPM de-emphasis."
        ),
        derived_from="#1018 BPM secondary evidence isolation",
    ),
    HarmonicRankingCandidate(
        candidate_id="harmonic.rank_filter.drop_uncertain",
        harmony_weight=float(BASELINE_WEIGHTS["harmony"]),
        bpm_weight=float(BASELINE_WEIGHTS["bpm"]),
        relation_scores=dict(BASELINE_RELATION_SCORES),
        drop_uncertain=True,
        description=(
            "Thin post-rank filter: drop relation=uncertain before metrics. "
            "Derived from #1018 Top-5 FP / theory-incompatible-in-Top-K visibility "
            "without claiming a theory-table fix."
        ),
        derived_from="#1018 Top-5 FP + theory-incompatible-in-Top-K",
    ),
)


def list_harmonic_ranking_candidates() -> list[HarmonicRankingCandidate]:
    return list(HARMONIC_RANKING_CANDIDATES)


def candidate_by_id(candidate_id: str) -> HarmonicRankingCandidate:
    for candidate in HARMONIC_RANKING_CANDIDATES:
        if candidate.candidate_id == candidate_id:
            return candidate
    raise Aq6HarmonicCandidateCompareError(
        f"unknown harmonic ranking candidate_id: {candidate_id}"
    )


def candidate_public(candidate: HarmonicRankingCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "harmony_weight": candidate.harmony_weight,
        "bpm_weight": candidate.bpm_weight,
        "relation_scores": dict(candidate.relation_scores),
        "drop_uncertain": candidate.drop_uncertain,
        "description": candidate.description,
        "derived_from": candidate.derived_from,
    }


def _harmony_score_for_candidate(
    relation: HarmonyRelation,
    candidate: HarmonicRankingCandidate,
) -> float:
    key = relation.value
    if key in candidate.relation_scores:
        return float(candidate.relation_scores[key])
    return float(_key_score_from_relation(relation))


def rate_harmony_for_candidate(
    reference: WorkbenchRow,
    candidate_row: WorkbenchRow,
    candidate: HarmonicRankingCandidate,
    *,
    key_override: Optional[str] = None,
) -> HarmonySuggestion:
    """Rate one pair with a declared thin ranking adapter (not production)."""
    ref_key = (
        parse_key_signature(key_override)
        if key_override is not None
        else _parse_key_from_row(reference)
    )
    cand_key = _parse_key_from_row(candidate_row)
    relation, explanation = determine_relation(ref_key, cand_key)
    bpm_score, _bpm_reason = _bpm_score_from_row(reference, candidate_row)
    harmony_score = _harmony_score_for_candidate(relation, candidate)
    denom = max(candidate.harmony_weight + candidate.bpm_weight, 1e-10)
    total_score = (
        candidate.harmony_weight * harmony_score + candidate.bpm_weight * bpm_score
    ) / denom

    pitch_shift: Optional[int] = None
    if (
        relation == HarmonyRelation.TRANSPOSE
        and ref_key is not None
        and cand_key is not None
    ):
        pitch_shift = _minimal_signed_shift(ref_key, cand_key)
        if pitch_shift > 3:
            pitch_shift = 3
        elif pitch_shift < -3:
            pitch_shift = -3

    return HarmonySuggestion(
        row=candidate_row,
        relation=relation,
        harmony_score=harmony_score,
        bpm_score=bpm_score,
        total_score=total_score,
        pitch_shift_semitones=pitch_shift,
        explanation=explanation,
    )


def find_harmony_matches_for_candidate(
    reference: WorkbenchRow,
    candidates: list[WorkbenchRow],
    candidate: HarmonicRankingCandidate,
    *,
    query: str = "",
    key_override: Optional[str] = None,
    limit: Optional[int] = None,
) -> tuple[list[HarmonySuggestion], Optional[str]]:
    """Mirror ``find_harmony_matches`` with a thin candidate adapter only."""
    # Baseline identity: reuse production finder when config matches production.
    if (
        candidate.harmony_weight == float(BASELINE_WEIGHTS["harmony"])
        and candidate.bpm_weight == float(BASELINE_WEIGHTS["bpm"])
        and dict(candidate.relation_scores) == BASELINE_RELATION_SCORES
        and not candidate.drop_uncertain
    ):
        return find_harmony_matches(
            reference,
            candidates,
            query=query,
            key_override=key_override,
            limit=limit,
        )

    if reference.bpm is None or reference.bpm <= 0:
        return [], "Ähnliche Samples benötigen ein analysiertes BPM."

    needle = query.strip().casefold()
    filtered = candidates
    if needle:
        filtered = []
        for cand in candidates:
            display_match = (
                needle in cand.display_name.casefold()
                or needle in str(cand.relative_path).casefold()
                or needle in (harmonic_match_key_for_row(cand) or "").casefold()
                or needle in (cand.pred_type or "").casefold()
            )
            if display_match:
                filtered.append(cand)

    filtered = [c for c in filtered if c.path != reference.path]
    if not filtered:
        return [], "Keine weiteren geladenen Samples zum Vergleichen."

    results = [
        rate_harmony_for_candidate(
            reference, cand, candidate, key_override=key_override
        )
        for cand in filtered
    ]
    if candidate.drop_uncertain:
        results = [s for s in results if s.relation is not HarmonyRelation.UNCERTAIN]

    relation_priority = {
        HarmonyRelation.DIRECT: 0,
        HarmonyRelation.RELATED: 1,
        HarmonyRelation.TRANSPOSE: 2,
        HarmonyRelation.UNCERTAIN: 3,
    }
    results.sort(
        key=lambda s: (
            relation_priority.get(s.relation, 99),
            -s.total_score,
            abs(s.pitch_shift_semitones) if s.pitch_shift_semitones is not None else 99,
            s.row.display_name.casefold(),
            s.row.path.casefold(),
        )
    )
    if limit is not None:
        results = results[:limit]
    return results, None


def rank_query_for_candidate(
    query: Mapping[str, Any],
    candidate: HarmonicRankingCandidate,
    *,
    upstream_state: str = "as_labeled",
) -> dict[str, Any]:
    """Rank one frozen #1016 query through a declared candidate adapter."""
    from .aq6_harmonic_ranking_baseline import _apply_upstream_to_candidates

    if upstream_state not in UPSTREAM_STATES:
        raise Aq6HarmonicCandidateCompareError(
            f"unknown upstream_state: {upstream_state!r}"
        )
    ref_item = dict(query["reference"])
    cand_items = _apply_upstream_to_candidates(
        list(query.get("candidates") or []),
        upstream_state=upstream_state,
        reference_key=ref_item.get("key"),
    )
    reference = row_from_fixture_item(ref_item)
    rows = [row_from_fixture_item(c) for c in cand_items]
    matches, error = find_harmony_matches_for_candidate(
        reference, rows, candidate
    )
    ranked_ids = [m.row.display_name for m in matches]
    rank_details = [
        {
            "synthetic_id": m.row.display_name,
            "relation": m.relation.value,
            "harmony_score": m.harmony_score,
            "bpm_score": m.bpm_score,
            "total_score": m.total_score,
            "pitch_shift_semitones": m.pitch_shift_semitones,
        }
        for m in matches
    ]
    empty = len(ranked_ids) == 0
    abstention_reason: str | None = None
    ref_bpm = ref_item.get("bpm")
    if empty and (ref_bpm is None or (isinstance(ref_bpm, (int, float)) and ref_bpm <= 0)):
        abstention_reason = "missing_reference_bpm"
    elif empty and error:
        abstention_reason = "product_empty_error"
    return {
        "query_id": query.get("query_id"),
        "partition": query.get("partition"),
        "upstream_state": upstream_state,
        "candidate_id": candidate.candidate_id,
        "ranked_ids": ranked_ids,
        "rank_details": rank_details,
        "error": error,
        "empty_result": empty,
        "abstention_reason": abstention_reason,
        "result_count": len(ranked_ids),
    }


def _partition_aggregate(
    scored_queries: Sequence[Mapping[str, Any]],
    partition: str,
) -> dict[str, Any]:
    subset = [
        q for q in scored_queries if str(q.get("partition") or "UNKNOWN") == partition
    ]
    return aggregate_query_metrics(subset)


def score_candidate_on_ranking(
    document: Mapping[str, Any],
    candidate: HarmonicRankingCandidate,
) -> dict[str, Any]:
    """Score one candidate across as_labeled ranking partitions + upstream states."""
    as_labeled_scored: list[dict[str, Any]] = []
    for query in document.get("queries") or []:
        ranked = rank_query_for_candidate(
            query, candidate, upstream_state="as_labeled"
        )
        as_labeled_scored.append(score_ranked_query(query, ranked))

    overall = aggregate_query_metrics(as_labeled_scored)
    by_partition = {
        part: _partition_aggregate(as_labeled_scored, part)
        for part in ("CALIBRATION", "TEST", "HOLDOUT")
    }

    upstream: dict[str, Any] = {}
    for state in UPSTREAM_STATES:
        if state == "as_labeled":
            continue
        scored = []
        for query in document.get("queries") or []:
            ranked = rank_query_for_candidate(
                query, candidate, upstream_state=state
            )
            scored.append(score_ranked_query(query, ranked))
        upstream[state] = {
            "queries_total": aggregate_query_metrics(scored)["queries_total"],
            "queries_scored": aggregate_query_metrics(scored)["queries_scored"],
            "queries_empty": aggregate_query_metrics(scored)["queries_empty"],
            "macro": aggregate_query_metrics(scored)["macro"],
        }

    return {
        "as_labeled": {
            "queries_total": overall["queries_total"],
            "queries_scored": overall["queries_scored"],
            "queries_empty": overall["queries_empty"],
            "empty_query_ids": overall["empty_query_ids"],
            "macro": overall["macro"],
            "coverage": overall["coverage"],
            "by_partition": {
                part: {
                    "queries_total": bucket["queries_total"],
                    "queries_scored": bucket["queries_scored"],
                    "queries_empty": bucket["queries_empty"],
                    "macro": bucket["macro"],
                }
                for part, bucket in by_partition.items()
            },
        },
        "upstream_states": upstream,
        "exploration_partition": "CALIBRATION",
        "frozen_evidence_partitions": ["TEST", "HOLDOUT"],
    }


def theory_gate_for_candidate(
    theory_document: Mapping[str, Any],
    candidate: HarmonicRankingCandidate,
) -> dict[str, Any]:
    """Hard theory gate: relation/compatibility/pitch-shift vs frozen #1015.

    Ranking adapters must not change theory fields. Score mapping / filters may
    change ranking-adjacent total_score only. Failures are hard-visible and
    cannot be averaged into ranking KPIs.
    """
    cells = list(theory_document.get("cells") or [])
    predictions: dict[str, dict[str, Any]] = {}
    for cell in cells:
        # Theory classification uses production determine_relation path via the
        # candidate rater; relation identity must match the #1017 product path.
        suggestion = rate_harmony_for_candidate(
            WorkbenchRow(
                display_name="ref",
                relative_path="ref.wav",
                path="/synthetic/aq6-compare/ref.wav",
                bpm=128.0,
                key=cell.get("source_key"),
                key_conf=0.8 if cell.get("source_key") else None,
                loudness=-20.0,
                brightness=2000.0,
                sample_class="loop",
                pred_type="kick",
                status="ok",
            ),
            WorkbenchRow(
                display_name="cand",
                relative_path="cand.wav",
                path="/synthetic/aq6-compare/cand.wav",
                bpm=128.0,
                key=cell.get("target_key"),
                key_conf=0.8 if cell.get("target_key") else None,
                loudness=-20.0,
                brightness=2000.0,
                sample_class="loop",
                pred_type="kick",
                status="ok",
            ),
            candidate,
        )
        relation = suggestion.relation.value
        if relation in {"direct", "related", "transpose"}:
            compatibility = "compatible"
        else:
            source_parsed = (
                parse_key_signature(cell.get("source_key"))
                if cell.get("source_key")
                else None
            )
            target_parsed = (
                parse_key_signature(cell.get("target_key"))
                if cell.get("target_key")
                else None
            )
            modeful = (
                source_parsed is not None
                and target_parsed is not None
                and source_parsed.mode is not None
                and target_parsed.mode is not None
            )
            compatibility = "incompatible" if modeful else "uncertain"
        predictions[str(cell["cell_id"])] = {
            "relation": relation,
            "compatibility": compatibility,
            "pitch_shift_semitones": suggestion.pitch_shift_semitones,
        }

    scored = score_theory_predictions(cells, predictions)
    accuracy = scored.get("relation_classification_accuracy")
    theory_pass = accuracy == 1.0 and int(scored.get("cells_scored") or 0) == len(
        cells
    )
    # Cross-check vs product baseline prediction identity on a sample of cells.
    product_mismatch = 0
    for cell in cells[:24]:
        product = theory_product_prediction(
            cell.get("source_key"), cell.get("target_key")
        )
        pred = predictions[str(cell["cell_id"])]
        if (
            product["relation"] != pred["relation"]
            or product["compatibility"] != pred["compatibility"]
            or product["pitch_shift_semitones"] != pred["pitch_shift_semitones"]
        ):
            product_mismatch += 1

    return {
        "token": THEORY_DOMAIN_TOKEN,
        "surface": THEORY_SURFACE,
        "truth_table_id": TRUTH_TABLE_ID,
        "cells_scored": scored.get("cells_scored"),
        "relation_classification_accuracy": accuracy,
        "incompatible_false_positive_rate": scored.get(
            "incompatible_false_positive_rate"
        ),
        "pass": bool(theory_pass) and product_mismatch == 0,
        "product_theory_field_mismatches_sample": product_mismatch,
        "ranking_gain_may_not_hide_theory_regression": True,
        "note": (
            "Theory plane remains independent; a ranking-only gain cannot excuse "
            "a theory regression on this gate."
        ),
    }


def measure_candidate_determinism(
    document: Mapping[str, Any],
    candidate: HarmonicRankingCandidate,
) -> dict[str, Any]:
    first: dict[str, list[str]] = {}
    second: dict[str, list[str]] = {}
    for query in document.get("queries") or []:
        qid = str(query.get("query_id"))
        r1 = rank_query_for_candidate(query, candidate, upstream_state="as_labeled")
        r2 = rank_query_for_candidate(query, candidate, upstream_state="as_labeled")
        first[qid] = list(r1["ranked_ids"])
        second[qid] = list(r2["ranked_ids"])
    identical = first == second
    return {
        "passes": 2,
        "ranked_lists_identical": identical,
        "deterministic": identical,
        "reference": "#959 / docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md",
    }


def baseline_anchor_matches(
    ranking_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Require baseline candidate to reproduce #1018 as_labeled anchor KPIs."""
    macro = (ranking_result.get("as_labeled") or {}).get("macro") or {}
    checks = {
        "precision_at_1": macro.get("precision_at_1") == 1.0,
        "mrr_at_5": macro.get("mrr_at_5") == 1.0,
        "ndcg_at_5": macro.get("ndcg_at_5") == 1.0,
        "queries_empty": ranking_result.get("as_labeled", {}).get("queries_empty")
        == 1,
        "queries_scored": ranking_result.get("as_labeled", {}).get("queries_scored")
        == 4,
    }
    return {
        "anchor": "harmonic.baseline.v1",
        "matches_1018_as_labeled": all(checks.values()),
        "checks": checks,
        "observed_macro": {
            "precision_at_1": macro.get("precision_at_1"),
            "mrr_at_5": macro.get("mrr_at_5"),
            "ndcg_at_5": macro.get("ndcg_at_5"),
            "top_5_false_positive_rate": macro.get("top_5_false_positive_rate"),
        },
    }


def _assert_output_outside_repo(output_path: Path, root: Path) -> None:
    resolved = output_path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return
    raise ValueError(f"output path must be outside repo: {resolved}")


def is_reproducible(result: Mapping[str, Any]) -> bool:
    if result.get("candidate_count") != len(HARMONIC_RANKING_CANDIDATES):
        return False
    if not result.get("no_tuning_on_test"):
        return False
    if result.get("production_switch") is not False:
        return False
    if not (result.get("missing_evidence_guard") or {}).get("pass"):
        return False
    candidates = result.get("candidates") or []
    if len(candidates) != len(HARMONIC_RANKING_CANDIDATES):
        return False
    baseline_ok = False
    for entry in candidates:
        theory = entry.get("theory_gate") or {}
        ranking = entry.get("ranking") or {}
        det = entry.get("determinism") or {}
        if not theory.get("pass"):
            return False
        if not det.get("deterministic"):
            return False
        as_labeled = ranking.get("as_labeled") or {}
        if as_labeled.get("queries_total") != 5:
            return False
        if "CALIBRATION" not in (as_labeled.get("by_partition") or {}):
            return False
        if "TEST" not in (as_labeled.get("by_partition") or {}):
            return False
        if "HOLDOUT" not in (as_labeled.get("by_partition") or {}):
            return False
        if entry.get("candidate_id") == "harmonic.baseline.v1":
            anchor = entry.get("baseline_anchor") or {}
            baseline_ok = bool(anchor.get("matches_1018_as_labeled"))
    return baseline_ok


def is_no_justified_candidate(result: Mapping[str, Any]) -> bool:
    """True when registry empty / no evaluable non-baseline identity survived."""
    candidates = result.get("candidates") or []
    if not candidates:
        return True
    non_baseline = [
        c for c in candidates if c.get("candidate_id") != "harmonic.baseline.v1"
    ]
    if not non_baseline:
        return True
    return False


def run_aq6_harmonic_ranking_candidate_compare(
    *,
    output_path: Path | str,
    repo_root: Path | str | None = None,
    ranking_fixture_path: Path | str | None = None,
    theory_fixture_path: Path | str | None = None,
) -> dict[str, Any]:
    """Compare frozen ranking candidates; write external JSON evidence."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    out = Path(output_path)
    _assert_output_outside_repo(out, root)

    ranking_fixture = (
        Path(ranking_fixture_path)
        if ranking_fixture_path is not None
        else root / FIXTURE_RELPATH
    )
    theory_fixture = (
        Path(theory_fixture_path)
        if theory_fixture_path is not None
        else root / THEORY_FIXTURE_RELPATH
    )
    ranking_doc = load_relevance_benchmark_fixture(ranking_fixture)
    theory_doc = load_truth_table_fixture(theory_fixture)
    guard = prove_missing_evidence_not_forced_certainty(ranking_doc)

    candidate_entries: list[dict[str, Any]] = []
    for candidate in HARMONIC_RANKING_CANDIDATES:
        ranking = score_candidate_on_ranking(ranking_doc, candidate)
        theory = theory_gate_for_candidate(theory_doc, candidate)
        determinism = measure_candidate_determinism(ranking_doc, candidate)
        entry: dict[str, Any] = {
            **candidate_public(candidate),
            "ranking": ranking,
            "theory_gate": theory,
            "determinism": determinism,
        }
        if candidate.candidate_id == "harmonic.baseline.v1":
            entry["baseline_anchor"] = baseline_anchor_matches(ranking)
        candidate_entries.append(entry)

    draft: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "domain": DOMAIN_TOKEN,
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": ranking_doc.get(
            "benchmark_version", BENCHMARK_VERSION
        ),
        "baseline_document_type": BASELINE_DOCUMENT_TYPE,
        "baseline_surface": BASELINE_SURFACE,
        "theory_truth_table_id": TRUTH_TABLE_ID,
        "fixture_relpath": str(FIXTURE_RELPATH).replace("\\", "/"),
        "theory_fixture_relpath": str(THEORY_FIXTURE_RELPATH).replace("\\", "/"),
        "partition_policy": dict(PARTITION_POLICY),
        "no_tuning_on_test": True,
        "production_switch": False,
        "candidate_count": len(candidate_entries),
        "candidates": candidate_entries,
        "missing_evidence_guard": guard,
        "theory_plane": {
            "token": THEORY_DOMAIN_TOKEN,
            "mixed_into_ranking_metrics": False,
            "hard_gate_per_candidate": True,
            "note": (
                "Ranking candidates must not claim theory fixes; theory regressions "
                "are hard-visible per candidate and cannot be averaged away."
            ),
        },
        "non_goals_honored": [
            "no_production_switch",
            "no_ui_qml",
            "no_key_bpm_detector_changes",
            "no_ml_embeddings",
            "no_private_audio",
            "no_tuning_on_test_holdout",
            "no_theory_fix_claimed_by_ranking",
        ],
        "parents": ["#948", "#942", "#1015", "#1016", "#1017", "#1018"],
        "issue": "#1019",
    }

    if is_reproducible(draft):
        draft["exit_status"] = EXIT_REPRODUCIBLE
    elif is_no_justified_candidate(draft):
        draft["exit_status"] = EXIT_NO_JUSTIFIED
    else:
        draft["exit_status"] = EXIT_INCOMPLETE

    payload = json.dumps(draft, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    root_resolved = str(root.resolve())
    for needle in ("D:/", "D:\\", "C:/", "C:\\", root_resolved):
        if needle and needle in payload:
            raise ValueError(f"refusing to write host path material: {needle!r}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload, encoding="utf-8")
    return draft


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare frozen AQ6 Harmonic Match ranking weight/relation "
            "candidates against #1016/#1018 evidence with a hard theory gate (#1019)."
        )
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
        "--fixture",
        default=None,
        help="Optional ranking-relevance fixture path (default: frozen repo fixture).",
    )
    parser.add_argument(
        "--theory-fixture",
        default=None,
        help="Optional theory truth-table fixture path (default: frozen repo fixture).",
    )
    args = parser.parse_args(argv)
    result = run_aq6_harmonic_ranking_candidate_compare(
        output_path=args.output,
        repo_root=args.repo_root,
        ranking_fixture_path=args.fixture,
        theory_fixture_path=args.theory_fixture,
    )
    print(
        json.dumps(
            {
                "exit_status": result["exit_status"],
                "candidate_count": result["candidate_count"],
                "baseline_p_at_1": next(
                    (
                        c["ranking"]["as_labeled"]["macro"]["precision_at_1"]
                        for c in result["candidates"]
                        if c["candidate_id"] == "harmonic.baseline.v1"
                    ),
                    None,
                ),
            }
        )
    )
    return 0 if result["exit_status"] == EXIT_REPRODUCIBLE else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BASELINE_DOCUMENT_TYPE",
    "BASELINE_RELATION_SCORES",
    "BASELINE_SURFACE",
    "BASELINE_WEIGHTS",
    "BENCHMARK_ID",
    "DOCUMENT_TYPE",
    "DOMAIN_TOKEN",
    "EXIT_INCOMPLETE",
    "EXIT_NO_JUSTIFIED",
    "EXIT_REPRODUCIBLE",
    "HARMONIC_RANKING_CANDIDATES",
    "PARTITION_POLICY",
    "SCHEMA_VERSION",
    "Aq6HarmonicCandidateCompareError",
    "HarmonicRankingCandidate",
    "baseline_anchor_matches",
    "candidate_by_id",
    "candidate_public",
    "find_harmony_matches_for_candidate",
    "is_no_justified_candidate",
    "is_reproducible",
    "list_harmonic_ranking_candidates",
    "measure_candidate_determinism",
    "rank_query_for_candidate",
    "rate_harmony_for_candidate",
    "run_aq6_harmonic_ranking_candidate_compare",
    "score_candidate_on_ranking",
    "theory_gate_for_candidate",
]
