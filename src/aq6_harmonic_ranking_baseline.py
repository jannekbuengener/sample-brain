"""AQ6 Harmonic Match ranking + upstream-error propagation baseline (#1018).

Measures current ``find_harmony_matches`` / total-score ranking against the
frozen #1016 ranking-relevance benchmark. Ranking plane only — theory
correctness (#1017) stays separate and must not be rewritten or excused by
ranking metrics. No production switch. External JSON evidence only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .aq6_harmonic_ranking_relevance import (
    BENCHMARK_ID,
    BENCHMARK_VERSION,
    DEFAULT_KS,
    DOMAIN_TOKEN as RANKING_DOMAIN_TOKEN,
    FIXTURE_RELPATH,
    load_relevance_benchmark_fixture,
    score_ranking_for_query,
)
from .workbench_controller import WorkbenchRow
from .workbench_harmony import find_harmony_matches, rate_harmony

DOCUMENT_TYPE = "sample-brain.aq6.harmonic-ranking-baseline.v1"
SCHEMA_VERSION = "1.0.0"
DOMAIN_TOKEN = RANKING_DOMAIN_TOKEN
EXIT_MEASURED = "AQ6_RANKING_BASELINE_AND_UPSTREAM_DELTA_MEASURED"
EXIT_PARTIAL = "AQ6_RANKING_BASELINE_PARTIAL_HOLD"
EXIT_INCOMPLETE = "AQ6_RANKING_BASELINE_INCOMPLETE"
SURFACE = "src.workbench_harmony.find_harmony_matches"
WEIGHTS = {"harmony": 0.75, "bpm": 0.25}
UPSTREAM_STATES: tuple[str, ...] = (
    "as_labeled",
    "missing_candidate_key",
    "wrong_candidate_key",
)
THEORY_PLANE_NOTE = (
    "separate plane - aq6.theory (#1017) must not rewrite or excuse ranking "
    "metrics; theory failures remain independently visible"
)
# Fixed wrong-key injector for controlled upstream-error measurement.
_WRONG_KEY_INJECT = "F#maj"

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]

_MACRO_KEYS = (
    "precision_at_1",
    "precision_at_3",
    "precision_at_5",
    "mrr_at_1",
    "mrr_at_3",
    "mrr_at_5",
    "ndcg_at_1",
    "ndcg_at_3",
    "ndcg_at_5",
    "top_1_false_positive_rate",
    "top_3_false_positive_rate",
    "top_5_false_positive_rate",
)


def row_from_fixture_item(
    item: Mapping[str, Any],
    *,
    key_override: Any = ...,
    bpm_override: Any = ...,
) -> WorkbenchRow:
    """Build a WorkbenchRow; display_name is the ranking identity (synthetic_id)."""
    sid = str(item["synthetic_id"])
    if key_override is ...:
        key = item.get("key")
    else:
        key = key_override
    if bpm_override is ...:
        bpm = item.get("bpm")
    else:
        bpm = bpm_override
    rel = str(item.get("path") or f"synthetic/aq6_ranking/{sid}.wav")
    return WorkbenchRow(
        display_name=sid,
        relative_path=rel,
        path=f"/synthetic/aq6-ranking-baseline/{sid}.wav",
        bpm=bpm,
        key=key,
        key_conf=0.8 if key else None,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type="kick",
        status="ok",
    )


def _apply_upstream_to_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    upstream_state: str,
    reference_key: str | None,
) -> list[dict[str, Any]]:
    """Apply controlled upstream key corruption; synthetic ids / labels stay fixed."""
    if upstream_state not in UPSTREAM_STATES:
        raise ValueError(f"unknown upstream_state: {upstream_state!r}")
    out: list[dict[str, Any]] = [dict(c) for c in candidates]
    if upstream_state == "missing_candidate_key":
        for row in out:
            row["key"] = None
        return out
    if upstream_state == "wrong_candidate_key":
        # Deterministic swap: first eligible relevant <-> first hard-negative.
        # Simulates wrong upstream key claims without retuning ranking weights.
        relevant_idx = next(
            (
                i
                for i, c in enumerate(out)
                if c.get("ranking_eligible")
                and isinstance(c.get("relevance_grade"), int)
                and int(c["relevance_grade"]) >= 1
            ),
            None,
        )
        negative_idx = next(
            (
                i
                for i, c in enumerate(out)
                if c.get("ranking_eligible") and c.get("relevance_grade") == 0
            ),
            None,
        )
        if relevant_idx is not None and negative_idx is not None:
            # Give the hard-negative the reference key (product sees DIRECT).
            # Give the relevant item a fixed far key (product sees UNCERTAIN).
            out[negative_idx]["key"] = reference_key or _WRONG_KEY_INJECT
            out[relevant_idx]["key"] = _WRONG_KEY_INJECT
        else:
            for row in out:
                row["key"] = _WRONG_KEY_INJECT
        return out
    return out


def rank_query(
    query: Mapping[str, Any],
    *,
    upstream_state: str = "as_labeled",
) -> dict[str, Any]:
    """Run product ``find_harmony_matches`` for one frozen query."""
    ref_item = dict(query["reference"])
    cand_items = _apply_upstream_to_candidates(
        list(query.get("candidates") or []),
        upstream_state=upstream_state,
        reference_key=ref_item.get("key"),
    )
    reference = row_from_fixture_item(ref_item)
    candidates = [row_from_fixture_item(c) for c in cand_items]
    matches, error = find_harmony_matches(reference, candidates)

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

    abstention_reason: str | None = None
    empty = len(ranked_ids) == 0
    ref_bpm = ref_item.get("bpm")
    if empty and (ref_bpm is None or (isinstance(ref_bpm, (int, float)) and ref_bpm <= 0)):
        abstention_reason = "missing_reference_bpm"
    elif empty and error:
        abstention_reason = "product_empty_error"

    return {
        "query_id": query.get("query_id"),
        "partition": query.get("partition"),
        "upstream_state": upstream_state,
        "ranked_ids": ranked_ids,
        "rank_details": rank_details,
        "error": error,
        "empty_result": empty,
        "abstention_reason": abstention_reason,
        "result_count": len(ranked_ids),
    }


def score_ranked_query(
    query: Mapping[str, Any],
    ranked: Mapping[str, Any],
    *,
    ks: Sequence[int] = DEFAULT_KS,
) -> dict[str, Any]:
    """Score a ranked product list against frozen #1016 relevance labels."""
    metrics = score_ranking_for_query(
        query, list(ranked.get("ranked_ids") or []), ks=ks
    )
    metrics["empty_result"] = bool(ranked.get("empty_result"))
    metrics["abstention_reason"] = ranked.get("abstention_reason")
    metrics["error"] = ranked.get("error")
    metrics["result_count"] = ranked.get("result_count", 0)
    metrics["upstream_state"] = ranked.get("upstream_state")
    label_by_id = {
        str(c["synthetic_id"]): c for c in (query.get("candidates") or [])
    }
    top_n = max(ks) if ks else 5
    theory_in_top: list[dict[str, Any]] = []
    for sid in list(ranked.get("ranked_ids") or [])[:top_n]:
        label = label_by_id.get(sid) or {}
        theory_in_top.append(
            {
                "synthetic_id": sid,
                "theory_relation": label.get("theory_relation"),
                "theory_compatibility": label.get("theory_compatibility"),
                "relevance_grade": label.get("relevance_grade"),
                "ranking_eligible": label.get("ranking_eligible"),
            }
        )
    metrics["theory_labels_in_topk"] = theory_in_top
    metrics["theory_incompatible_in_topk"] = sum(
        1
        for row in theory_in_top
        if row.get("theory_compatibility") == "incompatible"
    )
    return metrics


