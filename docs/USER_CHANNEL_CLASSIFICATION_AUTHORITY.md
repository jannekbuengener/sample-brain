# User-Channel Classification Authority — Sample Brain

**Status:** ACTIVE_SUPPORTING — ownership freeze for [#936](https://github.com/jannekbuengener/sample-brain/issues/936). No runtime behavior change is authorized by this document.
**Class:** ACTIVE_SUPPORTING
**Parent:** [`LOOP_ROW_PLAYBACK_CONTRACT.md`](LOOP_ROW_PLAYBACK_CONTRACT.md), [`WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md`](WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md) (§9), [#905](https://github.com/jannekbuengener/sample-brain/issues/905), [#908](https://github.com/jannekbuengener/sample-brain/issues/908)
**Depends on:** [`SESSION_OWNERSHIP_CONTRACT.md`](SESSION_OWNERSHIP_CONTRACT.md), [`PATTERN_CORE_CONTRACT.md`](PATTERN_CORE_CONTRACT.md), [`SEQUENCER_PLAYBACK_CONTRACT.md`](SEQUENCER_PLAYBACK_CONTRACT.md), [`LOOP_ROW_PLAYBACK_CONTRACT.md`](LOOP_ROW_PLAYBACK_CONTRACT.md)

This freeze resolves the *ownership gap* that #926's fail-closed Rack playback made visible for user-added Rack channels. It does **not** enable playback, does not change any class decision, and does not authorize a second classifier.

## Architecture outcome

```text
USER_CHANNEL_CLASSIFICATION_RESOLVER_INJECTED
```

The Workbench library remains the single classification authority. The session layer owns and injects a read-only resolver; the Channel Rack controller and every playback consumer read a **derived, non-persisted** binding. Low-level Rack/audio modules gain no I/O capability.

## Live preanalysis (code-backed)

Verified against `origin/main` at `122f0d4e` (#939):

| Surface | Live fact |
|---|---|
| `Channel` (`src/pattern_core.py`) | Exactly `channel_id`, `live_kit_group`, `live_kit_slot`, `sample_path`. No `sample_class`, no BPM. |
| `ChannelRackState` / `Pattern` | Path-only musical truth; `ChannelRackState` is a frozen dataclass. |
| `sample_class_for_channel(channel, live_kit)` (`src/channel_rack.py:63`) | Returns `None` for every channel without Live Kit group/slot provenance. This is the **single** classification consumption point. |
| Consumers of that one function | `build_channel_rack_state`, `reconcile_live_kit_sample_assignments`, `point_trigger_eligible_channel_ids`, `filter_pattern_for_point_trigger_playback`, `loop_rack_playback.build_loop_cycle_specs`. |
| Bottom Rack projection (`project_bottom_rack_for_qml`) | User channels are hardcoded `row_kind=loop_identity`, `step_grid_enabled=false`, `steps=[]`, with the comment "unless callers later attach classification through a dedicated seam" (`src/workbench_channel_rack.py:307`). |
| #926 playback owners | `PatternPassPlayer` (point trigger) and `NaturalCycleLoopPlayer` / `build_loop_cycle_specs` (`loop`). No third route exists. |
| `workbench_library.query_sample_by_path_on_readonly_connection(conn, path)` | Read-only, temp read-snapshot, includes committed WAL frames. Already fail-closed: analyzer-version mismatch or cached size/mtime fingerprint mismatch ⇒ `None` (catalog miss). |
| `workbench_library.workbench_library_readonly_connection(db_path)` | Yields `None` for missing/unopenable DB. One connection can serve a whole batch. |
| Canonical lookup path | `str(Path(original_path).expanduser().resolve())`, applied **inside** the library query seam. |
| `rehydrate_live_kit_from_library` (`src/workbench_session_store.py:207`) | Existing precedent: one read-only connection, fail-soft, never mutates the library, runs during restore **before** autosave observers are wired. |
| `compose_workbench_session(library_db_path=…)` (`src/workbench_session.py:199`) | Owns `library_db_path` and constructs `ChannelRackController(live_kit, transport)` with no classification argument. **This is the missing wiring.** |
| `apply_gesture_integration_plan` (#921, #680) | Atomic `self._state` replace with gesture-appended `Channel(live_kit_group=None, live_kit_slot=None, sample_path=…)` — i.e. user channels by the same definition. |
| Session JSON (`SCHEMA_VERSION = 2`) | Strict allowed-key sets; `Channel` serialized path-only. No `sample_class` key exists or may be added. |
| `build_loop_cycle_specs` source BPM | Reads `source_bpm` from the Live Kit assignment only. A user channel has no assignment ⇒ `None` ⇒ SYNC-on loop is skipped (canon-conformant fail-closed). |

## Frozen decisions

### 1. Resolver / derived-metadata contract

One new session-owned module, `src/workbench_user_sample_metadata.py`:

```text
UserSampleMetadataResolver      # Protocol: resolve(paths) -> UserSampleMetadataBinding
                                #         resolve_one(path) -> UserSampleMetadata | None
UserSampleMetadataBinding       # immutable Mapping[str, UserSampleMetadata]
                                #   key   == the exact durable Channel.sample_path string
                                #   value == UserSampleMetadata(sample_class, source_bpm)
WorkbenchLibraryUserSampleMetadataResolver  # the only I/O owner
                                #   __init__(*, library_db_path: Path | None)
```

Rules:

- **Binding key is the raw durable path string, never a normalized one.** Lookup canonicalization stays private to `workbench_library`. The controller therefore cannot drift from library path semantics, and no second normalizer exists.
- `source_bpm` is part of the same record because it comes from the *same already-read library row*. This closes the otherwise-forced second seam for SYNC-on user loop channels. It is **not** a BPM ownership transfer: `WorkbenchTransportAdapter` stays the sole tempo authority.
- Every missing/stale/unreadable condition resolves to `sample_class=None` ⇒ `ambiguous`.
- The binding is derived, in-memory, and never serialized. `pred_type` is never used.

**Rejected alternatives:** a third metadata store; a `sample_class` field on `Channel` or in session JSON; a controller-local SQLite handle; filename/folder text heuristics; a second classifier. `workbench_catalog` is explicitly *not* the active path — the session already has a library-cache rehydration seam, and two authority paths would be a second store.

### 2. Ownership between `WorkbenchSession` and `ChannelRackController`

| Concern | Owner |
|---|---|
| `library_db_path`, read-only connection, SQL | `WorkbenchLibraryUserSampleMetadataResolver`, constructed in `compose_workbench_session` |
| Resolver injection into the Rack | `WorkbenchSession` (composition boundary) |
| Derived binding storage, invalidation, rebuild | `ChannelRackController` (session-bound runtime state, never persisted) |
| Consumption for projection / seed / reconcile / point-trigger filter / loop specs | `channel_rack` + `loop_rack_playback` (pure, read-only) |
| Playback lifetime | existing `PatternPassPlayer` / `NaturalCycleLoopPlayer` (#926) |

`ChannelRackController` receives an **optional** `user_metadata_resolver` (default `None`). With `None`, every user channel stays `ambiguous` and all #926 behavior is unchanged. The controller may call the resolver **only** at the boundaries in §4.

**Enforced boundary (testable):** `src/channel_rack.py`, `src/loop_rack_playback.py`, `src/workbench_channel_rack.py`, `src/sequencer_playback.py`, and `src/pattern_core.py` must not import `sqlite3`, `workbench_library`, `db`, `config_loader`, or `config`. Guarded by `tests/test_user_channel_classification_authority_contract.py`.

### 3. Canonical path normalization for lookup

Unchanged and non-duplicated: `workbench_library.query_sample_by_path_on_readonly_connection` canonicalizes with `str(Path(p).expanduser().resolve())` internally. The resolver passes raw durable strings in and returns a binding keyed by the same raw strings. A path that cannot be found, resolves to a different file, or fails the fingerprint gate yields `None` ⇒ `ambiguous`.

### 4. Resolution boundaries (exhaustive)

| # | Boundary | Scope | I/O |
|---|---|---|---|
| B1 | `restore_state(...)` | all distinct user-channel paths of the restored state, **one** connection | 1 read-only connection |
| B2 | Any public seam that sets a user channel's path to a **non-empty** value it did not already hold: `add_user_channel(sample_path=...)` and `assign_user_channel_sample(cid, path)` | that one new path | 1 read-only connection |
| B3 | `apply_gesture_integration_plan(...)` after CONSTRUCT TARGET, before STOP | **only the delta**: user-channel paths that the gesture introduces or changes relative to the pre-apply binding | 1 read-only connection |
| B4 | `refresh_user_channel_metadata()` — explicit session seam for library re-analysis / manual rescan | all distinct user-channel paths | 1 read-only connection |
| B5 | `ensure_state()`, `reconcile_live_kit_state()`, `projection()`, `play()`, `tick_playback()` | **never resolves** | 0 |

B2 is defined by the *effect* (a user channel's path becomes a new non-empty value), not by one method name, so no current or future path-bearing user-channel creation seam can bypass resolution. `add_user_channel()` with no path, and `assign_user_channel_sample(...)` with the path the channel already holds, are no-ops and resolve nothing.

B3 resolves the **delta only**. `plan.target_channels` is `base_state.channels + composition.channels`, so resolving every target path would silently re-resolve every preserved base channel and turn a gesture apply into an implicit metadata refresh — contradicting the B4-only refresh policy in §6. Bindings for preserved base channels are carried over untouched; only paths the gesture introduces or changes are resolved.

Restore is one bounded connection for the whole set, never N opens. `rehydrate_live_kit_from_library` remains the Live Kit counterpart and keeps its own single connection.

### 5. Assignment / replacement / clear invalidation

| Event | Binding | Durable state | Playback |
|---|---|---|---|
| `add_user_channel(sample_path=…)` | resolve that path at creation | path set; DEFAULT_ON seeding unchanged from #808 | gated by the new classification; `ambiguous` ⇒ silent |
| empty → path via `assign_user_channel_sample` | replace the channel's key | path set; DEFAULT_ON seeding unchanged from #808 | gated by the new classification; `ambiguous` ⇒ silent |
| path A → path B | drop A if no other channel references it; add B | path = B; that channel's triggers preserved bit-identical | B must resolve explicitly, else silent |
| same path re-assign | no-op | unchanged | unchanged |
| `clear_user_channel_sample(channel_id)` | drop the key | path = `None`; that channel's triggers preserved; unrelated channels and triggers untouched | excluded from both playback paths (non-bearing) |

`clear_user_channel_sample(channel_id)` is a **named public operation that does not exist yet** and is added by the implementation slice. Today `assign_user_channel_sample` rejects `None`, empty, and whitespace paths, so no user channel can be cleared through any callable; the contract must not invent that interface during implementation. Frozen semantics:

- unknown `channel_id` ⇒ `ValueError`, no mutation, no resolution;
- Live Kit seed channel ⇒ `ValueError`, no mutation, no resolution — clearing a seed channel stays a Live Kit operation;
- already-empty user channel ⇒ no-op, no resolution, no observer call;
- otherwise drop the binding, set `sample_path=None`, preserve that channel's existing triggers and every unrelated channel/pattern invariant, and fire the musical-state observer **once**.

Ordering for B2/B3 is frozen as **resolve → build target state (including any classification-implied reconcile) → adopt state → notify once**, so a newly assigned path is never momentarily unclassified-but-playable, and the existing single observer call still holds.

`reconcile_live_kit_sample_assignments` gains the same user-channel reconcile it already performs for seed channels: resolved explicit `loop` ⇒ strip that channel's triggers (deterministic, once); `ambiguous` ⇒ preserve persisted triggers; unrelated channels untouched. **User-channel DEFAULT_ON seeding is not changed by this contract.**

### 6. Library re-analysis

- No implicit refresh. A running Rack Play is never affected, for **both** playback owners.
- The natural-loop specs are already frozen per Play (`_frozen_loop_specs`). Point-trigger eligibility is **not** implicitly frozen by the current pass loop: `_start_pattern_pass` re-plans every pass from live controller state. Therefore this contract adds:

```text
CLASSIFICATION_MUTATION_POLICY = DEFER_UNTIL_NEXT_RACK_PLAY
```

  At the Rack Play anchor the controller snapshots the classification binding used for playback, and every pass of that Play — `filter_pattern_for_point_trigger_playback` and `build_loop_cycle_specs` alike — reads that snapshot, exactly as `sync_enabled`, MASTER BPM, and per-loop `source_bpm` / `playback_rate` are already snapshotted. A binding change during Play therefore cannot add or remove point-trigger eligibility mid-Play either, and cannot stop or restart playback.

```text
CLASSIFICATION_RECONCILE_POLICY = DEFER_UNTIL_NEXT_RACK_PLAY
```

  Snapshotting the binding alone is not sufficient, because `_start_pattern_pass` also re-reads `self._state`: a classification-implied trigger strip (§5) applied mid-Play would strip live state and silence later passes of the same Play. Therefore any classification-implied reconcile of durable Pattern state is **queued while Rack Play is active** and applied only after `stop()`, or at the start of the next explicit Rack Play before its anchor. Mid-Play reconcile is never applied to the state the current Play is reading.

- Projection may continue to read the **live** derived binding, because projection is display and not playback. Mid-Play projection and playback may therefore disagree; the divergence resolves on the next explicit Rack Play and must not be presented as a classification change.
- Refresh happens only through B4, before any next explicit Rack Play.
- Safety is monotonic: a refresh can only move a channel toward what the library currently states. A fingerprint change makes the library return `None`, degrading the channel to `ambiguous` — it can never silently upgrade `ambiguous` to `oneshot`/`loop` without explicit library evidence.

### 7. Observer / autosave semantics

- The binding is derived: **never** serialized, never part of `snapshot_from_musical_state`, never a `SCHEMA_VERSION` change.
- Resolve-only with no state change ⇒ **no** `on_musical_state_changed`, **no** autosave, **no** `persistence_status` transition.
- Resolve + state change (explicit-loop trigger strip) ⇒ exactly **one** observer call, matching today's `reconcile_live_kit_state` semantics.
- Restore performs rehydrate → resolve → rack restore → user-metadata reconcile **before** observers are wired, so resume writes nothing.
- No new persistence-status code is introduced.

### 8. #680 gesture channels consume the same mechanism

Gesture-appended channels are user channels (`live_kit_group is None and live_kit_slot is None`) with a `sample_path`, applied atomically through `apply_gesture_integration_plan`. Because the binding is **path-keyed**, appended channels are covered by the same binding with no per-channel bookkeeping; B3 resolves the gesture-introduced or gesture-changed paths before the atomic replace and carries existing base-channel bindings over untouched. No gesture-specific classification code, no gesture ranking change, no auto-sample selection, no second mechanism.

### 9. `oneshot` / `loop` / `ambiguous`

`classification_kind` / `normalize_sample_class` stay the only classifier; `pred_type` stays display-only.

| Resolved class | Bottom Rack projection | Point-trigger path (#926 owner) | Loop path (#926 owner) |
|---|---|---|---|
| `one_shot` / `oneshot` | `row_kind=step`, step grid enabled, real steps | eligible ⇒ `PatternPassPlayer` | excluded |
| `loop` | `row_kind=loop_identity`, no step grid | excluded | `NATURAL_CYCLE_REPEAT` via `build_loop_cycle_specs` |
| missing DB / catalog miss / stale fingerprint / non-explicit value | `row_kind=loop_identity`, no step grid | **excluded — fail-closed** | **excluded — fail-closed** |

Fail-closed cases preserve persisted Pattern triggers. Pattern Core shapes, `Trigger`, and the default playback rate path are unchanged.

### 10. Frozen contract / regression tests for the implementation slice

The follow-up slice must freeze these before implementation. Today, the ownership subset is already green as architecture guards in `tests/test_user_channel_classification_authority_contract.py`; the rest are red until implementation.

**Already green today (architecture ownership guards):**

1. Low-level Rack/audio modules import no `sqlite3` / `workbench_library` / `db` / config surface, in any import form — relative or absolute `src.`-prefixed, module-level or function-level — plus a non-vacuity self-check proving the guard detects each forbidden form.
2. `snapshot_from_musical_state(...)` contains no `sample_class` key anywhere, recursively.
3. `dataclasses.fields(Channel)` is exactly `(channel_id, live_kit_group, live_kit_slot, sample_path)`; `Trigger` unchanged.
4. `sample_class_for_channel` on a user channel returns `None` for a suggestive filename and with no binding present — no filename/folder heuristic.
5. With no binding, user channels stay excluded from `point_trigger_eligible_channel_ids` and produce no `LoopCycleSpec`.

**Must be red until the implementation slice lands:**

6. Resolver-absent vs resolver-present equivalence: identical state and identical playback decisions when the resolver is not injected.
7. Binding keyed by the exact durable path string; a stale-key lookup is `ambiguous`, not silent playback.
8. Restore resolves all user-channel paths through one read-only connection (assert connection-open count ≤ 1) and never writes.
9. Assign (empty → path) to an explicit oneshot makes the channel point-trigger eligible; to an explicit loop makes it loop-eligible; to a miss stays silent.
10. Replacement A → B invalidates A immediately and never leaves the channel audible under A's class.
11. `clear_user_channel_sample(channel_id)` drops the association, preserves that channel's and every unrelated channel's triggers, and fires the observer once; unknown `channel_id`, Live Kit seed channel, and already-empty user channel all reject or no-op without mutation, resolution, or an observer call.
12. Explicit `loop` reconciles stale user-channel triggers once; `ambiguous` preserves them.
13. Resolve-only emits no musical-state observer call and no autosave; resolve + loop strip emits exactly one.
14. User loop + SYNC-on with a valid bound `source_bpm` builds a loop spec; missing/invalid BPM stays fail-closed.
15. `apply_gesture_integration_plan` resolves only the gesture-introduced or gesture-changed paths, leaves preserved base-channel bindings byte-identical, and keeps the single-observer guarantee.
16. `add_user_channel(sample_path=…)` and `assign_user_channel_sample(...)` are both resolution boundaries; `add_user_channel()` with no path and a same-path re-assign resolve nothing.
17. `CLASSIFICATION_MUTATION_POLICY`: a binding change during active Rack Play changes neither point-trigger eligibility nor loop specs for any pass of that Play, does not stop or restart playback, and applies on the next explicit Rack Play.
18. `CLASSIFICATION_RECONCILE_POLICY`: a B4 refresh during active Rack Play that would strip triggers does **not** touch the state the current Play is reading; no pass of that Play goes silent, and the queued strip lands after `stop()` or at the next explicit Rack Play before its anchor.
19. #926 regression suites stay green: `tests/test_channel_rack_loop_classification.py`, `tests/test_workbench_channel_rack_loop.py`, `tests/test_loop_rack_playback.py`, `tests/test_workbench_session_catalog_rehydrate.py`, `tests/test_workbench_session_persistence.py`.

## Explicit non-goals

- A second classifier, new ML, or any classification-quality change (owned by #946).
- Any change to `sample_class` / `pred_type` production in `analyze` / `classify`.
- Pattern Core or session-JSON schema changes.
- A new playback path, transport, or engine feature.
- Arranging, clip launcher, QML gesture workflow, microphone, Arrangement.
- Changing user-channel DEFAULT_ON seeding semantics.
- Touching gesture ranking logic or introducing auto-sample selection.

## Follow-up implementation slice (exactly one)

**Title:** `[RUNTIME][#936] Inject Workbench-library user-sample classification into the Channel Rack`
**Tracked as:** [#952](https://github.com/jannekbuengener/sample-brain/issues/952)

**Required order (no phase may be skipped):**

```text
DOCS -> TESTS -> TEST FREEZE -> IMPLEMENTATION -> CHECKS
```

1. **DOCS** — this freeze is the DOCS_GATE artifact; confirm it against live `main` before code.
2. **TESTS** — land tests 6–19 above (initially red where they must be red).
3. **TEST FREEZE** — freeze tests 6–19. Tests 1–5 may only ever be tightened.
4. **IMPLEMENTATION** — add `src/workbench_user_sample_metadata.py`; thread the optional `user_metadata` binding through `channel_rack` and `loop_rack_playback` as keyword-only, default `None`; inject the resolver in `compose_workbench_session`; implement B1–B4 including the B3 delta rule, the named `clear_user_channel_sample(...)` operation, the reconcile/observer rules, and the per-Play playback snapshot behind `CLASSIFICATION_MUTATION_POLICY` plus the queued reconcile behind `CLASSIFICATION_RECONCILE_POLICY`.
5. **CHECKS** — focused tests, the listed regression suites, then `python -m pytest -q`, `python -m ruff check .`, `python -m py_compile`, and `python tools/check_canon_drift.py`.

**Out of scope for that slice:** classification-quality changes (#946), Pattern Core or session-JSON changes, QML redesign, Arrangement, gesture ranking changes, user-channel DEFAULT_ON changes.

## Relationship to other contracts

| Contract | Relationship |
|---|---|
| Loop Row Playback (#920 / #926) | Supplies the two playback owners and the fail-closed matrix; this freeze only decides who resolves classification for user channels. |
| Session Ownership | Unchanged: Python session composition owns the injected resolver; QML stays projection + intent. |
| Pattern Core | Shapes unchanged; user channels continue to reference a sample path only. |
| #680 Gesture slices | Unchanged ranking/action logic; appended channels consume the same path-keyed binding. |
| #946 Analysis quality | Owns measured `sample_class` correctness. This contract consumes its output unchanged. |

## Exit

Done for #936 when this ownership freeze is reviewed and accepted. Runtime work requires explicit GO on the single follow-up slice above.
