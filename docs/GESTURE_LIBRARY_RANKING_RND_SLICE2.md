# Gesture Library Ranking R&D — Slice 2 (#680 / #882)

**Status:** R&D contract frozen at DOCS_GATE / TEST_GATE. Implementation follows TEST_FREEZE.

**Parent:** [#680](https://github.com/jannekbuengener/sample-brain/issues/680)  
**Child:** [#882](https://github.com/jannekbuengener/sample-brain/issues/882)  
**Dependency (DONE):** [#827](https://github.com/jannekbuengener/sample-brain/issues/827) / `docs/GESTURE_ANALYSIS_RND_SLICE1.md`

## Goal

Prove the smallest deterministic retrieval seam:

```text
gesture cluster (Slice 1) → one prototype → ranked oneshot library candidates
```

Output is R&D candidate ranking with measured distances. It is **not** a producer-quality automatic choice and must **not** write Pattern / Channel / Trigger state.

## Architecture boundary (hard)

| Domain | Time authority |
|--------|----------------|
| Gesture (`onset_time_sec`) | measured source seconds |
| Pattern Core (`Trigger.position`) | exact quarter-note `Fraction` |

This slice does **not** authorize or invent:

- seconds → quarter-note conversion
- source BPM requirement / BPM inference
- gesture loop-length mapping
- quantization

Timing on `GestureAnalysis` remains unchanged measured source time. Ranking ends at cluster → Top-N candidates.

## Live foundation verified on `origin/main` (base used for this branch)

### Gesture (`src/gesture_analysis.py`)

- Public: `analyze_gesture_audio(path) -> GestureAnalysis`
- Event: `onset_time_sec`, raw 15-D `feature_vector`, deterministic heuristic `cluster_id`
- Feature layout: `[0]=RMS amplitude`, `[1]=spectral centroid mean (Hz)`, `[2:15]=MFCC13 means`
- Onset window ≈ 40 ms pre + 120 ms post (not full-file)

### Catalog analysis (`src/analyze.py` / `features` / Library Intelligence)

- `loudness` = RMS in dBFS via `_rms_dbfs`: `20 * log10(rms + 1e-12)` when `rms > 0`, else `None`
- `brightness` = spectral centroid mean (Hz) over the **full** loaded sample
- `mfcc_mean` = 13×`float32` BLOB (`np.frombuffer(..., dtype=np.float32)` → length 13)
- `class` = `"oneshot"` if `duration <= 1.2` else `"loop"` (`_duration_class`)

### Existing retrieval seams (comparison only)

- `src/search.py` / embeddings / `hybrid_rank.py` = semantic + metadata hybrid path
- Not reused as a dependency for this classical DSP ranking core
- No second catalog system; a later adapter may project `features` rows into the frozen candidate struct

## Quality labels

| Label | What |
|-------|------|
| MEASURED | Raw gesture features, aligned/transformed values, distances, deterministic ordering |
| HEURISTIC | Cluster prototype aggregation (median), classical L2 after corpus z-score; window mismatch vs catalog full-file features |
| NOT YET CLAIMED | Kick/Snare/Hat identity, producer-quality match, musical correctness, calibrated confidence / probability |

**Window mismatch (explicit):** gesture MFCC/centroid are onset-window means; catalog values are full-sample means. Same dimensional contract (1+1+13), **not** identical feature spaces. Remains HEURISTIC / NOT YET CLAIMED for musical quality.

## Public seam

Module: `src/gesture_library_ranking.py`

```text
rank_gesture_library_candidates(
    analysis: GestureAnalysis,
    candidates: Sequence[LibraryCandidate],
    *,
    top_n: int = 5,
) -> tuple[ClusterRanking, ...]
```

### Immutable candidate contract

```text
LibraryCandidate (frozen)
  sample_id: str                 # stable opaque identity (caller may str(catalog id))
  path: str | None               # optional ref; unused by distance math
  audio_class: str               # catalog features.class
  loudness: float                # dBFS
  brightness: float              # Hz
  mfcc13: tuple[float, ...]      # length 13, finite
```

Core ranking **must not** open SQLite or import embedding/search backends.

### Result contract

```text
RankedCandidate (frozen)
  sample_id: str
  distance: float                # L2 after shared normalization; not a confidence
  rank: int                      # 1-based among returned Top-N for that cluster

ClusterRanking (frozen)
  cluster_id: int
  prototype_aligned: tuple[float, ...]   # length 15 after RMS→dBFS alignment
  ranked: tuple[RankedCandidate, ...]
```

- One `ClusterRanking` per distinct `cluster_id` present in `analysis.events`, ordered by ascending `cluster_id`.
- All events sharing a `cluster_id` share that ranking object’s semantic content (same prototype, same ranked list).
- Rank 1 ≠ approved musical choice.

## Frozen decisions

### 1. Cluster prototype — **per-dimension median** of raw gesture `feature_vector`s

**Evidence (synthetic):**

| Case | mean L2→true | median L2→true |
|------|-------------:|---------------:|
| Clean near-identical cluster | moderate | slightly better / comparable |
| One extreme outlier in cluster | very large | small |
| Asymmetric amplitude skew | large | near-zero |

**Decision:** median. Slice-1 clustering already prefers similar events, but median remains robust if a borderline event joins a cluster. Consistent across reruns; no RNG.

Prototype lives in **raw gesture space** (RMS amplitude, Hz, MFCC13), then a single alignment step is applied.

### 2. Feature alignment

| Gesture dim | Catalog field | Adapter |
|-------------|---------------|---------|
| `[0]` raw RMS | `loudness` dBFS | If RMS finite and `> 0`: `20 * log10(rms + 1e-12)` (same epsilon as `_rms_dbfs`). Else **fail closed** for that cluster → `ranked=()` and `prototype_aligned=()` (no productive ranking). |
| `[1]` centroid Hz | `brightness` Hz | Identity (Hz↔Hz). Non-finite → fail closed for cluster as above. |
| `[2:15]` MFCC13 | `mfcc13` / decoded `mfcc_mean` | Identity per coefficient. Require 13 finite values on candidates; non-finite prototype MFCC → fail closed for cluster. |

### 3. Candidate filtering

Initial pool: `audio_class == "oneshot"` only (canon: duration-class oneshot ≤ 1.2 s; drum replacements must not silently pull loops).

Exclude (not ranked) when any of:

- `audio_class != "oneshot"`
- any of `loudness`, `brightness` non-finite
- `mfcc13` length ≠ 13 or any non-finite entry
- `sample_id` empty / non-str after freeze rules (implementation: reject non-`str` or empty)

No semantic drum label is inferred from `cluster_id`.

### 4. Feature normalization — **candidate-corpus z-score**

Build the aligned 15-D matrix from the **filtered candidate pool only**. For each dimension `d`:

1. `mean_d`, `std_d` over that pool.
2. If `std_d` is non-finite or `std_d <= 1e-12` → emit `0.0` for query and all candidates on `d` (fail-soft zero-variance).
3. Else `(x - mean_d) / std_d`; non-finite results → `0.0`.

Apply the **same** transform to the cluster prototype (query) and every candidate.

**Why not median/MAD in this slice:** synthetic Top-N order (exact < near < far) held for both z-score and MAD under an injected corpus outlier; z-score is the smaller classical approach and matches Slice-1’s z-score family. MAD remains a documented alternative if later local-corpus evidence shows outlier pollution — that would be a **later calibrated decision**, not silent weights here.

**No hand-tuned per-feature weights** in this slice.

Candidate **iteration order must not** change semantic ranking: sort/tie-break uses identity, not input order.

### 5. Ranking / tie-break

- Distance: Euclidean L2 on the 15-D normalized vectors.
- Return Top-N by ascending distance.
- Ties: ascending `sample_id` (lexicographic on the frozen `str` identity).
- `top_n <= 0` → fail closed: raise `ValueError`.
- Empty filtered pool → each cluster returns `ranked=()` (no exception), unless the cluster itself failed alignment (also `ranked=()`).
- Same inputs twice → identical prototypes, distances, ranks.

### 6. Non-goals (unchanged)

No Pattern/Channel/Trigger creation, no BPM/quantize/seconds→beats, no QML/UI/mic, no Kick/Snare/Hat naming, no auto-accept rank 1, no model training/cloud, no DB schema, no Arrangement, no new runtime dependency, no embedding invocation in the core ranker.

## Optional local runtime evidence (outside repo)

Allowed anonymized metrics only: candidate pool N, excluded-invalid N, deterministic rerun, distance distributions, same-cluster Top-N stability. **No** private paths/filenames/DB/audio/track names. No musical-quality PASS without Owner listening/evidence.

## R&D exit (after implementation + evidence)

Exactly one of:

- `DETERMINISTIC_FEATURE_RANKING_VIABLE`
- `DETERMINISTIC_FEATURE_RANKING_INSUFFICIENT`
- `INSUFFICIENT_EVIDENCE`

Synthetic tests prove the algorithmic contract; they cannot alone prove producer-quality retrieval.

## Acceptance tests

See `tests/test_gesture_library_ranking_882.py` (frozen at TEST_FREEZE).
