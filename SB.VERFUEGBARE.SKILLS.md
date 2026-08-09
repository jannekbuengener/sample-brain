# SB.VERFUEGBARE.SKILLS — Verfügbare Skills für Sample Brain

Routing-Referenz: `.cursor/rules/skill-routing.mdc` und `docs/SKILL_INTEGRATION_PLAN.md`.
Skills werden empfohlen, nicht automatisch ausgeführt.

## Priority A (täglicher Workflow)

| Situation | Skill |
|-----------|-------|
| Neues Feature oder Issue planen | `sample-brain-issue-to-session-plan` |
| Unklare Fehlerursache | `sample-brain-root-cause` |
| Bekannter Defekt / fehlender Schutz | `sample-brain-regression-gap` |
| Bug oder Fehlverhalten | `jMerta/bug-triage` ergänzend |
| CI rot / fehlgeschlagene Checks | `jMerta/ci-fix` |
| Dependency-Bump / CVE | `jMerta/dependency-upgrader` |
| Doku driftet vom Code | `jMerta/docs-sync` |
| Implementierungsplanung | `jMerta/plan-work` |
| Wesentliche Produktivcode-Implementierung (vor Code) | `sample-brain-test-first` |
| Commit vorbereiten | `jMerta/commit-work` |
| PR vorbereiten / öffnen | `jMerta/create-pr` |
| Commit + PR zusammen | `jMerta/commit-work` + `jMerta/create-pr` |
| Qualitätsprüfung vor Merge | `jMerta/coding-guidelines-verify` |

## Priority B (nur bei explizitem Security-/CI-Audit-Auftrag)

| Thema | Skill |
|-------|-------|
| GitHub Actions härten | `securing-github-actions-workflows` |
| Gitleaks erweitern/tunen | `implementing-secret-scanning-with-gitleaks` |
| SAST-Pipeline | `integrating-sast-into-github-actions-pipeline` |
| Supply-Chain in CI/CD | `detecting-supply-chain-attacks-in-ci-cd` |
| Custom Semgrep-Regeln | `implementing-semgrep-for-custom-sast-rules` |

## Priority C (nicht als Default)

Snyk, ZAP, DevSecOps-Meta — nur bei explizitem Auftrag.

## Default-Reihenfolge

1. Priorität A
2. Priorität B (nur Security-Auftrag)
3. Priorität C (nicht als Default)

`sample-brain-test-first` ist der lokale Repo-Vertrag fuer die Reihenfolge
DOCS -> TESTS -> TEST FREEZE -> IMPLEMENTATION -> CHECKS. Die lokale Kette ist:

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
Unklarer Bug mit Docs-/Contract-Ursache -> sample-brain-root-cause -> jMerta/docs-sync; sample-brain-test-first nur bei einer späteren genehmigten Produktcode-Aenderung
Bekannter Defekt -> sample-brain-regression-gap -> sample-brain-test-first
```

Die lokalen Skills ergänzen, ersetzen aber nicht die externen Workflow-Skills.
