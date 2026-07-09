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

### 5.1 Current schema limitation

`workbench_library.db` stores a single `cue_source` column (`manual` | `detected` | `default`). There are **no per-field source columns** for `loop_start_ms`, `attack_ms`, etc.

Implication: we cannot reliably distinguish “user cleared attack but left loop” vs “attack never set” using `cue_source` alone.

### 5.2 v1 protection rules (no migration)

Use **field emptiness + conservative source flag**:

| Field state | Auto-fill allowed? |
|---|---|
| `loop_start_ms` **or** `loop_end_ms` is non-NULL | ❌ Never auto-loop |
| `attack_ms` is non-NULL | ❌ Never auto-attack |
| `cue_start_ms` is non-NULL **and** `cue_source == "manual"` | ❌ Never auto-cue |
| `cue_source == "manual"` **and** any of loop/attack/cue non-default | ❌ Skip affected auto writes (per-field in v1 impl) |
| All target fields NULL / unset | ✅ Auto-fill per §6–§7 |
| `cue_source == "detected"` with partial fields | ✅ Fill only still-empty fields (same event) |

**Default cue:** `cue_start_ms = 0` is the implicit default on read when NULL; for auto-fill purposes, treat NULL as empty. Do **not** overwrite `cue_start_ms` when it is `0` and `cue_source == "manual"`.

### 5.3 v2 recommendation (before aggressive re-analyze auto-fill)

Add nullable per-field provenance (requires approved DB migration):

```text
loop_source   TEXT  -- 'auto' | 'manual' | NULL
attack_source TEXT
cue_source    TEXT  -- already exists; keep
```

Until migration ships: **#172 / #173 must fail closed** if manual vs auto cannot be determined.

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
cue_source    = 'detected'    # only when no prior manual cue_source=manual
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
5. Set `cue_source = 'detected'`.

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
4. **Follow-up** — per-field `*_source` migration if re-analyze auto-refresh is needed  

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

*Refs #117, #171, #172, #173. Runtime auto-write at analyze persist only.*
