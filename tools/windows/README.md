# Windows helpers — Local Workbench

For source development, start the checkout explicitly:

```powershell
python -m src.cli workbench
```

This is intentionally a developer command: it runs the code in that checkout.

## Producer runtime and desktop shortcut

Install the dedicated, provenance-checked runtime from a current `main` ref:

```powershell
git fetch origin --prune
powershell -ExecutionPolicy Bypass -File .\tools\windows\install_runtime_workbench.ps1 -CreateShortcut
```

This creates **Sample Brain Runtime Workbench** on your desktop. It uses the
runtime's dedicated `.venv` and checks its manifest, Git HEAD, working-tree
state, interpreter, and import root before starting the Workbench.

- A known older valid runtime may start as `STALE`; it never updates itself.
- Missing, dirty, or contradictory runtime provenance blocks the launch.
- The legacy `create_workbench_desktop_shortcut.ps1` helper now only creates
  this verified shortcut when the default runtime already exists.

No packaged EXE is provided. Runtime installation is local and preserves
developer checkouts without `reset`, `clean`, or branch switching.
