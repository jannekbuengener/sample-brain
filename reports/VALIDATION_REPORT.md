# SampleBrain Validation Report
Generated: 2026-01-21T02:55:41
## Inventory
- Samples in catalog: **218**
- With BPM: **218** (100.0%)
- With Key: **218** (100.0%)
- With Key confidence: **218** (100.0%)
- With Class (loop/one-shot/etc): **218** (100.0%)

## BPM quality (weak ground truth)
We extract BPM hints from filenames like `128bpm` / `124 bpm` and compare with predicted BPM.
- match: **7** (58.3%)
- half_time: **4** (33.3%)
- double_time: **0** (0.0%)
- mismatch: **1** (8.3%)

Notes:
- `half_time` usually means the analyzer locked onto the half-tempo (common for claps/hats/ambient loops).
- For Techno/Hardtechno, we typically prefer **normalizing into 120–160 BPM** range.

## BPM distribution
- min/median/max: **0.0 / 120.2 / 304.0**
- 10th/90th percentile: **60.2 / 178.2**

## Key confidence
- min/median/max: **3.72 / 3.80 / 5.40**
- low-confidence share (key_conf < 2.0): **0.0%**

## Class / Predicted Type

Top classes:
- loop: 183
- oneshot: 35

Top pred_type:
- Loop: 108
- Drone: 70
- OneShot: 32
- Drum Loop: 5
- Snare: 2
- HiHat-Closed: 1

## Findings (actionable)
1) **BPM has known half-tempo errors** (see weak-ground-truth check). We should enable/extend BPM normalization for genre profiles.
2) **Key confidence is mostly high**, but we still need a low-confidence bucket to avoid over-tagging.
3) The catalog stores **absolute paths (e.g. `D:\\PRODUCING...`)** — this must not leak into Git history.

## Next steps
- Create `profiles/techno.yaml` with BPM normalization rules (e.g. map 60–90 → *2, clamp 110–160).
- Add a `validate.py` script to re-run this report on demand.
- Extend weak ground truth: add more BPM hints via filename conventions or a small manual tagging pass (50–100 samples).
