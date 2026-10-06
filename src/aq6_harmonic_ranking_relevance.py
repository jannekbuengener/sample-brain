"""AQ6 Harmonic Match ranking relevance benchmark — frozen labels (#1016).

Plane: graded ranking relevance only. Distinct from theory truth (#1015) and
from human preference. Current product 0.75/0.25 weights are measurement
targets, not ground truth.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .aq6_harmonic_theory_truth_table import classify_theory_pair
from .key_signature import parse_key_signature

BENCHMARK_ID = "sample-brain.aq6.harmonic-ranking.relevance.v1"
DOCUMENT_TYPE = "sample-brain.aq6.harmonic-ranking-relevance.v1"
BENCHMARK_VERSION = "1.0.0"
DOMAIN_TOKEN = "aq6.ranking"
LABEL_SOURCE = "synthetic_theory_aligned_graded_v1"
THEORY_TRUTH_TABLE_ID = "sample-brain.aq6.harmonic-theory.truth-table.v1"

PARTITIONS: tuple[str, ...] = ("CALIBRATION", "TEST", "HOLDOUT")
DEFAULT_KS: tuple[int, ...] = (1, 3, 5)
RELEVANCE_GRADE_MEANINGS: dict[str, str] = {
    "3": "direct_compatible",
    "2": "related_compatible",
    "1": "transpose_compatible",
    "0": "incompatible_known",
}

FIXTURE_RELPATH = Path(
    "tests/fixtures/aq6_harmonic_ranking/relevance_benchmark_v1.json"
)


class Aq6RankingRelevanceError(ValueError):
    """Raised when the AQ6 ranking relevance freeze is inconsistent."""


def _key_evidence(key: str | None) -> str:
    if key is None:
        return "missing_key"
    parsed = parse_key_signature(key)
    if parsed is None:
        return "unparseable"
    if parsed.mode is None:
        return "missing_mode"
    return "modeful"


def _bpm_evidence(ref_bpm: float | None, cand_bpm: float | None) -> str:
    ref_ok = ref_bpm is not None and math.isfinite(ref_bpm) and ref_bpm > 0
    cand_ok = cand_bpm is not None and math.isfinite(cand_bpm) and cand_bpm > 0
    if ref_ok and cand_ok:
        return "known"
    if not ref_ok and not cand_ok:
        return "missing_both"
    if not ref_ok:
        return "missing_reference"
    return "missing_candidate"


def _grade_for_theory(theory: Mapping[str, Any]) -> tuple[int | None, bool]:
    """Return (relevance_grade, ranking_eligible) from a theory cell."""
    compatibility = theory["compatibility"]
    relation = theory["relation"]
    if compatibility == "uncertain":
        return None, False
    if compatibility == "incompatible":
        return 0, True
    if relation == "direct":
        return 3, True
    if relation == "related":
        return 2, True
    if relation == "transpose":
        return 1, True
    # Modeful but unexpected — fail closed for ranking eligibility.
    return None, False


def _candidate_row(
    *,
    synthetic_id: str,
    key: str | None,
    bpm: float | None,
    reference_key: str | None,
    reference_bpm: float | None,
) -> dict[str, Any]:
    theory = classify_theory_pair(reference_key, key)
    grade, eligible = _grade_for_theory(theory)
    return {
        "synthetic_id": synthetic_id,
        "key": key,
        "bpm": bpm,
        "key_evidence": _key_evidence(key),
        "bpm_evidence": _bpm_evidence(reference_bpm, bpm),
        "theory_relation": theory["relation"],
        "theory_compatibility": theory["compatibility"],
        "relevance_grade": grade,
        "ranking_eligible": eligible,
        "path": f"synthetic/aq6_ranking/{synthetic_id}.wav",
    }


def _reference_row(
    *,
    synthetic_id: str,
    key: str | None,
    bpm: float | None,
) -> dict[str, Any]:
    return {
        "synthetic_id": synthetic_id,
        "key": key,
        "bpm": bpm,
        "key_evidence": _key_evidence(key),
        "bpm_evidence": (
            "known"
            if bpm is not None and math.isfinite(bpm) and bpm > 0
            else "missing_reference"
        ),
        "path": f"synthetic/aq6_ranking/{synthetic_id}.wav",
    }


def _query(
    *,
    query_id: str,
    partition: str,
    reference: dict[str, Any],
    candidates: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "query_id": query_id,
        "partition": partition,
        "reference": reference,
        "candidates": list(candidates),
    }


def build_relevance_benchmark_queries() -> list[dict[str, Any]]:
    """Build the frozen synthetic query/candidate set (deterministic order)."""
    queries: list[dict[str, Any]] = []

    # CALIBRATION — Cmaj @ 128 with full relation coverage + BPM known
    ref_cal = _reference_row(synthetic_id="ref_cmaj_128", key="Cmaj", bpm=128.0)
    queries.append(
        _query(
            query_id="q_cal_cmaj_full_spectrum",
            partition="CALIBRATION",
            reference=ref_cal,
            candidates=[
                _candidate_row(
                    synthetic_id="cal_direct_cmaj",
                    key="Cmaj",
                    bpm=128.0,
                    reference_key=ref_cal["key"],
                    reference_bpm=ref_cal["bpm"],
                ),
                _candidate_row(
                    synthetic_id="cal_related_amin",
                    key="Amin",
                    bpm=128.0,
                    reference_key=ref_cal["key"],
                    reference_bpm=ref_cal["bpm"],
                ),
                _candidate_row(
                    synthetic_id="cal_related_gmaj",
                    key="Gmaj",
                    bpm=126.0,
                    reference_key=ref_cal["key"],
                    reference_bpm=ref_cal["bpm"],
                ),
                _candidate_row(
                    synthetic_id="cal_transpose_dmaj",
                    key="Dmaj",
                    bpm=128.0,
                    reference_key=ref_cal["key"],
                    reference_bpm=ref_cal["bpm"],
                ),
                _candidate_row(
                    synthetic_id="cal_incompatible_fsharpmaj",
                    key="F#maj",
                    bpm=128.0,
                    reference_key=ref_cal["key"],
                    reference_bpm=ref_cal["bpm"],
                ),
                _candidate_row(
                    synthetic_id="cal_uncertain_root_only",
                    key="G",
                    bpm=128.0,
                    reference_key=ref_cal["key"],
                    reference_bpm=ref_cal["bpm"],
                ),
                _candidate_row(
                    synthetic_id="cal_uncertain_missing_key",
                    key=None,
                    bpm=128.0,
                    reference_key=ref_cal["key"],
                    reference_bpm=ref_cal["bpm"],
                ),
            ],
        )
    )

    # CALIBRATION — BPM missing on candidate (secondary evidence explicit)
    ref_cal_bpm = _reference_row(synthetic_id="ref_gmaj_120", key="Gmaj", bpm=120.0)
    queries.append(
        _query(
            query_id="q_cal_gmaj_bpm_missing_candidate",
            partition="CALIBRATION",
            reference=ref_cal_bpm,
            candidates=[
                _candidate_row(
                    synthetic_id="cal_g_direct_bpm_missing",
                    key="Gmaj",
                    bpm=None,
                    reference_key=ref_cal_bpm["key"],
                    reference_bpm=ref_cal_bpm["bpm"],
                ),
                _candidate_row(
                    synthetic_id="cal_g_related_emin",
                    key="Emin",
                    bpm=120.0,
                    reference_key=ref_cal_bpm["key"],
                    reference_bpm=ref_cal_bpm["bpm"],
                ),
                _candidate_row(
                    synthetic_id="cal_g_incompatible_csharpmaj",
                    key="C#maj",
                    bpm=120.0,
                    reference_key=ref_cal_bpm["key"],
                    reference_bpm=ref_cal_bpm["bpm"],
                ),
            ],
        )
    )

    # TEST — Dmin locked evaluation set
    ref_test = _reference_row(synthetic_id="ref_dmin_140", key="Dmin", bpm=140.0)
    queries.append(
        _query(
            query_id="q_test_dmin_spectrum",
            partition="TEST",
            reference=ref_test,
            candidates=[
                _candidate_row(
                    synthetic_id="test_direct_dmin",
                    key="Dmin",
                    bpm=140.0,
                    reference_key=ref_test["key"],
                    reference_bpm=ref_test["bpm"],
                ),
                _candidate_row(
                    synthetic_id="test_related_fmaj",
                    key="Fmaj",
                    bpm=140.0,
                    reference_key=ref_test["key"],
                    reference_bpm=ref_test["bpm"],
                ),
                _candidate_row(
                    synthetic_id="test_transpose_emin",
                    key="Emin",
                    bpm=138.0,
                    reference_key=ref_test["key"],
                    reference_bpm=ref_test["bpm"],
                ),
                _candidate_row(
                    synthetic_id="test_incompatible_abmaj",
                    key="G#maj",
                    bpm=140.0,
                    reference_key=ref_test["key"],
                    reference_bpm=ref_test["bpm"],
                ),
                _candidate_row(
                    synthetic_id="test_uncertain_unparseable",
                    key="not-a-key",
                    bpm=140.0,
                    reference_key=ref_test["key"],
                    reference_bpm=ref_test["bpm"],
                ),
            ],
        )
    )

    # TEST — reference BPM missing
    ref_test_bpm = _reference_row(
        synthetic_id="ref_amaj_bpm_missing", key="Amaj", bpm=None
    )
    queries.append(
        _query(
            query_id="q_test_amaj_bpm_missing_reference",
            partition="TEST",
            reference=ref_test_bpm,
            candidates=[
                _candidate_row(
                    synthetic_id="test_a_direct",
                    key="Amaj",
                    bpm=100.0,
                    reference_key=ref_test_bpm["key"],
                    reference_bpm=ref_test_bpm["bpm"],
                ),
                _candidate_row(
                    synthetic_id="test_a_related_fsharpmin",
                    key="F#min",
                    bpm=100.0,
                    reference_key=ref_test_bpm["key"],
                    reference_bpm=ref_test_bpm["bpm"],
                ),
                _candidate_row(
                    synthetic_id="test_a_incompatible_dsharpmaj",
                    key="D#maj",
                    bpm=100.0,
                    reference_key=ref_test_bpm["key"],
                    reference_bpm=ref_test_bpm["bpm"],
                ),
            ],
        )
    )

    # HOLDOUT — Fmaj locked final check
    ref_hold = _reference_row(synthetic_id="ref_fmaj_110", key="Fmaj", bpm=110.0)
    queries.append(
        _query(
            query_id="q_hold_fmaj_spectrum",
            partition="HOLDOUT",
            reference=ref_hold,
            candidates=[
                _candidate_row(
                    synthetic_id="hold_direct_fmaj",
                    key="Fmaj",
                    bpm=110.0,
                    reference_key=ref_hold["key"],
                    reference_bpm=ref_hold["bpm"],
                ),
                _candidate_row(
                    synthetic_id="hold_related_dmin",
                    key="Dmin",
                    bpm=110.0,
                    reference_key=ref_hold["key"],
                    reference_bpm=ref_hold["bpm"],
                ),
                _candidate_row(
                    synthetic_id="hold_transpose_gmaj",
                    key="Gmaj",
                    bpm=112.0,
                    reference_key=ref_hold["key"],
                    reference_bpm=ref_hold["bpm"],
                ),
                _candidate_row(
                    synthetic_id="hold_incompatible_bmaj",
                    key="Bmaj",
                    bpm=110.0,
                    reference_key=ref_hold["key"],
                    reference_bpm=ref_hold["bpm"],
                ),
                _candidate_row(
                    synthetic_id="hold_uncertain_missing_mode",
                    key="C",
                    bpm=110.0,
                    reference_key=ref_hold["key"],
                    reference_bpm=ref_hold["bpm"],
                ),
            ],
        )
    )

    return queries


def build_relevance_benchmark_document() -> dict[str, Any]:
    queries = build_relevance_benchmark_queries()
    support = {
        "queries_total": len(queries),
        "by_partition": {p: 0 for p in PARTITIONS},
        "candidates_total": 0,
        "eligible_by_grade": {str(g): 0 for g in (0, 1, 2, 3)},
        "ranking_ineligible": 0,
        "has_direct": False,
        "has_related": False,
        "has_transpose": False,
        "has_incompatible": False,
        "has_uncertain_evidence": False,
        "has_bpm_known": False,
        "has_bpm_missing": False,
    }
    for query in queries:
        support["by_partition"][query["partition"]] += 1
        ref = query["reference"]
        if ref.get("bpm_evidence") == "known":
            support["has_bpm_known"] = True
        else:
            support["has_bpm_missing"] = True
        for cand in query["candidates"]:
            support["candidates_total"] += 1
            if cand["ranking_eligible"]:
                grade = cand["relevance_grade"]
                support["eligible_by_grade"][str(grade)] += 1
                if grade == 3:
                    support["has_direct"] = True
                elif grade == 2:
                    support["has_related"] = True
                elif grade == 1:
                    support["has_transpose"] = True
                elif grade == 0:
                    support["has_incompatible"] = True
            else:
                support["ranking_ineligible"] += 1
                support["has_uncertain_evidence"] = True
            if cand["bpm_evidence"] != "known":
                support["has_bpm_missing"] = True
            else:
                support["has_bpm_known"] = True

    return {
        "document_type": DOCUMENT_TYPE,
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": BENCHMARK_VERSION,
        "domain": DOMAIN_TOKEN,
        "label_source": LABEL_SOURCE,
        "theory_truth_table_id": THEORY_TRUTH_TABLE_ID,
        "relevance_grades": dict(RELEVANCE_GRADE_MEANINGS),
        "binary_relevant_min_grade": 1,
        "default_ks": list(DEFAULT_KS),
        "partitions": list(PARTITIONS),
        "support": support,
        "queries": queries,
    }


def relevance_benchmark_json_bytes(
    document: Mapping[str, Any] | None = None,
) -> bytes:
    doc = build_relevance_benchmark_document() if document is None else document
    payload = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=False)
    return (payload + "\n").encode("utf-8")


def write_relevance_benchmark_fixture(path: Path) -> dict[str, Any]:
    document = build_relevance_benchmark_document()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(relevance_benchmark_json_bytes(document))
    return document


def load_relevance_benchmark_fixture(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def is_private_absolute_path(path: str) -> bool:
    """Reject Windows drive paths and POSIX absolute host paths."""
    if not path:
        return False
    if path.startswith("synthetic/"):
        return False
    if len(path) >= 3 and path[1] == ":" and path[0].isalpha():
        return True
    if path.startswith("/") and not path.startswith("//"):
        # Allow only explicit synthetic roots; bare absolute = private/host.
        return not path.startswith("/synthetic/")
    if path.startswith("\\\\") or path.startswith("//"):
        return True
    return False


def audit_relevance_benchmark(
    document: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate identities, theory alignment, partitions, and path hygiene."""
    doc = build_relevance_benchmark_document() if document is None else dict(document)
    findings: list[str] = []

    if doc.get("benchmark_id") != BENCHMARK_ID:
        findings.append(f"benchmark_id mismatch: {doc.get('benchmark_id')!r}")
    if doc.get("document_type") != DOCUMENT_TYPE:
        findings.append(f"document_type mismatch: {doc.get('document_type')!r}")
    if doc.get("domain") != DOMAIN_TOKEN:
        findings.append(f"domain mismatch: {doc.get('domain')!r}")
    if doc.get("theory_truth_table_id") != THEORY_TRUTH_TABLE_ID:
        findings.append("theory_truth_table_id must cite #1015 identity")

    query_ids: list[str] = []
    pair_grades: dict[tuple[str, str], int | None] = {}
    coverage = {
        "direct": False,
        "related": False,
        "transpose": False,
        "incompatible": False,
        "uncertain": False,
        "bpm_known": False,
        "bpm_missing": False,
    }

    for query in doc.get("queries") or []:
        qid = str(query.get("query_id"))
        query_ids.append(qid)
        partition = query.get("partition")
        if partition not in PARTITIONS:
            findings.append(f"{qid}: invalid partition {partition!r}")
        ref = query.get("reference") or {}
        ref_id = str(ref.get("synthetic_id"))
        ref_key = ref.get("key")
        ref_bpm = ref.get("bpm")
        if is_private_absolute_path(str(ref.get("path") or "")):
            findings.append(f"{qid}: private reference path")
        if ref.get("bpm_evidence") == "known":
            coverage["bpm_known"] = True
        else:
            coverage["bpm_missing"] = True

        for cand in query.get("candidates") or []:
            cid = str(cand.get("synthetic_id"))
            if is_private_absolute_path(str(cand.get("path") or "")):
                findings.append(f"{qid}:{cid}: private candidate path")
            theory = classify_theory_pair(ref_key, cand.get("key"))
            if cand.get("theory_relation") != theory["relation"]:
                findings.append(
                    f"{qid}:{cid}: theory_relation drift vs #1015 "
                    f"({cand.get('theory_relation')} != {theory['relation']})"
                )
            if cand.get("theory_compatibility") != theory["compatibility"]:
                findings.append(
                    f"{qid}:{cid}: theory_compatibility drift vs #1015"
                )
            expected_grade, expected_eligible = _grade_for_theory(theory)
            if cand.get("ranking_eligible") != expected_eligible:
                findings.append(f"{qid}:{cid}: ranking_eligible mismatch")
            if cand.get("relevance_grade") != expected_grade:
                findings.append(
                    f"{qid}:{cid}: relevance_grade mismatch "
                    f"({cand.get('relevance_grade')} != {expected_grade})"
                )
            expected_bpm = _bpm_evidence(ref_bpm, cand.get("bpm"))
            if cand.get("bpm_evidence") != expected_bpm:
                findings.append(f"{qid}:{cid}: bpm_evidence mismatch")

            pair = (ref_id, cid)
            grade = cand.get("relevance_grade")
            if pair in pair_grades and pair_grades[pair] != grade:
                findings.append(f"conflicting grades for pair {pair}")
            pair_grades[pair] = grade

            if cand.get("ranking_eligible"):
                g = cand.get("relevance_grade")
                if g == 3:
                    coverage["direct"] = True
                elif g == 2:
                    coverage["related"] = True
                elif g == 1:
                    coverage["transpose"] = True
                elif g == 0:
                    coverage["incompatible"] = True
            else:
                coverage["uncertain"] = True
            if cand.get("bpm_evidence") != "known":
                coverage["bpm_missing"] = True
            else:
                coverage["bpm_known"] = True

    if len(query_ids) != len(set(query_ids)):
        findings.append("duplicate query_id values")
    for name, ok in coverage.items():
        if not ok:
            findings.append(f"coverage missing: {name}")

    return {
        "status": "PASS" if not findings else "FAIL",
        "findings": findings,
        "coverage": coverage,
        "query_count": len(query_ids),
    }


