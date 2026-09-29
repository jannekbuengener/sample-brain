# SB.BOOTLOADER — Sample Brain Session Bootloader

## Purpose

Minimal session startup sequence for agents working on `jannekbuengener/sample-brain`. Prevents context loss, stale assumptions, and accidental use of private files.

## Mandatory Read Order (every session)

1. `AGENTS.md` — root scope, global rules, quality gates
2. `docs/CANON_INDEX.md` — authority/front-door map; classifies active canon, supporting contracts, durable snapshots and historical records
3. `.cursor/rules/sample-brain-project.mdc` — project guardrails
4. `.cursor/rules/skill-routing.mdc` — task-to-skill mapping (Priority A)
5. `docs/TARGET_ARCHITECTURE.md` — current and target architecture, including the locked Screen-1 renderer
6. `docs/PRODUCT_WORKFLOW_CANON.md` — Workbench-first producing path (Screen 1 → Live Kit → Channel Rack → Arrangement); overrides stale VST-first wording elsewhere
7. `docs/WORKBENCH_QML_PROOF_SPIKE.md` — Screen-1 QML shell and proof/evidence boundary
8. `README.md` — product one-liner, quickstart
9. `knowledge/CURRENT_STATUS.md` — current state, what works
10. `knowledge/ACTIVE_ROADMAP.md` — completed work, next priorities
11. `docs/PRODUCT_REQUIREMENTS.md` — product vision, MVP scope
12. `docs/SYSTEM_REQUIREMENTS.md` — functional/non-functional requirements
13. `docs/DATA_AND_ARTIFACT_POLICY.md` — committed vs untracked artifacts

For any Screen-1/UI task, the renderer gate above is mandatory before planning or
implementation: `SCREEN1_RENDERER = LOCK_PYSIDE6_QML`. New visual/product work
uses PySide6 / Qt Quick / QML; Tkinter remains legacy/fallback and behavioral
reference only. Reuse the Python Core/Controller/Audio/Catalog contracts and do
not reopen the renderer decision.

For Channel Rack / Screen-2 work, follow the build order in
`docs/PRODUCT_WORKFLOW_CANON.md` (ownership → pattern core → sequencer → UI).
Do not start Screen-2 UI before those docs gates.

## Task-Specific Context

| Domain | Documents |
|--------|-----------|
| Screen 1 / UI | `docs/TARGET_ARCHITECTURE.md`, `docs/WORKBENCH_QML_PROOF_SPIKE.md`, `docs/PRODUCT_WORKFLOW_CANON.md`, live #691 and the scoped child issue; #503/#579 are historical migration/governance evidence only |
| Channel Rack / Screen 2 | `docs/PRODUCT_WORKFLOW_CANON.md`, live #675/#678, `docs/SESSION_OWNERSHIP_CONTRACT.md`, `docs/PATTERN_CORE_CONTRACT.md`, `docs/SEQUENCER_PLAYBACK_CONTRACT.md` |
| EPIC 2 (Semantic Search) | `docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md`, ADR-0001–0005 |
| DAW / Export | `docs/DAW_INTEGRATION_SPEC.md`, `src/export_fl.py` (legacy/fallback; VST parked #469) |
| CI / Merge Governance | `docs/CI_DEGRADED_MODE.md`, `knowledge/governance/GOVERNANCE.md` |
| Repository Hygiene | `docs/ISSUE_BACKLOG.md`, `docs/DATA_AND_ARTIFACT_POLICY.md` |
| Agent / Role | `.cursor/agents/_SAMPLE_BRAIN_SUBAGENT_CONTRACT.md` |

## Forbidden Context

Never read these automatically: `knowledge/SHARED.WORKING.MEMORY.md`, `knowledge/logs/`, local SQLite DB (`data/catalog.db`), vector index files (`data/indexes/`), reports, venv, model caches, sample audio files, private skill packs.

## Startup Sequence

1. `git fetch origin --prune && git status -sb`
2. Confirm branch matches intended work target
3. Read mandatory documents (above)
4. For Screen-1/UI work, fetch live `main`, #691, and the relevant scoped child issue before planning or implementation; use closed #503/#579 only as historical evidence when the child explicitly references them
5. Classify task → load task-specific documents
6. Confirm no forbidden sources touched
7. Begin work

## Context Priority

| Priority | Category |
|----------|----------|
| 0 (live truth) | GitHub / Repo live execution evidence |
| 1 | Explicit current canon / supersession map (`docs/CANON_INDEX.md`, `docs/PRODUCT_WORKFLOW_CANON.md`) |
| 2 | Product Requirements |
| 3 | System Requirements |
| 4 | Target Architecture |
| 5 | Data and Artifact Policy |
| 6 | EPIC-specific specs |
| 7 | ADRs |
| 8 | Roadmap / Current Status |
| 9 | README |
| 10 | Agents docs |
| 11 | Issue Backlog |

See `docs/BOOTLOADER_AND_CONTEXT_STRATEGY.md` for full detail.


## Drift-Prevention Closeout

For documentation, canon, governance, status, routing or audit work, run before final packaging:

```bash
python tools/check_canon_drift.py
```

This check is deliberately narrow and deterministic. It verifies front-door paths, authority markers and a small set of audit-proven contradictions. It does not replace GitHub-live checks, task-specific tests or review.

If it finds an independent issue outside the current scope, record a scoped follow-up rather than silently broadening the change. Before declaring DONE, re-read live PR/check/issue state.
