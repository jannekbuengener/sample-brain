# Bootloader and Context Strategy — Sample Brain

## 1. Purpose

This document describes the session startup process for work on Sample Brain. It defines which documents must be loaded before architecture, documentation, or code work begins. It prevents context loss, wrong assumptions, and accidental use of private files.

## 2. Bootloader Goals

- Fast entry into the current project state
- Consistent decisions across sessions
- Clear separation of public repo context and private working memory
- Protection against artifact / data leaks
- Foundation for later Sample-Brain-specific skills

## 3. Mandatory Context Documents

The following documents must be read at the start of every new session before any architecture, documentation, or implementation work begins.

| Document | When to read | Purpose |
|----------|-------------|---------|
| `README.md` | Every session | Product one-liner, MVP features, quickstart, doc index |
| `docs/PRODUCT_REQUIREMENTS.md` | Every session | Product vision, target audience, MVP scope, non-goals, product principles |
| `docs/SYSTEM_REQUIREMENTS.md` | Every session | Functional and non-functional requirements, system constraints, data model, testing strategy |
| `docs/TARGET_ARCHITECTURE.md` | Every session | Current and target architecture, component boundaries, dependency direction, local-first rules |
| `docs/DATA_AND_ARTIFACT_POLICY.md` | Every session | What is committed vs untracked, gitignore reference, enforcement checklist |
| `knowledge/ACTIVE_ROADMAP.md` | Every session | Completed work, current focus, next priorities, future documentation strands |
| `knowledge/CURRENT_STATUS.md` | Every session | Branch state, what works, what exists on main, what is not done, next steps |
| `agents/AGENTS.md` | Every session | Shared charter: agent roles, rule against secrets and private data |

## 4. Task-Specific Context Documents

These documents are loaded depending on the task category.

### EPIC 2 — Semantic Search

- `docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md` — embedding contracts, index design, search pipeline, acceptance criteria
- `knowledge/roadmap/adr/ADR-0001-embedding-model-strategy.md` — CLAP selection rationale, backend design
- `knowledge/roadmap/adr/ADR-0002-local-vector-index-strategy.md` — FAISS selection, index lifecycle
- `knowledge/roadmap/adr/ADR-0003-embedding-db-schema-design.md` — SQLite schema for embeddings, BLOB rationale

### DAW / Export

- `docs/DAW_INTEGRATION_SPEC.md` — FL Studio tag format, Ableton/Reaper research, export architecture
- `src/export_fl.py` — only when working on export code

### MCP / Repo Operations

- `docs/MCP_SETUP.md` — canonical paths, MCP root key, validation commands, safety notes

### Agent / Role Context

- `agents/AGENTS.md` — shared charter (always read, see Section 3)
- `agents/CLAUDE.md` — template role: governance, decision moderation
- `agents/CODEX.md` — template role: deterministic execution
- `agents/GEMINI.md` — template role: review, audit, drift detection

### Repository Hygiene

- `docs/ISSUE_BACKLOG.md` — planned work across all epics, status of open items
- `docs/DATA_AND_ARTIFACT_POLICY.md` — enforcement checklist before any commit

## 5. Forbidden Context Sources

The following sources must never be read automatically during session startup. They contain private, environment-specific, or generated data.

| Source | Reason |
|--------|--------|
| `knowledge/SHARED.WORKING.MEMORY.md` | Private working memory — not part of the repo contract |
| `knowledge/logs/` | Agent session logs — runtime state, not project artifacts |
| Local SQLite database (`data/catalog.db`) | Generated artifact — environment-specific, untracked |
| FAISS index files (`data/indexes/`) | Generated artifact — rebuildable cache, untracked |
| Reports (`reports/`) | Generated artifact — untracked |
| `.venv/` or any virtual environment | Local setup state — never read as context |
| Model cache (`~/.cache/huggingface/`, `data/models/`) | Downloaded weights — system-global, outside repo contract |
| Sample audio files (`.wav`, `.aiff`, `.flac`, `.mp3`) | Source data — never read as project context |
| Private prompt collections or skill packs outside the repo | Not part of the repo — loaded only with explicit approval |

**Rule:** If a source is not listed in Section 3 or Section 4, it must not be read without explicit justification.

## 6. Session Startup Sequence

