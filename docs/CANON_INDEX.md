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
| Local Measurement Layer | `docs/adr/ADR-0006-measurement-contract-v1.md` | ACTIVE_SUPPORTING | Provider-neutral local measurement vs forbidden external telemetry in core; Mixpanel only as optional future sink. |
| Screen-1 renderer | `docs/WORKBENCH_QML_PROOF_SPIKE.md` | ACTIVE_SUPPORTING | `LOCK_PYSIDE6_QML`; #503/#579/#691 are delivered historical evidence. New Screen-1 work needs a new scoped issue. |
| Screen-1 preview playhead | `docs/WORKBENCH_PREVIEW_PLAYHEAD_CONTRACT.md` | ACTIVE_SUPPORTING | #738; Canvas body + thin overlay; engine-backed progress only. |
| Screen-1 display preferences | `docs/WORKBENCH_DISPLAY_PREFERENCES.md` | ACTIVE_SUPPORTING | #696; density/motion/layout reset/startup presets; header overflow only. |
| Screen-1 Browser column arrangement | `docs/WORKBENCH_BROWSER_COLUMN_ARRANGEMENT_CONTRACT.md` | ACTIVE_SUPPORTING | #767 order; #850 header/delegate Type alignment so Length/Type never swap visually. |
| Screen-1 Browser column resize | `docs/WORKBENCH_BROWSER_COLUMN_RESIZE_CONTRACT.md` | ACTIVE_SUPPORTING | #780 width authority/runtime resize; #846 header-owned ephemeral resize affordances, no permanent vertical column dividers; one interactive meta handle; narrow mode preserves #692 defaults; Type non-resizable. |
| Screen-1 panel collapse | `docs/WORKBENCH_ELASTIC_LAYOUT.md` | ACTIVE_SUPPORTING | #845 presentation OPEN/COLLAPSED for Browser / Matches / Live Kit; absorbed into elastic visibility (no separate collapse contract file). |
| Screen-1 sample context menu | `docs/WORKBENCH_SAMPLE_CONTEXT_MENU_CONTRACT.md` | ACTIVE_SUPPORTING | #839 wine-red Browser sample context menu; Python-owned stable target ≠ selection; #840 Context Menu sole visible Browser Add-to-Kit route; #843 context Harmonic Matches open/retarget via `open_harmonic_matches_for_row`, header `harmonicMatchButton` removed, #845 remains collapse owner. |
| Screen-1 Harmonic Match reference eligibility | `docs/product/02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md` §9.1–§9.2 | ACTIVE_SUPPORTING | #842: effective key = eligible V2 claim else product `row.key`; root-only fail-closed; Browser display key ≠ matching authority; #843: context target → harmony anchor open/retarget (not toggle); #847/#848 gates analysis-algorithm changes. |
| Screen-1 visual acceptance | `docs/WORKBENCH_VISUAL_ACCEPTANCE.md` | ACTIVE_SUPPORTING | Agents own technical/runtime/visual acceptance; Owner does not run operative acceptance loops. |
| Global program chrome | `docs/PROGRAM_CHROME_CONTRACT.md` | ACTIVE_SUPPORTING | #830; Owner frame is top bar (identity left, navigation center, transport/tempo right — no Harmonic Match header button after #843) plus footer (Library utility left, hint/status right). Pattern/Bars/Song in the reference image is not authority. Live Kit chrome is inert before materialization. |
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
| Screen-1 Epic #503 / Governance #579 / Epic #691 | HISTORICAL_LEDGER | Delivered migration/governance/Calm Adaptive Workspace evidence; not an active Screen-1 parent. |
| Historical benchmark/evidence documents | HISTORICAL_LEDGER | Keep measured results and capture commands tied to their recorded environment; do not treat them as current setup instructions unless explicitly marked current. |

## Task routing

- **Screen 1:** live GitHub + a **new scoped issue** (closed #691 is delivered historical authority, not an active parent), then Screen-1 authorities above. Do not reopen #691 for new slices.
- **Screen 2:** closed #675/#678 (evidence) + `PRODUCT_WORKFLOW_CANON.md` and Screen-2 supporting contracts. Foundations (#676/#677/#681/#698) and Screen-2 QML (#678 / PR #755) are **DONE**; do not reopen Screen-2 product work without explicit Owner-GO.
- **Screen 3 / VST / Bitwig / #697:** parked or research-only; explicit reactivation required. Do not auto-route.
- **Search:** EPIC-2 spec + active ADRs + current code/tests. #74 is upstream ANN watch only.
- **CI/governance:** GitHub live rules/checks first; docs describe policy, not current API state. Closed #494/#703 are historical.
- **Repository hygiene:** `DATA_AND_ARTIFACT_POLICY.md` + live working-tree/worktree state.
- **Visual acceptance:** agents own fixture/runtime/screenshot/reviewer acceptance; do not wait on Owner operative visual acceptance as the normal end-state.
- **Historical research:** use historical records as evidence only; do not promote them over active canon.

## Operations / capability (not product canon)

Capability, routing and process-KPI truth lives under [`docs/operations/README.md`](operations/README.md) with machine authority in [`docs/operations/CAPABILITY_REGISTRY.json`](operations/CAPABILITY_REGISTRY.json). This index does not duplicate those facts.

## Drift-prevention closeout

For documentation, canon, governance, status or audit changes:

1. fetch GitHub/repo live state;
2. run the task-specific tests;
3. run `python tools/check_canon_drift.py`;
4. review changed docs against this authority map;
5. if a new independent contradiction/risk is discovered, create a scoped follow-up instead of silently expanding the current change;
6. before claiming DONE, re-check PR/check/issue state live.

The checker intentionally verifies only deterministic invariants. It does **not** guess whether a dated roadmap is stale, infer issue state without GitHub, or rewrite historical evidence.
