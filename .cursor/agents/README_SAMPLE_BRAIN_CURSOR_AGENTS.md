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

- small Python CLI/project maintenance
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
- security audit: `sample-brain-security-triage`
- dependency bump: `sample-brain-dependency-upgrader`
- release/PR packaging: `sample-brain-pr-packager`
- board/backlog sync: `sample-brain-issue-backlog-maintainer`

## Hard guardrail

`readonly: false` means the agent can edit only after explicit scoped GO. Without GO, every agent behaves read-only.
