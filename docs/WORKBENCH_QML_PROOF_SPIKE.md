# Screen-1 Qt Quick Production Shell and Proof Harness

`LOCK_PYSIDE6_QML` ist die Renderer-Richtung für neue Screen-1-Arbeit. Die
kanonische optionale Shell liegt in `src/workbench_qml.py`; sie bleibt ein
dünner Renderer-/Intent-Layer über dem Python-authoritativen Core. Der
Proof-Harness in `src/workbench_qml_spike.py` verwendet exakt diese Shell für
Fixture, Virtualisierungsprobe und Visual Acceptance.

Tk bleibt Default und Legacy/Fallback, bis spätere Slices weitere Screen-1-
Flächen migrieren. Diese Entscheidung umfasst weder Installer/Distribution
noch eine vollständige Migration.

## Lokaler Start

```powershell
python -m pip install -e ".[qtquick]"
python -m src.cli workbench --qml-screen1
python -m src.cli workbench --qml-screen1 --qml-state screen1-harmonic-4panel
python -m src.cli workbench --qml-proof-spike
python -m src.cli workbench --qml-proof-spike --qml-state screen1-harmonic-4panel
python -m src.cli workbench --qml-proof-spike --qml-virtualization-probe
```

`--qml-screen1` und `--qml-proof-spike` sind gegenseitig exklusiv. Ein
expliziter Production-QML-Start fällt bei fehlendem Qt nicht auf Tk zurück,
sondern endet mit einem klaren Fehler.

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

Die Capture-Dateien und das Manifest bleiben außerhalb des Repositories. Die
frühere Owner-Acceptance begründet `LOCK_PYSIDE6_QML`, ersetzt aber nicht die
visuelle Abnahme des neuen Production-Shell-HEAD. Fehlende neue Owner-Acceptance
blockiert nicht `PR_OPEN`, wohl aber eine spätere Merge-Freigabe.

## Späteres Migrations-Follow-up

Replace eager QVariant-list handoff with production-scale Qt model / lazy data
adapter before full Screen-1 migration.

Die 50k-Probe beweist die QML-Delegate-Virtualisierung, materialisiert den
Python-Datenbestand für den Proof-Harness jedoch weiterhin vollständig. Das ist
kein Blocker für diese Shell-Baseline und keine Migrationsentscheidung.
