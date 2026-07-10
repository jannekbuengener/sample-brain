# Workbench Matching-/Vorschlagsansicht Plan

**Status:** Planning only — no implementation in this document.  
**Issue:** [#198 — Workbench: Matching- und Vorschlagsansicht planen](https://github.com/jannekbuengener/sample-brain/issues/198)  
**Parent:** [#117 — workbench usability and library workflow follow-ups](https://github.com/jannekbuengener/sample-brain/issues/117) (closed)  
**Related:** [`docs/product/02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md`](product/02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md), [`WORKBENCH_SEARCH_UI_PLAN.md`](WORKBENCH_SEARCH_UI_PLAN.md), `src/matching.py`, `src/workbench_controller.py`

## Zielbild in einfachen Worten

In der lokalen Workbench wählt der Producer ein Sample aus und klickt **„Ähnliche Samples"**. Die Workbench zeigt eine kurze, sortierte Liste anderer **bereits geladener** Samples, die rhythmisch, harmonisch und typisch passen — mit Score und kurzem Grund (z. B. „bpm direct match: 128 vs 128", „type match: Kick"). Der Producer kann einen Vorschlag in der Playlist fokussieren, den Pfad kopieren oder die bestehende Preview abspielen. Kein KI-Modell, kein Embedding-Download, keine automatische Playlist-Generierung.

## V1-Scope

Kleinster sinnvoller Vorschlagsmodus:

| Aspekt | V1-Verhalten |
|--------|--------------|
| **Eingabe** | Genau ein ausgewähltes `WorkbenchRow` mit gültigem `bpm > 0` |
| **Kandidatenpool** | Alle **aktuell geladenen** Rows der aktiven Ansicht (Ordner / Alle Library-Samples / Catalog lesen), `status == ok`, Referenz-Sample ausgeschlossen |
| **Scoring** | Direkte Wiederverwendung von `MatchProfile` + `match_candidates` aus `src/matching.py`; Referenz-BPM/Key/`pred_type` vom ausgewählten Row |
| **Ausgabe** | Top-N (Default 10), nur Rows mit `total_score > 0` |
| **Erklärbarkeit** | `reasons`-Strings aus `MatchResult` als „Grund"-Spalte |
| **Abhängigkeiten** | Keine Embeddings, kein `catalog.db`-SQL-Scan über geladene Rows hinaus |

### UI-Vorschlag (kleinste brauchbare Form)

1. **Auswahl** — Playlist-Zeile muss selektiert sein.
2. **Aktion** — Toolbar- oder Detail-Button **„Ähnliche Samples"** (deaktiviert ohne gültige Auswahl/BPM).
3. **Panel** — Einklappbares Panel **unterhalb der Playlist** (`ttk.Treeview`, analog bestehende Workbench-Panels).
4. **Spalten** — Name, BPM, Key, Typ, Grund (kompakt aus `reasons`), Score (`total_score`, 4 Dezimalstellen).
5. **Interaktionen** — Doppelklick/Enter → Vorschlag in Playlist selektieren; Kontextmenü: Pfad kopieren, Preview (bestehende Preview-Pipeline).
6. **Status** — Bei Referenz ohne BPM: „Ähnliche Samples benötigen ein analysiertes BPM."; bei leerem Ergebnis: „Keine Vorschläge in geladener Ansicht."

### Controller-Hook (Implementierungs-Slice, nicht in diesem Plan)

Reine Funktion in `src/workbench_controller.py`, z. B.:

```text
suggest_similar_workbench_rows(reference, candidates, *, limit=10) -> list[WorkbenchSuggestion]
```

- Mappt `WorkbenchRow` → `MatchCandidate` (synthetische `sample_id` aus Pfad-Hash oder Index).
- Baut `MatchProfile` aus Referenz-Row.
- Ruft `match_candidates` auf, filtert `total_score > 0`, schließt Referenz aus.
- Kein DB-Zugriff, kein Seiteneffekt.

## V1-Nicht-Ziele

| Thema | Warum out of scope |
|-------|-------------------|
| CLAP / HF / Embeddings | [#73](https://github.com/jannekbuengener/sample-brain/issues/73) — semantische Qualität, nicht Workbench V1 |
| sqlite-vec / ANN / NumPy-Index | [#74](https://github.com/jannekbuengener/sample-brain/issues/74) — CLI search backend |
| `search`-Command in Workbench | Embedding-Pfad; anderes Surface |
| Match gegen volle `catalog.db` | Nur geladene Rows; kein versteckter SQL-Scan |
| Camelot / relative Key / Circle-of-Fifths | Nicht in `matching.py`; Spec-Gap in [`02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md`](product/02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md) |
| Tag-Ähnlichkeit | `details.tags` rule-based; kein Scoring in `matching.py` |
| Lautstärke / Helligkeit | Felder vorhanden, aber kein belastbares Scoring |
| Dauer-Nähe | `duration_sec` in Row, aber nicht in `matching.py` |
| Automatische Playlist / Batch-Vorschläge | Zu groß für V1 |
| Realtime-FL-Projektkontext | Kein Host-Plugin in Workbench |
| Private Samples / Audio / DBs im Repo | Verboten |
| Neue Recommendation-Architektur | V1 = dünner Controller-Wrapper um bestehendes Scoring |

## Datenbasis

Welche vorhandenen Felder werden genutzt?

| Feld (`WorkbenchRow`) | V1 | Quelle | Scoring |
|----------------------|-----|--------|---------|
| `bpm` | **Pflicht** (Referenz) | `analyze` | `score_bpm_match` — linear decay ±8 BPM; half/double mit Penalty 0.9 |
| `key` | Optional | `analyze` | `score_key_match` — Root + optional maj/min exakt |
| `pred_type` | Optional | `classify` | `score_type_match` — case-insensitive exakt |
| `sample_class` | Nein (nur Anzeige) | `analyze` | — |
| `details.duration_sec` | Nein | `analyze` | — |
| `loudness`, `brightness` | Nein | `analyze` | — |
| `details.tags` | Nein | rule-tags | — |
| Camelot | Nein | — | nirgends implementiert |

Gewichtung (wie CLI `match`): BPM 0.5, Key 0.3, Type 0.2 — nur Dimensionen mit gesetztem Zielwert zählen im Nenner.

## Vorschlagslogik

In normaler Sprache:

1. **BPM-Nähe** — Direkter Tempo-Match innerhalb der Toleranz (Default 8 BPM); bei Abweichung prüft das Scoring half-time (`bpm × 2`) und double-time (`bpm ÷ 2`) mit leichtem Malus (Faktor 0.9).
2. **Tonart-Kompatibilität** — Gleiche Root-Note; wenn beide Modi bekannt, muss maj/min übereinstimmen. Kein DJ-Kompatibilitätsmodus (kein Camelot, keine relativen Keys).
3. **Typ/Tag-Nähe** — Exakter Match auf `pred_type` (case-insensitive). Rule-Tags in `details.tags` fließen **nicht** in V1 ein.
4. **Gesamtscore** — Gewichteter Durchschnitt der aktiven Dimensionen; Sortierung absteigend nach `total_score`, dann deterministische Tie-Breaker (`bpm_score`, `key_score`, `type_score`, `sample_id`, `path`).
5. **Filter** — Nur Kandidaten mit `total_score > 0`; Referenz-Sample und Rows mit `status != ok` ausgeschlossen.

## Abgrenzung zu bestehenden Features

| Feature | Abgrenzung |
|---------|------------|
| CLI `sample-brain match` | Fit-to-track (manuelle Ziel-BPM); V1 = fit-to-**selected sample** auf geladenen Workbench-Rows |
| `workbench_attack_suggest` | Nur Attack-ms-Metadaten; UI-Pattern (Button + Apply) übernehmbar, Logik getrennt |
| `filter_workbench_rows` / structured filters | Substring-/Metadaten-**Filter**, keine Scoring-Rangliste |
| `hybrid_rank` / `search` | Semantic + metadata; Backlog #16/#17, [#73](https://github.com/jannekbuengener/sample-brain/issues/73) |
| Backlog #15 audio-to-audio | Embedding-Suche; später |
| Backlog #17 recommendation mode | Langfrist-Copilot; V1 = kleinster deterministischer Slice |
| [`02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md`](product/02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md) §5.4 fit-to-sample | Spec-Gap; **#198 V1 schließt diese Lücke in der Workbench** |

## Tests

Welche Tests sind bei der späteren Umsetzung nötig?

| Bereich | Datei | Inhalt |
|---------|-------|--------|
| Scoring-Reuse | `tests/test_matching.py` (erweitern) | Profil aus Row-Dict; half/double BPM weiter abgedeckt |
| Controller | `tests/test_workbench_matching.py` (neu) | Self-Exclude, fehlende BPM, leerer Pool, Sortierung, `total_score > 0`-Filter, `reasons`-Text |
| Workbench-Controller-Integration | `tests/test_workbench_controller.py` (falls vorhanden, erweitern) | Row→Candidate-Mapping, Grenzfälle |
| GUI Smoke | `tests/test_workbench_gui_smoke.py` | Button/Panel existiert; Mock-Rows → Panel befüllt |
| Keine echten Samples | alle | Synthetische `MatchCandidate` / `WorkbenchRow`-Dicts; `tmp_path` WAV nur wo Preview explizit getestet wird |

**Akzeptanzkriterien (Implementierungs-Slice):**

- Ausgewähltes Sample mit BPM liefert sortierte Vorschlagsliste aus geladenen Rows.
- Referenz erscheint nicht in der Liste.
- Jede Zeile zeigt mindestens einen Grund-String und einen Score.
- Referenz ohne BPM → klarer Fehlerhinweis, kein Crash.
- Catalog-readonly-Modus: Vorschläge anzeigbar, keine Metadaten-Schreibaktion.
- `pytest -q` grün; kein CLAP/HF-Download; keine privaten Audio-Dateien im Repo.

## Offene Entscheidungen

Nur echte Entscheidungen — keine Fantasie-Roadmap:

| # | Frage | Empfehlung | Begründung |
|---|-------|------------|------------|
| 1 | Panel-Platzierung: unter Playlist vs. rechts | **Unter Playlist** | Weniger Layout-Risiko; konsistent mit Filter-Zeilen |
| 2 | Catalog-Modus: Vorschläge erlauben? | **Ja, read-only** | Nur Anzeige/Preview/Kopieren; kein Schreiben |
| 3 | Mindest-Score-Schwelle | **`total_score > 0`** | Vermeidet Rauschen bei fehlenden Keys/Types |
| 4 | `sample_id` für in-memory Kandidaten | **Pfad-basierter Hash oder Listen-Index** | `match_candidates` braucht stabile IDs für Tie-Break; kein `catalog.db`-Join nötig |

## Implementierungs-Follow-up

Nach Merge dieses Plans und separatem Implementierungs-GO:

1. Controller-Funktion `suggest_similar_workbench_rows` + Tests.
2. Workbench-UI: Button, Panel, Selection-Bridge.
3. GUI-Smoke erweitern.
4. Issue #198 schließen oder Implementierungs-Child-Issue öffnen.

**Nicht in diesem Slice:** Feature-Code, UI-Code, Matching-Code-Änderungen, Dependencies, Workflows.

## References

- `src/matching.py` — `MatchProfile`, `match_candidates`, `score_candidate`, `collect_matches`
- `src/workbench_controller.py` — `WorkbenchRow`, `filter_workbench_rows`
- `src/workbench_attack_suggest.py` — UI-Pattern für Vorschläge (Attack only)
- `tests/test_matching.py` — 8 synthetische Tests
- [`WORKBENCH_SEARCH_UI_PLAN.md`](WORKBENCH_SEARCH_UI_PLAN.md) — in-memory Filter-Präzedenz
- [`WORKBENCH_GUI_SMOKE.md`](WORKBENCH_GUI_SMOKE.md) — GUI-Smoke-Vertrag
