# Arrangement Block / Group / Mask Contract — Sample Brain

**Status:** ACTIVE_SUPPORTING — Arrangement domain contract freeze for [#1084](https://github.com/jannekbuengener/sample-brain/issues/1084).  
**Class:** ACTIVE_SUPPORTING  
**Exit marker:** `ARRANGEMENT_BLOCK_GROUP_MASK_CONTRACT_FROZEN`  
**Parent:** [#679](https://github.com/jannekbuengener/sample-brain/issues/679) Arrangement owner  
**Depends on:** [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076) product canon; [#1083](https://github.com/jannekbuengener/sample-brain/issues/1083) 32-field / 8-bar time contract  
**Consumes time contract:** [#1083](https://github.com/jannekbuengener/sample-brain/issues/1083) — no second time authority  
**Consumes persistence plane:** [#1082](https://github.com/jannekbuengener/sample-brain/issues/1082) track package ownership (opaque key `arrangement`); lifecycle runtime [#1085](https://github.com/jannekbuengener/sample-brain/issues/1085)  
**Runtime implementation owner:** [#1087](https://github.com/jannekbuengener/sample-brain/issues/1087)  
**QML projection owner:** [#1080](https://github.com/jannekbuengener/sample-brain/issues/1080)  
**Machine-readable companion:** [`arrangement_block_group_mask_v1.json`](arrangement_block_group_mask_v1.json)

This issue freezes the **smallest Python-owned Arrangement model contract** for v1: 16-bar blocks, four presentation groups with stable channel identities, separate group/track masks, bounded song time, and an explicit end marker. It does **not** authorize runtime implementation, QML, render-format, Live, MIDI, automation, mixer, or piano-roll work.

```text
ARRANGEMENT_BLOCK_GROUP_MASK_CONTRACT_FROZEN
```

## Normative contract vs future runtime

| Plane | Authority | What it is |
|---|---|---|
| **Normative contract schema** | This document + [`arrangement_block_group_mask_v1.json`](arrangement_block_group_mask_v1.json) | Block identity, default-on sparse state, presentation groups, membership, masks, end marker, cap, render eligibility, fail-closed outcomes, later #1087 vectors |
| **Future runtime** | [#1087](https://github.com/jannekbuengener/sample-brain/issues/1087) | Arrangement domain model implementation, migration execution, serialize/restore under #1082/#1085 |
| **QML projection** | [#1080](https://github.com/jannekbuengener/sample-brain/issues/1080) | Visual projection/intent only — never musical truth |

`docs/arrangement_block_group_mask_v1.json` is **not** runtime serialization (`not_runtime_serialization = true`).

## Scope / owners

**In scope (#1084):**

- Arrangement block identity / index
- Pattern reference semantics (consume #1083)
- Bounded default-on block model
- Presentation group identities
- Channel → presentation-group membership contract
- Group masks and track/channel masks
- Effective playback precedence
- Migration / reconciliation of older group structures
- End-marker / song-boundary state
- 10-minute logical/render safety cap
- Complete-song render eligibility predicate

**Out of scope:**

- Pattern timing redefinition → #1083 / runtime #1086
- Track package / persistence authority → #1082 / runtime #1085
- Runtime implementation → #1087
- Visual design → #1079
- QML → #1080
- Final render file format, MIDI, Live, automation, mixer, piano roll
- Final Vocals slot distribution
- Alternate Pattern variants per block / second half
- Analysis `StructureV1` / `ArrangementClassifier` conflation

## Time-contract consumption (#1083)

Use #1083 exactly. No new time truth.

```text
Pattern:            8 bars / 32 fields / 32 quarter notes
Arrangement block:  16 bars / 64 quarter notes
block N start:      64 * N quarter notes
block N interval:   [64*N, 64*(N+1))
```

Each initial Arrangement block references the **same** Pattern identity. Two Pattern projections per block:

```text
first half:  absolute offset 0 qn
second half: absolute offset 32 qn
```

No copied second Pattern truth. No 64-field Pattern state. A Step edit mutates that one Pattern and therefore appears in every active repetition that references it.

TempoMap (`src/session_grid.py`) remains the sole tempo → wall-clock / frame authority.

## Block model and identity

Prefer the simplest deterministic contract: **zero-based deterministic `block_index`**.

Properties:

- `block_index` is an exact non-bool integer `>= 0`
- Deterministic from timeline position: `block_start_qn = block_index * 64`
- Exact 16-bar / 64-qn segment: `[64*N, 64*(N+1))`
- Not display-name-based
- No random block UUIDs in v1
- Invalid / negative / non-integer indices fail closed (no musical mutation)
- Visual zoom / viewport open/close does **not** create or delete musical blocks
- No infinite-materialization model

### Structural validity (independent of end marker)

`block_index` is structurally valid when it is an exact non-bool integer `>= 0`.

Missing end marker does **not** make `block_index` structurally invalid. An Arrangement may exist before the user sets an end marker.

### Current horizon eligibility

The hard 10-minute bound is evaluated with the current TempoMap:

```text
TempoMap(block_start_qn) < 600 seconds
```

A block may be considered for current Arrangement use when its **start** is inside that window. The final visible/active block span **may overlap** the 600s boundary; the end marker owns the song boundary. Do **not** require the complete 16-bar block to end within 600s — that would forbid a legal end marker inside the last block.

Horizon eligibility is not UI viewport width and not a fixed BPM multiplier.

### Persisted state after tempo changes

If a previously horizon-eligible block later maps outside the current 600s window after a tempo change:

- do **not** delete stored masks / overrides
- do **not** auto-move or clamp
- do **not** rewrite block indices
- treat as `out_of_current_horizon` (or repo-equivalent)
- no musical mutation solely because of tempo change

Musical intent data stays stable; eligibility is re-evaluated.

## Default-on + bounded sparse state

New valid Arrangement time ranges are default-on, but serialization must stay bounded.

```text
default block_enabled = true
default group_enabled = true
default track_enabled = true

persist ONLY explicit exceptions:
  disabled_blocks
  disabled_group_blocks
  disabled_track_blocks
```

Identical state must serialize deterministically (stable sort order). Viewport open/close/zoom must not mutate musical state. No infinite list of `enabled=true` blocks.

**Unmapped membership is not a mask entry.** It belongs in separate membership / migration reconciliation state. Do not mix membership with group mask or track mask.

## Presentation groups (stable identities)

Four top-level presentation groups:

| Contract ID | Display label (projection only) |
|---|---|
| `pg_baseline` | Baseline |
| `pg_drums` | Drums |
| `pg_melodic_atmos_fx` | Melodic / Atmos / FX |
| `pg_vocals` | Vocals |

Group identity is a stable contract constant, independent of display copy. Do **not** slugify IDs from visible labels. Display labels remain projection metadata. No fifth visible product group in v1.

## Canonical Channel → Group mapping

Reuse existing stable Pattern Core channel IDs (`src/pattern_core.py`). Mapping is by channel ID, not Live Kit display group strings.

| Group ID | Channel IDs |
|---|---|
| `pg_baseline` | `ch_kick`, `ch_bass` |
| `pg_drums` | `ch_main_drum`, `ch_closed_hat`, `ch_open_hat`, `ch_percussion`, `ch_additional` |
| `pg_melodic_atmos_fx` | `ch_lead`, `ch_pad`, `ch_atmos`, `ch_fx` |
| `pg_vocals` | *(empty / unassigned — valid)* |

Empty Vocals is a valid v1 state. Do **not** invent vocal channels. Do **not** rename existing channels.

Legacy Live Kit labels (`Kick + Bass`, split `Melodic` + `Atmos / FX`) are migration input only; reconciliation uses stable `ch_*` IDs.

## Unknown / user channel policy

User-added channels (`ch_user_*` and any channel without authoritative membership) must not be lost.

If membership is not authoritatively proven, do **not** auto-assign from filename, display label, folder name, or sample-class heuristics.

For a musically populated unmapped channel:

```text
presentation_membership = unmapped
membership_resolution = migration_required
arrangement_membership_resolved = false
```

Preserve fully:

- channel ID
- assignment
- trigger / Pattern state
- track-owned musical state

### Unmapped is not a silent playback fallback

Until explicit membership exists, Arrangement must **not**:

- silently assign the channel to `pg_baseline`, `pg_drums`, `pg_melodic_atmos_fx`, or `pg_vocals`
- invent a surrogate group with `group_enabled = true`
- silent-mute as an allegedly successful migration
- silent-play under an invented group
- treat complete-song render as successful while musically relevant unmapped channels remain unresolved

Operations that need unambiguous group-mask semantics remain controlled fail-closed / `migration_required` until membership is resolved. Runtime [#1087](https://github.com/jannekbuengener/sample-brain/issues/1087) implements that migration/resolution state.

## Group mask vs track mask

Strictly separate per block:

```text
group_enabled(group_id, block_index)
track_enabled(channel_id, block_index)
```

Plus block enablement from the sparse default-on model.

### Effective playback precedence

Evaluate `effective(channel, block)` **only** for channels with resolved presentation membership.

For resolved channels:

```text
effective(channel, block)
=
block_enabled(block)
AND group_enabled(group_id, block)
AND track_enabled(channel_id, block)
```

For unmapped channels:

```text
effective = unresolved
```

Do **not** pretend `true` or `false`.

Invariants:

- Group toggle must not mutate track mask
- Track toggle must not mutate group mask
- If track X was OFF, then group OFF → group ON: track X remains OFF

## Expand / collapse

Expand/collapse is pure presentation. It never changes:

- group mask
- track mask
- Pattern
- Arrangement
- playback truth
- end marker
- membership

Zero musical mutation. Expand state is not musical domain truth.

## End marker (song boundary)

v1 snap rule (closes the previously open gate):

```text
end_marker_qn % 4 == 0
```

Whole-bar snap under the frozen #1083 `4/4` contract (`1 bar = 4 quarter notes`).

Marker state:

- stored as musical quarter-note position (`end_marker_qn`, Fraction-compatible), not milliseconds or pixels
- Python-owned Arrangement truth
- Track-owned persistence under the #1082 opaque `arrangement` key; lifecycle #1085
- **No second store**
- Visual drag/snap UI is later QML scope (#1080)

Zero-duration complete render must not count as successful song output. No silent coercion onto bar 1 / bar 2.

### Tempo change + end marker

```text
end_marker_qn remains unchanged
```

Wall-clock / render duration is recomputed via TempoMap. Never auto-move the marker musically. No silent clamp.

If a tempo change makes the mapped marker duration exceed 600 seconds:

- persist the musical position unchanged
- treat marker as `invalid/out_of_range` for complete render
- `render_eligible = false`
- user must correct marker/tempo explicitly later

## 10-minute cap

Hard cap: **600 seconds**, evaluated through the current TempoMap / musical-time mapping.

Not pixel width. Not a fixed BPM multiplier. Not UI viewport. An Arrangement may visually show roughly three minutes first; that is not domain truth.

Marker mapped duration `> 600s` → fail closed / render ineligible (qn preserved).

## Render eligibility

Freeze the predicate only (no render format).

`render_eligible = true` only when **all** hold:

- end marker present
- marker structurally valid
- marker bar-snapped (`end_marker_qn % 4 == 0`)
- resulting song duration `> 0`
- current TempoMap duration `<= 600s`
- Arrangement contract state otherwise valid
- no unresolved musically relevant presentation membership
- no other fail-closed mask/identity inconsistency

Without a valid marker: `render_eligible = false`.  
A musically populated `unmapped` channel must not disappear from a supposedly successful complete render.

## Persistence ownership

| Concern | Owner |
|---|---|
| Arrangement semantics (this contract) | #1084 |
| Track package opaque key reservation `arrangement` | #1082 |
| Persistence lifecycle / serialize-restore runtime | #1085 |
| Arrangement domain runtime | #1087 |

Do not invent a second musical persistence authority.

## Migration / reconciliation

Existing Live Kit / Channel state must not be destructively rewritten by visible group names.

Required:

- Kick/Bass → `pg_baseline` by channel ID
- existing Drums IDs → `pg_drums`
- Lead/Pad/Atmos/FX → `pg_melodic_atmos_fx`
- old state without Vocals remains valid (empty `pg_vocals`)
- unknown legacy labels do not lose assignment
- unknown channels are not guessed (`unmapped` / `migration_required`)
- no destructive rename migration

## Fail-closed outcomes

| Case | Outcome |
|---|---|
| Invalid / negative / non-integer `block_index` | fail closed; no musical mutation |
| Unknown group ID | fail closed; no musical mutation |
| Unknown channel ID for mask ops | fail closed; no musical mutation |
| Unknown Pattern ID | fail closed |
| Corrupt mask payload | fail closed |
| Membership-dependent op on unmapped channel | `migration_required` / fail closed |
| Marker not bar-snapped | structurally invalid; render ineligible |
| Marker mapped `> 600s` | keep qn; `invalid/out_of_range`; render ineligible |
| Missing end marker | render ineligible (blocks remain structurally valid) |
| Zero-duration marker | render ineligible |
| Unresolved musical membership | render ineligible |
| Block `out_of_current_horizon` after tempo change | keep persisted overrides; no auto mutation |

No silent coercion that changes music.

## Required later runtime vectors (#1087)

These are contract-expected results for #1087 — not pretended runtime tests in this slice:

1. first block defaults on without persisted entry
2. later block defaults on
3. group OFF persists restore
4. track OFF persists restore
5. group OFF→ON preserves track OFF
6. expand/collapse changes no musical state
7. invalid block index mutates nothing
8. invalid group ID mutates nothing
9. invalid channel ID mutates nothing
10. canonical legacy grouping migrates by Channel ID
11. no-Vocals old state restores valid
12. unknown user channel not lost/remapped
13. legal marker round-trip
14. marker after tempo change keeps qn
15. marker mapped `>600s` becomes ineligible
16. absent marker prevents complete render
17. corrupt masks fail closed
18. identical state serializes deterministically
19. unmapped populated channel → `effective = unresolved`
20. unmapped populated channel blocks complete render
21. missing marker does not invalidate structural `block_index`
22. horizon eligibility from `block_start` via TempoMap; overlapping final block allowed
23. tempo change can yield `out_of_current_horizon` without deleting masks

## Live seam inventory (evidence; do not rewrite)

| Seam | Live fact |
|---|---|
| #1083 time contract | Frozen; `block_bars: 16`, `block_length_quarter_notes: 64`, consumer #1084 |
| #1082 package contract | Reserves opaque `arrangement` key for #1084 semantics |
| `src/pattern_core.py` | Eleven frozen `ch_*` IDs + `ch_user_*` allocator |
| `src/workbench_live_kit.py` | Display groups `Kick + Bass` / `Drums` / `Melodic` / `Atmos / FX` — migration input only |
| `LiveKitPresentationState` | Expand/collapse presentation; not musical mask truth |
| `TempoMap` | Exact Fraction quarter ↔ frame mapping |
| Vocals channels | None authoritatively present — empty `pg_vocals` is correct |

## Absolute out of scope for this freeze

No changes to `src/**`, `*.qml`, Arrangement/Pattern/Track-Package/Render runtime, MIDI, Live, automation, mixer, piano roll, final Vocals slot distribution, or product-copy invention.
