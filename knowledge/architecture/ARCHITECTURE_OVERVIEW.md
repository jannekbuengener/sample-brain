# Architecture Overview

## Pipeline

```
Scan → Analyze → Autotype → Embed → Index → Search → Export
```

| Step | Module | Status |
|---|---|---|
| Scan | `src/scan.py` | Stable |
| Analyze | `src/analyze.py` (librosa features) | Stable |
| Autotype | `src/classify.py` (rules + kNN) | Stable |
| Embed | `src/embed.py` | Stable — CLAP optional, Noop default |
| Index | `src/index.py`, `src/search_backend.py` | Stable — NumPy default; sqlite-vec opt-in via `[vec]` |
| Search | `src/search.py` | Stable — text/audio queries; NumPy or sqlite-vec backend |
| Export | `src/export_fl.py` (FL Studio tags) | Stable |
| Recommend | future (hybrid ranking, EPIC 3) | **Not implemented** |
| API | FastAPI (planned, EPIC 4) | **Not implemented** |
| UI | React/Tauri (planned, EPIC 4+) | **Not implemented** |

**Current stack:** SQLite catalog, argparse CLI, local-first, single-user.

## Architecture Decisions

- **SQLite** is the source of truth for all metadata (samples, features, embeddings)
- **sqlite-vec** is the opt-in vector search cache (ADR-0004); NumPy remains default search backend
- **CLAP** is the optional embedding backend (local-first, no cloud dependency)
- **FAISS** is superseded by sqlite-vec (ADR-0004); never implemented on `main`
- All vector/ML artifacts are in `.gitignore` — never committed
