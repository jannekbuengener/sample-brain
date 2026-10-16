# Comparison Matrix — Arrangement Visual Directions (#1079)

All three directions show the **same representative Arrangement state** so the Owner compares visual treatment, not information differences. States covered: INITIAL, FIRST STEP, COLLAPSED GROUPS, EXPANDED GROUP (Drums), ZOOM, END MARKER. Direction B additionally ships a large HERO view at 1600×900.

Scale: strong / moderate / weak; ✔ = meets, △ = partial, ✖ = does not meet.

| Criterion | A — PURE 2D / PRECISION (unchanged) | B — SUBTLE 2.5D BLACK STAGE (revised) | C — SPATIAL REFERENCE (ceiling) |
|---|---|---|---|
| Musical precision | ✔ strongest — flat geometry, exact rectangles | ✔ same 2D hit geometry as A | ✔ same 2D hit geometry as A |
| Information density | ✔ high — no depth chrome competing | ✔ high — layers add little noise | △ moderate — softer layering reads busier |
| Visual calm | ✔ very calm, flat | ✔ calm — depth is subtle, not dramatic | △ calmer than B? spatial suggestion adds mass |
| Sample Brain identity (V7 noir) | ✔ exact V7 solid hierarchy | ✔ exact V7 + restrained depth | ✔ V7 but closer to spatial experiment |
| 32-Field readability | ✔ best — flat, maximal contrast | ✔ strong — same cells, inset device | ✔ strong |
| Block readability | ✔ precise — hairlines + contrast | ✔ precise — elevation ON/OFF, restrained Blood A | ✔ clear — strongest contrast between planes |
| Expanded-group readability | ✔ clear | ✔ clear + group vs track separation | ✔ clear |
| End-marker precision | ✔ best — distinct thin bar | ✔ distinct thin bar | ✔ distinct thin bar |
| Windows scaling (1600×900 … 1120×640) | ✔ robust — flat geometry scales cleanly | ✔ robust — layering is solid-fill based | △ more scaling cases to validate |
| QML robustness (#1080) | ✔ lowest risk — no depth to reconcile | ✔ low risk — depth is presentation only | △ moderate — spatial intent needs discipline |
| Visual depth (black stage / inset device) | ✖ absent by design | ✔ strong stage + inset sequencer | ✔ strongest spatial layering |
| Blood A restraint | ✔ none used | ✔ tiny functional indicator only | ✔ restrained |

## Direction notes

**A — PURE 2D / PRECISION.** Unchanged flat precision baseline. Maximum geometric precision, hairlines, flat contrast. Strongest technical robustness and lowest QML risk. Reads as a precise technical instrument. No black-stage atmosphere.

**B — SUBTLE 2.5D BLACK STAGE (revised).** Same precise 2D hit geometry as A (no precision loss), plus:
- Upper Arrangement area reads as a deep black stage via stronger hierarchy: background `#020203` → workspace `#040405` → panel `#080809` → raised `#101011`.
- Bottom sequencer feels like an inset precision device (raised outer frame + solid surface body), every Step cell a precise rectangle, no perspective distortion.
- ON blocks read primarily through black-surface elevation/contrast; Blood A reduced to a tiny functional indicator dot — not the block body/border language.
- Increased separation between stage, group rows, expanded tracks, and sequencer device using only V7 solid fills, hairlines, and controlled edge contrast.
- New HERO view at 1600×900: working Arrangement composition, upper stage dominant, bottom-center sequencer device, Drums expanded, several 16-bar blocks, one OFF state, end marker visible, restrained Blood A, normal ~3-minute viewport.

**C — SPATIAL REFERENCE.** Visibly exceeds B in spatial treatment: more pronounced layering between planes, a cooler mid stage floor, stronger contrast between background/workspace/panel/raised. Documented as a visual upper bound / reference ceiling, not V1. Still QML-realizable in thought (solid fills, rectangles), no 3D engine commitment. B and C no longer look nearly identical.

## Recommendation

**Freeze Direction B (revised).**

Evidence:
- B carries the exact same 2D hit geometry as A (no precision loss) while delivering the requested black-stage depth that A lacks.
- Depth is presentation-only (solid fills, hairlines, raised/inset), so QML implementation risk stays low and V7 rules (solid fills, no glow/gradient) are fully satisfied.
- Blood A is restrained to a functional indicator, not decorative block borders.
- C is retained as a documented reference ceiling, not a V1 target. A remains the safe no-depth fallback.

## Owner decision requested

**"Which direction should be frozen for #1079? A / B (revised) / C / changes to B"**

#1079 remains OPEN pending `ARRANGEMENT_VISUAL_ACCEPT_PASS`.
