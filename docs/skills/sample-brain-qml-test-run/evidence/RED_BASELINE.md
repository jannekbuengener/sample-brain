# RED baseline — `sample-brain-qml-test-run` (#1306)

**Status:** recorded before the skill body existed  
**Capability set used:** generic pytest / Qt habits only (no `sample-brain-qml-test-run`)  
**Repo head at capture:** `c5c5877eb899303fde0bbed84f2502fbf81d094d` (`origin/main`)  
**Live runner authority consulted after the fact (not during RED):**  
`docs/WINDOWS_TEST_HARNESS.md`, `AGENTS.md`, `tests/test_workbench_qml_worker_lifetime.py`

## Scenario

Run and interpret Sample Brain QML/component-adjacent pytest targets, especially
`tests/test_workbench_qml_worker_lifetime.py` (engine teardown + QML load
failure cleanup) without a specialist execution/classification skill.

## What a generic agent did / would do

1. Reach for an external Qt entry point (`qmltestrunner` / `qmllint`) that is
   **not** present on this host (`which` → none). Sample Brain's live path is
   **pytest** + `src.workbench_qml._qml_engine`, not a second Qt test runner.
2. Prefer a convenient project `.venv` without verifying imports. On this host
   that interpreter fails collecting QML tests with:
   `ImportError: DLL load failed while importing _collections_cy` (policy-
   blocked native extension). Exit code **4**, `ERROR` during collection —
   zero QML assertions exercised.
3. Treat “tests finished with a non-zero exit” as product/QML failure even when
   the selected node **PASSED** and the non-zero exit comes from shared
   `pytest-current` cleanup (`PermissionError` / `WinError 5`) — the exact
   class already documented in `docs/WINDOWS_TEST_HARNESS.md` (#1143).
4. Blindly set `QT_QPA_PLATFORM=offscreen` from generic Qt advice. Live Sample
   Brain Windows harness documents `QT_QPA_PLATFORM=windows` plus an isolated
   `--basetemp`. Unsupported/mismatched platform must be classified as
   environment limitation, not silently rewritten into a fake PASS/FAIL story.
5. Treat “no failed assertions” / skip-only runs as success. A synthetic
   `pytest.importorskip("NoSuchQtThing")` node produced `1 skipped` with exit
   **5** and never ran the intended assertion — not a QML product PASS.

## Misclassifications observed

| Observation | Naive label | Correct family |
|-------------|-------------|----------------|
| Collection `ImportError` / blocked DLL before any QML load | “QML/product broken” | `TEST/HARNESS/BOOTSTRAP` (or env policy) |
| Node PASSED + session cleanup `PermissionError` | “test failed / regression” | `UNRELATED BASELINE` / harness cleanup (see #1143 doc) |
| Missing `qmltestrunner` | “need new Qt test harness” | Discover live pytest runner; do **not** invent a second harness |
| Skip-only / importorskip | “green enough” | Not PASS — target not collected+executed |
| Blind `offscreen` | “headless CI parity” | Discover supported mode from `WINDOWS_TEST_HARNESS.md` / CI (`xvfb-run` on Linux) |

## Rationalization observed

“Exit code tells the truth” and “Qt tests need offscreen / qmltestrunner.”
Both rationalizations break Sample Brain’s documented Windows QML pytest path
and conflate harness/bootstrap with product behavior.

## Verdict of RED pass

`GENERIC_QML_TEST_RUN_INCOMPLETE` — real execution/diagnosis weakness without
the skill: wrong runner assumptions, env/bootstrap misread as product, PASS
claimed without exercised assertions, cleanup noise treated as regression.

## Same inputs required for GREEN

GREEN must use the **same** live targets / failure classes:

1. Passing focused QML pytest node with correct runner + exercised asserts → PASS
2. Genuine assertion/behavior failure → `ASSERTION/BEHAVIOR` (no invented root cause)
3. Collection/bootstrap import failure → `TEST/HARNESS/BOOTSTRAP` (not product)
4. Invalid QML load path (`QML_SOURCE` forced invalid in
   `test_qml_load_failure_closes_created_waveform_worker`) →
   `QML PARSE/LOAD/IMPORT` harness-owned expectation, not “BPM/product logic”
