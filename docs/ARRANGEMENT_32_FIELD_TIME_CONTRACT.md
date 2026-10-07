# Arrangement 32-Field / 8-Bar Time Contract — Sample Brain

**Status:** ACTIVE_SUPPORTING — musical time contract freeze for [#1083](https://github.com/jannekbuengener/sample-brain/issues/1083).  
**Class:** ACTIVE_SUPPORTING  
**Exit marker:** `ARRANGEMENT_32_FIELD_TIME_CONTRACT_FROZEN`  
**Parent:** [#679](https://github.com/jannekbuengener/sample-brain/issues/679) Arrangement owner  
**Depends on:** [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076) Edit → Arrangement → later Live product canon  
**Persistence plane:** [#1082](https://github.com/jannekbuengener/sample-brain/issues/1082) track package ownership (what is stored integrates there; this issue does not invent a second store)  
**Arrangement model consumer:** [#1084](https://github.com/jannekbuengener/sample-brain/issues/1084)  
**Runtime implementation owner:** [#1086](https://github.com/jannekbuengener/sample-brain/issues/1086)  
**Machine-readable companion:** [`arrangement_32_field_time_v1.json`](arrangement_32_field_time_v1.json)

This issue freezes the **smallest musical time contract** shared by Arrangement and the sequencer. It does **not** authorize Pattern/Channel Rack runtime changes, QML, Arrangement masks, or migration execution.

```text
ARRANGEMENT_32_FIELD_TIME_CONTRACT_FROZEN
```

## Normative contract vs future runtime

| Plane | Authority | What it is |
|---|---|---|
| **Normative contract schema** | This document + [`arrangement_32_field_time_v1.json`](arrangement_32_field_time_v1.json) | Time signature, field→quarter mapping, loop interval, 16-bar projection, TempoMap scheduling chain, legacy/DEFAULT_ON migration outcomes, fail-closed cases, later #1086 vectors |
| **Future runtime** | [#1086](https://github.com/jannekbuengener/sample-brain/issues/1086) | 32-field Pattern timing, loop scheduling verification, migration execution, serialize/restore integrated with #1082/#1085 |

`docs/arrangement_32_field_time_v1.json` is **not** runtime serialization (`not_runtime_serialization = true`).

## Scope

In scope:

- Freeze `4/4`, `4 fields/bar`, `8 bars/cycle`, `32 fields`, `1 quarter note/field`
- Exact field `0..31` → quarter-note mapping and cycle boundary at qn `32`
- 16-bar Arrangement block as two projections of one 8-bar Pattern identity
- TempoMap-only field→frame scheduling authority
- Evidence-based legacy 16-step / DEFAULT_ON migration outcomes (including HOLD / `migration_required`)
- Persistence *concepts* required for time truth (not a second store)
- Machine-testable contract vectors for this freeze

Out of scope (explicit):

- Changes to `src/pattern_core.py`, `src/channel_rack.py`, `src/session_grid.py`, `src/sequencer_playback.py`, `src/workbench_session_store.py`
- QML / Arrangement UI / groups / masks / markers
- 64-field sequencer, alternate second-half Pattern variants, finer input grids
- Live MIDI / multi-track
- Runtime migration execution and playback-loop verification (#1086)

## Authorities

| Concern | Authority |
|---|---|
| Musical grid / tempo→frame | `TempoMap` in `src/session_grid.py` |
| Pattern / Trigger identities + exact `Fraction` positions | `src/pattern_core.py` (Python-owned) |
| Current 16-step rack behavior (legacy evidence) | `src/channel_rack.py` |
| One-pass plan → engine frames | `plan_pattern_once` in `src/sequencer_playback.py` |
| Track package / durable persistence plane | #1082 / runtime #1085 |
| 32-field runtime + migration execution | #1086 |
| Arrangement blocks/groups/masks | #1084 (consumes this timebase; does not redefine it) |
| Source `BeatGrid` | Analysis / edit evidence only — **not** the Pattern clock |

## Live seam inventory (evidence; do not rewrite)

Verified against current `main` (includes #1082 / PR #1091):

| Seam | Live fact |
|---|---|
| `TempoMap` | Exact `Fraction` quarter-note ↔ frame mapping; one direct `round` from segment anchor |
| `Pattern.length_quarter_notes` | Exact `Fraction`; triggers satisfy `0 <= position < length` |
| `Trigger.position` | Exact quarter-note `Fraction` |
| Channel Rack v1 | `DEFAULT_STEP_COUNT = 16`, `DEFAULT_PATTERN_LENGTH = Fraction(4, 1)`, DEFAULT_ON at `Fraction(i, 4)` |
| Musical meaning of v1 rack | 16 sixteenth-note steps inside **one** 4/4 bar |
| Session store v2 | Persists `pattern_id`, `length_quarter_notes`, `step_count`, channels, triggers with exact Fraction positions |
| Workbench transport sample rate | Canonical adapter default **48000** Hz (`WorkbenchTransportAdapter`) |

**Critical:** the old 16-step rack must **not** be silently reinterpreted as the new 32-field / 8-bar semantics.

## Exact math

Owner-bound v1:

```text
time signature:     4/4
fields per bar:     4
bars per Pattern:   8
fields total:       32
Pattern cycle:      8 bars
Arrangement block:  16 bars = same 8-bar Pattern repeated twice
64 fields:          NOT V1
```

Derived:

```text
1 bar = 4 quarter notes
4 fields / bar
=> 1 field = 1 quarter note

field i -> quarter-note position i    for i = 0..31
cycle length = 32 quarter notes
```

## Field mapping

| Field | Quarter note | Bar (0-based) | Field in bar |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 |
| 3 | 3 | 0 | 3 |
| 4 | 4 | 1 | 0 |
| 7 | 7 | 1 | 3 |
| 8 | 8 | 2 | 0 |
| 15 | 15 | 3 | 3 |
| 16 | 16 | 4 | 0 |
| 31 | 31 | 7 | 3 |

Encoding: field `i` → `Fraction(i, 1)`.

Bar starts (field indexes): `0, 4, 8, 12, 16, 20, 24, 28`.

There is **no** field index `32` inside a cycle. Field `31` is the last in-cycle field.

## Loop semantics

Cycle interval (half-open):

```text
[0, 32 quarter notes)
```

The boundary point at quarter-note `32` is **bar 9 start / next cycle start**. It does **not** belong to the previous cycle.

### Scheduling invariant

Events for cycle `N` occupy absolute musical positions in `[N*32, (N+1)*32)`.

A Pattern-local trigger at position `p` with `0 <= p < 32` schedules **once** per cycle at absolute quarter `N*32 + p`.

The point `qn = (N+1)*32` is exclusively the start of cycle `N+1`. Planning must **not** double-schedule:

- the last event of cycle `N`, and
- the first event of cycle `N+1`

as if both belonged to the same cycle pass.

Runtime verification of loop playback is owned by #1086.

## 16-bar Arrangement projection

An Arrangement block has **no second Pattern truth**.

```text
Pattern P
  length = 32 quarter notes
  8 bars

Arrangement block (16 bars / 64 quarter notes):
  bars 1–8   -> Pattern P, cycle 0   (field n -> qn n)
  bars 9–16  -> Pattern P, cycle 1   (field n -> qn 32+n)
```

Invariants:

- one Pattern identity
- no copied second-half Pattern state
- no 64-field persistence
- no QML mirror state as musical truth
- a Step/field mutation changes the single Pattern truth and therefore every projection that references it

#1084 may consume this projection. #1083 owns the time semantics only.

## TempoMap scheduling contract

Chain:

```text
field
  → exact quarter-note position
  → TempoMap.quarter_note_to_frame
  → engine frame
```

Forbidden:

```text
field → hardcoded milliseconds
BeatGrid → Pattern clock
QML wall-clock → musical authority
```

On tempo change:

- stored musical positions remain unchanged
- future frame mapping changes through `TempoMap`
- Pattern positions are **not** rewrite-mutated

Rounding: reuse existing `TempoMap` semantics (one direct `Fraction.__round__` from the segment anchor; nearest integer, ties-to-even). Do not redefine rounding here.

### Representative frame mappings

Canonical Workbench sample rate for these contract vectors: **48000** Hz.

| qn | frame @ 120 BPM | frame @ 140 BPM |
|---:|---:|---:|
| 0 | 0 | 0 |
| 3 | 72000 | 61714 |
| 4 | 96000 | 82286 |
| 7 | 168000 | 144000 |
| 8 | 192000 | 164571 |
| 15 | 360000 | 308571 |
| 16 | 384000 | 329143 |
| 31 | 744000 | 637714 |
| 32 | 768000 | 658286 |

These values are machine-pinned in [`arrangement_32_field_time_v1.json`](arrangement_32_field_time_v1.json) and must match live `TempoMap` at the same inputs.

## Persistence ownership boundary

#1083 defines **musical time truth**. #1082 owns the track-package / persistence plane.

This contract requires that durable musical state eventually record:

- Pattern identity
- exact musical trigger positions (`Fraction` quarter notes)
- 32-field / 8-bar semantic version marker
- migration state where necessary

It must **not**:

- invent a second persistence store
- persist a 64-field view as truth
- persist a duplicated second-half Pattern
- treat a QML bar cache as musical truth

Schema / writer implementation belongs to #1086 integrated with #1082 / #1085.

## Legacy 16-step migration result

### Legacy musical meaning (evidence)

```text
16 steps
1 bar
step spacing = 1/4 quarter note
pattern length = 4 quarter notes
DEFAULT_ON positions = Fraction(i, 4) for i in 0..15
```

### New musical meaning

```text
32 fields
8 bars
field spacing = 1 quarter note
pattern length = 32 quarter notes
field i = Fraction(i, 1)
```

### Forbidden auto-migrations (no proof)

- `index × 2` or any index×factor remapping
- blind trigger copy into 32 fields
- spreading 16 steps across 32 fields
- replicating the Pattern eight times
- silently rounding fractional triggers onto fields
- silently reinterpreting canonical DEFAULT_ON as the new 32-field grid

### Field-aligned predicate

A trigger position `p` is **field-aligned** iff `p` is an exact non-negative integer `Fraction` and `0 <= p < 32`.

### Deterministic outcomes

| Outcome | When | Action |
|---|---|---|
| `migrated_empty` | Recognized legacy v1 shape (`step_count=16`, `length_quarter_notes=4`) with **zero** triggers | Set length=`32`, field/step count=`32`; keep empty triggers; preserve `pattern_id` / channels |
| `migrated_field_aligned_bar_replicated` | Recognized legacy v1 shape; **every** trigger position is an exact integer `Fraction` in `[0, 4)` | Set length=`32`, field/step count=`32`. For each legacy trigger at `p` and each bar offset `k` in `0..7`, emit the same channel at exact `p + 4*k` (dedupe identical pairs). This **preserves one-bar loop cadence**: legacy `length=4` fired every bar; unreplicated length extension would fire only once per 8-bar cycle and is **forbidden** |
| `migration_required` | Recognized legacy v1 with any off-grid trigger (including canonical DEFAULT_ON), or parseable legacy that cannot auto-migrate without reinterpretation | Do **not** activate 32-field truth automatically; leave legacy recoverable; no rounding / stretch / 32 DEFAULT_ON invention |
| `migration_hold` | Ambiguous mapping; legacy trigger outside old Pattern bounds; user-added unknown legacy step semantics | Fail closed / HOLD; #1086 must not invent a mapping |
| `reject_fail_closed` | Unknown/malformed `step_count`, corrupt payload, malformed types, invalid Pattern length under activated 32-field semantics | Reject; no silent musical repair |

Cadence note: recognized legacy v1 Patterns are one-bar loops (`length_quarter_notes=4`). Extending length alone without bar tiling is a silent rhythm change and must not be labeled lossless. Bar tiling applies only to proven field-aligned integer positions inside that one-bar window; it does not authorize blind 8× replication of off-grid / DEFAULT_ON / non-v1 shapes.

### Canonical DEFAULT_ON v1

Canonical DEFAULT_ON produces 16 positions:

`0, 1/4, 1/2, 3/4, 1, …, 15/4`

Only four of those (`0, 1, 2, 3`) are field-aligned. Forcing integer fields would be **lossy**. Therefore classification is exactly:

```text
canonical_default_on_v1 → migration_required
auto_expand_to_32_default_on → FORBIDDEN
```

## DEFAULT_ON handling (new vs historical)

Distinguish three planes:

1. **Historical persisted / in-memory DEFAULT_ON v1** → `migration_required` (above). Must not become 32 triggers automatically.
2. **New initialization under future 32-field semantics** → does **not** inherit the legacy 16-step DEFAULT_ON policy. Fresh oneshot / loop / ambiguous / empty / user-added channels initialize with **empty triggers** (no phantom seeds). A denser future seed needs a separate explicit owner decision.
3. **Manually edited all-off patterns** → remain empty; no phantom reseed on migration or mode activation.

## Fail-closed contract

At minimum, reject or HOLD (no silent coercion) for:

- `field < 0`
- `field >= 32`
- malformed field type
- trigger at/outside qn `32` in one-cycle truth of length 32
- invalid Pattern length under activated 32-field semantics (`!= 32`)
- unknown / malformed legacy `step_count`
- legacy Trigger outside old Pattern bounds → `migration_hold`
- ambiguous legacy mapping → `migration_required` or `migration_hold`
- corrupt persistence payload
- user-added channels with unknown legacy state → `migration_hold`
- any 64-field state presented as v1 truth

## Validation vectors

### Contract-plane (this issue / tests)

Pinned by `tests/test_arrangement_32_field_time_contract.py` against the JSON + Markdown freeze (not runtime):

1. 4/4
2. 4 fields/bar
3. 8 bars
4. 32 fields
5. 1 qn/field
6. field `0..31` mapping
7. 4-field bar boundaries
8. qn `32` cycle boundary
9. no field `32` inside cycle
10. 16-bar block = two projections of same Pattern ID
11. second repetition offset = 32 qn
12. block length = 64 qn
13. 64-field state forbidden
14. TempoMap authority
15. BeatGrid not Pattern clock
16. legacy migration policy explicit
17. DEFAULT_ON legacy handling explicit
18. unsupported legacy state fail-closed / HOLD
19. no second persistence owner
20. #1084 / #1086 ownership references correct

Representative TempoMap frames at 48000 Hz / 120 & 140 BPM are also pinned in the JSON companion.

### Later runtime (#1086)

Runtime frame scheduling, playback loop, serialize/restore, and migration **execution** remain #1086 tests. Required later vectors are enumerated in the JSON under `required_later_runtime_vectors`.

## Cross-contract ownership

| Issue | Owns |
|---|---|
| #1082 | Track package / persistence plane |
| #1083 (this) | Musical time / field mapping / loop / migration *policy* |
| #1084 | Arrangement blocks, groups, masks, song boundary (consumes this timebase) |
| #1085 | Track package runtime |
| #1086 | 32-field Pattern timing runtime + migration execution |

## Explicit out of scope

- Runtime implementation of the 32-field model
- Arrangement UI, groups/masks, markers, Live
- 64-field sequencer
- Alternate second 8-bar Pattern variants
- Finer sequencer input grids than 1 field = 1 quarter note
