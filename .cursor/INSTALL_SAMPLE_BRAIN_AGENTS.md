# Install SampleBrain Agents

Unzip this archive into the root of `jannekbuengener/sample-brain`.

Expected result:

```text
.cursor/agents/_SAMPLE_BRAIN_SUBAGENT_CONTRACT.md
.cursor/agents/sample-brain-control-orchestrator.md
...
```

After extraction, ask Cursor to reload agents if needed.

Recommended first prompt in Cursor:

```text
Read AGENTS.md, .cursor/rules/sample-brain-project.mdc, docs/SKILL_INTEGRATION_PLAN.md, .cursor/rules/skill-routing.mdc, and .cursor/agents/_SAMPLE_BRAIN_SUBAGENT_CONTRACT.md. Then report which SampleBrain subagent should handle a docs-only board/backlog sync and why. Do not edit files.
```
