# Search Quality Benchmark Evidence

Measured Tier-A gate results for [ADR-0005](../adr/ADR-0005-search-quality-evaluation.md). This campaign measures **ranking relevance** (P@K, R@K), not sqlite-vec latency or backend parity.

## Run metadata

| Field | Value |
|-------|-------|
| Date | 2026-05-31 |
| Branch | `feat/search-quality-campaign` |
| Commit | `da8c3fe` (base `main` + campaign work) |
| OS | Windows 11 (10.0.26200) |
| Python | 3.12.10 (64-bit) |
| Suite | `tests/fixtures/search_quality/golden_v1.yaml` |
| Tier | A (deterministic 8-d vectors, NumPy backend) |
| Catalog size | 9 synthetic samples (3 clusters × 3) |
| Query count | 9 (vector, filter, hybrid) |
| Harness wall time | ~3 s (CLI + temp DB under `%TEMP%`) |

## Commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_search_quality.py -m "not clap"
.\.venv\Scripts\python.exe -m src.cli benchmark search-quality --work-dir $env:TEMP\sample-brain-quality
```

Work directory was outside the repo (`%TEMP%\sample-brain-quality`); no `.db` files were committed.

## Aggregate results (Tier A)

| Metric | Measured | Threshold | Verdict |
|--------|----------|-----------|---------|
| Mean P@1 | 1.000 | ≥ 0.60 | **PASS** |
| Mean P@5 | 0.600 | ≥ 0.50 | **PASS** |
| Mean R@10 | 1.000 | ≥ 0.80 | **PASS** |
| MRR | 1.000 | (informative) | — |
| Must-recall queries | 9/9 | all PASS | **PASS** |
| Filter compliance | 9/9 @ 1.000 | 100% | **PASS** |

Full harness stdout:

```
suite=...\golden_v1.yaml tier=A queries=9
mean_precision_at_1=1.000 mean_precision_at_5=0.600 mean_recall_at_10=1.000 mrr=1.000
gate_mean_precision_at_1=PASS
gate_mean_precision_at_5=PASS
gate_mean_recall_at_10=PASS
gate_must_recall_queries=PASS
gate_filter_compliance=PASS
query=kick_cluster p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=snare_cluster p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=pad_cluster p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=kick_pred_type_filter p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=kick_tag_filter p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=snare_bpm_range_filter p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=hybrid_bpm_promote_snare p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=hybrid_key_match_pad p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=scale_minor_filter p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
```

## Per-query-type coverage

| Query type | IDs in suite | Notes |
|------------|--------------|-------|
| Vector cluster | kick_cluster, snare_cluster, pad_cluster | Cosine ranking over orthogonal clusters |
| Metadata filter | kick_pred_type_filter, kick_tag_filter, snare_bpm_range_filter, scale_minor_filter | 100% filter compliance |
| Hybrid rerank | hybrid_bpm_promote_snare, hybrid_key_match_pad | BPM/key uplift vs semantic-only baseline |

## Tier B (optional, not CI-blocking)

- Suite stub: `tests/fixtures/search_quality/golden_v2_clap.yaml`
- Run locally with `pip install -e ".[clap]"` and `@pytest.mark.clap` tests
- Semantic relevance labels require CLAP embeddings + external DB; evidence not captured in this slice

## Regression gate (pytest)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Campaign adds `tests/test_search_quality.py` (Tier A metrics + frozen P@5 baseline) and `tests/conftest.py` (`clap` marker). Full suite: **149 passed** on measured host (138 baseline + 11 new).

## Decision

**Tier A regression gates PASS.** The harness proves filter compliance, hybrid reranking, and P@K/R@K aggregation on deterministic fixtures. Tier B CLAP semantic quality remains optional local evidence; default merge gate is Tier A only.

**Explicitly not measured here:** sqlite-vec latency, CLAP semantic accuracy on private samples, hybrid weight tuning.
