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

Die beiden #538-Captures laufen nur aus einer `VALID` dedizierten Runtime:

```powershell
python -m src.cli workbench --qml-proof-spike --visual-acceptance `
  --runtime-root <runtime-root> --evidence-dir <lokaler-output-ordner>
```

Die Capture-Dateien und das Manifest bleiben außerhalb des Repositories. Ein
technischer Lauf ersetzt keine Owner-Visual-Acceptance.
