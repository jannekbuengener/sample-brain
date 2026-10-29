# Skill Integration Plan â€“ sample-brain

## Role of this document

**Human narrative / orientation only.**
Machine routing authority is [`docs/operations/CAPABILITY_REGISTRY.json`](operations/CAPABILITY_REGISTRY.json).
Operations front door: [`docs/operations/README.md`](operations/README.md).
Generated views: [`.cursor/rules/skill-routing.mdc`](../.cursor/rules/skill-routing.mdc), [`SB.VERFUEGBARE.SKILLS.md`](../SB.VERFUEGBARE.SKILLS.md).
`SB.VERFUEGBARE.SKILLS_LISTE_2026-08-09.md` is **historical/frozen**, not active routing authority.

Do not treat this file as a second independent routing matrix. Prefer regenerating views from the registry:

```bash
python tools/generate_capability_views.py
python tools/check_capability_drift.py
```

## Kurzbeschreibung

Skills geben Agenten in `sample-brain` wiederholbare Workflows statt Ad-hoc-Entscheidungen.
Sie beschleunigen Bugfix, CI-Triage, Dependency-Pflege, Doku-Sync und PR-Vorbereitung â€“ ohne neue Tools oder CI-Ã„nderungen einzufÃ¼hren.

**Bestehende CI/DevSecOps-Basis (nur Referenz, nicht Ã¤ndern):**

- `.github/workflows/ci-smoke.yml` â€“ Python smoke
- `.github/workflows/codeql.yml` â€“ CodeQL SAST
- `.github/workflows/dependency-review.yml` â€“ Dependency Review
- `.github/workflows/gitleaks.yml` â€“ Secret Scanning

Skill-Quellen:

- `sample-brain-issue-to-session-plan` â€“ lokaler Planungs-Start fuer ein konkretes Issue
- `sample-brain-root-cause` â€“ lokaler Nachweis einer unklaren Fehlerursache
- `sample-brain-regression-gap` â€“ lokaler fehlender Schutz fuer einen bekannten Defekt
- `sample-brain-test-first` â€“ lokaler Repo-Vertrag fuer wesentliche Produktivcode-Implementierung
- `sample-brain-jules-dispatch` â€“ expliziter Opt-in-Weg, ein klar abgegrenztes Issue sicher an Jules zu delegieren (RÃ¼ckprÃ¼fung bleibt lokal bei Sample Brain)
- `sample-brain-skill-effectiveness` â€“ Verhaltens-Evaluator (Baseline ohne Skill â†’ Skill-Run â†’ EFFECTIVE|INEFFECTIVE|UNNECESSARY); ersetzt keine Produkt-/Registry-Tests
- `sample-brain-qml-component-test` â€“ fokussierte QML-Komponententests fÃ¼r Signale, Focus, Pointer, Lifecycle, async Projection und Virtualisierung
| `sample-brain-qml-component-test` | QML-Komponententest-Design fÃ¼r Pointer/Focus/Signale/Lifecycle/Virtualisierung (nicht nur Python-Adapter) |
QML-Interaktions-/Lifecycle-Coverage planen -> sample-brain-qml-component-test -> optional sample-brain-test-first
- `jMerta` â€“ tÃ¤glicher Agenten-Workflow (PrioritÃ¤t A)
- `Anthropic-Cybersecurity-Skills` â€“ Security-Hardening (PrioritÃ¤t B)

Routing-Details (generated view): [.cursor/rules/skill-routing.mdc](../.cursor/rules/skill-routing.mdc)

---

## PrioritÃ¤t A â€“ TÃ¤glicher Agenten-Workflow

| Skill | Wann nutzen |
|-------|-------------|
| `jMerta/bug-triage` | Bug, Regression, fehlender Test/Build |
| `jMerta/ci-fix` | CI rot, fehlgeschlagene GitHub Actions |
| `jMerta/dependency-upgrader` | Dependency-Bump, CVE, `requirements.txt`-Update |
| `jMerta/docs-sync` | README/Docs passen nicht mehr zum Code |
| `jMerta/commit-work` | Commit vorbereiten, Message, Staging |
| `jMerta/create-pr` | PR Ã¶ffnen, Beschreibung, Checks |
| `jMerta/plan-work` | Implementierung planen, Scope klÃ¤ren |
| `sample-brain-issue-to-session-plan` | Neues Feature oder Issue zuerst in einen kleinen aktuellen Arbeitsplan Ã¼berfÃ¼hren |
| `sample-brain-jules-dispatch` | Klar abgegrenztes Issue explizit an Jules delegieren (Opt-in, RÃ¼ckprÃ¼fung lokal) |
| `sample-brain-root-cause` | Unklare Fehlerursache erst mit Evidenz isolieren |
| `sample-brain-regression-gap` | FÃ¼r bekannten Defekt den kleinsten fehlenden Schutz bestimmen |
| `sample-brain-test-first` | Vor jeder wesentlichen Produktivcode-Implementierung anwenden |
| `sample-brain-skill-effectiveness` | Skill-EffektivitÃ¤t per Baseline-vs-Skill Verhaltensvergleich prÃ¼fen |
| `jMerta/coding-guidelines-verify` | QualitÃ¤tsprÃ¼fung vor Merge (scoped AGENTS) |

**Default:** Bei unklarem Task zuerst PrioritÃ¤t A prÃ¼fen.

