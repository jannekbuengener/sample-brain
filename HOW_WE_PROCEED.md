# How we proceed with SampleBrain

## Goal
Turn SampleBrain into a **reproducible, genre-aware sample analysis system**
without committing audio or local state.

## Phase 1 – Stabilize (now)
- Repo hygiene (.gitignore enforced)
- PROJECT_META.md as single source of truth
- Deterministic feature extraction only (no ML training yet)

## Phase 2 – Validate
- Weak ground truth from filenames & folders
- BPM / Key confidence reports
- Error buckets (half/double BPM, key ambiguity)

## Phase 3 – Genre Profiles
- Per-genre config (Techno, Cinematic, LoFi…)
- Seeds + thresholds, not heavy ML
- Optional embeddings later

## Rule
No model training before validation passes.
