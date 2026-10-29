# GREEN validation — `sample-brain-qml-profiler` (#1307)

**Same RED symptom class:** Browser scroll / interaction lag without measurement  
**Capability:** `sample-brain-qml-profiler` + `scripts/qml_profiler_summarize.py`  
**RED fixture contrast:** `tests/fixtures/qml_profiler/red_naive_scroll_complaint.yaml`

## Tool discovery (live)

```bash
python docs/skills/sample-brain-qml-profiler/scripts/qml_profiler_summarize.py discover
```

Observed on authoring machine (re-verify per session):

- PySide6 / Qt **6.11.2** available from Sample Brain venv
- `qmlprofiler` CLI **absent**
- `qmldbg_*profiler*` plugins present under PySide6 `qmltooling`
- Decision tree falls through to repo instrumentation + helper summarize
- Explicit `do_not` includes installing a second Qt SDK

## Scenario A — proven hotspot (delegate churn)

Input: `tests/fixtures/qml_profiler/scenario_a_delegate_churn.json`

```bash
python docs/skills/sample-brain-qml-profiler/scripts/qml_profiler_summarize.py summarize \
  --json tests/fixtures/qml_profiler/scenario_a_delegate_churn.json
```

Expected:

- `verdict=HOTSPOT_PROVEN`
- Dominant category `delegate_lifecycle` / component `browserRow`
- Source mapped to `src/workbench_qml.py` (component marker; line not invented)
- MEASURED vs HYPOTHESIS vs VERIFY separated in summary
- Closes RED miss: no longer “guess reuseItems / rewrite Browser”

## Scenario B — variant transfer (bridge traffic)

Input: `tests/fixtures/qml_profiler/scenario_b_bridge_traffic.json`

- Different interaction (hover pass) and cost category (`python_bridge`)
- `verdict=HOTSPOT_PROVEN`
- Demonstrates transfer beyond delegate-only thinking

## Scenario C — honest negative / inconclusive

1. `scenario_c_no_hotspot.json` → `NO_ACTIONABLE_HOTSPOT`  
   Flat bounded costs; do not invent a bug.
2. `scenario_c_inconclusive.json` → `PROFILE_INCONCLUSIVE`  
   Confounders (`instrumentation_overhead_unseparated`, `unstable_capture`)
   and unmapped dominant candidate — inconclusive ≠ wrong theory.

## Behavioral delta vs RED

| Dimension | RED naive | GREEN skill |
|-----------|-----------|-------------|
| Reproduction | missing | required fields present |
| Tool discovery | assumed `qmlprofiler` | discover + fallback |
| Evidence | speculative | MEASURED hotspots |
| Source map | none | mapped or honestly unresolved |
| Verdict | guessed fix | HOTSPOT_PROVEN / NO_ACTIONABLE / INCONCLUSIVE |

## Exit

`SAMPLE_BRAIN_QML_PROFILER_SKILL_EFFECTIVE` when packaging, contract tests, and
CI also pass.
