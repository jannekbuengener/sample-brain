# ADR-0003: Embedding DB Schema Design

**Status:** Proposed  
**Applied:** Not yet  
**Deciders:** (project owner)

---

## Context

The existing SQLite catalog (`data/catalog.db`) has two tables:

- `samples` — file metadata (path, hash, duration, etc.)
- `features` — acoustic features (BPM, key, MFCCs, chroma, pred_type, etc.) linked by `sample_id`

EPIC 2 adds a new domain: model metadata and sample embeddings. The schema must support:

- Multiple embedding models (for comparison or fallback)
- Multiple embeddings per sample (one per model version)
- Reproducibility (same model + same sample → same embedding)
- Staleness detection (detect when model changes invalidate embeddings)
- Future hybrid search (joins between embeddings and feature-based filters)

---

## Decision / Target Tables

### `embedding_models`

Stores metadata about each embedding model/version ever used.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | auto-increment |
| `provider` | TEXT | e.g. "clap", "openl3" |
| `model_name` | TEXT | e.g. "laion/clap-htsat-fused" |
| `model_version` | TEXT | release tag, git hash, or checksum |
| `embedding_dim` | INTEGER | e.g. 512 |
| `modality` | TEXT | "audio", "text", "audio+text" |
| `created_at` | TEXT | ISO 8601 timestamp |

**Unique constraint:** `(provider, model_name, model_version)`

### `sample_embeddings`

Stores one embedding vector per sample per model.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | auto-increment |
| `sample_id` | INTEGER | FK → samples.id |
| `model_id` | INTEGER | FK → embedding_models.id |
| `embedding` | BLOB | raw float32 array bytes |
| `embedding_format` | TEXT | "numpy-blob", "json", etc. |
| `source_hash` | TEXT | hash of sample file content at embedding time |
| `created_at` | TEXT | ISO 8601 timestamp |

**Unique constraint:** `(sample_id, model_id, source_hash)` — prevents duplicate embeddings for the same sample+model+content

### Rationale

- **BLOB storage**: SQLite BLOB is simple, transactional, and avoids file-system sync issues. For <100k samples × 512 dims × 4 bytes ≈ 200 MB, this is well within SQLite's practical limits.
- **`source_hash`** enables staleness detection: if the sample file changes (re-exported, re-rendered), the hash won't match and re-embedding is triggered.
- **Separate `embedding_models` table** instead of string columns on `sample_embeddings` ensures referential integrity and avoids data duplication.

---

## Future Tables (Not Yet Decided)

| Table | Purpose | When |
|---|---|---|
| `embedding_jobs` | Track batch embedding progress, resume on failure | After batch worker implementation |
| `vector_indexes` | Track FAISS index builds (checksum, sample count, model, timestamp) | After FAISS integration |

---

## Open Questions

1. **BLOB vs. external vector store** — BLOB in SQLite is the starting point. If performance degrades with scale, external NumPy files or a dedicated vector store can be introduced later without changing the API.
2. **Migration strategy** — Current `init_db()` uses `CREATE TABLE IF NOT EXISTS`. For new tables this is sufficient. For future column changes, a migration tool (Alembic or hand-rolled) will be needed.
3. **Multi-modal embeddings** — Some models produce separate audio/text vectors or multiple vectors per sample. The schema can be extended with a `modality` column on `sample_embeddings` when needed.

---

## Consequences

1. **Idempotent deployment** — New tables can be added via `CREATE TABLE IF NOT EXISTS` in `init_db()`. No migration tool needed yet.
2. **Duplicate prevention** — The `(sample_id, model_id, source_hash)` unique constraint prevents accidental re-embedding of unchanged files.
3. **Join compatibility** — `sample_embeddings.sample_id` joins with `samples.id` and `features.sample_id`, enabling hybrid search in EPIC 3.
4. **Not implemented yet** — This ADR documents the schema design only. No table creation, no migration, no embedding storage exists at the time of writing.

---

## Non-Goals

- No schema code in this commit
- No migration execution
- No DB file creation or modification
- No embedding storage
