# Sample Brain — Skill-Auswahlhilfe für Agenten-Prompts

**Stand:** 2026-08-09  
**Repo-Basis:** jannekbuengener/sample-brain (main HEAD: 3fc4eb6)  
**Zweck:** Praktische Auswahlhilfe für Agenten und ChatGPT zur Skill-Selektion, Skill-Ketten, Beziehungen und typische Workflows

---

## 1. Das Wichtigste in einfachen Worten

Sample Brain arbeitet mit **vier Kernskills** und einer **Reihe spezialisierter Agenten**:

- **Repo-eigene Canon:** Vier lokale Skills unter `docs/skills/` – alle anderen Routing-Empfehlungen verweisen auf externe jMerta-Routen
- **Cursor-Spiegel:** `.cursor/skills/` enthält nur Mirrors der Canon-Skills – keine neuen Funktionen
- **Standalone-Garantie:** Jeder Skill funktioniert allein; Beziehungen stellen optionale Übergaben dar
- **Routing-Empfehlungen:** `.cursor/rules/skill-routing.mdc` und `docs/SKILL_INTEGRATION_PLAN.md` geben Vorschläge, aber keine Autorisierung
- **Externe Skills optional:** jMerta-Routen sind Empfehlungen; bei Unverfügbarkeit fallen lokale Agenten ein
- **Lokale Agenten (15):** Spezialisierte Cursor-Subagents unterstützen jede Skill-Kette, haben aber keine eigene Skill-Autorisierung
- **Live-State führt:** GitHub und Repo live state (git fetch, gh cli) gewinnt gegen Doku oder Erinnerung

---

## 2. Grundregeln für Skill-Einsatz

1. **Repo/GitHub-Live-State führt** – vor lokalem Wissen oder älteren Dokumenten
2. **Ein Skill kann allein starten** – Handoffs sind optional, keine Pflichtkette
3. **Nur product_code → test-first automatisch** – andere Slices haben spezialisierte Routen
4. **Keine externe Skill-Abhängigkeit ohne Fallback** – lokale Agenten puffern fehlerhafte externe Routen
5. **Explizites GO bleibt für Writes nötig** – Routing-Empfehlung autorisiert keine Commits/PRs
6. **Kein Skill autorisiert automatisch Merge** – siehe `SB.AGENT.RULESET.md` für Merge-Gating
7. **Test-First sperrt weich** – nur wenn ein Test rot ist, blockiert das Implementation
8. **Temporärer Notstandsmodus** – siehe Sektion 17

---

## 3. Standard-Skillketten für Sample Brain

### Feature / Neuer Produktcode
```
issue-to-session-plan → test-first → implementation-engineer (GO) → validation → optional PR packaging
```

### Bug mit unklarer Ursache
```
root-cause → regression-gap → test-first → implementation / validation
```

### Bekannter Defekt (Ursache klar)
```
regression-gap → test-first → implementation / validation
```

### CI fehlgeschlagen / Red Check
```
root-cause → ci-debugger
  oder direkt
ci-debugger
```

### Doku driftet vom Code
```
issue-to-session-plan → docs-sync-maintainer
```

### Dependency / CVE
```
issue-to-session-plan → dependency-upgrader
```

### Unbekanntes Problem
```
issue-to-session-plan → planning_blocked
```

**Wichtig:** Diese Ketten sind typische Wege, **keine Pflichtketten**. Jeder Skill kann allein benutzt werden.

---

## 4. Vollständiges Repo-Skill-Inventar (Kernskills)

