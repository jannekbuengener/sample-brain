# Gesture Analysis R&D — Slice 1 (#680 / #827)

**Status:** R&D foundation only. Not a product feature. Not producer-quality.

**Parent:** [#680](https://github.com/jannekbuengener/sample-brain/issues/680)  
**Child:** [#827](https://github.com/jannekbuengener/sample-brain/issues/827)

## Goal

Prove that a short local beatbox / vocal / knock audio file can be decomposed into:

1. time-ordered onset events (measured source timing),
2. per-event classical DSP features,
3. deterministic cluster IDs for recurring similar gestures.

## Quality labels

| Label | What |
|-------|------|
| MEASURED | Onset time (seconds), raw DSP feature values, L2 distances after normalization |
| HEURISTIC | `cluster_id` via fixed-threshold sequential nearest-centroid |
| NOT YET CLAIMED | Kick/Snare/Hat semantics, library sample match, producer quality |

## Public contract

Module: `src/gesture_analysis.py`

```text
analyze_gesture_audio(path) -> GestureAnalysis
```

- `GestureEvent.onset_time_sec` — measured onset time
- `GestureEvent.feature_vector` — raw finite floats, length `FEATURE_DIM` (**15**)
- `GestureEvent.cluster_id` — non-negative int, heuristic role index (not a drum name)
- `GestureAnalysis.status` — `ok` | `empty` | `too_short` | `unreadable`
- `feature_dim` — always 15: RMS(1) + spectral centroid mean(1) + MFCC mean(13)

## Onset rules

1. Load via `safe_load` at `ANALYZE_SR` (mono float32).
2. Detect with `librosa.onset.onset_strength` + `onset_detect` (first productive use in `src/`).
3. Convert to sample indices; drop out-of-bounds / non-finite.
4. Sort and dedupe identical sample indices.
5. Enforce minimum gap `_MIN_ONSET_GAP_SEC` (0.15 s) so final times are **strictly monotonically increasing**.
6. No grid quantization; timing remains measured source timing.

## Feature normalization (explicit)

Within a single analysis (not across files):

1. Replace non-finite raw values with `0.0`.
2. For each dimension `d`, compute `mean_d`, `std_d`, `peak_d = max(|x|)`.
3. Treat as zero-variance (emit `0.0` for all events on `d`) when:

   `std_d <= max(1e-6, 0.05 * peak_d)` or stats are non-finite.

4. Otherwise emit `(x - mean_d) / std_d`; non-finite results → `0.0`.

Rationale: plain z-score on near-identical events amplifies tiny onset-window noise into large distances. The relative std floor keeps near-duplicates collapsed without requiring RNG or cross-run state. Same input → identical normalized features and cluster IDs.

## Cluster threshold calibration

**Method:** build the synthetic golden WAVs used by `tests/test_gesture_analysis.py`, extract normalized feature rows, measure:

- `D_same_max` = max pairwise L2 among same-gesture events (identical impulses + mild amplitude variants)
- `D_cross_min` = min pairwise L2 among clearly different gestures (low decaying sine vs high click)

**Measured on the frozen fixtures (ANALYZE_SR=44100):**

| Quantity | Value (approx.) |
|----------|-----------------|
| `D_same_max` (amp-varied identical kicks) | ≈ 2.45 |
| `D_same` (identical kicks / ABAB same-class) | ≈ 0.00 … 0.67 |
| `D_cross_min` (kick vs hat) | ≈ 7.56 |

**Chosen threshold:** `CLUSTER_DISTANCE_THRESHOLD = 5.0`

**Margin:** midpoint of `[2.45, 7.56]` ≈ 5.0, leaving ≈ 2.5 L2 below the nearest cross-gesture distance and ≈ 2.5 above the worst same-gesture distance. Not fitted to a single outlier fixture.

Clustering algorithm: sequential nearest-centroid; join if L2 ≤ threshold, else new id. No random init, no training, no embeddings, no cloud.

## Non-goals (this slice)

- Microphone UI, QML, Screen 1/2, Arrangement
- Quantization, BPM prerequisite, pitch/stretch, sample generation/resynthesis
- ML training / new models / cloud inference
- DB tables / persistence schema
- Pattern Core / step-sequencer timebase / DEFAULT_ON changes
- Mapping `cluster → library sample → Channel → Trigger` (Slice 2+)

## Acceptance (tests)

See `tests/test_gesture_analysis.py`. Synthetic WAVs only; nothing committed as audio binaries.
