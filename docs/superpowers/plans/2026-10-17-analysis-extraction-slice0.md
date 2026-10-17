# Analysis Extraction Slice 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move attack/onset suggestion ownership from a Workbench-named module to a canonical analysis module without changing Product behavior, AQ3 evidence identity, packaging, or repository boundaries.

**Architecture:** `src/attack_analysis.py` becomes the only implementation owner. `src/workbench_attack_suggest.py` remains a temporary zero-logic compatibility facade for Product callers, while AQ3 imports the canonical analysis module directly. The canonical module reuses `src.canon_audio.probe_audio` for audio probing and owns only the local numeric clamp it needs.

**Tech Stack:** Python 3.12+, NumPy, soundfile, pytest, AST-based contract tests, existing Sample Brain CI/Ruff configuration.

**Spec:** `docs/superpowers/specs/2026-10-17-analysis-extraction-slice0-design.md`

## Global Constraints

- Baseline architecture is the owner-approved Slice 0 spec in PR #1140.
- No physical repository split, new package distribution, wheel, plugin framework, IPC, service, or process boundary.
- No DB, WorkbenchSession, Arrangement, Live Kit, Pattern Core, Track Package, QML, native-audio, persistence, or Windows-packaging changes.
- No attack algorithm or threshold changes.
- Preserve offline-first behavior and deterministic AQ3 evidence.
- Preserve `ATTACK_SURFACE = "src.workbench_attack_suggest.suggest_attack_ms"` for this slice.
- `src/workbench_attack_suggest.py` must contain no algorithmic implementation after the slice.
- No direct push to `main`; use an isolated branch/worktree and normal PR governance.

## Review Focus

- Missing, unreadable, empty, or non-positive-duration audio must keep returning `None` from `suggest_attack_ms` rather than raising.
- Very short and silent audio must preserve current marker/confidence behavior exactly.
- Duration conversion through `canon_audio.probe_audio` must preserve the current integer-millisecond rounding/clamp behavior.
- AQ3 frozen identity strings and baseline-vs-candidate aggregate parity must not drift.
- Product-side monkeypatch/import surfaces must remain valid through the compatibility facade.

---

### Task 1: Establish canonical attack-analysis owner

**Files:**
- Create: `src/attack_analysis.py`
- Create: `tests/test_attack_analysis.py`
- Reference: `src/workbench_attack_suggest.py`
- Reference: `src/canon_audio.py`

**Interfaces:**
- Consumes: `src.canon_audio.probe_audio(path: Path) -> AudioTimebase | None`
- Produces: `AttackSuggestion`, `suggest_attack_ms(path, *, frame_ms, energy_ratio_threshold, peak_fraction_threshold)`, and the existing frozen internal constants used by AQ3 candidate comparison.

- [ ] **Step 1: Write canonical behavioral tests before moving implementation**

Create `tests/test_attack_analysis.py` with the current assertions now living in `tests/test_workbench_attack_suggest.py`: leading silence, immediate start, very short signal, silent signal, missing file, invalid `frame_ms`. Add one explicit parity case for file-end duration/clamp behavior so `canon_audio.probe_audio` conversion cannot shift the result by 1 ms unnoticed.

- [ ] **Step 2: Run the new tests and confirm they fail because the canonical module does not exist**

Run: `python -m pytest -q tests/test_attack_analysis.py`

Expected: FAIL during import with `src.attack_analysis` missing.

- [ ] **Step 3: Create `src/attack_analysis.py` with the existing algorithm unchanged**

Move implementation ownership from `workbench_attack_suggest.py` without changing thresholds, dataclass fields, confidence values, method strings, reasons, or numerical behavior. Use `from .canon_audio import probe_audio` for duration probing, convert `AudioTimebase.duration_seconds` with the same millisecond rounding/minimum semantics as the old helper, and keep the cue clamp private. Import no `workbench_*`, PySide6, or QML module. Keep `__all__ = ["AttackSuggestion", "suggest_attack_ms"]`.

- [ ] **Step 4: Run canonical behavior tests**

Run: `python -m pytest -q tests/test_attack_analysis.py`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

`git commit -m "refactor(analysis): add canonical attack analysis owner"`

---

### Task 2: Convert Workbench module to compatibility facade and rewire AQ3

**Files:**
- Modify: `src/workbench_attack_suggest.py`
- Modify: `src/aq3_onset_attack_baseline.py`
- Modify: `src/aq3_onset_attack_candidate_compare.py`
- Modify: `tests/test_workbench_attack_suggest.py`
- Modify if required by import assertions only: `tests/test_aq3_onset_attack_candidate_compare.py`

**Interfaces:**
- Consumes: Task 1 `src.attack_analysis` surface.
- Produces: backward-compatible Workbench import path with object identity preserved; AQ3 canonical imports with frozen evidence identity unchanged.

- [ ] **Step 1: Rewrite Workbench tests as facade-contract tests first**

Assert object identity for `AttackSuggestion` and `suggest_attack_ms`; equality for `_FRAME_MS`, `_ENERGY_RATIO_THRESHOLD`, `_PEAK_FRACTION_THRESHOLD`; and unchanged `__all__ == ["AttackSuggestion", "suggest_attack_ms"]`.

