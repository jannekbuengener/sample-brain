# Sample Brain ↔ Agent Brain Shared Memory (G3a)

**Parent:** [agent-brain#96](https://github.com/jannekbuengener/agent-brain/issues/96) · **Child:** [#1364](https://github.com/jannekbuengener/sample-brain/issues/1364)

## Pin

```text
agent-brain==0.3.5
```

Verify after install: `python -c "import agent_brain; print(agent_brain.__version__)"` → `0.3.5`.

Optional extra: `pip install -e ".[agent-brain-handoff]"` (see `pyproject.toml`).

## Host wiring (required for functional proof)

| Host | Template |
| --- | --- |
| Cursor | [`docs/cursor_handoff_mcp.example.json`](../cursor_handoff_mcp.example.json) |
| Claude Code | [`docs/claude_code_handoff_mcp.example.json`](../claude_code_handoff_mcp.example.json) |

Copy into the host MCP config (local/gitignored). Set `AGENT_BRAIN_HANDOFF_TOKEN` from operator enroll (`agent-brain-handoff-auth enroll --consumer-id sample-brain --repository jannekbuengener/sample-brain`). Never commit tokens.

Tools: `shared_memory.handoff.append`, `shared_memory.handoff.recall`.

## Agent hooks (opt-in)

At task start / blocker / end, authorized agents may append a short handoff and later recall it in a **new session**. No Human-GO per ordinary note. Memory is untrusted context; GitHub/Repo Live wins. No audio/sample/secrets/PII in payloads.

## Smoke

```text
python tools/agent_brain_handoff_host_smoke.py
```

Fails closed if `agent-brain` is not installed or host snippets are missing.
