# SB.BOOTLOADER — Sample Brain Session Bootloader

## Purpose

Minimal session startup sequence for agents working on `jannekbuengener/sample-brain`. Prevents context loss, stale assumptions, and accidental use of private files.

## Mandatory Read Order (every session)

1. `AGENTS.md` — root scope, global rules, quality gates
2. `.cursor/rules/sample-brain-project.mdc` — project guardrails
3. `.cursor/rules/skill-routing.mdc` — task-to-skill mapping (Priority A)
4. `README.md` — product one-liner, quickstart
5. `knowledge/CURRENT_STATUS.md` — current state, what works
6. `knowledge/ACTIVE_ROADMAP.md` — completed work, next priorities
7. `docs/PRODUCT_REQUIREMENTS.md` — product vision, MVP scope
8. `docs/SYSTEM_REQUIREMENTS.md` — functional/non-functional requirements
9. `docs/TARGET_ARCHITECTURE.md` — current and target architecture
10. `docs/DATA_AND_ARTIFACT_POLICY.md` — committed vs untracked artifacts

## Task-Specific Context

| Domain | Documents |
|--------|-----------|
| EPIC 2 (Semantic Search) | `docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md`, ADR-0001–0005 |
| DAW / Export | `docs/DAW_INTEGRATION_SPEC.md`, `src/export_fl.py` |
| CI / Merge Governance | `docs/CI_DEGRADED_MODE.md`, `knowledge/governance/GOVERNANCE.md` |
| Repository Hygiene | `docs/ISSUE_BACKLOG.md`, `docs/DATA_AND_ARTIFACT_POLICY.md` |
| Agent / Role | `.cursor/agents/_SAMPLE_BRAIN_SUBAGENT_CONTRACT.md` |

## Forbidden Context

Never read these automatically: `knowledge/SHARED.WORKING.MEMORY.md`, `knowledge/logs/`, local SQLite DB (`data/catalog.db`), vector index files (`data/indexes/`), reports, venv, model caches, sample audio files, private skill packs.

## Startup Sequence

1. `git fetch origin --prune && git status -sb`
2. Confirm branch matches intended work target
3. Read mandatory documents (above)
4. Classify task → load task-specific documents
5. Confirm no forbidden sources touched
6. Begin work

## Context Priority

| Priority | Category |
|----------|----------|
| 1 (highest) | Product Requirements |
| 2 | System Requirements |
| 3 | Target Architecture |
| 4 | Data and Artifact Policy |
| 5 | EPIC-specific specs |
| 6 | ADRs |
| 7 | Roadmap / Current Status |
| 8 | README |
| 9 | Agents docs |
| 10 | Issue Backlog |

See `docs/BOOTLOADER_AND_CONTEXT_STRATEGY.md` for full detail.
