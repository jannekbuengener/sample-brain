# Arrangement Visual Design Contract — #1079

**Status:** `ARRANGEMENT_VISUAL_ACCEPT_PENDING` — Owner review gate.  
**Issue:** [#1079](https://github.com/jannekbuengener/sample-brain/issues/1079) (DESIGN / owner gate).  
**Branch:** `design/1079-arrangement-visual-gate` (from `origin/main` @ 236c49d2).  
**Blocks:** [#1080](https://github.com/jannekbuengener/sample-brain/issues/1080) (QML projection) until Owner issues `ARRANGEMENT_VISUAL_ACCEPT_PASS`.

This contract is **design / interaction intent only**. It is not product QML, not Python runtime, not domain truth.

## Scope boundary (enforced)

| Changed | NO |
|---|---|
| Product QML | not touched |
| Python runtime | not touched |
| Domain / Pattern / mask / marker truth | not touched |
| #1080 QML implementation | untouched |
| #1083 time contract | consumed, not redefined |
| #1084 block/group/mask contract | consumed, not redefined |

No visual choice in this document introduces new Pattern, group-mask, track-mask, end-marker, or persistence truth.

## Consumed domain truth (reference, not changed)

From [`docs/ARRANGEMENT_32_FIELD_TIME_CONTRACT.md`](../../../ARRANGEMENT_32_FIELD_TIME_CONTRACT.md) and [`docs/ARRANGEMENT_BLOCK_GROUP_MASK_CONTRACT.md`](../../../ARRANGEMENT_BLOCK_GROUP_MASK_CONTRACT.md):

- Pattern: 8 bars / 32 fields / 32 quarter notes; `field i → qn i`.
- Arrangement block: 16 bars / 64 qn; two projections of one Pattern identity.
- Four presentation groups: `pg_baseline` (Baseline), `pg_drums` (Drums), `pg_melodic_atmos_fx` (Melodic / Atmos / FX), `pg_vocals` (Vocals).
- Group mask and track mask strictly separate per block; expand/collapse = pure presentation.
- End marker: bar-snapped (`end_marker_qn % 4 == 0`), Python-owned musical truth, single marker type.
- Default-on: block / group / track default `true`; persist only explicit exceptions.
- Max logical horizon: 10 minutes (600 s via TempoMap); initial view ≈ 3 minutes.

## Visual system (V7, solid fills only)

Source: [`docs/assets/themes/presets.v1.json`](../../../../assets/themes/presets.v1.json), Blood-A default.

| Semantic | Token | Value | Use |
|---|---|---|---|
| Chrome / ink floor | `background` | `#020203` | root, OFF blocks |
| Workspace / calm canvas | `surfaceWorkspace` | `#040405` | upper Arrangement stage |
| Surface / panel | `surface` | `#080809` | panels, group rows |
| Raised | `surfaceRaised` | `#101011` | elevated/active surfaces |
| Hairline / divider | `divider` | `#19191a` | fine borders, OFF marks |
| Hover | `hover` | `#131314` | quiet hover |
| Selected | `selected` | `#21050a` | focus/selection (contrast, not color-only) |
| Foreground | `foreground` / `textPrimary` | `#e4e6ea` | primary text |
| Muted | `textSecondary` | `#68696b` | secondary labels |
| Blood-A accent | `accent` / `focusRing` | `#8f0e24` | sparse, functional signal only |

Rules (V7, non-negotiable):

- Solid fills only. No `Gradient`/`RadialGradient`, no glow, no soft-ellipse, no grain, no glass, no atmosphere.
- No flat `#000000` as the only surface; depth from solid hierarchy `#020203 → #040405 → #080809 → #101011`.
- Blood A is sparse and functional (selection / active toggle / focus). Never a broad panel fill or ambient red wash.
- Accent is functional-only, not decorative.

## Layout (per direction board)

- Top program chrome per [`docs/PROGRAM_CHROME_CONTRACT.md`](../../../../PROGRAM_CHROME_CONTRACT.md): identity left (`Sample Brain`), mode navigation center (Edit / Arrangement / Live), transport right. Arrangement mode active.
- Bottom-center: Step Sequencer, 32 fields, 8 bars × 4 fields, bar groups optically readable.
- Upper Arrangement stage: large, calm, quiet until first active Step.
- Footer: return-to-Edit/Kit left, context center, status right. No separate Live-Kit or Step-Sequencer top-level mode.

## Required states (shown in every direction board)

1. **INITIAL** — Arrangement mode active, no active Step, upper stage quiet/inactive, 32-field sequencer bottom-center.
2. **FIRST STEP** — one Step active (field 4), upper Arrangement reacts visibly to musical activity, no second Pattern truth implied.
3. **COLLAPSED GROUPS** — four rows (Baseline, Drums, Melodic / Atmos / FX, Vocals), readable 16-bar block rhythm, explicit ON vs explicit OFF distinguishable without color-only coding.
4. **EXPANDED GROUP** — Drums expanded, constituent tracks visible, Group Mask vs Track Mask visually distinct, one individually disabled track, expand ≠ mute visually.
5. **TIMELINE / ZOOM** — normal ≈ 3-minute view, zoomed-in, zoomed-out; Ctrl+Wheel is the intended route; full 10-minute horizon never materialized at once.
6. **END MARKER** — precise, calm, clearly distinct from block toggles, single marker type, bar-snapped.

## Interaction contract

- Hit targets remain precise 2D rectangles. Presentation depth (direction B/C) never distorts interaction geometry.
- Expand/collapse changes no musical state (group mask, track mask, Pattern, end marker, membership untouched).
- Zoom changes viewport only; never creates/deletes musical blocks; never mutates persistence.
- Reduced motion must be a trivial, static fallback; no functional animation delays input.
- Return chrome: clear, calm route back to Edit / Kit.

## Scaling targets (evaluated per direction)

| Target | Fixed | Compresses | Scrolls | Must never clip |
|---|---|---|---|---|
| 1600×900 @ 100% | 32 fields, group labels, end marker, return chrome | block width | upper stage beyond 10 min | 32-field sequencer, end marker, return chrome |
| 1280×720 @ 100% | 32 fields, group labels | block width, row density | Arrangement stage | 32 fields, end marker |
| 1280×720 @ 125% | 32 fields, group labels | block width | stage + sequencer rows | 32 fields, end marker |
| 1120×640 @ 150% | 32 fields, group labels, end marker | block width | stage | 32 fields, end marker, return chrome |

## QML implementation boundaries for #1080

- QML owns presentation and intent only; it projects runtime state, never owns musical truth.
- Python/domain remains the authority for Pattern, masks, end marker, membership, render eligibility.
- #1080 validates real geometry itself; this contract is not pixel-perfect QML geometry.
- Visuals consume `themeAuthority` semantic tokens; no second palette, no hardcoded HEX in QML (except named `transparent`).

## Artifacts

| Artifact | Path |
|---|---|
| Direction A — PURE 2D / PRECISION | `direction_A_pure_2d.svg` |
| Direction B — SUBTLE 2.5D BLACK STAGE | `direction_B_25d_black_stage.svg` |
| Direction C — SPATIAL REFERENCE | `direction_C_spatial_reference.svg` |
| Comparison matrix | `COMPARISON_MATRIX.md` |
| Review index | `README.md` |

## Owner gate

The agent may not pass this gate. Final status: `ARRANGEMENT_VISUAL_ACCEPT_PENDING`.

Owner is asked: **"Which direction should be frozen for #1079? A / B / C / changes to B"**

#1079 remains OPEN until explicit `ARRANGEMENT_VISUAL_ACCEPT_PASS`.
