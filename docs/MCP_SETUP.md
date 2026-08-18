# MCP setup (sample-brain)

This document configures **local AI tooling** for the `sample-brain` repository:
**Cursor** and **Codex** use the same read-only **`cdb_context`** stdio MCP as
**Claire de Binare (CDB)**. ChatGPT repo reads use the separate **`gpt-mcp-server`**.
This repo only holds client config and docs; the server implementations live outside
`sample-brain`.

## Architecture

```text
sample-brain (this repo)
  ├── .codex/config.toml          → Codex: spawns cdb_context stdio
  ├── .cursor/mcp.json            → Cursor: local copy (gitignored)
  └── docs/cursor_mcp.example.json
              │
              │  command + cwd → CDB repo root
              ▼
Claire_de_Binare (canon server)
  └── python -m tools.mcp.server   (stdio, read-only context tools)

ChatGPT
  └── gpt-mcp-server               (repo read/search across registered roots)
          └── sample_brain → D:/Dev/Workspaces/Repos/sample-brain
```

| Layer | Role |
|-------|------|
| **CDB** | Canon for `tools.mcp.server`, SurrealDB context bridge, tool definitions |
| **sample-brain** | Cross-repo client config; no MCP server code in this repo |
| **`gpt-mcp-server`** | Separate ChatGPT/repo-read workflow with registered `sample_brain` root; not `cdb_context` |

### Why stdio?

- **Process boundary**: Cursor/Codex spawn one Python process; no extra HTTP port or tokens in repo config.
- **Same as CDB**: Matches `claire-de-binare.mcp.json` and CDB `.cursor/mcp.json` (relative `command` inside CDB; absolute `command` + `cwd` when called from here).
- **Fail-closed**: If the server does not start (wrong `cwd`, missing venv), tools are absent; agents must not claim DB-backed context without tool evidence.

## Windows-local canonical paths (team convention)

These paths are **documented for this workspace layout only**. They are not portable
to Linux CI or other machines. Non-Windows setups must use the example templates below.

| Symbol | Path |
|--------|------|
| **sample-brain root** | `D:\Dev\Workspaces\Repos\sample-brain` |
| **CDB root** (`cwd` for `cdb_context`) | `D:\Dev\Workspaces\Repos\Claire_de_Binare` |
| **CDB Python (Windows venv)** | `D:\Dev\Workspaces\Repos\Claire_de_Binare\.venv\Scripts\python.exe` |
| **ChatGPT MCP server** | `D:\Dev\Workspaces\Prompts\mcp\gpt-mcp-server` |

Do **not** use `D:\Dev\Workspaces\sample-brain` (wrong tree).

## Versioned vs local-only files

| File | In git? | Notes |
|------|---------|--------|
| `docs/MCP_SETUP.md` | Yes | This guide |
| `docs/codex_config.example.toml` | Yes | Portable template (`CDB_REPO_ROOT`) |
| `docs/cursor_mcp.example.json` | Yes | Portable Cursor template |
| `.codex/config.toml` | Yes | Project Codex standard (Windows paths above; no secrets) |
| `.cursor/mcp.json` | **No** | Copy from `docs/cursor_mcp.example.json`; listed in `.gitignore` |
| CDB `claire-de-binare.mcp.json` | N/A (other repo) | Read-only reference when editing CDB |

**Redaction boundary:** No passwords, API keys, Redis secrets, host-specific DSNs, or
cert material in committed files. Optional Redis MCP in CDB canon uses
`REDIS_PASSWORD` placeholders only in the **CDB** repo—not wired in sample-brain
`cdb_context` setup.

## Cursor setup

1. Ensure CDB venv exists and MCP bridge works (validation below).
2. Copy the example and set your CDB checkout path (forward slashes in JSON):

   ```powershell
   Copy-Item docs\cursor_mcp.example.json .cursor\mcp.json
   # Edit .cursor\mcp.json: replace CDB_REPO_ROOT with your Claire_de_Binare path
   ```

3. Restart Cursor or reload MCP servers for this workspace.

Example entry (after replacing `CDB_REPO_ROOT`):

```json
{
  "mcpServers": {
    "cdb_context": {
      "enabled": true,
      "command": "D:/Dev/Workspaces/Repos/Claire_de_Binare/.venv/Scripts/python.exe",
      "args": ["-m", "tools.mcp.server"],
      "cwd": "D:/Dev/Workspaces/Repos/Claire_de_Binare",
      "type": "stdio"
    }
  }
}
```

## Codex setup

Codex merges **global** `~/.codex/config.toml` with **project** `.codex/config.toml`
in this repo.

