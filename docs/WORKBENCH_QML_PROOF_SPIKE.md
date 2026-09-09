# Screen-1 Qt Quick Proof Spike

Der Qt-Quick-Pfad ist ein optionaler, reversibler Proof für Issue #548. Er
ersetzt weder den Tk-Default noch den Runtime-Launcher und enthält keine
Installer- oder Distributionsentscheidung.

## Lokaler Start

```powershell
python -m pip install -e ".[qtquick]"
python -m src.cli workbench --qml-proof-spike
python -m src.cli workbench --qml-proof-spike --qml-state screen1-harmonic-4panel
python -m src.cli workbench --qml-proof-spike --qml-virtualization-probe
```

Die beiden #538-Captures laufen nur aus einer `VALID` dedizierten Runtime. Der
Command muss aus dem Runtime-Root mit dessen eigenem Interpreter gestartet
werden; ein beliebiger Checkout mit fremdem `--runtime-root` wird fail-closed
abgewiesen:

```powershell
Push-Location <runtime-root>
& .\.venv\Scripts\python.exe -m src.cli workbench --qml-proof-spike --visual-acceptance `
  --runtime-root . --evidence-dir <lokaler-output-ordner>
Pop-Location
```

Die Capture-Dateien und das Manifest bleiben außerhalb des Repositories. Ein
technischer Lauf ersetzt keine Owner-Visual-Acceptance.

## Späteres Migrations-Follow-up

Replace eager QVariant-list handoff with production-scale Qt model / lazy data
adapter before full Screen-1 migration.

Die 50k-Probe beweist die QML-Delegate-Virtualisierung, materialisiert den
Python-Datenbestand für den Spike jedoch weiterhin vollständig. Das ist kein
Blocker für diesen Spike und keine Migrationsentscheidung.
