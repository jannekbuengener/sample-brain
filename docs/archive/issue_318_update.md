## Ziel
Sample Brain von der reinen Offline-Sample-Verwaltung um eine lokale, grid-gebundene Audio-Workbench erweitern, ohne die bestehende Analyse- und Asset-Kette zu brechen.

Die Nutzeroberfläche bleibt bewusst minimal:

- `TEMPO: 132 BPM`
- `SYNC`

Produktregel:

- `SYNC` aktiv: alle geeigneten Samples folgen dem gemeinsamen TEMPO und bleiben – soweit der vorhandene BeatGrid es zuverlässig erlaubt – beat-/taktphasig im gemeinsamen Grid.
- `SYNC` inaktiv: jedes Sample läuft mit seinem Original-BPM.
- Originaldateien bleiben unverändert.
- Das Grid ist die gemeinsame musikalische Zeitbasis für Playback, Recording, Schneiden und `HÄFTIG`.

## Zielbild

```text
Python / Tkinter / Analyse / DB / Workbench
                ↓
         schmale native API
                ↓
     samplebrain_audio C++ Core
                ↓
 Transport / Tempo Map / Grid / Scheduler
                ↓
 miniaudio + WASAPI
        ↙                 ↘
Rate/Resampling      Signalsmith Stretch
Pitch folgt Tempo    Key bleibt erhalten
                ↓
              Mixer
                ↓
       Playback + Recording
```

## Festgelegte technische Richtung

- Autoritative Session-Zeit: ganzzahlige Audioframes.
- Engine-/Playback-Zeit und Session-/Musikzeit werden getrennt modelliert.
- Musikalisches Grid wird deterministisch aus Tempo-Segmenten abgeleitet; keine rekursive Rundung von Beat zu Beat.
- TEMPO-Änderungen erzeugen neue Tempo-Segmente; laufend standardmäßig ab nächstem Takt, gestoppt sofort.
- `SYNC` bedeutet intern Tempo-Anpassung plus Grid-/Phasen-Verankerung, wenn ein verlässlicher Beat-/Downbeat-Grid vorliegt.
- Live-Audiopfad nativ; Python bleibt UI/Analyse/Steuerung und darf nicht der harte Echtzeit-Audiopfad sein.
- Audio-Engine-Favorit: native miniaudio-C-API mit kleinem C++-Core.
- Windows-v1: WASAPI Shared; Exclusive später optional; ASIO darf v1 nicht blockieren.
- Key-Lock-Favorit: Signalsmith Stretch nativ.
- Analyse-Canon und Originaldateien bleiben erhalten; Live-Session darf eine eigene Engine-Samplerate nutzen.

## Children

### Fundament
- [x] #319 — Produkt-/Canon-Grenze für Realtime Workbench aktualisieren
- [x] #320 — Sample-genauen Session Transport, Tempo Map und Grid definieren
- [x] #321 — Nativen miniaudio/WASAPI Audio-Core als PoC bauen

### Workbench + SYNC
- [ ] #322 — `TEMPO` / `SYNC` / gemeinsames Grid in der Workbench anbinden
- [ ] #323 — SYNC-Modus: Playback-Rate ändern, Pitch folgt Tempo
- [ ] #324 — SYNC-Key-Lock mit Signalsmith Stretch

### Recording + Bearbeitung
- [ ] #325 — Direkte Aufnahme + automatische `Recordings`-Playlist
- [ ] #326 — Nicht-destruktives, grid-gebundenes Waveform-Schneiden
- [ ] #327 — 16-Takt-`HÄFTIG` per Hotkey auf Source-Grid

### Abschluss
- [ ] #328 — Langzeit-SYNC, Latenz, Recording und Windows-Geräte robust validieren

## Arbeitsstand / Handoff
Stand 2026-08-16:

- #319: **DONE_MERGED_CLOSED** — Produktgrenze für lokale Realtime-Workbench ist Canon.
- #320: **DONE_MERGED_CLOSED** — sample-genauer SessionTransport / TempoMap / Grid ist auf `main`.
- #321: **DONE_MERGED_CLOSED** — native miniaudio/WASAPI Audio-Core PoC merged (PR #332, commit 225b42e).
- #322: **PREPARED** — UI↔Session↔Native-Snapshot-Vertrag und bestehende Workbench-Andockpunkte stehen fest.
- #323: **PREPARED** — Rate-Formel, Sync-Fähigkeitsstufen, One-Shot-/BPM-Fehlerfälle und Pflicht-Tests stehen fest.
- #324: **PREPARED** — Signalsmith-Adapter, DSP-Latenzvertrag und ehrlicher Fallback stehen fest.
- #325: **PREPARED** — Capture/Worker-Grenze und Wiederverwendung der bestehenden `Recordings`-Playlist-Infrastruktur stehen fest.
- #326: **PREPARED** — Source-Frame-Regionen und Wiederverwendung des bestehenden `[start,end)`-Renderers stehen fest.
- #327: **PREPARED** — exakter 16-Bar-HÄFTIG-Algorithmus inkl. Bar-40-Fälle steht fest.
- #328: **PREPARED** — reproduzierbares Validation-Schema und Verdict-Regeln stehen fest.

### Was jetzt wirklich blockiert
Der nächste echte Produktfortschritt ist #322: Workbench-Anbindung des nativen Core.

## Bau-Reihenfolge

```text
#319
 ↓
#320
 ↓
#321  ✓ DONE
 ↓
#322
 ├──→ #323 ──→ #324
 ├──→ #325 ──→ #326
 └──→ #327
              ↓
             #328
```

#323/#324 und #325/#326 können nach dem gemeinsamen Fundament weitgehend unabhängig voneinander bearbeitet werden. #327 hängt primär am stabilen Grid/Workbench-Vertrag und kann ebenfalls parallel zu Recording/DSP vorbereitet werden.

## Produktfunktionen dieses Clusters

- gemeinsames `TEMPO`
- `SYNC` an/aus
- zwei Live-Tempo/Pitch-Modi
- direkte Aufnahme
- automatische Ablage in `Recordings`
- nicht-destruktives Schneiden in der Waveform
- genau ein manueller Part-Typ: `HÄFTIG`
- `HÄFTIG`: frühester gültiger Taktanfang innerhalb des letzten 16-Takt-Fensters; Region exakt 16 Takte
- Grid-/Waveform-Darstellung
- Langzeit-Sync, Recording- und Windows-Audio-Validierung

## Nicht-Ziele

- vollständige DAW
- VST-/FL-Studio-Plugin
- Cloud-Audioverarbeitung
- ASIO als Pflicht für v1
- Major→Minor als Release-Blocker; bleibt experimenteller späterer Follow-up
- Commit privater Sample- oder Recording-Dateien

## Definition of Done

- Alle Children sind abgeschlossen oder explizit als später/optional dokumentiert.
- Workbench zeigt exakt `TEMPO: <wert> BPM` und `SYNC`.
- Bei `SYNC` aktiv laufen mehrere Samples reproduzierbar auf dem gemeinsamen Tempo/Grid.
- Bei `SYNC` inaktiv laufen sie mit Original-BPM.
- Recording, `Recordings`, Schneiden und `HÄFTIG` funktionieren auf demselben Zeit-/Grid-Vertrag.
- Key-Lock funktioniert über den nativen DSP-Pfad.
- Langzeittest zeigt keinen kumulativen relativen Grid-Drift.
- Kein privates Audio oder Runtime-Artefakt gelangt ins Repo.