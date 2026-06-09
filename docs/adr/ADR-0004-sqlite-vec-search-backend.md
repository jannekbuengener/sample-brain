# ADR-0004: SQLite + sqlite-vec Search Backend

**Status:** Accepted  
**Date:** 2026-05-31  
**Supersedes:** [ADR-0002 (Local Vector Index Strategy)](../../knowledge/roadmap/adr/ADR-0002-local-vector-index-strategy.md) — für die lokale Vector-Index-Strategie (FAISS explizit No-Go)  
**Deciders:** (project owner)

---

## Kontext

EPIC 2 auf `main` liefert eine funktionierende semantische Such-Pipeline:

- Embeddings werden in SQLite persistiert (`sample_embeddings`, Schema gemäß [ADR-0003](../../knowledge/roadmap/adr/ADR-0003-embedding-db-schema-design.md)).
- Vector Search läuft über NumPy in-memory mit optionalem `.npz`-Cache ([`src/index.py`](../../src/index.py), [`src/search.py`](../../src/search.py)).
- M4 E2E-Smoke ist proven: Text-Query → CLAP-Embedding → NumPy-Index → ranked hits.

Anforderungen für die nächste Evolutionsstufe:

- Interaktive Suche bei wachsender Kataloggröße (Ziel: sub-second, siehe [EPIC 2 Spec](../EPIC_2_SEMANTIC_SEARCH_SPEC.md)).
- Local-first: keine Cloud-Index-Dienste, keine zweite Source of Truth.
- Eine SQLite-Datei als zentraler Katalog (Samples, Features, Embeddings).
- Rebuildbare Caches — Index-Verlust darf keine Datenverluste bedeuten.

[ADR-0002](../../knowledge/roadmap/adr/ADR-0002-local-vector-index-strategy.md) (Status: Proposed) benennt FAISS als primären Kandidaten. FAISS wurde nie implementiert; NumPy `.npz` ist der aktuelle Stand.

---

## Problemstellung

1. **Linear scan / externe Index-Dateien** — NumPy lädt alle Vektoren in den Speicher oder aus einer separaten `.npz`-Datei. Bei ~100k × 512-dim Vektoren wird interaktive Latenz und Artifact-Sync zum Engpass.
2. **FAISS-Dependency-Risiko** — Zusätzliche native Dependency, separates Index-Format (`.faiss` + Mapping-JSON), Plattform-Wheel-Story und Wartungsaufwand ohne bestehende Implementierung im Repo.
3. **Keine zweite SoT** — LanceDB, SurrealDB, PostgreSQL/pgvector oder andere dedizierte DBs würden Sync, Backup und Agent-Bootstrap verkomplizieren.
4. **Cache-Drift** — Jeder rebuildbare Index muss `model_id` und `source_hash`-Staleness respektieren; sonst liefert die Suche veraltete Treffer.

---

## Entscheidung

