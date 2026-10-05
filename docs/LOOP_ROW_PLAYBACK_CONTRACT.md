# Loop Row Playback Contract — Sample Brain

**Status:** ACTIVE_SUPPORTING — contract freeze for [#920](https://github.com/jannekbuengener/sample-brain/issues/920); Owner/Lead review pending before any runtime implementation.  
**Class:** ACTIVE_SUPPORTING  
**Parent:** [`WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md`](WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md) (§9), [#905](https://github.com/jannekbuengener/sample-brain/issues/905), [#908](https://github.com/jannekbuengener/sample-brain/issues/908)  
**Depends on:** [`PATTERN_CORE_CONTRACT.md`](PATTERN_CORE_CONTRACT.md), [`SEQUENCER_PLAYBACK_CONTRACT.md`](SEQUENCER_PLAYBACK_CONTRACT.md), [`SESSION_OWNERSHIP_CONTRACT.md`](SESSION_OWNERSHIP_CONTRACT.md)

This document freezes loop / sustained-sample Rack projection and playback semantics. It does **not** authorize product code, QML changes, a new loop engine, Arrangement, clips, or #908 rework in this slice.

## Architecture outcome

```text
LOOP_ROW_DISTINCT_PROJECTION_REQUIRED
```

Point-trigger `Trigger` remains correct for one-shot / point-trigger-safe rows. It is **not** a musically or operationally sufficient sole representation for loop-class Rack rows under current DEFAULT_ON + multi-pass Channel Rack playback.

Frozen loop playback mode for explicit `sample_class=loop`:

```text
NATURAL_CYCLE_REPEAT
```

Live-code evidence (`schedule_voice_start`, finite PCM → IDLE, control-thread create/stop/remove, absolute engine-frame planning already used by `PatternPassPlayer`) supports controller-owned absolute cycle starts without a native PCM wrap mode. Therefore this contract freezes `NATURAL_CYCLE_REPEAT` as the binding v1 loop semantics — **not** start-once-to-EOF as a finished loop definition.

`SUSTAINED_PHRASE_START_ONCE` is **not** the accepted loop freeze. It remains only a rejected interim sketch from the first draft.

## Live evidence summary (code-backed)

Verified against `origin/main` at freeze time (`c693d792`):

| Surface | Fact |
|---|---|
| `Trigger` (`src/pattern_core.py`) | Point fire only: `(channel_id, position)`. No duration, stop, sustain, or latch. |
| DEFAULT_ON (`src/channel_rack.py`) | Every sample-bearing channel seeds 16 triggers `Fraction(0..15, 4)` regardless of `sample_class`. |
| Sequencer (`src/sequencer_playback.py`) | Each planned trigger → `create_voice` + `schedule_voice_start`; `VoiceConfig.initial_rate = 1.0` (no RATE_SYNC on rack path). Absolute engine-frame lookahead already exists. |
| Native PCM (`native/audio`) | Finite PCM to EOF → `SB_VOICE_IDLE`. Public API: `schedule_start`, immediate `stop`. No Sample Brain PCM wrap/loop mode. No scheduled stop/release. At `rate=1.0`, audible length equals `pcm_frame_count` output frames. At constant rate `r`, position advances by `r` per output frame until EOF. |
| Channel Rack Play (`src/workbench_channel_rack.py`) | Controller-owned succession of finite pattern passes (#810). Pass restart re-plans oneshot triggers. Loop lifetime must **not** be owned by pass succession. |
| Classification | `Channel` has no `sample_class`. Authority lives on `WorkbenchRow.sample_class` via Live Kit assignment; persistence path-refs hydrate class best-effort from library. |
| #908 projection | `one_shot`/`oneshot` → `row_kind=step`; `loop` or ambiguous → `row_kind=loop_identity` (no step grid). |
| Persistence (`src/workbench_session_store.py`) | Live Kit path refs, Rack channels, Pattern triggers, MASTER/SYNC. No persisted `sample_class` field on Channel. |
| Audition SYNC (`src/workbench_transport_preview.py` + `compute_sync_playback_rate`) | Non-oneshot + SYNC on requires valid source BPM; otherwise fail-closed. RATE_SYNC only on audition path today. |
| Native availability | Rack Play already routes through native sequencer seams; no Rack OS/preview fallback exists and none is authorized here. |

## Core answers

1. **What a loop means today:** Catalog/`sample_class` taxonomy (`loop` vs one-shot). Rack Play still treats any sample-bearing channel as DEFAULT_ON point triggers. Audition may RATE_SYNC non-oneshots when BPM is valid. There is no Rack-owned loop-cycle layer yet.
2. **Is `Trigger` suitable alone?** Suitable for oneshot start instants. Unsuitable as the sole loop model under DEFAULT_ON, step-grid UX, and pattern-pass restart.
3. **Trigger lifecycle today:** create voice → schedule start → play → EOF → IDLE (not auto-removed) → reclaim/`stop`/`remove` on control thread. Pattern boundary does not stop an already-playing voice; the next pass can schedule another start.
4. **Native loop/repeat/sustain:** Not exposed as PCM wrap. Repeat is achievable by scheduling successive finite voices at absolute cycle boundaries.
5. **Stop/release seams:** Immediate `sb_voice_stop` / `stop_voice` yes. Scheduled stop/release FFI: no (not required for natural-cycle repeat).
6. **Sample length:** Measurable via decode / duration helpers / `pcm_frame_count`; required for cycle duration. Not stored on `Channel`.
7. **BPM metadata:** `WorkbenchRow.bpm` (and session master tempo). Not on `Channel`.
8. **RATE_SYNC / KEY_LOCK on Rack today:** Sequencer path uses `initial_rate=1.0`. Audition uses RATE_SYNC + fail-closed BPM for non-oneshots. Loop v1 reuses RATE_SYNC for cycle duration when SYNC on; KEY_LOCK not required.
9. **Missing source BPM under SYNC:** Fail-closed — no loop start, no invented tempo.
10. **Pattern length vs source length:** Pattern length does **not** own loop lifetime in v1. Pattern-pass boundaries are irrelevant to loop cycle boundaries.
11. **Too large for v1:** Sustained Pattern regions; clip launcher; timeline/Arrangement; native PCM wrap mode; scheduled-stop FFI; bar-length heuristics; invented 1/2/4/8-bar metadata.
12. **Minimal producer-viable deterministic v1:** Distinct loop-row projection + controller-owned `NATURAL_CYCLE_REPEAT` + non-destructive classification/restore rules + native-only fail-closed path.

## Alternatives compared

### A. Point-trigger loop (reuse `Trigger` only)

Rejected as sole model: DEFAULT_ON / pass restart / step-grid coupling remain musically wrong for sustained loop material.

### B. Sustained span / region (start + musical duration)

Correct for clip-like material; too large for v1 (Pattern Core duration/stop, region projection).

### C. Launch / latched loop outside step triggers

Risks a second transport owner / clip-launcher matrix. Rejected for v1.

### D. Distinct loop row + NATURAL_CYCLE_REPEAT (chosen)

- Distinct QML row kind (`loop_identity`)
- Classification-gated playback owned by Python
- First start at Rack Play anchor
- Successive finite PCM voices at absolute natural cycle boundaries while Play is active
- No step grid, no DEFAULT_ON contribution, no PatternPassPlayer retrigger for loop rows
- No new transport owner, no PCM wrap dependency

### Rejected interim: SUSTAINED_PHRASE_START_ONCE

One start → natural EOF → silence while Rack Play continues is **not** accepted as finished `loop` semantics. A 4-bar loop must continue across later pattern passes until Stop.

## Frozen v1 semantics

### Classification authority

| Class (normalized) | Row kind | Rack Play contribution |
|---|---|---|
| `one_shot` / `oneshot` | `step` | Existing point-trigger Pattern path (with restore rules below) |
| `loop` | `loop_identity` | `NATURAL_CYCLE_REPEAT` (below) |
| missing / ambiguous / other | `loop_identity` | **Fail-closed playback:** identity + audition only; **no** loop auto-start; **no** point-trigger Rack playback; **no** step grid |

Normalization matches #908: strip, lower, `-` → `_`. Authority is `WorkbenchRow.sample_class` on the Live Kit assignment (or an explicit future user-channel classification seam). `pred_type` is display/search only — not row-kind authority.

### Measurable inputs

- `sample_class` (assignment / hydrated library row)
- source path / PCM availability / `pcm_frame_count`
- source BPM (`WorkbenchRow.bpm`) when SYNC applies
- master BPM + `sync_enabled` (transport)
- play-anchor engine frame (Channel Rack Play session)
- native engine availability

Pattern `length_quarter_notes` is **not** a loop-cycle input in v1.

### Deterministically derived

- row kind / playback gate from classification
- RATE_SYNC rate = `master_bpm / source_bpm` when SYNC on and BPM valid/finite and rate in `[0.25, 4.0]`
- `effective_cycle_duration_frames` from source frame count + playback rate (see Cycle Boundary)
- absolute cycle start frames: `play_anchor + cycle_index * effective_cycle_duration_frames`

### Heuristics

None in v1. No invented BPM, no guessed bar length, no silent auto-wrap, no recursive rounded duration accumulation.

### Loop playback mode: NATURAL_CYCLE_REPEAT (explicit `loop` only)

| Rule | Freeze |
|---|---|
| First start | Exactly at the Rack Play anchor engine frame |
| Lifetime owner | `ChannelRackController` (not PatternPassPlayer, not QML, not a new transport) |
| Pattern DEFAULT_ON / step triggers | Forbidden for explicit `loop` channels |
| Step Grid | Forbidden |
| PatternPassPlayer retrigger | Forbidden for loop channels |
| Voice model | Finite PCM voices remain allowed; **no** PCM wrap / engine loop mode required |
| Repeat while Play active | After natural EOF of cycle `i`, cycle `i+1` starts at the computed absolute boundary; repeats continuously until Stop |
| Cycle boundary formula | Always `start(i) = play_anchor + i * effective_cycle_duration_frames` for integer `i >= 0`. Never accumulate rounded per-cycle deltas recursively |
| Pattern length | Does **not** own loop lifetime; pattern-pass boundaries are irrelevant to cycle starts |
| Overlap | At most one currently sounding loop voice per channel; at most necessary future scheduling ownership; **no** self-stacking |
| Stop | User Stop / #916 audio-focus transfer stops and clears all owned current/future loop voices via existing control-thread seams |
| Bar metadata | Not required; no 1/2/4/8-bar invention |

### Cycle Boundary

| SYNC | Cycle duration |
|---|---|
| Off | `effective_cycle_duration_frames = pcm_frame_count` at `rate = 1.0` |
| On | Valid finite source BPM required; `rate = compute_sync_playback_rate(master, source, sync_on)` (RATE_SYNC only — no second clamp algorithm); `effective_cycle_duration_frames = ceil(pcm_frame_count / playback_rate)` so absolute starts match native finite-PCM EOF under constant rate |
| On + invalid/missing BPM | Fail-closed: no start |

Runtime must prove zero cycle-frame drift over many repetitions by using the absolute formula above. KEY_LOCK_SYNC is not required for loop-row v1.

### Mutation policy during active Rack Play (Lead freeze)

| Policy | Value | Behavior |
|---|---|---|
| `LOOP_TRANSPORT_MUTATION_POLICY` | `DEFER_UNTIL_NEXT_RACK_PLAY` | On Play, snapshot `sync_enabled`, MASTER BPM, per-loop source BPM, `playback_rate`, and `effective_cycle_duration_frames`. Mid-play MASTER/SYNC changes must not retune sounding/scheduled loop voices or rewrite cycle frames. Stop→Play rebuilds. |
| `LOOP_ASSIGNMENT_MUTATION_POLICY` | `DEFER_UNTIL_NEXT_RACK_PLAY` | Live Kit assign during Play does not stop play and must not hot-swap loop PCM for the current Play; frozen loop specs continue until Stop. New assignment/class semantics apply on the next explicit Rack Play. |

### SYNC semantics (loop rows)

| Condition | Behavior |
|---|---|
| SYNC off | rate 1.0; natural PCM frame length owns cycle duration |
| SYNC on + valid BPM + rate in range | RATE_SYNC; effective cycle frames from source frames + rate |
| SYNC on + missing/invalid BPM | Fail-closed; do not start; do not invent tempo |
| KEY_LOCK_SYNC | Not required for loop-row v1 |

One-shot Rack triggers remain on the existing sequencer rate=1.0 path unless a later separate sync issue changes that contract.

### Native availability (Rack loop)

Rack loop playback has **no** legacy OS/preview fallback.

| Condition | Behavior |
|---|---|
| Native playback unavailable | Loop Rack playback **fail-closed**, whether SYNC is on or off |
| Native available + other gates pass | `NATURAL_CYCLE_REPEAT` may start |

Do not invent a Rack preview fallback path.

### Pattern Core / Trigger interaction

- Pattern Core `Trigger` / `Channel` / `Pattern` shapes stay unchanged.
- Explicit `loop` channels must not receive new DEFAULT_ON seeds and must not contribute point triggers to `plan_pattern_once` / `PatternPassPlayer` during Rack Play.
- Ambiguous channels must not contribute point-trigger Rack playback while classification remains unknown.
- Oneshot DEFAULT_ON + `toggle_step` semantics stay unchanged for **new** explicit oneshot assignments (see restore policy).
- Sequencer non-goals remain: no Arrangement, no piano-roll note lengths, no clip timeline.

### QML projection

- Keep `row_kind=loop_identity` and `step_grid_enabled=false` for non-point-trigger-safe rows (#908).
- QML may show identity and later a thin enable/armed affordance only as intent into Python.
- QML must not own cycle timing, rate, BPM invention, or pass/cycle policy.
- No fake step cells for loops.

### Classification / persistence / restore policy (non-destructive)

Persisted today: Live Kit path refs, Rack channels, Pattern triggers, MASTER/SYNC. `sample_class` is best-effort rehydrated from the library and may be missing after restore.

| Situation | Required behavior |
|---|---|
| Classification securely `loop` | No step grid; no DEFAULT_ON seed; no point-trigger playback contribution. Stale loop-channel triggers from older sessions **may** be deterministically reconciled/cleared once explicit `loop` classification is known. |
| Missing / ambiguous classification | Fail-closed playback: identity only; no loop auto-start; no point-trigger Rack playback; no step grid. **Do not** delete existing persisted Pattern triggers merely because metadata/catalog/library DB is missing. Preserve state until classification is known. |
| Restored session already has persisted triggers + library hydration later confirms `one_shot`/`oneshot` | Keep existing triggers **bit-identical**. Do **not** auto-reseed DEFAULT_ON solely because metadata hydrated. Respect manual all-off / edited patterns. |
| New explicit oneshot assignment (true new assign semantics) | Existing DEFAULT_ON seeding may apply (unchanged #677/#806 policy). |
| Ambiguous → later hydrated `loop` | Deterministic transition into loop gate + safe stale-trigger reconcile for that channel. |
| Ambiguous → later hydrated oneshot | Preserve already-persisted edits; no destructive rewrite; no automatic DEFAULT_ON reseed from hydration alone. |

Do not encode loop arming as a 16-step trigger list. Optional later `loop_enabled` is not required to freeze this contract.

### State ownership

| Concern | Owner |
|---|---|
| Kit assignment + `sample_class` / bpm | `LiveKitState` / `WorkbenchRow` |
| Pattern triggers (oneshots) | `ChannelRackState` / Pattern Core |
| Loop cycle scheduling / ownership | `ChannelRackController` (extend; not a new transport) |
| Tempo / SYNC flags | `WorkbenchTransportAdapter` |
| Voice schedule/stop/remove | Native engine via existing control-thread seams |
| Projection | QML only |

## Fail-closed matrix

| Case | Required behavior |
|---|---|
| `sample_class` unknown / ambiguous | Identity only; no step grid; no loop auto-start; no point-trigger Rack playback; **preserve** persisted triggers |
| Source BPM missing + SYNC on | Do not start loop voice |
| Source BPM `<= 0` / NaN / Inf + SYNC on | Do not start loop voice |
| Source duration / PCM missing | Soft skip that channel; no crash |
| Pattern shorter or longer than source | Allowed; pattern length does not cut or pad the loop cycle |
| Source not bar-aligned | Allowed; no forced bar snap |
| SYNC off + native available + class=`loop` | `NATURAL_CYCLE_REPEAT` at rate 1.0 |
| SYNC on + valid BPM + native available | `NATURAL_CYCLE_REPEAT` with RATE_SYNC cycle duration |
| Native playback unavailable | Fail-closed for loop Rack playback (**SYNC on or off**) |
| User channel without classification seam | Treat as ambiguous |

## Explicit non-goals

- Arrangement / timeline / clips / scenes / launcher matrix
- Mixer / automation / piano roll / external DAW
- Generalized track model / cloud / ML loop analysis
- Native PCM wrap-loop mode as a v1 dependency
- Scheduled stop FFI as a v1 dependency
- Bar-length heuristics / invented 1/2/4/8-bar metadata
- Changing oneshot DEFAULT_ON musical meaning for new assignments
- Redesigning #908 geometry
- Rack OS/preview fallback for loop playback
- Selling start-once-to-EOF as finished loop semantics

## Follow-up implementation slice (exactly one)

**Issue title (suggested):** `[RUNTIME][#920] Deterministic natural-cycle Loop Rack playback`

**Scope:**

1. Classification-aware seed/playback filter: explicit oneshot only on point-trigger path; explicit `loop` excluded from DEFAULT_ON / PatternPassPlayer contribution; ambiguous excluded from both loop auto-start and point-trigger playback.
2. Non-destructive persistence/hydration transition rules exactly as frozen above.
3. Controller-owned loop cycle scheduler:
   - first start at Rack Play anchor
   - repeat at absolute `play_anchor + i * effective_cycle_duration_frames`
   - RATE_SYNC cycle duration when SYNC on
   - fail-closed on invalid metadata or native unavailable
   - Stop / #916 focus cleanup of current and future owned loop voices
   - max one sounding voice per loop channel; no self-overlap
4. No Pattern Core shape change; no QML redesign; no PCM wrap dependency; no Arrangement/clip launcher.

**Required tests (minimum):**

1. Persisted oneshot pattern + library hydrate success → triggers bit-identical.
2. Persisted pattern + missing library DB → no destructive trigger deletion.
3. Persisted stale triggers + explicit loop classification → excluded from point-trigger playback; stale loop trigger state safely reconciled.
4. Ambiguous → later hydrated loop → deterministic transition.
5. Ambiguous → later hydrated oneshot → existing persisted edits preserved.
6. Finite loop continues across multiple Rack pattern passes (e.g. 4-bar-equivalent source while 1-bar/pattern passes advance).
7. No duplicate/pass-boundary retrigger for loop channels.
8. No self-overlap.
9. No cycle-frame drift over many repetitions (absolute boundary formula).
10. Stop clears current/future loop ownership.
11. #916 audio-focus invariant remains green.
12. Oneshot PatternPass path unchanged.

**Out of scope for that slice:** PCM wrap-loop engine, scheduled stop FFI, sustained Pattern regions, Arrangement, #908 layout redesign, preview fallback.

## Relationship to other contracts

| Contract | Relationship |
|---|---|
| Pattern Core | Unchanged shapes; trigger membership / reconcile policy for loop vs ambiguous vs oneshot restore is owned here |
| Sequencer Playback | One-pass player remains oneshot/point-trigger oriented; loop cycles are controller-owned absolute schedules, not PatternPass forever-loop API |
| Session Ownership | Python remains musical authority; QML projection + intent; #916 focus stop clears owned loop voices |
| Single Workspace | §9 resolved by this freeze; geometry remains #908 |

## Exit

Done for #920 contract work when this document is Owner/Lead-approved (Draft PR path) and the architecture outcome plus `NATURAL_CYCLE_REPEAT` freeze above are binding. Runtime work requires a separate GO on the follow-up slice.
