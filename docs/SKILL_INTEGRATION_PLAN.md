# Skill Integration Plan – sample-brain

## Kurzbeschreibung

Skills geben Agenten in `sample-brain` wiederholbare Workflows statt Ad-hoc-Entscheidungen.
Sie beschleunigen Bugfix, CI-Triage, Dependency-Pflege, Doku-Sync und PR-Vorbereitung – ohne neue Tools oder CI-Änderungen einzuführen.

**Bestehende CI/DevSecOps-Basis (nur Referenz, nicht ändern):**

- `.github/workflows/ci-smoke.yml` – Python smoke
- `.github/workflows/codeql.yml` – CodeQL SAST
- `.github/workflows/dependency-review.yml` – Dependency Review
- `.github/workflows/gitleaks.yml` – Secret Scanning

Skill-Quellen (extern, nicht ins Repo kopieren; lokale Pfade nur in privater Agent-/IDE-Konfiguration):

- `jMerta` – täglicher Agenten-Workflow (Priorität A)
- `Anthropic-Cybersecurity-Skills` – Security-Hardening (Priorität B)

Routing-Details: [.cursor/rules/skill-routing.mdc](../.cursor/rules/skill-routing.mdc)

---

## Priorität A – Täglicher Agenten-Workflow

| Skill | Wann nutzen |
|-------|-------------|
| `jMerta/bug-triage` | Bug, Regression, fehlender Test/Build |
| `jMerta/ci-fix` | CI rot, fehlgeschlagene GitHub Actions |
| `jMerta/dependency-upgrader` | Dependency-Bump, CVE, `requirements.txt`-Update |
| `jMerta/docs-sync` | README/Docs passen nicht mehr zum Code |
| `jMerta/commit-work` | Commit vorbereiten, Message, Staging |
| `jMerta/create-pr` | PR öffnen, Beschreibung, Checks |
| `jMerta/plan-work` | Implementierung planen, Scope klären |
| `jMerta/coding-guidelines-verify` | Qualitätsprüfung vor Merge (scoped AGENTS) |

**Default:** Bei unklarem Task zuerst Priorität A prüfen.

---

## Priorität B – Security-Hardening (nur gezielt)

Nur bei explizitem Security-/CI-Audit-Auftrag – **keine Auto-Änderung** an Workflows oder Tools.

| Skill | Wann nutzen |
|-------|-------------|
| `securing-github-actions-workflows` | Workflow-Härtung (Permissions, SHA-Pinning, Injection) |
| `implementing-secret-scanning-with-gitleaks` | Gitleaks-Setup/Tuning (ergänzt bestehendes `gitleaks.yml`) |
| `integrating-sast-into-github-actions-pipeline` | SAST-Erweiterung (ergänzt bestehendes `codeql.yml`) |
| `detecting-supply-chain-attacks-in-ci-cd` | CI/CD Supply-Chain-Audit |
| `implementing-semgrep-for-custom-sast-rules` | Custom SAST-Regeln (nur bei bewusster Semgrep-Einführung) |

**Guardrail:** Empfehlungen dokumentieren; Workflow-/Tool-Änderungen nur nach separatem, explizitem Auftrag.

---

## Priorität C – Optional / später

| Thema | Skill | Bedingung |
|-------|-------|-----------|
| Snyk SCA | `performing-sca-dependency-scanning-with-snyk` | Nur bei bewusster Snyk-Einführung |
| DAST / OWASP ZAP | `integrating-dast-with-owasp-zap-in-pipeline` | Nur mit stabiler Staging-URL |
| DevSecOps-Meta | `implementing-devsecops-security-scanning` | Nur als Playbook, nicht als Default |

---

## Nicht sinnvoll (aktuell außerhalb des Scopes)

Für `sample-brain` (lokal-first Python CLI, SQLite, Audio-Pipeline) derzeit **nicht** integrieren:

- Active Directory / Kerberos / Domain-Pentest
- Cloud-IAM / Multi-Cloud-Security (AWS/Azure/GCP)
- OT/ICS / SCADA / Purdue-Model
- Forensik / Memory-Dumps / Malware-RE
- Red-Team / C2 / Exploit-Frameworks
- Enterprise-SIEM/SOAR (Splunk, Sentinel, QRadar)

Bei Bedarf einzeln anfragen – nicht bulk-kopieren.

---

## Scope-Compliance (dieses Dokument)

- Docs-only: keine CI-Workflow-Änderungen
- Keine neuen Security-Tools einführen
- Keine Skills bulk ins Repo kopieren
- Keine produktiven Codeänderungen durch diesen Plan
