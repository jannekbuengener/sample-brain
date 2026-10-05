# Gesture Rack Request R&D - Slice 11 (#680 / #931)

**Status:** `TEST_FREEZE` - Slice-11 contract frozen. The Action module
`src/gesture_rack_request.py` is **absent by design** at this baseline. This
wording describes the freeze state only and does not describe the tree after
IMPLEMENTATION.

**Parent:** [#680](https://github.com/jannekbuengener/sample-brain/issues/680) (remains OPEN)

**Child:** [#931](https://github.com/jannekbuengener/sample-brain/issues/931)

**Freeze baseline:** `6e688d70d207b9ff7a5ab046d220f29ed149a236`

## Delivered dependencies (live on the freeze baseline)

| Issue | Role | Exit / seam |
|-------|------|-------------|
| [#827](https://github.com/jannekbuengener/sample-brain/issues/827) | Audio analysis | `analyze_gesture_audio` |
| [#882](https://github.com/jannekbuengener/sample-brain/issues/882) | Ranking Top-N | `rank_gesture_library_candidates` |
| [#886](https://github.com/jannekbuengener/sample-brain/issues/886) | Catalog adapter | `load_gesture_library_candidates`, `rank_gesture_against_catalog` |
| [#888](https://github.com/jannekbuengener/sample-brain/issues/888) | Timing | `project_gesture_timing` |
| [#891](https://github.com/jannekbuengener/sample-brain/issues/891) | Binding | `plan_gesture_pattern_binding` |
| [#893](https://github.com/jannekbuengener/sample-brain/issues/893) | Composition | `compose_gesture_pattern_core` |
| [#899](https://github.com/jannekbuengener/sample-brain/issues/899) | Rack plan | `plan_gesture_rack_integration` |
| [#910](https://github.com/jannekbuengener/sample-brain/issues/910) | Feature flag owner | `gesture_rack_apply_enabled` (default `False`) |
| [#921](https://github.com/jannekbuengener/sample-brain/issues/921) | Guarded apply | `ChannelRackController.apply_gesture_integration_plan` |
| [#925](https://github.com/jannekbuengener/sample-brain/issues/925) | Headless Action | `prepare_and_apply_gesture_rack` |

## Gap / why Slice 11 exists

Slice 10 delivered a correct, fail-closed headless Action. On the freeze
baseline `prepare_and_apply_gesture_rack` has **no product consumer**: its only
references are its own module, the Slice-10 doc, and its tests. Slice 10
deliberately requires eight explicit caller inputs, but no such caller exists,
so the Action is unreachable from any real product context.

Slice 11 adds the smallest headless seam that binds a **live Workbench session
context** to the already-delivered Action, without adding UI, hidden selection,
hidden config/settings I/O, or a second mutation path.

Slice 11 makes Slice 10 **session-bindable**. It does **not** make the feature
end-user reachable.

## Ownership decision

**Chosen:** new module `src/gesture_rack_request.py`.

**Rejected:**

- Extending `ChannelRackController` beyond `apply_gesture_integration_plan`
- Extending the Slice-10 Action signature
- Reimplementing analysis / ranking / timing / binding / composition / Rack-plan
  logic inside Slice 11
- Owning the live context on `WorkbenchSession`
- Auto rank-1, threshold, or fallback selection
- Resolving the catalog path from config, env, or module globals
- Reading or writing the Feature Settings file from the seam

### Reuse of the existing rank-against-catalog seam

Slice 11 must **not** re-implement load-then-rank. `gesture_catalog_adapter`
already owns the combined projection:

```python
rank_gesture_against_catalog(analysis, catalog_path, *, top_n=5)
```

The proposal seam delegates to it. This keeps ranking/domain math exclusively in
#882/#886 and satisfies the "no duplicate ranking/domain math" requirement.

## Public seam 1 (frozen)

```python
propose_gesture_rack_candidates(
    audio_path: Path | str,
    *,
    catalog_path: Path | str,
    top_n: int = 5,
) -> GestureRackCandidateProposal
```

`GestureRackCandidateProposal` is a frozen dataclass:

| Field | Type | Meaning |
|-------|------|---------|
| `status` | `str` | `ok` or `analysis_not_ok` |
| `analysis_status` | `str \| None` | underlying #827 status |
| `cluster_rankings` | `tuple[ClusterRanking, ...]` | existing #882 values, unchanged |

Behaviour:

1. `analyze_gesture_audio(audio_path)` is called with the explicit `audio_path`.
2. If `analysis.status != "ok"`, return `analysis_not_ok` with empty rankings
   and **no** catalog read.
3. Otherwise delegate to `rank_gesture_against_catalog(analysis, catalog_path,
   top_n=top_n)`.
4. `top_n <= 0` preserves the existing #882 `ValueError`; the seam does not
   swallow, translate, or pre-empt it.

The seam performs **no** selection, **no** mutation, and requires **no** session.

### Distance is not confidence

This is a hard contract boundary.

- `distance` is a measured L2 value in the shared normalized feature space.
- It is **not** a confidence, probability, match quality, or acceptance signal.
- `docs/GESTURE_LIBRARY_RANKING_RND_SLICE2.md` marks calibrated confidence /
  probability as `NOT YET CLAIMED`, and
  `src/gesture_library_ranking.py` documents `distance is not confidence`.

Slice 11 must **not** introduce `confidence`, `probability`, score calibration,
threshold semantics, or an acceptance recommendation.

The structural guarantee: the proposal returns the **existing** #882
`ClusterRanking` / `RankedCandidate` values unchanged. `RankedCandidate` carries
exactly `sample_id`, `distance`, `rank`. A confidence field therefore cannot
appear in Slice 11 output without a change to #882, which is out of scope here.

## Public seam 2 (frozen)

```python
submit_gesture_rack_request(
    audio_path: Path | str,
    live_context: LiveGestureRackContext,
    *,
    catalog_path: Path | str,
    selections: Mapping[int, str],
    pattern_id: str,
    allow_pattern_replacement: bool,
    feature_enabled: bool | WorkbenchFeatureSettingsLike,
) -> GestureRackRequestResult
```

`GestureRackRequestResult` is a frozen dataclass:

| Field | Type | Meaning |
|-------|------|---------|
| `status` | `str` | `submitted` or `state_none` |
| `action_result` | `GestureRackHeadlessActionResult \| None` | verbatim Slice-10 result |

### Caller-explicit inputs (human authority)

These stay explicit. Slice 11 never derives, defaults, or guesses them:

- `audio_path`
- `catalog_path`
- `selections` (`cluster_id -> sample_id`)
- `pattern_id`
- `allow_pattern_replacement`

`selections` is a **human/caller decision**. Top-N is advisory evidence only.

### Derived live context

Derived **only** from existing public seams:

| Slice-11 value | Source |
|----------------|--------|
| `channel_rack` | `live_context.channel_rack` |
| `reference_bpm` | `live_context.transport.get_current_tempo()` |
| `pattern_length_quarters` | `channel_rack.state.pattern.length_quarter_notes` |
| `feature_enabled` | injected `bool`, or `.gesture_rack_apply_enabled` on an already-loaded settings object |

`pattern_length_quarters` is passed through unchanged; the existing
`Pattern.length_quarter_notes` is already an exact `Fraction`.

### Structural live-context contract

The seam depends on a **narrow structural** context, not on the concrete session
class:

```python
class LiveGestureRackContext(Protocol):
    @property
    def channel_rack(self) -> ChannelRackController: ...
    @property
    def transport(self) -> object: ...   # must expose get_current_tempo()
```

`WorkbenchSession` satisfies this structurally. Slice 11 does **not** import
`workbench_session`: that module transitively pulls the QML/Workbench stack, and
the seam must not depend on it. Same reasoning for the settings shape: importing
`src.workbench_feature_settings` costs hundreds of transitive modules, so the
seam accepts a structural `gesture_rack_apply_enabled` provider instead.

### Delegation and mutation path

When live state is present, the seam delegates **exactly once**:

```text
submit_gesture_rack_request
  -> prepare_and_apply_gesture_rack        (Slice 10, #925)
    -> apply_gesture_integration_plan      (Slice 9, #921)  <- only mutation
```

Slice 11 introduces **zero** new Rack mutation paths. It never performs a
`stop()`, observer call, state assignment, Rack construction, or session-store
write. It never calls `ensure_state()`, `restore_state()`, or
`add_user_channel()`.

## Catalog ownership

`catalog_path` stays an **explicit injected input**, unchanged from the Slice-10
contract.

Forbidden in the seam:

- `set_db_path()` - it mutates module-global `config.DB_PATH` and performs
  filesystem work (`mkdir`) on the parent directory
- importing or calling the private `config._resolve_db_path()`
- deriving the catalog path from `config.DB_PATH`, `SAMPLE_BRAIN_DB_PATH`, or
  any other hidden default
- importing `config` at all

The caller resolves the catalog path through the existing config indirection.

Because the seam always passes a non-`None` `catalog_path`, the
`config.DB_PATH` fallback inside `load_gesture_library_candidates` is never
reached on this path.

## Settings policy

`feature_enabled` is **injected only**:

- an explicit `bool`, or
- an already-loaded settings object exposing `.gesture_rack_apply_enabled`

The seam performs **no** Settings file I/O. It must not call
`load_workbench_feature_settings` / `save_workbench_feature_settings`, and must
not open the settings JSON.

A `False` value stays fail-closed through Slice 10 and surfaces as
`action_result.status == "feature_disabled"` with zero mutation.

## State-none policy

Rack materialization is never hidden.

If `live_context.channel_rack.state is None`, the seam returns
`status="state_none"` with `action_result=None` and performs **no** delegation
and **no** mutation. `ensure_state()` is never called.

This pre-check is structurally required, not redundant: the seam must read
`state.pattern.length_quarter_notes` to derive `pattern_length_quarters`, and
that read is impossible when public state is absent. Failing closed before
delegation keeps the "never materialize implicitly" rule local to Slice 11
instead of relying on the Action's own guard.

## Failure model

| Condition | Slice-11 `status` | `action_result` | Mutation |
|-----------|-------------------|-----------------|----------|
| Rack state `None` | `state_none` | `None` | none |
| Delegated, applied | `submitted` | `status="applied"` | via #921 |
| Delegated, flag off | `submitted` | `status="feature_disabled"` | none |
| Delegated, incomplete selections | `submitted` | `status="unresolved_selections"` | none |
| Delegated, plan not ready | `submitted` | `status="not_ready_for_apply"` | none |
| Delegated, analysis not ok | `submitted` | `status="analysis_not_ok"` | none |
| Delegated, stale base state | `submitted` | `status="stale_base_state"` | none |
| Delegated, post-mutation observer failure | `submitted` | raises `GestureRackApplyPostMutationError` | already mutated |

Slice 11 adds no new failure status beyond `state_none`, and never swallows or
re-classifies a Slice-10 status. Post-mutation errors propagate unchanged.

## Architecture boundary (hard)

| Domain | Authority |
|--------|-----------|
| Audio analysis | `#827` - consume |
| Candidate load + ranking | `#882` / `#886` - consume via `rank_gesture_against_catalog` |
| Timing | `#888` - Slice 10 owns |
| Selection / length | `#891` - explicit caller inputs |
| Pattern id / composition | `#893` - Slice 10 owns |
| Rack plan | `#899` - Slice 10 owns |
| Feature flag value | caller injects the `#910` value |
| Mutation / stop / observer | `#921` apply only, reached via Slice 10 |
| Config / catalog resolution | caller; seam forbids `config` |
| Settings I/O | caller; seam is injection-only |
| Session store | **forbidden** |
| QML / microphone UI | **out of scope** |

## Anti-patterns (forbidden)

- Auto rank-1, first-candidate fallback, `min(distance)` as implicit approval
- Any confidence / probability / calibration / threshold / acceptance field
- Implicit pattern length from duration, last onset, or bars
- `set_db_path()` or importing `config`
- Importing or calling `_resolve_db_path()`
- `load_workbench_feature_settings` / settings JSON I/O in the seam
- `ensure_state()` / implicit Rack materialization
- Direct `controller._state` access
- Direct `workbench_session_store` writes
- `restore_state(...)` as a live apply shortcut
- `add_user_channel` / DEFAULT_ON seeding
- Re-implementing Stages 1-7 or duplicating rank-against-catalog math
- A second or alternate mutation path
- Importing `workbench_session` / `workbench_feature_settings` / `workbench_qml`
- Rewriting Slice 1-10 stage modules or `apply_gesture_integration_plan`
- QML gesture workflow / microphone UI
- Closing parent `#680`

## Non-goals

- Microphone / gesture capture UI
- Any QML, page, screen, or navigation work
- Automatic sample selection
- Confidence / probability claims
- Quantization or snap policy
- An implicit catalog owner or default
- Settings I/O inside the request seam
- Session Store I/O
- Pattern Core redesign
- Arrangement / Mixer / external DAW
- Stage-module behavior rewrites
- Closing `#680`

## R&D exits (exactly one)

- `GESTURE_RACK_SESSION_REQUEST_SEAM_VIABLE`
- `GESTURE_RACK_SESSION_REQUEST_SEAM_INSUFFICIENT`
- `INSUFFICIENT_EVIDENCE`

`GESTURE_RACK_SESSION_REQUEST_SEAM_VIABLE` means only: a live session can supply
existing public context to the headless proposal/submit pipeline, while explicit
human selection authority, the #882 evidence semantics, the #910 injection
boundary, and the #921 mutation boundary are all preserved.

It does **not** claim a finished UI, a microphone workflow, automatic selection,
calibrated confidence, quantization, or producer-quality validation.

## Acceptance

See `tests/test_gesture_rack_request_931.py` (domains A-H).

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
- `tests/test_gesture_rack_headless_action_925.py`
- `tests/test_gesture_rack_stale_classification_928.py`
- `tests/test_workbench_feature_settings_910.py`
