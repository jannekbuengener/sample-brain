# SB.VERFUEGBARE.SKILLS — Verfügbare Skills für Sample Brain

Routing-Referenz: `.cursor/rules/skill-routing.mdc` und `docs/SKILL_INTEGRATION_PLAN.md`.
Skills werden empfohlen, nicht automatisch ausgeführt.

## Priority A (täglicher Workflow)

| Situation | Skill |
|-----------|-------|
| Bug oder Fehlverhalten | `jMerta/bug-triage` |
| CI rot / fehlgeschlagene Checks | `jMerta/ci-fix` |
| Dependency-Bump / CVE | `jMerta/dependency-upgrader` |
| Doku driftet vom Code | `jMerta/docs-sync` |
| Implementierungsplanung | `jMerta/plan-work` |
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
