# ADR-0005: Search Quality Evaluation

**Status:** Accepted  
**Date:** 2026-05-31  
**Related:** [EPIC 2 Spec](../EPIC_2_SEMANTIC_SEARCH_SPEC.md) §M5, [ADR-0004](ADR-0004-sqlite-vec-search-backend.md) (backend gates, out of scope here)

---

## Kontext

EPIC 2 liefert auf `main` eine vollständige Search-Pipeline:

- Text- und Audio-Queries über CLAP (optional) + NumPy/sqlite-vec Vector Search
- Tag- und Metadaten-Pre-Filter (`SearchFilters`)
- Hybrid-Reranking (BPM, Key, pred_type)

Bestehende Validierung beweist **Infrastruktur**, nicht **Relevanz**:

| Artefakt | Misst |
|----------|--------|
| `benchmark vec` | Overlap @ k=10, Latenz p95 (Backend-Parität) |
| Unit-Tests | Wiring, Fehlerpfade, deterministischer Rerank |
| M4 Smoke | Ein Query, ein Treffer |

Es fehlt eine reproduzierbare Messung von Precision@K, Recall@K und Ranking-Regression über Query-Typen hinweg.

---

## Entscheidung

**Search-Qualität wird über ein versioniertes Golden Dataset, eine Query-Suite und einen Evaluation-Harness gemessen — ohne DB-Schema-Änderungen, ohne sqlite-vec-Optimierung, ohne Architektur-Umbau.**

### Zwei-Tier-Strategie

| Tier | Zweck | CI | Embedding |
|------|-------|-----|-----------|
| **A** | Pipeline-Regression (Ranking, Filter, Hybrid, Metriken) | Ja (`pytest`, kein CLAP) | Deterministische Vektoren in temp-DB |
| **B** | Semantische Relevanz (CLAP) | Optional lokal (`@pytest.mark.clap`) | `[clap]` + external DB |

### Metriken

- **Precision@K** = \|Top-K ∩ Relevant\| / K  
- **Recall@K** = \|Top-K ∩ Relevant\| / \|Relevant\| (nur wenn \|Relevant\| > 0)  
- **MRR** (optional, dokumentiert): Mean Reciprocal Rank der ersten relevanten ID  
- Aggregation: Mean über Queries; **pro Modus** (text, audio, tag, filter, hybrid) reporten  
- **K-Werte:** 1, 5, 10 (Default K=10)

### Golden-Dataset-Schema (YAML)

```yaml
version: 1
tier: A
embedding_dim: 8
defaults:
  topk: 10
  model_id: 1
thresholds:
  mean_precision_at_1: 0.60
  mean_precision_at_5: 0.50
  mean_recall_at_10: 0.80
catalog:
  samples: [...]
queries:
  - id: kick_cluster
    mode: vector
    query_vector: [1.0, 0.0, ...]
    relevant_sample_ids: [1, 2]
    filters: {}
    hybrid: {}
```

Query-Felder:

| Feld | Beschreibung |
|------|--------------|
| `id` | Stabile Query-ID |
| `mode` | `vector` (Tier A), `text`, `audio` (Tier B) |
| `query_vector` | Direkter Query-Vektor (Tier A) |
| `text` / `query_audio` | Tier B |
| `relevant_sample_ids` | Ground-truth Menge |
| `must_recall_within_k` | Optional; FN-Cap |
| `filters` | `SearchFilters`-Felder |
| `hybrid` | `HybridQuery`-Felder |

### Harness

- Modul: [`src/benchmark_search_quality.py`](../../src/benchmark_search_quality.py)  
- CLI: `sample-brain benchmark search-quality --suite <path> [--work-dir …]`  
- API: [`src/search_eval.py`](../../src/search_eval.py) — reine Metrik-Funktionen  
- Collector: [`collect_search_hits()`](../../src/search.py) — gleiche Pipeline wie `run_search()`, strukturierte Rückgabe  

### Schwellw (Tier A, blockierend für Regression)

| Metrik | Schwelle |
|--------|----------|
| Mean P@1 | ≥ 0.60 |
| Mean P@5 | ≥ 0.50 |
| Mean R@10 (|rel| ≤ 10) | ≥ 0.80 |
| Filter compliance | 100% |
| Regression delta P@5 | ≤ 0.02 vs frozen baseline |

Tier B Schwellw sind informativ bis kuratiertes CLAP-Set existiert.

---

## Non-Goals

- Keine neue SQLite-Tabelle oder Schema-Migration
- Keine sqlite-vec Latenz-Optimierung
- Kein Default-Backend-Switch
- Kein Hybrid-Algorithmus-Tuning in der Campaign (nur messen)
- Keine privaten Sample-Libraries im Repo

---

## Konsequenzen

