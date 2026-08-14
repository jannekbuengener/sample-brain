# Section Scoring v1

**Issue:** [#267](https://github.com/jannekbuengener/sample-brain/issues/267)
**Parent:** [#230](https://github.com/jannekbuengener/sample-brain/issues/230)
**Depends on:** [#250](https://github.com/jannekbuengener/sample-brain/issues/250) (Asset Manifest), [#266](https://github.com/jannekbuengener/sample-brain/issues/266) (Section Candidates), [#240](https://github.com/jannekbuengener/sample-brain/issues/240) (Arrangement Classifier), [#241](https://github.com/jannekbuengener/sample-brain/issues/241) (Confidence & Override), [#265](https://github.com/jannekbuengener/sample-brain/issues/265) (StructureV1)
**Schema/Interface version:** `1.0.0`
**Document type:** `sample_brain.section_scoring`
**Implementation:** `src/section_scoring.py`

---

## 1. Praktische Bedeutung

Diese Slice bewertet die in #266 erzeugten Section-Kandidaten nach ihrer
**musikalischen Nutzbarkeit**, ohne sie nach Loop-Regeln zu bestrafen. Sie
liefert reproduzierbare, getrennte Score-Komponenten und klar getrennte harte
Ausschlussgründe. Eine finale globale Auswahl-Schwelle wird hier **nicht**
festgeschrieben; sie wird erst im Techno-Pilot #256 aus echter Evidenz
kalibriert.

Die Bewertung ist rein deterministisch: keine Audio-IO, keine Datenbank, kein
Netzwerk, kein Modell-Download, kein Rendering, kein Crossfade.

---

## 2. Was praktisch bewertet wird

Jeder Section-Kandidat wird entlang sechs unabhängiger Komponenten bewertet.
Alle Werte liegen im Bereich `[0, 1]`, haben eine explizite Bedeutung und einen
eigenen Status. Fehlende Evidence wird durch `status != "ok"` und
`value is None` dargestellt — **niemals** durch ein erfundenes Dummy-0.

| Komponente | Bedeutung |
|------------|-----------|
| `section_coherence` | Innerer musikalischer Zusammenhalt der Section (Self-Similarity, Recurrence, Rhythm-Stabilität, konsistente Timbre/Spektral-Textur). **Nicht** Loop-Wiederholung oder Seam-Kontinuität. |
| `musical_development` | Sinnvolle musikalische Entwicklung über die Section (gerichteter Arc via `multi_bar_trend`). Eine flache/steady Section ist neutral (0.5), wird **nicht** bestraft. |
| `boundary_security` | Sicherheit der neutralen Section-Grenzen (Boundary-Status + optionale relative `quality` 0–1). |
| `role_security` | Sicherheit der effective Arrangement-Rolle (Rollen-Status bzw. manueller Override). `unknown` ist gültig mit moderatem Wert. |
| `transition_risk` | Risiko eines internen Bar-zu-Bar-Übergangs innerhalb der Section (Neighbor-Delta). Separat, kein Hard-Reject. |
| `vocal_fx_edge_risk` | Risiko aus **expliziter** Vocal-/FX-Evidence. Nur mit echter Evidence gesetzt, sonst `not_evaluated` (nie erfunden). |

---

## 3. Section-Kohärenz

`section_coherence` beschreibt, ob die Section in sich als ein musikalischer
Gedanke zusammenhängt. Sie nutzt vorhandene StructureV1/#239/#265-Evidence
pro Bar innerhalb der Section:

- `self_similarity` (Mittel) → höher = kohärenter
- `recurrence` (Mittel) → höher = kohärenter
- `rhythm_stability` (Mittel) → höher = steadier
- `timbre_delta` / `spectral_delta` (Mittel, invertiert) → niedriger = konsistentere Textur

Kohärenz ist **explizit nicht** Loop-Wiederholbarkeit oder Seam-Kontinuität.
Es wird keine neue schwere Analysepipeline gebaut; es werden die bereits
vorhandenen Bar-Features wiederverwendet. Fehlende Teil-Evidence wird transparent
als `not_evaluated` behandelt.

---

## 4. Musikalische Entwicklung

`musical_development` nutzt `multi_bar_trend` (Richtung der Energie-Entwicklung
über die Bars). Ein klarer, konsistenter gerichteter Verlauf (steady Build oder
Drop) scoret hoch. Eine flache/steady Section scoret neutral (0.5) — Veränderung
wird **nicht pauschal bestraft**, und Entwicklung ist nicht dasselbe wie
Stabilität. Es wird keine neue Arrangement-Rolle aus der Entwicklung erfunden.

---

## 5. Boundary-Sicherheit

`boundary_security` wird strikt getrennt von der Rollen-Evidence berechnet:

- Basiswert aus `boundary.status` (`ok` / `partial` / `no_result` / `failed`),
  über `SectionScoringConfig.boundary_status_scores` konfigurierbar.
- Wenn `boundary.quality` real vorliegt (0–1), fließt sie gewichtet ein.
- Eine unsichere Boundary impliziert **nicht** eine unsichere Rolle und
  umgekehrt.

Ungültige oder nicht-endliche `quality` (z. B. außerhalb `[0,1]`) wird nicht
stillkorrigiert, sondern auf den status-basierten Wert zurückgeführt.

---

## 6. Rollen-Sicherheit

`role_security` wird strikt getrennt von `boundary_security` berechnet:

- `arrangement_role_source == "manual"` → `role_manual_certainty` (Konfiguration,
  Default 0.9): ein menschlicher Override ist eine explizite Behauptung.
- sonst Basiswert aus `arrangement_role_status` (`available` / `uncertain` /
  `unknown` / `unavailable` / `failed`), über `role_status_scores` konfigurierbar.

`unknown` ist eine gültige, normale Rolle mit moderatem Wert — **kein**
Hard-Reject. Es gibt **keinen** einzigen Universal-`confidence`-Wert, der
Boundary und Rolle zusammenmischt.

---

## 7. Automatic / Manual / Effective

Der Scorer verändert den Kandidaten nicht. Die `automatic`/`manual`/`effective`-
Herkunft aus #241 bleibt im `SectionCandidate` erhalten und wird im
`config_provenance` des Ergebnisses mitgeführt (`effective_role`,
`effective_role_source`). Die effective Rolle wird bewertet; die automatische
Herkunft bleibt sichtbar.

---

## 8. Transition-/Vocal-/FX-Randrisiken

- `transition_risk` ist eine eigene Score-/Risk-Komponente, gespeist aus
  vorhandener `neighbor_delta`-Evidence (größter interner Bar-Sprung).
- `vocal_fx_edge_risk` wird **nur** bewertet, wenn explizite echte Evidence
  übergeben wird (`SectionEdgeRiskEvidence`). Ohne Evidence ist der Status
  `not_evaluated` mit `value is None` — kein Dummy-Score, kein neues Modell.

---

## 9. Harte Ausschlüsse versus Soft-Score

Harte Ausschlüsse werden strikt von den Soft-Scores getrennt in
`reject_reasons` geführt (maschinenlesbare Codes). V1 kennt bewusst nur einen
fachlich klaren, unbrauchbaren Fall:

| Code | Bedeutung |
|------|-----------|
| `INVALID_RANGE` | `n_samples <= 0` (fail-closed, defensiv). |

**Explizit keine** Hard-Rejects für:

- `unknown`-Rolle allein
- unsichere Rolle allein
- Section-Veränderung allein
- fehlende Wiederholung
- fehlende Seam-Kontinuität

Weitere harte Ausschlussgründe (z. B. Stille, echte Übergangsverschmutzung)
werden bewusst dem Pilot #256 überlassen, wo sie aus echter Evidenz kalibriert
werden.

---

## 10. Provisorische, konfigurierbare Schwellen

Alle Gewichte (`SectionScoringConfig.weights`) und Status-Mappings
(`boundary_status_scores`, `role_status_scores`, `role_manual_certainty`) sind
über die Config veränderbar. Die Defaults sind **PROVISIONAL** (kennzeichnend
über `config_provenance["provisional"] = True`). Es ist **keine** finale
Pilot-Schwelle eingebrannt; der Scorer trifft keine globale Auswahlentscheidung
(`status` ist `ok` / `excluded`, nie `selected`).

---

## 11. Warum keine Seam-/Wiederholungsstrafe existiert

Sections entstehen aus Arrangement-Grenzen, nicht aus Loop-Regeln (#266 §9).
Diese Slice übernimmt bewusst **keine** Loop-Seam-Logik aus #252:

- keine Seam-Komponente,
- keine End-zu-Start-Bewertung,
- keine Wiederholungspflicht,
- keine Recurrence-Strafe nur wegen fehlender Wiederholung,
- keine feste 4/8/16-Bar-Pflicht,
- keine Übernahme von #252-Hard-Rejects ohne Section-spezifische Begründung.

`recurrence` wird weich (sofern vorhanden) nur als Kohärenz-Signal genutzt,
niemals als Ausschlusskriterium.

---

## 12. Asset-Manifest-Mapping (#250)

`SectionScoreResult.as_candidate_dict()` liefert den `#250`-konformen
`candidate`-Block:

| Manifest-Feld | Quelle |
|---------------|--------|
| `candidate.status` | `"rejected"` wenn `hard_rejected`, sonst `"candidate"` |
| `candidate.score_components` | die sechs benannten Komponenten (je `{name, value, range, meaning, status}`) |
| `candidate.excluded` | `hard_rejected` |
| `candidate.reject_reasons` | `reject_reasons` (nur wenn `excluded`) |

Section-ID, Rolle und Boundary-Herkunft bleiben im `candidate_ref` unverändert
erhalten. `rendering.status` bleibt `not_rendered`; es findet keine Reanalyse
(#254) statt.

---

## 13. Abgrenzung zu #252, #253 und #256

- **#252 (Loop Scoring):** eigener, disjunkter Score-Vertrag (Seam, interne
  Stabilität, Groove). Section-Scoring verwendet keine Loop-Hard-Rejects und
  keine Seam-Metrik.
- **#253 (Rendering):** rendert deterministisch. Dieser Scorer rendert nicht.
- **#256 (Pilot):** liefert die echte Evidenz, aus der finale Schwellen und
  allenfalls weitere Hard-Rejects kalibriert werden — erst dort, nicht hier.

---

## 14. Akzeptanzmapping (#267)

| #267-Kriterium | Abgedeckt durch |
|----------------|-----------------|
| Score-Komponenten und Ausschlussgründe reproduzierbar/nachvollziehbar | `score_components` + `reject_reasons`, deterministisch |
| Sections erhalten keine Wiederholungs-/Seam-Strafe | §11; Tests `test_no_seam_component_exists`, `test_no_repetition_requirement_as_hard_reject` |
| unsichere Rolle und unsichere Boundary bleiben getrennt sichtbar | §5/§6; Tests `test_role_security_separate_from_boundary_security` u. a. |
| endgültige Schwellen erst mit #256-Evidenz | §10 (`provisional`, keine globale Schwelle) |

---

## 15. Nicht-Ziele (v1)

- kein Loop-Scoring (#252)
- keine neue Boundary-Erkennung (#265)
- keine neue Rollenklassifikation (#240)
- kein Rendering (#253)
- keine Reanalyse (#254)
- keine neuen Vocal-/FX-Modelle
- keine erfundene `confidence` oder generic `confidence`
- keine feste Taktlänge, keine Wiederholungs- oder Seam-Regeln
- keine finale globale Auswahl-Schwelle (gehört zu #256)
