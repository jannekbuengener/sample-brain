# Performance Pack Resume & Cache Reuse v1

Issue: **#262** · Parent: **#231** · Depends on: **#259**
Grenze zu: **#237** (Globaler Cache, OFFEN/getrennt) · **#261** (Stem-Separation, NOT_CONFIGURED)
· **#264** (End-to-End-Privatpilot)

Dieses Dokument spezifiziert die idempotente, unterbrechungssichere und
cache-bewusste Wiederaufnahme der Track-Deconstruction (`sample-brain deconstruct
<track>`). Es definiert eine **pack-lokale** Resume-/Cache-Schicht, die
sicherstellt, dass:

- wiederholte Läufe mit gleichen Inputs gültige Ergebnisse wiederverwenden,
- unterbrochene Läufe an der Stelle weitermachen, an der sie aufhörten,
- bei Quell-/Konfigurations-/Ausgabeänderung nur die betroffenen Schritte
  neu berechnet werden,
- und der Output-Integritätszustand vor jeder Wiederverwendung validiert wird.

Die Spezifikation ist eine Erweiterung des Orchestrators (#259), nicht dessen
Ersatz. Sie fügt Zustandsverwaltung, Fingerprinting und Cache-Validierung hinzu,
ändert aber den Step-Kontrollfluss und die Statussemantik von #259 nicht.

## Scope-Besitz (#262)

- pack-lokaler Resume-Zustand (`deconstruct_resume.json`) und Lebenszyklus
- Fingerprint-/Cache-Key-Berechnung pro Step
- Wiederverwendbarkeitsprüfung (Source-/Config-/Upstream-/Output-Integrität)
- atomares Schreiben von Resume- und Step-State
- Arrangement-Resume: Rekonstruktion der Laufzeitobjekte für den `assets`-Step
  ohne erneute Arrangement-Berechnung
- CLI-Flag `--no-resume` (Resume standardmäßig EIN, wenn kompatibler State existiert)
- Evidenz `computed` vs `reused` in `deconstruct_run.json` (Minor-Evolution auf 1.1.0)

## Grenzen (Hard Boundaries)

- **Kein globaler Cache.** Resume-State ist strikt pack-lokal unter
  `<pack-root>/deconstruct_resume.json`. Kein zentraler/repo-übergreifender
  Cache, keine SQLite-Cache-Tabelle. (#237 bleibt OFFEN und getrennt.)
- **Keine Stem-Separation.** `stems`-Step bleibt optionaler Hook für
  *vorhandene* Stem-Ergebnisse; keine Separation (#261).
- **Keine privaten Audio-/Testdaten.** Validierung ausschließlich mit
  synthetischen WAVs und `tmp_path`; keine echten Tracks committet.
- **Keine neuen Dependencies.** Nur stdlib (`hashlib`, `json`, `os`,
  `pathlib`, ggf. `tempfile`).
- **Keine absoluten Pfade** in serialisiertem Resume-State oder
  `deconstruct_run.json`. Alle `output_refs`/`canonical_audio_path` sind
  portable, pack-relative Pfade ohne Laufwerk/Root/`..`.

## Resume-State-Datei

Pfad: `<pack-root>/deconstruct_resume.json`.

```json
{
  "document_type": "sample_brain.deconstruct_resume",
  "schema_version": "1.0.0",
  "source": {
    "id": "<track-identity>",
    "content_hash_sha256": "<sha256 hex>",
    "pack_root_portable": "."
  },
  "contract_versions": {
    "track_map": 1,
    "arrangement": 1,
    "assets": 1,
    "stems": 1
  },
  "steps": {
    "track_map":   { "status": "ok",     "cache_key": "<sha256 hex>", "output_inventory": [ {"ref": "analysis/track_map.json", "sha1": "<hex>"} ] },
    "arrangement": { "status": "ok",     "cache_key": "<sha256 hex>", "output_inventory": [ {"ref": "analysis/working_audio.wav", "sha1": "<hex>"}, {"ref": "analysis/arrangement_map.json", "sha1": "<hex>"} ], "snapshot": { "...": "portable arrangement runtime objects" } },
    "assets":      { "status": "partial", "cache_key": "<sha256 hex>", "output_inventory": [ {"ref": "loops/loop_x.json", "sha1": "<hex>"}, {"ref": "loops/assets/loop_x.wav", "sha1": "<hex>"} ] },
    "stems":       { "status": "not_run", "cache_key": null, "output_inventory": [] }
  }
}
```

Der Resume-State ist ein **regenerierbarer Index**: Er speichert keine
Ergebnisse selbst, sondern nur Metadaten (Status, Cache-Keys, Output-Inventar
mit SHA-1) plus ein portables Arrangement-Snapshot. Die eigentlichen
Step-Ergebnisse liegen in den #258-Pack-Bereichen.

Der State kann jederzeit aus den Pack-Inhalten neu erzeugt werden, sofern die
Outputs vorhanden sind; er ist kein Source-of-Truth für die Analyse, sondern
eine Validierungs- und Wiederverwendungshilfe.

## Fingerprint-Regeln (Cache-Key)

Jeder Step-Cache-Key ist ein **SHA-256** über ein kanonisches JSON:

- `json.dumps(payload, sort_keys=True, separators=(",", ":"))`
- Keine Wall-Clock-Timestamps, keine absoluten Pfade, keine Zufalls-IDs, keine
  Prozess-IDs im Payload.
- Deterministisch bei gleichen Inputs + gleichen Adapterantworten.

Der Payload eines Steps enthält:

- `source_content_hash` (SHA-256 des Quell-Tracks) — gilt für alle Steps
  (Upstream-Invarianz).
- `step_id` und `contract_version`.
- relevante Konfiguration (nur die Felder, die den Step-Output beeinflussen,
  z. B. `--bpm-normalization`, `--beat-backend`).
- relevante **Upstream-Cache-Keys**: `arrangement` hängt vom `track_map`-
  Cache-Key ab; `assets` vom `arrangement`-Cache-Key; `stems` vom `assets`-
  Cache-Key. (Kaskadierende Invalidierung über Cache-Key-Änderung.)

Wenn sich der `source_content_hash` gegenüber dem prior State ändert, wird der
**gesamte** prior State verworfen (voller Recompute). Gleiche Quelle + gleiche
relevanten Configs + gleiche Upstream-Cache-Keys ⇒ identischer Cache-Key ⇒
Wiederverwendung (sofern Output-Integrität OK).

## Step-Abhängigkeiten

```
track_map → arrangement → assets → stems
```

Ein Step ist nur dann wiederverwendbar (`reused`), wenn:

1. sein gespeicherter `status` in `{ok, partial}` liegt (`failed`, `not_run`,
   `no_result` werden NICHT wiederverwendet),
2. sein berechneter Cache-Key mit dem gespeicherten übereinstimmt,
3. sein `output_inventory` physisch vorhanden ist und die SHA-1-Hashes
   übereinstimmen,
4. bei `arrangement`: zusätzlich `analysis/working_audio.wav` existiert und
   SHA-1 passt (siehe Arrangement-Resume).

Wenn ein Step neu berechnet werden muss, werden alle nachgelagerten Steps
ebenfalls neu berechnet (da deren Upstream-Cache-Key sich ändert).

## Output-Integritäts-Gate

Vor jeder Wiederverwendung werden alle `output_inventory`-Einträge geprüft:

- Datei existiert unter `pack_root / ref`.
- `file_hash(ref)` (SHA-1, siehe `src/utils.py`) == gespeicherter `sha1`.

Fehlschlag einer Integritätsprüfung ⇒ Step gilt als Cache-MISS ⇒ Recompute.
Dies fängt gelöschte/überschriebene/ korrupte Outputs ab, ohne auf absolute
Pfade oder externe Metadaten angewiesen zu sein.

## Invalidierungsregeln

- `source_content_hash` geändert ⇒ voller Recompute (State neu aufgebaut).
- relevante Step-Config geändert ⇒ nur dieser Step + Downstream recompute.
- `contract_version` dieses Steps erhöht ⇒ nur dieser Step + Downstream
  recompute (gezielte Invalidierung).
- Upstream-Cache-Key geändert ⇒ dieser Step + Downstream recompute.
- Output fehlt/SHA-1-Mismatch ⇒ betroffener Step + Downstream recompute.
- `--no-resume` ⇒ kompletter Recompute, prior State wird ignoriert (nicht
  zwingend gelöscht; neuer State überschreibt).

## Arrangement-Resume (kritisch)

Der `assets`-Step benötigt Laufzeitobjekte aus `arrangement`, die sonst durch
`build_arrangement_map` erzeugt werden. Für Resume müssen diese aus portablem
JSON rekonstruiert werden — ohne erneute Arrangement-Berechnung.

### Portable Referenz für Canonical-Audio

`canonical_audio_path` wird NICHT absolut serialisiert. Im Resume-State wird
nur `"analysis/working_audio.wav"` als portabler, pack-relativer Ref gespeichert.
Zugehörigkeit: Output des `arrangement`-Steps (in dessen `output_inventory`).

Vor der Arrangement-Wiederverwendung:

1. Existenzprüfung `pack_root / "analysis/working_audio.wav"`.
2. SHA-1-Abgleich mit dem `output_inventory`-Eintrag.
3. Bei Rehydrierung: `canonical_audio_path = pack_root / "analysis/working_audio.wav"`
   als Laufzeitpfad.

Fehlendes/Mismatch-WAV ⇒ Arrangement-Cache-MISS ⇒ Recompute (inkl. neuem
Canonical-WAV-Schreiben). Keine absoluten Pfade im Resume-Snapshot oder in
`deconstruct_run.json`.

### Snapshot-Inhalt (portsbewusst)

Der `arrangement`-Step-Snapshot serialisiert explizit (via `_snapshot_*`-
Helper in `src/deconstruct_resume.py`) und rekonstruiert explizit (via
`_resume_*`-Helper), importerend die eingefrorenen Dataclasses:

- `BeatGridResult` (`src.beat_grid`): `.downbeats` (`BeatGridSeries`:
  `status`, `sample_indices`, `reason_code`).
- `StructureV1Result` (`src.structure_v1`): `.boundaries`, `.sections`,
  `.bar_features`.
- `ArrangementResult` (`src.arrangement_classifier`): `.sections`
  (`SectionClassification`: `section_id`, `effective_value.role/.source`,
  `automatic_result.role/.status`).
- `AudioTimebase` (`src.canon_audio`): `sample_rate`, `n_samples`.
- `canonical_audio_path` = `"analysis/working_audio.wav"` (portabel).

Serialisierung vermeidet `pickle`/`marshal`; reine JSON-Konvertierung mit
expliziter `tuples↔lists`-Behandlung und Field-Name-Matching. Die
(De-)Serialisierungslogik liegt isoliert in `src/deconstruct_resume.py`;
`beat_grid.py`/`structure_v1.py`/`arrangement_classifier.py` werden nach
Möglichkeit nicht modifiziert.

## Crash / Resume nach Unterbrechung

- State wird **nach jedem** Step atomar geschrieben (Temp-Datei + `os.replace`).
  Ein unterbrochener Lauf hinterlässt daher einen State bis einschließlich des
  letzten erfolgreich beendeten Steps.
- Beim nächsten `deconstruct`-Aufruf (Resume EIN): bereits `ok`/`partial`
  Steps mit gültigem Cache-Key + Output-Integrität werden wiederverwendet;
  der erste betroffene Step wird ab dort neu berechnet.
- Resume ist sicher gegen teilweise geschriebene State-Dateien (atomares
  Schreiben + Validierung beim Lesen: bei Parse-/Schema-Fehler ⇒ voller
  Recompute).

## Computed vs Reused — Evidenz

`deconstruct_run.json` erfährt eine additive MINOR-Evolution auf `1.1.0`:

- Jeder `StepResult` erhält `execution: "computed" | "reused"` und `cache_key`.
- Run-Ebene: `reused_steps: [...]`, `computed_steps: [...]` (portabel,
  keine absoluten Pfade, keine Wall-Clock-Timestamps).

So ist nachvollziehbar, welche Schritte echte Arbeit geleistet und welche
sicher wiederverwendet wurden — ohne den Run-Status (#259) zu verändern.

## Legacy-Packs (kein Resume-State)

Fehlt `deconstruct_resume.json`, verhält sich der Lauf wie bisher
(Volle Berechnung der angeforderten Steps; kein Wiederverwendungsversuch).
Der State wird nach dem Lauf erzeugt. Keine Migration erforderlich.

## Cleanup-Regel

Wird ein Step neu berechnet, werden **nur** dessen prior inventarisierte
Dateien best-effort gelöscht (aus `output_inventory`). Niemals andere
Pack-Inhalte berühren.

## CLI

```
python -m src.cli deconstruct <track> --pack-root <dir> \
    [--bpm-normalization none|...] [--beat-backend auto|librosa|beat_this] \
    [--skip-arrangement] [--skip-assets] [--skip-stems] \
    [--no-resume] \
    [--write-evidence/--no-write-evidence] [--json]
```

`--no-resume` deaktiviert die Wiederverwendung für diesen Lauf (voller
Recompute). Standard: Resume EIN, wenn ein kompatibler State existiert.
Exit-Codes unverändert zu #259 (`0` bei `complete`/`partial`, `2` bei `failed`).

## Nicht-Ziele (Non-Goals)

#237 Globaler Cache · #261 Stem-Separation · #260 vollständiges Pack-Assembly
(nur Resume-Metadaten, kein finales `manifest.json`) · #263 Re-Import · #264
End-to-End-Privatpilot · CLAP · neue Modelle · DB-Migration · Dependency-
Änderungen · private Audio-Dateien · GUI/Workbench.

## Issue #249 — Stems-Step Resume

- Der `stems`-Step führt jetzt ein echtes `output_inventory`: jedes Stem-Manifest
  JSON (`stems/<stem_id>.json`) **und** die referenzierte WAV (`stems/<kind>.wav`).
- Pack-lokales Resume rechnet den `stems`-Step neu, sobald eine inventarisierte
  Datei fehlt oder verändert ist (analog zu `assets`/`arrangement`).
- Der `stems`-Step bleibt optional (`required=False`); ein `not_run`-Eintrag ist
  weiterhin resumable (leeres Inventory ist nie wiederverwendbar).
