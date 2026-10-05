# Deterministic Natural-Cycle Loop Rack Playback — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement #926 deterministic `NATURAL_CYCLE_REPEAT` Loop Rack playback for explicit `sample_class=loop`, with classification-aware non-destructive restore and frozen MASTER/SYNC + Live Kit mutation deferral until the next Rack Play.

**Architecture:** Keep Pattern Core shapes and QML unchanged. Classification stays on Live Kit `WorkbenchRow.sample_class`. Point-trigger playback uses a pure filter before `plan_pattern_once`. Loop cycles are owned by `NaturalCycleLoopPlayer` in [`src/loop_rack_playback.py`](src/loop_rack_playback.py), started/ticked/stopped by `ChannelRackController` beside (not inside) `PatternPassPlayer`. Play-time snapshots freeze rate/duration for the whole Rack Play.

**Tech Stack:** Python 3.12, `NativeAudioEngine`, `SequencerPcmProvider`, `TempoMap`, `compute_sync_playback_rate`, pytest.

**Plan path:** [`docs/superpowers/plans/2026-10-05-deterministic-natural-cycle-loop-rack-playback.md`](docs/superpowers/plans/2026-10-05-deterministic-natural-cycle-loop-rack-playback.md) (Writing-Plans default; no newer canon path exists).

I'm using the writing-plans skill to create this implementation plan.

## Global Constraints

- Authority: [`docs/LOOP_ROW_PLAYBACK_CONTRACT.md`](docs/LOOP_ROW_PLAYBACK_CONTRACT.md) + Issue #926 + Single Workspace / Session / Pattern / Sequencer contracts
- Outcome: `LOOP_ROW_DISTINCT_PROJECTION_REQUIRED` (do not reopen)
- Mode: `NATURAL_CYCLE_REPEAT`
- Owner: `ChannelRackController` + helper module; not PatternPassPlayer forever-loop; not QML; not new transport
- `LOOP_TRANSPORT_MUTATION_POLICY = DEFER_UNTIL_NEXT_RACK_PLAY` (Lead freeze)
- `LOOP_ASSIGNMENT_MUTATION_POLICY = DEFER_UNTIL_NEXT_RACK_PLAY` (live: assign does not stop play; freeze no mid-play PCM hot-swap)
- Cycle math: `effective_cycle_duration_frames = ceil(pcm_frame_count / playback_rate)`; `start(n) = play_anchor + n * duration`
- Rate source: only `compute_sync_playback_rate` — no second clamp algorithm
- Native unavailable → loop fail-closed (SYNC on or off)
- No Pattern Core shape change; no `Channel.sample_class`; no persistence schema bump; no QML/#908 redesign; no PCM wrap; no KEY_LOCK; no Arrangement
- TDD: DOCS → TESTS → RED → TEST FREEZE → IMPLEMENTATION → GREEN → protected → broad → PR
- No Production Code before RED

## Review Focus (failure class → owning test)

1. MASTER/SYNC mutation during Play → `test_loop_transport_mutation_defers_until_next_rack_play`
2. Live Kit assignment/class mutation during Play → `test_loop_assignment_mutation_defers_pcm_until_next_rack_play`
3. Ambiguous restore without library metadata → `test_persisted_triggers_preserved_when_library_db_missing`
4. Voice-budget / create/schedule failures → `test_loop_player_respects_sb_max_voices_fail_soft`, `test_loop_create_failure_fail_soft`, `test_loop_schedule_failure_cleans_up`
5. Cycle drift over long runs → `test_cycle_starts_no_drift_over_1000_cycles`

## Live State (verified)

- `origin/main` = `c3c34ea8712e43fb765c05c9d019b1d2045b065c`
- #920 CLOSED; #926 OPEN; #924 MERGED (`852b058b` accepted head)
- No open #926 implementation PR
- Implementation must start from fresh `origin/main` worktree

## Binding decisions

### Transport: DEFER_UNTIL_NEXT_RACK_PLAY

On Rack Play snapshot once: `sync_enabled`, MASTER BPM, per-loop source BPM, `playback_rate`, `effective_cycle_duration_frames`. Mid-play MASTER/SYNC changes must not retune voices or rewrite cycle frames. Stop→Play rebuilds. SYNC on + invalid BPM at Play → that loop channel fails closed.

### Assignment: DEFER_UNTIL_NEXT_RACK_PLAY

Live today: `LiveKitState.assign` → `ensure_state` reconciles `_state` and does **not** stop play. Freeze: no mid-play loop PCM hot-swap; no duplicate loop owners; current Play keeps frozen loop specs; new semantics on next explicit Play. Oneshot PatternPass keeps next-pass-applies behavior.

