# Workbench Auto-Metadata Plan (Loop, OneShot, Attack, Cue)

**Status:** Implemented in `src/workbench_auto_metadata.py` (#172 / #173).  
**Parent:** [#117 — workbench usability and library workflow follow-ups](https://github.com/jannekbuengener/sample-brain/issues/117)  
**Blocks:** [#172 — auto loop region](https://github.com/jannekbuengener/sample-brain/issues/172), [#173 — auto attack/cue for OneShot](https://github.com/jannekbuengener/sample-brain/issues/173)  
**Related:** [`WORKBENCH_CUE_METADATA_PLAN.md`](WORKBENCH_CUE_METADATA_PLAN.md), [`WORKBENCH_ATTACK_EDIT_PLAN.md`](WORKBENCH_ATTACK_EDIT_PLAN.md), `src/classify.py`, `src/workbench_library.py`, `src/workbench_attack_suggest.py`

## 1. Problem

After folder analysis, producers want sensible **default cue/loop/attack metadata** without manual clicks:

- **Loop** samples should show a full-file loop region immediately.
- **OneShot** samples should get a detected attack and optional cue at that attack.
- **Manually edited** values must never be silently overwritten on re-analyze or re-open.

Today: classification (`pred_type`) and cue metadata (`workbench_library.db`) are separate. Attack suggestion exists (`suggest_attack_ms`) but is **UI-only** until the user clicks *Vorschlag übernehmen*. Loop/attack fields are user-driven only.

## 2. Safety contract (non-negotiable)

1. **Original audio files are never modified** by auto-metadata.
2. **No catalog.db writes** — auto-metadata targets `workbench_library.db` cache rows only.
3. **Catalog-readonly rows** stay read-only (no auto-write to catalog source).
4. Auto-metadata is **idempotent** and **conservative**: when in doubt, skip write.
5. Re-analysis may refresh analysis columns; cue columns are preserved unless an explicit auto-fill rule applies to **empty** slots only.

## 3. Classification inputs (what we trust today)

Workbench rows expose `pred_type` (primary tag) and `sample_class` (`oneshot` | `loop` from analyze path). Rule-based autotype (`src/classify.py`) assigns:

| `sample_class` | Typical `pred_type` values | Auto-metadata role |
|---|---|---|
| `loop` | `Loop`, `Drum Loop`, `Drone`, … | Loop region candidate |
| `oneshot` | `OneShot`, `Kick`, `Snare`, `HiHat-Closed`, `Impact`, `Drone`, `FX`, … | Attack/cue candidate |

### 3.1 Loop labels (v1)

Treat as **Loop** when `pred_type` is one of:

- `Loop`
- `Drum Loop`

**Exclude** from auto-loop v1: `Drone`, `Pad`, `Atmospheric` — duration may be long but loop bounds are ambiguous without bar detection.

Fallback: if `pred_type` is missing but `sample_class == "loop"`, treat as `Loop`.

### 3.2 OneShot labels (v1)

Treat as **OneShot** when `pred_type` is exactly:

- `OneShot`

**Kick / Snare / HiHat / Impact:** v1 **does not** auto-fill attack/cue — rule tags are heuristic and share duration overlap with loops/perc. Include only after explicit product GO or a dedicated `is_definite_oneshot(pred_type)` gate in code review.

Fallback: if `pred_type` is missing but `sample_class == "oneshot"`, treat as `OneShot`.

## 4. When auto-metadata runs (v1 trigger)

| Event | Auto-loop | Auto-attack/cue | Notes |
|---|---|---|---|
| First analysis write to cache (`analyze_folder_for_workbench`) | ✅ | ✅ | Primary v1 hook |
| Re-analyze same file (cache hit, user forces re-run) | ❌ skip if loop fields set | ❌ skip if attack/cue set | Protect existing metadata |
| Open workbench / load cached rows | ❌ | ❌ | No retroactive backfill in v1 |
| User manual edit | — | — | Sets provenance to manual (see §5) |
| Catalog-readonly row | ❌ | ❌ | Never write |

**Rationale:** v1 applies auto-fill **once at analysis persist time** when metadata slots are still empty. Retroactive backfill across thousands of cached rows is a separate optional maintenance command (out of scope).

## 5. Manual value protection

### 5.1 Per-field provenance (schema v3, shipped #177)

`workbench_library.db` schema v3 adds nullable per-field source columns:

```text
loop_source   TEXT  -- 'detected' | 'manual' | NULL
attack_source TEXT  -- 'detected' | 'manual' | NULL
cue_source    TEXT  -- 'manual' | 'detected' | 'default' (existing)
```

`WORKBENCH_LIBRARY_SCHEMA_VERSION = 3`. Migration is idempotent (`ALTER TABLE` per missing column). Legacy rows keep `loop_source`/`attack_source` as `NULL` (unknown); field-emptiness protection from v1 remains for those rows.

### 5.2 Protection rules (with provenance)

| Field state | Auto-fill allowed? |
|---|---|
| `loop_source == "manual"` | ❌ Never auto-loop |
| `loop_start_ms` **or** `loop_end_ms` is non-NULL | ❌ Never auto-loop (legacy NULL-source rows) |
| `attack_source == "manual"` | ❌ Never auto-attack |
| `attack_ms` is non-NULL | ❌ Never auto-attack (legacy NULL-source rows) |
| `cue_start_ms` is non-NULL **and** `cue_source == "manual"` | ❌ Never auto-cue |
| All target fields NULL / unset | ✅ Auto-fill per §6–§7 |
| `*_source == "detected"` with partial fields | ✅ Fill only still-empty fields (same event) |

**Default cue:** `cue_start_ms = 0` is the implicit default on read when NULL; for auto-fill purposes, treat NULL as empty. Do **not** overwrite `cue_start_ms` when it is `0` and `cue_source == "manual"`.

Auto-metadata sets `loop_source='detected'` / `attack_source='detected'` on write. Manual UI edits set `loop_source='manual'` / `attack_source='manual'`. **Clear actions** (Loop löschen / Attack löschen) also set the corresponding `*_source='manual'` so re-analyze does not restore values the user explicitly removed.

### 5.3 Follow-up (not in #177)

- Re-analyze auto-refresh for rows with `*_source='detected'` only — separate slice after #178 UI
- Retroactive backfill for legacy NULL-source rows — optional maintenance command

## 6. Auto-loop rule (v1)

**Preconditions (all required):**

1. Row classified as Loop per §3.1.
2. `loop_start_ms` and `loop_end_ms` are both NULL.
3. `duration_ms` known and `> 0`.
4. Row is not catalog-readonly.
5. Manual protection per §5.2 does not block.

**Write:**

```text
loop_start_ms = 0
loop_end_ms   = duration_ms   # clamped to sample end
loop_source   = 'detected'
```

**Do not** set `cue_start_ms` in the loop auto-fill slice.

**UI effect:** loop region visible on waveform after cache reload; no original file change.

## 7. Auto-attack / cue rule (v1)

**Preconditions (all required):**

1. Row classified as OneShot per §3.2.
2. `attack_ms` is NULL.
3. `duration_ms` known.
4. Row is not catalog-readonly.
5. Manual protection per §5.2 does not block.

**Write:**

1. Call existing `suggest_attack_ms(path)` (librosa onset heuristic).
2. If suggestion is `None` or confidence is `low` with duration edge cases → **skip** (no write).
3. Set `attack_ms = suggestion.attack_ms`.
4. **Cue (optional):** if `cue_start_ms` is NULL and `cue_source` is not `manual`, set `cue_start_ms = attack_ms`.
5. Set `cue_source = 'detected'` when cue is auto-set; set `attack_source = 'detected'`.

**Do not** auto-set cue when user already has `cue_start_ms` at default 0 with `cue_source = manual` from an explicit Shift+click workflow.

## 8. Implementation hooks (future slices)

| Slice | Module | Function (proposed) |
|---|---|---|
| Loop auto-fill | `workbench_auto_metadata.py` | `apply_auto_loop_metadata(existing, duration_ms=...) -> WorkbenchCueMetadata \| None` |
| OneShot auto-fill | `workbench_auto_metadata.py` | `apply_auto_oneshot_metadata(existing, path, duration_ms=...) -> ...` |
| Persist gate | `workbench_controller.py` `analyze_folder_for_workbench` after `upsert_sample` | `apply_auto_metadata_after_analyze(row)` |

All logic must be **unit-testable** without tkinter. Tests use synthetic WAV in `tmp_path` only.

## 9. Tests (when implementing #172 / #173)

- Loop: `pred_type=Loop`, empty loop fields → full duration region; non-loop → unchanged.
- Loop: existing `loop_start_ms` → unchanged on re-analyze.
- OneShot: empty attack → `attack_ms` set; existing attack → unchanged.
- OneShot: manual `cue_source=manual` with `cue_start_ms` set → attack auto skipped or cue skipped per §5.
- Catalog-readonly row → no writes.
- Missing duration → no crash, no write.
- Short/silent WAV → suggest returns None or 0 without crash.

## 10. Explicit non-goals

- Bar-aligned loop detection / autocorrelation loop finder
- Auto-fill for Kick/Snare/HiHat in v1
- Writing auto-metadata into `catalog.db` or FL export tags
- Retroactive batch backfill command
- DB migration without explicit GO
- CLAP / sqlite-vec / semantic search (#73, #74)
- Changing analysis/classification rules in `classify.py` as part of auto-metadata v1

## 11. Recommended delivery order

1. **This plan** (#171) — ✅ docs-only  
2. **#172** — auto-loop at analyze persist (after plan merge)  
3. **#173** — auto-attack/cue at analyze persist (after #172 or parallel if shared helper)  
4. **Follow-up** — per-field `*_source` migration (#177) — ✅ shipped schema v3
5. **#178** — preview UX for provenance badges — ✅ Workbench shows compact `erkannt` / `manuell` hints for loop/attack/cue via `loop_source`, `attack_source`, `cue_source` (read-only UI; no rule change; no backfill)

## 12. Decision summary (v1 rule card)

```text
LOOP:     pred_type in {Loop, Drum Loop} OR sample_class=loop without contradicting type
          AND loop_* empty → [0, duration_ms], source=detected

ONESHOT:  pred_type == OneShot OR sample_class=oneshot (no Kick/Snare v1)
          AND attack_ms empty → suggest_attack_ms(); optional cue_start_ms=attack_ms
          AND respect manual cue_source

PROTECT:  any set loop field / set attack / manual cue → skip
TRIGGER:  analyze_folder_for_workbench persist only
```

---

*Refs #117, #171, #172, #173, #178. Runtime auto-write at analyze persist only.*

### Preview UX (#178)

The workbench waveform area shows compact German provenance hints when metadata sources are known:

- `detected` → **erkannt**
- `manual` → **manuell**
- `NULL` / unset loop or attack source → hidden (legacy unknown)
- Default cue without user edit → hidden; shown when auto-detected or after explicit cue save

No auto-metadata rule changes and no retroactive backfill in this slice.
