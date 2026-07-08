# Workbench Cue / Loop / Attack Metadata Plan

**Status:** Cue metadata v1 + preview from saved cue + waveform play controls shipped on `main`. Permanent cue-set UX and loop/attack UI follow-ups remain open.  
**Parent:** [#117 — workbench usability and library workflow follow-ups](https://github.com/jannekbuengener/sample-brain/issues/117)  
**Related code:** `src/workbench_library.py`, `src/workbench_waveform.py`, `src/workbench_preview.py`, `src/workbench.py`

## Implementation status (v1)

| Item | Status |
|---|---|
| Schema v2 columns on `samples` | ✅ Shipped |
| Idempotent migration for existing `workbench_library.db` | ✅ Shipped |
| `WorkbenchCueMetadata` + `load_sample_cue` / `save_sample_cue` | ✅ Shipped |
| Read-only cue marker on waveform canvas | ✅ Shipped |
| Interactive cue set / drag | ❌ Follow-up (Shift+click, cue mode, or context menu — not simple left-click) |
| Preview from `cue_start_ms` | ✅ Shipped (temp WAV slice; original unchanged) |
| Waveform play controls | ✅ Shipped (left = play from saved cue; right = temp play at click; no visible Play/Stop buttons) |
| Loop region UI | ❌ Follow-up |

## 1. Problem

Producers need to see and later adjust where a sample **starts**, where the **attack** is, and (for loops) **loop boundaries** — without Sample Brain renaming, trimming, or rewriting the original audio file.

The workbench already ships:

| Capability | Module | Status |
|---|---|---|
| Read-only peak waveform | `workbench_waveform.compute_waveform_envelope` | ✅ Shipped (PR #131) |
| Play / stop preview | `workbench_preview.WorkbenchPreviewPlayer` | ✅ Shipped (PR #129–#130; waveform is primary play surface since waveform play-controls slice) |
| Library cache (analysis) | `workbench_library.db` | ✅ Shipped |

What is missing: **persistent edit points** stored as metadata and drawn on the waveform.

## 2. Safety contract (non-negotiable)

1. **Original audio files are never modified** by workbench cue/loop/attack features.
2. **No automatic rename, move, delete, or export** of source files in the first metadata slices.
3. Cue/loop/attack values are **local metadata** in `~/.sample-brain/workbench_library.db` (or `SAMPLE_BRAIN_WORKBENCH_STATE_DIR`).
4. Any future “bounce trimmed sample” or DAW export is a **separate explicit action** with its own issue/GO.
5. Preview may **start playback at `cue_start_ms`** in memory/player only; it must not write a new file.

## 3. Field model (v1 target)

All times in **milliseconds** from file start (`t=0`), integer or real with ≤1 ms precision.

| Field | Meaning | Required v1 | Notes |
|---|---|---|---|
| `cue_start_ms` | User-facing start / audition point | ✅ | Default `0`; preview may begin here |
| `attack_ms` | Detected or user-set attack peak / onset | Optional v1 | May equal `cue_start_ms` initially |
| `start_offset_ms` | Alias / legacy name | — | Prefer `cue_start_ms`; do not store both |
| `loop_start_ms` | Loop region start | Optional v1 | Only when `duration_class == loop` or user override |
| `loop_end_ms` | Loop region end | Optional v1 | Must be `> loop_start_ms` when set |
| `cue_source` | `manual` \| `detected` \| `default` | ✅ | Provenance for UI and re-analysis |
| `cue_updated_at` | ISO UTC timestamp | ✅ | Last user or detector write |

**Invariants**

- `0 <= cue_start_ms < duration_ms`
- When `loop_end_ms` is set, `loop_start_ms` must be set and `loop_start_ms < loop_end_ms <= duration_ms`
- Clearing loop markers sets both to `NULL`

`duration_ms` is derived at read time from cached analysis or `soundfile` metadata — not duplicated in the cue row unless needed for validation cache.

## 4. Storage: `workbench_library.db` schema v2

Current `samples` table (v1) stores analysis fields only. **v2** adds nullable cue columns on the same row (one row per `original_path` + size/mtime identity):

```sql
-- Planned migration (workbench_library v2)
ALTER TABLE samples ADD COLUMN cue_start_ms REAL;
ALTER TABLE samples ADD COLUMN attack_ms REAL;
ALTER TABLE samples ADD COLUMN loop_start_ms REAL;
ALTER TABLE samples ADD COLUMN loop_end_ms REAL;
ALTER TABLE samples ADD COLUMN cue_source TEXT;
ALTER TABLE samples ADD COLUMN cue_updated_at TEXT;
```

**Versioning:** bump `WORKBENCH_ANALYZER_VERSION` only when analysis outputs change; add separate `WORKBENCH_LIBRARY_SCHEMA_VERSION = 2` (or `user_metadata_version`) so cue migrations do not invalidate analysis cache.

**Invalidation:** cue columns are **not** cleared when `size_bytes` / `mtime_ns` change — user metadata is discarded only when the sample row is deleted (folder remove) or path identity changes. If the file content changes but path stays the same, show a “stale cue” warning in UI (follow-up).

## 5. API sketch (implementation slices)

Planned Python surface in `workbench_library.py` (names indicative):

```python
@dataclass
class SampleCueMetadata:
    cue_start_ms: float | None
    attack_ms: float | None
    loop_start_ms: float | None
    loop_end_ms: float | None
    cue_source: str | None
    cue_updated_at: str | None

def load_sample_cue(original_path: str, ...) -> SampleCueMetadata: ...
def save_sample_cue(original_path: str, cue: SampleCueMetadata, ...) -> None: ...
def default_cue_for_duration(duration_ms: float) -> SampleCueMetadata: ...
```

`WorkbenchRow` / `CachedWorkbenchRow` may expose optional `cue: SampleCueMetadata` for UI binding in `workbench_cue_metadata_v1`.

## 6. UI phases (incremental)

| Phase | Scope | Depends on |
|---|---|---|
| **Plan** (this doc) | Fields, safety, schema | — |
| **v1 read** | Show default `cue_start_ms=0`; draw vertical marker on waveform | ✅ Shipped |
| **v1 edit** | ~~Click on waveform to set `cue_start_ms`~~ superseded by waveform play controls; permanent cue-set UX follow-up | ✅ Shipped then superseded |
| **v1 preview** | Preview starts at `cue_start_ms` | ✅ Shipped (temp slice only; original files unchanged) |
| **v1 waveform play** | Left-click play from saved cue; right-click temp play at click position; no cue write on click | ✅ Shipped |
| **v2 detect** | Optional `attack_ms` via librosa onset (analysis thread only) | analyze / workbench analyze path |
| **v2 loop** | Loop region handles on waveform for loops only | v1 edit |
| **Later** | Export trimmed copy, DAW drag with offset | product decision + #93 |

**Waveform panel today:** peak envelope + saved cue marker; left-click plays from saved cue; right-click plays temporarily from click position; double-click row and Space still toggle preview; no visible Play/Stop buttons in detail header.

## 7. Detection heuristics (future, non-blocking)

For `cue_source=detected` (optional slice, not v1):

- **Attack / onset:** librosa `onset.onset_strength` + `onset.onset_detect` on mono float32 (already used in pipeline).
- **Leading silence:** first frame above noise floor (e.g. −60 dBFS relative to peak).
- **Loop bounds:** defer — requires bar/grid or autocorrelation; do not block metadata v1.

Detector output is **suggestion only**; user override sets `cue_source=manual`.

## 8. Tests (when implementing v1)

- Unit: `default_cue_for_duration`, validation of loop invariants, save/load round-trip (temp DB).
- Unit: cue persistence survives re-analysis (analysis columns update, cue columns preserved).
- No committed audio; synthetic WAV in `tmp_path` only.
- No real playback in CI for cue-offset preview.

## 9. Explicit non-goals (this plan)

- Writing cue points into `catalog.db` / FL export tags
- Cross-folder cue sync
- Waveform pixel cache in DB (recompute envelope on demand for now)
- Pause / playhead tracking (separate preview slice)
- sqlite-vec, CLAP, VST (#73, #74, #93 tracks)

## 10. Recommended implementation order

1. ~~`workbench_cue_metadata_v1` — schema v2 migration + load/save + read-only markers at 0 ms~~ ✅  
2. ~~`workbench_cue_waveform_edit_v1` — click to set `cue_start_ms`~~ ✅ (superseded by waveform play controls; permanent cue-set UX is follow-up)  
3. ~~`workbench_preview_cue_offset` — preview from cue (platform limits documented)~~ ✅  
4. ~~`workbench_waveform_play_controls` — waveform as play surface; left/right click playback~~ ✅  
5. `workbench_cue_set_ux` — permanent cue set (Shift+click, cue mode, or context menu)  
6. `workbench_attack_detect_suggest` — optional detector → `attack_ms`  
7. `workbench_loop_metadata_v1` — loop region fields + UI  

## 11. Docs sync checklist

When cue v1 ships, update:

- `knowledge/CURRENT_STATUS.md`
- `docs/ISSUE_BACKLOG.md` (issue 22 partial)
- `docs/PRODUCT_REQUIREMENTS.md` §5.1 workbench paragraph
- This plan → mark sections **Implemented** with PR links

---

*Refs #117 — planning only; does not close the parent issue.*
