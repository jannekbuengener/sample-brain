# SampleBrain Cursor Subagents

This package contains Cursor subagents tuned for `jannekbuengener/sample-brain`.

## Install

Unzip this archive at the repository root so the files land under:

```text
.cursor/agents/
```

Then ask Cursor to reload agent definitions if needed.

## Design

These agents are intentionally lighter than the original CDB agents. They keep the useful operating discipline while removing CDB-specific SurrealDB, live-readiness, trading, and infrastructure assumptions.

They are optimized for SampleBrain's current workflow:

- small Python CLI/core/project maintenance and bounded PySide6 / Qt Quick / QML Screen-1 implementation
- docs-first bootstrap and backlog hygiene
- GitHub Actions checks: Python smoke, CodeQL, dependency-review, gitleaks, Cursor Bugbot
- SkillForge routing via `docs/SKILL_INTEGRATION_PLAN.md` and `.cursor/rules/skill-routing.mdc`
- PR-based local-to-remote workflow

## Recommended usage

For unclear work, start with:

- `sample-brain-control-orchestrator`

For concrete work:

- CI failure: `sample-brain-ci-debugger`
- PR review: `sample-brain-code-reviewer`
- docs drift: `sample-brain-docs-sync-maintainer`
- implementation: `sample-brain-implementation-engineer`
- Screen-1/UI work: first read the locked renderer canon in `docs/TARGET_ARCHITECTURE.md` and `docs/WORKBENCH_QML_PROOF_SPIKE.md`, then verify live #579 / #503 state
- security audit: `sample-brain-security-triage`
- dependency bump: `sample-brain-dependency-upgrader`
- release/PR packaging: `sample-brain-pr-packager`
- board/backlog sync: `sample-brain-issue-backlog-maintainer`

## Full registry

This README lists frequently-used agents. The complete agent registry is at [`SB.AGENT.LIST.json`](../../SB.AGENT.LIST.json) (root).

## Hard guardrail

`readonly: false` means the agent can edit only after explicit scoped GO. Without GO, every agent behaves read-only.