Die lokale Reihenfolge ist verbindlich fuer Sample-Brain-spezifische Arbeit:

```text
Issue mit signifikantem Produktcode-Slice -> sample-brain-issue-to-session-plan -> sample-brain-test-first
Issue mit Docs-Slice -> sample-brain-issue-to-session-plan -> jMerta/docs-sync
Issue mit CI-/Tooling-Slice -> sample-brain-issue-to-session-plan -> jMerta/ci-fix und optional sample-brain-ci-debugger
Issue mit Dependency-Slice -> sample-brain-issue-to-session-plan -> jMerta/dependency-upgrader
Issue mit Workflow-Slice -> sample-brain-issue-to-session-plan -> bestehende workflow-spezifische Route
Issue mit Governance-Slice -> sample-brain-issue-to-session-plan -> bestehender Governance-/Docs-Weg
Issue mit unbekanntem Slice -> sample-brain-issue-to-session-plan -> planning_blocked
Unklarer Bug mit Produkt-/Verhaltensursache -> sample-brain-root-cause -> sample-brain-regression-gap -> sample-brain-test-first
Unklarer Bug mit CI-/Tooling-/Infrastruktur-Ursache -> sample-brain-root-cause -> jMerta/ci-fix und sample-brain-ci-debugger
Unklarer Bug mit Docs-/Contract-Ursache -> sample-brain-root-cause -> jMerta/docs-sync; sample-brain-test-first nur bei einer spÃ¤teren genehmigten Produktcode-Aenderung
Bekannter Defekt -> sample-brain-regression-gap -> sample-brain-test-first
Issue geplant + expliziter Jules-Dispatch -> sample-brain-jules-dispatch -> unabhÃ¤ngige lokale RÃ¼ckprÃ¼fung
```

`sample-brain-test-first` fixiert DOCS -> TESTS -> TEST FREEZE ->
IMPLEMENTATION -> CHECKS. Die lokalen Skills ergÃ¤nzen externe Workflow-Skills;
sie ersetzen diese nicht.

---

## PrioritÃ¤t B â€“ Security-Hardening (nur gezielt)

Nur bei explizitem Security-/CI-Audit-Auftrag â€“ **keine Auto-Ã„nderung** an Workflows oder Tools.

Priority B skills come from the external Anthropic-Cybersecurity-Skills package (not copied into this repo).

| Skill | Wann nutzen |
|-------|-------------|
| `securing-github-actions-workflows` | Workflow-HÃ¤rtung (Permissions, SHA-Pinning, Injection) |
| `implementing-secret-scanning-with-gitleaks` | Gitleaks-Setup/Tuning (ergÃ¤nzt bestehendes `gitleaks.yml`) |
| `integrating-sast-into-github-actions-pipeline` | SAST-Erweiterung (ergÃ¤nzt bestehendes `codeql.yml`) |
| `detecting-supply-chain-attacks-in-ci-cd` | CI/CD Supply-Chain-Audit |
| `implementing-semgrep-for-custom-sast-rules` | Custom SAST-Regeln (nur bei bewusster Semgrep-EinfÃ¼hrung) |

**Guardrail:** Empfehlungen dokumentieren; Workflow-/Tool-Ã„nderungen nur nach separatem, explizitem Auftrag.

---

## PrioritÃ¤t C â€“ Optional / spÃ¤ter

| Thema | Skill | Bedingung |
|-------|-------|-----------|
| Snyk SCA | `performing-sca-dependency-scanning-with-snyk` | Nur bei bewusster Snyk-EinfÃ¼hrung |
| DAST / OWASP ZAP | `integrating-dast-with-owasp-zap-in-pipeline` | Nur mit stabiler Staging-URL |
| DevSecOps-Meta | `implementing-devsecops-security-scanning` | Nur als Playbook, nicht als Default |

---

## Nicht sinnvoll (aktuell auÃŸerhalb des Scopes)

FÃ¼r `sample-brain` (lokal-first Python CLI, SQLite, Audio-Pipeline) derzeit **nicht** integrieren:

- Active Directory / Kerberos / Domain-Pentest
- Cloud-IAM / Multi-Cloud-Security (AWS/Azure/GCP)
- OT/ICS / SCADA / Purdue-Model
- Forensik / Memory-Dumps / Malware-RE
- Red-Team / C2 / Exploit-Frameworks
- Enterprise-SIEM/SOAR (Splunk, Sentinel, QRadar)

Bei Bedarf einzeln anfragen â€“ nicht bulk-kopieren.

---

## Scope-Compliance (dieses Dokument)

- Docs-only: keine CI-Workflow-Ã„nderungen
- Keine neuen Security-Tools einfÃ¼hren
- Keine Skills bulk ins Repo kopieren
- Keine produktiven CodeÃ¤nderungen durch diesen Plan
- `sample-brain-qml-test-run`
- `sample-brain-qml-test-run` – QML/Component-Tests ausführen, beobachten und Fehlerschichten klassifizieren (kein zweites Harness, keine Root-Cause-Vermutung)
| `sample-brain-qml-test-run` | QML/Component-pytest ausführen und Harness/Load/Behavior/Platform klassifizieren |
QML-/Component-Test-Ausführung -> sample-brain-qml-test-run -> bei Verhaltensversagen sample-brain-root-cause; bei Coverage-Lücke sample-brain-qml-component-test (wenn verfügbar); bei QML-Review-Bedarf sample-brain-qml-review (wenn verfügbar)
