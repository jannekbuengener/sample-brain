# Sample Brain — Portfolio Case Study

## 1. Ausgangsproblem

Sample Brain entstand aus einem realen Producer-Problem: Große lokale Sample-Libraries wachsen schneller, als Ordner- und Dateinamenskonventionen sie sinnvoll durchsuchbar halten können. BPM, Tonart, Typ, Klangcharakter und musikalische Passung stecken im Audio, sind aber im normalen Dateibrowser nur teilweise sichtbar.

Das Produktziel ist deshalb nicht „KI macht Musik“, sondern: **Ein Producer findet und bewertet vorhandenes Material schneller, nachvollziehbarer und ohne seine Library in eine Cloud hochladen zu müssen.**

## 2. Product Discovery / Vision

Die Produktdefinition priorisiert fünf Themen:

1. Library Intelligence
2. Harmonic & Rhythmic Matching
3. Track Context Analysis
4. Realtime Fit & Transform
5. Producing Workspace

Die Vision ist größer als der aktuelle Stand. Genau deshalb trennt das Projekt konsequent zwischen **shipped**, **experimental** und **target**.

Siehe: [Product Requirements](PRODUCT_REQUIREMENTS.md).

## 3. Meine Rolle

Meine Rolle ist Product-/System-Orchestrierung:

- Problem und Zielgruppe definieren,
- Anforderungen in implementierbare Slices zerlegen,
- Schnittstellen und Systemgrenzen festlegen,
- spezialisierte AI-Coding- und Review-Agenten einsetzen,
- Acceptance Criteria und Tests verlangen,
- Ergebnisse gegen Evidence prüfen,
- bei fehlender Evidenz bewusst keine Produktionsclaims zulassen.

Die Implementierung ist stark AI-assisted. Das Projekt ist daher kein Claim auf klassische eigenständige Python-Entwicklung, sondern auf die Fähigkeit, mit KI ein komplexes Produkt strukturiert, überprüfbar und iterativ zu bauen.

## 4. Systemzerlegung

Der aktuelle Kern lässt sich in wenige nachvollziehbare Pfade zerlegen:

```text
Local Samples
   ↓
Scan → Analyze → Catalog
                 ├→ Search / Matching → Workbench / Live Kit
                 └→ Track Context → Deconstruction → Performance Pack
```

Schwere oder optionale Funktionen werden nicht als magischer Monolith behandelt, sondern als getrennte Komponenten mit eigenen Verträgen, Artefakten und Gates.

Siehe: [Target Architecture](TARGET_ARCHITECTURE.md).

## 5. AI-assisted Delivery

Die Delivery folgt einem wiederkehrenden Muster:

1. Problem und gewünschter Nutzerzustand definieren.
2. Scope und Nicht-Ziele festhalten.
3. Acceptance Criteria formulieren.
4. Implementierungsarbeit an passende Agenten delegieren.
5. Tests / Review / Visual Acceptance ausführen.
6. Findings klassifizieren.
7. Relevante Blocker reparieren.
8. Erst bei belastbarer Evidence den Status hochstufen.

Die AI ist dabei Ausführungs- und Analysewerkzeug, nicht die Instanz, die ungeprüft den Wahrheitsstatus des Produkts bestimmt.

## 6. Drei wichtige Fehlversuche / Gegenentscheidungen

### CLAP: Textsuche ist nicht automatisch produktionsreif

Die optionale CLAP-Suche wurde auf reproduzierbaren synthetischen Fixtures bewertet. Audio-to-Audio schnitt dabei stärker ab als Textsuche. Das Projekt veröffentlicht diese Werte inklusive Grenzen und behauptet ausdrücklich **keine Produktionsreife auf echten Producer-Libraries**.

Siehe: [Search Quality Evidence](benchmarks/SEARCH_QUALITY_EVIDENCE.md).

### sqlite-vec: Schneller bedeutet nicht automatisch besser

sqlite-vec zeigte attraktive Latenzen, aber die Entscheidung über den Default wurde an Korrektheits- und Qualitätsgates gebunden. Der schnellere Pfad wurde nicht einfach aktiviert, nur weil die Performance überzeugend aussah.

Siehe: [sqlite-vec Gate Evidence](benchmarks/SQLITE_VEC_GATE_EVIDENCE.md).

### Stem Separation: Technisch möglich, trotzdem kein Default

Stem-Separation wurde technisch validiert, aber ungeklärte Lizenzfragen der Modellgewichte verhindern einen seriösen Produktions-Default. Das ist eine bewusste Produkt-/Governance-Entscheidung, kein verstecktes „fast fertig“.

## 7. Validation / Evidence

Sample Brain verwendet mehrere Evidence-Arten:

- Regressionstests für Kernverträge,
- deterministische Fixtures für Search-Evaluation,
- Runtime-Provenance für verifizierte lokale Builds,
- Visual-Acceptance-Harness für Screen-1,
- dokumentierte Benchmark- und Gate-Ergebnisse,
- explizite HOLD-/Experimental-Zustände.

Für Visual Acceptance siehe [WORKBENCH_VISUAL_ACCEPTANCE.md](WORKBENCH_VISUAL_ACCEPTANCE.md).

## 8. Wichtige Produktentscheidungen

### Local-first

Private Samples sollen das System für Kernfunktionen nicht verlassen müssen. Datenbank, Indizes, Modell-Caches und generierte Packs bleiben lokale Runtime-Artefakte.

### Explicit over magical

Unsicherheit wird sichtbar gemacht. Ein System, das einen Key, eine Klassifikation oder eine Search-Qualität nicht belastbar kennt, soll das nicht als Gewissheit verkaufen.

### Producer workflow over demo wow-factor

Entscheidend ist nicht, ob ein einzelner AI-Demo-Run beeindruckt, sondern ob Library, Matching, Auditioning und Wiederverwendung im echten Producer-Workflow verlässlich zusammenspielen.

## 9. Aktueller Stand

Auf `main` sind heute unter anderem vorhanden:

- Library-/Sample-Katalog,
- Audioanalyse,
- Track Context,
- strukturiertes Matching,
- NumPy Search,
- optionale experimentelle Search-Backends,
- Track Deconstruction,
- Performance Packs,
- lokaler Workbench,
- Screen-1-/QML- und Visual-Acceptance-Infrastruktur.

Noch nicht als fertiges Produkt behauptet werden insbesondere:

- VST3-Produkt,
- vollständige Realtime Fit & Transform Engine,
- Produktionsreife experimenteller Search-/Stem-Pfade ohne ausreichende Evidence.

Die laufend gepflegte Feature-Matrix steht in der [README](../README.md).

## 10. Nächste Produktstufe

Die nächste Stufe besteht nicht einfach aus „mehr Features“, sondern aus Konvergenz:

- hochwertige Screen-1-Produktoberfläche,
- klarer Library → Matching → Live-Kit-Flow,
- belastbare Visual Evidence,
- weitere echte Producer-Evaluation statt nur synthetischer Search-Fixtures,
- schrittweiser Übergang von experimentellen Komponenten zu belegbaren Produktpfaden.

## 11. Was dieser Case demonstriert

Sample Brain ist für mich der stärkste Nachweis für die Kombination aus:

- Product Thinking,
- Audio-/Music-Tech-Domainwissen,
- Systemzerlegung,
- AI-/Agenten-Orchestrierung,
- Requirements Engineering,
- Evaluation und QA,
- transparentem Umgang mit Unsicherheit,
- AI-assisted Produktentwicklung ohne falsche Coding-Claims.
