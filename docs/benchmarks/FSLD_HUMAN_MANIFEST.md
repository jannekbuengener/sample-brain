# FSLD Human Manifest (Slice 1 von #595)

`data/benchmarks/fsld_human_manifest_v1.json` ist eine kleine, abgeleitete
öffentliche Benchmark-Grundlage. Sie ist eine balancierte, stratifizierte
Teilmenge und ausdrücklich keine populationsrepräsentative FSLD-Auswertung.
Sie enthält keine Predictions, keine künstliche Confidence und keine Audio- oder
lokalen Metadaten.

## Provenance und Reproduktion

Die alleinige Quelle für Ground Truth ist [FSLD Zenodo Record 3967852,
Version 1.0](https://zenodo.org/records/3967852), Datei `annotations.zip`.
Der Builder akzeptiert ausschließlich deren erwartete MD5
`3920ee437802cf047a990b2968fa066c` und liest nur JSON-Dateien unter
`annotations/<annotator-id>/sound-<freesound-id>.json`. Automatische FSL10K-
Analyseflächen werden nicht eingelesen und nie als Ground Truth behandelt.

Mit einer lokal außerhalb des Repositories gespeicherten Datei:

```powershell
python -m src.fsld_human_manifest build `
  --annotations-zip <path-to-annotations.zip> `
  --manifest data/benchmarks/fsld_human_manifest_v1.json `
  --sha256 data/benchmarks/fsld_human_manifest_v1.sha256

python -m src.fsld_human_manifest verify `
  --annotations-zip <path-to-annotations.zip> `
  --manifest data/benchmarks/fsld_human_manifest_v1.json `
  --sha256 data/benchmarks/fsld_human_manifest_v1.sha256
```

`verify` prüft sowohl die kanonischen Manifest-Bytes als auch den SHA256-
Sidecar. Die Serialisierung ist UTF-8 mit sortierten Keys, kompakten
Separatoren, `allow_nan=False` und genau einem finalen Newline.

Der eingecheckte Build hat SHA256
`8e443d603b712aeb15b66b87a6e87921b53a3cdf9c94834fb80a4d2b262a7571`.
Der Smoke zählte 1.472 ursprünglich mehrfach annotierte und 1.464 ursprünglich
einzeln annotierte Human-Samples; davon waren 1.196 `no_key`- und 1.256
`tonal`-Kandidaten benchmark-eligible. Die eingefrorene Teilmenge enthält 100
`CALIBRATION`- und 400 `TEST`-Records.

## Ground-Truth-Contract

- `annotation_tier=ma` behält nur ursprünglich mehrfach annotierte Sounds mit
  mindestens zwei gültigen nicht-discardeten Human-Annotationen. Ein
  degradierter MA-Fall wird nie zu `sa`.
- `annotation_tier=sa` enthält ursprünglich einzeln annotierte, gültige
  Human-Annotationen. MA und SA bleiben für Folgeauswertungen getrennt.
- `ground_truth.tonality` ist `no_key` nur bei `none/none`; ein sonstiger
  annotierter Inhalt — auch mit `unknown` — ist `tonal`. Gegensätzliche
  MA-Tonalität wird ausgeschlossen.
- Die feldweisen Evidence-Werte sind `known`, `unknown`, `conflicting`,
  `missing` und `not_applicable`. Bei tonalen Samples mit unbekanntem oder
  konflikthaftem Key bleiben Tonality-Evidence und das Sample erhalten.
- MA-BPM erfordert übereinstimmende positive numerische BPM bei allen gültigen
  Annotationen mit `defined_tempo=true`. SA darf die einzelne entsprechend
  bestätigte BPM als sekundäre Human-Evidence enthalten.

## Auswahl und Splits

Der Builder wählt bis zu 250 `no_key`- und bis zu 250 `tonal`-Records anhand
von Tier, Tonalität sowie Root-/Mode-Evidence. Weitere Gleichstände werden mit
einem namensraumgebundenen SHA256-Ranking aufgelöst. Bei 500 Records sind es
100 `CALIBRATION` und 400 `TEST`; andernfalls ist das Ziel
`floor(N * 0.20 + 0.5)`, mindestens eins bei `N > 1`.

Ohne Metadaten ist der Split exakt. Optional kann ein lokal bereitgestelltes
FSLD-`metadata.json` die uploader-basierte Gruppierung nur aktivieren, wenn
für jeden gewählten Record ein nichtleerer `username` vorliegt. Bei einer
partiellen Abdeckung bleibt der komplette Split ungruppiert, damit keine
unbekannte Uploader-Gruppe über Splits verteilt wird. Bei aktiver Gruppierung
haben vollständige Gruppen Vorrang; der Builder verwendet ausschließlich
`fsld-uploader-sha256:<digest>` und serialisiert weder Uploadernamen noch
lokale Pfade. Da `metadata.json` nur im 8,8-GB-FSL10K-Archiv liegt, nutzt das
versionierte Manifest keine Gruppierung (`source_group_id: null`).

## Slice-Grenze

Dies ist nur die Datenbasis für #595: kein Analyzer-Bake-off, kein #598-
Abstention-/No-Key-Gate und keine Änderung an Production-Key-, Mode- oder BPM-
Semantik.
