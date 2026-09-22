# FSLD Current-Analyzer Evaluation (Slice 2 von #595)

`python -m src.fsld_current_analyzer_eval` misst den bestehenden
Sample-Brain-Analyzer gegen genau einen Split des eingefrorenen FSLD-Human-
Manifests. Der Runner ist DB-frei und ruft ausschließlich
`src.analyze.extract_features(..., bpm_normalization="none")` auf. Er ändert
weder Key-, Mode- noch Tempo-Semantik.

## Aufruf

FSL10K-Audio bleibt lokal außerhalb des Repositories und wird ausschließlich
über die öffentliche, deterministische Struktur aufgelöst:

```text
<audio-root>/<public_sample_id>.wav
```

Beispiel mit einem externen Output-Artefakt:

```powershell
python -m src.fsld_current_analyzer_eval `
  --audio-root <FSL10K-audio-root> `
  --split TEST `
  --output <external-directory>/fsld-current-analyzer-test.json
```

`--manifest` und `--sha256` überschreiben die versionierten Standardpfade nur
für Tests oder gezielte Reproduktion. Vor jeder Auswertung verifiziert der
Runner die kanonischen Manifest-Bytes und den SHA256-Sidecar. Ein Output-Pfad
innerhalb des Repositories wird abgewiesen.

## Ergebniscontract

Jeder Record des gewählten Splits erscheint genau einmal in numerischer
`public_sample_id`-Reihenfolge. Fehlende Audiodateien und Analysefehler bleiben
als statusbehaftete Records erhalten. Der Output enthält keine lokalen Pfade,
Dateinamen, Audioinhalte, Dateihashes, Host- oder Hardwaredaten.

Pro Record enthält der Report die unveränderte Manifest-Ground-Truth,
Analyzer-/Runtime-Provenance, Predictions, native Key-/Mode-Evidence,
Laufzeit sowie Status und Exclusion Reason. `predicted_key_root` wird aus dem
bereits gelieferten `Features.key` über den bestehenden Key-Signature-Contract
abgeleitet; `predicted_key_mode` kommt direkt aus `Features.key_mode`.

Die Metriken bleiben strikt in `ma` und `sa` getrennt:

- Key Root: nur tonale Records mit `root_evidence=known`.
- Full Key: zusätzlich `mode_evidence=known`.
- Tempo: nur `bpm_evidence=known`, inklusive absolutem/relativem BPM-Fehler
  sowie der bestehenden Relationen `correct`, `half`, `double`, `ambiguous`
  und `outlier`.

Das erzeugte JSON ist ein lokales, ungetracktes Runtime-Artefakt und darf nicht
in das Repository übernommen werden.

## Grenze dieses Slices

Dieser Runner liefert ausschließlich die Baseline des aktuellen Analyzers.
Er führt keinen Engine-Bake-off aus (#596), sucht keine Thresholds und führt
kein Tonal-/No-Key-Abstention-Gate ein (#598). Ohne lokal verfügbar gemachte
öffentliche FSLD-Audios wird keine Dataset-Baseline behauptet; der Zustand ist
als `PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY` zu dokumentieren.