| Skill | Praktische Aufgabe | Verwenden wenn | Nicht verwenden wenn | Standalone | Canon-Pfad |
|-------|-------|-------|-------|-------|-------|
| `sample-brain-issue-to-session-plan` | GitHub-Issue in kleine, aktuelle Workplan umwandeln | Neues Feature, Bug, oder Issue-Klassifizierung nötig | Ursache bereits klar und isoliert (→ root-cause direkt) | ✅ Ja | `docs/skills/sample-brain-issue-to-session-plan/SKILL.md` |
| `sample-brain-root-cause` | Fehlerursache mit Evidenz isolieren, ohne Fix/Tests zu schreiben | Symptom unklar, mehrere Hypothesen möglich | Ursache bereits bekannt; für blocker-Analyse → direkt issue-plan | ✅ Ja | `docs/skills/sample-brain-root-cause/SKILL.md` |
| `sample-brain-regression-gap` | Fehlende Guard/Test finden (nicht schreiben) | Bekannter Defekt, Ursache klar; Test-Lücke finden | Ursache noch unklar; CI-Fehler ohne Produkt-Cause | ✅ Ja | `docs/skills/sample-brain-regression-gap/SKILL.md` |
| `sample-brain-test-first` | DOCS → TESTS → TEST_FREEZE → IMPL → CHECKS erzwingen | Wesentliche Produktcode-Änderung vor Code-Implementierung | Docs-only, CI-only, Dependency-only Arbeit | ✅ Ja | `docs/skills/sample-brain-test-first/SKILL.md` |

---

## 5. Die vier Kernskills ausführlicher

### sample-brain-issue-to-session-plan

**Zweck:** GitHub-Issue in einen kleinen, verarbeitbaren Workplan verwandeln.

**Was es macht:**
- Klassifiziert die Arbeit: `product_code`, `docs`, `ci_tooling`, `dependency`, `workflow`, `governance`, oder `unknown`
- Baut einen engen Slice mit Blockern und direkten Abhängigkeiten
- Nur `product_code` → automatisch `sample-brain-test-first`
- Andere Slices → spezialisierte externe Routen (docs-sync, ci-fix, dependency-upgrader, …)
- Unklare Slice → `planning_blocked` mit fehlender Info

**Output:** Klassifikation, Slice, Route, Test-Anforderung

**Typische Übergabe an:** test-first (product_code), docs-sync (docs), ci-fix (ci_tooling)

---

### sample-brain-root-cause

**Zweck:** Unklare Fehlerursache mit harter Evidenz isolieren.

**Was es macht:**
- Symptom → Hypothesen → Evidenz-Check → Root Cause Bestimmung
- **Schreibt keine Tests, implementiert keine Fixes**
- Produktbehavior-Ursache → regression-gap
- CI/Tooling/Infrastruktur-Ursache → ci-fix
- Doku-/Contract-Ursache → docs-sync

**Output:** Confirmed cause oder INCONCLUSIVE

**Typische Übergabe an:** regression-gap (Produkt), ci-fix (CI), docs-sync (Doku)

---

### sample-brain-regression-gap

**Zweck:** Fehlende Guard/Test für bekannten Defekt identifizieren.

**Was es macht:**
- Findet die schmalste fehlende Test-Protection
- **Schreibt die Tests nicht selbst** – nur Identifikation
- Taxonomy: unit, contract, regression, integration, cli, sqlite, config, audio-fixture, ui, smoke
- Bei unklarer Ursache → zurück zu root-cause
- Bei klarem Guard → test-first

**Output:** Test-Typ, Target-Pfad, Priorität (P0/P1/P2), Risiko wenn übersprungen

**Typische Übergabe an:** test-first

---

### sample-brain-test-first

**Zweck:** Bindender Repo-Vertrag für Produktcode: DOCS → TESTS → FREEZE → IMPL → CHECKS

**Was es macht:**
1. **DOCS_GATE:** Dokumentation muss vor Tests existieren und klar sein
2. **TEST_GATE:** Tests schreiben (red), bevor Code ändert sich
3. **TEST_FREEZE:** Tests sind danach eingefroren, kein Weichmachen
4. **IMPLEMENTATION:** Code implement nur wenn Tests frozen sind
5. **CHECKS:** CI/Linting/Tests grün vor Merge

