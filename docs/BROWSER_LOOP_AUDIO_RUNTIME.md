# Browser Loop Audio Runtime (#1284)

**Status:** ACTIVE — domain/audio authority for single persistent Browser Loop  
**Exit:** `BROWSER_LOOP_AUDIO_RUNTIME_PASS`  
**Frozen transport contract:** #1282  
**Design gate:** closed #1283 (`BROWSER_LOOP_DESIGN_APPROVED`, MagicPath `466704025803440128`)  
**QML projection consumer:** #1285 (not implemented here)

## Roles

| Role | Owner | Lifetime |
|---|---|---|
| MASTER tempo/grid/phase | `SessionTransport` / `TempoMap` via `WorkbenchTransportAdapter` | session |
| Transient Browser audition | `TransportAwarePreview` | click-scoped |
| Persistent Browser Loop | `BrowserLoopOwner` (`src/browser_loop_playback.py`) | until LOOP OFF / atomic replace |

Audition and Loop are separate roles. Click replaces audition only. LOOP OFF clears Loop only. Scroll emits zero audio mutation.

## Musical extent

```text
WorkbenchRow.details.beat_grid.downbeats
→ source_edit_grid_from_details() / load_source_downbeats()
→ browser_loop_extent_from_downbeats()
```

For reliable `d[0..k]`:

- `source_start_frame = d[0]`
- `source_end_frame_exclusive = d[k]`
- `bar_count = k`

Tail after the final downbeat is outside the Loop. No BPM×seconds, raw file-end, or synthetic terminals.

## Canonical Python seams

```text
BrowserLoopOwner.loop_on(row) / loop_off() / tick() / on_sync_changed() / on_master_bpm_changed()
Screen1QmlInteractionAdapter.request_loop_on_for_row(row)
Screen1QmlInteractionAdapter.request_loop_off()
Screen1QmlInteractionAdapter.request_context_loop_on()   # uses sample_context_target
Screen1QmlInteractionAdapter.request_context_loop_off()
```

Context actions must reuse `sample_context_target` and must not re-resolve a virtualized delegate index.

## SYNC

- **OFF:** source/original rate; independent local clocks; restart at musical extent boundary.
- **ON:** both roles use MASTER tempo/grid/phase; Loop length `L` is the comparison cycle; audition enters at current MASTER comparison phase with deterministic modulo mapping into audition extent `A`.
- **OFF→ON:** re-anchor at transition engine/session frame (bounded de-click).
- **ON→OFF:** keep current source phase at rate 1.0.

Fail closed when downbeats are missing (LOOP) or BPM is invalid under SYNC. Never silently play unsynced while SYNC is asserted.

## Windows native evidence

```text
python tools/browser_loop_windows_runtime_evidence.py --work-dir %TEMP%\sb-1284-evidence
```

Requires a loadable `samplebrain_audio` native library under the trusted search paths.
Synthetic WAVs are generated at runtime and must not be committed.
