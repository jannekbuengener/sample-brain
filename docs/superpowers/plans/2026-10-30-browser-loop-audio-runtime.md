# Browser Loop Audio Runtime (#1284) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline; owner authorized autonomous execution). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement exactly one persistent Browser Loop playback role that coexists with transient Browser audition, reusing `SessionTransport`/`TempoMap`/`WorkbenchTransportAdapter` MASTER/SYNC authority, until exit `BROWSER_LOOP_AUDIO_RUNTIME_PASS`.

**Architecture:** Add `src/browser_loop_playback.py` as the sole Python-owned Loop state/scheduling owner. Keep `TransportAwarePreview` as the transient audition owner. Share one `WorkbenchTransportAdapter`. Loop extent comes only from reliable real downbeats via existing editing helpers. SYNC ON uses MASTER bar/beat phase with deterministic modulo mapping against Loop length `L`; SYNC OFF uses independent source-rate local clocks. No QML visuals (#1285), no second musical clock.

**Tech Stack:** Python 3.12, `NativeAudioEngine` voice primitives, `SessionTransport`/`TempoMap`, `compute_sync_playback_rate`, pytest, synthetic WAV fixtures.

## Global Constraints

- Frozen contract: GitHub #1282 + #1284 body (design gate cleared by closed #1283 / `BROWSER_LOOP_DESIGN_APPROVED`, MagicPath rev `466704025803440128`)
- Exactly one persistent Loop owner; audition is a separate role
- Loop extent: `d[0]..d[k]` → start=`d[0]`, end_excl=`d[k]`, `bar_count=k`; ≥2 real downbeats; no BPM×seconds / file-end / synthetic terminals
- No Browser-private clock; no QML timer as audio authority
- Fail closed: missing downbeats → LOOP unavailable; SYNC ON + invalid BPM → unavailable (never silent unsync)
- Context target: reuse `Screen1QmlInteractionAdapter.sample_context_target`; LOOP ON on B must not change selection/audition A
- TDD: RED → verify RED → GREEN → verify GREEN → refactor
- No #1285 QML visuals; minimal Python adapter seams for later projection only
- No private samples/caches/absolute machine paths in commits
- No direct push to `main`

---

## File Map

**Create:**
- `src/browser_loop_playback.py` — extent/phase helpers + `BrowserLoopOwner`
- `tests/test_browser_loop_playback.py` — domain/scheduling contract suite (#1284 cases)
- `tests/test_browser_loop_context_target.py` — context-target LOOP ON invariant
- `tools/browser_loop_windows_runtime_evidence.py` — exact-head Windows native/audible acceptance harness (synthetic audio only)
- `docs/BROWSER_LOOP_AUDIO_RUNTIME.md` — thin domain seam contract for #1285 consumers

**Modify:**
- `src/native_pcm_decode.py` — optional `end_ms` / frame-span slice for musical extent (or slice helper in browser_loop module)
- `src/workbench_transport_preview.py` — role-aware shared-transport stop; optional phase/frame entry for SYNC audition
- `src/workbench_session.py` — compose `browser_loop`; keep-alive when Loop active; wire SYNC transition hooks
- `src/workbench_qml.py` — canonical `request_loop_on_for_row` / `request_loop_off` / `request_context_loop_on|off` seams (no visual Loop UI)
- `docs/WORKBENCH_SAMPLE_CONTEXT_MENU_CONTRACT.md` — document LOOP ON/OFF via context target
- GitHub issue bodies #1269 / #1284 — documentary reconciliation only

**Reuse (do not fork):**
- `SessionTransport`, `TempoMap`, `compute_sync_playback_rate`
- `source_edit_grid_from_details`, `load_source_downbeats`
- `TransportAwarePreview` (audition only)
- Native `create_voice` / `schedule_voice_start` / `set_voice_rate` / `stop_voice` / `remove_voice`
- Cycle scheduling *ideas* from `NaturalCycleLoopPlayer` (absolute engine frames, voice reclaim) — do **not** subclass Rack player

**Do not modify:** MagicPath, #1285 QML Loop visuals, multi-loop, mixer, Arrangement, BPM estimator, time-stretch engine

---

## Interfaces (locked)

```python
# src/browser_loop_playback.py

@dataclass(frozen=True)
class BrowserLoopExtent:
    source_start_frame: int
    source_end_frame_exclusive: int
    bar_count: int
    downbeat_frames: tuple[int, ...]  # full reliable span d[0..k]


def browser_loop_extent_from_downbeats(
    downbeat_frames: Sequence[int],
) -> BrowserLoopExtent | None:
    """None unless ≥2 strictly increasing non-negative int frames.
    start=d[0], end_excl=d[-1], bar_count=len(d)-1.
    """


def map_comparison_phase_to_source_frame(
    *,
    master_bar: int,
    master_beat: int,
    master_beat_fraction: Fraction | float,
    beats_per_bar: int,
    loop_bar_count: int,          # L
    audition_bar_count: int,      # A (use L when mapping the Loop itself)
    downbeat_frames: Sequence[int],
) -> int:
    """comparison_bar = master_bar % L; source_bar = comparison_bar % A;
    interpolate within [d[source_bar], d[source_bar+1]).
    """


@dataclass(frozen=True)
class BrowserLoopResult:
    ok: bool
    message: str = ""
    owner_path: str | None = None
    bar_count: int | None = None
    reason_code: str | None = None  # e.g. NO_DOWNBEATS, SYNC_NOT_SYNCABLE, NATIVE_UNAVAILABLE


class BrowserLoopOwner:
    """Exactly one persistent Browser Loop role on a shared transport."""

    def __init__(
        self,
        transport: WorkbenchTransportAdapter,
        *,
        pcm_load_fn: Callable | None = None,
        allocate_voice_id: Callable[[], int] | None = None,
    ) -> None: ...

    @property
    def is_active(self) -> bool: ...
    @property
    def owner_row(self) -> WorkbenchRow | None: ...
    @property
    def extent(self) -> BrowserLoopExtent | None: ...
    @property
    def active_voice_ids(self) -> tuple[int, ...]: ...

    def validate_row(self, row: WorkbenchRow) -> BrowserLoopResult:
        """Validate extent + SYNC/BPM/native readiness without mutating owner."""

    def loop_on(self, row: WorkbenchRow) -> BrowserLoopResult:
        """Validate/prepare first; on success set owner and start. Atomic replace."""

    def loop_off(self) -> BrowserLoopResult:
        """Clear Loop role only; do not stop audition."""

    def tick(self, *, engine_frame: int | None = None) -> None:
        """Schedule next cycle voice(s) at musical boundaries; reclaim finished."""

    def on_sync_changed(self, *, enabled: bool) -> None:
        """OFF→ON re-anchor to MASTER phase; ON→OFF keep source phase at rate 1.0."""

    def on_master_bpm_changed(self) -> None:
        """Keep synced roles coherent via existing adapter rate path; no second engine."""

    def comparison_source_frame_for_row(
        self, row: WorkbenchRow, *, session_frame: int | None = None
    ) -> int | None:
        """SYNC ON entry frame for audition (or None if unavailable)."""

# Adapter seams (workbench_qml.py / session)
# request_loop_on_for_row(row: WorkbenchRow) -> BrowserLoopResult
# request_loop_off() -> BrowserLoopResult
# request_context_loop_on() -> uses sample_context_target only
# request_context_loop_off() -> clears Loop only
```

---

## Self-review vs #1282 / #1284

| Requirement | Task |
|---|---|
| One MASTER authority | T2–T4 reuse transport only |
| Downbeat musical extent | T1 |
| Exactly one Loop owner + atomic replace | T2 |
| LOOP OFF clears Loop only | T2 |
| Scroll zero audio | T5 (regression: selectRow ≠ preview/loop) |
| Click replaces audition, Loop stays | T3 |
| SYNC OFF independent clocks | T4 |
| SYNC ON MASTER phase + modulo L/A | T4 |
| OFF→ON / ON→OFF transitions | T4 |
| BPM change coherent / fail-closed | T4 |
| No stale/duplicate voices | T2 |
| Context target B vs selection A | T5 |
| Windows native evidence | T6 |
| No #1285 visuals | Scope lock |

---

### Task 0: Issue documentary reconciliation

**Files:** GitHub #1269, #1284 bodies (no product semantics)

- [ ] **Step 1:** Update #1284 gate checkboxes: #1283 design approved; remove stale “must still reach DESIGN_APPROVED”
- [ ] **Step 2:** Update #1269: states 10–17 approved; strike “review-only until explicitly approved” / unchecked “remain review-only”
- [ ] **Step 3:** Confirm #1283 CLOSED and #1284 OPEN via `gh issue view`

---

### Task 1: Downbeat extent + phase mapping (pure)

**Files:**
- Create: `src/browser_loop_playback.py` (helpers first)
- Test: `tests/test_browser_loop_playback.py`

**Interfaces:**
- Produces: `BrowserLoopExtent`, `browser_loop_extent_from_downbeats`, `map_comparison_phase_to_source_frame`

- [ ] **Step 1: Write failing tests** for cases 7–9, 13–14 (extent + modulo + tail exclusion)

```python
def test_extent_from_downbeats_full_span():
    ext = browser_loop_extent_from_downbeats((0, 100, 200, 300, 400))
    assert ext is not None
    assert ext.source_start_frame == 0
    assert ext.source_end_frame_exclusive == 400
    assert ext.bar_count == 4

def test_extent_rejects_single_downbeat():
    assert browser_loop_extent_from_downbeats((0,)) is None

def test_modulo_mapping_different_L_and_A():
    # L=8, A=4, master bar 17 → comparison 1 → source bar 1
    frame = map_comparison_phase_to_source_frame(
        master_bar=17, master_beat=0, master_beat_fraction=0,
        beats_per_bar=4, loop_bar_count=8, audition_bar_count=4,
        downbeat_frames=tuple(i * 100 for i in range(5)),
    )
    assert frame == 100
```

- [ ] **Step 2: Run RED** — `pytest tests/test_browser_loop_playback.py -k extent_or_modulo -v`
- [ ] **Step 3: Implement helpers**
- [ ] **Step 4: Run GREEN**
- [ ] **Step 5: Commit** `test(#1284): add browser loop extent and phase mapping`

---

### Task 2: BrowserLoopOwner lifecycle (ON/OFF/replace/voices)

**Files:**
- Modify: `src/browser_loop_playback.py`
- Test: `tests/test_browser_loop_playback.py`

**Interfaces:**
- Consumes: Task 1 helpers, `WorkbenchTransportAdapter`, fake/native engine
- Produces: `BrowserLoopOwner.loop_on/off/validate_row/tick/active_voice_ids`

- [ ] **Step 1: Write failing tests** for cases 1–4, 20–21 (owner, invalid replace, atomic replace, LOOP OFF, no stale/duplicate)

```python
def test_first_valid_loop_creates_exactly_one_owner(owner, row_ok):
    result = owner.loop_on(row_ok)
    assert result.ok
    assert owner.is_active
    assert owner.owner_row is row_ok
    assert len(owner.active_voice_ids) >= 1

def test_invalid_replacement_preserves_owner(owner, row_ok, row_no_grid):
    owner.loop_on(row_ok)
    path = owner.owner_row.path
    bad = owner.loop_on(row_no_grid)
    assert not bad.ok
    assert owner.owner_row.path == path
```

- [ ] **Step 2: Run RED**
- [ ] **Step 3: Implement owner with prepare-then-swap; LOOP OFF clears Loop voices only**
- [ ] **Step 4: Run GREEN**
- [ ] **Step 5: Commit** `feat(#1284): add persistent BrowserLoopOwner lifecycle`

---

### Task 3: Coexistence with audition + scroll neutrality

**Files:**
- Modify: `src/workbench_transport_preview.py` (keep-alive callback)
- Modify: `src/workbench_session.py` (compose + stop policy)
- Test: `tests/test_browser_loop_playback.py`

- [ ] **Step 1: Failing tests** cases 5–6 (scroll emits no playback; click replaces audition, Loop stays)
- [ ] **Step 2: RED**
- [ ] **Step 3: Wire `should_keep_shared_transport` so audition stop does not tear down active Loop; ensure selectRow path never calls loop/audition**
- [ ] **Step 4: GREEN**
- [ ] **Step 5: Commit** `feat(#1284): keep Loop alive across audition replace/stop`

---

### Task 4: SYNC OFF/ON, transitions, BPM, drift

**Files:**
- Modify: `src/browser_loop_playback.py`, `src/workbench_transport_adapter.py` (hook sync toggle → loop), `src/workbench_session.py`
- Test: `tests/test_browser_loop_playback.py`

- [ ] **Step 1: Failing tests** cases 10–19, 22 (SYNC paths, transitions, BPM, drift, fail-closed, de-click bound)
- [ ] **Step 2: RED**
- [ ] **Step 3: Implement**
  - SYNC OFF: rate 1.0; cycle = musical PCM length; restart at extent boundary
  - SYNC ON: rate via `compute_sync_playback_rate`; schedule cycle starts at MASTER `bar % L == 0` boundaries; audition entry via `comparison_source_frame_for_row`
  - OFF→ON: re-anchor at transition session/engine frame (bounded crossfade ≤ small constant frames; musical boundary unshifted)
  - ON→OFF: keep current source phase at rate 1.0
  - Invalid BPM under SYNC: fail-closed; preserve owner identity, stop audio, project reduced capability
- [ ] **Step 4: GREEN**
- [ ] **Step 5: Commit** `feat(#1284): sync phase mapping and transition policy`

---

### Task 5: Context-target seam + docs

**Files:**
- Modify: `src/workbench_qml.py`, `src/workbench_session.py`
- Modify: `docs/WORKBENCH_SAMPLE_CONTEXT_MENU_CONTRACT.md`
- Create: `docs/BROWSER_LOOP_AUDIO_RUNTIME.md`
- Test: `tests/test_browser_loop_context_target.py`

- [ ] **Step 1: Failing test** case 23 (selection/audition A, context B, LOOP ON → owner B, A unchanged)
- [ ] **Step 2: RED**
- [ ] **Step 3: Implement `request_context_loop_on/off` consuming `sample_context_target` only**
- [ ] **Step 4: GREEN + docs**
- [ ] **Step 5: Commit** `feat(#1284): context-target Loop seam`

---

### Task 6: Validation + Windows native evidence + PR

**Files:**
- Create: `tools/browser_loop_windows_runtime_evidence.py`
- Evidence note under work-dir outside repo (or `docs/` summary without binaries)

**Validation order:**
1. `pytest tests/test_browser_loop_playback.py tests/test_browser_loop_context_target.py -q`
2. `pytest tests/test_session_grid.py tests/test_workbench_tempo_sync_grid.py tests/test_workbench_shared_playback.py tests/test_workbench_editing.py tests/test_workbench_qml_sample_context_menu_839.py tests/test_workbench_preview_playhead_contract.py tests/test_loop_rack_playback.py -q`
3. Full `pytest -q` (classify baselines)
4. `ruff check` on touched paths
5. Windows native harness (4/8/16/N-bar, tail, Loop+audition, scroll, replace, OFF, SYNC transitions, BPM, missing metadata, drift run)
6. Diff + hygiene review
7. Push + PR → checks → review → squash-merge → verify main → close #1284

- [ ] **Step 1: Run focused + regression suites**
- [ ] **Step 2: Run Windows runtime evidence script; record PASS/FAIL with SHA**
- [ ] **Step 3: Open PR referencing #1284**
- [ ] **Step 4: Address review; merge only when gates green**
- [ ] **Step 5: Verify main; close #1284 with `BROWSER_LOOP_AUDIO_RUNTIME_PASS`**

---

## Execution note

Owner authorized autonomous inline execution (no mid-plan wait for subagent vs inline choice). Escalate only for true scope expansion or external blockers.
