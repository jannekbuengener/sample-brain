# Analysis Extraction Slice 0 — Ownership Boundary Design

**Date:** 2026-10-17  
**Status:** design for owner review  
**Baseline:** `b37031677e3c187c88ce8197287346feaa5deeaf`  
**Scope:** internal ownership refactor only; no physical repository split

## Intent

Prepare Sample Brain for a later `sample-brain-analysis` Single Source of Truth by proving one small, real ownership correction inside the existing repository.

Slice 0 moves the attack/onset suggestion algorithm out of a Workbench-named module into an analysis-owned module while preserving Product behavior, AQ3 evidence identity, compatibility imports, and existing packaging.

Success means the analysis path no longer imports Workbench presentation/helpers for this algorithm, while existing Product consumers continue to work through a compatibility facade.

## Constraints

- Keep `sample-brain` as the current Product/Composition repository.
- No new repository, package distribution, wheel, dependency, plugin framework, IPC, service, or process boundary.
- No DB, Track Package, WorkbenchSession, Arrangement, Live Kit, QML, native-audio, or persistence changes.
- No analyzer algorithm or threshold change.
- Preserve offline-first behavior and deterministic AQ3 evidence.
- Preserve the existing AQ3 surface identity string for this slice.
- Keep changes minimal, reversible, and testable.

## Current Evidence

At the baseline commit:

- `src/workbench_attack_suggest.py` describes itself as analysis-only and owns `AttackSuggestion`, `suggest_attack_ms`, threshold constants, and the attack-energy algorithm.
- Its Workbench coupling is `src/workbench_waveform.py`, from which it imports `read_audio_duration_ms` and `clamp_cue_start_ms`.
- `src/aq3_onset_attack_baseline.py` imports `suggest_attack_ms` from `workbench_attack_suggest`.
- `src/aq3_onset_attack_candidate_compare.py` imports `suggest_attack_ms` plus `_FRAME_MS`, `_ENERGY_RATIO_THRESHOLD`, and `_PEAK_FRACTION_THRESHOLD` from the same Workbench module.
- Product consumers including `src/workbench.py` and `src/workbench_auto_metadata.py` also import the Workbench module.
- Existing tests already cover attack behavior and AQ3 baseline/candidate parity.
- The repository already uses AST-based architecture/forbidden-import tests, so Slice 0 does not require a new import-linter dependency.

## Approaches Considered

### A. Rename the module and update every consumer in one PR

Move all implementation to `attack_analysis.py`, delete `workbench_attack_suggest.py`, and update Product and AQ consumers together.

**Rejected for Slice 0.** It creates avoidable Product blast radius and couples the ownership correction to a broad import migration.

### B. Add a canonical analysis owner and retain a compatibility facade

Move the algorithm to `attack_analysis.py`. Convert `workbench_attack_suggest.py` into a zero-logic re-export facade. Update AQ3 to use the canonical analysis module directly; leave Product consumers on the facade for now.

**Chosen.** This creates one implementation owner immediately, keeps rollback simple, and proves the strangler migration pattern without duplicating logic.

### C. Defer the correction until the physical `sample-brain-analysis` extraction

Keep current ownership until a later multi-repo cut.

**Rejected.** That would carry a known upward dependency into the extraction work and make the first repository cut larger and harder to validate.

## Chosen Design

### Canonical module

Create:

`src/attack_analysis.py`

It owns:

- `AttackSuggestion`
- `suggest_attack_ms`
- `_FRAME_MS`
- `_ENERGY_RATIO_THRESHOLD`
- `_PEAK_FRACTION_THRESHOLD`
- `_SILENCE_PEAK`
- `_CLEAR_RISE_RATIO`
- private attack-analysis helpers required by the algorithm

The public surface remains:

```python
__all__ = ["AttackSuggestion", "suggest_attack_ms"]
```

The underscore-prefixed constants remain internal implementation/configuration surfaces. AQ3 candidate comparison may continue importing the three currently frozen constants directly because that existing benchmark explicitly compares those production values. This is not a promise that they become long-term public package API.

### Remove Workbench helper dependency

`attack_analysis.py` must not import `workbench_waveform` or any other `workbench_*` module.

The two semantics it currently needs are small and analysis-local:

1. probe audio duration from the input file;
2. clamp the returned attack marker into `[0, duration_ms)`.

Implement these as private helpers inside `attack_analysis.py` using the already-required `soundfile` dependency. Preserve the exact existing observable semantics:

- missing/unreadable/non-positive-duration input -> `None` from `suggest_attack_ms`;
- duration rounds to integer milliseconds and is at least 1 ms when positive;
- negative cue value clamps to 0;
- cue value at/after duration clamps to `duration_ms - 1`.

Do not create a new generic shared-utilities module for these two helpers in Slice 0. That would widen architecture before there is evidence for another owner.

### Compatibility facade

Retain:

`src/workbench_attack_suggest.py`

It must contain no algorithmic implementation. It re-exports from `attack_analysis.py`:

- `AttackSuggestion`
- `suggest_attack_ms`
- `_FRAME_MS`
- `_ENERGY_RATIO_THRESHOLD`
- `_PEAK_FRACTION_THRESHOLD`

Its `__all__` remains the existing public pair only.

Compatibility expectations:

```python
workbench_attack_suggest.AttackSuggestion is attack_analysis.AttackSuggestion
workbench_attack_suggest.suggest_attack_ms is attack_analysis.suggest_attack_ms
```

The facade is temporary migration infrastructure. Its later deletion belongs to a separate Product-consumer migration slice.

### AQ3 ownership update

Update:

- `src/aq3_onset_attack_baseline.py`
- `src/aq3_onset_attack_candidate_compare.py`

Both must import attack analysis directly from `attack_analysis.py`.

