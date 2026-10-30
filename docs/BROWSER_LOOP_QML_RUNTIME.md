# Browser Loop QML Runtime (#1285)

## Authority

Python/core remains authoritative for persistent Loop ownership, real-downbeat extent, source phase, MASTER/SYNC state, reduced capability and audio lifecycle. QML projects the immutable `BrowserLoopProjectionSnapshot`, emits typed intent, and owns only presentation state required for inline/sticky handoff. No QML musical clock, Loop owner, bar counter authority or per-delegate playback timer was introduced.

The design authority is MagicPath revision `466704025803440128`. The audio/runtime authority is #1284, merged at `85b026d05550c732249eb6d62fa7ed94392396a7` with exit `BROWSER_LOOP_AUDIO_RUNTIME_PASS`.

## Projection contract

The Screen-1 interaction bridge exposes the Python-owned Loop snapshot: active owner identity, owner name/path, normalized bar positions, authoritative source-phase progress, playback availability and reduced-capability reason. The existing playback `FrameAnimation` is shared by preview and Loop projection; `refreshPlaybackProjection()` refreshes both without creating a second transport clock. `refreshPreviewPlayback()` remains a compatibility wrapper.

Browser presentation enforces `INLINE XOR STICKY`. A visible owner is rendered as the expanded inline Loop surface. An offscreen or filtered owner is represented by one subordinate top/bottom sticky proxy. Delegate pooling/reuse clears only presentation residue; Python Loop ownership persists. Context target remains independent from selection/audition.

## Validation evidence

Final local validation head: `8f69df536ea6921b47159f998e6808285d25f592`.

Focused Browser Loop/QML/audio authority suite:

```text
123 passed, 1 warning in 21.48s
```

Additional Browser chrome / compact-density / playlist-surface regression suite after updating stale source-shape assertions for the expanded delegate:

```text
40 passed, 1 warning in 4.82s
```

The warning is the expected test-host warning that `samplebrain_audio` is unavailable in this isolated QML run. Windows emitted `0x8001010d` in the known Qt UIA path; per `docs/WINDOWS_REGRESSION_HARNESS.md` this exact constellation is a proven non-terminating upstream Qt diagnostic and the test process still exited successfully.

Deterministic QML specialist scan:

```json
{"activated": true, "findings": [], "verdict": "PASS"}
```

Semantic review found no QML shadow authority, delegate identity used as product authority, binding-breaking geometry assignment, timer-as-transport, duplicate command feedback, or high-frequency full-model scan in the #1285 surface.

Windows exact-head evidence driver: `tools/screen1_browser_loop_1285_evidence.py`. It uses synthetic row identities only and writes captures/JSON outside the repository. Fresh processes passed at all required scales:

| Qt scale | Result | Checks |
| --- | --- | --- |
| 1.00 / 100% | PASS | 14/14 |
| 1.25 / 125% | PASS | 14/14 |
| 1.50 / 150% | PASS | 14/14 |

Each run proves inline grid/playhead, different-row audition without Loop mutation, sticky top, return-to-inline, atomic replacement + sticky bottom, hidden-owner persistence under filtering, context-target coexistence, global SYNC authority, reduced-capability fail-closed behavior, reduced-motion truth, hover coexistence, narrow-width geometry and LOOP OFF clearing only the persistent role. Evidence output is external under `D:/Temp/sb-1285-evidence/` and is intentionally not committed.

A broad ad-hoc glob over every test filename containing `qml|browser_loop|preview_playhead` was not used as acceptance evidence: it surfaced stale source-shape assertions and then entered a long-running unrelated path. The directly relevant regressions were isolated, repaired as test-shape maintenance, and rerun green above. Repository-required CI remains the authoritative broad gate before merge.

## Exit target

Local evidence supports `BROWSER_LOOP_QML_RUNTIME_PASS` subject to repository CI/review and live merge verification. Issue #1285 must not be closed until the PR is merged and exact-head live evidence is reconciled.
