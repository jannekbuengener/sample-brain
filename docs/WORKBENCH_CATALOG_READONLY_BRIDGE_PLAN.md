# Workbench ↔ Catalog Read-Only Bridge Plan

**Status:** Planning only — no runtime bridge, no schema change, no migration, no writes to `catalog.db`.  
**Parent:** [#117 — workbench usability and library workflow follow-ups](https://github.com/jannekbuengener/sample-brain/issues/117)  
**Related:** [`WORKBENCH_CATALOG_UNIFICATION_PLAN.md`](WORKBENCH_CATALOG_UNIFICATION_PLAN.md), `src/config.py`, `src/db.py`, `src/workbench_library.py`, `src/workbench_controller.py`

## 1. Problem

The workbench today uses a **user-local cache** (`workbench_library.db`) for fast folder analysis and cue/loop/attack metadata. The CLI pipeline stores the broader library in **`catalog.db`**. Producers eventually need to **browse catalog samples in the workbench** without merging databases, modifying original audio, or writing to the catalog.

**Shipped prerequisites (main):**

| Slice | Status |
|---|---|
| Global workbench library view (`load_all_cached_samples`) | ✅ PR #154 |
| Cross-folder search/filter/sort | ✅ PR #155 |
| Catalog unification planning doc | ✅ PR #153 |

**Next safe step:** read-only bridge — display catalog rows in the workbench UI without touching `catalog.db`.

## 2. Where `catalog.db` lives

| Resolution order | Source | Default |
|---|---|---|
| 1 | Profile `database.path` | — |
| 2 | Env `SAMPLE_BRAIN_DB_PATH` | — |
| 3 | Fallback | `data/catalog.db` under project root |

Implemented in `src/config.py` (`set_db_path`, `DEFAULT_DB_PATH`). Workbench code must **not** hardcode paths; use `config.DB_PATH` or an explicit `path` argument for tests.

**Workbench state** (separate): `~/.sample-brain/workbench_library.db` via `SAMPLE_BRAIN_WORKBENCH_STATE_DIR` override (`src/workbench_library.py`).

## 3. Catalog schema (read-only subset)

Authoritative definition: `src/db.py` `init_db()`.

### `samples` (identity + file metadata)

| Column | Workbench use | Notes |
|---|---|---|
| `id` | Internal only | Not shown in playlist |
| `path` | ✅ `path` | Absolute path; preview only if file exists |
| `relpath` | ✅ `relative_path` | May be empty |
| `samplerate`, `channels`, `duration` | Optional detail | Not in playlist v1 |
| `size_bytes` | Optional detail | No mtime in catalog |
| `hash` | Optional detail / future link | Not shown v1 |

### `features` (analysis, 1:1 via `sample_id`)

| Column | Workbench field | Notes |
|---|---|---|
| `bpm` | `bpm` | Nullable |
| `key`, `key_conf` | `key`, `key_conf` | Nullable |
| `loudness`, `brightness` | `loudness`, `brightness` | Nullable |
| `class` | `sample_class` | Maps to workbench `sample_class` |
| `pred_type` | `pred_type` | Nullable |
| `mfcc_*`, `chroma_*` blobs | ❌ | Not loaded in bridge v1 |

### Not in catalog (must not be claimed)

| Workbench field | Catalog | Bridge behavior |
|---|---|---|
| `cue_start_ms`, `attack_ms`, `loop_*` | ❌ | Default 0 / NULL; **read-only** — no save target |
| `display_name` | ❌ | Derive from filename via `normalize_display_name` |
| `status`, `error_code`, `quality_note` | Partial | Derive: `ok` if features row exists; `pending` if sample without features |
| `library_folder` | N/A | Use sentinel e.g. `catalog.db (read-only)` in `details` |
| Tags / embeddings | Separate tables | Out of scope for loader v1 |

### Join rule

```sql
SELECT s.id, s.path, s.relpath, s.size_bytes, s.duration,
       f.bpm, f.key, f.key_conf, f.loudness, f.brightness,
       f.class, f.pred_type
FROM samples s
LEFT JOIN features f ON f.sample_id = s.id
ORDER BY s.path COLLATE NOCASE
```

- **LEFT JOIN:** samples without `features` still appear (status `pending`).
- **Only `SELECT`:** connection opened read-only where possible (`mode=ro` URI or `PRAGMA query_only=ON`).

## 4. Field mapping → `WorkbenchRow`

Catalog rows map into existing `WorkbenchRow` (`src/workbench_controller.py`) for filter/sort reuse:

| `WorkbenchRow` | Catalog source |
|---|---|
| `display_name` | `normalize_display_name(Path(path).name)` |
| `relative_path` | `relpath` or `""` |
| `path` | `samples.path` |
| `bpm` … `pred_type` | `features.*` (nullable) |
| `sample_class` | `features.class` |
| `status` | `ok` / `pending` (derived) |
| `error` | `None` (v1) |
| `details` | `{"source": "catalog", "catalog_readonly": true, "library_folder": "…"}` |

**Source marker:** `details["source"] == "catalog"` distinguishes cache rows (`cache` or absent).

## 5. Safety contract (non-negotiable)

1. **Original audio files are never modified** by the catalog bridge.
2. **No `INSERT` / `UPDATE` / `DELETE` / `ALTER`** on `catalog.db` from workbench code.
3. **No automatic import** from catalog into `workbench_library.db` without explicit user action (later slice).
4. **No schema migration** on `catalog.db` for bridge slices.
5. Test databases only in `tmp_path`; never commit `.db` files.
6. Cue/loop/attack editors **disabled or no-op** for `source=catalog` rows until a write target exists.

## 6. Phased implementation

### Phase 1 — This document ✅

- Read API sketch, field matrix, safety contract, test strategy.
- No runtime code.

### Phase 2 — `workbench_catalog_readonly_loader_v1` ✅

New module `src/workbench_catalog.py`:

| Function | Status |
|---|---|
| `catalog_db_path()` | ✅ Shipped |
| `catalog_available()` | ✅ Shipped |
| `load_catalog_samples()` | ✅ Shipped |
| `load_catalog_rows()` in controller | ✅ Shipped |

`CatalogSampleRow` dataclass + `to_workbench_row()` with `source=catalog`, `catalog_readonly=True`.

**Tests** (`tests/test_workbench_catalog.py`): tmp_path DB, mapped fields, pending without features, missing DB → `[]`.

### Phase 3 — `workbench_catalog_readonly_view_v1` ✅

UI in `src/workbench.py`:

- Sidebar entry **「Catalog lesen」** (shows unavailable when DB missing)
- Loads catalog rows into playlist; status `Catalog-Samples: N geladen (read-only)`
- Detail panel: `Quelle: catalog.db (read-only)`
- Reuses filter/sort; blocks cue/loop/attack saves for catalog rows
- Preview: only if `Path(path).is_file()`

**Tests:** `is_catalog_readonly_row`, `load_catalog_rows`, sort stability in `tests/test_workbench_catalog.py`.

### Phase 4 — Cache import planning ✅

- **Dedicated plan:** [`WORKBENCH_CATALOG_CACHE_IMPORT_PLAN.md`](WORKBENCH_CATALOG_CACHE_IMPORT_PLAN.md) — catalog→cache direction, conflicts, backup, explicit user action, no auto-import.

### Phase 5 — Later unification (explicit GO)

See [`WORKBENCH_CATALOG_UNIFICATION_PLAN.md`](WORKBENCH_CATALOG_UNIFICATION_PLAN.md) Phase C–D: cue export, single source of truth, user-triggered cache import implementation.

## 7. Smallest safe loader sketch

```python
# Pseudocode — not shipped in Phase 1
def load_catalog_samples(path=None, limit=None):
    db = catalog_db_path(path)
    if not catalog_available(db):
        return []
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    sql = "SELECT s.path, s.relpath, ... FROM samples s LEFT JOIN features f ..."
    if limit:
        sql += " LIMIT ?"
    rows = conn.execute(sql, (limit,) if limit else ()).fetchall()
    return [_to_catalog_row(r) for r in rows]
```

- No SQLAlchemy required for read path (keeps workbench import graph light).
- Do **not** call `init_db()` on user catalog (would create tables / side effects).

## 8. Testing without user data

| Rule | Implementation |
|---|---|
| Isolated DB | `tmp_path / "catalog.db"` + `monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", ...)` |
| Schema | `init_db()` then INSERT fixtures |
| No committed binaries | No audio, no `.db` in repo |
| Workbench tests | Mock `load_catalog_samples` for UI slice |

## 9. What must NOT happen in bridge slices

- No `ALTER TABLE` on `catalog.db`
- No sync job catalog → workbench cache
- No embedding / index / search UI from catalog in v1
- No FL export from catalog rows in v1
- No dependency or workflow changes

## 10. Open questions (non-blocking)

1. **Large catalogs:** default `limit=5000` in UI? Plan default: optional limit in loader; UI shows count + warning if truncated.
2. **Missing files on disk:** show row with `status=ok` but preview disabled + hint "Datei nicht gefunden".
3. **Profile vs env:** loader uses same resolution as CLI (`config.DB_PATH`).

---

*Refs #117 — planning only; does not close the parent issue.*
