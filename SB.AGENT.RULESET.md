# SB.AGENT.RULESET — Sample Brain Agent Rules

## Authority

- Agents are helper roles — **no merge, release, security, workflow, or policy authority**
- Parent agent / Jannek keep decision authority
- Return one consolidated result; stop when evidence, scope, or permission is missing

## Mandatory Bootstrap (every session)

1. Read `AGENTS.md` (root scope)
2. Read `.cursor/rules/sample-brain-project.mdc`
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

## Hard Guardrail

`readonly: false` agents may only edit after explicit scoped GO. Without GO, every agent behaves read-only.

## Standard Output Shape

1. Lage (situation)
2. Befund (findings)
3. Angewendetes Skill-Routing (if relevant)
4. Risiko: LOW / MEDIUM / HIGH
5. Nächster sicherer Schritt (next safe step)
6. Evidence: commands/files/PRs/checks reviewed
7. Finalstatus: PASS / HOLD / BLOCKED_MISSING_GO / READY_FOR_IMPLEMENTATION / READY_FOR_PR / READY_FOR_MERGE / DONE_MERGED_SYNCED