**Keine Phase darf übersprungen werden.**

**Output:** Durchlaufen aller 5 Gates oder BLOCKED_* Fehler

**Typische Übergabe an:** implementation-engineer (wenn alle Gates ok)

---

## 6. Relationship-System (Beziehungen zwischen Skills)

Jeder Skill hat optionale Beziehungen:

| Begriff | Bedeutung |
|---------|-----------|
| **standalone** | Skill funktioniert allein, braucht keine Eingabe von anderen |
| **can_receive_from** | Welche Skills können diesen Skill mit Ergebnis versorgen |
| **route_if** | Bedingung, unter der dieser Skill empfohlen wird |
| **next_recommended** | Wohin es typisch nach diesem Skill weitergehen könnte |
| **optional_external** | Externe jMerta-Route, die optional ist |
| **local_fallback** | Welcher lokale Agent fällt ein, wenn externe Route fehlt |

**Praktisch:** Relationships machen Kombinationen stärker, aber erzeugen **keine Pflichtabhängigkeiten**. Sie sind Empfehlungen, keine Autorisierung.

---

## 7. Skill-Beziehungen kompakt

### Issue Planner (`sample-brain-issue-to-session-plan`)
- **Standalone:** ✅ Ja
- **Kann von empfangen:** Manuelle Issue-URL / GitHub Link
- **Routes zu:** test-first (product_code) | docs-sync (docs) | ci-fix (ci_tooling) | dependency-upgrader (dependency) | planning_blocked (unknown)
- **Optional external:** jMerta/plan-work (Implementierung planen)
- **Lokaler Fallback:** control-orchestrator

### Root Cause (`sample-brain-root-cause`)
- **Standalone:** ✅ Ja
- **Kann von empfangen:** issue-to-session-plan (klassifiziert als product/CI), manuelle Fehler-Beschreibung
- **Routes zu:** regression-gap (Produkt) | ci-debugger (CI) | docs-sync (Doku)
- **Optional external:** jMerta/bug-triage (ergänzend)
- **Lokaler Fallback:** code-reviewer (Diff-Analyse)

### Regression Gap (`sample-brain-regression-gap`)
- **Standalone:** ✅ Ja
- **Kann von empfangen:** root-cause (cause confirmed) | issue-to-session-plan (known defect classification)
- **Routes zu:** test-first (guard clear)
- **Optional external:** jMerta/bug-triage (ergänzend)
- **Lokaler Fallback:** Zurück zu root-cause (bei unclear cause)

### Test First (`sample-brain-test-first`)
- **Standalone:** ✅ Ja (wenn Issue/Slice bereits verständlich)
- **Kann von empfangen:** issue-to-session-plan (product_code) | regression-gap (guard identified)
- **Routes zu:** implementation-engineer (GO) | quality-gatekeeper (PR review)
- **Optional external:** jMerta/commit-work, jMerta/create-pr
- **Lokaler Fallback:** pr-packager (Commit/Branch-Vorbereitung)

---

## 8. Externe Skills (jMerta-Routen)

| Skill | Praktische Aufgabe | Status | Optional für | Lokaler Fallback |
|-------|-------|-------|-------|-------|
| `jMerta/bug-triage` | Bug-Klassifizierung, erste Triage | DECLARED_BUT_NOT_VERIFIED | Ergänzung zu root-cause | root-cause (allein) |
| `jMerta/ci-fix` | GitHub Actions Fehler diagnostizieren | DECLARED_BUT_NOT_VERIFIED | CI-Tooling Slices | ci-debugger (allein) |
| `jMerta/dependency-upgrader` | Dependency-Bumps, CVE-Fixes | DECLARED_BUT_NOT_VERIFIED | Dependency Slices | pr-packager (manual handle) |
| `jMerta/docs-sync` | Doku-Drift beheben | DECLARED_BUT_NOT_VERIFIED | Docs Slices | docs-sync-maintainer (lokal) |
| `jMerta/plan-work` | Implementierung planen | DECLARED_BUT_NOT_VERIFIED | Planungs-Details | control-orchestrator (lokal) |
| `jMerta/commit-work` | Commit vorbereiten | DECLARED_BUT_NOT_VERIFIED | PR-Workflow | pr-packager (lokal) |
| `jMerta/create-pr` | PR öffnen/aktualisieren | DECLARED_BUT_NOT_VERIFIED | PR-Workflow | pr-packager (lokal) |
| `jMerta/coding-guidelines-verify` | Code-Qualität vor Merge | DECLARED_BUT_NOT_VERIFIED | PR-Quality-Gate | quality-gatekeeper (lokal) |

