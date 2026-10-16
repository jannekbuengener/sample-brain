# #1079 Arrangement Visual Direction + Owner Gate

**Status:** `ARRANGEMENT_VISUAL_ACCEPT_PENDING`  
**Issue:** [#1079](https://github.com/jannekbuengener/sample-brain/issues/1079)  
**Branch:** `design/1079-arrangement-visual-gate` (from `origin/main` @ 236c49d2)  
**Blocks:** [#1080](https://github.com/jannekbuengener/sample-brain/issues/1080) until Owner issues `ARRANGEMENT_VISUAL_ACCEPT_PASS`.

This is a **design / owner gate only**. No product QML, no Python runtime change, no domain change. #1080 is untouched.

## Artifacts

| Artifact | File |
|---|---|
| Direction A — PURE 2D / PRECISION (unchanged flat baseline) | `direction_A_pure_2d.svg` |
| Direction B — SUBTLE 2.5D BLACK STAGE (revised, recommended) | `direction_B_25d_black_stage.svg` |
| Direction B — HERO view at 1600×900 | `direction_B_hero.svg` |
| Direction C — SPATIAL REFERENCE (ceiling, not V1) | `direction_C_spatial_reference.svg` |
| Design / interaction contract | `DESIGN_CONTRACT.md` |
| A/B/C comparison matrix | `COMPARISON_MATRIX.md` |
| Review index | `README.md` |

All SVGs are static, V7-palette-conformant (solid fills only, no gradients/glow/neon), 1600×900 reference viewbox, and show the same representative Arrangement state across the six required states (INITIAL, FIRST STEP, COLLAPSED GROUPS, EXPANDED GROUP, ZOOM, END MARKER). Direction B adds a large HERO composition.

## Required states covered (per direction board)

1. INITIAL — no active Step, upper Arrangement quiet/inactive
2. FIRST STEP — one Step active, upper Arrangement reacts
3. COLLAPSED GROUPS — four groups, 16-bar blocks, ON vs explicit OFF
4. EXPANDED GROUP — Drums expanded, Group Mask vs Track Mask distinct, one disabled track
5. ZOOM / TIMELINE — ≈ 3 min normal, zoomed-in, zoomed-out
6. END MARKER — precise, distinct from block toggles, single type

## What changed vs the first review (B revised)

Per Owner feedback "changes to B":
- Upper Arrangement area now reads as a deep black stage via stronger background → workspace → panel → raised hierarchy.
- Bottom sequencer feels like an inset precision device (raised outer frame, solid surface body, exact rectangular Step cells).
- Blood-A block outlines reduced; ON blocks read via black-surface elevation/contrast, Blood A only as a tiny functional indicator.
- Increased separation between stage, group rows, expanded tracks, and sequencer device using only V7 solid fills, hairlines, controlled edge contrast.
- Direction C visibly exceeds B in spatial treatment (more pronounced layering, cooler mid stage floor, stronger plane contrast); B and C no longer look nearly identical.
- Direction A unchanged as the flat precision baseline.
- New B HERO view added at 1600×900.

## Recommendation

Freeze **Direction B (revised)** (see `COMPARISON_MATRIX.md`).

## Owner gate

The agent may not pass this gate. Final status: `ARRANGEMENT_VISUAL_ACCEPT_PENDING`.

Owner is asked: **"Which direction should be frozen for #1079? A / B (revised) / C / changes to B"**

#1079 remains OPEN until explicit `ARRANGEMENT_VISUAL_ACCEPT_PASS`.  
Do not merge this PR. Do not close #1079. Do not touch #1080.

## Scope validation

| Scope item | Value |
|---|---|
| Product QML changed | NO |
| Python runtime changed | NO |
| Domain changed | NO |
| #1080 changed | NO |