**SQLite bleibt Source of Truth. [sqlite-vec](https://github.com/asg017/sqlite-vec) (`vec0`) wird als rebuildbarer Vector-Search-Cache in derselben DB-Datei evaluiert und eingeführt. NumPy `.npz` bleibt Fallback und Benchmark-Referenz bis die Benchmark-Gates (Phase 6–7) bestanden sind.**

### Architektur (ASCII)

```text
                    ┌──────────────────────────────────────┐
                    │  SQLite catalog (Source of Truth)     │
                    │  samples · features · embedding_models│
                    │  sample_embeddings (BLOB + keys)      │
                    └──────────────────┬───────────────────┘
                                       │
              embed / re-embed         │  rebuild (idempotent)
                                       ▼
                    ┌──────────────────────────────────────┐
                    │  sqlite-vec vec0 cache (rebuildable)  │
                    │  keyed by model_id + source_hash state  │
                    └──────────────────┬───────────────────┘
                                       │
                         search adapter (config gate)
                                       │
              ┌────────────────────────┴────────────────────────┐
              ▼                                                  ▼
     query → backend.embed_*()                          fallback / benchmark
              → vec search                                         NumPy .npz
              → enrich from SQLite (paths, features, hybrid)
```

### Abgelehnte Alternativen

| Kandidat | Grund der Ablehnung |
|----------|---------------------|
| **FAISS** | Superseded durch diese Entscheidung; native Dependency, separates Artifact-Format, nie implementiert |
| **LanceDB** | Zweite Storage-Schicht; widerspricht Single-DB-Katalog |
| **SurrealDB** | Externe DB-Runtime; Overkill für Single-User-CLI |
| **PostgreSQL / pgvector** | Server-Dependency; verletzt local-first |
| **Chroma / Qdrant (embedded)** | Zusätzliche Runtime; keine Join-Kompatibilität mit bestehendem SQLite-Schema |
| **Weitere DB-Kandidaten** | Explizit out of scope — keine parallele Evaluierung |

---

## Komponenten-Rollen

### `sample_embeddings` (Source of Truth)

- Einzige persistente Vektor-SoT in [`src/db.py`](../../src/db.py).
- Spalten: `sample_id`, `model_id`, `embedding` (BLOB float32), `embedding_format`, `source_hash`, `created_at`.
- UNIQUE `(sample_id, model_id, source_hash)` — verhindert Duplikate; alte Hashes bleiben traceable bei Content-Änderung.
- `load_embeddings_for_model()` in [`src/index.py`](../../src/index.py) liest daraus für Index-Build und Search.

### `model_id`

- FK auf `embedding_models.id`; definiert Provider, Name, Version, `embedding_dim`, Modality.
- Cache (`vec0`) und NumPy `.npz` sind pro `model_id` scoped.
- Dimension- und Metric-Validierung beim Rebuild und bei Search muss `model_id`-Konsistenz erzwingen.

### `source_hash`

- SHA-1 des Sample-Contents zum Embed-Zeitpunkt; muss `samples.hash` matchen.
- `iter_pending_samples()` in [`src/db.py`](../../src/db.py) nutzt Hash-Vergleich für Staleness — fehlende oder veraltete Embeddings werden neu berechnet.
- vec0-Cache-Einträge müssen an `(sample_id, model_id, source_hash)` gebunden sein; Hash-Drift invalidiert Cache-Zeilen oder erzwingt Rebuild.

### NumPy `.npz` (Fallback + Benchmark-Referenz)

- Aktuelle Implementierung: [`save_numpy_index()`](../../src/index.py), [`load_numpy_index()`](../../src/index.py), `default_index_path()`.
- Metadata: `format_version`, `backend: numpy`, `model_id`, `embedding_dim`, `metric: cosine`, `normalized`, `sample_count`, `created_at`.
- Rolle bis Phase 7: Default-Search-Backend, Offline-Vergleich, Korrektheits-Referenz für sqlite-vec Benchmark-Gates.
- Artifact-Hygiene: `data/indexes/` bleibt gitignored (siehe [DATA_AND_ARTIFACT_POLICY.md](../DATA_AND_ARTIFACT_POLICY.md)).

### sqlite-vec `vec0` (Rebuildable Cache)

- ANN/flat Vector-Tabelle via sqlite-vec Extension in derselben SQLite-Datei (oder dokumentiertes Attachment-Pattern in der Roadmap).
- Jederzeit droppable/rebuildable aus `sample_embeddings` — kein Datenverlust bei Cache-Löschung.
- Kein Ersatz für BLOB-SoT; nur beschleunigte Query-Schicht.
- State-Tracking (Rebuild-Zeitpunkt, Sample-Count, Staleness) über geplante Metadaten-Tabellen — siehe [SQLITE_VEC_ROADMAP.md](../SQLITE_VEC_ROADMAP.md) Phase 2.

---

## Vorteile

- **Transaktionaler Rebuild** — Cache und Katalog in einer DB-Datei; kein separates `.faiss`/`.npz`-Sync.
- **SQL-Joins** — Direkte Joins mit `samples`, `features` und künftigen Tag-Tabellen für Hybrid-Search.
- **Weniger Artifacts** — Optional weniger externe Index-Dateien; `SAMPLE_BRAIN_DB_PATH` bleibt zentraler Runtime-Pfad.
- **Agent-freundlicher Pfad** — Klare Phasen-Roadmap; NumPy als Referenz reduziert Korrektheits-Risiko.
- **Local-first** — Keine Server-, Cloud- oder zweite DB-Runtime.

---

## Risiken

| Risiko | Mitigation |
|--------|------------|
| Extension-Load (Windows/Linux) | Phase 1: Availability smoke + Diagnostics vor Schema-Änderungen |
| Native/WASM wheel story | Guarded import; klare Fehlermeldung; Fallback auf NumPy |
| Fixed dimension per model | Validierung bei Rebuild; `embedding_dim` aus `embedding_models` |
| Cache drift ohne Rebuild | `source_hash`-Binding; Metadaten-Tabellen; Staleness-Gate in Benchmarks |
| DB-Größe bei ~100k × 512d | Benchmark-Gate Rebuild-Zeit und Dateigröße; Rollback zu NumPy-only |
| Zusätzliche Runtime-Dependency | Reproduzierbarer Bootstrap-Pfad dokumentieren; No-Go bei fehlendem Wheel |

---

## No-Go-Kriterien

Stop oder Rollback zur NumPy-only-Search, wenn:

1. sqlite-vec lässt sich auf Zielplattformen (Windows + Linux Agent-Smoke) nicht zuverlässig laden.
2. Top-k-Ergebnisse weichen systematisch von der NumPy-Referenz ab (Korrektheits-Gate nicht bestanden).
3. Rebuild-Zeit oder DB-Größe sprengen dokumentierte Budgets bei Referenz-Kataloggröße (~100k × 512d, EPIC-2-Spec).
4. Zusätzliche Runtime-Dependency ohne reproduzierbaren Bootstrap-Pfad in README/AGENTS.

---

## Benchmark-Gates

Schwellwerte gemessen 2026-05-31 auf Windows 11 / Python 3.12.10 — Details: [SQLITE_VEC_GATE_EVIDENCE.md](../benchmarks/SQLITE_VEC_GATE_EVIDENCE.md).

| Gate | Kriterium | Schwellwert | Gemessen | Verdict |
|------|-----------|-------------|----------|---------|
| **Correctness** | Top-k overlap vs NumPy (flat/cosine, gleiche `model_id`) | ≥ 95 % overlap @ k=10 | 100 % @ N∈{1k, 10k, 100k} | **PASS** |
| **Latency (warm)** | p95 Query-Zeit @ N≥100k | ≤ 200 ms | 3,568.61 ms | **FAIL** |
| **Latency (filtered)** | p95 Query-Zeit @ N≥100k | ≤ 250 ms | 3,440.95 ms | **FAIL** |
| **Rebuild** | Vollständiger vec0-Rebuild aus `sample_embeddings` @ 100k | budget TBD (EPIC-2) | 20,297 ms (~20 s) | dokumentiert |
| **Staleness** | Nach `source_hash`-Änderung | Betroffene Vektoren entfernt / Rebuild erzwungen | Harness nicht in diesem Lauf | offen (separater Test) |

Referenz-EPIC: [EPIC_2_SEMANTIC_SEARCH_SPEC.md](../EPIC_2_SEMANTIC_SEARCH_SPEC.md) — „Sub-second approximate nearest-neighbor search over up to ~100k samples“ (ursprünglich ADR-0002-Anforderung, hier via sqlite-vec verfolgt).

**Entscheidung:** Default `search.backend` bleibt **`numpy`** bis alle Latenz-Gates PASS.

---

## Nicht-Ziele

- Keine LanceDB, SurrealDB, PostgreSQL oder weitere DB-Kandidaten
- Kein FAISS-Adapter (M6 aus CURRENT_STATUS ist obsolet für Index-Strategie)
- Kein Cloud-Index oder Multi-User-Sync
- Kein Model-Training oder Fine-Tuning
- Keine Implementierung, Schema-Migration oder Dependency-Änderung in diesem ADR
- Keine Benchmark-Ausführung in diesem docs-only PR

---

## Konsequenzen / Follow-up

1. **Roadmap** — Agent-gesteuerte Umsetzung in Phasen 1–8: [SQLITE_VEC_ROADMAP.md](../SQLITE_VEC_ROADMAP.md).
2. **Erster Code-Slice** — Phase 1 (Issue #2): sqlite-vec Availability smoke + Diagnostics.
3. **Docs-Sync (Phase 8)** — EPIC-2-Spec, TARGET_ARCHITECTURE, DATA_AND_ARTIFACT_POLICY schrittweise auf sqlite-vec anpassen; FAISS-Spuren in Docs deprecaten (ADR-0002-Datei unverändert lassen).
4. **Config-Gate (Phase 7)** — Default bleibt `numpy` bis Benchmark-Gates PASS.
5. **ADR-0003 „Future Tables“** — `vector_indexes` aus ADR-0003 wird durch `vector_index_state` / Cache-Metadaten in Phase 2 konkretisiert (Roadmap, nicht Code).

---

---

## Amendment 2026-06-09: Staged Latency Gates

Die ursprünglichen Benchmark-Gates (warm p95 ≤ 200ms, filtered p95 ≤ 250ms bei N≥100k) sind für den aktuellen brute-force-vec0-Pfad (v0.1.9) nicht erreichbar. Gemessene Werte: warm p95 ≈ 3568ms, filtered p95 ≈ 3440ms bei 100k.

Der Gate-Modell wird daher in fünf realistischen Stages abgebildet, die von der aktuellen Brute-Force-Implementierung über Quantisierungs- und Partitionierungs-Optimierungen bis zu ANN führen:

| Stage | Strategie | Overlap@k10 | Latency p95@100k (Ziel) | Status |
|-------|-----------|-------------|-------------------------|--------|
| 1 | Brute-force (vec0, aktuell) | ≥ 0.95 | ≤ 5000ms (dokumentiert, kein Gate) | **Aktuell** |
| 2 | int8 Quantisierung | ≥ 0.95 | ≤ 1000ms | Zu benchmarken |
| 3 | Binary Quantisierung | ≥ 0.85 | ≤ 250ms | Zu benchmarken |
| 4 | Partition Key | ≥ 0.95 | ≤ 500ms | Zu benchmarken |
| 5 | ANN (wenn sqlite-vec stabil) | ≥ 0.95 | ≤ 200ms | Future |

**Regeln:**
- NumPy bleibt Default-Backend, bis alle Latenz-Gates einer gewählten Stage PASS sind.
- Jede Stage wird unabhängig gebenchmarkt und dokumentiert (Evidence in `docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md`).
- Der Overlap@k10 muss gegen die NumPy-Referenz gemessen werden.
- Eine Stage gilt erst als bestanden, wenn alle ihre Gates in einer reproduzierbaren Benchmark-Umgebung PASS sind.
- Der Wechsel zu einer neuen Stage erfordert ein explizites GO (Issue/PR).

---

## Referenzen

| Referenz | Pfad |
|----------|------|
| DB-Schema & Embedding-Persistence | [`src/db.py`](../../src/db.py) |
| NumPy Index Build/Search/Persistence | [`src/index.py`](../../src/index.py) |
| Search Flow & Hybrid Rerank | [`src/search.py`](../../src/search.py) |
| Embedding DB Schema ADR | [ADR-0003](../../knowledge/roadmap/adr/ADR-0003-embedding-db-schema-design.md) |
| Superseded FAISS ADR (unverändert) | [ADR-0002](../../knowledge/roadmap/adr/ADR-0002-local-vector-index-strategy.md) |
| EPIC 2 Semantic Search Spec | [EPIC_2_SEMANTIC_SEARCH_SPEC.md](../EPIC_2_SEMANTIC_SEARCH_SPEC.md) |
| Umsetzungs-Roadmap | [SQLITE_VEC_ROADMAP.md](../SQLITE_VEC_ROADMAP.md) |
| Status-Ledger | [CURRENT_STATUS.md](../../knowledge/CURRENT_STATUS.md) |
