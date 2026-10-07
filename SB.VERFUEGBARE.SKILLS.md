# SB.VERFUEGBARE.SKILLS — Verfügbare Skills für Sample Brain

Skills werden empfohlen, nicht automatisch ausgeführt.

**Machine routing authority:** `docs/operations/CAPABILITY_REGISTRY.json`
**Operations front door:** `docs/operations/README.md`
**Product canon (separate):** `docs/CANON_INDEX.md`

Human narrative (not machine authority): `docs/SKILL_INTEGRATION_PLAN.md`
Generated companion view: `.cursor/rules/skill-routing.mdc`

`SB.VERFUEGBARE.SKILLS_LISTE_2026-08-09.md` is **historical/frozen** and not active routing authority.

The routing matrix below is generated. Do not hand-edit inside the markers; run:
`python tools/generate_capability_views.py`

<!-- BEGIN GENERATED CAPABILITY ROUTING -->

## Routing-Matrix

| Situation | Capability |
|-----------|------------|
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
| Commit + PR zusammen | `jMerta/commit-work`, `jMerta/create-pr` |
| Qualitätsprüfung vor Merge | `jMerta/coding-guidelines-verify` |
| Klar abgegrenztes Issue explizit an Jules delegieren | `sample-brain-jules-dispatch` |
| Screen-1 UI/QML Visual Acceptance nach automatisierten Tests | `workflow-screen1-visual-acceptance` |
| Repository-/Worktree-Hygiene | `workflow-repository-hygiene`, `sample-brain-repository-auditor` |

## Security-Workflow-Audit (Priorität B, nur gezielt)

Nur bei **explizitem** Security-/CI-Audit-Auftrag. Keine Auto-Änderung ohne separaten Auftrag.

Priority B skills come from the external Anthropic-Cybersecurity-Skills package (not copied into this repo).

| Thema | Skill |
|-------|-------|
| GitHub Actions härten | `securing-github-actions-workflows` |
| Gitleaks erweitern/tunen | `implementing-secret-scanning-with-gitleaks` |
| SAST-Pipeline | `integrating-sast-into-github-actions-pipeline` |
| Supply-Chain in CI/CD | `detecting-supply-chain-attacks-in-ci-cd` |
| Custom Semgrep-Regeln | `implementing-semgrep-for-custom-sast-rules` |

## Default-Reihenfolge

1. Priorität A (täglicher Workflow)
2. Priorität B nur bei explizitem Security-Auftrag
3. Priorität C (Snyk, ZAP, DevSecOps-Meta) nicht als Default

Die lokale Reihenfolge ist verbindlich fuer Sample-Brain-spezifische Arbeit:

```text
Issue mit signifikantem Produktcode-Slice -> sample-brain-issue-to-session-plan -> sample-brain-test-first
Issue mit Docs-Slice -> sample-brain-issue-to-session-plan -> jMerta/docs-sync
Issue mit CI-/Tooling-Slice -> sample-brain-issue-to-session-plan -> jMerta/ci-fix und optional agent sample-brain-ci-debugger
Issue mit Dependency-Slice -> sample-brain-issue-to-session-plan -> jMerta/dependency-upgrader
Issue mit Workflow-Slice -> sample-brain-issue-to-session-plan -> bestehende workflow-spezifische Route
Issue mit Governance-Slice -> sample-brain-issue-to-session-plan -> bestehender Governance-/Docs-Weg
Issue mit unbekanntem Slice -> sample-brain-issue-to-session-plan -> planning_blocked
Unklarer Bug mit Produkt-/Verhaltensursache -> sample-brain-root-cause -> sample-brain-regression-gap -> sample-brain-test-first
Unklarer Bug mit CI-/Tooling-/Infrastruktur-Ursache -> sample-brain-root-cause -> jMerta/ci-fix und agent sample-brain-ci-debugger
Unklarer Bug mit Docs-/Contract-Ursache -> sample-brain-root-cause -> jMerta/docs-sync; sample-brain-test-first nur bei einer späteren genehmigten Produktcode-Aenderung
Bekannter Defekt -> sample-brain-regression-gap -> sample-brain-test-first
Issue geplant + expliziter Jules-Dispatch -> sample-brain-jules-dispatch -> unabhängige lokale Rückprüfung
Screen-1 UI/QML visual change -> automated validation -> visual fixture/runtime evidence -> AGENT VISUAL ACCEPTANCE -> VISUAL_ACCEPT_PASS|FAIL
```

## Screen-1 Visual Acceptance

For Screen-1 UI/QML visual work, automated tests are necessary but not sufficient. Agents own technical/runtime/visual acceptance using fixtures, screenshots, MCP/UI automation, plugins, skills, and reviewers. Owner does not run operative acceptance loops.

Sequence:

```text
automated validation
visual fixture/runtime evidence
AGENT VISUAL ACCEPTANCE
VISUAL_ACCEPT_PASS | VISUAL_ACCEPT_FAIL
```

Status values: `VISUAL_ACCEPT_PENDING`, `VISUAL_ACCEPT_PASS`, `VISUAL_ACCEPT_FAIL`

Agents own visual/runtime acceptance via fixtures, screenshots, MCP/UI automation, plugins, skills, and reviewers. `VISUAL_ACCEPT_PENDING` means agent evidence is incomplete — not an Owner wait state. Owner does not run operative acceptance loops. Automated tests alone are not sufficient.

## Repository Hygiene

Repository hygiene uses live repo/worktree state plus artifact policy and the repository auditor.

- live git worktree/branch state
- docs/DATA_AND_ARTIFACT_POLICY.md
- agent sample-brain-repository-auditor

Not an active hygiene authority: `docs/ISSUE_BACKLOG.md` (HISTORICAL_LEDGER only).

## Parked Tracks (do not auto-route)

These tracks are parked/HOLD. Do not auto-route or reactivate them.

- later Live #1088

Reactivation: `explicit_owner_go` only.

## Capability typing notes

- sample-brain-ci-debugger is an AGENT, not a skill.
- SB.VERFUEGBARE.SKILLS_LISTE_2026-08-09.md is historical/frozen and not active routing authority.
- Machine routing authority is docs/operations/CAPABILITY_REGISTRY.json.
- Agent contract authority is .cursor/agents/*.md; SB.AGENT.LIST.json is inventory/view only.
- Private ChatGPT MCP is chatgpt-operator-only and never a worker requirement.

Machine routing authority: `docs/operations/CAPABILITY_REGISTRY.json`. Do not hand-edit this generated block; regenerate via `python tools/generate_capability_views.py`.

<!-- END GENERATED CAPABILITY ROUTING -->
