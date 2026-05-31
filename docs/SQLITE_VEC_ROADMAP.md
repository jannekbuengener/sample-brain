# SQLite + sqlite-vec Roadmap

Agent-taugliche Umsetzungs-Roadmap für die Architektur aus [ADR-0004](adr/ADR-0004-sqlite-vec-search-backend.md).

---

## Agent-Arbeitsanweisung

1. **Reihenfolge:** Phasen **1 → 8** strikt einhalten. Phase **0** ist dieser docs-only PR — kein Code ohne explizites GO.
2. **Validierung pro Phase:** `pytest -q` + CLI smoke (`python -m src.cli --help` und betroffene Subcommands).
3. **Externe DB:** Runtime-Tests mit `SAMPLE_BRAIN_DB_PATH` außerhalb des Repos — `git status` muss clean bleiben.
4. **Scope:** Minimaler Diff; keine Drive-by-Refactors.
5. **CI/Workflows:** Keine `.github/workflows/`-Änderungen ohne separaten Auftrag (Projektregel).
6. **Fallback:** Bei No-Go aus ADR-0004 → NumPy-only beibehalten; sqlite-vec hinter Config-Gate (Phase 7).
7. **Referenz:** Korrektheits-Vergleich immer gegen NumPy-Referenz (`src/index.py`).

---

## Phase 0 — Architektur-Freeze (docs-only)

| Feld | Inhalt |
|------|--------|
| **Ziel** | Architekturentscheidung dokumentieren; agent-ausführbaren Backlog bereitstellen |
| **Scope** | Nur Markdown — ADR-0004, diese Roadmap, minimaler CURRENT_STATUS-Patch |
| **Betroffene Dateien** | `docs/adr/ADR-0004-sqlite-vec-search-backend.md`, `docs/SQLITE_VEC_ROADMAP.md`, `knowledge/CURRENT_STATUS.md` |
| **Deliverables** | Accepted ADR; Phasen 0–8; Future Issues; Status-Links |
| **Erfolgsbedingungen** | `git diff` enthält nur die drei Doc-Pfade; ADR-0002-Datei unverändert; Supersession nur in ADR-0004 |
| **Risiken** | Doc-Drift vs `main`-Code — Phase 8 adressiert Sync |

---

## Phase 1 — Availability Smoke + Diagnostics

