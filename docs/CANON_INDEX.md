# Sample Brain Canon Index

**Status:** ACTIVE FRONT DOOR  
**Purpose:** Small authority map for agents and maintainers. This file points to truth; it does not duplicate the underlying contracts.

## Truth order

1. **GitHub live / Repo live** — execution state, branches, PRs, issue state, checks, current code.
2. **ACTIVE_CANON** — current product, system, architecture and policy decisions.
3. **ACTIVE_SUPPORTING** — subsystem contracts that refine an active canon.
4. **DURABLE_SNAPSHOT** — orientation only; never a replacement for live state.
5. **HISTORICAL_LEDGER / SUPERSEDED_RECORD** — evidence only, never current execution authority.

A closed issue, old benchmark or historical spec can remain useful evidence without becoming current canon again.

## Active canon

| Topic | Authority | Class | Notes |
|---|---|---|---|
| Product producing flow | `docs/PRODUCT_WORKFLOW_CANON.md` | ACTIVE_CANON | Workbench-first; Screen 1 → Live Kit → Channel Rack → later Arrangement. VST3 remains parked. |
| Product requirements | `docs/PRODUCT_REQUIREMENTS.md` | ACTIVE_CANON | Product intent and non-goals; newer explicit canon overrides superseded historical framing. |
| System requirements | `docs/SYSTEM_REQUIREMENTS.md` | ACTIVE_CANON | Functional/non-functional system contract. |
| Architecture | `docs/TARGET_ARCHITECTURE.md` | ACTIVE_CANON | Current vs target architecture and ownership boundaries. |
| Realtime Workbench boundary | `docs/REALTIME_WORKBENCH_SCOPE.md` | ACTIVE_CANON | Local realtime scope; not a general DAW authorization. |
| Data / artifacts | `docs/DATA_AND_ARTIFACT_POLICY.md` | ACTIVE_CANON | Private/local/generated data boundary. |
| Screen-1 renderer | `docs/WORKBENCH_QML_PROOF_SPIKE.md` | ACTIVE_SUPPORTING | `LOCK_PYSIDE6_QML`; current live work is under #691, not closed #503/#579. |
| Screen-1 preview playhead | `docs/WORKBENCH_PREVIEW_PLAYHEAD_CONTRACT.md` | ACTIVE_SUPPORTING | #738; Canvas body + thin overlay; engine-backed progress only. |
| Semantic search | `docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md` | ACTIVE_SUPPORTING | NumPy default, sqlite-vec opt-in, VST-first historical framing is superseded. |
| Screen-2 ownership | `docs/SESSION_OWNERSHIP_CONTRACT.md` | ACTIVE_SUPPORTING | Python-owned session state. |
| Pattern core | `docs/PATTERN_CORE_CONTRACT.md` | ACTIVE_SUPPORTING | Pattern/trigger truth. |
| Sequencer playback | `docs/SEQUENCER_PLAYBACK_CONTRACT.md` | ACTIVE_SUPPORTING | Scheduling/PCM boundary. |

## Durable orientation — not live trackers

| Surface | Class | Rule |
|---|---|---|
| `knowledge/CURRENT_STATUS.md` | DURABLE_SNAPSHOT | Durable "what exists / what matters" orientation. Query GitHub/repo live before execution. |
| `knowledge/ACTIVE_ROADMAP.md` | DURABLE_SNAPSHOT | Durable priority/sequence view. Do not infer exact open issue/PR state. |
| `docs/ISSUE_BACKLOG.md` | HISTORICAL_LEDGER | Historical issue/PR cross-reference only. Never use as live board reality. |

## Explicit historical / superseded records

| Surface | Class | Current authority |
|---|---|---|
| `docs/product/05_VST_PRODUCING_WORKSPACE_SPEC.md` | SUPERSEDED_RECORD | VST3 primary-path framing is parked under #469; current path is `PRODUCT_WORKFLOW_CANON.md`. |
| `knowledge/roadmap/adr/ADR-0002-local-vector-index-strategy.md` | SUPERSEDED_RECORD | FAISS strategy was superseded by ADR-0004; retained as ADR history. |
| Screen-1 Epic #503 / Governance #579 | HISTORICAL_LEDGER | Delivered migration/governance evidence; current Screen-1 parent is #691. |
| Historical benchmark/evidence documents | HISTORICAL_LEDGER | Keep measured results and capture commands tied to their recorded environment; do not treat them as current setup instructions unless explicitly marked current. |

## Task routing

- **Screen 1:** live #691 + scoped child, then Screen-1 authorities above.
- **Screen 2:** live #675/#678 + `PRODUCT_WORKFLOW_CANON.md` and Screen-2 supporting contracts. QML UI remains HOLD until its explicit gate is lifted.
- **Search:** EPIC-2 spec + active ADRs + current code/tests.
- **CI/governance:** GitHub live rules/checks first; docs describe policy, not current API state.
- **Repository hygiene:** `DATA_AND_ARTIFACT_POLICY.md` + live working-tree/worktree state.
- **Historical research:** use historical records as evidence only; do not promote them over active canon.

## Drift-prevention closeout

For documentation, canon, governance, status or audit changes:

1. fetch GitHub/repo live state;
2. run the task-specific tests;
3. run `python tools/check_canon_drift.py`;
4. review changed docs against this authority map;
5. if a new independent contradiction/risk is discovered, create a scoped follow-up instead of silently expanding the current change;
6. before claiming DONE, re-check PR/check/issue state live.

The checker intentionally verifies only deterministic invariants. It does **not** guess whether a dated roadmap is stale, infer issue state without GitHub, or rewrite historical evidence.
