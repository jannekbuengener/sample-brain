# ADR-0002: Local Vector Index Strategy

**Status:** Proposed  
**Applied:** Not yet  
**Deciders:** (project owner)

---

## Context

EPIC 2 requires fast semantic similarity search over the sample catalog. Storing embeddings in SQLite is sufficient for persistence, but linear scans over thousands of embedding vectors are too slow for interactive search.

Requirements:

- Sub-second approximate nearest-neighbor search over up to ~100k samples
- Local-first: no cloud index service
- Rebuildable: index is a cache, not the source of truth
- Must not be committed to version control

---

## Decision

**FAISS** (Facebook AI Similarity Search) is the primary candidate for the local vector index.

Rationale:

- Industry standard for approximate nearest-neighbor (ANN) search
- CPU-only support available (`faiss-cpu`) — no GPU required
- Works with flat (exact) and IVF (approximate) index types
- Embedding vectors are 512-dim (CLAP) → FAISS IndexFlatIP or IndexIVFFlat
- Open-source (MIT license)
- Well-integrated with NumPy arrays (embeddings from backend)

Index lifecycle:

- **Source of truth:** SQLite (`sample_embeddings` table) — stores all sample-to-vector mappings
- **Cache:** FAISS index file on disk — rebuilt from `sample_embeddings` on demand
- **Rebuild:** `sample-brain index_build` command reads all embeddings from DB, trains index, writes to `data/indexes/`
- **Staleness detection:** Index has a version/checksum in its filename; rebuild if mismatched with DB

Index file location (planned):

```
data/indexes/
├── <model_name>-<model_version>-<index_type>.faiss
└── <model_name>-<model_version>-<index_type>.meta  # JSON: sample_id mapping
```

---

## Alternatives Considered

| Alternative | Reason Not Chosen (as primary) |
|---|---|
| **SQLite BLOB + linear scan** | Too slow for >10k samples; no ANN support |
| **Annoy** (Spotify) | Simpler but less flexible; fixed index type |
| **scikit-learn NearestNeighbors** | No persistent index format; in-memory only |
| **Chroma / Qdrant (embedded)** | Overkill for single-user local tool; heavier dependencies |
| **Elasticsearch** | Violates local-first constraint; heavy runtime |

---

## Consequences

1. **Artifact hygiene** — FAISS index files (`*.faiss`), NumPy cache files (`*.npy`, `*.npz`), and index metadata (`data/indexes/`) are all in `.gitignore`. This was verified during EPIC 0.
2. **Rebuild cost** — Index rebuild requires iterating all embeddings. For ~100k 512-dim vectors this takes seconds to minutes on CPU.
3. **Sample ID mapping** — FAISS indexes by integer position, not sample_id. A separate metadata file (JSON) maps index position → sample_id.
4. **Not implemented yet** — This ADR documents the design decision only. No FAISS import, no index build, no search exists at the time of writing.

---

## Non-Goals

- No FAISS import in this commit
- No index build
- No search implementation
- No GPU index types in first iteration
