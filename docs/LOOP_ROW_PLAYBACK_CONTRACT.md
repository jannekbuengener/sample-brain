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

## Live evidence summary (code-backed)

Verified against `origin/main` at freeze time (`c693d792`):

| Surface | Fact |
|---|---|
| `Trigger` (`src/pattern_core.py`) | Point fire only: `(channel_id, position)`. No duration, stop, sustain, or latch. |
| DEFAULT_ON (`src/channel_rack.py`) | Every sample-bearing channel seeds 16 triggers `Fraction(0..15, 4)` regardless of `sample_class`. |
| Sequencer (`src/sequencer_playback.py`) | Each planned trigger → `create_voice` + `schedule_voice_start`; `VoiceConfig.initial_rate = 1.0` (no RATE_SYNC on rack path). |
| Native PCM (`native/audio`) | Finite PCM to EOF → `SB_VOICE_IDLE`. Public API: `schedule_start`, immediate `stop`. No Sample Brain PCM wrap/loop mode. No scheduled stop/release. |
| Channel Rack Play (`src/workbench_channel_rack.py`) | Controller-owned succession of finite pattern passes (#810). Pass restart re-plans triggers. |
| Classification | `Channel` has no `sample_class`. Authority lives on `WorkbenchRow.sample_class` via Live Kit assignment. |
| #908 projection | `one_shot`/`oneshot` → `row_kind=step`; `loop` or ambiguous → `row_kind=loop_identity` (no step grid). |
| Persistence (`src/workbench_session_store.py`) | Channels + triggers + master_bpm/sync_enabled. No loop-arm field. Path restore may lose class until library hydrate. |
| Audition SYNC (`src/workbench_transport_preview.py` + `compute_sync_playback_rate`) | Non-oneshot + SYNC on requires valid source BPM; otherwise fail-closed. RATE_SYNC only on audition path today. |

## Core answers

1. **What a loop means today:** Catalog/`sample_class` taxonomy (`loop` vs one-shot). Rack Play still treats any sample-bearing channel as DEFAULT_ON point triggers. Audition may RATE_SYNC non-oneshots when BPM is valid. There is no Rack-owned sustained/loop layer semantics yet.
2. **Is `Trigger` suitable alone?** Suitable for the *start instant* of a natural-length fire. Unsuitable as the *only* model when DEFAULT_ON, 16-step UX, and pass restart would retrigger or imply step-grid editing for sustained material.
3. **Trigger lifecycle today:** create voice → schedule start → play → EOF → IDLE (not auto-removed) → reclaim/`stop`/`remove` on control thread. Pattern boundary does not stop an already-playing voice; the next pass can schedule another start.
4. **Native loop/repeat/sustain:** Not exposed on the Sample Brain voice API. miniaudio looping exists only as third-party capability, not a product seam.
5. **Stop/release seams:** Immediate `sb_voice_stop` / `stop_voice` yes. Scheduled stop/release at a future engine frame: no.
6. **Sample length:** Measurable via decode/`read_audio_duration_ms` / catalog `duration`; required for PCM create. Not stored on `Channel`.
7. **BPM metadata:** `WorkbenchRow.bpm` (and session master tempo). Not on `Channel`.
8. **RATE_SYNC / KEY_LOCK for loop material on Rack:** Not applied on sequencer/rack schedule path (`initial_rate=1.0`). Audition uses RATE_SYNC + fail-closed BPM for non-oneshots. KEY_LOCK exists for synthetic/key-lock paths; not a Rack loop v1 requirement.
9. **Missing source BPM:** Audition fail-closes under SYNC for non-oneshots. Rack path currently ignores SYNC and plays at rate 1.0.
10. **1/2/4/8-bar source vs pattern length:** No Rack rule today. Pattern length does not truncate voices; pass restart can overlap longer sources.
11. **Theoretically correct but too large:** Sustained span/region in Pattern Core; clip launcher; timeline/Arrangement; PCM wrap-loop engine; scheduled release FFI; generalized track model.
12. **Minimal producer-viable deterministic v1:** Distinct loop-row projection + one start-per-Play natural-length voice + no DEFAULT_ON + no pass retrigger + audition-aligned SYNC fail-closed + Stop via existing `stop_voice`.

## Alternatives compared

### A. Point-trigger loop (reuse `Trigger` only)

| Concern | Assessment |
|---|---|
| Natural length | Viable if single start → EOF |
| Pattern restart | Multi-pass retriggers unless excluded — musically wrong for long loops |
| Overlap | Longer-than-pattern sources stack voices across passes |
| Pattern length mismatch | No truncate; silent musical mismatch if DEFAULT_ON remains |
| Repeat | No native PCM wrap; fake step-repeat is incorrect |
| Usefulness | Low while DEFAULT_ON + step-grid semantics remain coupled |

**Verdict:** Not viable as the sole contract without becoming a distinct policy that no longer behaves like oneshot triggers.

### B. Sustained span / region (start + musical duration)

Requires Pattern Core duration/stop events, persistence shape change, scheduler stop planning, and QML region projection. Correct for clip-like material; **out of scope** for smallest v1 and drifts toward note/clip models.

### C. Launch / latched loop outside step triggers

Useful as a layer idea, but risks a second transport owner / clip-launcher matrix. Rejected for v1.

### D. Minimal distinct loop row (chosen)

- Distinct QML row kind (already `loop_identity` under #908)
- Explicit classification-gated playback policy owned by Python
- One start per Rack Play session at the play-anchor frame
- Natural PCM length to EOF
- No step grid, no DEFAULT_ON, no pass retrigger, no new transport owner

## Frozen v1 semantics

### Classification authority

| Class (normalized) | Row kind | Rack Play contribution |
|---|---|---|
| `one_shot` / `oneshot` | `step` | Existing point-trigger Pattern / DEFAULT_ON path |
| `loop` | `loop_identity` | Distinct loop-start policy below |
| missing / ambiguous / other | `loop_identity` | **Fail-closed:** identity + audition only; **no** Rack loop auto-start; **no** step grid |

Normalization matches #908: strip, lower, `-` → `_`. Authority is `WorkbenchRow.sample_class` on the Live Kit assignment (or an explicit future user-channel classification seam). `pred_type` is display/search only — not row-kind authority.

### Measurable inputs

- `sample_class` (assignment)
- source path / PCM availability
- source duration (decode / duration helpers)
- source BPM (`WorkbenchRow.bpm`) when SYNC applies
- master BPM + `sync_enabled` (transport)
- pattern `length_quarter_notes` (context only; does not own loop lifetime in v1)
- play-anchor engine frame / quarter (Channel Rack Play session)

### Deterministically derived

- whether the row is point-trigger-safe vs loop vs fail-closed identity
- expected RATE_SYNC rate = `master_bpm / source_bpm` when SYNC on and BPM valid/finite and rate in `[0.25, 4.0]`
- whether metadata is sufficient to start under SYNC

### Heuristics

None in v1. No invented BPM, no guessed bar length, no silent auto-wrap.

### Playback (explicit `loop` only)

| Rule | Freeze |
|---|---|
| Start when | Rack Play begins: exactly one start at the play-session anchor frame (pass index 0 start) |
| How often | Once per Play session per loop channel |
| Voice lifetime | Natural PCM length to EOF |
| Pattern pass restart (#810) | Must **not** schedule another start for that loop channel while the same Play session is active |
| Overlap | At most one live voice per loop channel; no self-stacking across passes |
| Stop | User Stop / audio-focus transfer uses existing control-thread `stop_voice` + owned cleanup; EOF → IDLE then reclaim |
| Pattern-length rule | Pattern length does **not** truncate or extend the loop voice in v1 |
| PCM wrap / sample-looping | Forbidden in v1 |
| Retrigger from step cells | Forbidden (no step grid for loop rows) |

### SYNC semantics

Align with audition fail-closed behavior; do not invent a third policy:

| Condition | Behavior |
|---|---|
| SYNC off | `initial_rate = 1.0` |
| SYNC on + valid finite source BPM + rate in range | RATE_SYNC (`master/source`) |
| SYNC on + missing/invalid BPM (`None`, `<=0`, NaN/Inf) | Fail-closed: do **not** start that loop voice; do not invent tempo |
| KEY_LOCK_SYNC | Not required for loop-row v1 |
| Native unavailable + SYNC on | Fail-closed for loop Rack start (same honesty as audition) |

One-shot Rack triggers remain on the existing sequencer rate=1.0 path unless a later separate sync issue changes that contract.

### Pattern Core / Trigger interaction

- Pattern Core `Trigger` / `Channel` / `Pattern` shapes stay unchanged.
- Loop-class and ambiguous channels must **not** receive DEFAULT_ON seeds and must **not** contribute point triggers to `plan_pattern_once` / `PatternPassPlayer` for Rack Play.
- Existing oneshot DEFAULT_ON + toggle_step semantics stay unchanged.
- Sequencer non-goals remain: no Arrangement, no piano-roll note lengths, no clip timeline.

### QML projection

- Keep `row_kind=loop_identity` and `step_grid_enabled=false` for non-point-trigger-safe rows (#908).
- QML may show identity (label/path) and later a thin enable/armed affordance only as intent into Python.
- QML must not own loop lifetime, rate, BPM invention, or pass restart policy.
- No fake step cells for loops.

### Persistence

- v1 may persist **no new field** if “assigned explicit `loop` ⇒ armed” is the rule.
- Must persist honesty: after restore, classification comes from hydrated `WorkbenchRow` (path + library), not from inventing `sample_class` on `Channel`.
- Do not encode loop arming as a 16-step trigger list.
- Optional later field (`loop_enabled` per channel) is allowed only if product needs disarm-without-clear; not required to freeze this contract.

### State ownership

| Concern | Owner |
|---|---|
| Kit assignment + `sample_class` / bpm | `LiveKitState` / `WorkbenchRow` |
| Pattern triggers (oneshots) | `ChannelRackState` / Pattern Core |
| Loop start-once Play policy | `ChannelRackController` (extend; not a new transport) |
| Tempo / SYNC flags | `WorkbenchTransportAdapter` |
| Voice schedule/stop | Native engine via existing sequencer/controller seams |
| Projection | QML only |

## Fail-closed matrix

| Case | Required behavior |
|---|---|
| `sample_class` unknown / ambiguous | Identity only; no step grid; no Rack loop auto-start |
| Source BPM missing + SYNC on | Do not start loop voice |
| Source BPM `<= 0` / NaN / Inf + SYNC on | Do not start loop voice |
| Source duration / PCM missing | Soft skip that channel; no crash |
| Pattern shorter than source | Allowed; voice continues to EOF; no silent truncate |
| Pattern longer than source | Allowed; no auto-repeat to fill pattern |
| Source not bar-aligned | Allowed; no forced bar snap |
| SYNC off | Natural rate 1.0 start permitted when class=`loop` and PCM ok |
| SYNC on + valid BPM | RATE_SYNC start |
| Native playback unavailable + SYNC on | Fail-closed for loop Rack start |
| User channel without classification seam | Treat as ambiguous (identity only) |

## Explicit non-goals

- Arrangement / timeline / clips / scenes / launcher matrix
- Mixer / automation / piano roll / external DAW
- Generalized track model / cloud / ML loop analysis
- Native PCM wrap-loop mode as a v1 dependency
- Scheduled stop FFI as a v1 dependency
- Changing oneshot DEFAULT_ON musical meaning
- Redesigning #908 geometry

## Follow-up implementation slice (exactly one)

**Issue title (suggested):** `[RUNTIME][#920] Loop-row start-once Rack playback (exclude from DEFAULT_ON)`

**Scope:**

1. Classification gate in Channel Rack reconcile/seed: point-trigger-safe only get DEFAULT_ON / step triggers; `loop` and ambiguous contribute zero triggers.
2. On Rack Play: for each occupied explicit-`loop` channel, schedule one native PCM voice at the play-anchor frame with SYNC rules above; track owned loop voice ids separately from `PatternPassPlayer` oneshot voices.
3. On pass succession: do not re-fire those loop voices; on Stop/focus transfer: stop/remove them via existing seams.
4. Tests: no 16× retrigger for loop assignment; pass restart does not stack loop voices; SYNC missing BPM fail-closed; oneshot path unchanged.
5. QML: projection-only if an armed affordance is required; otherwise keep `loop_identity` as shipped by #908.

**Out of scope for that slice:** PCM wrap-loop engine, scheduled stop FFI, sustained Pattern regions, Arrangement, #908 layout redesign.

## Relationship to other contracts

| Contract | Relationship |
|---|---|
| Pattern Core | Unchanged shapes; trigger membership policy for loop rows is owned here |
| Sequencer Playback | One-pass player remains oneshot/point-trigger oriented; loop start-once is controller-adjacent, not inside `PatternPassPlayer` forever-loop |
| Session Ownership | Python remains musical authority; QML projection + intent |
| Single Workspace | §9 resolved by this freeze; geometry remains #908 |

## Exit

Done for #920 contract work when this document is merged (or Owner-approved) and the architecture outcome above is the binding decision. Runtime work requires a separate GO on the follow-up slice.
