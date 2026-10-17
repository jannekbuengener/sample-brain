# Analysis Extraction S2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver #1148 by moving shared Analysis constants, BPM-normalization vocabulary, and the neutral `Features` DTO behind a product-free owner without changing analyzer behavior.

**Architecture:** Introduce one narrow `src.analysis_contracts` module. Application config/profile code adapts into it; computation modules consume it. Existing import surfaces remain compatible via re-exports. DB/scan/classification orchestration is not split in this slice.

**Tech Stack:** Python 3.12+, pytest, dataclasses, typing, existing librosa/soundfile analysis stack.

**Spec:** GitHub issue #1148 (`[ARCH][#1147][ANALYSIS S2] Freeze neutral Analysis config + DTO boundary`) at the live planning baseline.

## Global Constraints

- No global/mega `AnalysisConfig`.
- Preserve `ANALYZE_SR=44100`, `ANALYZE_HOP_LENGTH=512`, and BPM modes `none | heuristic | domain_110_170`.
- Preserve `src.analyze.Features` compatibility for current callers.
- `src.analysis_contracts` must not import config, DB, Workbench, QML, PySide6, session/controller, or application UI modules.
- No DB/schema/orchestration rewrite; no algorithm/threshold changes; no physical repo split.
- Durable truth goes to current repo canon only; no parallel `knowledge/` truth.

## Review Focus

- Importing the neutral contract must have no path/DB side effects.
- Legacy imports of `src.analyze.Features` and `src.config.ANALYZE_*` must still work.
- Invalid BPM-normalization values must retain current rejection behavior.
- Track-analysis cache fingerprints must remain identical for the same effective inputs.
- Synthetic analysis/gesture/canonical-audio behavior must remain deterministic and unchanged.

---

### Task 1: Freeze neutral contract tests and owner

**Files:**
- Create: `src/analysis_contracts.py`
- Create: `tests/test_analysis_public_contract.py`
- Create: `tests/test_analysis_contract_boundary.py`

**Interfaces:**
- Produces: `ANALYZE_SR: int`, `ANALYZE_HOP_LENGTH: int`, `BPMNormalizationMode`, `VALID_BPM_NORMALIZATION_MODES`, `validate_bpm_normalization(mode: str) -> str`, `Features`.

- [ ] Write failing tests proving the module exists, exposes exact current constants/modes/Features fields, and its import closure rejects product/config/DB/UI dependencies.
- [ ] Run those tests and verify RED for missing module/symbols.
- [ ] Implement the minimal neutral contract owner.
- [ ] Run focused tests and verify GREEN.

### Task 2: Rewire current owners with compatibility preserved

**Files:**
- Modify: `src/analyze.py`
- Modify: `src/config.py`
- Modify: `src/config_loader.py`
- Modify: `src/canon_audio.py`
- Modify: `src/gesture_analysis.py`
- Modify: `src/track_analysis_cache.py`
- Test: existing config/analyze/canon/gesture/cache tests plus `tests/test_analysis_public_contract.py`.

**Interfaces:**
- Consumes Task 1 symbols.
- Produces legacy-compatible imports from `src.analyze.Features` and `src.config.ANALYZE_*`.

- [ ] Extend RED tests for compatibility re-exports, single BPM-mode authority, and product-free package-candidate imports.
- [ ] Run and verify RED for current ownership/import graph.
- [ ] Rewire imports/re-exports with no semantic change.
- [ ] Run focused regression set and verify GREEN.

### Task 3: Freeze durable contract and canon wiring

**Files:**
- Create: `docs/ANALYSIS_PUBLIC_CONTRACT_V1.md`
- Modify: `docs/TARGET_ARCHITECTURE.md`
- Modify: `docs/CANON_INDEX.md`

**Interfaces:**
- Documents the exact Task 1/2 ownership boundary; does not duplicate issue execution evidence.

- [ ] Write the contract with neutral inputs/results, config ownership, exclusions, and #1149 handoff.
- [ ] Add one narrow architecture link/direction update and one Canon Index entry.
- [ ] Run `python tools/check_canon_drift.py` and documentation/link-focused tests if present.

### Task 4: Validate, review, and package the branch

**Files:**
- No new production scope.

- [ ] Run focused #1148 regression suite.
- [ ] Run `python -m ruff check .`.
- [ ] Run `python tools/check_canon_drift.py`.
- [ ] Run `git diff --check`.
- [ ] Run the broadest practical pytest suite; classify any known Windows baseline failures explicitly.
- [ ] Review the complete diff for scope creep, duplicate authorities, hidden application imports, behavior changes, and accidental path/private-data leakage.
- [ ] Commit in small scoped commits, push branch, open PR with `Fixes #1148`, then inspect CI/review feedback before any merge.
