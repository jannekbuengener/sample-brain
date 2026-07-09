# Workbench ↔ Catalog Unification Plan

**Status:** Planning only — no schema merge, no migration in this document.  
**Parent:** [#117 — workbench usability and library workflow follow-ups](https://github.com/jannekbuengener/sample-brain/issues/117)  
**Related:** `src/workbench_library.py`, `src/db.py`, [`WORKBENCH_CUE_METADATA_PLAN.md`](WORKBENCH_CUE_METADATA_PLAN.md)

## 1. Problem

The workbench today uses a **separate** user-local SQLite cache (`workbench_library.db`). The CLI pipeline uses **`catalog.db`** (`src/db.py`). Producers need both to converge eventually without breaking existing data or modifying original audio files.

## 2. Two databases today

| Aspect | `workbench_library.db` | `catalog.db` |
|---|---|---|
| Location | `~/.sample-brain/workbench_library.db` (or `SAMPLE_BRAIN_WORKBENCH_STATE_DIR`) | `SAMPLE_BRAIN_DB_PATH` / profile default |
| Purpose | Fast workbench UI cache per folder | CLI scan/analyze/embed/search source of truth |
| Scope | Registered workbench folders + cached analysis | Full library scan roots |
| Identity key | `original_path` UNIQUE | `samples.path` UNIQUE + `hash` |
| Invalidation | `size_bytes` + `mtime_ns` per sample | Rescan / re-analyze workflows |
| Folder model | `folders` table (explicit register) | Implicit via `relpath` under scan root |
| Cue/loop/attack | ✅ `cue_start_ms`, `attack_ms`, `loop_*` on `samples` | ❌ not stored |
| Embeddings / tags | ❌ | ✅ `sample_embeddings`, `sample_tags`, `features` blobs |
| Analyzer version | `analyzer_version` (`workbench_v1`) | Pipeline modules (librosa + classify) |

## 3. Field overlap

| Concept | Workbench `samples` | Catalog `samples` + `features` |
|---|---|---|
| Path | `original_path` | `path` |
| Relative path | `relative_path` | `relpath` |
| Size | `size_bytes` | `size_bytes` |
| Change detection | `mtime_ns` | rescan / hash |
| BPM | `bpm` | `features.bpm` |
| Key | `key`, `key_conf` | `features.key`, `features.key_conf` |
| Loudness / brightness | `loudness`, `brightness` | `features.loudness`, `features.brightness` |
| Type | `sample_class`, `pred_type` | `features.class`, `features.pred_type` |
| Error state | `status`, `error_code`, `quality_note` | implicit (missing features row) |
| Display title | `display_name` (internal) | filename from path |
| Cue metadata | ✅ workbench-only columns | ❌ |
| MFCC/chroma blobs | ❌ | ✅ |
| Semantic search | ❌ | ✅ via embeddings |

## 4. Recommended direction (phased)

### Phase A — Now (safe, no catalog touch) — ✅ shipped

1. **Global workbench library view** — `load_all_cached_samples` across registered folders.
2. **Cross-folder filter/sort** — `library_folder` included in search haystack.
3. **Cue/loop/attack** remain in workbench DB only.

### Phase B — Read-only bridge (next, still no writes to catalog)

1. Optional UI: “Catalog öffnen (read-only)” pointing at `SAMPLE_BRAIN_DB_PATH`.
2. Read `samples` + `features` into `WorkbenchRow` for display/preview only.
3. **Do not** write cue metadata into catalog until schema + product GO.
4. **Dedicated plan:** [`WORKBENCH_CATALOG_READONLY_BRIDGE_PLAN.md`](WORKBENCH_CATALOG_READONLY_BRIDGE_PLAN.md) — field mapping, loader sketch, UI phases, safety contract.

### Phase C — Unified metadata (later, explicit GO)

1. Add cue columns to catalog **or** linked `sample_edit_metadata` table with FK to `samples.id`.
2. One-way import: workbench cache → catalog on user action.
3. Migration script with backup; never auto-merge silently.

### Phase D — Single source of truth (long-term)

1. Catalog becomes authoritative for analysis + search.
2. Workbench becomes a view/controller over catalog + local cue overlay.
3. FL export / semantic search UI read same DB.

## 5. What must NOT happen now

- No `ALTER TABLE` on `catalog.db` for workbench slices
- No automatic merge of `workbench_library.db` into `catalog.db`
- No writes from workbench analysis into catalog without dedicated issue/GO
- No embedding/index build from workbench UI in first unification slices
- Original audio files never modified

## 6. Smallest safe implementation slices (ordered)

| Slice | Scope | Risk |
|---|---|---|
| `workbench_global_cached_library_view_v1` | All folders from workbench cache | ✅ Low |
| `workbench_global_search_filter_v1` | Filter across global rows | ✅ Low |
| `workbench_catalog_readonly_bridge_plan` | Docs + read API sketch | ✅ Plan doc shipped |
| `workbench_catalog_readonly_loader_v1` | Read-only `load_catalog_samples` | ✅ Shipped |
| `workbench_catalog_readonly_view_v1` | Catalog sidebar + playlist | ✅ Shipped |
| `workbench_catalog_cache_import_plan` | Import/sync semantics (docs only) | ✅ Plan doc |
| `workbench_catalog_to_cache_import_v1` | Explicit catalog → cache import (code) | High — needs implementation GO |
| `workbench_cue_export_to_catalog` | Explicit user export of cue fields | High — needs schema GO |

## 7. Identity matching (future bridge)

When linking rows across DBs:

- **Primary:** resolved absolute `path` equality
- **Secondary:** `size_bytes` + content `hash` (catalog) vs `mtime_ns` (workbench cache)
- **Conflict:** same path, different analysis — show “catalog vs cache” badge; user picks refresh source

## 8. Open product questions (non-blocking)

1. Should workbench analysis eventually call `scan` + `analyze` on `catalog.db`? **Plan default:** yes, long-term; not in first bridge slice.
2. Should global view include folders not yet analyzed? **Plan default:** no — only cached rows; empty folders show hint to analyze.
3. Should removed library folders keep orphan cue rows? **Current:** `remove_library_folder` deletes cached samples for that folder.

---

*Refs #117 — planning only; does not close the parent issue.*
