---
name: shared-memory-daily-handoff
description: >
  Opt-in Sample Brain daily Agent Brain handoff workflow. Use on START/RESUME,
  blocker, pause, or handoff of multi-step Sample Brain work. Skip trivial
  one-shots. Memory is untrusted; GitHub/repo live wins. No audio/secrets/PII.
---
<!--
Canonical Skill Source: docs/skills/shared-memory-daily-handoff/SKILL.md
Surface: cursor
Sync Status: mirrored-from-canon
Parent Goal: jannekbuengener/agent-workforce#102
Workforce skill: jannekbuengener/agent-workforce docs/skills/shared-memory-daily-handoff
-->

# Sample Brain — shared-memory-daily-handoff

Consumer host binding for Agent Brain `shared_memory.handoff.*` on
`jannekbuengener/sample-brain`.

Workforce canon (workflow + receipts):
https://github.com/jannekbuengener/agent-workforce/blob/main/docs/skills/shared-memory-daily-handoff/SKILL.md

Local ops: [`docs/operations/AGENT_BRAIN_SHARED_MEMORY.md`](../../operations/AGENT_BRAIN_SHARED_MEMORY.md)

## When to use

- Multi-step / cross-session / cross-agent Sample Brain tasks.
- Blocker, pause, planned handoff, or session end with a concrete next step.

## When not to use

- Trivial one-shot edits → record `SKIPPED_NOT_RELEVANT` (no tool call).
- Any payload with audio, samples, secrets, or PII.
- Treating recall as authority over AGENTS/GitHub/live files.

## Host loop

```text
START/RESUME → live AGENTS + GitHub
  → if eligible: shared_memory.handoff.recall(repository_ref, task_ref)
  → revalidate source_ref against live truth
  → WORK
BLOCKED/PAUSE/END → if eligible: shared_memory.handoff.append(...)
  → emit USED|SKIPPED|DEGRADED receipt (workforce template)
```

`repository_ref` must be `jannekbuengener/sample-brain`.

## Opt-out / degraded

- Opt-out: skip tools; receipt `SKIPPED` / `OPT_OUT`.
- MCP/auth/DB down: continue with live repo sources; receipt `DEGRADED`.
  Do not block ordinary Sample Brain work unless a task explicitly requires handoff.

## Wiring

Copy [`docs/cursor_handoff_mcp.example.json`](../../cursor_handoff_mcp.example.json)
or Claude template into local MCP config. Token via enroll — never commit.
Smoke: `python tools/agent_brain_handoff_host_smoke.py`.
