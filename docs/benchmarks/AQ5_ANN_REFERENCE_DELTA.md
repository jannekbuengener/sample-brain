# AQ5 ANN / index approximation vs semantic relevance separation

**Status:** ACTIVE_SUPPORTING — measured ANN/reference ranking delta for [#1011](https://github.com/jannekbuengener/sample-brain/issues/1011)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#947](https://github.com/jannekbuengener/sample-brain/issues/947) (AQ5), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on:** [#1010](https://github.com/jannekbuengener/sample-brain/issues/1010) retrieval baseline (`AQ5_RETRIEVAL_BASELINE_MEASURED`)  
**Normative KPI:** [`AQ5_RETRIEVAL_KPI_CONTRACT.md`](AQ5_RETRIEVAL_KPI_CONTRACT.md)  
**Query/catalog identity:** [`AQ5_RELEVANCE_BENCHMARK.md`](AQ5_RELEVANCE_BENCHMARK.md) / `sample-brain.aq5.relevance.adr0005-golden.v1` (Tier-A deterministic vectors)  
**Historical large-N overlap (cite, do not reopen as AQ5 fixture authority):** [`SQLITE_VEC_GATE_EVIDENCE.md`](SQLITE_VEC_GATE_EVIDENCE.md)  
**Runner:** `python -m src.aq5_ann_reference_delta`

## Architecture outcome

```text
AQ5_ANN_REFERENCE_DELTA_MEASURED
```

This slice measures **index/backend approximation loss** against an explicit exact/reference search path on **identical fixed embeddings and query vectors**. It keeps that ranking-plane delta separate from semantic retrieval relevance (#1010 `aq5.retrieval`) and from operational latency/size (#958 / SQLITE_VEC_GATE methodology). It does **not** change search algorithms, promote sqlite-vec, invent graded NDCG labels, or publish an opaque relevance+latency score.

## Exact / approximate identities (frozen)

| Role | `path_id` | Owner surface | Default promotion |
|---|---|---|---|
| Exact / reference | `sample-brain.aq5.path.numpy.exact_reference` | `NumpySearchBackend` via `collect_search_hits(..., search_backend="numpy")` on Tier-A golden catalog | yes (current production default) |
| Approximate / index | `sample-brain.aq5.path.sqlite_vec.ann_vs_numpy` | `SqliteVecSearchBackend` via `collect_search_hits(..., search_backend="sqlite-vec")` after `rebuild_vec0_cache` on the **same** catalog/embeddings | **no** — evaluation only |

Semantic inputs held fixed: Tier-A suite vectors + query vectors from `tests/fixtures/search_quality/golden_v1.yaml` under benchmark `sample-brain.aq5.relevance.adr0005-golden.v1`. No embedding/model swap during approximation measurement.

## Plane separation (normative)

| Plane | Contents in this slice |
|---|---|
| `aq5.ranking` | Top-K set overlap vs reference, relevant-item rank displacement, ordered ranking deltas, deterministic tie/order checks (#959) |
| `aq5.retrieval` | **out of scope here** — reuse #1010 baseline; do not treat ANN overlap as semantic relevance |
| `operational` | Optional query/rebuild wall timings + index size notes via #958 / SQLITE_VEC_GATE methodology — **never** folded into ranking |

No `quality_latency` / opaque combined score. NDCG remains **HOLD** (no graded labels upstream).

## How to run

External work-dir + JSON only (outside the git tree):

```powershell
python -m src.aq5_ann_reference_delta `
  --work-dir <external-directory>/aq5-ann-reference-delta-work `
  --output <external-directory>/aq5-ann-reference-delta.json
```

Optional: `--skip-runtime`. Exact floats live in the external JSON. Tables below are rounded display values. No private audio, absolute host paths, DBs, or model caches are committed.

Fail-closed rule: when `sqlite-vec` is unavailable or the approximate path cannot be built, the harness exits `AQ5_ANN_BACKEND_HOLD` (or `AQ5_ANN_COMPARISON_INCOMPLETE` on partial failure) and **does not** silently substitute another backend.

## Measured summary (portable)

Benchmark: `sample-brain.aq5.relevance.adr0005-golden.v1` / Tier-A `golden_v1.yaml`  
External JSON `exit_status=AQ5_ANN_REFERENCE_DELTA_MEASURED`  
Reference: `sample-brain.aq5.path.numpy.exact_reference`  
Approximate: `sample-brain.aq5.path.sqlite_vec.ann_vs_numpy`  
Queries compared: **9** Tier-A (3 vector / 4 filter / 2 hybrid); errors: **0**  
Default production backend remains **NumPy**. **No promotion.**

### Ranking plane (`aq5.ranking`)

| Metric | Result |
|---|---|
| Mean Top-K set overlap (K=suite topk) | **1.000** |
| Queries with identical ordered Top-K | **9 / 9** |
| Mean \|rank displacement\| for relevant IDs | **0.000** |
| Deterministic NumPy ordered projections (2 passes) | **measured** — equal |
| Deterministic sqlite-vec ordered projections (2 passes) | **measured** — equal |

| Mode slice | n | mean overlap@K | identical ordered Top-K |
|---|---:|---:|---:|
| vector | 3 | 1.000 | 3/3 |
| filter | 4 | 1.000 | 4/4 |
| hybrid | 2 | 1.000 | 2/2 |

Interpretation: on the frozen Tier-A synthetic catalog, sqlite-vec brute-force vec0 reproduces the NumPy reference ranking exactly. This is **approximation equivalence evidence**, not a semantic-relevance claim and not a production switch.

### Operational plane (separate)

Paired NumPy+sqlite-vec query wall timing on Tier-A probe query (`input_bucket=synthetic_unit`, 5 ok attempts): p50 ≈ **9 ms**, p95 ≈ **9 ms**. Diagnostic only — not a relevance substitute. Large-N latency/size/rebuild budgets remain owned by [`SQLITE_VEC_GATE_EVIDENCE.md`](SQLITE_VEC_GATE_EVIDENCE.md) and are **not** promotion authority here.

### Reused historical evidence (not AQ5 fixture authority)

SQLITE_VEC_GATE Stage-1 float32 overlap@10 = 1.000 at N∈{1k,10k,100k} with latency gates still FAIL at 100k. That campaign answers scale/ops questions; this slice answers AQ5 fixture-bound ranking-delta questions. Upstream-release tracking [#74](https://github.com/jannekbuengener/sample-brain/issues/74) is **not** solved by this slice unless its live trigger is separately satisfied.

### HOLD stubs

| Item | Status |
|---|---|
| Graded relevance / NDCG@K | HOLD |
| Semantic retrieval quality as ANN proof | out of scope — use #1010 `aq5.retrieval` |
| sqlite-vec / ANN production promotion | blocked — quality + external readiness both required; this slice alone is insufficient |
| Opaque relevance+latency aggregate | forbidden |
| Private producer queries/samples | HOLD / not committed |

## Non-goals

- no search / embedding / ANN algorithm rewrite beyond thin measurement adapters
- no sqlite-vec / default production switch
- no opaque relevance+latency (or relevance+ANN) score
- no local index artifacts committed
- no inventing graded labels for NDCG
- no treating #74 as solved without its live trigger

## Exit vocabulary

Exactly one:

- `AQ5_ANN_REFERENCE_DELTA_MEASURED`
- `AQ5_ANN_BACKEND_HOLD`
- `AQ5_ANN_COMPARISON_INCOMPLETE`

This slice exits `AQ5_ANN_REFERENCE_DELTA_MEASURED` for NumPy exact vs sqlite-vec on frozen Tier-A vectors/queries, with ranking metrics separated from relevance and latency, fail-closed backend policy, and **no** promotion.
