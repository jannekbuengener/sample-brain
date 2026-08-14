# Asset Rendering v1 — Deterministic Loop & Section Renderer

**Issue:** [#253](https://github.com/jannekbuengener/sample-brain/issues/253)
**Parent:** [#230](https://github.com/jannekbuengener/sample-brain/issues/230)
**Depends on:** [#250](https://github.com/jannekbuengener/sample-brain/issues/250) (Asset Manifest), [#252](https://github.com/jannekbuengener/sample-brain/issues/252) (Loop Scoring), [#266](https://github.com/jannekbuengener/sample-brain/issues/266) (Section Candidates), [#267](https://github.com/jannekbuengener/sample-brain/issues/267) (Section Scoring)
**Implementing module:** `src/asset_renderer.py`
**Status on tracker:** delivered, see PR.

This document describes the deterministic, lossless rendering of already-selected
loop and section candidates to WAV assets. It is the implementation contract
that closes #253 and fills the `rendering` block of the Asset Manifest v1 (#250 §11).

---

## 1. Practical meaning

Kandidaten aus #251/#252 (Loops) und #266/#267 (Sections) tragen bereits
autoritative ganzzahlige Sample-Grenzen. Dieser Renderer schneidet exakt diesen
Bereich aus dem Quell-Audio heraus und schreibt ihn verlustfrei als WAV. Er
trifft **keine** Qualitätsentscheidung, **keine** Score-Logik und **keine**
Grenz-Neuberechnung.

Ziel: ein Loop- oder Section-Asset, das bitgenau dem gewählten Quellbereich
entspricht, mit vollständiger Herkunfts- und Rendering-Provenance.

---

## 2. Authoritative sample boundaries

Die einzige Render-Wahrheit sind integer Sample-Indizes auf der #234-Timebase:

```text
source_audio[start_sample : end_sample_exclusive]
```

* `start_sample` ist inklusiv, `end_sample_exclusive` exklusiv (Half-open
  Interval `[start, end)`, wiederverwendet aus `canon_audio.AudioRange`).
* Sekunden sind abgeleitet und **niemals** autoritativ.
* Keine BPM×Sekunden-Näherung.
* Keine automatische Grenzverschiebung oder Neuberechnung aus dem Kandidaten.
* Ungültige Grenzen führen zu `status = "failed"` mit statusbasiertem
  `error.code` (fail-closed), nicht zu einem stillschweigend korrigierten Schnitt.

---

## 3. Loop versus Section

Loop und Section werden über **einen kleinen gemeinsamen Rendervertrag**
(`RenderRequest`) akzeptiert. Beide teilen `asset_kind`, `asset_id`,
`source_kind`, `start_sample`, `end_sample_exclusive` und den Quellpfad.

* `render_request_from_loop_candidate(candidate, path, *, renderable, asset_id)`
* `render_request_from_section_candidate(candidate, path, *, renderable)`

`asset_kind` (`loop` / `section`) bleibt in Manifest und Dateiname erkennbar und
wird **nie** allein aus dem Dateinamen abgeleitet. Beide Asset-Arten werden
getrennt behandelt und separat benannt.

---

## 4. master / stem / producer_group

Die `source_kind` des Kandidaten wird 1:1 übernommen und in der Manifest-`source`
sowie in der Rendering-Provenance festgehalten:

* `master` → Original-Track-Working-Audio.
* `stem` → technischer Stem (andere Audio-Datei, gleiche Sample-Indizes).
* `producer_group` → Producer-Gruppe (eigene Audio-Datei, gleiche Sample-Indizes).

Der Renderer misst die Sample-Indizes **immer** gegen die tatsächliche Audio, die
im `source.audio`-Block des Manifests beschrieben wird. Master, Stem und
Producer-Group sind niemals gleichgesetzt.

---

## 5. Verlustfreie WAV-Ausgabe

* Standardmäßig wird der **Subtype der Quelle erhalten** (`subtype=None` →
  Quell-Subtype). Damit ist der Round-Trip verlustfrei (PCM_16→int16,
  PCM_24/32→int32, FLOAT→float32, DOUBLE→float64).
* Kanalzahl wird erhalten (`always_2d=True`); keine automatische Mono-Konvertierung.
* Keine automatische Resampling-Stufe; die Sample-Rate der Quelle wird übernommen.
* Wird technisch ein Subtype-Wert verlangt, wird die bestehende Source-/Repo-
  Konvention bevorzugt und die Entscheidung explizit in `configuration`/
  Provenance dokumentiert.

---

## 6. Kein Crossfade / Fade im Default

* `fade_in_samples = 0`, `fade_out_samples = 0` im Default.
* Der Standardpfad verändert **keine** Ränder: bei deaktivierten Fades ist die
  Ausgabe bitgenau die Quell-Scheibe.
* **Crossfade ist in v1 aus Scope.** Es ist niemals eine automatische
  Seam-Reparatur; schlechte Seams werden bereits in #252/#267 verworfen.
* Fades sind nur als opt-in `RenderConfig`-Parameter vorhanden (lineare Rampen),
  werden vollständig in `configuration` dokumentiert und ändern den Default
  nicht.

---

## 7. Kein Stretch / Pitch / Normalize

* **Kein** Time-Stretch, **kein** Pitch-Shift. Die Frame-Zahl der Ausgabe ist
  exakt `end_sample_exclusive - start_sample`.
* **Keine** versteckte Lautheitsnormalisierung (`normalize=False` im Default).
* **Keine** Dither-/DSP-Stufe als versteckter Default.

---

## 8. Portable Dateinamen

* `file_name = f"{asset_kind}_{asset_id}.wav"` (deterministisch, kollisionsfrei
  über den `asset_id`).
* `file_ref = "assets/{file_name}"` (portable relative Referenz, keine absoluten
  Pfade, keine Laufwerksbuchstaben, keine `..`-Segmente).
* Der `asset_id` (bzw. `track_ref`) bleibt die Wahrheit; der Dateiname ist nur
  ein portables Transport-/Benutzermerkmal, niemals die alleinige Identität.

---

## 9. Rendering-Provenance

Jeder Renderlauf erzeugt das Manifest-`rendering`-Block (#250 §11):

```json
{
  "status": "rendered",
  "renderer": {
    "component": "asset_renderer",
    "sample_brain_version": "0.1.0",
    "configuration": {
      "format": "WAV",
      "subtype": "pcm_16",
      "subtype_preserved": true,
      "fade_in_samples": 0,
      "fade_out_samples": 0,
      "normalize": false,
      "crossfade_samples": 0,
      "time_stretch": false,
      "pitch_shift": false
    },
    "source_ref": "comp_asset_renderer"
  },
  "output": {
    "file_ref": "assets/loop_4bar_100_300.wav",
    "file_name": "loop_4bar_100_300.wav",
    "hash": { "algorithm": "sha1", "value": "..." },
    "audio_properties": { "sample_rate_hz": 44100, "channels": 2, "n_samples": 200 },
    "format": "wav/pcm_16"
  }
}
```

* `hash.value` wird aus der **tatsächlich geschriebenen** Datei gebildet.
* `audio_properties` werden aus der geschriebenen Datei gelesen.
* `source_ref` zeigt in `provenance.components["comp_asset_renderer"]`.
* Keine privaten absoluten Pfade, keine Secrets im serialisierbaren Resultat.

---

## 10. Fehler- / not-rendered-Verhalten

| Zustand | Verhalten |
|---------|-----------|
| `renderable=False` | `status = "not_rendered"`, kein File geschrieben, `error.code = NOT_RENDERABLE`. Hart verworfene Kandidaten werden nicht heimlich gerendert. |
| `start_sample < 0` | `status = "failed"`, `error.code = INVALID_START_SAMPLE`. |
| `end <= start` | `status = "failed"`, `error.code = INVALID_RANGE`. |
| Bereich übersteht Quell-Länge | `status = "failed"`, `error.code = RANGE_BEYOND_SOURCE`. |
| Quelldatei fehlt | `status = "failed"`, `error.code = SOURCE_NOT_FOUND`. |

Nicht gerenderte Assets bleiben ein valides Manifest (`rendering.status =
not_rendered`). Fehler erzeugen nachvollziehbare status-/error-Evidence.

---

## 11. Original bleibt unverändert

Der Renderer schreibt **immer** in einen neuen Pfad
(`<output_dir>/assets/<file_name>`). Die Original-Quelldatei wird nie
überschrieben, nie mutiert und nie gelöscht. Die Hash-Identität der Quelle vor
und nach dem Rendern ist identisch.

---

## 12. Abgrenzung zu #254

Dieser Renderer **analysiert** gerenderte Assets nicht. Re-Analyse (Metadaten,
Features) ist alleinige Aufgabe von #254 (`analysis.status = not_run` im
Manifest). #253 liefert ausschließlich den Schnitt + die Render-Provenance.

---

## 13. Nicht-Ziele (v1)

* Keine neue Kandidatengenerierung oder Score-Logik.
* Keine Stem-Separation oder Producer-Gruppen-Erzeugung.
* Kein Crossfade, kein Time-Stretch, kein Pitch-Shift, keine versteckte
  Normalisierung.
* Keine Performance-Pack-Aggregation (#231 / #257).
* Keine Re-Analyse (#254).
* Keine Dependency- oder Workflow-Änderungen.

---

## 14. Tests & Evidence

* `tests/test_asset_renderer.py` (test-first) deckt exakte Slice-Grenzen,
  Frame-Zahl, Determinismus, Original-Unverändertheit, Default-ohne-DSP,
  Master/Stem/Producer-Group-Traceability, Asset-Kind-Trennung, portable
  Dateinamen, Output-Hash, Provenance, fail-closed Grenzen und
  `renderable=False`-Verhalten ab.
* Synthetische Runtime-Smokes nutzen ausschließlich erzeugtes Testaudio in
  temporären Verzeichnissen außerhalb des Repos; es werden keine privaten
  Samples committet.
