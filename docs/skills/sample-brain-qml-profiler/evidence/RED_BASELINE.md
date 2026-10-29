# RED baseline — `sample-brain-qml-profiler` (#1307)

**Status:** recorded before the skill body existed  
**Capability set used:** generic performance habits + external Qt profiler
assumptions only (no `sample-brain-qml-profiler`)  
**Repo head at capture:** `origin/main` =
`c5c5877eb899303fde0bbed84f2502fbf81d094d`  
**Live stack at capture (primary Sample Brain venv):** PySide6 / Qt **6.11.2**

## Scenario A (primary risk)

Symptom report (synthetic, product-shaped):

> Screen-1 Browser scroll feels janky after the Library loads a few hundred
> rows. Waveforms are visible in the row. Fix QML performance.

No reproduction contract, no SHA, no dataset scale, no capture window.

## Live tooling facts that already break naive paths

Verified on this machine before writing any skill body:

| Probe | Result |
|-------|--------|
| `qmlprofiler` / `qmlprofiler.exe` on PATH | **absent** |
| PySide6 wheel `bin/` helpers | `qml`, `qmllint`, `qmlformat`, … — **no** `qmlprofiler` |
| `PySide6/plugins/qmltooling/` | `qmldbg_profiler.dll`, `qmldbg_quickprofiler.dll` present |
| `QQmlDebuggingEnabler` | importable; `profilerServices()` reports limited connector services |
| Second full Qt SDK / Qt Creator | **not** required and **not** installed for this session |
| Repo local measurement precedent | `#695` `src/workbench_waveform_research.py` can time scroll + count delegate creations on a research ListView — **not** the Screen-1 Browser surface |

## What a generic agent did / would do without the skill

Observed / reconstructed failure modes against the same symptom (not theatrical
fiction — each maps to a live gap):

1. **Guess virtualization without measurement.**  
   Read `browserList` / `reuseItems: true` in `src/workbench_qml.py` and claim
   “virtualization is broken” or “enable reuseItems” without a bounded scroll
   trace or delegate create/destroy count for the complained interaction.

2. **Assume expensive bindings from source reading.**  
   Flag waveform / theme bindings as “binding storms” because they look busy,
   with no evaluation-frequency or frame-cost evidence for the scroll window.

3. **Profile the wrong workload.**  
   Time cold startup / QML compile, or run a generic CPU sample of the whole
   process, while the user complaint is mid-session Browser scrolling.

4. **Aggregate-only evidence.**  
   Report “CPU high during scroll” or “frames dropped” with no mapping to
   QML component, delegate, Loader, waveform provider, or Python bridge call.

5. **Attribute lag to QML when Python boundary may dominate.**  
   Propose QML rewrite / caching while never counting synchronous
   `window.interaction.*` / bridge traffic on the hover/scroll path.

6. **Invent universal thresholds.**  
   Treat any frame >16 ms as a bug despite Sample Brain having no frozen
   Screen-1 frame budget for this complaint class.

7. **Hard-require external `qmlprofiler` + CMake `QT_QML_DEBUG` rebuild.**  
   Following TheQtCompanyRnD `qt-qml-profiler` literally stalls: no
   `qmlprofiler` binary in the installed PySide6 stack, and Sample Brain is
   not a CMake QML app. Installing a second Qt toolchain is out of scope.

8. **Unbounded / uninterpretable capture.**  
   Leave a profiler (if somehow available) running across unrelated UI, or
   dump a huge raw trace without warm-up → interaction → cool-down bounds.

9. **Empty / unrealistic Library.**  
   “Prove” smoothness on an empty Browser model, then declare no issue — or
   the opposite, invent a multi-GB private library (forbidden) as the only
   representative case.

10. **Optimize a low-cost path while ignoring dominant churn.**  
    Suggest micro-caching a cheap label binding while delegate create counts
    or bridge call rates dominate the interaction window (when measured).

## Fixture capturing the naive narrative

`tests/fixtures/qml_profiler/red_naive_scroll_complaint.yaml` records the
pre-skill “answer” shape: guessed cause, no reproduction, no tool discovery,
no source-mapped hotspot, premature repair.

## Verdict of RED pass

`GENERIC_PERF_INVESTIGATION_INCOMPLETE` — plausible QML guesses without
MEASURE → LOCATE → VERIFY; tooling assumptions incompatible with the live
PySide6 install; no evidence-backed hotspot.

## Same inputs required for GREEN

GREEN must:

- start from a **reproducible user action** (surface, precondition, scale,
  action, bounded window, SHA);
- **discover** live tooling (and fall back when `qmlprofiler` is absent);
- produce a compact report that separates MEASURED / HYPOTHESIS / VERIFY;
- map at least one dominant cost category to a concrete source/component
  **or** honestly return `NO_ACTIONABLE_HOTSPOT` / `PROFILE_INCONCLUSIVE`.
