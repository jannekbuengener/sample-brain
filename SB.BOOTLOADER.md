# SB.BOOTLOADER — Sample Brain Session Bootloader

## Purpose

Minimal session startup sequence for agents working on `jannekbuengener/sample-brain`. Prevents context loss, stale assumptions, and accidental use of private files.

## Mandatory Read Order (every session)

1. `AGENTS.md` — root scope, global rules, quality gates
2. `.cursor/rules/sample-brain-project.mdc` — project guardrails
3. `.cursor/rules/skill-routing.mdc` — task-to-skill mapping (Priority A)
4. `docs/TARGET_ARCHITECTURE.md` — current and target architecture, including the locked Screen-1 renderer
5. `docs/WORKBENCH_QML_PROOF_SPIKE.md` — Screen-1 QML shell and proof/evidence boundary
6. `README.md` — product one-liner, quickstart
7. `knowledge/CURRENT_STATUS.md` — current state, what works
8. `knowledge/ACTIVE_ROADMAP.md` — completed work, next priorities
9. `docs/PRODUCT_REQUIREMENTS.md` — product vision, MVP scope
10. `docs/SYSTEM_REQUIREMENTS.md` — functional/non-functional requirements
11. `docs/DATA_AND_ARTIFACT_POLICY.md` — committed vs untracked artifacts

For any Screen-1/UI task, the renderer gate above is mandatory before planning or
implementation: `SCREEN1_RENDERER = LOCK_PYSIDE6_QML`. New visual/product work
uses PySide6 / Qt Quick / QML; Tkinter remains legacy/fallback and behavioral
reference only. Reuse the Python Core/Controller/Audio/Catalog contracts and do
not reopen the renderer decision.

## Task-Specific Context

| Domain | Documents |
|--------|-----------|
| Screen 1 / UI | `docs/TARGET_ARCHITECTURE.md`, `docs/WORKBENCH_QML_PROOF_SPIKE.md`, live #579 / #503 and the scoped child issue |
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
4. For Screen-1/UI work, fetch live `main`, #579, #503, and the relevant scoped child issue before planning or implementation
5. Classify task → load task-specific documents
6. Confirm no forbidden sources touched
7. Begin work

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
