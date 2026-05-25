# TITLE_RULES.md

## Verbindlicher Titel-Standard (SampleBrain)

**Ziel:** Einheitliche, menschlich lesbare Sample-Titel.
Analyse ergänzt **nur fehlende Informationen**. Bestehende Titelinhalte haben immer Priorität.

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
  Wird nur ergänzt, wenn im Titel nicht vorhanden.

- **KEY** *(optional)*  
  Format: `F#m`, `C`, `Eb`  
  Wird nur ergänzt, wenn Analyse sicher ist.

- **CHARACTER** *(optional)*  
  Freie, kurze Beschreibung, durch `/` getrennt  
  Beispiele: `dark/vintage`, `bright/clean`, `lofi/gritty`

---

## 3. Prioritätsregeln (sehr wichtig)

1. **Titel > Analyse**  
   Was im Titel steht, gilt als Wahrheit.

2. **Analyse ergänzt nur Lücken**  
   - BPM fehlt → analysieren und ergänzen  
   - Key fehlt → nur bei hoher Sicherheit ergänzen  
   - TYPE fehlt → aus Dateilänge + Struktur ableiten

3. **Nichts wird überschrieben**  
   Auch wenn die Analyse etwas anderes sagt.

---

## 4. Normalisierung (einheitliche Schreibweise)

Unabhängig von der Quelle wird normalisiert zu:

- BPM: `132BPM`
- Key: `F#m`, `Bb`, `C`
- Type: `[LOOP]`, `[ONE-SHOT]`, `[FX]`, `[VOCAL]`
- Trennzeichen:  
  - Kommas zwischen Meta-Feldern  
  - `-` zwischen Name/Meta und Analyse-Teil

---

## 5. Genre-Regel (bewusst ausgelagert)

- **Genre gehört nicht in den Titel**
- Genre ergibt sich aus:
  - Ordnerstruktur
  - Tags / Metadaten

Der Titel bleibt **arbeitsorientiert**, nicht kategorisch.

---

## 6. Beispiele

**Vollständig (nichts ändern):**
```
HH, closed, [LOOP] - 132BPM, F#m, dark/vintage
```

**Teilweise (ergänzen):**
```
Kick, deep, [ONE-SHOT]
→ Kick, deep, [ONE-SHOT] - --BPM, --KEY, punchy/sub
```

**Ohne BPM/Key (bewusst):**
```
Riser, long, [FX] - --BPM, --KEY, tense/cinematic
```

---

## 7. Stop-Regeln

Die Titel-Erzeugung **bricht ab**, wenn:
- der Titel nicht eindeutig parsebar ist
- widersprüchliche BPM/Key-Angaben existieren
- der Nutzer manuelle Kontrolle erzwingen möchte

---

## 8. Philosophie

> Der Titel ist für Menschen.  
> Die Analyse arbeitet im Hintergrund.  
> Ordnung entsteht durch **Konsistenz**, nicht durch Kreativität.

---

**Status:** v1 – verbindlich  
**Änderungen:** nur bewusst, versioniert
