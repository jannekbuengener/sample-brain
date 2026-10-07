# TITLE_RULES.md

## Verbindlicher Titel-Standard (SampleBrain)

**Ziel:** Einheitliche, menschlich lesbare Sample-Titel.

Filename/title metadata is **strong declarative evidence**, not unquestioned
ground truth. Explicit path/title claims may become **resolved catalog
metadata** when independent audio/classifier evidence confirms or compatibly
supports them. Conflicts remain explicit. Raw analyzer outputs
(`features.bpm`, key evidence, `class`, `pred_type`) stay measurements and are
never overwritten by filename values.

See [`docs/PATH_METADATA_RECONCILIATION.md`](PATH_METADATA_RECONCILIATION.md).

---

## 1. Finales Titel-Format (fix)

```
HH, closed, [LOOP] - 132BPM, F#m, dark/vintage
```

**Aufbau:**
```
<NAME>, <DETAIL>, [TYPE] - <BPM>, <KEY>, <CHARACTER>
```

---

## 2. Bedeutung der Felder

- **NAME**  
  Kurzer Hauptname des Sounds (z. B. HH, Kick, Snare, Riser, Vox)

- **DETAIL**  
  Verfeinerung oder Spielart (z. B. closed, open, tight, long)

- **[TYPE]** *(Pflichtfeld)*  
  `[LOOP]`, `[ONE-SHOT]`, `[FX]`, `[VOCAL]`

- **BPM** *(optional)*  
  Format: `132BPM`  
  Explizite Titel-/Dateiname-BPM-Angaben sind deklarative Claims; reconciled
  product values follow the path-metadata contract.

- **KEY** *(optional)*  
  Display forms such as `F#m`, `C`, `Eb` are accepted; catalog comparison uses
  the canonical key-signature contract (`F#min`, `Cmaj`, …).

- **CHARACTER** *(optional)*  
  Freie, kurze Beschreibung, durch `/` getrennt  
  Beispiele: `dark/vintage`, `bright/clean`, `lofi/gritty`

---

## 3. Prioritätsregeln (sehr wichtig)

1. **Filename/title = strong declarative evidence**  
   Explicit tokens are parsed into provenance-bearing claims. They are **not**
   absolute truth that silently overrides analysis.

2. **Independent analysis always runs for overlapping measurable fields**  
   Audio BPM/key and classifier `sample_class` / `pred_type` remain separate
   evidence sources. Filename existence does not skip analyze.

3. **Resolved metadata follows reconciliation**  
   - Agreement / half-double compatibility → filename-normalized value may become
     the resolved catalog value (`CONFIRMED` / `COMPATIBLE`).
   - Partial evidence (e.g. root-only analysis vs modeful filename) stays
     `PARTIAL`, not full confirmation.
   - Hard conflicts stay `CONFLICT`; filename must not silently overwrite
     analyzer results. Both sides remain inspectable.
   - Genre/path keywords without an independent analyzer are `DECLARED_ONLY`.

4. **Raw analyzer columns stay untouched**  
   Offline title-suggestion tools may still fill display gaps for human-facing
   rename proposals, but the catalog must not treat title content as
   unquestioned ground truth or contaminate analyzer-quality measurements.

---

## 4. Normalisierung (einheitliche Schreibweise)

Unabhängig von der Quelle wird für Anzeige normalisiert zu:

- BPM: `132BPM`
- Key (title display): `F#m`, `Bb`, `C` — catalog canonical: `F#min`, `A#maj`, …
- Type: `[LOOP]`, `[ONE-SHOT]`, `[FX]`, `[VOCAL]`
- Trennzeichen:  
  - Kommas zwischen Meta-Feldern  
  - `-` zwischen Name/Meta und Analyse-Teil

---

## 5. Genre-Regel (bewusst ausgelagert)

- **Genre gehört nicht in den Titel**
- Genre ergibt sich aus:
  - Ordnerstruktur
  - Tags / Metadaten (`DECLARED_ONLY` when path-derived)

Der Titel bleibt **arbeitsorientiert**, nicht kategorisch.

---

## 6. Beispiele

**Vollständig (nichts ändern am Anzeigeformat):**
```
HH, closed, [LOOP] - 132BPM, F#m, dark/vintage
```

**Teilweise (Anzeige ergänzen, Claims separat reconcilen):**
```
Kick, deep, [ONE-SHOT]
→ Kick, deep, [ONE-SHOT] - --BPM, --KEY, punchy/sub
```

**Ohne BPM/Key (bewusst):**
```
Riser, long, [FX] - --BPM, --KEY, tense/cinematic
```

**Konflikt (explizit, nicht still überschreiben):**
```
filename 128BPM + analysis 143 BPM → CONFLICT; features.bpm stays 143
```

---

## 7. Stop-Regeln

Die Titel-Erzeugung **bricht ab**, wenn:
- der Titel nicht eindeutig parsebar ist
- widersprüchliche BPM/Key-Angaben im Titel selbst existieren
- der Nutzer manuelle Kontrolle erzwingen möchte

Catalog reconciliation does **not** abort ingestion on conflict; it records
`CONFLICT` and continues.

---

## 8. Philosophie

> Der Titel ist für Menschen.  
> Die Analyse arbeitet im Hintergrund.  
> Ordnung entsteht durch **Konsistenz und explizite Provenance**, nicht durch
> blindes Vertrauen in Dateinamen.

---

**Status:** v2 – verbindlich (evidence reconciliation)  
**Änderungen:** nur bewusst, versioniert  
**Contract:** [`docs/PATH_METADATA_RECONCILIATION.md`](PATH_METADATA_RECONCILIATION.md)