Do **not** change the frozen AQ3 evidence field in this slice:

```python
ATTACK_SURFACE = "src.workbench_attack_suggest.suggest_attack_ms"
```

Reason: the compatibility path remains valid and existing evidence/artifact identity should not change as a side effect of an internal ownership refactor. A later explicit contract-version migration may change that identity after Product consumers have moved to the canonical owner.

## Dependency Direction After Slice 0

```text
AQ3 / Analysis
      |
      v
attack_analysis.py          <- canonical implementation owner
      ^
      | zero-logic re-export
workbench_attack_suggest.py <- temporary Product compatibility facade
      ^
      |
Workbench / Auto Metadata
```

Forbidden direction:

```text
attack_analysis.py -> workbench_*
AQ3 attack path    -> workbench_*
```

## Files in Scope

### Add

- `src/attack_analysis.py`
- `tests/test_attack_analysis.py`
- `tests/test_analysis_boundary_contract.py`

### Modify

- `src/workbench_attack_suggest.py`
- `src/aq3_onset_attack_baseline.py`
- `src/aq3_onset_attack_candidate_compare.py`
- `tests/test_workbench_attack_suggest.py`
- AQ3 tests only where an import assertion must point at the canonical module while frozen output identity remains unchanged

### Explicitly Out of Scope

- `src/db.py`
- `src/config.py`
- `src/analyze.py` broad configuration refactor
- `src/workbench_controller.py`
- `src/workbench_session.py`
- `src/workbench_session_store.py`
- `src/workbench_live_kit.py`
- `src/pattern_core.py`
- `src/track_package.py`
- QML files
- native audio code
- Windows packaging
- new repository/package publishing
- AQ6/WorkbenchRow/harmony ownership

## Architecture Gate

Add an AST-based contract test following existing repository patterns.

For the Slice 0 analysis set:

- `src/attack_analysis.py`
- `src/aq3_onset_attack_baseline.py`
- `src/aq3_onset_attack_candidate_compare.py`
- `src/gesture_analysis.py`

fail if a static import resolves to:

- any `src.workbench_*` / relative `workbench_*` module;
- `PySide6`.

Do not introduce Import Linter in this slice. The local AST gate is intentionally narrow and dependency-free. Broader package-layer enforcement belongs to the later Analysis boundary/package slice.

## Test Design

### Canonical algorithm tests

Move/copy the behavioral assertions from `tests/test_workbench_attack_suggest.py` so `tests/test_attack_analysis.py` directly validates the canonical module:

- onset after leading silence;
- immediate start near zero;
- very short signal;
- silent signal -> low confidence / zero marker;
- missing file -> `None`;
- invalid `frame_ms` -> `ValueError`.

No expected values change.

### Compatibility tests

Reduce `tests/test_workbench_attack_suggest.py` to facade behavior:

- class identity is canonical-class identity;
- function identity is canonical-function identity;
- frozen AQ3 tuning constants resolve to the canonical values;
- `__all__` remains the existing public surface.

### AQ3 regression

Run at minimum:

- `tests/test_aq3_onset_attack_baseline.py`
- `tests/test_aq3_onset_attack_candidate_compare.py`
- canonical attack-analysis tests
- compatibility-facade tests
- analysis boundary-contract tests

The existing candidate-parity test must continue proving that the frozen baseline candidate produces the same aggregate metrics as the AQ3 baseline harness.

### Broader validation

Because the facade remains a Product import surface, run:

- Product tests that import/use `workbench_attack_suggest` directly or through auto metadata / play controls;
- full repository test suite if the focused gates pass;
- Ruff static gate;
- `git diff --check` and clean-worktree verification.

No Windows distributable build is required for this internal pure-Python ownership move unless the implementation unexpectedly touches packaging/import discovery.

## Acceptance Gates

Slice 0 is complete only when all are true:

1. `attack_analysis.py` is the only file containing the attack algorithm implementation.
2. `attack_analysis.py` imports zero `workbench_*`, QML, or PySide6 modules.
3. AQ3 baseline and candidate compare import zero Workbench modules for the attack path.
4. `workbench_attack_suggest.py` is a zero-logic compatibility facade.
5. Compatibility object identity passes for `AttackSuggestion` and `suggest_attack_ms`.
6. Existing attack behavior is unchanged on frozen tests.
7. AQ3 baseline/candidate metric parity remains unchanged.
8. `ATTACK_SURFACE` remains the existing string for this slice.
9. Product consumers still pass without being migrated in the same PR.
10. No persistence/schema/config/package/repository boundary changes are included.
11. Focused tests, full relevant CI, Ruff, and repository-cleanliness gates pass.

## Failure and Rollback

The refactor is reversible because the Product keeps its existing import module.

If canonical behavior diverges or AQ3 metrics change:

- do not update expected metrics to make the refactor green;
- treat the difference as a regression;
- restore exact old behavior in `attack_analysis.py` or revert the slice.

If Product compatibility breaks, keep or expand only the zero-logic facade surface required by existing consumers. Do not duplicate implementation back into the facade.

## Follow-up Boundary Sequence

After Slice 0 is merged and verified:

1. define the broader Analysis configuration/public DTO seam (`AnalysisConfig` / result/catalog contracts only where live callsites justify them);
2. remove AQ6/WorkbenchRow/workbench_harmony leaks;
3. audit Scan/Analyze/Classify/DB ownership and callsites before assigning `db.py` to a future external repository;
4. harden an internal package-shaped Analysis API;
5. only then perform the physical `sample-brain-analysis` SSOT repository cut with wheel + consumer-CI gates.

The separate Musical Core boundaries (`WorkbenchRow` -> neutral SampleRef, Live Kit taxonomy, Product state paths) are not blockers for this Analysis Slice 0 and remain separate workstreams.
