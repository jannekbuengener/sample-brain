# Realtime Workbench Scope

Status: canonical product boundary for issue #318 / child #319.

## In einfachen Worten

Sample Brain bleibt lokal und private Audio-Dateien bleiben auf dem Rechner. Zusätzlich zur bestehenden Offline-Analyse darf die lokale Workbench jetzt einen kleinen nativen Echtzeit-Audiopfad bekommen.

Dieser neue Pfad ist ausdrücklich **keine vollständige DAW** und **kein FL-Studio-/VST-Plugin-Scope**. Er erweitert die bestehende Workbench um gezielte Producer-Funktionen, ohne Scan, Analyse, Track Map, Performance Packs oder Stem-Flows zu ersetzen.

## Erlaubter Produktumfang

Der Realtime-Workbench-Cluster darf folgende Funktionen umsetzen:

- gemeinsames `TEMPO`
- `SYNC` an/aus
- lokales Sample-Playback und Mixing
- grid-/phasengebundene Wiedergabe, wenn der vorhandene BeatGrid verlässlich genug ist
- Playback-Rate-Modus, bei dem Pitch dem Tempo folgt
- Key-Lock/Time-Stretch über einen nativen DSP-Pfad
- direkte lokale Aufnahme
- automatische lokale `Recordings`-Playlist
- nicht-destruktives, grid-gebundenes Waveform-Schneiden
- genau einen manuellen Part-Typ `HÄFTIG`
- `HÄFTIG` als exakt 16 Takte ab dem frühesten gültigen Taktanfang im zurückliegenden 16-Takt-Fenster
- Grid-/Waveform-Darstellung
- einen kleinen nativen Audio-Core für zeitkritisches Playback, Scheduling und Recording

## Technische Grenze

- Python/Tkinter bleibt für UI, Analyse, Steuerung und nicht-zeitkritische Aufgaben zuständig.
- Der harte Live-Audiopfad darf nativ umgesetzt werden; Python ist nicht die autoritative Echtzeit-Audio-Clock.
- Autoritative Session-Zeit wird in ganzzahligen Audioframes geführt.
- Source-Zeit/BeatGrid aus der Analyse und Session-/Playback-Zeit bleiben getrennte Begriffe.
- Original-Audio wird nie destruktiv verändert. Schnitte, Tempo-Anpassung und Regionen sind Session-/Workbench-Zustand oder neu gerenderte lokale Artefakte.
- Offline/local-first bedeutet weiterhin: keine Cloud-Abhängigkeit. Es bedeutet **nicht**, dass lokale Echtzeit-Wiedergabe verboten ist.

## Nicht-Ziele dieses Clusters

- keine vollständige DAW
- kein VST-/VST3-/FL-Studio-Plugin als Bestandteil von #318
- kein FLP-Parsing oder Zugriff auf undokumentierte FL-Studio-Interna
- keine Cloud-Audioverarbeitung
- kein schweres Scanning, DB-Zugriff, ML-Inferenz oder Track-Analyse im Echtzeit-Audiopfad
- kein ASIO-Pflichtziel für v1
- keine destruktive Änderung von Original-Samples oder Original-Tracks

Ein möglicher Plugin-Pfad bleibt ein separates, späteres Produkt-/Integrationsvorhaben und darf die Umsetzung von #318 nicht blockieren.

## Datenschutz und Repository-Safety

- Private Samples, Tracks und Recordings werden niemals committed.
- Generierte Recordings, Renderings, Caches, Device-Dumps und Runtime-Artefakte bleiben lokal und untracked.
- Keine privaten absoluten Pfade, Gerätekennungen, Tokens oder lokale Audioinhalte in Issues, PRs, Logs oder Test-Evidence.
- Tests verwenden synthetische Fixtures oder ausdrücklich freigegebenes Audio.

## Bestehende Funktionen bleiben gültig

Der neue Workbench-Scope ersetzt nichts von Folgendem:

- Library Scan / Analyse / Autotype / Search
- FL Browser Export als bestehender Integrationspfad
- Track Map / BeatGrid / Structure / Arrangement
- Track Deconstruction und Performance Packs
- optionale Stem-Separation

Die neue Audio-Workbench baut auf diesen Informationen auf, ohne deren Verträge umzudeuten.

## Folge-Verträge

- #320 definiert Session Transport, Tempo Map und Grid.
- #321 baut den nativen miniaudio/WASAPI-Core als PoC.
- #322–#327 hängen TEMPO/SYNC, Playback-Modi, Recording, Editing und `HÄFTIG` an denselben Zeitvertrag.
- #328 validiert Langzeit-SYNC, Latenz, Recording und Windows-Geräte.
