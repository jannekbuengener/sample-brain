# Session Ownership Contract — Live Kit + QML → Native Audio

Status: **completed prerequisite** on `main` (PR [#647](https://github.com/jannekbuengener/sample-brain/pull/647); `src/workbench_session.py`).  
Build-order step 2 is done. Does not authorize Screen-2 UI, Pattern Core, or Sequencer implementation by itself.

Parent: [`PRODUCT_WORKFLOW_CANON.md`](PRODUCT_WORKFLOW_CANON.md) build-order step 2.  
Next: complete sequencer playback with the production PCM cache/decode provider; Screen-2 Channel Rack QML remains HOLD until then.

## Goal

One Workbench session owns:

1. Exactly one authoritative `LiveKitState` (musical kit assignments)
2. One command path from QML intents into that state
3. One native transport/audio path for Live Kit audition (and later sequencer), not the legacy OS preview default

## Historical friction (pre-#647 evidence)

| Issue | Evidence (pre-convergence) |
|-------|----------|
| Dual kit owners (Tk vs QML) | `WorkbenchApp` constructed its own `LiveKitState`; `LiveKitPresenter` constructed another |
| QML bootstrap defaulted to `WorkbenchPreviewPlayer` | `_qml_engine` when no adapter injected |
| Native audition monophonic | `TransportAwarePreview` single `_active_voice_id` — OK for audition; **not** the sequencer owner |

Resolved on `main` by composing one `WorkbenchSession` (`compose_workbench_session`) that shares kit + native audition.

## Target ownership (minimal)

```text
WorkbenchSession (name TBD; Python-owned)
  ├── live_kit: LiveKitState                 # single musical truth
  ├── live_kit_presentation: LiveKitPresentationState
  ├── transport: WorkbenchTransportAdapter   # TempoMap + native engine
  ├── audition: TransportAwarePreview        # monophonic Screen-1 audition only
  └── pattern / sequencer core              # implemented separately; still separate from audition

QML Screen-1 / future Screen-2
  → InteractionAdapter / Presenter
  → mutates WorkbenchSession only
  → never owns kit assignments or audio clock
```

### Rules

1. **Single `LiveKitState` instance** per Workbench process/session. Tk and QML must share it when both are present; QML must not silently create a second kit.
2. **QML remains projection + intent.** Assign/audition/toggle go through the existing adapter style (`Screen1QmlInteractionAdapter` / `LiveKitPresenter` wrapping the **shared** state).
3. **QML production path must inject native preview/transport**, not construct `WorkbenchPreviewPlayer` as the default for producer launches that expose Live Kit audition.
4. **Audition stays monophonic** under `TransportAwarePreview`. Polyphonic pattern playback is a **later** owner (sequencer slice), not this slice.
5. **No kit persistence** in this slice. State remains in-memory; durable refs are a later decision.
6. **No Pattern / Channel Rack UI** in this slice.

## Likely paths (implementation later)

- `src/workbench_live_kit.py` — keep contracts; possibly add session wiring helper only if needed
- `src/workbench_qml.py` — share injected `LiveKitState` / native preview callbacks
- `src/workbench.py` — share kit with QML entry if co-hosted
- `src/workbench_transport_ui.py` / `src/workbench_transport_adapter.py` — reuse, do not expand into sequencer
- Tests under `tests/test_workbench_qml_live_kit_*.py` and transport tests

## Non-goals

- Screen-2 / Channel Rack UI
- Pattern model
- Polyphony / step scheduling
- Kit save/load
- Renaming Live Kit taxonomy
- Mixer / gain FFI
- VST / external DAW

## Acceptance (step 2 — met on `main` via #647)

- [x] One process → one `LiveKitState` observable from QML and Tk paths under test
- [x] QML Live Kit audition uses native `TransportAwarePreview` (or equivalent native callback), not `WorkbenchPreviewPlayer`, on the production Screen-1 path
- [x] Existing Live Kit assign / pending / audition contracts remain green
- [x] No Screen-2 / pattern types introduced

## Next

Pattern Core (#656), the sequencer scheduling seam (#663), and Channel Rack Python core (#667) are on `main`; the production PCM cache/decode provider is the remaining playback prerequisite before Screen-2 QML.
