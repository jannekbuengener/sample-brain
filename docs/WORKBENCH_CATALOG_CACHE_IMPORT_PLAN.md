# Workbench ↔ Catalog Cache Import Plan

**Status:** Planning only — no runtime import, no migration, no writes to `catalog.db`, no automatic data transfer.  
**Parent:** [#117 — workbench usability and library workflow follow-ups](https://github.com/jannekbuengener/sample-brain/issues/117)  
**Related:** [`WORKBENCH_CATALOG_UNIFICATION_PLAN.md`](WORKBENCH_CATALOG_UNIFICATION_PLAN.md), [`WORKBENCH_CATALOG_READONLY_BRIDGE_PLAN.md`](WORKBENCH_CATALOG_READONLY_BRIDGE_PLAN.md), `src/workbench_library.py`, `src/workbench_catalog.py`

## 1. Problem

The workbench today has **two data surfaces**:

| Surface | DB | Editable in workbench |
|---|---|---|
| Workbench cache | `workbench_library.db` | ✅ analysis + cue/loop/attack |
| Catalog browse | `catalog.db` (read-only) | ❌ display/preview only |

Producers eventually need a **controlled** way to copy selected catalog metadata into the workbench cache (or export cache metadata into the catalog) without silent overwrites, without modifying original audio files, and without automatic background sync.

**Shipped prerequisites (main):**

| Slice | Status |
|---|---|
| Read-only catalog loader (`load_catalog_samples`) | ✅ PR #157 |
| Catalog sidebar + playlist (`Catalog lesen`) | ✅ PR #158 |
| Cue/loop/attack in workbench cache only | ✅ prior PRs |

**Next safe step:** plan explicit user-triggered import/sync semantics before any write path is implemented.

## 2. What “import” means (practical)

**Import** = a deliberate, user-initiated copy of **metadata rows** from one SQLite store into the other, scoped to selected samples or an explicit scope (folder / filter result). It does **not** mean:

- re-scanning or re-analyzing audio automatically
- copying or moving audio files on disk
- merging databases wholesale
- background sync on workbench startup
- writing cue metadata into `catalog.db` without schema + product GO

### 2.1 Direction matrix

| Direction | First slice? | Rationale |
|---|---|---|
| **Catalog → Workbench cache** | ✅ Yes (smallest) | User brings catalog analysis into editable cache; cue fields stay cache-only; no `catalog.db` writes |
| **Workbench cache → Catalog** | Later (explicit GO) | Requires catalog schema extension for cue columns or linked overlay table |
| **Bidirectional sync** | Long-term | Only after conflict rules, backup, and per-field ownership are proven |

**Plan default:** implement **Catalog → cache** first; treat cache → catalog as a separate issue with schema GO.

## 3. Which data may be copied

### 3.1 Catalog → Workbench cache (planned)

| Field group | Copy on import? | Notes |
|---|---|---|
| `path`, `relpath` | ✅ | Identity key: resolved absolute `path` |
| `size_bytes` | ✅ | From catalog `samples`; cache also stores `mtime_ns` from disk at import time |
| `bpm`, `key`, `key_conf`, `loudness`, `brightness` | ✅ | From `features` |
| `sample_class`, `pred_type` | ✅ | Maps `features.class` / `features.pred_type` |
| `status` | ✅ derived | `ok` if features exist; `pending` otherwise |
| `display_name` | ✅ derived | `normalize_display_name(filename)` |
| `cue_start_ms`, `attack_ms`, `loop_*` | ❌ from catalog | Not in catalog; remain cache defaults (0 / NULL) unless user edits after import |
| Tags, embeddings, MFCC blobs | ❌ v1 | Out of scope for first import slice; catalog remains search authority |
| `hash` | Optional later | Cache uses `mtime_ns` + `size_bytes` for invalidation today |

**Missing in catalog (cannot import):** cue/loop/attack, workbench `quality_note`, per-folder registration unless user also registers the scan root folder.

### 3.2 Workbench cache → Catalog (later, not v1)

| Field group | Requires |
|---|---|
| Cue/loop/attack | `ALTER TABLE` or `sample_edit_metadata` table + product GO |
| Re-analysis fields | Existing `features` upsert path via CLI `analyze` — not workbench UI v1 |
| Folder registration | `scan --root` workflow; not implicit from cache |

## 4. Conflict detection

Match rows primarily by **resolved absolute path** (`original_path` in cache == `samples.path` in catalog).

| Situation | Detection | Planned UX |
|---|---|---|
| Path not in cache | No conflict | Insert new cache row under registered folder (or prompt to register folder) |
| Path in cache, same analysis | `bpm`/`key`/`pred_type` equal within tolerance | Skip or “already up to date” |
| Path in cache, different analysis | Field mismatch | Show **catalog vs cache** badge; user chooses: keep cache / overwrite from catalog / skip |
| Path in cache, user cue edits | Cue columns non-default in cache | **Never silent overwrite** of cue fields on catalog import |
| Same path, different file on disk | `size_bytes` or `mtime_ns` mismatch | Warn “file changed since cache”; offer re-import analysis fields only |
| Catalog row, file missing on disk | `Path(path).is_file()` false | Import metadata allowed; preview disabled; status hint |

Secondary match (future): catalog `hash` vs cache `size_bytes` + `mtime_ns` when path moved — **out of scope** for first import slice.

## 5. Backup and undo

| Mechanism | Plan |
|---|---|
| Pre-import backup | Copy `workbench_library.db` to timestamped file under `~/.sample-brain/backups/` (user-local, not committed) |
| Undo | Restore from backup file via explicit “Aus Backup wiederherstellen” action — not automatic rollback |
| Catalog safety | Import slices **never** write `catalog.db`; no catalog backup required for catalog→cache |
| Audit | Optional import log table in workbench DB (later): source, timestamp, row count, scope |

**No silent merge:** user confirms scope and conflict resolution before any `INSERT`/`UPDATE` on `workbench_library.db`.

## 6. Required user action

Every import requires **explicit** steps (no defaults-on-startup):

1. User browses catalog (read-only) or selects rows in catalog view.
2. User triggers **「Aus Catalog importieren」** (or equivalent) — button/menu, not automatic.
3. Dialog shows: row count, target folder registration, conflicts preview.
4. User confirms **Import starten** (or cancels).
5. Post-import status: `N importiert, M übersprungen, K Konflikte`.

Optional later: **「In Catalog exportieren」** as separate flow with its own confirmation and schema GO.

## 7. Explicitly not allowed (any slice without new GO)

1. **No automatic import** on workbench launch, catalog open, or folder register.
2. **No silent overwrite** of cache cue/loop/attack from catalog (catalog has no cue data).
3. **No writes to `catalog.db`** from workbench import v1.
4. **No modification of original audio files** on disk.
5. **No full-database merge** (`ATTACH` + bulk copy without user scope).
6. **No embedding/index build** triggered by import UI.
7. **No committed user DBs**, audio, or machine-local paths in repo.
8. **No schema change** on `catalog.db` for import-plan or first cache-import slice.

## 8. Smallest later implementation slice

**`workbench_catalog_to_cache_import_v1`** (code — **not** in this document):

| Step | Scope |
|---|---|
| 1 | `preview_catalog_import(paths) -> ImportPreview` (read-only catalog + cache read) |
| 2 | UI button on catalog view; disabled when not in catalog mode |
| 3 | Confirm dialog with counts + conflict list |
| 4 | `import_catalog_rows_to_cache(rows, folder_id, conflict_policy)` — writes **only** `workbench_library.db` |
| 5 | Backup hook before first write |
| 6 | Tests: tmp_path both DBs, conflict paths, cue preservation, no catalog writes |

**Conflict policy enum (sketch):** `skip_existing` | `overwrite_analysis_only` | `cancel_on_conflict`.

## 9. Relationship to other tracks

| Track | Relationship |
|---|---|
| [#117](https://github.com/jannekbuengener/sample-brain/issues/117) | Parent; remains open after import slices |
| [#73](https://github.com/jannekbuengener/sample-brain/issues/73) CLAP eval | Separate; semantic search not part of import v1 |
| [#74](https://github.com/jannekbuengener/sample-brain/issues/74) sqlite-vec | Separate; no ANN in import |
| PR #103 numpy bump | Unrelated; hold |
| Read-only bridge | Prerequisite ✅; import builds on loader + UI |

## 10. Open product questions (non-blocking)

1. **Folder registration:** Must user register scan root before import, or auto-create folder row from `relpath`? **Plan default:** require explicit folder register (consistent with cache model).
2. **Bulk import cap:** Max rows per operation? **Plan default:** same optional limit as large-catalog UX; confirm dialog shows cap.
3. **Cache → catalog:** Cue export table vs `ALTER TABLE samples`? Deferred to [`WORKBENCH_CATALOG_UNIFICATION_PLAN.md`](WORKBENCH_CATALOG_UNIFICATION_PLAN.md) Phase C.

---

*Refs #117 — planning only; does not close the parent issue.*
