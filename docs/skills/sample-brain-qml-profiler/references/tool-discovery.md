# Tool discovery notes — Sample Brain QML profiler

Re-run discovery every session. Do not copy stale paths.

```bash
python docs/skills/sample-brain-qml-profiler/scripts/qml_profiler_summarize.py discover
```

## Expected shapes (illustrative)

### PySide6 wheel without `qmlprofiler` CLI (common)

- `qmlprofiler_cli: null`
- `pyside6.available: true` with Qt version from `qVersion()`
- `qmltooling_profiler_plugins` may list `qmldbg_profiler*` / `qmldbg_quickprofiler*`
- Prefer bounded **repo instrumentation** / bridge counters for Screen-1 shaped
  interactions rather than installing a second Qt SDK

### Full Qt SDK with `qmlprofiler`

- Use CLI only after verifying major-version compatibility with the running
  PySide6/Qt
- Keep captures bounded; summarize with the helper (JSON or `.qtd`)

## Anti-patterns

- Assuming Qt 6.12+ features
- CMake `-DQT_QML_DEBUG` rebuild rituals meant for C++ QML apps when the app is
  PySide6-hosted
- Treating research spike ListView timings as proof about Screen-1 Browser
  without repeating the Browser reproduction
