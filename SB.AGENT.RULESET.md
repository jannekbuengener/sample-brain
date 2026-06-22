# SB.AGENT.RULESET — Sample Brain Agent Rules

## Authority

- Agents are helper roles — **no merge, release, security, workflow, or policy authority**
- Parent agent / Jannek keep decision authority
- Return one consolidated result; stop when evidence, scope, or permission is missing

## Mandatory Bootstrap (every session)

1. Read `AGENTS.md` (root scope)
2. Read `.cursor/rules/sample-brain-project.mdc` (if present)
3. Read `SB.BOOTLOADER.md`
4. Read `.cursor/rules/skill-routing.mdc` when task involves skill selection
5. Fetch live repo/GitHub state before making board/PR/issue claims
6. GitHub live state > stale docs > screenshots > prior chat history

## Operating Mode

- **Read-only (default):** repo reads, git status/log/diff, gh read-only commands, planning, review, reports
- **Write requires explicit GO:** file edits, commits, pushes, PR create/update/ready/merge, issue comments/labels/close, workflow dispatch, branch deletion

## GitHub Mutation Rule

- Use `gh` CLI for GitHub mutations when available
- Do not silently replace `gh` mutations with GitHub API, MCP, connector, or IDE integration

## Repo Write Rules

- Work local → remote
- Do not push directly to `main`
- Use feature branch and PR flow
- Keep diffs minimal and tied to one task
- Never commit: private samples, runtime artifacts, local DB files, venvs, cache files, logs, local Cursor/MCP config
- Never expose secrets
- Do not change `.github/workflows/**`, dependencies, tools, or security config unless explicitly scoped

## Validation Defaults

```bash
python -m src.cli --help       # CLI smoke
sample-brain --help            # Entry point smoke
python -m pytest -q            # Core tests
```

- Docs-only diff → no runtime tests needed
- CLI behavior change → include CLI help or pytest evidence
- DB behavior change → use `SAMPLE_BRAIN_DB_PATH`, never commit runtime DB

## CI / Degraded Mode

- **`CI_GREEN` remains the default.** Required checks must be green for normal merge readiness.
- **Use `DEGRADED_CI_ACTIVE` only after live verification** that the failure is external infrastructure (billing lock, hosted-runner outage, unavailable self-hosted runner), not PR content.
- **`BILLING_LOCK_DOCS_ONLY_WAIVER` is narrow.** Recommend it only for small docs-only PRs with explicit GO, a PR-specific waiver comment, and no code, dependency, workflow, artifact, or secret risk.
- **Code, test, runtime, dependency, workflow, or security scope under CI outage is not docs-waivable.** Escalate to `LOCAL_VALIDATION_REQUIRED`, `HOLD_SECURITY_CHECK_UNAVAILABLE`, `HOLD_WORKFLOW_SCOPE`, or `HOLD_ARTIFACT_OR_SECRET_RISK` as appropriate.
- **Prefer `RUNNER_FALLBACK_REQUIRED` over repeated hosted-runner workarounds.** Runner and workflow changes stay separate scoped work and need explicit GO.
- **If GitHub blocks merge despite an approved waiver, stop at `HOLD_BRANCH_PROTECTION`.** Do not force, bypass, or direct-push.

## Hard Guardrail

`readonly: false` agents may only edit after explicit scoped GO. Without GO, every agent behaves read-only.

## Standard Output Shape

1. Lage (situation)
2. Befund (findings)
3. Angewendetes Skill-Routing (if relevant)
4. Risiko: LOW / MEDIUM / HIGH
5. Nächster sicherer Schritt (next safe step)
6. Evidence: commands/files/PRs/checks reviewed
7. Finalstatus: PASS / HOLD / BLOCKED_MISSING_GO / READY_FOR_IMPLEMENTATION / READY_FOR_PR / READY_FOR_MERGE / DONE_MERGED_SYNCED / CI_GREEN / DEGRADED_CI_ACTIVE / BILLING_LOCK_DOCS_ONLY_WAIVER / LOCAL_VALIDATION_REQUIRED / RUNNER_FALLBACK_REQUIRED / HOLD_BRANCH_PROTECTION / HOLD_SECURITY_CHECK_UNAVAILABLE / HOLD_WORKFLOW_SCOPE / HOLD_ARTIFACT_OR_SECRET_RISK
