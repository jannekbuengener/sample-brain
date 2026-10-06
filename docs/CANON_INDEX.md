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
| Product producing flow | `docs/PRODUCT_WORKFLOW_CANON.md` | ACTIVE_CANON | Workbench-first Single Workspace; one persistent Workbench + progressive disclosure. VST3 remains parked. |
| Single Workspace product navigation | `docs/WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md` | ACTIVE_SUPPORTING | Owner Decision A (#905) Owner-reviewed / approved. Binding product-navigation / workspace-geometry authority. #907 owns audio/session-focus audit; #908 is bottom Rack projection after those gates; #679 Arrangement stays PARKED / UNDESIGNED. |
| Product requirements | `docs/PRODUCT_REQUIREMENTS.md` | ACTIVE_CANON | Product intent and non-goals; newer explicit canon overrides superseded historical framing. |
| System requirements | `docs/SYSTEM_REQUIREMENTS.md` | ACTIVE_CANON | Functional/non-functional system contract. |
| Architecture | `docs/TARGET_ARCHITECTURE.md` | ACTIVE_CANON | Current vs target architecture and ownership boundaries. |
| Realtime Workbench boundary | `docs/REALTIME_WORKBENCH_SCOPE.md` | ACTIVE_CANON | Local realtime scope; not a general DAW authorization. |
| Data / artifacts | `docs/DATA_AND_ARTIFACT_POLICY.md` | ACTIVE_CANON | Private/local/generated data boundary. |
| Local Measurement Layer | `docs/adr/ADR-0006-measurement-contract-v1.md` | ACTIVE_SUPPORTING | Provider-neutral local measurement vs forbidden external telemetry in core; Mixpanel only as optional future sink. |
| Analyzer runtime bench methodology | `docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md` | ACTIVE_SUPPORTING | #958 frozen cold/steady runtime measurement contract for analyzers; distinct from ADR-0006 local measurement and from #956 ARVP artifact mapping. |
| Workbench QML renderer | `docs/WORKBENCH_QML_PROOF_SPIKE.md` | ACTIVE_SUPPORTING | `LOCK_PYSIDE6_QML`; #503/#579/#691 are delivered historical evidence. New Workbench visual work needs a new scoped issue under #905. |
| Workbench preview playhead | `docs/WORKBENCH_PREVIEW_PLAYHEAD_CONTRACT.md` | ACTIVE_SUPPORTING | #738; Canvas body + thin overlay; engine-backed progress only. Historical “Screen-1” wording in the contract is delivery evidence. |
| Workbench display preferences | `docs/WORKBENCH_DISPLAY_PREFERENCES.md` | ACTIVE_SUPPORTING | #696; density/motion/layout reset/startup presets; header overflow only. |
| Workbench functional feature settings | `docs/WORKBENCH_FEATURE_SETTINGS.md` | ACTIVE_SUPPORTING | #910; reusable functional toggles (`WorkbenchFeatureSettings`); distinct from view/display/theme/layout; `gesture_rack_apply_enabled` default disabled; no Rack mutation in the enabler. |
| Workbench Browser column arrangement | `docs/WORKBENCH_BROWSER_COLUMN_ARRANGEMENT_CONTRACT.md` | ACTIVE_SUPPORTING | #767 order; #850 header/delegate Type alignment so Length/Type never swap visually. |
| Workbench Browser column resize | `docs/WORKBENCH_BROWSER_COLUMN_RESIZE_CONTRACT.md` | ACTIVE_SUPPORTING | #780 width authority/runtime resize; #846 header-owned ephemeral resize affordances, no permanent vertical column dividers; one interactive meta handle; narrow mode preserves #692 defaults; Type non-resizable. |
| Workbench panel collapse | `docs/WORKBENCH_ELASTIC_LAYOUT.md` | ACTIVE_SUPPORTING | #845 presentation OPEN/COLLAPSED for Browser / Matches / Live Kit; absorbed into elastic visibility (no separate collapse contract file). |
| Workbench sample context menu | `docs/WORKBENCH_SAMPLE_CONTEXT_MENU_CONTRACT.md` | ACTIVE_SUPPORTING | #839 wine-red Browser sample context menu; Python-owned stable target ≠ selection; #840 Context Menu sole visible Browser Add-to-Kit route; #843 context Harmonic Matches open/retarget via `open_harmonic_matches_for_row`, header `harmonicMatchButton` removed, #845 remains collapse owner. |
| Harmonic Match reference eligibility | `docs/product/02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md` §9.1–§9.2 | ACTIVE_SUPPORTING | #842: effective key = eligible V2 claim else product `row.key`; root-only fail-closed; Browser display key ≠ matching authority; #843: context target → harmony anchor open/retarget (not toggle); #847/#848 gates analysis-algorithm changes. |
| Workbench visual acceptance | `docs/WORKBENCH_VISUAL_ACCEPTANCE.md` | ACTIVE_SUPPORTING | Agents own technical/runtime/visual acceptance; Owner does not run operative acceptance loops. |
| V7 Asset Foundation | `docs/assets/themes/README.md` | ACTIVE_SUPPORTING | Approved Superdesign V7 default Blood-A chrome/workspace/surface token freeze; runtime source remains Theme Core + `presets.v1.json`. |
| Global program chrome | `docs/PROGRAM_CHROME_CONTRACT.md` | ACTIVE_SUPPORTING | #830; Owner frame is top bar (identity left, navigation center, transport/tempo right — no Harmonic Match header button after #843) plus footer (Library utility left, context info true-center on full footer width, status right). Pattern/Bars/Song in the reference image is not authority. Live Kit chrome is inert before materialization. Chrome route labels may remain historical/runtime wording; product navigation authority is Single Workspace (#905). |
| Semantic search | `docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md` | ACTIVE_SUPPORTING | NumPy default, sqlite-vec opt-in, VST-first historical framing is superseded. |
| Session ownership | `docs/SESSION_OWNERSHIP_CONTRACT.md` | ACTIVE_SUPPORTING | Python-owned session state. Screen-transition seam names (`enter_screen2` / `return_to_screen1`) are runtime ownership hooks, not product-page navigation; #907 owns audit/repair. |
| Pattern core | `docs/PATTERN_CORE_CONTRACT.md` | ACTIVE_SUPPORTING | Pattern/trigger truth. |
| Sequencer playback | `docs/SEQUENCER_PLAYBACK_CONTRACT.md` | ACTIVE_SUPPORTING | Scheduling/PCM boundary. |
| Loop-row Rack playback | `docs/LOOP_ROW_PLAYBACK_CONTRACT.md` | ACTIVE_SUPPORTING | #920 freeze: `LOOP_ROW_DISTINCT_PROJECTION_REQUIRED` + `NATURAL_CYCLE_REPEAT` for explicit `loop`; non-destructive classification/restore; native-only fail-closed; runtime follow-up separate. |
| User-channel classification authority | `docs/USER_CHANNEL_CLASSIFICATION_AUTHORITY.md` | ACTIVE_SUPPORTING | #936 freeze: `USER_CHANNEL_CLASSIFICATION_RESOLVER_INJECTED`; Workbench library stays the single classification authority, session injects a read-only resolver, Rack/audio modules stay I/O-free; derived non-persisted path-keyed binding; ambiguous stays fail-closed; runtime follow-up separate. |
| Analyzer perturbation / metamorphic fixtures | `docs/ANALYZER_PERTURBATION_FIXTURE_CONTRACT.md` | ACTIVE_SUPPORTING | #957 freeze: transform mechanics + provenance only for AQ robustness tests; no AQ thresholds; no #956 ARVP artifact ownership. |
| Analyzer semantic determinism comparator | `docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md` | ACTIVE_SUPPORTING | #959 freeze: semantic projection + equality/mismatch/incompatibility for analyzer evidence; volatile metadata excluded by enumeration; no blanket float rounding or silent sorting. |
| Analysis-eval artifact / ARVP bridge | `docs/benchmarks/SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` | ACTIVE_SUPPORTING | #956 freeze: `sample-brain.analysis-eval.v1` portable envelope + structural ARVP #7 mapping; no runtime `import arvp`; #960 portable baseline consumed; #957/#958/#959 adjacent owners; ARVP #11/#12 deferred. |
| AQ1 Tempo & BeatGrid KPI / benchmark | `docs/benchmarks/AQ1_TEMPO_BEATGRID_KPI_CONTRACT.md` | ACTIVE_SUPPORTING | #973 freeze under #943/#942: tempo KPI + `classify_bpm_error` buckets + FSLD `bpm_evidence=known` baseline; BeatGrid correctness metrics HOLD without public annotation corpus; consumes #956–#959 by reference. |
| AQ1 Tempo baseline (FSLD measured) | `docs/benchmarks/AQ1_TEMPO_BASELINE.md` | ACTIVE_SUPPORTING | #975 under #943/#942: current-analyzer tempo baseline on FSLD `bpm_evidence=known` (CALIBRATION→DEVELOPMENT/CALIBRATION, TEST→TEST/HOLDOUT); BeatGrid correctness HOLD; no promotion thresholds. |
| AQ1 Tempo candidate comparison (FSLD) | `docs/benchmarks/AQ1_TEMPO_CANDIDATE_COMPARE.md` | ACTIVE_SUPPORTING | #977 under #943/#942: reproducible ≤3 `bpm_normalization` candidates on FSLD; CALIBRATION exploration + frozen TEST evidence; no production switch / no promotion thresholds; BeatGrid HOLD. |
| AQ1 Tempo decision memo | `docs/benchmarks/AQ1_TEMPO_DECISION_MEMO.md` | ACTIVE_SUPPORTING | #981 under #943/#942: evidence-backed keep-current recommendation from contract/baseline/compare; Path B adapter limits noted; BeatGrid HOLD; no production switch. |
| AQ2 Key, Mode & Tonality KPI / benchmark | `docs/benchmarks/AQ2_KEY_TONALITY_KPI_CONTRACT.md` | ACTIVE_SUPPORTING | #983 freeze under #944/#942: key correctness vs tonality claimability; FSLD `root_evidence`/`mode_evidence`; `aq2.key`/`aq2.tonality`; AUROC/calibration HOLD without continuous claim score; consumes #956–#959 by reference. |
| AQ2 Key/Mode/Tonality baseline (FSLD measured) | `docs/benchmarks/AQ2_KEY_TONALITY_BASELINE.md` | ACTIVE_SUPPORTING | #985 under #944/#942: current-analyzer key/mode/tonality baseline on FSLD (CALIBRATION→DEVELOPMENT/CALIBRATION, TEST→TEST/HOLDOUT); AUROC/calibration HOLD; no promotion thresholds. |
| AQ2 Key/Mode candidate comparison (FSLD) | `docs/benchmarks/AQ2_KEY_CANDIDATE_COMPARE.md` | ACTIVE_SUPPORTING | #987 under #944/#942: reproducible ≤4 key/mode thin adapters on FSLD; CALIBRATION exploration + frozen TEST evidence; no production switch / no Harmonic Match changes; AUROC/calibration HOLD. |

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
| Former multi-screen product navigation `Screen 1 → Screen 2 → Screen 3` | SUPERSEDED_RECORD | Superseded by #905 + `WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md` + migrated `PRODUCT_WORKFLOW_CANON.md`. Closed #675/#678 remain historical Rack delivery evidence. |
| `knowledge/roadmap/adr/ADR-0002-local-vector-index-strategy.md` | SUPERSEDED_RECORD | FAISS strategy was superseded by ADR-0004; retained as ADR history. |
| Historical Workbench UI epics #503 / #579 / #691 | HISTORICAL_LEDGER | Delivered migration/governance/Calm Adaptive Workspace evidence; not an active Workbench parent. |
| Historical benchmark/evidence documents | HISTORICAL_LEDGER | Keep measured results and capture commands tied to their recorded environment; do not treat them as current setup instructions unless explicitly marked current. |

## Task routing

- **Single Workspace / Workbench product:** live GitHub + [#905](https://github.com/jannekbuengener/sample-brain/issues/905) and a **new scoped child issue**. Do not route new product work as Screen 1 / Screen 2 / Screen 3 page navigation.
- **Canon / docs alignment:** [#906](https://github.com/jannekbuengener/sample-brain/issues/906) (this migration track).
- **Session / audio-focus for Rack embed:** [#907](https://github.com/jannekbuengener/sample-brain/issues/907) — audit only until Owner-authorized repair; do not invent second transport/QML musical truth.
- **Bottom Live Kit / Rack projection:** [#908](https://github.com/jannekbuengener/sample-brain/issues/908) after #906/#907 — **DONE_MERGED_CLOSED** on `main`.
- **Loop-row / sustained-sample Rack semantics:** [#920](https://github.com/jannekbuengener/sample-brain/issues/920) + `docs/LOOP_ROW_PLAYBACK_CONTRACT.md`. Contract-first; no runtime until Owner/Lead review + separate GO.
- **User-channel sample classification ownership:** [#936](https://github.com/jannekbuengener/sample-brain/issues/936) + `docs/USER_CHANNEL_CLASSIFICATION_AUTHORITY.md`. Frozen injection boundary; runtime follow-up is [#952](https://github.com/jannekbuengener/sample-brain/issues/952); classification quality itself stays owned by [#946](https://github.com/jannekbuengener/sample-brain/issues/946).
- **Analyzer robustness / metamorphic fixtures:** [#957](https://github.com/jannekbuengener/sample-brain/issues/957) + `docs/ANALYZER_PERTURBATION_FIXTURE_CONTRACT.md` under [#950](https://github.com/jannekbuengener/sample-brain/issues/950). Mechanics/provenance only; AQ1–AQ7 own tolerances; [#956](https://github.com/jannekbuengener/sample-brain/issues/956) owns ARVP artifact mapping.
- **Analyzer semantic determinism / cache equivalence:** [#959](https://github.com/jannekbuengener/sample-brain/issues/959) + `docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md` under [#950](https://github.com/jannekbuengener/sample-brain/issues/950). Projection/equality seam only; [#956](https://github.com/jannekbuengener/sample-brain/issues/956) owns portable artifact mapping; [#960](https://github.com/jannekbuengener/sample-brain/issues/960) owns non-finite baseline audit.
- **Analysis-eval artifact / ARVP bridge:** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) + `docs/benchmarks/SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` under [#950](https://github.com/jannekbuengener/sample-brain/issues/950). Portable envelope + ARVP #7 structural mapping; no runtime `import arvp`.
- **AQ1 Tempo & BeatGrid KPI / benchmark:** [#973](https://github.com/jannekbuengener/sample-brain/issues/973) + `docs/benchmarks/AQ1_TEMPO_BEATGRID_KPI_CONTRACT.md` under [#943](https://github.com/jannekbuengener/sample-brain/issues/943) / [#942](https://github.com/jannekbuengener/sample-brain/issues/942). Docs-only KPI freeze; BeatGrid annotation corpus remains HOLD; do not reopen closed #956–#960.
- **AQ1 Tempo baseline (FSLD measured):** [#975](https://github.com/jannekbuengener/sample-brain/issues/975) + `docs/benchmarks/AQ1_TEMPO_BASELINE.md` under [#943](https://github.com/jannekbuengener/sample-brain/issues/943) / [#942](https://github.com/jannekbuengener/sample-brain/issues/942). Current tempo path evidence only; no algorithm change / no promotion thresholds; BeatGrid HOLD.
- **AQ1 Tempo candidate comparison (FSLD):** [#977](https://github.com/jannekbuengener/sample-brain/issues/977) + `docs/benchmarks/AQ1_TEMPO_CANDIDATE_COMPARE.md` under [#943](https://github.com/jannekbuengener/sample-brain/issues/943) / [#942](https://github.com/jannekbuengener/sample-brain/issues/942). Fair `bpm_normalization` bake-off only; no production switch; TEST/HOLDOUT not used for threshold discovery; BeatGrid HOLD.
- **AQ1 Tempo decision memo:** [#981](https://github.com/jannekbuengener/sample-brain/issues/981) + `docs/benchmarks/AQ1_TEMPO_DECISION_MEMO.md` under [#943](https://github.com/jannekbuengener/sample-brain/issues/943) / [#942](https://github.com/jannekbuengener/sample-brain/issues/942). Keep-current baseline path from frozen evidence; BeatGrid HOLD; no production switch in this slice.
- **AQ2 Key, Mode & Tonality KPI / benchmark:** [#983](https://github.com/jannekbuengener/sample-brain/issues/983) + `docs/benchmarks/AQ2_KEY_TONALITY_KPI_CONTRACT.md` under [#944](https://github.com/jannekbuengener/sample-brain/issues/944) / [#942](https://github.com/jannekbuengener/sample-brain/issues/942). Docs-only KPI freeze; key correctness separate from claimability; do not reopen closed #956–#960.
- **AQ2 Key/Mode/Tonality baseline (FSLD measured):** [#985](https://github.com/jannekbuengener/sample-brain/issues/985) + `docs/benchmarks/AQ2_KEY_TONALITY_BASELINE.md` under [#944](https://github.com/jannekbuengener/sample-brain/issues/944) / [#942](https://github.com/jannekbuengener/sample-brain/issues/942). Current key/tonality path evidence only; no algorithm change / no promotion thresholds; AUROC/calibration HOLD.
- **AQ2 Key/Mode candidate comparison (FSLD):** [#987](https://github.com/jannekbuengener/sample-brain/issues/987) + `docs/benchmarks/AQ2_KEY_CANDIDATE_COMPARE.md` under [#944](https://github.com/jannekbuengener/sample-brain/issues/944) / [#942](https://github.com/jannekbuengener/sample-brain/issues/942). Fair thin-adapter bake-off only; no production switch; TEST/HOLDOUT not used for threshold discovery; AUROC/calibration HOLD.
- **Channel Rack domain foundations:** closed [#675](https://github.com/jannekbuengener/sample-brain/issues/675)/[#678](https://github.com/jannekbuengener/sample-brain/issues/678) are **historical delivery evidence**; reuse contracts, do not reopen without explicit Owner-GO.
- **Arrangement:** [#679](https://github.com/jannekbuengener/sample-brain/issues/679) — **PARKED / UNDESIGNED — requires later explicit Owner design decision**. Do not auto-route.
- **VST / Bitwig / #697:** parked or research-only; explicit reactivation required. Do not auto-route.
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
