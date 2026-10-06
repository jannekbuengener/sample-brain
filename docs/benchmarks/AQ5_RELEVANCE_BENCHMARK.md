# AQ5 Relevance Labels, Hard Negatives & Query-Set Freeze

**Status:** ACTIVE_SUPPORTING — relevance benchmark freeze for [#1009](https://github.com/jannekbuengener/sample-brain/issues/1009)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#947](https://github.com/jannekbuengener/sample-brain/issues/947) (AQ5), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on:** [#1038](https://github.com/jannekbuengener/sample-brain/issues/1038) / `docs/benchmarks/AQ5_RETRIEVAL_KPI_CONTRACT.md` (`AQ5_RETRIEVAL_KPI_CONTRACT_FROZEN`)  
**Related evidence (cite, do not reopen):** [#73](https://github.com/jannekbuengener/sample-brain/issues/73) / ADR-0005 / `docs/benchmarks/SEARCH_QUALITY_EVIDENCE.md`; `docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md` (ANN/latency plane — separate)  
**Related (by reference only):** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) portable join; [#957](https://github.com/jannekbuengener/sample-brain/issues/957) / [#958](https://github.com/jannekbuengener/sample-brain/issues/958) / [#959](https://github.com/jannekbuengener/sample-brain/issues/959)  
**Tooling:** `src/aq5_relevance_benchmark.py`

## Architecture outcome

```text
AQ5_RELEVANCE_BENCHMARK_FROZEN
```

This slice **audits and freezes** a reproducible AQ5 query/relevance identity from existing Tier-A / Tier-B ADR-0005 suites: stable query keys, binary relevance labels, hard negatives where present, CALIBRATION/TEST roles, family support counts, and explicit HOLDs. It does **not** change search/embedding/ANN algorithms, promote sqlite-vec, invent graded labels for NDCG, or commit private samples/query text.

## Named benchmark identity

| Field | Value |
|---|---|
| `benchmark_id` | `sample-brain.aq5.relevance.adr0005-golden.v1` |
| `document_type` | `sample-brain.aq5.relevance-benchmark.v1` |
| `benchmark_version` | `1.0.0` |
| `label_source` | `adr0005_synthetic_binary` |
| Included Tier-A suite | `tests/fixtures/search_quality/golden_v1.yaml` (9 queries) |
| Included Tier-B suite | `tests/fixtures/search_quality/golden_v2_clap.yaml` (37 queries) |
| Partition overlay | `tests/fixtures/search_quality/aq5_relevance_benchmark_v1.yaml` |
| Composite query identity | `suite:query_id` (e.g. `tier_b:kick_text_basic`) |

KPI contract lift (narrow):

```text
AQ5_LABELED_PUBLIC_RELEVANCE_BENCHMARK = sample-brain.aq5.relevance.adr0005-golden.v1
```

This adopts **public/synthetic** ADR-0005 fixtures already on `main`. It does **not** claim human-graded producer-library relevance or unlock NDCG.

## Ownership

| Concern | Owner |
|---|---|
| Benchmark id, query keys, partitions, label audit, leakage checks | this freeze |
| Metric definitions / plane separation | `AQ5_RETRIEVAL_KPI_CONTRACT.md` |
| Tier-A/Tier-B suite schema + harness | ADR-0005 + `src/search_quality_contract.py` / `src/search_eval.py` |
| Published relevance campaign numbers | `SEARCH_QUALITY_EVIDENCE.md` (#73) |
| Search / embed / ANN algorithms | out of scope |
| Promotion thresholds / backend switch | future evidence-backed issues only |

## Non-goals

- no search / embedding / ANN / hybrid ranking algorithm changes
- no production backend switch
- no opaque relevance+latency score
- no private samples, private query text, or absolute host paths in committed artifacts
- no invented graded labels solely to unlock NDCG
- no silent dropping of unsupported families (HOLD instead)
- no rebuild of proven ADR-0005 query sets without need

## Adopted surfaces

| Surface | Role in this freeze |
|---|---|
| `golden_v1.yaml` | Tier-A pipeline regression queries (vector / filter / hybrid); binary `relevant_sample_ids`; no hard negatives |
| `golden_v2_clap.yaml` | Tier-B semantic families (6/6); binary relevance + `negative_sample_ids` on every query |
| `aq5_relevance_benchmark_v1.yaml` | Frozen CALIBRATION / TEST assignment for every included query id |
| `golden_v2_clap_vocal_proxy_spike.yaml` | **HOLD / excluded** — historical proxy spike; overlapping query ids with Tier-B golden; not in aggregate identity |

## Relevance & hard-negative policy

| Policy | Rule |
|---|---|
| Relevance scheme | **binary** via `relevant_sample_ids` (required, non-empty for scored queries) |
| Hard negatives | Tier-B: required present and disjoint from relevant; Tier-A: absent → hard-negative FP metrics N/A (HOLD stub) |
| Graded labels | **none** in adopted suites → NDCG **HOLD** |
| Uncertain labels | do not force into relevant sets |
| Private queries | reality-check only later; not calibration truth; not committed |

## Partition policy

| Overlay `split` | KPI role |
|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION |
| `TEST` | TEST / HOLDOUT |

- Every included query appears in **exactly one** split.
- Do **not** tune thresholds, labels, or embeddings on TEST/HOLDOUT.
- Catalog samples may be shared across queries (retrieval corpus); partition leakage is defined on **query keys** and on identical query text / `query_audio_fixture` crossing splits.

## Query-family support (or HOLD)

| Family / slice | Support in freeze | Notes |
|---|---|---|
| `kick_snare_perc` | measured (count ≥ 1) | Tier-B |
| `pad_texture` | measured | Tier-B |
| `riser_impact` | measured | Tier-B |
| `dry_wet` | measured | Tier-B |
| `vocal_no_vocal` | measured + **production-claim HOLD** | proxies only; still reported |
| `genre_mood` | measured + **production-claim HOLD** | scene hypotheses; still reported |
| `tier_a_pipeline` | measured (9 Tier-A queries) | vector/filter/hybrid slice axis |
| Graded / NDCG families | **HOLD** | no graded labels |
| Vocal proxy spike suite | **HOLD / excluded** | not silently merged |

Machine-readable `support_counts` are emitted by `build_aq5_relevance_benchmark_manifest()`.

## Leakage / duplicate audit (reproducible)

`src/aq5_relevance_benchmark.py` fails closed unless:

1. ADR-0005 suite contract validation passes for included YAMLs  
2. Partition overlay covers every included query id exactly once  
3. No duplicate composite `query_key`  
4. No `relevant_sample_ids` ∩ `negative_sample_ids`  
5. No private absolute paths in suite fields  
6. No identical query `text` or `query_audio_fixture` spanning CALIBRATION and TEST  
7. All six Tier-B families have support ≥ 1 (HOLDs are status flags, not omissions)

Fingerprints: `partition_fingerprint`, `query_set_fingerprint` (SHA-256 over canonical JSON).

## Artifact policy

- Committed: suite YAMLs (already present), partition overlay, Python audit module, docs, tests  
- Runtime export: `write_aq5_relevance_benchmark_manifest(path, …)` writes JSON **outside** the repo root only  
- No committed WAVs, DBs, model caches, or private query text

## Automation seam (#1040 bootstrap)

Deterministic/headless consumers can call:

```text
src/aq5_relevance_benchmark.py
  BENCHMARK_ID / DOCUMENT_TYPE / BENCHMARK_VERSION
  build_aq5_relevance_benchmark_manifest(...)
  audit_aq5_relevance_benchmark(...) -> status + fingerprints + support_counts + HOLDs
  write_aq5_relevance_benchmark_manifest(output_path, ...)  # outside repo
```

Status token: `AQ5_RELEVANCE_BENCHMARK_FROZEN`. Portable join key: `query_key`. Domain tokens remain `aq5.retrieval` / `aq5.ranking` under the KPI contract. This slice does **not** build the orchestrator.

## Separation reminder

1. Relevance labels here are **not** ANN/backend promotion evidence.  
2. Operational latency stays on the sqlite-vec / #958 plane.  
3. Missing graded labels → NDCG HOLD, never fabricated grades.  
4. Unsupported / production-claim-weak families stay visible with HOLD — never dropped from support tables.

## Exit vocabulary

Exactly one:

- `AQ5_RELEVANCE_BENCHMARK_FROZEN` — named identity, auditable binary labels + hard negatives, partitions, leakage checks, family support counts, and explicit HOLDs frozen from ADR-0005 suites
- `AQ5_RELEVANCE_BENCHMARK_PARTIAL_HOLD` — core identity frozen but a required family/partition cannot be stated without silent exclusion
- `AQ5_RELEVANCE_BENCHMARK_INSUFFICIENT` — cannot freeze without private data or inventing labels

This slice exits `AQ5_RELEVANCE_BENCHMARK_FROZEN`.
