# FL Workflow Reconstruction Analyzer (#1322)

Deterministic offline reconstruction of producer flows from the #1321 recorder SQLite sidecar.

Contract: [`docs/rnd/FL_WORKFLOW_RECONSTRUCTION_1322.md`](../../docs/rnd/FL_WORKFLOW_RECONSTRUCTION_1322.md)

**Does not** modify the recorder. **Does not** emit #1323 rolling reports.

## Run

```powershell
cd <repo>\tools\fl_workflow_analyzer
python -m fl_workflow_analyzer analyze --clear-previous
python -m fl_workflow_analyzer status
```

Optional: `--db <path\to\workflow.sqlite3>` or `--root <observer-root>`.

Default DB: `%LOCALAPPDATA%/sample-brain/workflow-observer/workflow.sqlite3`

## Tests

```powershell
python -m pytest -q tests/test_fl_workflow_analyzer.py
```

## Privacy

Derived tables never restore typed text, paths, project names, clipboard, or screenshots.
Raw events remain the immutable evidence source.