**Status-Legende:**
- `VERIFIED_AVAILABLE` – Live verfügbar und getestet
- `DECLARED_BUT_NOT_VERIFIED` – In Routing-Docs deklariert, Live-Verfügbarkeit nicht geprüft
- `UNAVAILABLE` – Nicht verfügbar oder deprecated
- `REPLACED_BY_LOCAL_AGENT` – Lokaler Agent übernimmt Funktion

---

## 9. Lokale Fallbacks und spezialisierte Agenten

Wenn externe Skills nicht verfügbar sind, greifen diese lokalen Agenten ein:

| Aufgabe | Externe Route | Lokaler Fallback |
|---------|-------|-------|
| Bug-Triage | jMerta/bug-triage | root-cause (direkt) |
| CI-Diagnose | jMerta/ci-fix | ci-debugger (allein) |
| Doku-Sync | jMerta/docs-sync | docs-sync-maintainer (allein) |
| Dependency-Bump | jMerta/dependency-upgrader | pr-packager (manual) |
| Planung | jMerta/plan-work | issue-to-session-plan + control-orchestrator |
| Commit/PR | jMerta/commit-work + jMerta/create-pr | pr-packager (allein) |
| PR-Quality-Gate | jMerta/coding-guidelines-verify | quality-gatekeeper (allein) |
| Code-Review | jMerta/coding-guidelines-verify | code-reviewer (diff-only) |

---

## 10. Cursor-Subagents (15 verfügbar)

Subagents sind **KEINE Skills**. Sie sind spezialisierte Agenten, die Skills unterstützen.

| Subagent | Typ | Praktische Aufgabe | Sinnvoll zusammen mit | Write-Fähigkeit |
|----------|------|-------|-------|-------|
| control-orchestrator | CONTEXT_PROVIDER | Workflows koordinieren, an Agenten delegieren, Board-Zustand pflegen | issue-to-session-plan, Planung | ❌ Readonly |
| ci-debugger | ANALYSIS_HELPER | GitHub Actions Logs, Fehler diagnostizieren, Fixes vorschlagen | root-cause, ci-fix | ❌ Readonly |
| code-reviewer | VALIDATION_TARGET | PR-Diff-Analyse, Safety/Scope-Checks | test-first, quality-gatekeeper | ❌ Readonly |
| docs-sync-maintainer | IMPLEMENTATION_TARGET | Canon-Drift Erkennung, Docs mit Code sync | root-cause (Doku-Cause), docs-sync | ✅ Schreib |
| implementation-engineer | IMPLEMENTATION_TARGET | Features/Fixes nach ADR, Code + Tests + Docs | test-first | ✅ Schreib |
| security-triage | VALIDATION_TARGET | Security-Audit, Gitleaks, Dependency-Review, Secret-Scan | root-cause (Security-Cause) | ❌ Readonly |
| dependency-upgrader | IMPLEMENTATION_TARGET | Dependency-Bumps, Range-Checks, Compatibility | issue-to-session-plan (dependency slice) | ✅ Schreib |
| pr-packager | PACKAGING_TARGET | Branch-Erstellung, Commit-Squash, PR-Body | test-first (nach Impl), pr-packaging | ✅ Schreib |
| issue-backlog-maintainer | CONTEXT_PROVIDER | ISSUE_BACKLOG.md pflegen, Issue-Status ↔ Board sync | issue-to-session-plan | ✅ Schreib |
| bootstrap-validator | VALIDATION_TARGET | Bootstrap-Proof, CLI-Entry-Points, Runtime-Smoke | tests, setup validation | ❌ Readonly |
| quality-gatekeeper | VALIDATION_TARGET | Scope-Compliance, Required-Checks, Merge-Gates, PASS/HOLD-Calls | test-first, pr-packaging | ❌ Readonly |
| repository-auditor | ANALYSIS_HELPER | Repo-State, Layout, Drift, Hygiene, Risik-Inventar | root-cause, skill-routing-audit | ❌ Readonly |
| skill-routing-auditor | ANALYSIS_HELPER | Skill-Routing-Qualität, Cursor-Rules, Prioritäten | issue-to-session-plan | ❌ Readonly |
| system-architect | ANALYSIS_HELPER | Kleine Arch-Entscheidungen, CLI/Data-Flow, Design-Notes | test-first (spec), root-cause | ❌ Readonly |
| validation-evidence-analyst | VALIDATION_TARGET | Command-Evidence, Test-Interpretation, Bootstrap-Proof | test-first, quality-gatekeeper | ❌ Readonly |

