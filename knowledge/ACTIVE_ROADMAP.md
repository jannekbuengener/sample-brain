# ACTIVE_ROADMAP

## Current Status

- **Repository hygiene** (EPIC 0): completed
  - Tracked artifacts removed from index (`.venv/`, `data/catalog.db`, `reports/`)
  - `.gitignore` tightened for local/private/generated artifacts
  - `analyze.py` repaired (patch/diff artifacts removed)
  - Packaging metadata added (`pyproject.toml`)
  - Minimal CI smoke workflow committed (GitHub Actions blocked by billing)
  - Dependencies tightened (`typer` removed, `pyyaml` pinned)
  - README aligned with current CLI commands
  - ADRs created for EPIC 2 architecture decisions

## Next Focus: EPIC 2 — Semantic Search Foundation

### P0 — Design & Hygiene
- [x] ADR-0001: Embedding Model Strategy (CLAP)
- [x] ADR-0002: Local Vector Index Strategy (FAISS)
- [x] ADR-0003: Embedding DB Schema Design

### P1 — First Implementation Steps
- [ ] Idempotent DB schema extension (`embedding_models`, `sample_embeddings`)
- [ ] Embedding backend interface (abstract base, no CLAP yet)
- [ ] CLAP backend spike (torch + transformers)

### P2 — Search Pipeline
- [ ] FAISS index build module
- [ ] Text-to-sample search
- [ ] Audio-to-audio similarity search

## Later: EPIC 3-6

- Hybrid ranking (BPM, key, type + vector similarity)
- FastAPI local service
- React/Tauri desktop UI
- DAW integration (FL Studio, Ableton, Reaper)
- DSP-based re-imagine / variant generator

---

> **Note:** Features listed under P1/P2 are not yet implemented. The codebase currently supports: Scan → Analyze → Autotype → Export only.
