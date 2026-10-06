# AQ5 Retrieval Baseline (frozen relevance query set)

**Status:** ACTIVE_SUPPORTING — measured current retrieval/ranking paths for [#1010](https://github.com/jannekbuengener/sample-brain/issues/1010)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#947](https://github.com/jannekbuengener/sample-brain/issues/947) (AQ5), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on:** [#1038](https://github.com/jannekbuengener/sample-brain/issues/1038) KPI contract, [#1009](https://github.com/jannekbuengener/sample-brain/issues/1009) relevance freeze  
**Normative KPI:** [`AQ5_RETRIEVAL_KPI_CONTRACT.md`](AQ5_RETRIEVAL_KPI_CONTRACT.md)  
**Query/label identity:** [`AQ5_RELEVANCE_BENCHMARK.md`](AQ5_RELEVANCE_BENCHMARK.md) / `sample-brain.aq5.relevance.adr0005-golden.v1`  
**Runner:** `python -m src.aq5_retrieval_baseline`

## Architecture outcome

```text
AQ5_RETRIEVAL_BASELINE_MEASURED
```

This slice measures **current** product-reachable retrieval paths on the frozen AQ5 relevance benchmark with **separate** reporting planes for relevance (`aq5.retrieval`), ranking/ANN equivalence (`aq5.ranking`), and operational latency (#958). It does **not** change search/embedding/ANN algorithms, promote sqlite-vec, invent graded NDCG labels, or commit private queries/samples.

## Candidate path inventory

| `candidate_id` | Plane | Product-reachable | Status in this baseline |
|---|---|---|---|
| `sample-brain.aq5.path.numpy.tier_a.vector_filter_hybrid` | `aq5.retrieval` | yes (default NumPy) | **measured** |
| `sample-brain.aq5.path.numpy.tier_b.text_clap` | `aq5.retrieval` | yes (CLAP text→sample) | **measured** |
| `sample-brain.aq5.path.numpy.tier_b.audio_clap` | `aq5.retrieval` | yes (CLAP audio→audio) | **measured** |
| `sample-brain.aq5.path.sqlite_vec.ann_vs_numpy` | `aq5.ranking` | yes (optional backend; **not** default) | **HOLD** — optional `sqlite-vec` unavailable here; overlap campaign remains [`SQLITE_VEC_GATE_EVIDENCE.md`](SQLITE_VEC_GATE_EVIDENCE.md); **no promotion** |
| `sample-brain.aq5.path.historical.vocal_proxy_spike` | `aq5.retrieval` | no | **HOLD** — excluded from #1009 freeze |

Identical #1009 query keys / candidate catalogs are used across comparable NumPy paths. ANN comparison (when measured later) must hold embedding/catalog/query set fixed vs NumPy reference.

## How to run

External work-dir + JSON only (outside the git tree):

```powershell
python -m src.aq5_retrieval_baseline `
  --work-dir <external-directory>/aq5-retrieval-baseline-work `
  --output <external-directory>/aq5-retrieval-baseline.json
```

Optional flags: `--skip-tier-b`, `--skip-runtime`, `--skip-sqlite-vec`, `--runtime-repetitions N`.

Exact floats live in the external JSON. Tables below are rounded display values. No private audio, absolute host paths, DBs, or model caches are committed.

## Plane separation (normative)

| Plane | Contents |
|---|---|
| `aq5.retrieval` | P@K / R@K / MRR / HitRate@K / hard-negative FP@5; per split × family × mode; failure buckets; NDCG **HOLD** |
| `aq5.ranking` | Deterministic ordered projection check (#959); ANN vs NumPy equivalence (HOLD here) |
| `operational` | Suite-wall p50/p95 via #958 methodology — **never** folded into relevance |

No `quality_latency` / opaque combined score.

## Measured summary (portable)

Benchmark: `sample-brain.aq5.relevance.adr0005-golden.v1` / `benchmark_version=1.0.0`  
External JSON `exit_status=AQ5_RETRIEVAL_BASELINE_MEASURED`  
Partition fingerprint: `6dfa03c4…0b4ff5a3`  
Query-set fingerprint: `654687d8…02e936f7`  
Queries scored: **46** (9 Tier-A + 37 Tier-B); errors: **0**

### Support

| Axis | Counts |
|---|---|
| split | CALIBRATION 15, TEST 31 |
| mode | text 26, audio 11, vector 3, filter 4, hybrid 2 |
| family | kick_snare_perc 6, pad_texture 4, riser_impact 6, dry_wet 7, vocal_no_vocal 6, genre_mood 8, tier_a_pipeline 9 |

### CALIBRATION → DEVELOPMENT/CALIBRATION (`aq5.retrieval`)

15 queries; mean P@1 **0.533**, P@5 **0.400**, P@10 **0.220**, R@10 **0.911**, MRR **0.691**, HitRate@5 **0.867**, hard-neg FP@5 **0.533**.

| Family | n | P@5 | MRR | Hit@5 | HN-FP@5 |
|---|---:|---:|---:|---:|---:|
| `tier_a_pipeline` | 3 | 0.600 | 1.000 | 1.000 | 0.000 |
| `kick_snare_perc` | 2 | 0.600 | 0.667 | 1.000 | 0.000 |
| `riser_impact` | 2 | 0.600 | 1.000 | 1.000 | 1.000 |
| `pad_texture` | 2 | 0.200 | 0.306 | 0.500 | 0.000 |
| `dry_wet` | 2 | 0.200 | 0.500 | 1.000 | 1.000 |
| `vocal_no_vocal` | 2 | 0.300 | 0.583 | 0.500 | 1.000 |
| `genre_mood` | 2 | 0.200 | 0.625 | 1.000 | 1.000 |

| Mode | n | P@5 | MRR |
|---|---:|---:|---:|
| vector | 1 | 0.600 | 1.000 |
| filter | 1 | 0.600 | 1.000 |
| hybrid | 1 | 0.600 | 1.000 |
| text | 6 | 0.267 | 0.505 |
| audio | 6 | 0.433 | 0.722 |

### TEST → TEST/HOLDOUT (`aq5.retrieval`)

31 queries; **no tuning on this split**. Mean P@1 **0.516**, P@5 **0.258**, P@10 **0.158**, R@10 **0.790**, MRR **0.610**, HitRate@5 **0.742**, hard-neg FP@5 **0.613**.

| Family | n | P@5 | MRR | Hit@5 | HN-FP@5 |
|---|---:|---:|---:|---:|---:|
| `tier_a_pipeline` | 6 | 0.600 | 1.000 | 1.000 | 0.000 |
| `kick_snare_perc` | 4 | 0.300 | 0.656 | 0.750 | 0.000 |
| `riser_impact` | 4 | 0.150 | 0.275 | 0.250 | 1.000 |
| `pad_texture` | 2 | 0.100 | 0.556 | 0.500 | 0.500 |
| `dry_wet` | 5 | 0.120 | 0.333 | 0.600 | 1.000 |
| `vocal_no_vocal` | 4 | 0.200 | 0.800 | 1.000 | 0.750 |
| `genre_mood` | 6 | 0.167 | 0.533 | 0.833 | 1.000 |

| Mode | n | P@5 | MRR |
|---|---:|---:|---:|
| vector | 2 | 0.600 | 1.000 |
| filter | 3 | 0.600 | 1.000 |
| hybrid | 1 | 0.600 | 1.000 |
| text | 20 | 0.160 | 0.395 |
| audio | 5 | 0.240 | 1.000 |

### Ranking plane (`aq5.ranking`)

| Check | Result |
|---|---|
| Deterministic Tier-A ordered projections (2 harness passes) | **measured** — 9/9 equal; tie/order checked (#959) |
| sqlite-vec ANN vs NumPy overlap | **HOLD** — optional dependency unavailable in this run; cite SQLITE_VEC_GATE_EVIDENCE; default backend remains NumPy; **no promotion** |

### Operational plane (#958)

Tier-A suite-wall wall-clock (`input_bucket=synthetic_unit`, 5 ok attempts): p50 ≈ **98 ms**, p95 ≈ **100 ms**. Diagnostic only — not a relevance substitute.

### HOLD stubs

| Item | Status |
|---|---|
| Graded relevance / NDCG@K | HOLD |
| `vocal_no_vocal` production claim | HOLD (slice still measured) |
| `genre_mood` production claim | HOLD (slice still measured) |
| Vocal proxy spike suite | HOLD / excluded |
| Private producer reality-check queries | HOLD |
| sqlite-vec promotion / production switch | out of scope / HOLD |

## Non-goals (this slice)

- no search / embedding / ANN / hybrid ranking algorithm changes
- no production backend switch / promotion thresholds
- no opaque relevance+latency score
- no private samples, private query text, or absolute host paths in committed artifacts
- no invented graded labels for NDCG

## Exit vocabulary

Exactly one:

- `AQ5_RETRIEVAL_BASELINE_MEASURED`
- `AQ5_RETRIEVAL_BASELINE_PARTIAL_HOLD`
- `AQ5_RETRIEVAL_BASELINE_INCOMPLETE`

This slice exits `AQ5_RETRIEVAL_BASELINE_MEASURED` for NumPy Tier-A + Tier-B text/audio on `sample-brain.aq5.relevance.adr0005-golden.v1`, with separate planes, explicit ANN/NDCG/production-claim HOLDs, and no algorithm or promotion change.
