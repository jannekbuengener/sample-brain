# Architecture Overview

## Current Pipeline (Implemented)

```
Scan → Analyze → Autotype → Export
```

| Step | Module | Status |
|---|---|---|
| Scan | `src/scan.py` | Stable |
| Analyze | `src/analyze.py` (librosa features) | Stable |
| Autotype | `src/classify.py` (rules + kNN) | Stable |
| Export | `src/export_fl.py` (FL Studio tags) | Stable |

**Current stack:** SQLite catalog, argparse CLI, local-first, single-user.

## Target Pipeline (Planned)

```
Scan → Analyze → Embed → Index → Search → Recommend → Export / DAW Workflow
```

| Step | Module | Status |
|---|---|---|
| Embed | `src/embed.py` (planned) | **Not implemented** |
| Index | `src/index.py` (FAISS, planned) | **Not implemented** |
| Search | `src/search.py` (text/audio similarity, planned) | **Not implemented** |
| Recommend | future (hybrid ranking, EPIC 3) | **Not implemented** |
| API | FastAPI (planned, EPIC 4) | **Not implemented** |
| UI | React/Tauri (planned, EPIC 4+) | **Not implemented** |

## Architecture Decisions

- **SQLite** is the source of truth for all metadata (samples, features, embeddings)
- **FAISS** is the planned local vector index cache (rebuildable, not committed)
- **CLAP** is the planned embedding backend (local-first, no cloud dependency)
- All vector/ML artifacts are in `.gitignore` — never committed

> **Note:** Modules under "Planned" do not yet exist. CLI subcommands `embed`, `index_build`, and `search` are registered as optional but fail gracefully with a warning when invoked.
