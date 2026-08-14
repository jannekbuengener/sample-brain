# Section Candidate Generation v1

**Issue:** [#266](https://github.com/jannekbuengener/sample-brain/issues/266)
**Parent:** [#230](https://github.com/jannekbuengener/sample-brain/issues/230)
**Depends on:** [#250](https://github.com/jannekbuengener/sample-brain/issues/250) (Asset Manifest), [#240](https://github.com/jannekbuengener/sample-brain/issues/240) (Arrangement Classifier), [#241](https://github.com/jannekbuengener/sample-brain/issues/241) (Confidence & Override), [#234](https://github.com/jannekbuengener/sample-brain/issues/234) (Canonical Timebase), [#265](https://github.com/jannekbuengener/sample-brain/issues/265) (StructureV1)
**Schema/Interface version:** `1.0.0`
**Document type:** `sample_brain.section_candidates`
**Implementation:** `src/section_candidates.py`

---

## 1. Praktische Bedeutung

Loop-Kandidaten (#251) entstehen aus echten Downbeats in fester 4/8/16-Bar-Form.
Für Intro, Drop, Breakdown oder Outro gibt es keinen solchen Generator. Diese
Slice erzeugt **pro Arrangement-Section genau einen reproduzierbaren
Asset-Kandidaten** aus der bereits vorhandenen Arrangement Map: den
neutralen Section-Grenzen von StructureV1 (#265) plus den Rollen und
manuellen Korrekturen der Arrangement Map (#240 / #241).

Die Slice bewertet nicht, rendert nicht und klassifiziert Rollen neu. Sie
übersetzt bestehende Ergebnisse 1:1 in das Asset-Manifest-`section`-Format
aus #250.

---

## 2. Input aus der Arrangement Map

`generate_section_candidates(structure_result, arrangement_result, *, source, track_ref)`
konsumiert:

- `structure_result` (`StructureV1Result`, #265): liefert die **autoritativen
  Sample-Grenzen** (`start_sample`, `end_sample_exclusive`) und Bar-Spannen
  je Section. Jede Section trägt eine `id`.
- `arrangement_result` (`ArrangementResult`, #240/#241): liefert Rolle,
  Rollenstatus, automatisches Ergebnis, manuellen Override und den
  effective-Wert je Section (`section_id` schließt mit `StructureSection.id`).
- `source` (`SectionSourceIdentity`): portable Quell-Identität
  (`master` / `stem` / `producer_group`), analog zu `loop_candidates`.
- `track_ref`: portable Track-Referenz für das Asset-Manifest.

`arrangement_result` ist optional. Ohne ihn werden Sections mit Rolle
`unknown` und `automatic`-Herkunft erzeugt — eine fehlende optionale Rolle
verhindert keinen Kandidaten.

---

## 3. Automatic / Manual / Effective

Der Generator übernimmt das #241-Effective-Value-Modell unverändert:

| Feld im Kandidaten | Bedeutung |
|--------------------|-----------|
| `arrangement_role` | **Effective** Rolle (Override gewinnt vor automatisch) |
| `arrangement_role_source` | `automatic` oder `manual` — woher der effective Wert kam |
| `automatic_role` | originales automatisches Ergebnis, **immer erhalten** |
| `arrangement_role_status` | Status des automatischen Ergebnisses (#241) |

Ein manueller Override überschreibt den effective Wert, **zerstört aber nicht**
das automatische Ergebnis: `automatic_role` und `arrangement_role_status`
bleiben erhalten, sodass später nachvollziehbar ist, was automatisch und was
manuell war.

---

## 4. Sample-Grenzen

Alle Grenzen sind ganzzahlige Sample-Indizes auf der #234-Timebase,
halboffenes Intervall `[start_sample, end_sample_exclusive)`. Sekunden sind
abgeleitet, nie autoritativ. Ungültige Ranges (`end <= start`) werden
fail-closed mit `ValueError` behandelt.

---

## 5. Section-ID und Rolle

`section_ref` ist die `id` der neutralen StructureV1-Section. Die Rolle wird
vom effective Wert übernommen. Die Reihenfolge der Kandidaten entspricht der
Reihenfolge der Arrangement-Sections und ist deterministisch.

---

## 6. Unknown-Verhalten

`unknown` ist ein erstklassiges, normales Ergebnis — kein Fehler, kein
Platzhalter. Sections mit Rolle `unknown` erzeugen einen voll gültigen
Kandidaten. Es wird bewusst **keine** Confidence erfunden.

---

## 7. Boundary- / Rollen-Trennung

Boundary-Evidenz und Rollen-Evidenz bleiben strikt getrennte Ebenen (#241):

- `boundary.source` = `arrangement_map`, `boundary.kind` = `neutral_section`.
- `boundary.status` folgt dem StructureV1-Status (`ok` / `partial` /
  `no_result` / `failed`).
- `boundary.quality` (0–1, relativ) kommt aus dem entsprechenden
  StructureV1-Boundary-Score an der Startkante der Section; für die erste
  Section (Start bei Sample 0) entfällt die Qualität.
- Eine unsichere Boundary impliziert **nicht** eine unsichere Rolle und
  umgekehrt. Die Felder liegen in unterschiedlichen Blöcken des Manifests.

---

## 8. Asset-Manifest-Mapping (#250)

Jeder Kandidat liefert via `as_manifest_dict()` die `#250`-konformen Blöcke:

| Manifest-Feld | Quelle |
|---------------|--------|
| `asset_kind` | `"section"` |
| `track_ref` / `asset_id` | Eingabe bzw. `asset_section_{section_id}` |
| `range.start_sample` / `end_sample_exclusive` / `n_samples` | StructureV1 |
| `section.section_ref` | StructureV1 `id` |
| `section.arrangement_role` | effective Rolle |
| `section.arrangement_role_status` | automatischer Status (#241) |
| `section.arrangement_role_ref` | `arrangement_classifier/{section_id}` |
| `section.bars` | StructureV1 Bar-Spanne (optional) |
| `boundary` | arrangement_map / neutral_section |
| `candidate.status` | `"candidate"` |
| `rendering.status` | `"not_rendered"` |
| `analysis.status` | `"not_run"` (`ANALYSIS_NOT_REQUESTED`) |

Eine vollständige Asset-Manifest-Assemblierung (audio-`hash`, `timebase`,
zentrales `provenance`-Register, `quality`) erfolgt in einem höheren
Pipeline-Schritt und liegt außerhalb dieser Slice.

---

## 9. Keine Wiederholungs- / Seam-Pflicht

Sections unterliegen **keiner** Loop-Regel:

- keine feste 4/8/16-Bar-Länge erforderlich,
- keine Wiederholungsprüfung,
- keine Seam-Kontinuitätsprüfung,
- Section-Kandidaten werden nicht nach Loop-Regeln verworfen.

Die Bewertung erfolgt erst separat in #267.

---

## 10. Abgrenzung zu #267 und #253

- **#267 (Scoring):** bewertet die hier erzeugten Kandidaten musikalisch, ohne
  Wiederholungs- oder Seam-Strafe. Diese Slice enthält **kein** Scoring.
- **#253 (Rendering):** rendert deterministisch auf ganzzahligen Sample-
  grenzen. Diese Slice setzt `rendering.status = "not_rendered"` und rendert
  nicht.

---

## 11. Akzeptanzmapping (#266)

| #266-Kriterium | Abgedeckt durch |
|----------------|-----------------|
| jede Kandidatengrenze besitzt Startsample und exklusiven Endsample | `range` aus StructureV1; fail-closed bei ungültig |
| automatische und manuell korrigierte Grenzen unterscheidbar | `arrangement_role_source` |
| Section-Rolle und Boundary-Herkunft erhalten | `arrangement_role`, `boundary` |
| keine Wiederholungs- oder Seam-Pflicht für Sections | §9; Tests `test_no_repetition_or_seam_check` |

---

## 12. Nicht-Ziele (v1)

- keine Rollenklassifikation (gehört zu #240)
- keine Boundary-Erkennung (gehört zu #265)
- keine Audioanalyse, kein Rendering (gehört zu #253)
- kein Scoring (gehört zu #267)
- keine erfundene Confidence oder generic `confidence`
- keine feste Taktlänge, keine Wiederholungs- oder Seam-Regeln
