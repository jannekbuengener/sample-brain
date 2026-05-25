# MCP Setup

This document prepares `sample-brain` for the local ChatGPT MCP workflow.

## Canonical local repository path

```text
D:\Dev\Workspaces\Repos\sample-brain
```

Use this checkout as the canonical local working copy for MCP and GitHub work.
Do not use `D:\Dev\Workspaces\sample-brain`.

## Intended MCP registration

Local MCP server repo:

```text
D:\Dev\Workspaces\Prompts\mcp\cdb-mcp-server
```

Planned MCP root key:

```text
sample_brain
```

Planned root path:

```text
D:/Dev/Workspaces/Repos/sample-brain
```

Planned repo-target:

```text
sample_brain
```

GitHub target:

```text
owner: jannekbuengener
repo: sample-brain
```

## Expected behavior after MCP server update

- `sample_brain` is available as a read root for `repo_list_dir`, `repo_read_file`, and `repo_search`
- if repo-target registration is enabled, `sample_brain` is also available where the MCP server uses repo-targets
- existing keys remain unchanged: `working`, `db`, `mcp`, `config`, `traumtaenzer`

## Local validation steps

Start the MCP server locally:

```powershell
cd D:\Dev\Workspaces\Prompts\mcp\cdb-mcp-server
npm run start
```

Then validate in-session with:

1. `mcp_preflight`
2. `repo_list_dir` with:

```json
{
  "name": "repo_list_dir",
  "arguments": {
    "repo": "sample_brain",
    "path": ""
  }
}
```

## Safety notes

- Do not index sample libraries as part of MCP setup.
- Do not commit generated artifacts such as `.venv`, `data/catalog.db`, FAISS indexes, or cache outputs.
- This setup step is only for local repository access through MCP, not for feature implementation.