1. `git status --short --branch` — verify branch and working tree state
2. Check current branch — confirm it matches the intended work target
3. Read mandatory context documents (Section 3)
4. Classify the task:
   - Documentation
   - Architecture / Design
   - EPIC 2 — Semantic Search
   - DAW / Export
   - Repository Hygiene
   - Skill / Bootloader
5. Load task-specific documents (Section 4)
6. Check risks:
   - No private files opened
   - No generated artifacts touched
   - Branch / PR context is understood
   - Code vs documentation-only distinction is clear
7. Begin work

## 7. Context Priority Order

If documents contradict each other, the following priority applies:

| Priority | Document category | Example |
|----------|------------------|---------|
| 1 (highest) | Product Requirements | `docs/PRODUCT_REQUIREMENTS.md` |
| 2 | System Requirements | `docs/SYSTEM_REQUIREMENTS.md` |
| 3 | Target Architecture | `docs/TARGET_ARCHITECTURE.md` |
| 4 | Data and Artifact Policy | `docs/DATA_AND_ARTIFACT_POLICY.md` |
| 5 | EPIC-specific specs | `docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md` |
| 6 | ADRs | `knowledge/roadmap/adr/ADR-*.md` |
| 7 | Roadmap / Current Status | `knowledge/ACTIVE_ROADMAP.md`, `knowledge/CURRENT_STATUS.md` |
| 8 | README | `README.md` |
| 9 | Agents docs | `agents/AGENTS.md`, `agents/CLAUDE.md`, `agents/CODEX.md`, `agents/GEMINI.md` |
| 10 | Issue Backlog | `docs/ISSUE_BACKLOG.md` |

**Rule:** Requirements, architecture, and policy always take precedence over roadmap, backlog, and agent role descriptions.

## 8. Role of AGENTS.md

- AGENTS.md contains working rules for AI agents operating on this repository.
- It does not replace product, system, or architecture documentation.
- It references this bootloader document for session startup procedure.
- It must never contain private prompts, working memory content, or personal data.
- Agent roles (Claude, Codex, Gemini) are templates — they define governance boundaries, not task-specific instructions.

## 9. MCP Role

- MCP provides clean read-only repo access for audits and context loading.
- Repo target: `sample_brain` (root key in the local MCP server).
- Write actions (git, file creation beyond docs) require explicit approval.
- `git add .` is forbidden — only explicitly staged files are committed.
- Private files (Section 5) must never be read through MCP tools.
- Generated artifacts (DB, indexes, models, caches) must not be opened or read through MCP; metadata/status checks may be allowed when needed for hygiene audits.

## 10. Bootloader Output

Every session should report after bootloader execution:

- Detected branch and working tree status
- List of loaded documents (mandatory + task-specific)
- Relevant constraints identified (no push, documentation-only, etc.)
- Confirmation that forbidden sources were not read
- Recommended next action

## 11. Future Skill Integration

Sample-Brain-specific skills should be built against these bootloader rules:

- Skills must not hardcode private paths.
- Skills must know which task-specific context documents are relevant for their operation.
- Skill selection must be based on repo context, not on blind import.
- Skills must respect the forbidden context sources defined in Section 5.

Skill candidates to evaluate later (not analyzed here):

- `jMerta`
- `skillforge`
- `Anthropic-Cybersecurity-Skills`
- `cdb-docs-ops`
- `cdb-ci-cd-guard`
- `gh-address-comments`
- `cdb-session-start`
- `cdb-session-close`
- `cdb-issue-to-session-plan`
- `cdb-drift-reconcile`

## 12. Non-Goals

- Not a replacement for requirements documentation
- Not a private working memory store
- Not a prompt dump or tool log
- Not a skill installer or package manager
- Not an automatic reader of external skill packs
- Not a GitHub or PR governance document

## 13. Related Documents

- `README.md`
- `agents/AGENTS.md`
- `docs/PRODUCT_REQUIREMENTS.md`
- `docs/SYSTEM_REQUIREMENTS.md`
- `docs/TARGET_ARCHITECTURE.md`
- `docs/DATA_AND_ARTIFACT_POLICY.md`
- `docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md`
- `docs/DAW_INTEGRATION_SPEC.md`
- `docs/MCP_SETUP.md`
- `knowledge/ACTIVE_ROADMAP.md`
- `knowledge/CURRENT_STATUS.md`