1. Use the committed `.codex/config.toml` when your CDB path matches the Windows table above.
2. Otherwise copy `docs/codex_config.example.toml` → `.codex/config.toml` and set `CDB_REPO_ROOT`.
3. Restart Codex or reconnect MCP so stdio reloads.

Reference (CDB template): `Claire_de_Binare/agents/templates/codex_mcp_config.md`.

## `cdb_context` vs `gpt-mcp-server`

| | **`cdb_context` (stdio)** | **`gpt-mcp-server`** |
|--|---------------------------|----------------------|
| **Purpose** | CDB Context Intelligence (`context.briefing`, readiness, etc.) | ChatGPT repo read/search across registered roots |
| **Server location** | CDB `tools.mcp.server` | `D:\Dev\Workspaces\Prompts\mcp\gpt-mcp-server` |
| **sample-brain key** | N/A (cross-repo spawn) | `sample_brain` → this repo path |
| **Config in sample-brain** | `.codex/config.toml`, `.cursor/mcp.json` | Documented only; no server code here |

Both can coexist; they do not replace each other.

## Validation

### Syntax (sample-brain repo root)

```powershell
cd D:\Dev\Workspaces\Repos\sample-brain
python -c "import json; json.load(open('docs/cursor_mcp.example.json')); print('cursor example OK')"
python -c "import tomllib; tomllib.load(open('.codex/config.toml','rb')); print('codex config OK')"
python -c "import tomllib; tomllib.load(open('docs/codex_config.example.toml','rb')); print('codex example OK')"
```

### CDB MCP bridge (from CDB checkout)

```powershell
cd D:\Dev\Workspaces\Repos\Claire_de_Binare
.\.venv\Scripts\python.exe -c "from tools.mcp.context_bridge import create_bridge; b=create_bridge(); print(len(b.list_tools()))"
pwsh -File agents/templates/onboarding_mcp_setup.ps1
```

Expect **26** tools from the bridge smoke line when SurrealDB/context prerequisites are satisfied.

### sample-brain CI

GitHub Actions (`ci-smoke.yml`) does not start MCP; it only runs `py_compile` and CLI `--help`.

## ChatGPT / `gpt-mcp-server` registration

The active ChatGPT MCP server is the external repository `jannekbuengener/gpt-mcp-server`.
The live contract verified for issue #353 is:

- server version: `1.2.0`
- server build: `d76d64725e82`
- MCP root key: `sample_brain`
- root path: `D:/Dev/Workspaces/Repos/sample-brain`
- GitHub target: `jannekbuengener/sample-brain`
- expected preflight result: `sample-brain-read-smoke: PASS` and `root:sample_brain: OK`

Local MCP server repo:

```text
D:\Dev\Workspaces\Prompts\mcp\gpt-mcp-server
```

```powershell
cd D:\Dev\Workspaces\Prompts\mcp\gpt-mcp-server
npm run start
```

In a Developer-MCP-capable ChatGPT session, run `mcp_preflight` first. A valid
Sample-Brain preflight must show the server version/build, `root:sample_brain: OK`,
and `sample-brain-read-smoke: PASS`. Then run `repo_list_dir` with
`"repo": "sample_brain"`; the root read must expose at least `SB.BOOTLOADER.md`,
`src`, and `tests`.

### Failure classes and fallback

- **Server unavailable / health failure**: treat the local MCP as unavailable; do not claim local reads.
- **`root:sample_brain` missing or wrong**: root-registration failure; fix server/root configuration before claiming Sample-Brain access.
- **`FORBIDDEN: This conversation does not support developer MCPs`**: ChatGPT host/session capability blocker, not a Sample-Brain or server-code failure.
- **Repo read fails after a healthy preflight**: treat as repo/root access failure; do not fake-green from preflight metadata alone.
- **GitHub connector fallback**: may inspect and modify GitHub-visible repo state, but does not prove local tests, private-audio pilots, Windows device behavior, or local filesystem state.

## Safety notes

- Do not index sample libraries as part of MCP setup.
- Do not commit `.venv`, `data/catalog.db`, FAISS indexes, or cache outputs.
- Agents without `cdb_context` in the tool list must report `brain_source=repo-only` and must not invent DB-backed memory claims.
- GitHub-only sessions must explicitly distinguish remote evidence from local MCP evidence.
- CDB live-readiness and trading gates are unchanged; this doc is tooling only.

## Related docs

- Root agent rules: `AGENTS.md` (no machine-local paths in committed code; MCP client paths are documented exceptions in this file).
- CDB canon MCP: `Claire_de_Binare/claire-de-binare.mcp.json` (read-only reference).
