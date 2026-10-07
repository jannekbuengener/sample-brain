# SB.BOOTLOADER — Sample Brain Session Bootloader

## Purpose

Minimal session startup sequence for agents working on `jannekbuengener/sample-brain`. Prevents context loss, stale assumptions, and accidental use of private files.

## Mandatory Read Order (every session)

1. `AGENTS.md` — root scope, global rules, quality gates
2. `docs/CANON_INDEX.md` — authority/front-door map; classifies active canon, supporting contracts, durable snapshots and historical records
3. `.cursor/rules/sample-brain-project.mdc` — project guardrails
4. `.cursor/rules/skill-routing.mdc` — task-to-skill mapping (generated from `docs/operations/CAPABILITY_REGISTRY.json`)
4b. `docs/operations/README.md` — operations/capability front door (not product canon)
5. `docs/TARGET_ARCHITECTURE.md` — current and target architecture, including the locked Workbench QML renderer
6. `docs/PRODUCT_WORKFLOW_CANON.md` — Workbench-first producing path Edit → Arrangement → later Live (#1075/#1076); overrides stale VST-first, multi-screen, and exclusive Single-Workspace-only navigation wording elsewhere
6b. `docs/WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md` — supporting progressive-disclosure / Edit geometry evidence (#905 historical; exclusive nav thesis superseded by #1075/#1076)
7. `docs/WORKBENCH_QML_PROOF_SPIKE.md` — Workbench QML shell and proof/evidence boundary (`LOCK_PYSIDE6_QML`)
8. `README.md` — product one-liner, quickstart
9. `knowledge/CURRENT_STATUS.md` — current state, what works
10. `knowledge/ACTIVE_ROADMAP.md` — completed work, next priorities
11. `docs/PRODUCT_REQUIREMENTS.md` — product vision, MVP scope
12. `docs/SYSTEM_REQUIREMENTS.md` — functional/non-functional requirements
13. `docs/DATA_AND_ARTIFACT_POLICY.md` — committed vs untracked artifacts

For any Workbench UI / visual task, the renderer gate above is mandatory before planning or
implementation: `SCREEN1_RENDERER = LOCK_PYSIDE6_QML` (historical lock name). New visual/product work
uses PySide6 / Qt Quick / QML; Tkinter remains legacy/fallback and behavioral
reference only. Reuse the Python Core/Controller/Audio/Catalog contracts and do
not reopen the renderer decision. Current product navigation is Edit → Arrangement → later Live
([#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076)), not Screen 1/2/3 pages and not exclusive Single-Workspace-only modes.

For Channel Rack / Pattern domain work, follow the build-order evidence in
`docs/PRODUCT_WORKFLOW_CANON.md` (ownership → pattern core → sequencer → UI).
Closed [#908](https://github.com/jannekbuengener/sample-brain/issues/908) is historical Rack projection evidence; do not invent a second musical state owner.

## Task-Specific Context

| Domain | Documents |
|--------|-----------|
| Product nav / Workbench UI | `docs/PRODUCT_WORKFLOW_CANON.md`, `docs/PROGRAM_CHROME_CONTRACT.md`, `docs/WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md` (Edit geometry), `docs/TARGET_ARCHITECTURE.md`, `docs/WORKBENCH_QML_PROOF_SPIKE.md`, live `main` + [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076); closed/historical #691/#503/#579/#905 are delivery evidence only |
| Channel Rack / Pattern domain | `docs/PRODUCT_WORKFLOW_CANON.md`, closed #675/#678 (historical evidence), `docs/SESSION_OWNERSHIP_CONTRACT.md`, `docs/PATTERN_CORE_CONTRACT.md`, `docs/SEQUENCER_PLAYBACK_CONTRACT.md`; product placement in Arrangement workflow |
| Session / audio-focus audit | [#907](https://github.com/jannekbuengener/sample-brain/issues/907), `docs/SESSION_OWNERSHIP_CONTRACT.md` (runtime seams are not product-page authority) |
| Arrangement | [#679](https://github.com/jannekbuengener/sample-brain/issues/679) — **ACTIVE** Arrangement owner; later Live [#1088](https://github.com/jannekbuengener/sample-brain/issues/1088) |
| EPIC 2 (Semantic Search) | `docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md`, ADR-0001–0005 |
| DAW / Export | `docs/DAW_INTEGRATION_SPEC.md`, `src/export_fl.py` (legacy/fallback; VST parked #469) |
| CI / Merge Governance | `docs/CI_DEGRADED_MODE.md`, `docs/MERGE_REVIEW_FEEDBACK_GATE.md`, `docs/BRANCH_PROTECTION.md`, `knowledge/governance/GOVERNANCE.md` |
| Repository Hygiene | live worktree/branch state, `docs/DATA_AND_ARTIFACT_POLICY.md`, agent `sample-brain-repository-auditor`; ops front door `docs/operations/README.md` |
| Operations / capabilities | `docs/operations/README.md`, `docs/operations/CAPABILITY_REGISTRY.json` |
| Agent / Role | `.cursor/agents/_SAMPLE_BRAIN_SUBAGENT_CONTRACT.md` |

## Forbidden Context

Never read these automatically: `knowledge/SHARED.WORKING.MEMORY.md`, `knowledge/logs/`, local SQLite DB (`data/catalog.db`), vector index files (`data/indexes/`), reports, venv, model caches, sample audio files, private skill packs.

## Startup Sequence

1. `git fetch origin --prune && git status -sb`
2. Confirm branch matches intended work target
3. Read mandatory documents (above)
4. For Workbench UI / Screen-1 visual work, fetch live `main` and open a new scoped issue under [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#679](https://github.com/jannekbuengener/sample-brain/issues/679) / [#1069](https://github.com/jannekbuengener/sample-brain/issues/1069) before planning or implementation; treat closed/historical #691/#503/#579/#905 as delivered authority only
5. Classify task → load task-specific documents
6. Confirm no forbidden sources touched
7. Begin work

## Context Priority

| Priority | Category |
|----------|----------|
| 0 (live truth) | GitHub / Repo live execution evidence |
| 1 | Explicit current canon / supersession map (`docs/CANON_INDEX.md`, `docs/PRODUCT_WORKFLOW_CANON.md`, `docs/WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md`) |
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
