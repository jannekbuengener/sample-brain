# BPM Half/Double Detection Evidence

Evidence for octave-error (half/double BPM) detection rates from `librosa.beat.beat_track` on controlled synthetic fixtures. This document records measured error classes and feeds the decision on which BPM normalization strategy to implement next.

## Run metadata

| Field | Value |
|-------|-------|
| Date | 2026-06-09 |
| Branch | `eval/bpm-half-double-evidence` |
| Commit | `e17afc7` (base `main` + evidence harness) |
| OS | Windows 11 |
| Python | 3.12.10 |
| librosa | 0.11.0 |
| numpy | 2.x (no `float(ndarray)` scalar coercion) |
| Fixture set | 9 BPM x 2 variants = 18 synthetic WAVs |
| Harness command | `python -m src.cli benchmark bpm-evidence --work-dir %TEMP%\bpm-evidence` |

## Fixture description

| Variant | Generator | Signal |
|---------|-----------|--------|
| pulse train | `write_pulse_train_wav` | 5 ms decaying sine clicks at 800 Hz, one per beat |
| kick transient | `write_kick_transient_wav` | 150 ms low-frequency (60 Hz) decaying sine, one per beat |

Both variants are 4-second mono 44100 Hz PCM_16 WAVs at each BPM in:

```
60, 70, 85, 100, 120, 128, 140, 160, 175
```

18 synthetic WAVs total. No private audio committed.

## Per-sample results

| label_bpm | actual_bpm | variant | ratio | error_class |
|-----------|------------|---------|-------|-------------|
| 60 | 60.1 | pulse | 1.002 | correct |
| 60 | 60.1 | kick | 1.002 | correct |
| 70 | 69.8 | pulse | 0.998 | correct |
| 70 | 69.8 | kick | 0.998 | correct |
| 85 | 84.7 | pulse | 0.997 | correct |
| 85 | 84.7 | kick | 0.997 | correct |
| 100 | 99.4 | pulse | 0.994 | correct |
| 100 | 99.4 | kick | 0.994 | correct |
| 120 | 120.2 | pulse | 1.002 | correct |
| 120 | 120.2 | kick | 1.002 | correct |
| 128 | 129.2 | pulse | 1.009 | correct |
| 128 | 129.2 | kick | 1.009 | correct |
| 140 | 139.7 | pulse | 0.998 | correct |
| 140 | 139.7 | kick | 0.998 | correct |
| 160 | 161.5 | pulse | 1.009 | correct |
| 160 | 161.5 | kick | 1.009 | correct |
| **175** | **87.6** | pulse | **0.501** | **half** |
| **175** | **87.6** | kick | **0.501** | **half** |

## Aggregate metrics

| Metric | Value |
|--------|-------|
| total | 18 |
| correct | 16 (88.9%) |
| half | 2 (11.1%) |
| double | 0 (0.0%) |
| ambiguous | 0 (0.0%) |
| outlier | 0 (0.0%) |
| octave_error | 2 (11.1%) |
| mean_abs_error | 10.2 BPM |

## Recommendation

**`heuristic_clamp`** — moderate octave error rate (11.1%).

The only octave errors occurred at 175 BPM where librosa detected ~87.6 BPM (half). A simple heuristic that clamps detected BPM into a plausible range (e.g. `bpm < 80 -> bpm*2; bpm > 200 -> bpm/2`) would correct these cases.

However, note that the failure threshold (80 BPM) would need adjustment: the erroneous value is 87.6 BPM, which is above a naive 80 BPM clamp. A safer heuristic would be to look for octave relationships in a broader range (e.g. `if bpm < 100` consider doubling).

Suggested next implementation:

1. Add a config profile key `analyze.bpm_normalization` with values `none` (default, no change) and `heuristic` (clamp-based).
2. In `src/analyze.py`, apply the heuristic after librosa extraction:
   - `if bpm < 90: bpm *= 2`
   - `if bpm > 200: bpm /= 2`
3. Measure on real private samples to tune the threshold before changing the default.

## Error class definitions

| Class | Ratio (actual / label) | Description |
|-------|----------------------|-------------|
| correct | 0.95-1.05 | Within +-5% of ground truth |
| half | 0.45-0.55 | ~50% of ground truth (octave down) |
| double | 1.90-2.10 | ~200% of ground truth (octave up) |
| ambiguous | 0.2-5.0, not in above classes | Plausible BPM but not correct/half/double |
| outlier | <0.2 or >5.0 or None or <=0 | Wildly wrong or unavailable |

## Implementation note: numpy 2.x compatibility

`librosa.beat.beat_track` returns tempo as a 1-element `numpy.ndarray`, not a Python scalar. In numpy 2.x, `float(ndarray)` raises `TypeError`. The harness uses `.item()` to extract the scalar. Note: `src/analyze.py:113` uses the same `float(tempo)` pattern and may silently drop BPM values on numpy >= 2.0. This was discovered during evidence collection and is tracked in the follow-up recommendation.

## Limitations

- Synthetic pulse/kick fixtures are a **lower bound** for octave error rates. Real-world samples with ghost kicks, layering, sparse rhythms, or harmonic content may produce higher error rates.
- This evidence does **not** include private-sample validation.
- No ground truth beyond the synthetic BPM labels used at generation time.
- Weak labels from filenames (e.g. `{bpm}bpm`) are implicit through fixture naming; explicit weak-label parsing from user samples is out of scope.

## Explicitly out of scope

- No production code change in `src/analyze.py`
- No change to FL Studio export (`src/export_fl.py`)
- No database schema changes
- No new dependencies
- No committed audio binaries
- No workflow or CI changes

## Decision

This document provides evidence only. The decision on which BPM normalization strategy to implement belongs to a follow-up issue.

**Recommended follow-up issue:** `feat: add heuristic BPM normalization with profile toggle`

- Add `analyze.bpm_normalization` config key (`none` default)
- Implement heuristic clamp: `bpm < 90 -> bpm*2; bpm > 200 -> bpm/2`
- Also fix numpy 2.x `float(ndarray)` issue in `src/analyze.py`
- Evidence threshold decisions require real-sample validation, not just synthetic fixtures
