# ADRS

Architektur-Entscheidungen (kurz). ADR-Dateien in `docs/adr/` und `knowledge/roadmap/adr/`.

## Accepted

- `docs/adr/ADR-0004-sqlite-vec-search-backend.md` — Accepted (2026-05-31); sqlite-vec statt FAISS
- `docs/adr/ADR-0005-search-quality-evaluation.md` — Accepted (2026-05-31); Tier A/B evaluation

## Historical (executed design decisions, kept for record)

- `knowledge/roadmap/adr/ADR-0001-embedding-model-strategy.md` — Accepted; CLAP embedding backend
- `knowledge/roadmap/adr/ADR-0002-local-vector-index-strategy.md` — Superseded by ADR-0004; FAISS never implemented
- `knowledge/roadmap/adr/ADR-0003-embedding-db-schema-design.md` — Accepted; SQLite schema for embeddings

> ADRs dokumentieren Design-Entscheidungen, keine Implementierungsnachweise.
> "Accepted" bedeutet: Entscheidung getroffen und umgesetzt oder gültig.
> "Superseded" bedeutet: durch eine spätere Entscheidung ersetzt (die Datei bleibt als historischer Record).