**Wichtig:**
- `readonly: false` bedeutet nur **technische** Schreibfähigkeit
- Schreiben braucht weiterhin scoped GO (explizite Freigabe)
- Jeder Agent hat Bootloader-Anforderungen (AGENTS.md, SB-Files lesen)

---

## 11. Skill + Agent Kombinationen (praktische Beispiele)

### Neue Produktfunktion
```
issue-to-session-plan
+ control-orchestrator (Orchestrierung)
+ repository-auditor (Kontext)
→ test-first
+ implementation-engineer (Implementierung)
→ quality-gatekeeper (Final Gate)
+ pr-packager (PR vorbereiten)
```

### Bug mit unklarer Ursache
```
root-cause
+ code-reviewer (Diff-Analyse optional)
+ ci-debugger (wenn CI-relevant)
→ regression-gap
+ validation-evidence-analyst (Evidence sammeln)
→ test-first
+ implementation-engineer (Fix)
```

### Bekannter Defekt
```
regression-gap
+ validation-evidence-analyst (Gap-Bestätigung)
→ test-first
+ implementation-engineer
→ quality-gatekeeper (Merge-Gate)
```

### CI rot
```
root-cause
+ ci-debugger
→ ci-fix (jMerta oder ci-debugger allein)
+ pr-packager (wenn Workflow-Change nötig)
```

### Doku driftet
```
issue-to-session-plan (Klassifizierung)
+ repository-auditor (Drift-Nachweis)
→ docs-sync-maintainer (lokal) oder jMerta/docs-sync
```

### PR-Abschluss (Quality-Gate)
```
quality-gatekeeper (Final Check)
+ code-reviewer (Diff-Review)
+ validation-evidence-analyst (Evidence-Prüfung)
→ pr-packager (Merge vorbereiten)
```

**Keine künstlichen Pflichtkombinationen** – jede Kombination ist optional und situativ.

---

## 12. Typische Auswahl nach Auftrag

**Neue Produktfunktion:** issue-to-session-plan → test-first  
**Bug (Ursache unklar):** root-cause → regression-gap → test-first  
**Bekannter Defekt:** regression-gap → test-first  
**CI rot:** root-cause → ci-debugger oder direkt ci-debugger  
**Doku passe nicht:** issue-to-session-plan → docs-sync-maintainer  
**Dependency-CVE:** issue-to-session-plan → dependency-upgrader  
**Security-Audit:** skill-routing-auditor oder root-cause (Security-Cause)  
**PR-Review:** quality-gatekeeper + code-reviewer  
**Issue-Backlog-Pflege:** issue-backlog-maintainer  
**Skill/Routing-Audit:** skill-routing-auditor  

