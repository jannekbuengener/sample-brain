# Browser Loop QML Runtime (#1285) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use `sample-brain-qml-component-test` for component coverage, `sample-brain-qml-test-run` to execute/classify QML tests, `sample-brain-qml-review` before completion, and `sample-brain-qml-profiler` only when a measurable performance concern exists.

**Goal:** Deliver the production Screen-1 Browser Loop projection for #1285: one authoritative persistent Loop owner appears as a full-width inline Loop view while visible and as one subordinate top/bottom sticky proxy while offscreen/filtered, consuming #1284 Python/audio truth without creating QML musical authority.

**Architecture:** Keep `BrowserLoopOwner` (#1284) as the sole Loop/runtime authority. Add one immutable Python-owned `BrowserLoopProjectionSnapshot` in the QML adapter layer, derived on demand from `BrowserLoopOwner`; expose that snapshot through the existing interaction bridge and refresh it through the existing single `FrameAnimation` playback-refresh path. QML owns only representation (inline vs sticky, visibility edge, transition presentation, context-menu intent). It never owns Loop identity, playback phase, bar count, reduced capability, SYNC truth, or a musical timer.

**Tech Stack:** Python 3.12, PySide6 6.12 / Qt Quick embedded `QML_SOURCE`, pytest 9.x, existing `_qml_engine` / `_settle_qml_frame` / Screen-1 visual fixture, `BrowserLoopOwner`, `SessionTransport`/`TempoMap`, existing QML specialist skills.

**Spec:** GitHub #1285 + closed #1283 (`BROWSER_LOOP_DESIGN_APPROVED`, MagicPath rev `466704025803440128`) + closed #1284 (`BROWSER_LOOP_AUDIO_RUNTIME_PASS`, merge `85b026d05550c732249eb6d62fa7ed94392396a7`) + `docs/BROWSER_LOOP_AUDIO_RUNTIME.md` + `docs/WORKBENCH_SAMPLE_CONTEXT_MENU_CONTRACT.md` + `docs/WORKBENCH_PREVIEW_PLAYHEAD_CONTRACT.md` + `docs/WORKBENCH_DISPLAY_PREFERENCES.md`.

## Global Constraints

- Work only in external worktree `D:/Temp/sample-brain-1285-qml-runtime` on `feat/1285-browser-loop-qml-runtime`; do not modify the dirty main checkout.
- Baseline commit is `85b026d05550c732249eb6d62fa7ed94392396a7` unless live `origin/main` advances before implementation; re-check before first product edit.
- Python/Core/native runtime owns Loop identity/state, real-downbeat extent, phase, MASTER/SYNC truth, reduced-capability reason and audio lifecycle.
- QML owns projection + typed user intent only. No QML Loop owner, musical clock, bar counter authority, source-phase mutation, or per-delegate playback timer.
- Exactly one persistent Loop owner. UI invariant is `INLINE XOR STICKY`; neither representation creates a second actionable owner.
- `sample_context_target` remains the sole context-target authority. Right-click B must not select/audition B when selection/audition is A.
- `browserList` remains virtualized with `reuseItems: true`; no offscreen delegate is kept alive for Sticky.
- Scroll/filter/search never mutates Loop ownership or audio.
- Existing #1281 waveform-only hover and edge immersion remain; Loop presentation visually outranks ordinary hover.
- Reduced capability is fail-closed and projected from #1284; no QML fallback timing.
- Motion preference `off` means no playback `FrameAnimation` work for Loop/preview motion; `reduced` preserves truthful state without animation-dependent meaning.
- No new audio engine, time-stretch backend, analyzer, multi-loop state, mixer, Arrangement/Pattern timeline, global SYNC control or Browser IA redesign.
- No private samples, DBs, indexes, caches, credentials, machine-local absolute paths, or screenshot evidence containing private data in commits.
- TDD for product changes: failing test -> verify RED -> minimal implementation -> verify GREEN -> refactor.
- No direct push to `main`; final implementation requires PR/review/CI/Windows acceptance before merge.

## Verified Baseline

External worktree is clean at `85b026d05550c732249eb6d62fa7ed94392396a7`.

Focused Windows QML/Loop baseline command:

```powershell
$env:QT_QPA_PLATFORM='windows'
$env:PYTHONFAULTHANDLER='1'
$env:PYTHONPYCACHEPREFIX='D:/Temp/sb-1285-baseline-pycache'
py -3.12 -m pytest `
  tests/test_browser_loop_context_target.py `
  tests/test_workbench_qml_sample_context_menu_839.py `
  tests/test_qml_component_context_menu_pattern_1305.py `
  tests/test_workbench_qml_browser_hover_1281.py `
  tests/test_workbench_preview_playhead_contract.py `
  tests/test_workbench_qml_browser_waveform_viewport.py `
  -q -p no:cacheprovider `
  --basetemp 'D:/Temp/sb-1285-baseline-pytest'
```

Verified result: **55 passed, exit 0**. The documented non-terminating Windows Qt UIA diagnostic `0x8001010d` appeared during visible-window testing and is classified by `docs/WINDOWS_TEST_HARNESS.md` as upstream Qt for that exact constellation. Native `samplebrain_audio` was not loaded in this QML-only baseline; #1284 native audio acceptance is already delivered separately.

## File Structure

### Create

- `tests/test_workbench_qml_browser_loop_1285.py` — Python projection/bridge contract plus static QML invariants for #1285.
- `tests/test_qml_component_browser_loop_1285.py` — real QML pointer/scroll/filter/virtualization/handoff coverage using the existing `_qml_engine` harness.
- `tools/screen1_browser_loop_1285_evidence.py` — thin exact-head Windows visual/runtime scenario driver using existing Screen-1/QML harnesses; not a second framework.
- `docs/BROWSER_LOOP_QML_RUNTIME.md` — durable Python->QML projection contract and acceptance evidence for downstream #1220.

### Modify

- `src/workbench_qml.py` — immutable Loop projection snapshot, adapter/bridge properties and intents, one shared playback refresh path, third context action, inline/sticky QML, geometry-aware waveform prefetch for variable owner-row height.
- `tests/test_qml_component_context_menu_pattern_1305.py` — extend canonical three-action context component pattern where needed without duplicating #1285-specific scenarios.
- `tests/test_workbench_preview_playhead_contract.py` — prove one bounded refresh driver covers preview + Loop and no per-delegate musical timers appear.
- `tests/test_workbench_qml_browser_hover_1281.py` — regression: Loop owner outranks ordinary hover while existing waveform-only hover remains unchanged for non-owner rows.
- `tests/test_workbench_qml_browser_waveform_viewport.py` — replace fixed-row-height viewport arithmetic contract with geometry-aware visible-index discovery compatible with one expanded Loop row.
- `docs/WORKBENCH_SAMPLE_CONTEXT_MENU_CONTRACT.md` — record the shipped third action/intent projection while preserving Python context-target authority.
- `docs/WORKBENCH_PREVIEW_PLAYHEAD_CONTRACT.md` — document shared bounded playback refresh for transient preview + persistent Loop projection.

### Read/Reuse; Do Not Fork

- `src/browser_loop_playback.py` — authoritative `BrowserLoopOwner` and `BrowserLoopExtent`.
- `src/workbench_session.py` — one session-owned `BrowserLoopOwner` bound to `Screen1QmlInteractionAdapter`.
- `src/workbench_transport_preview.py` — `PreviewPlaybackSnapshot` pattern and current preview telemetry.
- `src/workbench_transport_adapter.py` / `src/session_grid.py` — MASTER/SYNC/time authority.
- `tests/test_browser_loop_playback.py` / `tests/test_browser_loop_context_target.py` — #1284 authority tests; do not reimplement their domain cases in QML.
- `docs/skills/sample-brain-qml-component-test/SKILL.md`.
- `docs/skills/sample-brain-qml-test-run/SKILL.md`.
- `docs/skills/sample-brain-qml-review/SKILL.md`.
- `docs/skills/sample-brain-qml-profiler/SKILL.md` when profiling is actually needed.

## Locked Interfaces

### Python-owned read-only projection

Add in `src/workbench_qml.py` near existing renderer projections:

```python
@dataclass(frozen=True)
class BrowserLoopProjectionSnapshot:
    active: bool
    owner_path: str
    owner_name: str
    progress: float
    bar_count: int
    bar_positions: tuple[float, ...]
    reduced_capability_reason: str
    playback_available: bool

    @classmethod
    def idle(cls) -> "BrowserLoopProjectionSnapshot": ...
```

Semantics:

- `owner_path`/`owner_name` come from `BrowserLoopOwner.owner_row` only.
- `bar_count` and `bar_positions` derive from `BrowserLoopOwner.extent`; `bar_positions` are normalized `[0,1]` positions from the authoritative real-downbeat frames, including both extent endpoints.
- `progress` derives from `BrowserLoopOwner.current_source_phase_frame()` normalized to the authoritative extent and is clamped `[0,1)`; QML never advances it locally.
- `reduced_capability_reason` comes directly from `BrowserLoopOwner.reduced_capability_reason`.
- `playback_available` is `active` with no reduced-capability reason; owner identity may remain active while fail-closed audio is unavailable.
- `idle()` contains no owner/path/grid/reason and `progress=0.0`.
- Do not duplicate `syncEnabled` in this snapshot; QML already projects authoritative `tempoSyncModel.syncEnabled`.

### Adapter projection seams

Add to `Screen1QmlInteractionAdapter`:

```python
def browser_loop_projection_snapshot(self) -> BrowserLoopProjectionSnapshot: ...
def refresh_browser_loop_projection(self) -> BrowserLoopProjectionSnapshot: ...
def request_context_loop_toggle(self) -> object: ...
```

Rules:

- Snapshot is derived from the currently bound `_browser_loop`; no second state owner/cache may survive an authoritative owner change.
- `request_context_loop_toggle()` reads the existing `sample_context_target` exactly once. If target is current authoritative owner, route through `request_loop_off()`; otherwise route through `request_loop_on_for_row(target)`. Do not resolve the delegate index again.
- Rejected ON leaves the old authoritative owner unchanged and returns the #1284 result; do not optimistically mutate QML projection.
- Existing explicit `request_context_loop_on/off()` remain compatible for Python callers/tests.

### QML interaction bridge

Expose notifyable read-only properties backed by the snapshot:

```text
browserLoopActive: bool
browserLoopOwnerPath: str
browserLoopOwnerName: str
browserLoopProgress: real
browserLoopBarCount: int
browserLoopBarPositions: var/list
browserLoopReducedCapabilityReason: str
browserLoopPlaybackAvailable: bool
contextTargetIsLoopOwner: bool
```

Add typed slots:

```text
contextLoopToggle()
refreshPlaybackProjection()
```

`refreshPlaybackProjection()` refreshes preview telemetry and Loop projection in one bridge cycle and emits one `state_changed`. Keep `refreshPreviewPlayback()` as a compatibility wrapper until existing callers/tests are migrated; do not create a second FrameAnimation.

## Review Focus

1. **Variable-height owner row corrupts viewport math.** Existing `contentY / rowHeight` prefetch becomes wrong when a Loop row above/inside the viewport is expanded. Pin this to Task 3 with a geometry-aware `indexAt`/visible-index regression.
2. **Virtualized delegate identity leaks into Loop authority.** Pool/reuse/filter may recycle an old owner delegate. Pin to Task 5 with real `reuseItems` component tests and owner-path assertions against Python state.
3. **High-frequency playback refresh accidentally becomes O(rows) or per-delegate Python chatter.** Pin to Tasks 1/4/6: one global snapshot refresh, no model scan in `FrameAnimation`, no delegate Timer, profiler only if measurements show a hotspot.
4. **Sticky/inline boundary exposes two actionable owners or flickers during row expansion/rapid scroll.** Pin to Task 5 with repeated top/bottom crossing and `INLINE XOR STICKY` assertions.
5. **Context LOOP action mutates selection/audition or lies on rejected replacement.** Pin to Task 2 with real right-click/QML action tests and a rejected #1284 result retaining selection, audition and prior owner.

---

### Task 1: Python-owned Loop projection snapshot and bridge contract

**Files:**
- Modify: `src/workbench_qml.py` (`QmlBrowserRow`/projection declarations; `Screen1QmlInteractionAdapter`; interaction bridge near preview properties)
- Create/Test: `tests/test_workbench_qml_browser_loop_1285.py`

**Interfaces:**
- Consumes: `BrowserLoopOwner.owner_row`, `.extent`, `.current_source_phase_frame()`, `.reduced_capability_reason`, existing `request_loop_on_for_row` / `request_loop_off`.
- Produces: `BrowserLoopProjectionSnapshot`, `browser_loop_projection_snapshot()`, `refresh_browser_loop_projection()`, bridge `browserLoop*` properties, `refreshPlaybackProjection()`.

- [ ] **Step 1: Write failing snapshot tests.** Cover idle/unbound, active owner identity, normalized real-downbeat bar positions, source-phase progress, reduced-capability owner-preserved state, and no duplicated SYNC field.
- [ ] **Step 2: Verify RED.**

```powershell
py -3.12 -m pytest tests/test_workbench_qml_browser_loop_1285.py -q -p no:cacheprovider --basetemp D:/Temp/sb-1285-t1-red
```

Expected: collection succeeds and fails because `BrowserLoopProjectionSnapshot` / `browserLoop*` projection is missing.

- [ ] **Step 3: Implement `BrowserLoopProjectionSnapshot` and adapter derivation.** Derive all values from the bound #1284 owner; no QML-facing musical mutation API.
- [ ] **Step 4: Add bridge properties and `refreshPlaybackProjection()`.** Reuse the existing `state_changed` notification; preserve `refreshPreviewPlayback()` as a wrapper.
- [ ] **Step 5: Verify GREEN plus #1284 authority regressions.**

```powershell
py -3.12 -m pytest tests/test_workbench_qml_browser_loop_1285.py tests/test_browser_loop_playback.py tests/test_browser_loop_context_target.py -q -p no:cacheprovider --basetemp D:/Temp/sb-1285-t1-green
```

- [ ] **Step 6: Refactor only if green.** Keep snapshot derivation small and side-effect free; avoid per-property native calls by reading one snapshot per bridge refresh.
- [ ] **Step 7: Commit.** `feat(#1285): project authoritative Browser Loop state to QML`

---

### Task 2: Canonical context menu gains LOOP ON/OFF without selection/audition mutation

**Files:**
- Modify: `src/workbench_qml.py` (adapter toggle seam, interaction bridge slot, `sampleContextMenu`)
- Modify/Test: `tests/test_qml_component_context_menu_pattern_1305.py`
- Modify/Test: `tests/test_workbench_qml_browser_loop_1285.py`
- Modify: `docs/WORKBENCH_SAMPLE_CONTEXT_MENU_CONTRACT.md`

**Interfaces:**
- Consumes: `sample_context_target`, `request_loop_on_for_row`, `request_loop_off`, Task 1 owner projection.
- Produces: `request_context_loop_toggle()`, QML `contextLoopToggle()`, third context action with truthful `LOOP ON`/`LOOP OFF` label.

- [ ] **Step 1: Write failing Python contract tests.** Cases: selection/audition A + context B -> ON B; context current owner -> OFF; rejected B replacement preserves old owner; no target -> no command.
- [ ] **Step 2: Write failing QML component tests using real right-click/keyboard/Accessible paths.** Assert three actions, exactly-once dispatch, selection unchanged, no preview caused by open, focus navigation spans indices `0..2`, Escape restores browser focus.
- [ ] **Step 3: Verify RED with `sample-brain-qml-test-run` conventions.**
- [ ] **Step 4: Implement the canonical toggle seam in Python.** Do not derive owner truth from QML or a delegate index.
- [ ] **Step 5: Add third Popup action.** Update `focusedAction`, hint IDs/clears, keyboard clamp, accessibility and menu geometry. Replace fixed `height - 96` clamp assumption with Popup/content-derived geometry so the third row cannot detach/clip.
- [ ] **Step 6: On rejected LOOP ON, keep projection authoritative.** Surface the returned failure/reason through a small presentation status; do not fake owner replacement.
- [ ] **Step 7: Verify GREEN and existing Add/Harmonic context regressions.**

```powershell
py -3.12 -m pytest tests/test_qml_component_context_menu_pattern_1305.py tests/test_workbench_qml_sample_context_menu_839.py tests/test_workbench_qml_context_add_to_kit_840.py tests/test_workbench_qml_context_harmonic_matches_843.py tests/test_browser_loop_context_target.py tests/test_workbench_qml_browser_loop_1285.py -q -p no:cacheprovider --basetemp D:/Temp/sb-1285-t2-green
```

- [ ] **Step 8: Commit.** `feat(#1285): add target-bound Browser Loop context action`

---

### Task 3: Full-width inline owner row and geometry-aware waveform viewport

**Files:**
- Modify: `src/workbench_qml.py` (`browserList`, delegate layout, waveform viewport request logic)
- Modify/Test: `tests/test_workbench_qml_browser_loop_1285.py`
- Modify/Test: `tests/test_workbench_qml_browser_waveform_viewport.py`
- Modify/Test: `tests/test_workbench_qml_browser_hover_1281.py`

**Interfaces:**
- Consumes: Task 1 `browserLoopOwnerPath`, `browserLoopBarPositions`, `browserLoopProgress`, reduced-capability state; existing `modelData.path` and waveform envelope.
- Produces: presentation-only `isLoopOwner` binding and one expanded inline Loop surface rooted to the existing logical row.

- [ ] **Step 1: Write failing static/projection tests.** Require `isLoopOwner` from authoritative owner path, larger owner-row height, nearly full Browser-width Loop waveform/grid surface, normal metadata recession, ordinary rows unchanged, no Arrangement vocabulary/controls.
- [ ] **Step 2: Write failing viewport regression.** Build variable-height owner rows and prove waveform request range comes from actual visible ListView geometry, not `contentY / fixedRowHeight` arithmetic.
- [ ] **Step 3: Verify RED.**
- [ ] **Step 4: Implement owner-height as a binding, not an imperative geometry assignment.** Do not animate layout height; use opacity/transform for optional handoff polish to avoid scroll-feedback oscillation.
- [ ] **Step 5: Implement the full inline surface.** Reuse the row's already projected waveform; draw static authoritative bar/grid positions from Task 1; project the playhead separately. Keep Sample Name/Loop identity quiet; hide/recede BPM/Key/Length/Type only for the owner row.
- [ ] **Step 6: Migrate `requestVisibleWaveforms()` to geometry-aware visible index discovery.** Use ListView `indexAt`/equivalent actual delegate geometry with bounded prefetch margin; handle top/bottom when `indexAt` returns `-1`. Do not scan the full model on every contentY tick.
- [ ] **Step 7: Make hover subordinate to owner.** Owner waveform must not receive ordinary #1281 scale/luminance; non-owner rows retain existing primary/±1 hover behavior.
- [ ] **Step 8: Verify GREEN.** Run Task 3 files plus Browser chrome/compact-density regressions.
- [ ] **Step 9: Commit.** `feat(#1285): render full-width inline Browser Loop owner`

---

### Task 4: One bounded authoritative Loop playhead/grid refresh path

**Files:**
- Modify: `src/workbench_qml.py` (root playback driver, inline/sticky progress binding)
- Modify/Test: `tests/test_workbench_preview_playhead_contract.py`
- Modify/Test: `tests/test_workbench_qml_browser_loop_1285.py`
- Modify: `docs/WORKBENCH_PREVIEW_PLAYHEAD_CONTRACT.md`

**Interfaces:**
- Consumes: Task 1 `refreshPlaybackProjection()` and `browserLoopProgress`; existing preview snapshot/driver and `waveformMotionMode`.
- Produces: exactly one global playback presentation driver for whichever authoritative playhead(s) are active.

- [ ] **Step 1: Write failing tests.** Require one `FrameAnimation`, driver armed by preview OR active Loop when motion is not `off`, one bridge refresh per frame, no `Timer` inside Browser delegate/Sticky, no QML arithmetic advancing Loop phase, and Loop playhead x bound to authoritative `browserLoopProgress`.
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Replace preview-only driver call with `refreshPlaybackProjection()`.** Keep compatibility wrapper for old tests/callers. The driver must stop when both preview and Loop motion are inactive or motion mode is `off`.
- [ ] **Step 4: Render bar/grid lines from `browserLoopBarPositions`.** These are static extent coordinates; they are not a clock.
- [ ] **Step 5: Reduced motion.** `reduced` may remove transition animation but still projects authoritative phase; `off` removes moving playhead/FrameAnimation work according to display preference contract.
- [ ] **Step 6: Verify GREEN.**

```powershell
py -3.12 -m pytest tests/test_workbench_preview_playhead_contract.py tests/test_workbench_display_preferences_contract.py tests/test_workbench_qml_browser_loop_1285.py -q -p no:cacheprovider --basetemp D:/Temp/sb-1285-t4-green
```

- [ ] **Step 7: Commit.** `feat(#1285): project Loop phase through shared playback refresh`

---

### Task 5: Bidirectional Sticky, hidden-owner persistence and deterministic handoff

**Files:**
- Modify: `src/workbench_qml.py` (`browserList` presentation state + one sticky visual inside sample viewport)
- Create/Test: `tests/test_qml_component_browser_loop_1285.py`
- Modify/Test: `tests/test_workbench_qml_browser_loop_1285.py`

**Interfaces:**
- Consumes: Python owner path/snapshot from Task 1; actual ListView visibility/geometry; Task 3 inline owner binding.
- Produces: presentation-only sticky edge (`top|bottom|none`) and strict `INLINE XOR STICKY` representation.

- [ ] **Step 1: Design the component-test block using `sample-brain-qml-component-test`.** Record authority, real QML events, observable assertions, wait strategy and virtualization behavior before writing tests.
- [ ] **Step 2: Write failing component tests with enough synthetic Browser rows to recycle delegates.** Cases: owner visible -> inline only; scroll owner above -> sticky top; below -> sticky bottom; return -> inline once; rapid crossing -> never both; pooled/reused delegates do not inherit owner presentation.
- [ ] **Step 3: Add failing filter/search tests.** Hide owner via authoritative Browser projection; owner identity stays Python-owned; Sticky remains; clearing filter restores inline exactly once.
- [ ] **Step 4: Verify RED using real Windows QML runner.**
- [ ] **Step 5: Implement one non-actionable Sticky under `browserListViewport`.** It may use owner name, authoritative grid/progress and already available presentation data; it must not decode an offscreen waveform or retain an owner delegate.
- [ ] **Step 6: Implement presentation-only edge memory.** Determine top/bottom from actual owner delegate exit geometry while materialized; when filter removes the row, preserve the last truthful presentation edge. Do not store product owner identity in this state.
- [ ] **Step 7: Guard high-frequency paths.** Owner-index/edge resolution runs on owner/model/visibility/scroll-boundary changes, not as a full-model scan from every playback `FrameAnimation` tick.
- [ ] **Step 8: Ensure `ListView.onPooled/onReused` clears only delegate presentation residue.** It must never clear or replace Python Loop ownership.
- [ ] **Step 9: Verify GREEN plus #1281 runtime reuse tests.**
- [ ] **Step 10: Commit.** `feat(#1285): add deterministic bidirectional Loop sticky handoff`

---

### Task 6: QML specialist review, measured performance and Windows visual/runtime acceptance

**Files:**
- Create: `tools/screen1_browser_loop_1285_evidence.py`
- Create/Modify: `docs/BROWSER_LOOP_QML_RUNTIME.md`
- No product change unless evidence finds a reproducible in-scope defect.

**Interfaces:**
- Consumes: completed Tasks 1–5, final MagicPath rev `466704025803440128`, existing Screen-1 fixture/_qml_engine.
- Produces: sanitized repeatable evidence for #1285 and #1269.

- [ ] **Step 1: Run focused QML/component suite with `sample-brain-qml-test-run`.** Classify any nonzero result by harness/load/behavior/bridge/platform; do not patch blindly.
- [ ] **Step 2: Run deterministic QML review helper and semantic review.**

```powershell
py -3.12 docs/skills/sample-brain-qml-review/scripts/qml_review_scan.py --json src/workbench_qml.py tests/test_qml_component_browser_loop_1285.py tests/test_workbench_qml_browser_loop_1285.py
```

Review specifically for delegate identity authority, binding breaks, QML shadow authority, stale pooled state, feedback/double intents, high-frequency Python chatter and Timer-as-transport. Material findings are HOLD until repaired/tested.

- [ ] **Step 3: Measure before performance repair.** Inspect delegate creation count, rapid scroll/Sticky crossing, bridge refresh calls and row relayout. Only if evidence shows a hotspot, invoke `sample-brain-qml-profiler`; no speculative optimization.
- [ ] **Step 4: Implement the thin Windows evidence driver.** Reuse existing Screen-1 fixture/QML engine and synthetic/repo-safe row identities. Capture/check states: inline owner, grid/playhead, different-row audition, top/bottom Sticky, return, filter hidden owner, replacement, context coexistence, LOOP OFF, SYNC on/off projection, reduced capability, hover coexistence, reduced motion, narrow Browser width.
- [ ] **Step 5: Exercise Windows DPI 100/125/150 in separate fresh processes.** The driver must set the Qt scale environment before constructing `QApplication`; never mutate scale inside a running Qt process. Evidence path is external, e.g. `D:/Temp/sb-1285-evidence/<scale>/`; do not commit captures.
- [ ] **Step 6: Compare exact-head runtime against MagicPath rev `466704025803440128`.** Evaluate hierarchy/geometry/state ownership, not prototype-only behavior that conflicts with repo contracts. No private path/sample data in screenshots/logs.
- [ ] **Step 7: Run broad relevant regression suite.** At minimum #1285 tests + #1281 hover + context-menu + preview playhead + Browser waveform/virtualization + #1284 loop authority + Screen-1 QML suite. Then run repo-required broad pytest/lint/format/type commands from current live repo instructions.
- [ ] **Step 8: Document evidence in `docs/BROWSER_LOOP_QML_RUNTIME.md`.** Include authority boundaries, projection interface, exact commands/results, Windows scale results, review verdict, and known upstream `0x8001010d` classification when observed.
- [ ] **Step 9: Commit evidence/doc changes.** `docs(#1285): record Browser Loop QML runtime acceptance`

---

### Task 7: Traceability, PR, CI, merge and live closeout

**Files/Systems:**
- GitHub issue #1285
- GitHub issue #1269
- Pull request against `main`

**Interfaces:**
- Consumes: all validated implementation/evidence from Tasks 1–6.
- Produces: merged #1285 runtime and reconciled Screen-1 traceability.

- [ ] **Step 1: Reconcile stale #1285 gates before/with PR.** Mark #1283 design gate and #1284 runtime gate fulfilled; do not rewrite frozen semantics.
- [ ] **Step 2: Final diff hygiene.** Confirm no private samples/paths/caches/DBs, no unexpected binary evidence, no changes from the dirty main checkout, no #1284 audio redesign.
- [ ] **Step 3: Run `verification-before-completion`.** Re-run the exact focused/broad commands whose PASS will be claimed; record current HEAD.
- [ ] **Step 4: Push feature branch and open PR.** Title: `feat(#1285): Browser Loop inline + sticky QML runtime`; body includes `Closes #1285`, MagicPath rev, #1284 merge SHA, focused/broad tests, Windows visual/runtime evidence and QML review verdict.
- [ ] **Step 5: Run/request review.** Use `requesting-code-review` plus repository `sample-brain-qml-review`; repair material findings with TDD and rerun affected validation.
- [ ] **Step 6: Wait for required CI checks and classify failures.** No admin bypass. In-scope regressions are repaired; unrelated baseline failures are documented with evidence.
- [ ] **Step 7: Squash-merge only when all gates pass.** Verify merge SHA on live `main`.
- [ ] **Step 8: Close/reconcile issues.** #1285 closes only after merged exact-head evidence proves `BROWSER_LOOP_QML_RUNTIME_PASS`. Update #1269 with #1283 design authority, #1284 audio merge, #1285 PR/merge/runtime evidence. Close #1269 only if every one of its own live acceptance criteria is satisfied; otherwise leave it open.

## Self-Review

### Spec coverage

- Full inline owner: Task 3.
- Wide waveform + grid + authoritative playhead: Tasks 3–4.
- Top/bottom Sticky + return/rapid boundary: Task 5.
- Search/filter hidden owner: Task 5.
- Replace / LOOP OFF authoritative projection: Tasks 1–5.
- Context target A/B invariant + three actions: Task 2.
- Hover hierarchy: Task 3 + #1281 regressions.
- No QML musical authority/timer: Tasks 1/4/6 review.
- Reduced capability / reduced motion: Tasks 1/4/6.
- Virtualization / delegate reuse: Tasks 3/5.
- Performance: Tasks 1/5/6, measurement first.
- 100/125/150 DPI + narrow width: Task 6.
- Traceability/PR/merge/closure: Task 7.

### Type/interface consistency

- Product owner remains `BrowserLoopOwner`; snapshot is presentation-only and immutable.
- Existing #1284 intent seams remain canonical; new context toggle composes them.
- Existing `tempoSyncModel.syncEnabled` remains SYNC projection; no duplicate bool in snapshot.
- Existing preview `FrameAnimation` is extended, not duplicated.
- Existing Screen-1 QML test harness is reused; no second QML framework.

### Proportion / YAGNI

- No extraction of embedded `QML_SOURCE` into a new QML architecture in this slice.
- No generic multi-loop model.
- No new transport abstractions.
- No offscreen waveform decoder for Sticky.
- No new performance cache unless profiler evidence requires one.
- No design changes outside approved MagicPath states 07–17.

## Exit Criteria

Only claim #1285 complete when live evidence proves all of:

- full inline Loop matches approved hierarchy;
- `INLINE XOR STICKY` under normal, rapid, filter and reuse transitions;
- top/bottom Sticky direction is correct;
- context target remains separate from selection/audition;
- Loop owner/phase/grid/reduced capability all originate from Python/#1284;
- no QML musical clock or per-delegate playback timer exists;
- ordinary #1281 hover stays coherent and subordinate;
- variable-height owner row does not break waveform viewport requests or scrolling;
- virtualization remains bounded with no stale delegate owner state;
- reduced motion/capability are truthful;
- focused and broad relevant tests pass;
- QML specialist review is PASS;
- Windows exact-head visual/runtime acceptance passes at 100/125/150% and narrow width;
- CI/review gates pass;
- PR is merged and merge is verified on live `main`;
- #1285 is closed with exit `BROWSER_LOOP_QML_RUNTIME_PASS`;
- #1269 is reconciled to actual runtime evidence.
