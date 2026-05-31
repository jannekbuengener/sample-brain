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