**Status:** ✅ Done (PR #47)

| Feld | Inhalt |
|------|--------|
| **Ziel** | Prüfen, ob sqlite-vec auf Zielplattformen (Windows, Linux) ladbar ist; klare Diagnose bei Fehlschlag |
| **Scope** | Guarded Extension-Load; optional CLI-Diagnostic (z. B. `init`-Hook oder dedizierter Subcommand); keine Schema-Änderung |
| **Betroffene Dateien** | Neu: `src/vec_availability.py`; `src/cli.py`; `tests/test_vec_availability.py` |
| **Deliverables** | `is_sqlite_vec_available()` o. ä.; strukturierte Fehlermeldung (Plattform, Wheel, Version); Unit-Tests ohne Extension-Pflicht |
| **Erfolgsbedingungen** | `pytest -q` PASS; Diagnostic unterscheidet „nicht installiert“ vs „Load-Fehler“; Core-CLI ohne sqlite-vec weiterhin PASS |
| **Risiken** | Native Wheel fehlt auf Windows; WASM-Fallback unklar — dokumentieren, No-Go triggern wenn nötig |

**Future Issue:** #2 — `feat: add sqlite-vec availability smoke and diagnostics`

---

## Phase 2 — Schema: Vector Search State + Tags

**Status:** ✅ Done (PR #48)

| Feld | Inhalt |
|------|--------|
| **Ziel** | Metadaten für vec0-Cache-Lifecycle und Tag-Vorbereitung in SQLite |
| **Scope** | `CREATE TABLE IF NOT EXISTS` in `init_db()`; keine vec0-Daten yet |
| **Betroffene Dateien** | `src/db.py`; `tests/test_db_embeddings.py`; ggf. `tests/test_db_vec_schema.py` |
| **Deliverables** | Tabellen-Skizze (Namen fix in Roadmap, Implementierung in Code) — siehe unten |
| **Erfolgsbedingungen** | Tabellen idempotent via `init_db()`; Tests für Constraints; bestehende Embedding-Tests unverändert PASS |
| **Risiken** | Migration bei bestehenden externen DBs; Abstimmung mit ADR-0003 „Future Tables“ |

**Geplante Tabellen (Namen):**

```sql
-- Cache-Rebuild-Metadaten pro model_id
vector_index_state (
  id INTEGER PRIMARY KEY,
  model_id INTEGER NOT NULL REFERENCES embedding_models(id),
  backend TEXT NOT NULL,           -- 'sqlite-vec' | 'numpy'
  vec_table_name TEXT,             -- z. B. vec0 virtual table name
  embedding_dim INTEGER NOT NULL,
  sample_count INTEGER NOT NULL,
  last_rebuild_at TEXT,
  source_fingerprint TEXT,         -- Hash über (sample_id, source_hash) Set
  UNIQUE(model_id, backend)
)

-- Optionale Tag-Vorbereitung (Phase 5 entscheidet Quelle)
-- sample_tags (sample_id, tag, source) — siehe Phase 5
```

**Future Issue:** #3 — `feat: add SQLite schema support for vector search state and tags`

---

## Phase 3 — vec0 Cache Rebuild from `sample_embeddings`

**Status:** ✅ Done (PR #49)

| Feld | Inhalt |
|------|--------|
| **Ziel** | Idempotenter Rebuild der sqlite-vec vec0-Tabelle aus `sample_embeddings` |
| **Scope** | Rebuild-Logik; CLI-Erweiterung `index_build`; State in `vector_index_state` |
| **Betroffene Dateien** | `src/index.py` oder neu `src/vec_index.py`; `src/db.py` (Helpers); `src/cli.py`; Tests |
| **Deliverables** | `rebuild_vec0_cache(model_id)`; Staleness via `source_hash`; Update `vector_index_state` |
| **Erfolgsbedingungen** | Rebuild aus externer DB; Drop+Rebuild idempotent; `sample_count` stimmt; Phase-1-Availability-Gate PASS |
| **Risiken** | Rebuild-Dauer bei großem N; vec0-Dimension muss `embedding_dim` matchen |

**Future Issue:** #4 — `feat: add sqlite-vec current embedding cache rebuild`

**Abhängigkeit:** Phase 1, Phase 2

---

## Phase 4 — Search Backend Adapter (`numpy` | `sqlite-vec`)

**Status:** ✅ Done (PR #50)

| Feld | Inhalt |
|------|--------|
| **Ziel** | Einheitliche Search-Schnittstelle; Backend-Wahl zur Laufzeit |
| **Scope** | Adapter-Pattern; `run_search()` delegiert; NumPy-Pfad unverändert als Default |
| **Betroffene Dateien** | Neu: `src/search_backend.py`; `src/search.py`; `src/index.py`; Tests |
| **Deliverables** | `SearchBackend` Protocol/ABC; `NumpySearchBackend`, `SqliteVecSearchBackend`; gleiches `SearchHit`-Format |
| **Erfolgsbedingungen** | Beide Backends liefern ranked hits; NumPy bleibt Default; `pytest -q` PASS |
| **Risiken** | Score-Semantik (cosine vs inner product) muss dokumentiert und konsistent sein |

**Future Issue:** #5 — `feat: add search backend adapter for numpy and sqlite-vec`

**Abhängigkeit:** Phase 3

---

## Phase 5 — Tags + FTS5 MVP (SQLite-only)

| Feld | Inhalt |
|------|--------|
| **Ziel** | Tag-aware Search MVP rein in SQLite (ohne externe Index-Dienste) |
| **Scope** | Tag-Quelle festlegen; FTS5-Virtual-Table; CLI-Flags für Tag-Filter |
| **Betroffene Dateien** | `src/db.py`; `src/search.py` oder neues Tag-Query-Modul; `src/cli.py`; Tests |

**Design-Entscheidung — FTS5 Tag-Quelle (in Phase 5 zu treffen):**

| Option | Quelle | Pro | Contra |
|--------|--------|-----|--------|
| A | `features.pred_type` + strukturierte Feature-Felder | Bereits vorhanden | Begrenztes Vokabular |
| B | FL-Export-Tags (`export_fl`) | Producer-facing Labels | Nicht immer befüllt |
| C | Neue `sample_tags`-Tabelle | Flexibel, normalisiert | Mehr Schema + Ingest |

**Empfehlung Roadmap:** Option C skizzieren, MVP mit A starten wenn Export-Tags fehlen — Entscheid in Phase-5-PR dokumentieren.

| **Deliverables** | FTS5-Index über gewählte Tag-Quelle; kombinierbar mit Vector-Hits (Pre-Filter oder Post-Filter) |
| **Erfolgsbedingungen** | Tag-Query + Vector-Search smoke; keine Regression Hybrid-Rerank |
| **Risiken** | FTS5 Tokenizer für Producer-Tags; Duplikat-Tags aus mehreren Quellen |

**Future Issue:** #6 — `feat: add tag-aware search MVP inside SQLite`

**Abhängigkeit:** Phase 4

---

## Phase 6 — Benchmark Harness

**Status:** ✅ Done (PR #51) — measured gates: [SQLITE_VEC_GATE_EVIDENCE.md](benchmarks/SQLITE_VEC_GATE_EVIDENCE.md)

| Feld | Inhalt |
|------|--------|
| **Ziel** | Messbare Gates aus ADR-0004; Schwellwerte von TBD → konkrete Zahlen |
| **Scope** | Harness-Skript oder `tests/benchmarks/`; synthetische Fixtures; kein CI-Gate ohne separaten Auftrag |
| **Betroffene Dateien** | `tests/benchmarks/test_vec_search_benchmark.py` oder `scripts/bench_vec_search.py`; Docs-Update ADR-0004 TBD-Felder |
| **Deliverables** | Correctness (top-k overlap); Latency p95 @ N; Rebuild-Zeit; Staleness-Test |
| **Erfolgsbedingungen** | Harness reproduzierbar lokal; Ergebnisse dokumentiert; EPIC-2 sub-second als Referenz |
| **Risiken** | CI-Zeit; Hardware-Varianz — Benchmarks optional/lokal |

**Future Issue:** #7 — `test: add sqlite-vec benchmark harness`

**Abhängigkeit:** Phase 4 (mindestens); Phase 5 optional für Tag-Benchmarks

---

## Phase 7 — Default Switch Behind Config Gate

**Status:** ✅ Done (PR #50) — default remains `numpy` until latency gates PASS (see Phase 6 evidence)

| Feld | Inhalt |
|------|--------|
| **Ziel** | `sqlite-vec` als wählbares Backend via Config/CLI — **Default bleibt `numpy` bis Gates PASS** |
| **Scope** | Profile-Key z. B. `search.backend`; CLI `--search-backend`; Gates aus Phase 6 müssen PASS |
| **Betroffene Dateien** | `src/config_loader.py`; `config/profiles.example.yaml`; `src/cli.py`; Tests |
| **Deliverables** | Config-Precedence dokumentiert; Warnung wenn sqlite-vec gewählt aber unavailable |
| **Erfolgsbedingungen** | Default `numpy`; opt-in `sqlite-vec` nur nach dokumentiertem Gate-PASS; `pytest -q` PASS |
| **Risiken** | User erwartet sqlite-vec als Default — Docs müssen Fallback klar kommunizieren |

**Future Issue:** #8 — `feat: switch sqlite-vec search backend behind config gate`

**Abhängigkeit:** Phase 6 (Gates PASS)

---

## Phase 8 — Cleanup / Hardening

**Status:** ✅ Done (closeout PR) — README, EPIC_2, AGENTS, CURRENT_STATUS, artifact/architecture sync

| Feld | Inhalt |
|------|--------|
| **Ziel** | Docs-Sync; FAISS-Spuren in Docs schrittweise deprecaten; README/AGENTS Bootstrap für sqlite-vec |
| **Scope** | Docs-only + kleine Hygiene; **nicht** ADR-0002-Datei ändern |
| **Betroffene Dateien** | `docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md`; `docs/TARGET_ARCHITECTURE.md`; `docs/DATA_AND_ARTIFACT_POLICY.md`; `knowledge/CURRENT_STATUS.md`; `README.md` / `AGENTS.md` (Bootstrap-Hinweis) |
| **Deliverables** | EPIC-2-Spec: sqlite-vec als Ziel-Index, FAISS als deprecated; Artifact-Policy: vec0 in DB |
| **Erfolgsbedingungen** | Keine Docs behaupten FAISS als „primary candidate“ ohne ADR-0004-Verweis; CURRENT_STATUS aktuell |
| **Risiken** | Widerspruch mit unverändertem ADR-0002 — immer ADR-0004 als gültige Strategie zitieren |

**Abhängigkeit:** Phase 7 (oder parallel wenn nur Docs)

---

## Future Issues

Mapping der GitHub-Issues (noch anzulegen) auf Phasen, Abhängigkeiten und Definition of Done.

| # | Issue-Titel | Phase | Abhängigkeiten | Definition of Done |
|---|-------------|-------|----------------|-------------------|
| 1 | docs: add SQLite + sqlite-vec search backend ADR | 0 | — | ADR-0004 Accepted; Roadmap; CURRENT_STATUS-Patch; docs-only diff |
| 2 | feat: add sqlite-vec availability smoke and diagnostics | 1 | Issue #1 (Architektur) | Phase-1 Erfolgsbedingungen; `pytest -q` PASS |
| 3 | feat: add SQLite schema support for vector search state and tags | 2 | Issue #2 | `vector_index_state` (+ Tag-Skizze); idempotent `init_db()`; Tests PASS |
| 4 | feat: add sqlite-vec current embedding cache rebuild | 3 | #2, #3 | Rebuild aus `sample_embeddings`; State-Update; idempotent |
| 5 | feat: add search backend adapter for numpy and sqlite-vec | 4 | #4 | Beide Backends; gleiches Hit-Format; NumPy default |
| 6 | feat: add tag-aware search MVP inside SQLite | 5 | #5 | FTS5 MVP; Tag-Quellen-Entscheid dokumentiert |
| 7 | test: add sqlite-vec benchmark harness | 6 | #5 | ADR-Gates messbar; TBD-Schwellwerte ersetzt oder bewusst offen |
| 8 | feat: switch sqlite-vec search backend behind config gate | 7 | #6 (Gates PASS) | Config/CLI opt-in; Default `numpy` bis Gates PASS |

### Abhängigkeitsgraph (kurz)

```text
#1 (docs) → #2 → #3 → #4 → #5 → #6 → #7 → #8
                              └→ #6 (parallel möglich ab #5)
Phase 8 (docs cleanup) nach #7 oder parallel ab #4
```

---

## Referenzen

- [ADR-0004: SQLite + sqlite-vec Search Backend](adr/ADR-0004-sqlite-vec-search-backend.md)
- [EPIC 2 Semantic Search Spec](EPIC_2_SEMANTIC_SEARCH_SPEC.md)
- [ADR-0003: Embedding DB Schema](../../knowledge/roadmap/adr/ADR-0003-embedding-db-schema-design.md)
- [CURRENT_STATUS](../knowledge/CURRENT_STATUS.md)