- Evidence-Report: [`docs/benchmarks/SEARCH_QUALITY_EVIDENCE.md`](../benchmarks/SEARCH_QUALITY_EVIDENCE.md)  
- Fixtures: [`tests/fixtures/search_quality/golden_v1.yaml`](../../tests/fixtures/search_quality/golden_v1.yaml)  
- Regression: [`tests/test_search_quality.py`](../../tests/test_search_quality.py)  
- EPIC 2 M5: Tier A ✅ nach Harness-Merge; Tier B 🔶 optional  

---

## Referenzen

- [`docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md`](../benchmarks/SQLITE_VEC_GATE_EVIDENCE.md) — Backend-Gates (separates Concern)
- [`src/search.py`](../../src/search.py), [`src/hybrid_rank.py`](../../src/hybrid_rank.py), [`src/search_filters.py`](../../src/search_filters.py)

---

## Appendix: Tier-B Golden Query Contract (Issue #214)

Tier B uses [`tests/fixtures/search_quality/golden_v2_clap.yaml`](../../tests/fixtures/search_quality/golden_v2_clap.yaml) with machine validation in [`src/search_quality_contract.py`](../../src/search_quality_contract.py). `load_search_quality_suite()` rejects invalid suites before benchmark runs.

### Runtime reproducibility (Issue #218)

The optional CLAP Tier-B runtime path is documented and tested separately from
quality evidence: [SEARCH_QUALITY_EVIDENCE.md](../benchmarks/SEARCH_QUALITY_EVIDENCE.md).
The model identity (`laion/clap-htsat-unfused`, 512-d, `audio_text`) is
centralized as constants in `src/embed.py` and shared by `model_info()`, the
model loader, the benchmark harness, and the runtime tests. A clean machine must
install the base `requirements.txt` **and** the `[clap]` extra — `pip install -e
".[clap]"` alone does not install the base runtime (`pyproject.toml` declares
`dependencies = []`). The `@pytest.mark.clap` path skips cleanly without `[clap]`
or when the model is offline and uncached; only a genuine model/processor load
failure is treated as runtime-unavailable. Quality interpretation stays in
#216 / #217 / #219.

### Tier A vs Tier B

| Aspect | Tier A | Tier B |
|--------|--------|--------|
| Purpose | Pipeline regression (ranking, filters, hybrid) | Semantic relevance (CLAP) |
| Query modes | `vector` | `text`, `audio` |
| Embeddings | Deterministic vectors in YAML | CLAP at benchmark time |
| CI | Blocking (`pytest`, no CLAP) | Optional local (`@pytest.mark.clap`) |

### Query modes (Tier B)

- **Text-to-sample (`mode: text`)** — requires non-empty `text`; must not set `query_audio` or `query_audio_fixture`.
- **Audio-to-audio (`mode: audio`)** — requires `query_audio_fixture` referencing a catalog `fixture_name`; must not set `text` or private `query_audio` paths.

### Canonical query classes

Stable enum: `kick_snare_perc`, `pad_texture`, `riser_impact`, `dry_wet`, `vocal_no_vocal`, `genre_mood`.

On `main` (Phase 1+2, PRs #110/#111; Phase 3 #215): **6/6 present** — all canonical query classes including `vocal_no_vocal` and `genre_mood` with safe synthetic fixtures.

### Relevance and hard negatives

| Field | Semantics |
|-------|-----------|
| `relevant_sample_ids` | Expected positive hits (required, non-empty for evaluatable queries) |
| `negative_sample_ids` | Hard negatives — must not appear in top-K; optional but must not overlap relevant |
| `must_recall_within_k` | Optional recall gate within K (default reporting K=10) |

### Portable fixture references

Catalog samples use `fixture_name` + `fixture_type` (runtime WAV generation). Audio queries reference `query_audio_fixture: <fixture_name>`. Private absolute paths (`C:\…`, `/Users/…`, `/home/…`) are rejected.

### Failure buckets (reporting)

Assigned by [`src/search_eval.py`](../../src/search_eval.py): `success`, `negative_leak_top5`, `zero_precision_at_5`, `zero_mrr`, `must_recall_fail`, `error`. Aggregated per query class and mode in the benchmark harness.

### Informative Tier-B thresholds

Documented in suite `thresholds:` (not CI-blocking): mean P@5, mean R@10. Final Tier-B evidence is published in SEARCH_QUALITY_EVIDENCE.md; #216/#217 measured the two modes and #219 consolidated the campaign.

### Child issues using this contract

- **#215** — safe audio fixtures for `vocal_no_vocal`, `genre_mood`
- **#216** — text-to-sample evaluation
- **#217** — audio-to-audio evaluation
- **#218** — reproducible optional CLAP runtime
- **#219** — evidence publication

Vocal proxy spike (`golden_v2_clap_vocal_proxy_spike.yaml`) remains **HOLD** — not Tier-B production evidence.
