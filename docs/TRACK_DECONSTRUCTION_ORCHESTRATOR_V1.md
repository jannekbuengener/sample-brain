# Track Deconstruction Orchestrator v1

Issue: **#259** · Parent: **#231** · Depends on: **#257**, **#258**
Resume/Cache: **#262** (siehe [`PERFORMANCE_PACK_RESUME_V1.md`](PERFORMANCE_PACK_RESUME_V1.md))

Dieses Dokument beschreibt den headless Track-Deconstruction-Einstieg
(`sample-brain deconstruct <track>`). Er koordiniert vorhandene Sample-Brain-
Bausteine in definierter Reihenfolge, gibt Teilergebnisse statusbasiert weiter
und bereitet das Performance-Pack-Layout (#258) vor – ohne die eigentliche
Pack-Integration (#260) oder Stem-Integration (#261) vorwegzunehmen.

## Zweck

Ein einzelner Befehl startet eine Track-Deconstruction, ohne dass ein Nutzer
Track Map, Arrangement, Loop-/Section-Kandidaten, Bewertung, Rendering und
leichte Asset-Reanalyse einzeln von Hand anstoßen muss.

Der Orchestrator ist **reiner Kontrollfluss**. Er implementiert keine
BPM-/Arrangement-/Candidate-/Scoring-/Render-/Analyse-Logik neu, sondern
ruft die bestehenden Fachfunktionen auf.

## Scope-Besitz (#259)

- Steuerungslogik und Reihenfolge der Deconstruction-Schritte
- einheitlicher Step-/Run-Status
- Weitergabe von Teilergebnissen zwischen Schritten
- Fehlerbehandlung (statusbasiert, keine Fake-Erfolge)
- Behandlung optionaler Schritte
- headless Einstieg + CLI-Wiring für `deconstruct`
- Pack-Root/Layout gemäß #258 vorbereiten

## Grenze zu #260 / #261

- **#260** verbindet Track Map, Arrangement und Asset-Manifests zum finalen
  `performance_pack_manifest` (vollständige Parent-/Child-/Asset-Referenzen).
- **#261** bindet echte Stem-Ausgaben in das Performance Pack ein.
- **#259 erzeugt bewusst KEIN finales `manifest.json` im #257-Sinne.** Es
  schreibt ein klar gekennzeichnetes Orchestrator-Run-Evidence
  (`deconstruct_run.json`) als Zwischenresultat, keine integrierte
  Performance-Pack-Definition. Step-Outputs werden an den vorgesehenen
  #258-Stellen erzeugt/weitergereicht.

## Einschränkungen

- kein DB-Zwang
- kein Netzwerk, keine Cloud
- keine neuen Modelle, keine neuen Dependencies
- Originaltrack wird niemals verändert (Canonical-WAV wird in den Pack-Root
  geschrieben, nicht über den Originalpfad)

## Schrittordnung

| id | required | Zweck | Bausteine |
|----|----------|-------|-----------|
| `track_map` | **ja** | Track analysieren, Track Map erzeugen | `analyze_context_file` |
| `arrangement` | nein | Structure + Arrangement koordinieren | `StructureV1Analyzer`, `SectionSignalsAssembler`, `build_arrangement_map` |
| `assets` | nein | Loop-/Section-Kandidaten, Bewertung, Rendering, leichte Reanalyse | `generate_loop_candidates`, `generate_section_candidates`, `score_loop_candidate`, `score_section_candidate`, `render_asset`, `attach_rendered_asset_analysis` |
| `stems` | nein | nur optionaler Hook für vorhandene Stem-Ergebnisse; keine Separation | – |

## Step-Status

Werte: `ok`, `partial`, `not_run`, `no_result`, `failed`.

Jeder Step-Result enthält:

- `step_id`
- `required`
- `status`
- `output_refs` – portable, pack-relative Pfade (keine absoluten Pfade)
- `reason_code` – bei `not_run` / `no_result`
- `error` – bei `failed` (`{code, message}`)
- `adapter` / `provenance` – tatsächlich verwendeter Adapter + Versionen
- `track_analysis_cache_status` – nur für den `track_map`-Step: `hit` | `miss` | `disabled` (siehe unten)

### Track-Analyse-Cache-Evidence (#237)

Der `track_map`-Step nutzt den globalen, user-lokalen Track-Analyse-Cache
(`docs/TRACK_ANALYSIS_CACHE_V1.md`). Wenn der Step wegen #262 tatsächlich
gerechnet wird (`execution = computed`), führt seine Evidence zusätzlich:

```text
track_analysis_cache_status: hit | miss | disabled
```

Dies ist **additive** Evidence, getrennt von #262 `execution = reused | computed`.
Ein gültiger Zustand ist z. B.:

```text
execution = computed
track_analysis_cache_status = hit
```

Der Cache-Status beschreibt nur, *wie die Analysewerte diesmal beschafft wurden*;
er wird **nicht** in die portable Track Map geschrieben. Es wird niemals ein
Cache-Pfad serialisiert — nur der Statuswert.

### Verhalten

- **required track_map failure** (`failed` oder `no_result`): Gesamtstatus
  `failed`, keine folgenden Schritte werden ausgeführt, keine falsche
  Erfolgsmeldung.
- **optional step failure** (`partial`/`no_result`/`not_run`/`failed`): der
  Run bleibt verwertbar; Gesamtstatus `partial`, nicht `failed`.
- **kein Fake-Success**: bei `failed` wird niemals `complete` gemeldet.

### Gesamtstatus-Regel (deterministisch)

1. Ein required Step mit `failed`/`no_result` → `failed`.
2. Sonst ein Step mit `failed` (optionaler harter Fehler) → `partial`.
3. Sonst ein Step mit `partial`/`no_result` → `partial`.
4. Sonst → `complete`.

## Pack-Layout-Vorbereitung (#258)

Der Orchestrator legt die vorgesehenen Bereiche an und schreibt Step-Outputs
dorthin:

- `analysis/track_map.json` (required)
- `analysis/arrangement_map.json` (optional)
- `loops/*.json` + gerenderte Loops (optional)
- `sections/*.json` + gerenderte Sections (optional)
- `stems/` (optional, nur bei vorhandenem Stem-Adapter)
- `deconstruct_run.json` – Orchestrator-Run-Evidence (Zwischenresultat)

Alle `output_refs` sind portable, pack-relative Pfade ohne Laufwerk/Root/`..`.

## Run-Evidence-Format

`document_type: sample_brain.deconstruct_run`, `schema_version: 1.0.0`.
Felder: `status`, `track` (Quell-Track-Identität), `pack_root` (portabel),
`steps` (in Ausführungsreihenfolge), `reason_codes`, portable `output_refs`.
Keine absoluten Pfade, keine Wall-Clock-Timestamps → deterministisch bei
gleichen Inputs + gleichen Adapterantworten.

### Resume-Evidenz (additive Minor-Evolution auf 1.1.0, via #262)

Jeder `StepResult` erhält zusätzlich `execution: "computed" | "reused"` und
`cache_key`. Run-Ebene fügt `reused_steps` / `computed_steps` (portabel) hinzu.
Der Run-Status (#259) bleibt unverändert. Detailregeln:
[`PERFORMANCE_PACK_RESUME_V1.md`](PERFORMANCE_PACK_RESUME_V1.md).

## Adapter-Injektion

Jeder Step wird über ein Adapter-Callable ausgeführt:
`adapter(ctx) -> (StepResult, payload)`. `ctx` trägt Track-Pfad, Pack-Root,
Konfiguration und die `artifacts` (Zwischenergebnisse vorheriger Steps).
Standardmäßig laufen die echten Produktions-Adapter; Tests injizieren
Mock-Adapter, um Delegation und Statusverhalten deterministisch zu prüfen,
ohne die schwere Echt-Audio-Pipeline auszuführen.

## CLI

```
python -m src.cli deconstruct <track> --pack-root <dir> \
    [--bpm-normalization none|...] [--beat-backend auto|librosa|beat_this] \
    [--skip-arrangement] [--skip-assets] [--skip-stems] \
    [--track-cache-dir <dir>] [--no-track-cache] \
    [--write-evidence/--no-write-evidence] [--json]
```

`--no-resume` deaktiviert die Wiederverwendung für diesen Lauf (voller
Recompute; Resume ist sonst standardmäßig EIN bei kompatiblem State, siehe
[`PERFORMANCE_PACK_RESUME_V1.md`](PERFORMANCE_PACK_RESUME_V1.md)).

Exit-Codes: `0` bei `complete`/`partial`, `2` bei `failed`.

## Nicht-Ziele (Non-Goals)

#260 vollständiges Pack-Assembly · #261 Stem-Pack-Integration · #263 Re-Import
· #264 End-to-End-Privatpilot · #268 Producer Groups · CLAP · neue Modelle ·
DB-Migration · Dependency-Änderungen · private Audio-Dateien · GUI/Workbench.

(Resume/Cache ist Gegenstand von **#262**, siehe
[`PERFORMANCE_PACK_RESUME_V1.md`](PERFORMANCE_PACK_RESUME_V1.md) — kein
Non-Goal mehr.)

## Issue #249 — Optionaler Stem-Step (Deconstruct-Integration)

- `stems` ist ein **optionaler** Step (`required=False`). Er ist ein No-Op,
  sofern nicht `--stems` übergeben wird; sonst meldet er `not_run` mit
  `STEMS_NOT_REQUESTED`.
- Opt-in verlangt wahrheitsgemäße Provenance: `--stem-model`
  (z. B. `htdemucs.yaml`, `htdemucs_ft.yaml`) und `--stem-weight-hash`
  (tatsächliche kryptografische Weight-Identity). Der Weight-Hash-Algorithmus
  wird gegen das Modell validiert (`sha256` für `htdemucs`, `sha256-set-v1` für
  `htdemucs_ft`); ein Missmatch wird mit `WEIGHT_IDENTITY_UNAVAILABLE`
  abgewiesen, es läuft keine Separation.
- Separation nutzt das **kanonische Working-Audio** (`analysis/working_audio.wav`)
  als exakten Separation-Input; `track_ref` ist der Track-Map-Wert
  `source.original.hash.value` (kein Pfad/UUID-Fallback).
- Separation läuft in isoliertem Subprocess via `tools/stem_separator_spike`
  (`audio_separator`/`torch` werden nie von Core importiert). Outputs landen in
  `<pack_root>/stems/` (WAVs + signierte Stem-Manifests, #244).
- Stem-Separation ist **research-only**: Demucs-Weights sind
  `RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED`. Es gibt **keinen Production-
  Default** (`production_default: NO_GO`); der Step ist experimentell.
- Failure Isolation: ein Stem-Fehler (`not_run`/`failed`/`partial`) bricht die
  gesamte Track Deconstruction nie ab. Der Run-Status wird `partial`, nicht
  `failed`.
- Cache-Ebenen: globaler #248 Stem-Cache (`separate_with_cache`) und pack-lokales
  #262 Resume. Bei einem #248 `hit` werden die Outputs nach
  `<pack_root>/stems/` kopiert, ohne Separation erneut auszuführen.