### NEW vs RESTORE/HYDRATION (no Channel.sample_class)

| Path | Signal | Behavior |
|---|---|---|
| Restore | `restore_state(snapshot)` | Triggers bit-identical; never DEFAULT_ON rebuild |
| Hydration | `rehydrate_live_kit_from_library` | Fills `sample_class` only; must not reseed |
| New assign | reconcile `empty→bearing` = `"seed"` | DEFAULT_ON only if explicit oneshot |
| Replace | `"keep"` | Preserve triggers |
| Clear | `"strip"` | Strip triggers |
| Class becomes explicit loop | known loop on reconcile | May strip stale loop-channel triggers |
| Ambiguous | missing/other | Keep persisted triggers; exclude from point-trigger playback + loop auto-start |

---

## File Map

**Create:** [`src/loop_rack_playback.py`](src/loop_rack_playback.py), [`tests/test_channel_rack_loop_classification.py`](tests/test_channel_rack_loop_classification.py), [`tests/test_loop_rack_playback.py`](tests/test_loop_rack_playback.py)

**Modify:** [`src/channel_rack.py`](src/channel_rack.py), [`src/workbench_channel_rack.py`](src/workbench_channel_rack.py), [`tests/test_workbench_channel_rack_loop.py`](tests/test_workbench_channel_rack_loop.py), [`tests/test_workbench_session_persistence.py`](tests/test_workbench_session_persistence.py), narrow sync [`docs/LOOP_ROW_PLAYBACK_CONTRACT.md`](docs/LOOP_ROW_PLAYBACK_CONTRACT.md) (DEFER policy + ceil formula only)