---

## 13. Was bewusst KEIN eigener Skill ist

| Ding | Warum kein Skill? |
|-----|-------|
| Session-Start | Bootloader-Funktion (SB.BOOTLOADER.md reguliert) |
| Session-Close | Bootloader-Funktion |
| Symptom-Triage | root-cause deckt das ab |
| Debug-Handoff | Agenten-Aufgabe (control-orchestrator) |
| Docs-Ops | Spezifisch für docs-sync-maintainer Agent |
| Integration-Wiring-Audit | system-architect Agent übernimmt |
| PR-Gap-Classifier | quality-gatekeeper Agent übernimmt |
| PR-Completeness-Review | quality-gatekeeper Agent übernimmt |
| Merge Conductor | control-orchestrator Agent übernimmt |
| Contract-Evidence-Gatekeeper | quality-gatekeeper + validation-evidence-analyst |
| Audio-Analyse | Runtime-Code (cli.py, analyze.py) – nicht Skill-Scope |
| Track-Deconstruction | Produktwissen + Spec (docs/TRACK_MAP_V1.md) – nicht Skill-Scope |
| Search-Matching | Runtime-Code (search.py) – nicht Skill-Scope |
| Workbench | Produktwissen – nicht Skill-Scope |
| SQLite-Management | Runtime-Code (db.py) – nicht Skill-Scope |
| FL-Studio-Export | Runtime-Code (export.py) – nicht Skill-Scope |

---

## 14. Zukünftige Kandidaten (noch nicht aktiv)

Diese Skills könnten später sinnvoll werden:

| Skill-Name | Status | Wann sinnvoll? |
|-------|-------|-------|
| `sample-brain-drift-reconcile` | USEFUL_LATER | Nach mehreren PR-Zyklen mit großen Refactorings |
| `sample-brain-pr-readiness` | USEFUL_LATER | Bei Merge-Konflikten oder komplexen Multi-Skill-PRs |

Nicht als aktive Skills behandeln; nur für späteren Kontext dokumentiert.

---

## 15. Nicht als aktive Sample-Brain-Skills behandeln

- **`.cursor/agents/*`** = Agenten, keine Skills (nur ausführend)
- **`.cursor/rules/*`** = Regeln, keine Skills (nur informativ)
- **`.cursor/skills/*`** = Mirrors der Canon-Skills, nur Kopien
- **`Externe jMerta-Routen`** = Empfehlungen, optional, nicht Repo-Canon
- **`Zukünftige Skills`** = Noch nicht aktiv (Sektion 14)
- **`Track Map / Specs / ADRs`** = Produktwissen, keine Skills

---

## 16. Regeln für künftige Agenten-Prompts

Wenn Sie Agenten auffordern, Skills zu nutzen:

1. **Session-Skills und Sub-Agents getrennt aufführen**

   ```
   Session-Skills:
   /sample-brain-issue-to-session-plan
   /sample-brain-test-first
   
   Sub-Agents:
   /sample-brain-control-orchestrator
   /sample-brain-implementation-engineer
   ```

2. **Nur passende Skills aufnehmen** – nicht alle in jeden Prompt
3. **Routing-Empfehlung ist nicht Autorisierung** – GO bleibt erforderlich
4. **Live-State zuerst** – git fetch, gh pr list vor jeder Aussage über PRs/Issues
5. **Bootloader-Sequenz respektieren** – AGENTS.md, SB-Files lesen

---

## 17. Temporärer Notstandsmodus

Der aktuelle Bootloader aktiviert einen zeitlich begrenzten Notstandsmodus:

**Kriterien:**
- Technische Checks grün (Code compiles, Linting ok)
- Harte Gates bestanden (Security, Dependency)
- Tests grün (unit + integration)

