# [STEMS] Spike python-audio-separator integration

Dieses Dokument hält die Ergebnisse des Integrations-Spikes für die technische 4-Stem-Separation via `python-audio-separator` in Sample Brain (#245) fest.

---

## 1. Trennung von Wrapper und Modell

Wir betrachten die Wrapper-Schicht (`python-audio-separator`) und die eigentlichen Trennungsmodelle (`htdemucs`/`htdemucs_ft`) als getrennte Komponenten:
- **Wrapper-Schicht:** Verantwortlich für die Prozesssteuerung, das Herunterladen von Modellgewichten, das Ensembling und die Übergabe an das Inferenz-Backend (ONNX Runtime, PyTorch). Sie ist unter der permissiven MIT-Lizenz veröffentlicht.
- **Trennungsmodell:** Die neuronale Netzarchitektur und deren vortrainierte Gewichte. Der Demucs-Code ist MIT-lizenziert, aber die vortrainierten Gewichte sind rechtlich oft restriktiver (z. B. CC-BY-NC-4.0 für nicht-kommerzielle Nutzung) oder lizenstechnisch ungeklärt. Daher trennen wir die Code-Lizenz streng von der Weight-Lizenz.

---

## 2. Installationsweg und Core-Isolation

Um den Core von Sample Brain schlank und frei von schweren Machine-Learning-Abhängigkeiten (wie `torch` und `onnxruntime`) zu halten, wurde ein optionaler Installationsweg etabliert:

- **Eigener Extra-Pfad:** In `pyproject.toml` wurde das Extra `[project.optional-dependencies].stems` definiert.
- **Gepinnte Version:** `audio-separator[cpu]==0.44.5` ist als reproduzierbare Version festgelegt.
- **Installationsbefehl:**
  ```bash
  pip install -e .[stems]
  ```
- **Zusätzlicher Sync:** `requirements-stems.txt` dokumentiert denselben Vertrag.
- **Core-Isolation:** Kein Modul unter `src/` importiert jemals direkt `audio_separator` oder `torch`. Dadurch bleibt Sample Brain für Standardanalysen (BPM, Key, Loudness, Brightness) ohne ML-Abhängigkeiten voll funktionsfähig.

---

## 3. Prozessisolierung (Subprocess Boundary)

Um importseitige Belastungen und potenzielle CUDA-/Speicher-Konflikte im Hauptprozess vollständig auszuschließen, kommuniziert Sample Brain mit dem Stem-Separator ausschließlich über eine Prozessgrenze (**Subprocess-Modus**):

- **Werkzeug:** `tools/stem_separator_spike.py` dient als isolierter Wrapper, der als eigenständiger Prozess via `subprocess` aufgerufen wird.
- **Vorteile:**
  - Abstürze (z. B. Out-of-Memory oder ONNX Runtime Segfaults) reißen nicht den Haupt-Thread von Sample Brain mit.
  - Timeouts und Exit-Codes werden kontrolliert abgefangen.
  - Speicher wird nach Beendigung des Subprozesses sofort wieder vom Betriebssystem freigegeben.

---

## 4. CLI- und Python-API-Probe

Der Spike-Wrapper bietet zwei Betriebsweisen:
1. **CLI-Aufruf:**
   ```bash
   python tools/stem_separator_spike.py list-models
   python tools/stem_separator_spike.py separate --input <WAV> --model htdemucs.yaml --output-dir <DIR>
   ```
2. **Python-API:** Die Klasse `StemSeparatorProcessWrapper` kapselt den Subprocess-Aufruf und gibt strukturierte Python-Dicts zurück, die dem Stem-Manifest-Vertrag entsprechen.

---

## 5. Modellauflistung und Baseline-Kandidaten

Über die Modellliste von `audio-separator` wurden die beiden Baseline-Kandidaten dynamisch verifiziert:
- **`htdemucs.yaml`** (Friendly Name: `Demucs v4: htdemucs`)
- **`htdemucs_ft.yaml`** (Friendly Name: `Demucs v4: htdemucs_ft`)

Beide Kandidaten können über ihren Modell-Identifier explizit adressiert und heruntergeladen werden. Es wird keine implizite Default-Modellwahl im Wrapper getroffen; der Modellname muss immer explizit übergeben werden.

---

## 6. Mapping nach Stem Manifest v1

Jeder erzeugte Stem (`drums`, `bass`, `vocals`, `other`) wird auf genau ein Stem Manifest gemäß `#244` (`sample_brain.stem_manifest` v1.0.0) abgebildet:
- **`track_ref`:** Eindeutiger Content-Hash des Originaltracks (SHA-1), kein Dateiname-Fallback.
- **`source.origin_sample`:** Ist immer `0`, da die Separation am Dateianfang ansetzt.
- **`output.file_ref`:** Portabler, relativer Pfad zum erzeugten Stem-WAV innerhalb des Ausgabeordners (keine Laufwerksbuchstaben, absoluten Pfade oder `..` Traversierungen).
- **Audio-Properties & Hashes:** Werden live aus den tatsächlichen Ausgabedateien via `soundfile` und `hashlib` berechnet.

---

## 7. Windows- und CPU-Smoke-Ergebnis

- **OS:** Windows 11
- **Python-Version:** 3.12+
- **Wrapper-Version:** `audio-separator 0.44.5`
- **Ausführungsmodus:** CPU-Inferenz via PyTorch und ONNX Runtime.
- **Verhalten unter Windows:** Demucs-Modelle laufen stabil auf CPU. DirectML wird für Demucs von Upstream nicht unterstützt (da die LSTM-Operatoren in `torch-directml` fehlen), weshalb für diesen 4-Stem-Pfad die CPU-Ausführung als Standard gilt.
- **Laufzeit:** CPU-Smoke-Test trennt kurze synthetische Signale im Sekundenbereich.

---

## 8. Lizenz- und Checkpoint-Evidence

- **Wrapper Code-Lizenz:** MIT
- **Demucs Code-Lizenz:** MIT
- **Weight-Lizenzen (Status #247):**
  - Für die Gewichte von `htdemucs.yaml` und `htdemucs_ft.yaml` ist die kommerzielle Nutzung nicht freigegeben. Der autoritative Status aus #247 lautet: **`RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED`** (interne Policy-Klassifikation `VERIFIED_NONCOMMERCIAL`).
  - `CC-BY-NC` wird **nicht** behauptet; die Hugging-Face-`license: mit`-Metadaten werden niemals still in eine kommerzielle Gewichtlizenz umgedeutet.
  - Der Spike stampft **keine** erfundene Weight-Hash mehr. Die tatsächliche kryptographische Weight-Identity muss zur Laufzeit explizit geliefert werden (`--weight-hash`); ohne sie wird die Separation nicht ausgeführt und keine Provenance erfunden.
  - Deklarierte Checkpoint-Identifier (keine vollständigen lokalen Weight-Hashes):
    - `htdemucs.yaml` → `955717e8`
    - `htdemucs_ft.yaml` → `f7e0c4bc,d12395a8,92cfc3b6,04573f0d`

---

## 9. Bekannte Grenzen und Übergabe an #268

- **LSTM-Limits:** DirectML kann für Demucs mangels Operatoren-Support nicht genutzt werden. CUDA-Beschleunigung bleibt CUDA-kompatiblen Grafikkarten vorbehalten.
- **Qualitätsvergleich:** Es wurde kein musikalischer Hörvergleich vorgenommen, dies ist dedizierter Scope von **#246**.
- **Produktives Wiring:** Es wurde keine automatische Separation in `src/deconstruct.py` eingehängt; der Spike verbleibt als isolierte technische Integrationsstudie. Die Übergabe für Benchmark-Hörtests erfolgt an **#246** bzw. die produktive Einbindung an **#249**.
