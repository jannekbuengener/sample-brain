# Workbench Search UI Plan

**Status:** Structured filter controls and BPM range shipped on `main`; status bar polish shipped; active-filter summary and reset button planned next.  
**Parent:** [#117 — workbench usability and library workflow follow-ups](https://github.com/jannekbuengener/sample-brain/issues/117)  
**Related:** [`WORKBENCH_CATALOG_UNIFICATION_PLAN.md`](WORKBENCH_CATALOG_UNIFICATION_PLAN.md), [`WORKBENCH_CATALOG_READONLY_BRIDGE_PLAN.md`](WORKBENCH_CATALOG_READONLY_BRIDGE_PLAN.md), [`WORKBENCH_CATALOG_CACHE_IMPORT_PLAN.md`](WORKBENCH_CATALOG_CACHE_IMPORT_PLAN.md), `src/workbench_controller.py`, `src/search_filters.py`

## 1. Problem

Producers need a **local, honest sample workbench** — find samples across folders, distinguish workbench cache from catalog, and narrow results by metadata **without** semantic search, CLAP, sqlite-vec, or ANN.

**Shipped on `main` (prerequisites):**

| Capability | Status |
|---|---|
| Single-folder analyze + playlist | ✅ |
| Library folder list + cache (`workbench_library.db`) | ✅ PR #128 |
| **Alle Library-Samples** — cross-folder cache view | ✅ PR #154 |
| Text filter on playlist (`filter_workbench_rows`) | ✅ PR #120, #155 |
| Column sort | ✅ PR #121 |
| **Catalog lesen** — read-only `catalog.db` browse | ✅ PR #158–#161 |
| Catalog load limit + total count status | ✅ PR #160 |
| Catalog read-only badges + edit block | ✅ PR #161 |

**Gap:** Only a single free-text search field exists. No structured filters for BPM, key, type/class, status, or source. Status lines during search are minimal and do not always explain mode, limits, or read-only context.

## 2. Product goal (this track)

Sample Brain becomes a **local sample workbench**:

1. Find samples in multiple folders (cache) and in `catalog.db` (read-only).
2. Clearly separate **Workbench-Cache** vs **Catalog-Readonly** rows.
3. Search/filter by **name, folder, BPM, key, type, status, source** using existing metadata.
4. Keep UI simple — no query language, no new search page.
5. **Prepare** for semantic search later without building it now.

**Explicit non-goals for this track:**

| Topic | Issue / track | Why separate |
|---|---|---|
| CLAP embeddings / Tier-B eval | [#73](https://github.com/jannekbuengener/sample-brain/issues/73) | Semantic quality evidence, not workbench UI |
| sqlite-vec / ANN backend | [#74](https://github.com/jannekbuengener/sample-brain/issues/74) | CLI search backend, not workbench playlist |
| Semantic / text-to-sample search | EPIC 2 CLI (`search` command) | Different surface; workbench uses in-memory row filters |
| Catalog→cache import | [`WORKBENCH_CATALOG_CACHE_IMPORT_PLAN.md`](WORKBENCH_CATALOG_CACHE_IMPORT_PLAN.md) | Explicit user action; later slice |
| `catalog.db` writes / schema change | — | Forbidden |
| Original audio modification | — | Forbidden |

## 3. Current search behavior

### 3.1 View modes (sidebar)

| Mode | Token / label | Row source | Writable cue/loop? |
|---|---|---|---|
| Single folder | Registered folder path | `workbench_library.db` cache for that folder | ✅ |
| Global library | `Alle Library-Samples` | All cached rows across folders | ✅ |
| Catalog | `Catalog lesen` | `catalog.db` read-only (`details.catalog_readonly`) | ❌ |

Mode is selected via sidebar — not a filter dropdown today.

### 3.2 Text search (`filter_workbench_rows`)

Implemented in `src/workbench_controller.py`. Case-insensitive substring match across:

- `display_name`, `relative_path`
- `key`, `pred_type`, `sample_class`, `status`, `error`
- `details.library_folder` and folder basename (global view)

**Not searched today:** `bpm` (numeric), `tags` (unless in error text), explicit source marker.

### 3.3 CLI precedent (`src/search_filters.py`)

The CLI `search` command already supports `SearchFilters` (tags, BPM range, key, scale, duration, `pred_type`) against `catalog.db`. Workbench filters should **mirror field names** where possible but operate **in-memory** on loaded `WorkbenchRow` lists — no SQL, no `catalog.db` writes.

## 4. Recommended filter fields (priority order)

### 4.1 Keep: free-text search

| Field | Matches |
|---|---|
| Textsuche | Name, relative path, library folder path, tags (when present in `details.tags`), status/error text |

Stays as primary quick filter; structured filters narrow further (AND logic).

### 4.2 Slice 1 — structured filters (`workbench_structured_filter_controls_v1`)

| Control | Values | Applies to | Notes |
|---|---|---|---|
| **Quelle** | `alle` / `cache` / `catalog` | Rows in current view | `catalog` ⇔ `details.catalog_readonly`; `cache` ⇔ not catalog. In single-folder/global views all rows are cache; in catalog view all are catalog — control still useful for consistency and future mixed views. |
| **Type/Class** | Dropdown + `alle` | Rows with `pred_type` or `sample_class` | Match either field case-insensitively; empty = no type filter. |
| **Key** | Dropdown + `alle` | Rows with `key` | Exact match (case-insensitive); populate from distinct values in loaded rows. |
| **Status** | `alle` / `ok` / `error` / `pending` | All rows | `pending` mainly catalog rows without features. |

**UI placement:** Second row below existing search `Entry`, compact `ttk.Combobox` or `OptionMenu` controls. Existing search field is **not** replaced.

### 4.3 Slice 2 — BPM range (`workbench_bpm_filter_v1`)

| Control | Behavior |
|---|---|
| BPM von | Optional minimum (inclusive); blank = no min |
| BPM bis | Optional maximum (inclusive); blank = no max |

- Rows with `bpm is None` excluded when any BPM bound is active (honest: unknown BPM cannot satisfy a range).
- Invalid input (non-numeric) ignored with no crash; optional subtle status hint.
- Reuse numeric comparison pattern from `SearchFilters.min_bpm` / `max_bpm`.

### 4.4 Slice 3 — status polish (`workbench_search_status_polish`)

Unify status bar messages when filters are active:

| Mode | Example status |
|---|---|
| Single folder | `Ordner: 12 von 80 Treffer` |
| Global library | `Alle Library-Samples: 23 von 240 Treffer` |
| Catalog + filter | `Catalog-Samples: 18 Treffer (500 von 12000 geladen, read-only, Limit aktiv)` |
| Catalog, no filter | Existing `format_catalog_load_status` + read-only hint |

Show active filter summary when structured filters differ from defaults (e.g. `Filter: Key=Am, Status=ok`).

## 5. Filter applicability matrix

| Filter | Single folder | Alle Library-Samples | Catalog lesen |
|---|---|---|---|
| Textsuche | ✅ | ✅ | ✅ |
| Quelle | cache only* | cache only* | catalog only* |
| Type/Class | ✅ | ✅ | ✅ |
| Key | ✅ | ✅ | ✅ |
| Status | ✅ | ✅ | ✅ (incl. `pending`) |
| BPM range | ✅ | ✅ | ✅ |

\*Until a unified mixed-source view exists, Quelle is redundant per mode but keeps API stable.

## 6. Source / read-only / limit display

| Signal | Where shown |
|---|---|
| Catalog row | `⧉` prefix in playlist name (shipped) |
| Read-only edit block | Status message on cue/loop/attack attempt (shipped) |
| Catalog load limit | `format_catalog_load_status` — `N von M geladen` (shipped) |
| Filter hit count | Status bar after Slice 3 |
| Quelle filter | Control label + optional status suffix |

**`catalog.db` remains read-only.** Filter logic must not trigger writes, imports, or schema changes.

## 7. UI simplicity rules

1. **One playlist** — no separate search tab.
2. **No query language** — no `bpm:120 key:Am` syntax in v1.
3. **AND composition** — text + each active structured filter must all match.
4. **Reset** — clearing text (Escape) + setting dropdowns to `alle` restores full loaded set.
5. **Sort preserved** — filters apply before or after sort consistently (filter → sort, current pattern).
6. **No new dependencies** — tkinter/ttk only.

## 8. Implementation sketch

### 8.1 New controller API (proposed)

```python
@dataclass(frozen=True)
class WorkbenchRowFilters:
    source: Literal["all", "cache", "catalog"] = "all"
    pred_type: str | None = None      # matches pred_type or sample_class
    key: str | None = None
    status: str | None = None         # ok | error | pending
    min_bpm: float | None = None
    max_bpm: float | None = None

def apply_workbench_filters(
    rows: list[WorkbenchRow],
    text_query: str,
    filters: WorkbenchRowFilters | None = None,
) -> list[WorkbenchRow]:
    ...
```

`filter_workbench_rows` remains for backward compatibility; internally delegates or composes.

### 8.2 Source detection

```python
def row_source_kind(row: WorkbenchRow) -> Literal["cache", "catalog"]:
    return "catalog" if row.details.get("catalog_readonly") else "cache"
```

Catalog rows set `details["source"] == "catalog"` in `workbench_catalog.py`; cache rows omit or use cache markers only.

### 8.3 Tests (per slice)

- Unit tests in `tests/test_workbench_controller.py` (no GUI).
- Catalog tests in `tests/test_workbench_catalog.py` for readonly preservation.
- Doc test in `tests/test_workbench_docs.py` for this plan.
- No audio files, no committed DBs; `tmp_path` only.

## 9. Phased delivery

| Phase | Slice | Scope |
|---|---|---|
| **1** | `workbench_search_ui_plan` | This document ✅ |
| **2** | `workbench_structured_filter_controls_v1` | Quelle, Type, Key, Status + UI row ✅ |
| **3** | `workbench_bpm_filter_v1` | BPM min/max fields ✅ |
| **4** | `workbench_search_status_polish` | Status bar clarity ✅ |
| **5** | `workbench_active_filter_summary_v1` | Active filter hint line |
| Later | Catalog→cache import | Separate plan |
| Later | Semantic search in workbench | Blocked on product decision + #73/#74 |

## 10. Safety contract

1. **Original audio files are never modified** by search/filter UI.
2. **No writes to `catalog.db`** — browse remains `SELECT` only.
3. **No schema changes** to `catalog.db` or `workbench_library.db` for filter slices.
4. **No new dependencies** or workflow changes.
5. **#117 stays OPEN** — collective workbench issue; PRs use `Refs #117` only.
6. Test databases only in `tmp_path`; never commit `.db`, audio, caches, or secrets.

## 11. Acceptance (planning phase)

- [x] Document exists and is linked from backlog/status.
- [x] Filter field priorities defined.
- [x] Cache vs catalog vs semantic tracks separated.
- [x] Smallest implementation slices named.
- [x] Structured filter UI shipped (Phase 2).
- [x] BPM filter shipped (Phase 3).
- [x] Status polish shipped (Phase 4).
- [ ] Active filter summary (Phase 5).

## 12. References

- Issue [#117](https://github.com/jannekbuengener/sample-brain/issues/117) — workbench collective follow-ups (stays OPEN)
- Issue [#73](https://github.com/jannekbuengener/sample-brain/issues/73) — CLAP Tier-B (out of scope)
- Issue [#74](https://github.com/jannekbuengener/sample-brain/issues/74) — sqlite-vec ANN (out of scope)
- `src/workbench.py` — playlist UI, `_filter_var`, mode flags
- `src/workbench_controller.py` — `filter_workbench_rows`, `WorkbenchRow`
- `src/search_filters.py` — CLI filter precedent (not imported by workbench in v1)