**Verhalten:**
- ✅ Weiter, keine freiwilligen Zusatzreviews
- ✅ Nice-to-have-Probleme blockieren nicht
- ✅ Kleine In-Scope-Probleme können autonom behoben werden
- ❌ Nur echte harte Blocker stoppen

**WICHTIG: Wird als TEMPORÄR markiert.** Dies ist keine dauerhafte Skill-Governance.

---

## 18. Aktueller technischer Stand

- **Main HEAD:** 3fc4eb6 (Merge pull request #273)
- **PR #273:** ✅ MERGED (Skill-Relationship-Graph)
- **Aktive Canon-Skills:** 4 Kernskills unter `docs/skills/`
- **Cursor-Mirrors:** 4 Kopien unter `.cursor/skills/`
- **Verfügbare Agenten:** 15 Subagents (SB.AGENT.LIST.json)
- **Externe Routen-Status:** DECLARED_BUT_NOT_VERIFIED (jMerta-Set)
- **Relationship-Graph:** Aktiv (nach PR #273 merge)
- **Live Open PRs:** Keine (Stand 2026-08-09)

---

## 19. Pflege dieser Datei

Aktualisieren Sie diese Auswahlhilfe, wenn:

- Ein neuer Skill hinzugefügt / entfernt / umbenannt wird
- Skill-Beziehungen ändern
- Ein Agent hinzugefügt / entfernt wird
- Externer Skill-Status ändert
- Routing-Empfehlung ändert
- Neuer dauerhafter Governance-Schritt entsteht

---

## 20. Kurzfassung für ChatGPT & schnelle Referenz

**Neue Produktfunktion:**  
Plan → Test First → Implement → Validate

**Bug (Ursache unklar):**  
Root Cause → Regression Gap → Test First

**Bekannter Defekt:**  
Regression Gap → Test First

**CI / GitHub Actions kaputt:**  
Root Cause oder CI Debugger (direkt)

**Doku passe nicht zum Code:**  
Planner oder Docs Maintainer

**Dependency / CVE:**  
Planner → Dependency Upgrader

**Immer:**
- ✅ Live-State zuerst (git fetch, gh cli)
- ✅ Skills sind standalone
- ✅ Handoffs sind optional
- ✅ Externe Skills sind optional
- ✅ GO ist für Writes nötig
- ✅ Kein Auto-Merge durch Skill
- ✅ Bootloader-Sequence respektieren

---

## 21. Qualitätssicherung dieser Datei

- ✅ Deutsches Verständlich-Deutsch (keine unnötige Fachsprache)
- ✅ Praktische Bedeutung vor Theorie
- ✅ Keine CDB-spezifischen Terms (Echtgeld, Trading, …)
- ✅ Nicht aufgebläht, um CDB-Länge zu erreichen
- ✅ Canon-Skill-Inhalte gegen echte SKILL.md geprüft
- ✅ Agent-Rollen gegen SB.AGENT.LIST.json geprüft
- ✅ Externe Verfügbarkeit als DECLARED_BUT_NOT_VERIFIED behandelt
- ✅ Keine erfundenen Skill-Funktionen

---

## Validierung vor Merge

- ✅ `git diff --check` (trailing spaces)
- ✅ Links/Pfade prüfen (`docs/skills/`, `.cursor/rules/`)
- ✅ Skill-Namen gegen `docs/skills/` geprüft
- ✅ Agent-Namen gegen `SB.AGENT.LIST.json` geprüft
- ✅ Externe Namen gegen `SB.VERFUEGBARE.SKILLS.md` geprüft
- ✅ Keine falschen Canon-Claims
- ✅ Keine Runtime/Dependencies/Workflows geändert
- ✅ Keine privaten Pfade / Samples / Artefakte

---

**Autor:** Copilot CLI  
**Stand:** 2026-08-09  
**Version:** 1.0