def eligible_candidates(
    query: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [c for c in query.get("candidates") or [] if c.get("ranking_eligible")]


def grades_by_id(query: Mapping[str, Any]) -> dict[str, int]:
    return {
        str(c["synthetic_id"]): int(c["relevance_grade"])
        for c in eligible_candidates(query)
        if c.get("relevance_grade") is not None
    }


def is_relevant(grade: int, *, min_grade: int = 1) -> bool:
    return grade >= min_grade


def precision_at_k(
    ranked_ids: Sequence[str],
    grades: Mapping[str, int],
    k: int,
    *,
    min_grade: int = 1,
) -> float:
    if k <= 0:
        raise Aq6RankingRelevanceError("k must be positive")
    top = list(ranked_ids)[:k]
    hits = sum(
        1
        for item in top
        if item in grades and is_relevant(grades[item], min_grade=min_grade)
    )
    return hits / k


def mrr_at_k(
    ranked_ids: Sequence[str],
    grades: Mapping[str, int],
    k: int,
    *,
    min_grade: int = 1,
) -> float:
    if k <= 0:
        raise Aq6RankingRelevanceError("k must be positive")
    for idx, item in enumerate(list(ranked_ids)[:k], start=1):
        if item in grades and is_relevant(grades[item], min_grade=min_grade):
            return 1.0 / idx
    return 0.0


def _dcg(gains: Sequence[float]) -> float:
    total = 0.0
    for idx, gain in enumerate(gains, start=1):
        total += gain / math.log2(idx + 1)
    return total


def ndcg_at_k(
    ranked_ids: Sequence[str],
    grades: Mapping[str, int],
    k: int,
) -> float | None:
    """Graded NDCG@K over eligible candidates only.

    Returns None when IDCG is 0 (no positive graded items).
    """
    if k <= 0:
        raise Aq6RankingRelevanceError("k must be positive")
    ideal_grades = sorted(grades.values(), reverse=True)[:k]
    ideal_gains = [float((2**g) - 1) for g in ideal_grades]
    idcg = _dcg(ideal_gains)
    if idcg == 0.0:
        return None
    pred_gains = [
        float((2 ** grades[item]) - 1) if item in grades else 0.0
        for item in list(ranked_ids)[:k]
    ]
    return _dcg(pred_gains) / idcg


def top_k_false_positive_rate(
    ranked_ids: Sequence[str],
    grades: Mapping[str, int],
    k: int,
) -> float:
    if k <= 0:
        raise Aq6RankingRelevanceError("k must be positive")
    top = list(ranked_ids)[:k]
    fps = sum(1 for item in top if grades.get(item) == 0)
    return fps / k


def score_ranking_for_query(
    query: Mapping[str, Any],
    ranked_ids: Sequence[str],
    *,
    ks: Sequence[int] = DEFAULT_KS,
) -> dict[str, Any]:
    grades = grades_by_id(query)
    eligible = eligible_candidates(query)
    ineligible = [
        c for c in query.get("candidates") or [] if not c.get("ranking_eligible")
    ]
    metrics: dict[str, Any] = {
        "query_id": query.get("query_id"),
        "partition": query.get("partition"),
        "eligible_count": len(eligible),
        "ineligible_count": len(ineligible),
        "relevant_count": sum(1 for g in grades.values() if is_relevant(g)),
    }
    for k in ks:
        metrics[f"precision_at_{k}"] = precision_at_k(ranked_ids, grades, k)
        metrics[f"mrr_at_{k}"] = mrr_at_k(ranked_ids, grades, k)
        metrics[f"ndcg_at_{k}"] = ndcg_at_k(ranked_ids, grades, k)
        metrics[f"top_{k}_false_positive_rate"] = top_k_false_positive_rate(
            ranked_ids, grades, k
        )
    return metrics


def iter_queries(
    document: Mapping[str, Any],
    *,
    partition: str | None = None,
) -> Iterable[dict[str, Any]]:
    for query in document.get("queries") or []:
        if partition is None or query.get("partition") == partition:
            yield query


__all__ = [
    "BENCHMARK_ID",
    "BENCHMARK_VERSION",
    "DEFAULT_KS",
    "DOCUMENT_TYPE",
    "DOMAIN_TOKEN",
    "FIXTURE_RELPATH",
    "LABEL_SOURCE",
    "PARTITIONS",
    "RELEVANCE_GRADE_MEANINGS",
    "THEORY_TRUTH_TABLE_ID",
    "Aq6RankingRelevanceError",
    "audit_relevance_benchmark",
    "build_relevance_benchmark_document",
    "build_relevance_benchmark_queries",
    "eligible_candidates",
    "grades_by_id",
    "is_private_absolute_path",
    "is_relevant",
    "iter_queries",
    "load_relevance_benchmark_fixture",
    "mrr_at_k",
    "ndcg_at_k",
    "precision_at_k",
    "relevance_benchmark_json_bytes",
    "score_ranking_for_query",
    "top_k_false_positive_rate",
    "write_relevance_benchmark_fixture",
]
