# Session Transport, Tempo Map & Grid v1

Status: canonical contract for #320 (parent #318). Depends on #319.

## 1. Zweck

Dieser Vertrag definiert die gemeinsame musikalische Zeitbasis der lokalen Audio-Workbench. Er ist die Grundlage für späteres `TEMPO`, `SYNC`, Recording, grid-gebundenes Schneiden, `HÄFTIG` und Live-DSP.

Der bestehende Analyse-`BeatGrid` bleibt Source-Evidence. Er wird **nicht** zur Session-Clock umgedeutet.

## 2. Autoritative Zeit

- Die autoritative Session-Zeit ist `session_frame`: ein signed-int64 Audioframe auf einer festen Session-Samplerate.
- `engine_frame` und `session_frame` sind getrennte Werte.
  - `engine_frame`: fortlaufende Frameposition der Audio-Engine / des Callback-Stroms.
  - `session_frame`: musikalische Position im Session-Timeline-Raum; darf durch Stop/Seek unabhängig von `engine_frame` stehen oder springen.
- Float-Sekunden und GUI-Timer sind niemals autoritative Zeitquellen.
- Unterstützte Session-Sampleraten sind nicht auf 44,1/48 kHz begrenzt; diese beiden Raten sind Pflicht-Testfälle.

Signed-int64 liefert bei 48 kHz mehr als fünf Millionen Jahre positiven Framebereich. Implementierungen müssen Werte außerhalb `[-2^63, 2^63-1]` ablehnen statt still zu überlaufen.

## 3. Exakte musikalische Position

Musikalische Position wird intern als exakte rationale Viertelnotenposition (`quarter_note`) dargestellt.

- BPM bedeutet Viertelnoten pro Minute.
- Dezimale BPM-Werte wie `127.5` werden als exakter Dezimalbruch behandelt, nicht als binärer Float-Fehler.
- Frame → Quarter-Note innerhalb eines Tempo-Segments:

```text
quarter_note = segment.start_quarter
             + (frame - segment.start_frame) * bpm / (60 * sample_rate)
```

- Quarter-Note → Frame wird direkt vom Segmentanker berechnet und genau einmal auf den nächsten ganzzahligen Frame gerundet.
- Es ist verboten, Beat- oder Bar-Grenzen rekursiv aus der jeweils vorherigen gerundeten Grenze abzuleiten.

Dadurch entsteht kein kumulativer Rundungsdrift über lange Sessions.

## 4. TimeSignature

`TimeSignature` ist explizit modelliert.

v1-Regeln:

- Default: `4/4`.
- `numerator > 0`.
- `denominator` ist eine positive Zweierpotenz.
- Der v1-`TempoMap` nutzt eine gemeinsame Time Signature für die gesamte Map. Time-Signature-Wechsel sind späterer Scope.

Abgeleitete Werte:

```text
quarter_notes_per_beat = 4 / denominator
quarter_notes_per_bar  = numerator * quarter_notes_per_beat
```

Bar und Beat sind intern 0-basiert.

## 5. TempoSegment und TempoMap

Ein `TempoSegment` enthält mindestens:

- `start_frame`
- `start_quarter`
- `bpm`

`TempoMap` enthält:

- feste `sample_rate`
- explizite `TimeSignature`
- chronologisch sortierte Tempo-Segmente

Regeln:

- Segment 0 startet bei `session_frame = 0`, `quarter_note = 0`.
- Neue Segmente dürfen bestehende frühere Segmente nicht rückwirkend verschieben.
- Ein Tempo-Wechsel an einer musikalischen Grid-Grenze nutzt die **exakte** Quarter-Note-Grenze als Segmentanker; der zugehörige Frame wird direkt aus dem vorherigen Segment berechnet.
- Ein sofortiger Tempo-Wechsel im Stop-Zustand darf an einem beliebigen aktuellen `session_frame` beginnen; dessen `start_quarter` wird aus der bisherigen Map an genau diesem Frame abgeleitet.
- Änderungen vor dem jüngsten Segmentanker sind in v1 nicht erlaubt.

## 6. SessionTransport

`SessionTransport` hält mindestens:

- `engine_frame`
- `session_frame`
- `playing`
- `TempoMap`

Verhalten:

- `play()` startet Session-Fortschritt.
- `stop()` hält `session_frame`; `engine_frame` bleibt ein eigener Engine-Zähler.
- `seek(frame)` verändert nur `session_frame`.
- `advance(engine_frames)` erhöht `engine_frame` immer; `session_frame` nur bei laufendem Transport.
- `set_tempo(bpm)`:
  - **gestoppt:** wirksam sofort am aktuellen `session_frame`.
  - **laufend:** standardmäßig wirksam am Start des **nächsten Taktes**, selbst wenn der aktuelle Frame bereits exakt auf einem Taktanfang liegt.

`set_tempo` liefert den effektiven Session-Frame zurück, damit UI und Audio-Core denselben Umschaltpunkt verwenden können.

## 7. Frame ↔ Bar/Beat

Die zentrale API muss deterministisch bereitstellen:

- `frame_to_quarter_note(frame)`
- `quarter_note_to_frame(quarter_note)`
- `quarter_note_to_bar_beat(quarter_note)`
- `bar_beat_to_quarter_note(position)`
- `frame_to_bar_beat(frame)`
- `bar_beat_to_frame(position)`
- `next_bar_start_frame(frame)`

`MusicalPosition` besteht aus:

- `bar`
- `beat`
- `beat_fraction` als rationaler Wert `[0, 1)`

## 8. Event-Scheduling innerhalb eines Buffers

Events werden in absoluten `session_frame`-Werten geplant.

Für einen Buffer `[buffer_start_frame, buffer_start_frame + frame_count)` liefert der Scheduler nur Events in diesem half-open Bereich und deren Offset:

```text
offset = event_frame - buffer_start_frame
```

Die absolute Eventposition darf **nicht** von der Audio-Buffergröße abhängen. Ein Lauf mit Buffergrößen 64, 128, 257 oder 512 muss dieselben absoluten Eventframes ergeben.

## 9. Source-Grid vs Session-Grid

Bestehende Analyse-Zeit bleibt getrennt:

- `BeatGrid.sample_indices` / Track-Map-Zeit beziehen sich auf das Source-/Analyse-Audio.
- `session_frame` bezieht sich auf die laufende Workbench-Session.
- Spätere `SYNC`-Logik darf Source-Beat/Downbeat-Evidence verwenden, muss sie aber explizit auf Session-Zeit abbilden.
- Keine API dieses v1-Vertrags importiert oder überschreibt `BeatGrid`-Daten.

## 10. Pflicht-Tests

Der Vertrag ist nur erfüllt, wenn automatisiert geprüft wird:

- 44,1 kHz und 48 kHz
- 120 / 127 / 127,5 / 132 BPM
- direkte Bar-Grenzen bis mindestens 1000 Takte ohne kumulative Rundungsdrift
- Tempo 128 → 132 → 140, ohne Veränderung bereits vergangener Gridpositionen
- laufender Tempo-Wechsel ab nächstem Takt; gestoppter Wechsel sofort
- getrennte `engine_frame`/`session_frame`-Semantik
- identische absolute Eventframes bei simulierten Buffergrößen 64/128/257/512
- signed-int64-Grenzprüfung

## 11. Nicht-Ziele

- kein echtes Audio-I/O
- keine miniaudio-/WASAPI-Einbindung
- kein Signalsmith Stretch
- keine Workbench-UI
- keine Source-Audio-Resampling- oder BeatGrid-Neuberechnung
- keine Time-Signature-Wechsel innerhalb einer Session in v1