- [ ] **Step 2: Run facade tests and confirm they fail against the old implementation-owning module**

Run: `python -m pytest -q tests/test_workbench_attack_suggest.py`

Expected: FAIL on canonical object-identity/facade expectations.

- [ ] **Step 3: Replace `src/workbench_attack_suggest.py` with a zero-logic re-export facade**

Re-export `AttackSuggestion`, `suggest_attack_ms`, `_FRAME_MS`, `_ENERGY_RATIO_THRESHOLD`, `_PEAK_FRACTION_THRESHOLD` from `src.attack_analysis`. Retain the public `__all__` pair only. No duplicate private helpers or DSP logic.

- [ ] **Step 4: Rewire AQ3 imports to `src.attack_analysis`**

Update baseline and candidate-compare imports to the canonical module. Do not change `ATTACK_SURFACE = "src.workbench_attack_suggest.suggest_attack_ms"`. Existing `monkeypatch.setattr(compare, "suggest_attack_ms", ...)` behavior must remain valid because the name stays bound in the candidate-compare module namespace.

- [ ] **Step 5: Run focused compatibility + AQ3 tests**

Run:
`python -m pytest -q tests/test_attack_analysis.py tests/test_workbench_attack_suggest.py tests/test_aq3_onset_attack_baseline.py tests/test_aq3_onset_attack_candidate_compare.py tests/test_workbench_auto_metadata.py tests/test_workbench_play_controls.py`

Expected: PASS, including frozen `ATTACK_SURFACE`, candidate-vs-baseline aggregate parity, and Product-side monkeypatch/import behavior.

- [ ] **Step 6: Commit Task 2**

`git commit -m "refactor(analysis): route aq3 through canonical attack owner"`

---

### Task 3: Add the narrow Analysis boundary regression gate

**Files:**
- Create: `tests/test_analysis_boundary_contract.py`

**Interfaces:**
- Consumes: source files from Tasks 1-2 plus existing `src/gesture_analysis.py`.
- Produces: deterministic AST guard preventing Slice-0 analysis surfaces from importing Product/Workbench UI dependencies.

- [ ] **Step 1: Write the AST contract test**

Inspect static imports in exactly `src/attack_analysis.py`, `src/aq3_onset_attack_baseline.py`, `src/aq3_onset_attack_candidate_compare.py`, and `src/gesture_analysis.py`. Fail when imports resolve to relative/absolute `workbench_*` modules or `PySide6`. `gesture_analysis.py` is intentionally preventive.

- [ ] **Step 2: Run the boundary test**

Run: `python -m pytest -q tests/test_analysis_boundary_contract.py`

Expected: PASS if Tasks 1-2 are correct. Fix a violating dependency rather than weakening the gate.

- [ ] **Step 3: Commit Task 3**

`git commit -m "test(analysis): enforce slice 0 dependency boundary"`

---

### Task 4: Final regression and PR governance

**Files:**
- No planned new production files beyond Tasks 1-3.
- Update only files required to fix regressions within Slice 0 scope.

**Interfaces:**
- Consumes: completed Tasks 1-3.
- Produces: validated implementation branch ready for review/merge.

- [ ] **Step 1: Run the focused Slice 0 suite again**

Run: `python -m pytest -q tests/test_attack_analysis.py tests/test_workbench_attack_suggest.py tests/test_analysis_boundary_contract.py tests/test_aq3_onset_attack_baseline.py tests/test_aq3_onset_attack_candidate_compare.py tests/test_workbench_auto_metadata.py tests/test_workbench_play_controls.py`

Expected: PASS.

- [ ] **Step 2: Run static and repository-hygiene gates**

Run: `python -m ruff check .`, `git diff --check`, and `python tools/check_canon_drift.py`.

Expected: PASS.

- [ ] **Step 3: Run the full repository test suite**

Run the repo-supported full suite (`xvfb-run -a python -m pytest -q tests` on Linux where required, otherwise the equivalent local command). Separate any known pre-existing environment/baseline failure from a Slice 0 regression with evidence.

- [ ] **Step 4: Verify final diff and scope**

Confirm one canonical algorithm implementation only; no `attack_analysis -> workbench_*` edge; AQ3 imports canonical owner; Product imports remain compatible through the facade; no DB/config/session/QML/native-audio/packaging/repository-split changes; no private samples, DBs, caches, generated audio, credentials, or local paths.

- [ ] **Step 5: Push branch and open/update one focused PR**

PR body must include the owner-approved spec reference PR #1140, exact commits, focused/full test results, Ruff/diff-check/canon-drift results, frozen `ATTACK_SURFACE` confirmation, and confirmation that no physical repo split occurred.

- [ ] **Step 6: Review gate before merge**

Inspect all CI checks, review submissions, inline threads, and bot comments on the final PR head. Fix all Critical/Important findings in scope, rerun relevant validation, and do not merge with unresolved relevant feedback or failing/unknown required checks.

- [ ] **Step 7: Merge only when repo governance is satisfied and merge is authorized**

Never push directly to `main`, force-push, bypass checks, or hide a regression by changing frozen AQ3 expected values.