# GREEN validation — `sample-brain-qml-test-run` (#1306)

**Status:** after skill + helper  
**Same RED classes exercised** (not renamed away)  
**Helper:** `docs/skills/sample-brain-qml-test-run/scripts/qml_test_run.py`  
**Repo branch:** `feat/1306-qml-test-run-skill`

## Scenario 1 — Passing focused QML pytest

```text
target: tests/test_workbench_qml_worker_lifetime.py::test_qml_load_failure_closes_created_waveform_worker
run_mode: focused-pytest
QT_QPA_PLATFORM: windows (WINDOWS_TEST_HARNESS.md)
basetemp: isolated under temp (not shared pytest-current)
failure_class: PASS
target_collected: true
assertions_exercised: true
exit_code: 0
next_route: PASS
```

Live run via helper returned `result_state: PASS` with counts `passed=1`.

## Scenario 2 — Genuine behavior / assertion failure

Transcript fixture: `tests/fixtures/qml_test_run/transcripts/assertion_behavior_fail.txt`

```text
failure_class: ASSERTION_BEHAVIOR
assertions_exercised: true
next_route: sample-brain-root-cause
```

No product root cause invented.

## Scenario 3 — Harness / bootstrap failure

Transcript fixture: `tests/fixtures/qml_test_run/transcripts/harness_bootstrap_import.txt`  
(mirrors live RED blocked-interpreter collection `ImportError` / DLL policy)

```text
failure_class: TEST_HARNESS_BOOTSTRAP
target_collected: false
assertions_exercised: false
next_route: HOLD_INFRASTRUCTURE
```

Not labeled as QML product regression.

## Scenario 4 — QML parse / load / import failure

Transcript fixture: `tests/fixtures/qml_test_run/transcripts/qml_parse_load_fail.txt`

```text
failure_class: QML_PARSE_LOAD_IMPORT
evidence includes: keine QML roots; module "QtQuick" is not installed
next_route: HOLD_QML_LOAD
```

Interpretation requires separating invalid product QML vs missing import/runtime;
not musical/product authority guessing.

## Additional RED→GREEN delta

Cleanup noise transcript `cleanup_noise_after_pass.txt` (PASSED asserts +
`PermissionError` on `pytest-current`, exit≠0):

- RED naive exit-code-only → “product/unknown fail”
- GREEN helper → `UNRELATED_BASELINE` with `assertions_exercised=true`

Skip-only (`1 skipped`, exit 5) → `TEST_HARNESS_BOOTSTRAP` / HOLD, not PASS.

## Related skills availability note

At validation time on `origin/main`, `#1303` / `#1304` / `#1305` remain OPEN.
Routes to `sample-brain-qml-review` / `sample-brain-qml-component-test` are
optional; when unavailable, continue with evidence and current pytest /
`_qml_engine` conventions without blocking.

## Verdict

`SAMPLE_BRAIN_QML_TEST_RUN_SKILL_EFFECTIVE` (pending PR merge + main verify)
