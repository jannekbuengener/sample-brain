# Windows regression harness (#1143)

## Ownership contract

Nested pytest suites use the running interpreter (`sys.executable`) and a
dedicated child directory below the invoking test's `tmp_path` as `--basetemp`.
They must not rely on pytest's shared, user-wide numbered-directory cleanup.
The subprocess completes before the parent test returns; failures retain both
stdout and stderr. No global pytest temporary directories are deleted or repaired.

Each QML engine owns its waveform polling and channel-rack timers. Destroying
the engine while the application remains alive must destroy those timers and
close its waveform loader. Failed QML loading must also close the loader.
Loader close remains nonblocking: an in-flight file decode may finish, but no
new work is accepted. Lifecycle tests release synthetic decodes and join their
owned worker with a bounded wait before completing. Do not turn GUI teardown
into an unbounded wait for filesystem I/O.

## Evidence boundaries

At baseline `ab11f422c93a84439ef9f547314abfab4729a979`, the two nested
regression suites completed their assertions but exited 1 during shared
`pytest-current` cleanup (`WinError 5`). Running their targets directly with an
explicit isolated basetemp passed 41 tests. The parent basetemp alone does not
isolate subprocesses.

An engine-destruction probe confirmed an active waveform worker and unparented
polling timer surviving the engine. This is a distinct ownership defect.

The native Windows footer baseline reported 13 passed and process exit 0, but
also emitted `0x8001010d` inside the first runtime test's nested Qt event loop.
Thus previous-test worker leakage is not required for that diagnostic. Its
native cause remains UNKNOWN; neither passing pytest assertions nor the
ownership repair proves that diagnostic fixed. Do not suppress it or treat a
log containing it as a clean native run.
The separate native investigation is tracked in
[#1145](https://github.com/jannekbuengener/sample-brain/issues/1145).

## Reproducible local run

Use an activated project environment and an external, new output directory for
each run. Replace the output argument with a deliberately selected local path;
never point basetemp at an existing directory containing valuable data.

```powershell
$runRoot = Join-Path $env:TEMP ('sample-brain-tests-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $runRoot | Out-Null
$env:PYTHONFAULTHANDLER = '1'
$env:QT_QPA_PLATFORM = 'windows'
$env:PYTHONPYCACHEPREFIX = Join-Path $runRoot 'pycache'
git rev-parse HEAD | Out-File (Join-Path $runRoot 'commit.txt')
python -c "import sys, pytest; print(sys.executable); print(sys.version); print(pytest.__version__)" |
    Out-File (Join-Path $runRoot 'interpreter.txt')
python -m pytest -q -p no:cacheprovider --basetemp=(Join-Path $runRoot 'pytest') `
    --junitxml=(Join-Path $runRoot 'results.xml') *> (Join-Path $runRoot 'suite.log')
$suiteExit = $LASTEXITCODE
$suiteExit | Out-File (Join-Path $runRoot 'exit-code.txt')
Select-String -Path (Join-Path $runRoot 'suite.log') -Pattern 'fatal exception|access violation|PermissionError'
```

Record assertion failures, process exit, and native diagnostics separately.
Classify every remaining failure as `REGRESSION_FROM_1143`, `BASELINE_EXISTING`,
`INDEPENDENT_NEW_FINDING`, `ENVIRONMENT/HOST`, or `UNKNOWN`, using unchanged-main
comparisons where required. An incomplete run or UNKNOWN cause is not PASS.
Optional CLAP/Torch behavior, analysis algorithms and Workbench UX are outside
this harness repair.
