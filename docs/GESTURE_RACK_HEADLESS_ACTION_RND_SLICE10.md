# Gesture Rack Headless Action R&D — Slice 10 (#680 / #925)

**Status:** `IMPLEMENTED` — frozen Slice-10 contract satisfied by `src/gesture_rack_headless_action.py`. Lifecycle tracked by [#925](https://github.com/jannekbuengener/sample-brain/issues/925) / PR #928 (open, not yet merged).

> **Historical — TEST_FREEZE stage.** At `TEST_FREEZE` (baseline `c693d792`, contract + focused acceptance commit `b39d375b`) the Action module was **absent by design** and the document below was frozen against it. That wording is retained here as freeze-time history only; it does **not** describe the current tree. Where this document says "absent at `TEST_FREEZE`", read it as "did not exist at the freeze baseline".

**Parent:** [#680](https://github.com/jannekbuengener/sample-brain/issues/680) (remains OPEN)

**Child:** [#925](https://github.com/jannekbuengener/sample-brain/issues/925)

## Delivered dependencies (live on `origin/main`)

| Issue | Role | Exit / seam |
|-------|------|-------------|
| [#827](https://github.com/jannekbuengener/sample-brain/issues/827) | Audio analysis | `analyze_gesture_audio` |
| [#882](https://github.com/jannekbuengener/sample-brain/issues/882) | Ranking Top-N | `rank_gesture_library_candidates` — rank 1 ≠ approved choice |
| [#886](https://github.com/jannekbuengener/sample-brain/issues/886) | Catalog adapter | `load_gesture_library_candidates` / `rank_gesture_against_catalog` |
| [#888](https://github.com/jannekbuengener/sample-brain/issues/888) | Timing | `project_gesture_timing` — exact `Fraction` quarters |
| [#891](https://github.com/jannekbuengener/sample-brain/issues/891) | Binding | `plan_gesture_pattern_binding` — explicit selections + length |
| [#893](https://github.com/jannekbuengener/sample-brain/issues/893) | Composition | `compose_gesture_pattern_core` — explicit `pattern_id` |
| [#899](https://github.com/jannekbuengener/sample-brain/issues/899) | Rack plan | `plan_gesture_rack_integration` — plan only |
| [#904](https://github.com/jannekbuengener/sample-brain/issues/904) | SETTINGS_GATE history | `FEATURE_SETTINGS_OWNER_BLOCKED` — do not rewrite |
| [#910](https://github.com/jannekbuengener/sample-brain/issues/910) | Feature flag owner | `gesture_rack_apply_enabled` (default `False`) |
| [#921](https://github.com/jannekbuengener/sample-brain/issues/921) | Guarded apply | `ChannelRackController.apply_gesture_integration_plan` |

Live `main` baseline for this freeze:

`c693d792ca025cabad26ff5de51d7b3e03a62d58`

**BLOCKER check:** `NO_BLOCKER` — *(freeze-time check)* intermediate contracts were present on the baseline and the Action seam was the only missing piece. *Current state:* the Action seam is implemented; the remaining gate is review/approval of PR #928.

## Goal

Deliver one **standalone headless orchestrator** that prepares a gesture audio
→ Rack integration plan through existing Stages 1–7 and, when gates pass,
applies it **once** through the Slice 9 controller seam. *(Delivered as of the
implementation commit; the frozen contract and acceptance were proven against
this seam as specified.)*

```text
audio_path
  + catalog_path (explicit)
  + reference_bpm
  + pattern_length_quarters: Fraction
  + selections: cluster_id → sample_id
  + pattern_id
  + allow_pattern_replacement: bool
  + feature_enabled: bool   (injected; no Settings I/O)
  + channel_rack: ChannelRackController
  → prepare_and_apply_gesture_rack(...)
  → GestureRackHeadlessActionResult
```

## Ownership decision

**Chosen:** new module `src/gesture_rack_headless_action.py` — **implemented and live in this tree**; it was absent at the `TEST_FREEZE` baseline.

**Rejected:**

- Owning this flow on `WorkbenchSession` (session may only supply `session.channel_rack`)
- Extending `ChannelRackController` beyond existing `apply_gesture_integration_plan`
- Reimplementing Stages 1–7 inside the Action
- Auto-picking rank-1 / implicit pattern length / implicit `ensure_state()`
- Direct `workbench_session_store` writes from the Action

## Public seam (frozen)

Module: `src/gesture_rack_headless_action.py` (present in this tree; absent at the `TEST_FREEZE` baseline).

```python
prepare_and_apply_gesture_rack(
    audio_path: Path | str,
    channel_rack: ChannelRackController,
    *,
    catalog_path: Path | str,
    reference_bpm: int | float | str | Fraction,
    pattern_length_quarters: Fraction,
    selections: Mapping[int, str],
    pattern_id: str,
    allow_pattern_replacement: bool,
    feature_enabled: bool,
) -> GestureRackHeadlessActionResult
```

### Result type (frozen, YAGNI-minimal)

```python
@dataclass(frozen=True)
class GestureRackHeadlessActionResult:
    status: str
    unresolved_cluster_ids: tuple[int, ...]
    applied_state: ChannelRackState | None
    binding_plan: GesturePatternBindingPlan | None
    rack_plan: GestureRackIntegrationPlan | None
    analysis_status: str | None
```

### Status vocabulary (frozen)

| `status` | Meaning |
|----------|---------|
| `applied` | Guarded apply succeeded; `applied_state` is the new public rack state |
| `analysis_not_ok` | Stage 1 returned non-`ok` analysis; zero mutation |
| `unresolved_selections` | Binding not ready (missing/incomplete explicit selections); zero mutation |
| `state_none` | `channel_rack.state is None`; **no** `ensure_state()`; zero mutation |
| `feature_disabled` | `feature_enabled is not True`; zero mutation |
| `not_ready_for_apply` | Rack plan `ready_for_apply is not True` (e.g. replacement refused); zero mutation |
| `stale_base_state` | Typed **pre-mutation** rejection `StaleGestureRackIntegrationPlanError` (#921): public state does not match plan `expected_base_state` **before** any `stop()` / state assignment / observer; zero mutation |

## Stage order (frozen Action call sequence)

```text
1. analyze_gesture_audio(audio_path)
2. load_gesture_library_candidates(catalog_path)
   + rank_gesture_library_candidates(analysis, candidates)
   (equivalent: rank_gesture_against_catalog with the same explicit catalog_path)
3. project_gesture_timing(analysis, reference_bpm)
4. Read base_state = channel_rack.state  (public property only)
   — if None → status=state_none (fail-closed; never ensure_state)
5. plan_gesture_pattern_binding(
       timing, rankings, candidates, selections,
       existing_channel_ids from base_state.channels,
       pattern_length_quarters=...)
   — if not ready_for_pattern → status=unresolved_selections
6. compose_gesture_pattern_core(binding_plan, pattern_id=...)
7. plan_gesture_rack_integration(
       base_state, composition,
       allow_pattern_replacement=...)
   — if not ready_for_apply → status=not_ready_for_apply
8. if feature_enabled is not True → status=feature_disabled
9. FIRST MUTATION BOUNDARY ONLY:
   channel_rack.apply_gesture_integration_plan(
       rack_plan, feature_enabled=feature_enabled)
   → status=applied with applied_state
```

Ranking (#882) and timing (#888) are independent after analysis; binding joins
both. The Action documents the call sequence above.

## Policies (hard)

### No auto rank-1

Selections are caller-authoritative. Missing cluster selection yields
`unresolved_selections` (or binding unresolved evidence). The Action must
**never** silently choose `RankedCandidate.rank == 1`.

### State-none policy

```text
CONFIRMED fail-closed — no ensure_state()
```

Public read path: `channel_rack.state` only. Never `channel_rack._state`.
Never call `ensure_state()` / screen enter from the Action.

### Feature flag policy

- Action accepts injected `feature_enabled: bool` only (keyword-only).
- Action must **not** call `load_workbench_feature_settings` or open JSON.
- Controller already refuses disabled apply; Action still returns
  `feature_disabled` **before** calling apply when the injected flag is not
  strictly `True`, so prepare work may complete but mutation does not start.

### First mutation boundary

```text
FIRST_MUTATION_BOUNDARY = ChannelRackController.apply_gesture_integration_plan
```

Stages 1–7 remain pure / plan / read-only. Persistence must **not** be invoked
by the Action; success autosave happens only via existing controller
`on_musical_state_changed` → session callback.

### Pre-apply failure side effects

On any non-`applied` status (and on the caught typed pre-mutation stale reject
from #921):

- zero `stop()`
- zero rack state mutation
- zero observer notify
- zero autosave
- zero `workbench_session_store` writes
- zero Settings I/O

`stale_base_state` is reached **only** by catching
`StaleGestureRackIntegrationPlanError`, which #921 raises in its
`expected_base_state` validation branch — ahead of `stop()`, the state
assignment, and the observer. The Action catches **no** generic `ValueError`
around apply and performs no message-based classification.

Consequence, enforced by regression coverage: an exception raised *after* the
state assignment (e.g. from the musical-state observer callback) propagates
out of the Action. A mutation that already happened is therefore never reported
as a zero-mutation status, and never yields a stale retry signal.

### Final guarded apply route

Only when analysis is `ok`, binding is ready, rack plan is ready, public state
is present and still matches the planned base, and `feature_enabled is True`,
call:

```python
channel_rack.apply_gesture_integration_plan(rack_plan, feature_enabled=True)
```

## Architecture boundary (hard)

| Domain | Authority |
|--------|-----------|
| Audio / clustering | `#827` — consume |
| Ranking Top-N | `#882` — consume; no auto rank-1 |
| Catalog load | `#886` — explicit `catalog_path` |
| Timing `Fraction` | `#888` — consume |
| Selection / length | `#891` — explicit caller inputs |
| Pattern id / composition | `#893` — explicit `pattern_id` |
| Rack plan | `#899` — consume |
| Feature flag value | caller injects `#910` bool |
| Mutation / stop / observer | `#921` apply only |
| Session store | **forbidden** for Action |
| QML / microphone UI | **out of scope** |

## Anti-patterns (forbidden)

- Implementing product Action body in this freeze commit
- Auto rank-1 / confidence thresholds / fallback ranks
- Implicit Pattern length from duration / last onset / bars
- `ensure_state()` / screen enter from Action
- Direct `controller._state` access
- Direct `workbench_session_store` writes
- Settings JSON load/save inside Action
- `restore_state(...)` as live apply shortcut
- Substring/message-based stale classification (catch `StaleGestureRackIntegrationPlanError`, never `except ValueError` around apply)
- `add_user_channel` / DEFAULT_ON seeding
- Rewriting Slice 1–9 stage modules or `apply_gesture_integration_plan` body
- QML gesture workflow / microphone UI
- Closing parent `#680`

## Non-goals

- Microphone / gesture capture UI
- Arrangement / Screen-3
- New settings architecture
- Engine rewrite
- Changing Pattern Core / DB schema
- Closing `#680`

## R&D exits (exactly one)

- `GESTURE_RACK_HEADLESS_ACTION_VIABLE`
- `GESTURE_PIPELINE_ORCHESTRATION_CONTRACT_INSUFFICIENT`
- `INSUFFICIENT_EVIDENCE`

`GESTURE_RACK_HEADLESS_ACTION_VIABLE` means only: the frozen Action can prepare
through Stages 1–7 with explicit caller inputs, fail closed with zero side
effects on pre-apply failures, inject `feature_enabled`, and apply at most once
through `#921` with observer/autosave reuse — without owning session/store/QML.

## Acceptance

See `tests/test_gesture_rack_headless_action_925.py` (domains A–K).

## Protected suites (must stay green during freeze + implementation)

- `tests/test_gesture_analysis.py`
- `tests/test_gesture_library_ranking_882.py`
- `tests/test_gesture_catalog_adapter_886.py`
- `tests/test_gesture_timing_projection_888.py`
- `tests/test_gesture_pattern_binding_891.py`
- `tests/test_gesture_pattern_core_composition_893.py`
- `tests/test_gesture_rack_session_integration_899.py`
- `tests/test_gesture_rack_controller_apply_904_settings_gate.py`
- `tests/test_gesture_rack_controller_apply_921.py`
