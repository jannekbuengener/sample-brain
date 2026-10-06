# AQ5 Retrieval / Ranking Candidate Comparison (frozen relevance set)

**Status:** ACTIVE_SUPPORTING — reproducible candidate comparison for [#1012](https://github.com/jannekbuengener/sample-brain/issues/1012)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#947](https://github.com/jannekbuengener/sample-brain/issues/947) (AQ5), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on (CLOSED — consume, do not reopen):** [#1038](https://github.com/jannekbuengener/sample-brain/issues/1038) KPI, [#1009](https://github.com/jannekbuengener/sample-brain/issues/1009) relevance freeze, [#1010](https://github.com/jannekbuengener/sample-brain/issues/1010) retrieval baseline, [#1011](https://github.com/jannekbuengener/sample-brain/issues/1011) ANN/reference separation  
**Normative KPI:** [`AQ5_RETRIEVAL_KPI_CONTRACT.md`](AQ5_RETRIEVAL_KPI_CONTRACT.md)  
**Query/label identity:** [`AQ5_RELEVANCE_BENCHMARK.md`](AQ5_RELEVANCE_BENCHMARK.md) / `sample-brain.aq5.relevance.adr0005-golden.v1`  
**Baseline surface:** [`AQ5_RETRIEVAL_BASELINE.md`](AQ5_RETRIEVAL_BASELINE.md) / `python -m src.aq5_retrieval_baseline`  
**ANN plane (separate):** [`AQ5_ANN_REFERENCE_DELTA.md`](AQ5_ANN_REFERENCE_DELTA.md) / `python -m src.aq5_ann_reference_delta`  
**Compare runner:** `python -m src.aq5_retrieval_candidate_compare`

## Architecture outcome

```text
AQ5_RETRIEVAL_CANDIDATE_COMPARE_REPRODUCIBLE
```

This document freezes a **small, fair retrieval/ranking candidate set** (≤4) and a **reproducible comparison harness** on the frozen AQ5 relevance benchmark. Relevance quality, ANN approximation, and operational latency stay on **separate planes**. It does **not** promote a candidate, switch production search defaults, invent graded NDCG labels, or tune on TEST/HOLDOUT.

## Non-goals

- no production backend switch / no promotion thresholds
- no TEST/HOLDOUT threshold discovery or tuning
- no new heavy model/dependency solely for benchmark novelty
- no private calibration set / no private queries or samples
- no opaque relevance+latency (or relevance+ANN) score
- no inventing graded labels when NDCG remains HOLD
- no collapsing #1011 approximation into #1010 relevance

## Candidate identity (frozen ≤4)

All candidates are thin config / classical adapters over the **same** surfaces measured in #1010 (`collect_search_hits` + NumPy / optional CLAP). Suite query keys, relevance sets, and hard negatives stay identical across candidates.

| `candidate_id` | Adapter knobs | Derived from (#1010 evidence) |
|---|---|---|
| `retrieval.baseline.v1` | suite hybrid/filters/topk unchanged | #1010 measured NumPy Tier-A + Tier-B anchor |
| `hybrid.semantic_weight.0.8` | when suite declares hybrid: `semantic_weight=0.8` (metadata weights kept) | #1010 hybrid queries use `semantic_weight=0.2`; isolate metadata vs semantic pull |
| `classical.type_rerank.text_hint.0.5` | Tier-B text: type-token → `HybridQuery(target_type, type_weight=0.5)`; suite hybrid left intact | #1010 CALIBRATION hard-neg FP@5 ≈ 0.533 / family HN leaks |
| `classical.type_rerank.text_hint.1.0` | same classical path with `type_weight=1.0` | stronger classical type pull for the same HN-FP narrative |

### Scoring rule (normative)

1. Each candidate scores every #1009 query key with its declared adapter only.
2. Relevance metrics reuse #1010 helpers (`score_retrieval_query` / split×family×mode aggregates): P@K, R@K, MRR, HitRate@K, hard-negative FP@5; NDCG remains HOLD.
3. `retrieval.baseline.v1` must reproduce the #1010 harness aggregates on the same benchmark identity (same fingerprints).
4. CALIBRATION may narrate exploration; TEST/HOLDOUT is frozen evidence once — **no tuning**.
5. ANN approximation (#1011) is reported on `aq5.ranking` only and never folded into relevance macros.
6. Operational latency (#958) and determinism (#959) are recorded separately and never opaque-combined.
7. Do not invent promotion thresholds from TEST/HOLDOUT.

## Partition policy

| Overlay `split` | AQ5 role | Allowed use in this slice |
|---|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION | exploration / comparison narrative only |
| `TEST` | TEST / HOLDOUT | frozen evidence report once; **no threshold discovery** |

## How to run

External work-dir + JSON only (outside the git tree):

```powershell
python -m src.aq5_retrieval_candidate_compare `
  --work-dir <external-directory>/aq5-retrieval-candidate-compare-work `
  --output <external-directory>/aq5-retrieval-candidate-compare.json
```

Optional flags: `--skip-tier-b`, `--skip-runtime`, `--skip-ann`. The runner rejects outputs inside the git tree. Exact floats live in the external JSON; tables below are rounded display values. No private audio, absolute host paths, DBs, or model caches are committed.

## Artifact schema (compare)

| Field | Notes |
|---|---|
| `document_type` | `sample-brain.aq5.retrieval-candidate-compare.v1` |
| `schema_version` | `1.0.0` |
| `benchmark_id` | `sample-brain.aq5.relevance.adr0005-golden.v1` |
| `baseline_document_type` | `sample-brain.aq5.retrieval-baseline.v1` |
| `no_tuning_on_test` | always `true` |
| `production_switch` | always `false` |
| `candidates[]` | frozen registry + per-candidate `splits.CALIBRATION\|TEST` relevance metrics |
| `aq5.retrieval` | cross-candidate relevance plane (no latency/ANN mix-in) |
| `aq5.ranking` | determinism (#959) + ANN approximation carry (#1011) |
| `operational` | #958 suite-wall timings — diagnostic only |
| `automation_seam` | machine-readable status/decision tokens for #1040 quality loop |

## Plane separation (normative)

| Plane | Contents |
|---|---|
| `aq5.retrieval` | Per-candidate P@K / R@K / MRR / HitRate / hard-neg FP; per split × family × mode; NDCG HOLD |
| `aq5.ranking` | Deterministic ordered projection (#959); ANN vs NumPy approximation (#1011) — **not** a relevance substitute |
| `operational` | Suite-wall p50/p95 via #958 — **never** folded into relevance |

No `quality_latency` / opaque combined score.

## Measured summary (portable)

Benchmark: `sample-brain.aq5.relevance.adr0005-golden.v1` / `benchmark_version=1.0.0`  
External JSON `exit_status=AQ5_RETRIEVAL_CANDIDATE_COMPARE_REPRODUCIBLE`  
Partition fingerprint: `6dfa03c4…` / query-set fingerprint: `654687d8…` (same #1009 identity as #1010)  
Queries scored per candidate: **46** (9 Tier-A + 37 Tier-B). Production search defaults were **not** switched. sqlite-vec was **not** promoted.

### CALIBRATION → DEVELOPMENT/CALIBRATION (exploration)

15 queries. Exploration only — not a promotion gate.

| Candidate | n | P@5 | MRR | Hit@5 | HN-FP@5 | Notes |
|---|---:|---:|---:|---:|---:|---|
| `retrieval.baseline.v1` | 15 | 0.400 | 0.691 | 0.867 | 0.533 | matches #1010 anchor |
| `hybrid.semantic_weight.0.8` | 15 | 0.400 | 0.691 | 0.867 | 0.533 | ties baseline (hybrid-only delta) |
| `classical.type_rerank.text_hint.0.5` | 15 | 0.413 | 0.748 | 0.933 | 0.533 | MRR/Hit↑; HN-FP unchanged |
| `classical.type_rerank.text_hint.1.0` | 15 | 0.413 | 0.748 | 0.933 | 0.533 | ties 0.5 on this set |

### TEST → TEST/HOLDOUT (frozen evidence; no tuning)

31 queries. Report once; do not tune.

| Candidate | n | P@5 | MRR | Hit@5 | HN-FP@5 | Notes |
|---|---:|---:|---:|---:|---:|---|
| `retrieval.baseline.v1` | 31 | 0.258 | 0.610 | 0.742 | 0.613 | matches #1010 anchor |
| `hybrid.semantic_weight.0.8` | 31 | 0.258 | 0.610 | 0.742 | 0.613 | ties baseline |
| `classical.type_rerank.text_hint.0.5` | 31 | 0.277 | 0.701 | 0.806 | 0.613 | MRR/Hit↑; HN-FP unchanged |
| `classical.type_rerank.text_hint.1.0` | 31 | 0.277 | 0.701 | 0.806 | 0.613 | ties 0.5 on this set |

### Ranking / operational planes

| Check | Result |
|---|---|
| Determinism (#959) on baseline Tier-A ordered projections (2 harness passes) | **measured** — 9/9 equal; tie/order checked |
| ANN approximation (#1011 carry) | **HOLD** in this environment (`AQ5_ANN_BACKEND_HOLD`); cite closed [#1011](https://github.com/jannekbuengener/sample-brain/issues/1011) MEASURED overlap 1.0 on Tier-A — ranking plane only; **no promotion** |
| Operational #958 Tier-A suite-wall (5 ok attempts) | p50 ≈ **75 ms**, p95 ≈ **77 ms** — diagnostic only |

### Non-promotional observation

On this frozen public/synthetic set, thin classical type-hint re-rank improves mean MRR and HitRate@5 on both CALIBRATION and frozen TEST without moving hard-negative FP@5, while the hybrid semantic-weight adapter ties `retrieval.baseline.v1`. CALIBRATION narrative is not a production promotion proof. Decision / keep-current belongs to a later scoped issue (#1014); this slice only freezes the reproducible compare.

## HOLD stubs

| Item | Status |
|---|---|
| Graded relevance / NDCG@K | HOLD |
| `vocal_no_vocal` / `genre_mood` production claim | HOLD (still measured) |
| sqlite-vec production promotion | HOLD / out of scope |
| Opaque relevance+latency score | forbidden |
| Private producer reality-check queries | HOLD |

## AQ8 / upstream reuse (by reference)

Consume closed [#956](https://github.com/jannekbuengener/sample-brain/issues/956) / [#958](https://github.com/jannekbuengener/sample-brain/issues/958) / [#959](https://github.com/jannekbuengener/sample-brain/issues/959), plus #1010/#1011 evidence, by reference. Do not reopen those issues in this slice. Leave automation-facing seams (headless runner, machine-readable exit/status tokens, portable identity fields) for [#1040](https://github.com/jannekbuengener/sample-brain/issues/1040) — do not build the orchestrator here.

## Exit vocabulary

Exactly one:

- `AQ5_RETRIEVAL_CANDIDATE_COMPARE_REPRODUCIBLE`
- `AQ5_RETRIEVAL_NO_JUSTIFIED_CANDIDATE`
- `AQ5_RETRIEVAL_CANDIDATE_COMPARE_INCOMPLETE`

This slice exits `AQ5_RETRIEVAL_CANDIDATE_COMPARE_REPRODUCIBLE` for the frozen ≤4 candidates on identical #1009 query/relevance records with separate planes, CALIBRATION exploration preceding frozen TEST evidence, and no production switch.
