"""Verify Sample Brain Cursor/Claude handoff host templates and optional pin.

Does not call the live database. Exits 0 when templates are present and, if
agent_brain is installed, the pin surface exposes handoff MCP entry metadata.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURSOR = ROOT / "docs" / "cursor_handoff_mcp.example.json"
CLAUDE = ROOT / "docs" / "claude_code_handoff_mcp.example.json"


def main() -> int:
    for path in (CURSOR, CLAUDE):
        payload = json.loads(path.read_text(encoding="utf-8"))
        server = payload["mcpServers"]["agent-brain-handoff"]
        if server.get("command") != "agent-brain-mcp-handoff":
            print(f"FAIL: {path.name} command mismatch", file=sys.stderr)
            return 1
        env = server.get("env") or {}
        if "AGENT_BRAIN_HANDOFF_TOKEN" not in env:
            print(f"FAIL: {path.name} missing token env", file=sys.stderr)
            return 1
    try:
        import agent_brain
        from agent_brain.mcp.host_configs import (
            claude_code_handoff_mcp_json,
            cursor_handoff_mcp_json,
        )
    except ImportError:
        print("OK: host templates valid (agent-brain not installed in this env)")
        return 0
    cursor = cursor_handoff_mcp_json()
    claude = claude_code_handoff_mcp_json()
    assert cursor["mcpServers"]["agent-brain-handoff"]["command"] == "agent-brain-mcp-handoff"
    assert claude["mcpServers"]["agent-brain-handoff"]["command"] == "agent-brain-mcp-handoff"
    print(f"OK: templates + agent-brain=={agent_brain.__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