def _mean(values: Sequence[float | None]) -> float | None:
    usable = [v for v in values if v is not None]
    if not usable:
        return None
    return sum(usable) / len(usable)


def aggregate_query_metrics(
    scored_queries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Macro-average ranking KPIs; track empty/abstention coverage separately."""
    total = len(scored_queries)
    scored = [q for q in scored_queries if not q.get("empty_result")]
    empty = [q for q in scored_queries if q.get("empty_result")]
    macro: dict[str, float | None] = {}
    for key in _MACRO_KEYS:
        macro[key] = _mean([q.get(key) for q in scored])

    by_partition: dict[str, Any] = {}
    for q in scored_queries:
        part = str(q.get("partition") or "UNKNOWN")
        bucket = by_partition.setdefault(
            part,
            {
                "queries_total": 0,
                "queries_scored": 0,
                "queries_empty": 0,
                "macro": {},
            },
        )
        bucket["queries_total"] += 1
        if q.get("empty_result"):
            bucket["queries_empty"] += 1
        else:
            bucket["queries_scored"] += 1
    for part, bucket in by_partition.items():
        part_scored = [
            q
            for q in scored_queries
            if str(q.get("partition") or "UNKNOWN") == part
            and not q.get("empty_result")
        ]
        part_macro: dict[str, float | None] = {}
        for key in _MACRO_KEYS:
            part_macro[key] = _mean([q.get(key) for q in part_scored])
        bucket["macro"] = part_macro

    queries_with_relevant = sum(
        1 for q in scored_queries if (q.get("relevant_count") or 0) > 0
    )
    ineligible_total = sum(int(q.get("ineligible_count") or 0) for q in scored_queries)
    eligible_total = sum(int(q.get("eligible_count") or 0) for q in scored_queries)
    cand_total = ineligible_total + eligible_total
    return {
        "queries_total": total,
        "queries_scored": len(scored),
        "queries_empty": len(empty),
        "empty_query_ids": [q.get("query_id") for q in empty],
        "macro": macro,
        "by_partition": by_partition,
        "coverage": {
            "queries_with_eligible_relevant": queries_with_relevant,
            "ineligible_candidate_fraction": (
                (ineligible_total / cand_total) if cand_total else 0.0
            ),
            "eligible_candidates": eligible_total,
            "ineligible_candidates": ineligible_total,
        },
        "per_query": list(scored_queries),
    }


def measure_upstream_states(
    document: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Score every frozen query under each controlled upstream evidence state."""
    by_state: dict[str, dict[str, Any]] = {}
    for state in UPSTREAM_STATES:
        scored = []
        for query in document.get("queries") or []:
            ranked = rank_query(query, upstream_state=state)
            scored.append(score_ranked_query(query, ranked))
        by_state[state] = aggregate_query_metrics(scored)
    return by_state


def compute_upstream_deltas(
    by_state: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Attribute metric deltas vs as_labeled to upstream evidence changes."""
    base = by_state.get("as_labeled") or {}
    base_macro = base.get("macro") or {}
    deltas: dict[str, Any] = {}
    for state in UPSTREAM_STATES:
        if state == "as_labeled":
            continue
        other_macro = (by_state.get(state) or {}).get("macro") or {}
        metric_deltas: dict[str, Any] = {}
        for key in (
            "precision_at_1",
            "precision_at_5",
            "mrr_at_5",
            "ndcg_at_5",
            "top_5_false_positive_rate",
        ):
            left = base_macro.get(key)
            right = other_macro.get(key)
            delta = None
            if left is not None and right is not None:
                delta = right - left
            metric_deltas[key] = {
                "as_labeled": left,
                state: right,
                "delta": delta,
            }
        deltas[f"as_labeled_to_{state}"] = {
            **metric_deltas,
            "attribution": "upstream_evidence",
            "note": (
                "Labels stay frozen (#1016); only injected upstream key evidence "
                "changes. Ranking weights remain 0.75/0.25."
            ),
        }
    return deltas


def prove_missing_evidence_not_forced_certainty(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    """Ineligible / uncertain evidence must not become product-compatible."""
    checked = 0
    forced = 0
    examples: list[dict[str, Any]] = []
    for query in document.get("queries") or []:
        ref_bpm = (query.get("reference") or {}).get("bpm")
        if ref_bpm is None or (isinstance(ref_bpm, (int, float)) and ref_bpm <= 0):
            # Synthetic BPM only to inspect key-evidence relation; does not
            # change the ranking-baseline product-empty measurement for this query.
            ref = row_from_fixture_item(query["reference"], bpm_override=120.0)
        else:
            ref = row_from_fixture_item(query["reference"])
        for cand in query.get("candidates") or []:
            if cand.get("ranking_eligible"):
                continue
            checked += 1
            suggestion = rate_harmony(ref, row_from_fixture_item(cand))
            if (
                suggestion.relation.value != "uncertain"
                or suggestion.harmony_score != 0.0
            ):
                forced += 1
                examples.append(
                    {
                        "query_id": query.get("query_id"),
                        "synthetic_id": cand.get("synthetic_id"),
                        "relation": suggestion.relation.value,
                        "harmony_score": suggestion.harmony_score,
                    }
                )
    return {
        "ineligible_candidates_checked": checked,
        "forced_compatible_count": forced,
        "examples": examples[:10],
        "pass": checked >= 1 and forced == 0,
        "rule": (
            "missing/uncertain key/mode evidence must keep relation=uncertain and "
            "harmony_score=0; never forced certainty"
        ),
    }


def measure_repeatability(document: Mapping[str, Any]) -> dict[str, Any]:
    """Two identical as_labeled passes — consume #959 by reference."""
    first_lists: dict[str, list[str]] = {}
    second_lists: dict[str, list[str]] = {}
    first_metrics: list[dict[str, Any]] = []
    second_metrics: list[dict[str, Any]] = []
    for query in document.get("queries") or []:
        qid = str(query.get("query_id"))
        r1 = rank_query(query, upstream_state="as_labeled")
        r2 = rank_query(query, upstream_state="as_labeled")
        first_lists[qid] = list(r1["ranked_ids"])
        second_lists[qid] = list(r2["ranked_ids"])
        first_metrics.append(score_ranked_query(query, r1))
        second_metrics.append(score_ranked_query(query, r2))
    lists_identical = first_lists == second_lists
    a1 = aggregate_query_metrics(first_metrics)
    a2 = aggregate_query_metrics(second_metrics)
    metrics_identical = a1["macro"] == a2["macro"]
    return {
        "passes": 2,
        "ranked_lists_identical": lists_identical,
        "metrics_identical": metrics_identical,
        "deterministic": lists_identical and metrics_identical,
        "reference": "#959 / docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md",
    }


def theory_plane_visibility(document: Mapping[str, Any]) -> dict[str, Any]:
    """Keep #1017 theory plane visible without remixing into ranking KPIs."""
    incompatible_topk = 0
    for query in document.get("queries") or []:
        ranked = rank_query(query, upstream_state="as_labeled")
        scored = score_ranked_query(query, ranked)
        incompatible_topk += int(scored.get("theory_incompatible_in_topk") or 0)
    return {
        "token": "aq6.theory",
        "issue_ref": "#1017",
        "mixed_into_ranking_metrics": False,
        "incompatible_in_top_k_reported_separately": True,
        "as_labeled_theory_incompatible_in_topk_sum": incompatible_topk,
        "note": THEORY_PLANE_NOTE,
        "baseline_doc": "docs/benchmarks/AQ6_HARMONIC_MATCH_THEORY_BASELINE.md",
    }


def measure_bpm_cohorts(document: Mapping[str, Any]) -> dict[str, Any]:
    """Split as_labeled metrics by secondary BPM evidence presence."""
    known_queries: list[Mapping[str, Any]] = []
    missing_queries: list[Mapping[str, Any]] = []
    for query in document.get("queries") or []:
        ref = query.get("reference") or {}
        ref_missing = ref.get("bpm_evidence") != "known"
        cand_missing = any(
            (c.get("bpm_evidence") != "known")
            for c in (query.get("candidates") or [])
        )
        bucket = missing_queries if (ref_missing or cand_missing) else known_queries
        ranked = rank_query(query, upstream_state="as_labeled")
        bucket.append(score_ranked_query(query, ranked))
    return {
        "bpm_known": aggregate_query_metrics(known_queries) if known_queries else None,
        "bpm_missing": (
            aggregate_query_metrics(missing_queries) if missing_queries else None
        ),
        "note": (
            "BPM is secondary evidence only; missing BPM must not invent tempo "
            "certainty. Missing reference BPM triggers product abstention."
        ),
    }


def coverage_report(
    document: Mapping[str, Any],
    as_labeled: Mapping[str, Any],
) -> dict[str, Any]:
    queries = list(document.get("queries") or [])
    support = document.get("support") or {}
    complete = (
        len(queries) == 5
        and as_labeled.get("queries_total") == 5
        and as_labeled.get("queries_scored", 0) >= 4
        and as_labeled.get("queries_empty", 0) >= 1
        and bool(support.get("has_direct"))
        and bool(support.get("has_related"))
        and bool(support.get("has_transpose"))
        and bool(support.get("has_incompatible"))
        and bool(support.get("has_uncertain_evidence"))
        and bool(support.get("has_bpm_known"))
        and bool(support.get("has_bpm_missing"))
    )
    return {
        "queries_expected": 5,
        "queries_total": len(queries),
        "queries_scored": as_labeled.get("queries_scored"),
        "queries_empty": as_labeled.get("queries_empty"),
        "benchmark_id": document.get("benchmark_id"),
        "benchmark_version": document.get("benchmark_version", BENCHMARK_VERSION),
        "complete": complete,
    }


def is_measured(result: Mapping[str, Any]) -> bool:
    """Return True when measurement meets #1018 acceptance completeness."""
    coverage = result.get("coverage") or {}
    as_labeled = result.get("as_labeled") or {}
    upstream = result.get("upstream_states") or {}
    deltas = result.get("upstream_deltas") or {}
    determinism = result.get("determinism") or {}
    guard = result.get("missing_evidence_guard") or {}
    theory = result.get("theory_plane") or {}
    bpm = result.get("bpm_cohorts") or {}

    if not coverage.get("complete"):
        return False
    if as_labeled.get("queries_total") != 5:
        return False
    if as_labeled.get("queries_scored", 0) < 4:
        return False
    if as_labeled.get("queries_empty", 0) < 1:
        return False
    for state in UPSTREAM_STATES:
        if state not in upstream:
            return False
    if "as_labeled_to_missing_candidate_key" not in deltas:
        return False
    if "as_labeled_to_wrong_candidate_key" not in deltas:
        return False
    if not determinism.get("deterministic"):
        return False
    if not guard.get("pass"):
        return False
    if theory.get("mixed_into_ranking_metrics") is not False:
        return False
    if bpm.get("bpm_known") is None or bpm.get("bpm_missing") is None:
        return False
    macro = as_labeled.get("macro") or {}
    for key in (
        "precision_at_1",
        "mrr_at_5",
        "ndcg_at_5",
        "top_5_false_positive_rate",
    ):
        if key not in macro:
            return False
    return True


def is_partial_hold(result: Mapping[str, Any]) -> bool:
    """Partial hold: core as_labeled metrics exist but upstream/guards incomplete."""
    as_labeled = result.get("as_labeled") or {}
    macro = as_labeled.get("macro") or {}
    if as_labeled.get("queries_scored", 0) < 1:
        return False
    if "precision_at_1" not in macro:
        return False
    return not is_measured(result)


def _assert_output_outside_repo(output_path: Path, root: Path) -> None:
    resolved = output_path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return
    raise ValueError(f"output path must be outside repo: {resolved}")


def _strip_per_query_for_size(agg: Mapping[str, Any]) -> dict[str, Any]:
    """Keep portable aggregates; drop bulky per-query dumps from nested copies."""
    out = dict(agg)
    compact = []
    for q in list(agg.get("per_query") or []):
        compact.append(
            {
                "query_id": q.get("query_id"),
                "partition": q.get("partition"),
                "empty_result": q.get("empty_result"),
                "abstention_reason": q.get("abstention_reason"),
                "result_count": q.get("result_count"),
                "precision_at_1": q.get("precision_at_1"),
                "precision_at_3": q.get("precision_at_3"),
                "precision_at_5": q.get("precision_at_5"),
                "mrr_at_1": q.get("mrr_at_1"),
                "mrr_at_3": q.get("mrr_at_3"),
                "mrr_at_5": q.get("mrr_at_5"),
                "ndcg_at_1": q.get("ndcg_at_1"),
                "ndcg_at_3": q.get("ndcg_at_3"),
                "ndcg_at_5": q.get("ndcg_at_5"),
                "top_1_false_positive_rate": q.get("top_1_false_positive_rate"),
                "top_3_false_positive_rate": q.get("top_3_false_positive_rate"),
                "top_5_false_positive_rate": q.get("top_5_false_positive_rate"),
                "theory_incompatible_in_topk": q.get("theory_incompatible_in_topk"),
                "eligible_count": q.get("eligible_count"),
                "ineligible_count": q.get("ineligible_count"),
                "relevant_count": q.get("relevant_count"),
            }
        )
    out["per_query"] = compact
    return out


def run_aq6_ranking_baseline(
    *,
    output_path: Path | str,
    repo_root: Path | str | None = None,
    fixture_path: Path | str | None = None,
) -> dict[str, Any]:
    """Score current product ranking against frozen #1016 labels; write JSON."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    out = Path(output_path)
    _assert_output_outside_repo(out, root)

    fixture = (
        Path(fixture_path) if fixture_path is not None else root / FIXTURE_RELPATH
    )
    document = load_relevance_benchmark_fixture(fixture)

    by_state = measure_upstream_states(document)
    deltas = compute_upstream_deltas(by_state)
    determinism = measure_repeatability(document)
    guard = prove_missing_evidence_not_forced_certainty(document)
    theory = theory_plane_visibility(document)
    bpm_cohorts = measure_bpm_cohorts(document)
    as_labeled = _strip_per_query_for_size(by_state["as_labeled"])
    coverage = coverage_report(document, as_labeled)

    upstream_compact: dict[str, Any] = {}
    for state, agg in by_state.items():
        compact = _strip_per_query_for_size(agg)
        if state != "as_labeled":
            upstream_compact[state] = {
                "queries_total": compact["queries_total"],
                "queries_scored": compact["queries_scored"],
                "queries_empty": compact["queries_empty"],
                "empty_query_ids": compact["empty_query_ids"],
                "macro": compact["macro"],
                "coverage": compact["coverage"],
                "by_partition": {
                    p: {
                        "queries_total": b["queries_total"],
                        "queries_scored": b["queries_scored"],
                        "queries_empty": b["queries_empty"],
                        "macro": b["macro"],
                    }
                    for p, b in (compact.get("by_partition") or {}).items()
                },
            }
        else:
            upstream_compact[state] = compact

    bpm_compact: dict[str, Any] = {"note": bpm_cohorts.get("note")}
    for key in ("bpm_known", "bpm_missing"):
        cohort = bpm_cohorts.get(key)
        if cohort is None:
            bpm_compact[key] = None
        else:
            c = _strip_per_query_for_size(cohort)
            bpm_compact[key] = {
                "queries_total": c["queries_total"],
                "queries_scored": c["queries_scored"],
                "queries_empty": c["queries_empty"],
                "empty_query_ids": c["empty_query_ids"],
                "macro": c["macro"],
            }

    draft: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "domain": DOMAIN_TOKEN,
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": document.get("benchmark_version", BENCHMARK_VERSION),
        "surface": SURFACE,
        "weights": dict(WEIGHTS),
        "fixture_relpath": str(FIXTURE_RELPATH).replace("\\", "/"),
        "coverage": coverage,
        "as_labeled": as_labeled,
        "upstream_states": upstream_compact,
        "upstream_deltas": deltas,
        "bpm_cohorts": bpm_compact,
        "determinism": determinism,
        "missing_evidence_guard": guard,
        "theory_plane": theory,
        "tie_order": {
            "policy": (
                "relation_priority(direct>related>transpose>uncertain), "
                "then -total_score, then |pitch_shift|, then display_name, path"
            ),
            "deterministic": determinism.get("deterministic"),
            "note": "Opaque score fusion is not used; components remain visible.",
        },
        "non_goals_honored": [
            "no_ranking_weight_tuning",
            "no_ui_qml",
            "no_key_bpm_detector_changes",
            "no_ml_embeddings",
            "no_private_audio",
            "no_production_switch",
            "theory_plane_not_remeasured_as_ranking",
        ],
        "parents": ["#948", "#942", "#1016", "#1017"],
        "issue": "#1018",
    }
    if is_measured(draft):
        draft["exit_status"] = EXIT_MEASURED
    elif is_partial_hold(draft):
        draft["exit_status"] = EXIT_PARTIAL
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
            "Measure AQ6 Harmonic Match ranking quality + upstream-error "
            "propagation against the frozen relevance benchmark (#1018)."
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
    args = parser.parse_args(argv)
    result = run_aq6_ranking_baseline(
        output_path=args.output,
        repo_root=args.repo_root,
        fixture_path=args.fixture,
    )
    print(
        json.dumps(
            {
                "exit_status": result["exit_status"],
                "queries_scored": result["as_labeled"]["queries_scored"],
                "precision_at_1": result["as_labeled"]["macro"]["precision_at_1"],
                "mrr_at_5": result["as_labeled"]["macro"]["mrr_at_5"],
                "ndcg_at_5": result["as_labeled"]["macro"]["ndcg_at_5"],
            }
        )
    )
    return 0 if result["exit_status"] == EXIT_MEASURED else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BENCHMARK_ID",
    "DOCUMENT_TYPE",
    "DOMAIN_TOKEN",
    "EXIT_INCOMPLETE",
    "EXIT_MEASURED",
    "EXIT_PARTIAL",
    "SCHEMA_VERSION",
    "SURFACE",
    "THEORY_PLANE_NOTE",
    "UPSTREAM_STATES",
    "WEIGHTS",
    "aggregate_query_metrics",
    "compute_upstream_deltas",
    "coverage_report",
    "is_measured",
    "is_partial_hold",
    "measure_bpm_cohorts",
    "measure_repeatability",
    "measure_upstream_states",
    "prove_missing_evidence_not_forced_certainty",
    "rank_query",
    "row_from_fixture_item",
    "run_aq6_ranking_baseline",
    "score_ranked_query",
    "theory_plane_visibility",
]
