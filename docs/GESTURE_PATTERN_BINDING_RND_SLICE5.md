# Gesture Pattern Binding Plan R&D — Slice 5 (#680 / #891)

**Status:** R&D contract frozen; implementation delivered. See post-implementation result.

**Parent:** [#680](https://github.com/jannekbuengener/sample-brain/issues/680)
**Child:** [#891](https://github.com/jannekbuengener/sample-brain/issues/891)
**Dependencies (DONE):** [#827](https://github.com/jannekbuengener/sample-brain/issues/827), [#882](https://github.com/jannekbuengener/sample-brain/issues/882), [#886](https://github.com/jannekbuengener/sample-brain/issues/886), [#888](https://github.com/jannekbuengener/sample-brain/issues/888)

## Goal

Freeze and prove the smallest deterministic **Pattern-binding plan** that joins delivered ranking + catalog + timing evidence into explicit channel/sample/event binding intent **before** any `Pattern`, `Channel`, or `Trigger` object is created.

```text
GestureTimingProjection
  + ClusterRanking (Top-N)
  + LibraryCandidate pool
  + explicit cluster_id → sample_id selections
  + existing_channel_ids
  + explicit pattern_length_quarters: Fraction
  → plan_gesture_pattern_binding(...)
  → GesturePatternBindingPlan
```

## Live foundation (verified on `origin/main` @ `bb5c1168`)

| Surface | Fact |
|---------|------|
| Ranking `#882` | `ClusterRanking` / `RankedCandidate`; `distance` is measured L2, **not** confidence; rank 1 ≠ approved choice |
| Catalog `#886` | `LibraryCandidate.sample_id` + `path`; read-only adapter; no writes |
| Timing `#888` | `ProjectedGestureEvent.quarter_position: Fraction`; event-specific; unquantized; source `t=0` origin; `projected_duration_quarters` evidence only |
| Pattern Core | `allocate_user_channel_id(Iterable[str])` → first free `ch_user_N`; always unions canonical Live Kit IDs; `Trigger.position` exact `Fraction`; Pattern end exclusive |
| Channel Rack | `add_user_channel(sample_path=...)` seeds DEFAULT_ON 16th-note triggers — **forbidden** as gesture-binding seam |
| Concurrent PR | [#889](https://github.com/jannekbuengener/sample-brain/pull/889) draft QML/theme — do not touch those paths; `docs/CANON_INDEX.md` not edited |

## Architecture boundary (hard)

| Domain | Authority |
|--------|-----------|
| Ranking / Top-N | `#882` — consume only; no recompute |
| Catalog candidates | `#886` / caller-supplied pool — no DB in this seam |
| Timing quarters | `#888` — preserve exact positions and event order |
| Channel ID allocation | `pattern_core.allocate_user_channel_id` |
| Pattern length | **explicit caller** `Fraction` |
| Sample choice | **explicit caller** `cluster_id → sample_id` |

This slice does **not** authorize:

- automatic rank-1 / confidence thresholds / fallback ranks
- Pattern / Channel / Trigger / `ChannelRackState` construction
- `channel_rack.add_user_channel` or DEFAULT_ON seeding
- Live Kit Kick/Snare/Hat / slot mapping
- automatic Pattern length from duration / last onset / bars / defaults
- quantization / snap / swing / groove
- BPM inference
- ranking or timing recomputation
- DB writes
- QML / UI / microphone

## Ownership decision: dedicated pure planner

**Chosen:** `src/gesture_pattern_binding.py` (absent at `TEST_FREEZE`).

**Rejected for this slice:**

- Calling `channel_rack.add_user_channel` (DEFAULT_ON 16ths overwrite exact `#888` quarters).
- Auto-selecting `RankedCandidate.rank == 1` when selection is missing.
- Deriving Pattern length from `projected_duration_quarters`.
- Mapping clusters onto Live Kit taxonomy.

## Public seam (smallest clear form)

Module: `src/gesture_pattern_binding.py` (absent at `TEST_FREEZE`).

```text
plan_gesture_pattern_binding(
    timing: GestureTimingProjection,
    rankings: Sequence[ClusterRanking],
    candidates: Sequence[LibraryCandidate],
    selections: Mapping[int, str],
    existing_channel_ids: Collection[str],
    *,
    pattern_length_quarters: Fraction,
) -> GesturePatternBindingPlan
```

Arguments are explicit. No DB path, no hidden global rack state, no session singleton.

### Immutable result models

```text
PlannedGestureChannelBinding (frozen)
  cluster_id: int
  channel_id: str
  sample_id: str
  sample_path: str
  selected_rank: int                 # copied from RankedCandidate.rank
  distance: float                    # copied measured distance; NOT confidence

PlannedGestureEventBinding (frozen)
  cluster_id: int
  channel_id: str
  quarter_position: Fraction         # exact #888 position; type(x) is Fraction

GesturePatternBindingPlan (frozen)
  channel_bindings: tuple[PlannedGestureChannelBinding, ...]
  event_bindings: tuple[PlannedGestureEventBinding, ...]
  unresolved_cluster_ids: tuple[int, ...]
  pattern_length_quarters: Fraction
  ready_for_pattern: bool
```

Ordering freezes:

- `channel_bindings` sorted by ascending `cluster_id`
- `unresolved_cluster_ids` sorted ascending
- `event_bindings` preserve `#888` timing **event order** (source truth; planner must not sort/reorder timing events)

## Frozen decisions

### 1. Sample-selection authority — explicit, never auto-rank-1

Caller supplies `cluster_id → sample_id`.

Valid selection requires:

1. `sample_id` appears in that cluster's current `ClusterRanking.ranked`
2. exactly one matching `LibraryCandidate` in the supplied pool
3. candidate `path` is a non-empty `str`

Otherwise fail closed for that selection path.

**Missing selection** for a known timing/ranking cluster:

- cluster enters `unresolved_cluster_ids`
- no channel binding
- no event binding
- `ready_for_pattern = False`
- **do not** auto-pick rank 1

Selection for an unknown cluster → fail closed.

### 2. Cluster → channel

- One **selected** cluster → one newly planned user channel
- Repeated events of the same cluster reuse that planned `channel_id` and sample
- Distinct `cluster_id`s remain distinct channels
- Same `sample_id` / path across two clusters → still two channels (no merge by sample)
- No Live Kit / semantic drum roles

### 3. Channel allocation authority

Caller supplies `existing_channel_ids: Collection[str]`.

Validate:

- each ID is a non-empty `str`
- IDs unique
- deterministic semantics for identical inputs

Allocate only for **selected** clusters, in ascending `cluster_id` order:

```text
existing = set(existing_channel_ids)
for cluster_id in sorted(selected_clusters):
    channel_id = allocate_user_channel_id(existing)
    existing.add(channel_id)
```

Reuse public `pattern_core.allocate_user_channel_id` (internally unions canonical Live Kit IDs). No `Channel` object creation.

### 4. Pattern-length authority — explicit Fraction

`pattern_length_quarters` must satisfy:

- `type(value) is Fraction`
- `value > 0`

Reject int / float / str / bool / zero / negative.

Every timing event (including those belonging to unresolved clusters) must satisfy:

```text
0 <= quarter_position < pattern_length_quarters
```

Fail closed on `position == length` or `position > length`. No loop extension, bar rounding, or quantization.

### 5. Source duration relationship

`GestureTimingProjection.projected_duration_quarters` remains evidence only. It may equal, be shorter than, or be longer than Pattern length as long as all event positions fit. Do not rewrite either value. Trailing silence policy is caller/product authority.

### 6. Repeated events

Every `#888` projected event remains an event. Same cluster → same planned channel; multiple exact event bindings; positions unchanged. No dedupe / collapse / snap / step conversion.

### 7. Cluster-set consistency

Timing cluster IDs and ranking cluster IDs must match **exactly**.

Fail closed on:

- missing ranking for a timing cluster
- extra / stale ranking cluster
- duplicate ranking cluster IDs

Selection keys must be a subset of that known set.

### 8. Ranking / candidate validation

For each selected cluster:

- selected sample appears exactly once in that cluster ranking
- copy `rank` (positive int) and finite `distance` as evidence
- no re-ranking, no prototype / z-score / L2 / Top-N recompute

Candidate pool:

- unique non-empty `sample_id` strings
- selected path non-empty `str`
- duplicate `sample_id` → fail closed
- no DB query in this seam

### 9. Same sample across clusters

Allowed. Distinct channels; same path permitted. Cluster identity is the role boundary.

### 10. Unresolved event bindings

Unresolved cluster:

- entry in `unresolved_cluster_ids`
- **no** channel binding
- **no** event binding
- plan `ready_for_pattern = False`

Not silent data loss: readiness is explicit; future composer must refuse non-ready plans. No placeholder channel IDs.

### 11. Readiness contract

`ready_for_pattern == True` only when:

- every timing cluster is represented in rankings
- every timing cluster has explicit valid selection
- every selected sample validates
- all event positions fit Pattern length
- channel allocation succeeds
- all structural invariants pass

If any cluster is unresolved → `ready_for_pattern = False`.

### 12. Input order / permutation semantics

| Input | Ordering authority |
|-------|--------------------|
| Timing events | `#888` source order — **preserve**; do not sort/reorder; **do not** require permutation invariance of timing event order |
| Selection mapping | semantic map; insertion-order permutation must not change plan |
| Candidate pool | unordered for identity; order permutation must not change plan |
| Ranking sequence | cluster identity by `cluster_id`; duplicate IDs fail closed; planned channels sorted by `cluster_id` |

### 13. Immutability / determinism

Planner must not mutate timing / rankings / candidates / selections / existing IDs. Same inputs → identical plan.

### 14. Import / ownership boundary

May import: dataclasses, fractions, collections/typing, gesture timing types, gesture ranking types, `pattern_core.allocate_user_channel_id`.

Must **not** construct/import for production construction: `Pattern`, `Trigger`, `Channel`, `ChannelRackState`. Must not call `channel_rack.add_user_channel`.

Tests may assert Pattern-Core `Trigger(position=...)` compatibility TEST-ONLY from planned Fractions.

## Fail-closed validation matrix (summary)

| Condition | Result |
|-----------|--------|
| missing selection for known cluster | unresolved; not ready |
| selection unknown cluster | fail closed |
| selected sample not in cluster Top-N | fail closed |
| selected sample missing / empty path | fail closed |
| duplicate candidate IDs | fail closed |
| duplicate / mismatched ranking clusters | fail closed |
| non-Fraction / ≤0 Pattern length | fail closed |
| any timing event `position >= length` | fail closed (incl. unresolved) |
| invalid / non-unique existing channel IDs | fail closed |
| non-finite ranking distance / nonpositive rank | fail closed |

## Future Pattern composer boundary

A later slice may compose `Channel` + `Trigger` + `Pattern` from a **ready** plan only. Non-ready plans must be rejected. That composer must still not invent selection, length, quantization, or DEFAULT_ON semantics.

**Forward link:** Slice 6 (#893) freezes that pure composition contract in
`docs/GESTURE_PATTERN_CORE_COMPOSITION_RND_SLICE6.md` (`compose_gesture_pattern_core`
→ `GesturePatternCoreComposition`). Composition still does not mutate
`ChannelRackState`.

## Quality / evidence boundary

| Label | Meaning |
|-------|---------|
| MEASURED | copied rank/distance, paths, exact quarters, allocated IDs, readiness |
| HEURISTIC | none introduced (no auto sample choice) |
| NOT YET CLAIMED | producer-quality match, automatic selection, final Pattern generation, UI |

## R&D exit (after later implementation)

Exactly one of:

- `EXPLICIT_SELECTION_BINDING_PLAN_VIABLE`
- `PATTERN_BINDING_CONTRACT_INSUFFICIENT`
- `INSUFFICIENT_EVIDENCE`

**Viable means only:** ranking + catalog + timing can be deterministically joined into a Pattern-Core-compatible plan under explicit sample selection and explicit Pattern length.

It does **not** mean automatic sample choice, producer-quality matching, final Pattern generation, or UI are validated.

Parent `#680` stays OPEN.

## Acceptance tests

See `tests/test_gesture_pattern_binding_891.py` (frozen at `TEST_FREEZE`).

## Non-goals

No automatic rank1, confidence calibration, Pattern/Channel/Trigger creation, ChannelRack mutation, DEFAULT_ON, Live Kit slot mapping, semantic drum labeling, automatic Pattern length, quantization, BPM inference, DB writes, QML/UI/mic, Arrangement, `docs/CANON_INDEX.md` churn, PR `#889` theme/QML paths.

## Post-implementation result

| Field | Value |
|-------|-------|
| Implementation seam | `src/gesture_pattern_binding.py` → `plan_gesture_pattern_binding(...)` |
| Immutable models | `PlannedGestureChannelBinding`, `PlannedGestureEventBinding`, `GesturePatternBindingPlan` (`frozen=True`) |
| Measured tests | Focused `tests/test_gesture_pattern_binding_891.py`: **61 passed**; protected ranking/catalog/timing/pattern/channel-rack/DEFAULT_ON/sequencer group: **222 passed** |
| R&D EXIT | `EXPLICIT_SELECTION_BINDING_PLAN_VIABLE` |
| Quality claim | `BINDING_PLAN_ONLY — FINAL_PATTERN_GENERATION_NOT_YET_VALIDATED` |
| Limitation boundary | No auto rank-1, no Pattern/Channel/Trigger creation, no DEFAULT_ON / Channel Rack mutation, no ranking/timing recompute; parent `#680` remains OPEN |
