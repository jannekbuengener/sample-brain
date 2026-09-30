# Screen-1 UI Acceptance (local Windows)

## Purpose

Smallest repeatable local acceptance workflow for Sample Brain Screen 1 after a
UI change:

```text
PRECHECK → START_APP → FOCUS_APP → SNAPSHOT_INITIAL → RUN_CASES → RESTORE → CAPTURE_EVIDENCE → FINAL_RESULT
```

This is **not** Owner Visual Acceptance (`docs/WORKBENCH_VISUAL_ACCEPTANCE.md`).
It is a fail-closed desktop smoke/acceptance contract for Cursor agents on a
local Windows host.

## Entry point

```powershell
python tools/screen1_ui_acceptance.py
python tools/screen1_ui_acceptance.py --keep-app
# debug only — never default:
python tools/screen1_ui_acceptance.py --allow-reuse
```

Exit codes:

| Code | Meaning |
|------|---------|
| 0 | PASS |
| 1 | FAIL |
| 2 | PARTIAL |
| 3 | BLOCKED |

Default V1 starts a fresh `workbench --qml-screen1` from the repo interpreter and
binds cases to that PID. An already-open Sample Brain window yields **BLOCKED**
(no silent reuse). `--allow-reuse` is debug-only.

## Cases (V1)

1. **app_start** — start `python -m src.cli workbench --qml-screen1`, detect window owned by that PID, require `Display preferences` in UIA, capture screenshot.
2. **display_preferences** — UIA-only open/verify/Esc(+outside-click)/restore for `Display preferences` and unique open markers (`Reset Layout`, `Save Workspace Preset`, `Density`, `Motion`, …).
3. **harmonic_match** — UIA button invoke; sample-row selection may be `VISUAL_FALLBACK` while ListView rows lack UIA; **open/restore require a real visual panel delta** (sticky `Harmonic Matches` UIA title alone is never PASS).

A click acknowledgement alone is never PASS.

## Focus guard

Before each case the runner brings the `Sample Brain` window to the foreground
and requires `GetForegroundWindow() == hwnd`. Shown-but-not-foreground is
**BLOCKED**, not PASS. This reduces false results from IDE z-order steals.

## Evidence

Written **outside** the repository:

```text
%USERPROFILE%\.sample-brain\ui-acceptance\<run-id>\
```

Override root with `SAMPLE_BRAIN_UI_ACCEPTANCE_EVIDENCE_ROOT`.

Each case writes machine-readable JSON (`schema_version: 1`) plus BMP screenshots
and UIA name dumps. Do not commit evidence.

## Architecture boundary

- No `windows-mcp` Python dependency in Sample Brain.
- Desktop automation uses Windows built-in UI Automation via
  `tools/windows/screen1_ui_acceptance_uia.ps1` plus ctypes focus/input/capture.
- Cursor Windows-MCP remains an optional agent capability aligned with the same
  cases; it is not required to import the runner.

## Accessibility follow-ups (not in this slice)

- Expose browser ListView rows to UIA.
- Expose Harmonic Match pane open-state / title to UIA.
- Add explicit `Accessible.name` on `harmonicMatchButton`.
