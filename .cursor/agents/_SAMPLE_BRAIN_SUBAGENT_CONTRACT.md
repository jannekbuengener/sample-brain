---
name: sample-brain-subagent-contract
description: Shared contract for SampleBrain Cursor subagents.
model: inherit
readonly: true
is_background: false
---

# SampleBrain Subagent Contract

Scope: all `.cursor/agents/sample-brain-*.md` subagents.
Repository target: `jannekbuengener/sample-brain`.

## Authority and limits

SampleBrain subagents are helper roles. They do not grant merge, release, security, workflow, or policy authority.

The parent agent and Jannek keep decision authority. Subagents return one consolidated result and must stop when evidence, scope, or permission is missing.

## Mandatory bootstrap

Before analysis, planning, implementation, review, or GitHub work:

1. Read `AGENTS.md`.
2. Read `.cursor/rules/sample-brain-project.mdc` if present.
3. Read `docs/SKILL_INTEGRATION_PLAN.md` and `.cursor/rules/skill-routing.mdc` when the task involves task-to-skill selection.
4. Fetch live repo/GitHub state before making board, PR, issue, or status claims.
5. Treat GitHub live state and current repo state as stronger than stale docs, old status files, screenshots, or prior chat history.

If a required file is missing, report it exactly and continue only with an explicit limitation.

## Default operating mode

Default is read-only until Jannek gives a precise GO for the scoped action.

Read-only discovery is allowed:

- repo reads
- `git status`, `git diff`, `git log`, `git rev-parse`
- `gh pr view/list/checks`, `gh issue view/list`, read-only check inspection
- planning, review, reports, and patch proposals

Writes require explicit GO:

- file edits
- commits
- pushes
- PR create/update/ready/merge
- issue comments/labels/closing
- workflow dispatch or rerun
- dependency/tooling changes
- branch deletion

## GitHub mutation rule

Use `gh` CLI for GitHub mutations when available. Do not silently replace `gh` mutations with GitHub API, MCP, connector, or IDE integration.

Allowed without GO: `gh view/list/checks` style read actions.

Requires GO: PR creation/update/ready/merge, issue comments/labels/close, review submissions, workflow reruns, branch deletion.

## Repo write rules

- Work local to remote.
- Do not push directly to `main`.
- Use a feature branch and PR flow.
- Keep diffs minimal and tied to one task.
- Do not commit private samples, runtime artifacts, local DB files, venvs, cache files, logs, or local Cursor/MCP config.
- Do not expose secrets. If a file may contain secrets, classify without printing values.
- Do not change `.github/workflows/**`, dependencies, tools, or security config unless the task explicitly scopes it.
- Do not introduce new scanners, services, frameworks, or external accounts without explicit GO.

## SampleBrain validation defaults

Use the narrowest useful validation. Common commands:

```bash
python -m src.cli --help
sample-brain --help
python -m pytest -q
```

When a task touches docs only, do not pretend runtime tests prove the docs. Report docs-only scope and whether CI is expected to be unaffected.

When a task touches CLI behavior, include CLI help or focused pytest evidence.

When a task touches runtime DB behavior, use `SAMPLE_BRAIN_DB_PATH` deliberately and avoid committing runtime DB artifacts.

## Skill-routing rule

Use `.cursor/rules/skill-routing.mdc` and `docs/SKILL_INTEGRATION_PLAN.md` for task-to-skill mapping.

Default Priority A routing:

- Bug or regression → `jMerta/bug-triage`
- CI failure → `jMerta/ci-fix`
- Dependency bump → `jMerta/dependency-upgrader`
- Docs drift → `jMerta/docs-sync`
- Planning → `jMerta/plan-work`
- Commit/PR packaging → `jMerta/commit-work` + `jMerta/create-pr`
- Pre-merge quality check → `jMerta/coding-guidelines-verify`

Priority B security skills are recommendation and audit guidance only. They do not authorize automatic security implementation or workflow changes.

Priority C is not default.

## Standard output shape

Return:

1. Lage
2. Befund
3. Angewendetes Skill-Routing, falls relevant
4. Risiko: LOW / MEDIUM / HIGH
5. Nächster sicherer Schritt
6. Evidence: commands/files/PRs/checks reviewed
7. Finalstatus

Use final statuses such as:

- `PASS`
- `HOLD`
- `BLOCKED_MISSING_GO`
- `READY_FOR_IMPLEMENTATION`
- `READY_FOR_PR`
- `READY_FOR_MERGE`
- `DONE_MERGED_SYNCED`
