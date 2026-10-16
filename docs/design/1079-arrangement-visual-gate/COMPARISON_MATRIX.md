# Comparison Matrix — Arrangement Visual Directions (#1079)

All three directions show the **same representative Arrangement state** so the Owner compares visual treatment, not information differences. States covered: INITIAL, FIRST STEP, COLLAPSED GROUPS, EXPANDED GROUP (Drums), ZOOM, END MARKER.

Scale: strong / moderate / weak; ✔ = meets, △ = partial, ✖ = does not meet.

| Criterion | A — PURE 2D / PRECISION | B — SUBTLE 2.5D BLACK STAGE | C — SPATIAL REFERENCE |
|---|---|---|---|
| Musical precision | ✔ strongest — flat geometry, exact rectangles | ✔ same 2D hit geometry as A | ✔ same 2D hit geometry as A |
| Information density | ✔ high — no depth chrome competing | ✔ high — layers add little noise | △ moderate — softer layering reads busier |
| Visual calm | ✔ very calm, flat | ✔ calm — depth is subtle, not dramatic | △ calmer than B? spatial suggestion adds mass |
| Sample Brain identity (V7 noir) | ✔ exact V7 solid hierarchy | ✔ exact V7 + restrained depth | ✔ V7 but closer to spatial experiment |
| 32-Field readability | ✔ best — flat, maximal contrast | ✔ strong — same cells, subtle lift | ✔ strong |
| Block readability | ✔ precise — hairlines + contrast | ✔ precise — raised/inset ON/OFF | ✔ good — slightly softer edges |
| Expanded-group readability | ✔ clear | ✔ clear + group vs track separation | ✔ clear |
| End-marker precision | ✔ best — distinct thin bar | ✔ distinct thin bar | ✔ distinct thin bar |
| Windows scaling (1600×900 … 1120×640) | ✔ robust — flat geometry scales cleanly | ✔ robust — layering is solid-fill based | △ more scaling cases to validate |
| QML robustness (#1080) | ✔ lowest risk — no depth to reconcile | ✔ low risk — depth is presentation only | △ moderate — spatial intent needs discipline |
| Implementation risk | ✔ lowest | ✔ low | △ moderate |
| Visual depth (2.5D stage feel) | ✖ absent by design | ✔ present, restrained | ✔ strongest (reference only) |

## Direction notes

**A — PURE 2D / PRECISION.** Maximum geometric precision, hairlines, flat contrast. Strongest technical robustness and lowest QML risk. Reads as a precise technical instrument. Least "stage" atmosphere.

**B — SUBTLE 2.5D BLACK STAGE.** Same precise 2D hit geometry as A, plus layered black surfaces, raised/inset impression, hairlines, controlled contrast. Sequencer feels like an inset device; Arrangement above feels like a black stage. Depth via light/contrast/layer/shadow only — no perspective distortion, no camera, no distorted interaction geometry. Strongest match to the "BLACK STAGE / BLACK TABLE" design goal while keeping interaction rectangular and exact.

**C — SPATIAL REFERENCE.** Slightly more spatial than B; documented as a visual upper bound / reference. Still QML-realizable in thought, no 3D engine commitment. Elements that V1 does not need: any deeper layering beyond B, any spatial cue that complicates hit targeting. Kept as reference so the Owner has a ceiling, not a commitment.

## Recommendation

**Freeze Direction B.**

Evidence:
- B carries the exact same 2D hit geometry as A (no precision loss) while delivering the requested black-stage depth that A lacks and C over-reaches.
- Depth is presentation-only (solid fills, hairlines, raised/inset), so QML implementation risk stays low and V7 rules (solid fills, no glow/gradient) are fully satisfied.
- A is the safe fallback if the Owner rejects any depth illusion; C is retained as a documented reference ceiling, not a V1 target.

## Owner decision requested

**"Which direction should be frozen for #1079? A / B / C / changes to B"**

#1079 remains OPEN pending `ARRANGEMENT_VISUAL_ACCEPT_PASS`.
