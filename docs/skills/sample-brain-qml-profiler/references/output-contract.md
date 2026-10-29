# Output contract — Sample Brain QML profiler

## Capture schema (`sample_brain_qml_profile_v1`)

```json
{
  "schema": "sample_brain_qml_profile_v1",
  "reproduction": {
    "build_sha": "<git sha or null if unknown>",
    "surface": "screen1.browserList",
    "precondition": "Library revealed; synthetic rows loaded",
    "dataset_scale": "synthetic_400_rows",
    "user_action": "scroll contentY 0->max + burst",
    "capture_window": "warmup_200ms + interaction + cooldown_200ms",
    "observed_symptom": "scroll stutter"
  },
  "tool": {
    "name": "repo_instrumentation|qmlprofiler_qtd|...",
    "version": "<tool or PySide6 version>",
    "discovery_notes": "short live discovery note"
  },
  "events": [
    {
      "category": "delegate_lifecycle",
      "component": "browserRow",
      "source": "src/workbench_qml.py:browserList delegate",
      "line": null,
      "count": 80,
      "duration_ms": 42.5,
      "details": "create during scroll burst"
    }
  ],
  "confounders": ["instrumentation_overhead_checked"]
}
```

Categories: `frame_render`, `binding`, `delegate_lifecycle`, `layout`,
`js_qml`, `resource_waveform`, `python_bridge`, `memory`, `other`.

## Summary verdicts

- `HOTSPOT_PROVEN`
- `NO_ACTIONABLE_HOTSPOT`
- `PROFILE_INCONCLUSIVE`

Always keep MEASURED / HYPOTHESIS / VERIFY separated. No confidence %.