**Protected (run; change only if #926 proves breakage):** focus suites, bottom_rack, sequencer playback/PCM, DEFAULT_ON contract tests

**Do not modify:** Pattern Core shapes, QML, native wrap, persistence schema

---

## Interfaces (locked)

```python
# src/channel_rack.py
ClassificationKind = Literal["oneshot", "loop", "ambiguous"]

def normalize_sample_class(value: object | None) -> str: ...
def classification_kind(sample_class: object | None) -> ClassificationKind: ...
def is_point_trigger_safe(sample_class: object | None) -> bool: ...
def is_explicit_loop(sample_class: object | None) -> bool: ...
def sample_class_for_channel(channel: Channel, live_kit: LiveKitState) -> str | None: ...
def point_trigger_eligible_channel_ids(state: ChannelRackState, live_kit: LiveKitState) -> frozenset[str]: ...
def filter_pattern_for_point_trigger_playback(state: ChannelRackState, live_kit: LiveKitState) -> Pattern:
    """Pure filter; do not mutate state. Only explicit oneshot channel triggers remain."""

# seed/reconcile: DEFAULT_ON only when action=="seed" AND is_point_trigger_safe(assignment)
# explicit loop on reconcile: may strip that channel's triggers
# ambiguous: never strip for missing class; never seed DEFAULT_ON
# play_channel_rack_once: plan from filter_pattern_for_point_trigger_playback(...)
```

```python
# src/loop_rack_playback.py
@dataclass(frozen=True)
class LoopCycleSpec:
    channel_id: str
    sample_path: str
    pcm_frame_count: int
    source_bpm: float | None
    playback_rate: float
    effective_cycle_duration_frames: int
    play_anchor_engine_frame: int

@dataclass(frozen=True)
class LoopTickResult:
    scheduled_voice_ids: tuple[int, ...]
    scheduled_count: int
    skipped_missing_source_count: int
    skipped_voice_limit_count: int
    skipped_engine_error_count: int
    next_cycle_index_by_channel: Mapping[str, int]

def pcm_frame_count(pcm: Any) -> int:  # size//channels; fail-closed bad channels/empty
def effective_cycle_duration_frames(pcm_frame_count: int, playback_rate: float) -> int:  # math.ceil; fail-closed
def cycle_start_engine_frame(play_anchor_engine_frame: int, cycle_index: int, duration_frames: int) -> int: ...
def build_loop_cycle_specs(*, state, live_kit, pcm_for_path, play_anchor_engine_frame, sync_enabled, master_bpm) -> tuple[LoopCycleSpec, ...]: ...

class NaturalCycleLoopPlayer:
    def __init__(self, specs, *, pcm_for_path, lookahead_frames, max_voices=SB_MAX_VOICES) -> None: ...
    def tick(self, *, engine_frame: int, engine: Any, allocate_voice_id: Callable[[], int]) -> LoopTickResult: ...
    def stop(self, engine: Any) -> None: ...
```

Scheduler: absolute `start(n)`; bounded lookahead; max one sounding + at most one future scheduled voice per channel; IDLE reclaim with `seen_active` semantics; `VoiceConfig(initial_rate=spec.playback_rate)`; never mid-play `set_rate` for transport mutation; `SB_MAX_VOICES` fail-soft.

Controller Play: ensure state → #916 focus → stop previous → native required → capture anchor + freeze transport → `build_loop_cycle_specs` → filtered `play_channel_rack_once` → `NaturalCycleLoopPlayer` + initial tick. Tick: PatternPass + pass succession **and** independent loop tick. Stop: clear both ownerships; no auto-resume.

---

## Task 1 — Classification-aware seed/reconcile + playback filter

**Files:** Modify [`src/channel_rack.py`](src/channel_rack.py); Test [`tests/test_channel_rack_loop_classification.py`](tests/test_channel_rack_loop_classification.py)

**Interfaces:** Produces classification helpers, filter, seed/reconcile gates; `play_channel_rack_once` uses filtered pattern

- [ ] **Step 1: Write failing tests** — `test_new_oneshot_assignment_seeds_default_on`, `test_new_loop_assignment_does_not_seed_default_on`, `test_ambiguous_assignment_does_not_seed_default_on`, `test_filter_excludes_loop_and_ambiguous_from_point_playback_without_mutating_state`, `test_explicit_loop_stale_triggers_reconciled_when_class_known`, `test_ambiguous_keeps_persisted_triggers_in_state`
- [ ] **Step 2: RED** — `pytest tests/test_channel_rack_loop_classification.py -q`
- [ ] **Step 3: Minimal implementation** in `channel_rack.py` only
- [ ] **Step 4: GREEN** — same command
- [ ] **Step 5: Commit** — `test(channel_rack): classify seed and point-trigger playback filter (#926)`

---

## Task 2 — Pure loop cycle math + spec construction

**Files:** Create [`src/loop_rack_playback.py`](src/loop_rack_playback.py) (math/builders); Test [`tests/test_loop_rack_playback.py`](tests/test_loop_rack_playback.py)

**Interfaces:** Produces `pcm_frame_count`, `effective_cycle_duration_frames`, `cycle_start_engine_frame`, `build_loop_cycle_specs`, `LoopCycleSpec`

- [ ] **Step 1: Write failing tests** — mono/stereo frame count; reject zero/bad channels; rate 1.0 / RATE_SYNC example / 0.25 / 4.0; reject `<=0`/NaN/Inf; absolute 1000-cycle starts; build_specs SYNC off/on/missing BPM; ignore oneshot/ambiguous
- [ ] **Step 2: RED** — `pytest tests/test_loop_rack_playback.py -k "pcm_frame or cycle_ or build_specs" -q`
- [ ] **Step 3: Implement** with `math.ceil` + `compute_sync_playback_rate`
- [ ] **Step 4: GREEN**
- [ ] **Step 5: Commit** — `feat(loop_rack): add natural-cycle duration math and specs (#926)`

---

## Task 3 — Bounded NaturalCycleLoopPlayer lifecycle

**Files:** Modify [`src/loop_rack_playback.py`](src/loop_rack_playback.py); Test [`tests/test_loop_rack_playback.py`](tests/test_loop_rack_playback.py)

**Interfaces:** Produces `NaturalCycleLoopPlayer.tick/stop`, `LoopTickResult`

- [ ] **Step 1: Write failing tests** (fake engine) — first cycle at anchor; lookahead-bounded future cycles; no self-overlap; IDLE reclaim; multi-channel lengths; SB_MAX_VOICES fail-soft; create/schedule failure; Stop clears current+future; Stop before future cycle; `test_cycle_starts_no_drift_over_1000_cycles`
- [ ] **Step 2: RED**
- [ ] **Step 3: Implement player** (reuse PatternPassPlayer reclaim patterns; distinct ownership)
- [ ] **Step 4: GREEN** — `pytest tests/test_loop_rack_playback.py -q`
- [ ] **Step 5: Commit** — `feat(loop_rack): add NaturalCycleLoopPlayer lifecycle (#926)`

---

## Task 4 — ChannelRackController integration

**Files:** Modify [`src/workbench_channel_rack.py`](src/workbench_channel_rack.py); Test [`tests/test_workbench_channel_rack_loop.py`](tests/test_workbench_channel_rack_loop.py)

**Interfaces:** Controller `_loop_player` / frozen specs; Play/tick/Stop; public QML commands unchanged

- [ ] **Step 1: Write failing tests** — continues across pattern passes; no pass-boundary retrigger; loop+oneshot; loop-only; oneshot path unchanged; native unavailable fail-closed SYNC on/off; Play/Stop idempotence; bottom_rack `loop_identity` unchanged
- [ ] **Step 2: RED** — `pytest tests/test_workbench_channel_rack_loop.py -q`
- [ ] **Step 3: Wire Play/tick/Stop**
- [ ] **Step 4: GREEN** + `pytest tests/test_workbench_single_workspace_bottom_rack.py -q`
- [ ] **Step 5: Commit** — `feat(workbench): integrate natural-cycle loop player into rack play (#926)`

---

## Task 5 — MASTER/SYNC freeze + Live Kit mutation guards

**Files:** Modify controller/player as needed; Test in loop/controller suites

- [ ] **Step 1: Write failing tests** — `test_loop_transport_mutation_defers_until_next_rack_play` (capture rate/duration/starts; change MASTER; toggle SYNC; assert freeze; no voice `set_rate`; Stop→Play rebuilds; missing BPM → no loop voice); `test_loop_assignment_mutation_defers_pcm_until_next_rack_play`; `test_next_play_sync_on_missing_bpm_starts_no_loop_voice`
- [ ] **Step 2: RED**
- [ ] **Step 3: Freeze snapshot at Play; ignore mid-play transport/assignment for loop scheduler**
- [ ] **Step 4: GREEN**
- [ ] **Step 5: Commit** — `fix(workbench): defer loop transport/assignment mutations until next play (#926)`

---

## Task 6 — Persistence / focus / protected + contract sync

**Files:** [`tests/test_workbench_session_persistence.py`](tests/test_workbench_session_persistence.py); narrow [`docs/LOOP_ROW_PLAYBACK_CONTRACT.md`](docs/LOOP_ROW_PLAYBACK_CONTRACT.md)

- [ ] **Step 1: Write failing persistence tests** — oneshot hydrate bit-identical; missing library DB preserves triggers; stale+loop hydrate reconciles + excluded from PatternPass; ambiguous→loop; ambiguous→oneshot preserves edits/no reseed
- [ ] **Step 2: RED**
- [ ] **Step 3: Minimal restore/hydrate/reconcile fixes (no schema bump)**
- [ ] **Step 4: GREEN** persistence + protected focus/bottom_rack/sequencer/PCM suites
- [ ] **Step 5: Record DEFER + ceil in contract; commit** — `test(session): non-destructive loop classification restore (#926)`

---

## Task 7 — Broad validation / PR readiness

- [ ] Focused #926 suites
- [ ] Protected DEFAULT_ON + channel_rack contracts
- [ ] `git diff --check`; Ruff on touched files; `python tools/check_canon_drift.py`
- [ ] Broad `pytest -q`
- [ ] Open #926 PR after GREEN (no merge in planning)

## Test Matrix (requirement → task)

| Requirement | Task |
|---|---|
| New oneshot DEFAULT_ON; loop/ambiguous no seed; filter non-mutating; stale loop reconcile | T1 |
| Cycle math rates/boundaries/invalid/stereo/1000-cycle absolute starts; build_specs | T2 |
| Player lifecycle, voice limit, failures, Stop, drift | T3 |
| Multi-pass continue; no pass retrigger; loop+oneshot; loop-only; oneshot unchanged; native fail-closed; QML identity | T4 |
| Transport/assignment DEFER; next Play missing BPM | T5 |
| Persistence hydrate cases; #916 focus protected | T6 |
| Broad validation / PR | T7 |

## Validation

Focused #926 → protected #916/#908/sequencer/PCM/DEFAULT_ON → diff-check/Ruff/canon drift → broad pytest. No QML Visual Acceptance unless QML changes → STOP/escalate. Native C tests only if native files change (should not).

## Scope Guard

Allowed: classification reconcile, playback filter, `loop_rack_playback.py`, controller integration, tests, narrow contract sync. Forbidden: Pattern Core shape change, QML/#908 redesign, PCM wrap, scheduled-stop FFI, Arrangement/clips, mixer/piano roll, new transport, schema expansion, KEY_LOCK, unrelated cleanup.

## Self-Review

1. Spec coverage: every #926 requirement + Lead DEFER mapped to Tasks 1–7
2. Granularity: independent RED→GREEN commit boundaries
3. Interface names consistent across tasks
4. Review Focus covered by named tests
5. Proportion: one runtime slice; helper justified (~688-line controller + scheduler weight)
6. No TODO/TBD/FIXME
7. No hidden QML scope
8. Required tests mapped in matrix

## Blockers

None for planning. Implementation waits for Owner/Lead plan approval (TEST_GATE).

## NEXT

Owner/Lead reviews the #926 test-first implementation plan before TEST_GATE.

## FINAL

`PLAN_READY_FOR_REVIEW`
