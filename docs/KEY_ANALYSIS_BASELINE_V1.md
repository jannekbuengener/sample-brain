# Key Analysis Baseline v1.0

## Overview
This document records the current baseline behavior, evidence semantics, and measured benchmark counts for key analysis in `sample-brain` (#418).

## Current Algorithm
- **Root Detection (`estimate_key`)**:
  Computes mean chroma via CQT (`librosa.feature.chroma_cqt`). The root estimate is the argmax of the mean chroma vector (`SEMITONES[argmax]`). The confidence metric `key_conf` is normalized peak prominence (`max(chroma_mean) / (sum(chroma_mean) + 1e-9)`).
  *Note:* This is a simple mean-chroma peak/root heuristic and does **not** implement Krumhansl-Schmuckler key profile matching.
- **Mode Estimation (`estimate_key_mode`)**:
  Calculates normalized third contrast between major third (root + 4 semitones) and minor third (root + 3 semitones):
  $$\text{contrast} = \frac{|\text{major\_third} - \text{minor\_third}|}{\text{major\_third} + \text{minor\_third} + \epsilon}$$
  If $\text{contrast} \ge \text{MODE\_CONTRAST\_MIN}$ ($0.30$), mode is committed as `"maj"` or `"min"`. Below threshold, mode is `None`.

## Evidence Semantics
- `key_mode_evidence` contains structured relative analysis evidence:
  - `kind`: `"third_contrast"`
  - `major_third_energy`: float
  - `minor_third_energy`: float
  - `contrast`: float
  - `threshold`: float ($0.30$)
  - `mode`: `"maj"`, `"min"`, or `None`
- Evidence represents relative third energy contrast and is **NOT** a calibrated probability or confidence score.

## Deterministic Baseline Counts
From frozen probe evaluation on deterministic synthetic fixtures:
- **Tonal cases**:
  - Root accuracy: $3/4$
  - Mode accuracy: $3/4$
  - Combined accuracy: $3/4$
- **Ambiguous cases** (single sine, octave, root+fifth power chord, major/minor blend):
  - Abstention rate: $3/3$ ($100\%$)

## Known Algorithm Weakness: Bass Dominance
- When a chord has an intentionally heavy low bass note (e.g., C major with a prominent sub-bass/bass note at 65.4 Hz C1 or lower), lower harmonic overtones and low-frequency spectral distribution can cause mean chroma CQT energy to peak on a harmonic (such as G or C# depending on spectral energy distribution) instead of the nominal pitch class root.
- In the baseline set, this bass-dominant C-major case yields root `G` / mode `maj`, resulting in the $3/4$ tonal root/mode score.
- **Decision**: The key detection algorithm is kept unchanged in this persistence/evidence slice (#418). Future algorithm decisions or profile-based improvements are deferred until evidence is gathered from persisted catalog data.
