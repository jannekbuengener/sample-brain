<!--
Canonical Skill Source: docs/skills/sample-brain-qml-test-run/SKILL.md
Surface: docs (canonical)
Sync Status: canonical
Last Verified: 2026-10-29
Drift Policy: Cursor mirrors must match this skill body.
-->
---
name: sample-brain-qml-test-run
description: >
  Use when running, observing, classifying, or reporting Sample Brain
  PySide6 / Qt Quick / QML component or workbench pytest targets — especially
  when distinguishing harness/bootstrap, QML load/import, assertion/behavior,
  bridge, and platform failures from a mere non-zero exit code.
---

# Sample Brain QML Test-Run Skill

## Purpose

Own **running + observing + classifying + reporting** for Sample Brain
QML/component-test execution. Prove whether the selected target was collected,
assertions were exercised, and which failure layer owns the result.

Architecture contract (never dilute):

```text
Python/Core/Controller/Audio/Catalog = authoritative
QML                                 = presentation / projection / typed intent
Symptom location ≠ ownership
```

This skill does **not** primarily design new component tests, does **not** guess
product root causes, and does **not** create a second test harness.

## When To Activate

Activate when the task is to **execute or interpret** a Sample Brain QML /
PySide6 / Qt Quick test or component-level pytest target, including:

- focused `tests/test_workbench_qml_*.py` / arrangement QML pytest nodes
- `_qml_engine` / `QQmlApplicationEngine` / QML load failures under pytest
- headless vs windowed / `QT_QPA_PLATFORM` / display questions for those tests
- “the test failed” vs “the product behavior failed” classification

Do **not** activate for pure:

- designing a new QML component-test suite (route
  `sample-brain-qml-component-test` when available; otherwise note the design
  gap using current pytest/`_qml_engine` conventions — do not block)
- specialist static QML review without running tests (`sample-brain-qml-review`
  when available)
- inventing root cause for an unclear product symptom (`sample-brain-root-cause`)
- broad unrelated CI repair or product patches to force green

## Method

```text
TARGET TEST/COMPONENT
→ DISCOVER LIVE RUNNER
→ VERIFY ENVIRONMENT/IMPORTS
→ RUN SMALLEST REPRODUCIBLE TARGET
→ CAPTURE RELEVANT OUTPUT
→ CLASSIFY FAILURE LAYER
→ RERUN/ROUTE
→ PASS | HOLD
```

### 1. Discover the live runner

Discover from repository evidence — never hardcode an external Qt layout:

- `docs/WINDOWS_TEST_HARNESS.md` (Windows: `QT_QPA_PLATFORM=windows`, isolated
  `--basetemp`, pytest)
- `AGENTS.md` / CI (Linux CI: `xvfb-run -a python -m pytest`)
- existing tests using `src.workbench_qml._qml_engine` /
  `pytest.importorskip("PySide6")`

Default runner: **`python -m pytest`** on a focused node. Do not invent
`qmltestrunner` / a duplicate QML harness unless live evidence proves pytest
cannot exercise the target.

Optional helper (normalize + classify, not a framework):

```bash
python docs/skills/sample-brain-qml-test-run/scripts/qml_test_run.py --probe-env
python docs/skills/sample-brain-qml-test-run/scripts/qml_test_run.py \
  --target tests/<file>.py::<test_name> --basetemp <isolated-dir>
```

### 2. Verify environment / imports

Before blaming product QML:

- interpreter can import `PySide6` (and project deps used by the test module)
- working directory is the repository root
- do **not** blindly set `QT_QPA_PLATFORM=offscreen`; use live docs. On Windows
  Sample Brain, documented harness value is `windows`. Unsupported mode →
  `PLATFORM_WINDOW_DISPLAY_RUNTIME`, not fake PASS/FAIL
- prefer isolated `--basetemp` on Windows to avoid shared `pytest-current`
  cleanup noise (#1143 / `WINDOWS_TEST_HARNESS.md`)

### 3. Run smallest first

Order: single test node → file → focused subsystem → broader suite. Rerun only
with a reason (env fix, basetemp isolation, narrower node). Report flakiness
rather than lucky green.

### 4. Classify failure layer

| Class | Meaning |
|-------|---------|
| `TEST_HARNESS_BOOTSTRAP` | collection/import/DLL/skip-only — not product regression |
| `QML_PARSE_LOAD_IMPORT` | parse/load/import; separate invalid product QML vs missing import/runtime |
| `ASSERTION_BEHAVIOR` | boots, executes, assertion fails — candidate product/test-contract evidence |
| `PYTHON_BRIDGE_ADAPTER` | bridge/adapter path owns the failure when evidenced |
| `PLATFORM_WINDOW_DISPLAY_RUNTIME` | display/QPA/plugin/host limitation |
| `UNRELATED_BASELINE` | e.g. cleanup PermissionError after green asserts — record separately |
| `PASS` | target collected **and** assertions exercised **and** exit coherent |

Exit code alone is **not** enough. Skip/xfail/deselect must not masquerade as
PASS. Capture only relevant Qt warnings (binding loops, property/type/load
errors) — minimal evidence. Sanitize private paths.

### 5. Report (compact)

```yaml
target: <node id>
run_mode: focused-pytest | classify-only
command: [...]
environment_assumptions: []
result_state: PASS | HOLD
exit_code: <int>
counts: {passed: 0, failed: 0, errors: 0, skipped: 0}
target_collected: true|false
assertions_exercised: true|false
failure_class: <class>
relevant_evidence: []
interpretation: <short>
next_route: PASS | sample-brain-root-cause | HOLD_INFRASTRUCTURE | HOLD_QML_LOAD | sample-brain-qml-component-test | sample-brain-qml-review | HOLD_ENVIRONMENT
```

No confidence percentages. Do not invent root cause under
`ASSERTION_BEHAVIOR` — route to `sample-brain-root-cause` when cause is unclear.

## Relationships

**Standalone Guarantee:** `standalone: true`

### Can Receive From

- `sample-brain-qml-component-test` — optional designed target (when available)
- `sample-brain-qml-review` — optional review findings to verify under pytest
- `sample-brain-regression-gap` / `sample-brain-test-first` — optional frozen test to run
- generic “tests are red” handoffs

### Route If

| Condition | Target | Required | Notes |
|-----------|--------|----------|-------|
| `behavior_failed_cause_unclear` | `sample-brain-root-cause` | Yes | Do not guess product cause |
| `coverage_gap_needs_design` | `sample-brain-qml-component-test` | No | If unavailable, describe gap via current conventions |
| `qml_specialist_review_useful` | `sample-brain-qml-review` | No | If unavailable, continue with evidence only |
| `harness_or_env_blocker` | infrastructure / env HOLD | Yes | Not a product patch inside this skill |
| `pass_proven` | `PASS` / STOP | Yes | |

### When to STOP

- PASS proven with collected target + exercised assertions
- HOLD with classified layer and next route named
- Evidence would require private samples/DBs/tokens/absolute private paths
- Request expands into product implementation or a second harness

### Cycle Rules

No loop that re-runs broad suites hoping for green. Re-enter only with a new
target, env fact, or narrowed node.

## Quality Boundaries

This skill must not:

- design a new component-test suite as its primary job
- invent product root cause from a red assertion
- create a second QML test harness or bootstrap framework
- suppress Qt warnings or patch product code to force green
- claim PASS on exit 0 with skips/deselected-only / no assertions exercised
- blindly force `QT_QPA_PLATFORM=offscreen` against live Sample Brain docs
- commit private samples, DBs, caches, tokens, or machine-local secrets
