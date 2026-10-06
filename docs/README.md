# Sample Brain — Documentation Index

Quick navigation for reviewing the repository. Product-facing docs are listed first;
internal agent- and process docs are clearly separated.

## Portfolio & Product Story

| Document | What it is |
|---|---|
| [Portfolio Case Study](CASE_STUDY.md) | Full product story: problem, role, decisions, evidence |
| [Screen-1 Visual Acceptance](WORKBENCH_VISUAL_ACCEPTANCE.md) | How runtime UI evidence is captured from a verified build |
| [Screen-1 UI Acceptance](SCREEN1_UI_ACCEPTANCE.md) | Local Windows desktop smoke/acceptance workflow for Screen 1 |
| [Screen-1 Clean Start](WORKBENCH_CLEAN_START.md) | Neutral launch, source-driven disclosure, startup preset hook |
| [Screen-1 Elastic Layout](WORKBENCH_ELASTIC_LAYOUT.md) | Coupled weighted panel ratios, solver + QML projection (#694) |
| [README](../README.md) | Landing page, feature status matrix, quickstart |

## Product & Requirements

| Document | What it is |
|---|---|
| [Canon Index](CANON_INDEX.md) | Authority map: active canon vs supporting / snapshot / historical (front door) |
| [Product Workflow Canon](PRODUCT_WORKFLOW_CANON.md) | Workbench-first producing path; overrides stale VST-first framing |
| [Product Requirements](PRODUCT_REQUIREMENTS.md) | Vision, audience, MVP scope |
| [System Requirements](SYSTEM_REQUIREMENTS.md) | Functional / non-functional requirements |
| [Product Pillar Specs](product/README.md) | Historical capability pillar specs; VST-first framing is parked/superseded as primary path |
| [Realtime Workbench Scope](REALTIME_WORKBENCH_SCOPE.md) | Boundary of the local real-time workbench |
| [Screen-1 QML Proof / Renderer](WORKBENCH_QML_PROOF_SPIKE.md) | `LOCK_PYSIDE6_QML`; proof vs production-shell boundary |

## Architecture & Decisions

| Document | What it is |
|---|---|
| [Target Architecture](TARGET_ARCHITECTURE.md) | Module boundaries, pipeline contracts |
| [Data & Artifact Policy](DATA_AND_ARTIFACT_POLICY.md) | Committed vs. runtime artifacts |
| [ADR: sqlite-vec Search Backend](adr/ADR-0004-sqlite-vec-search-backend.md) | Default-search decision |
| [ADR: Search Quality Evaluation](adr/ADR-0005-search-quality-evaluation.md) | Golden dataset contract |
| Key contracts | [Track Map v1](TRACK_MAP_V1.md), [Key Mode Analysis v1](KEY_MODE_ANALYSIS_V1.md), [Track Analysis Cache v1](TRACK_ANALYSIS_CACHE_V1.md) |
| Packs | [Manifest](PERFORMANCE_PACK_MANIFEST_V1.md), [Layout](PERFORMANCE_PACK_LAYOUT_V1.md), [Resume](PERFORMANCE_PACK_RESUME_V1.md) |
| Deconstruction | [Track Deconstruction Orchestrator v1](TRACK_DECONSTRUCTION_ORCHESTRATOR_V1.md) |

## Benchmarks & Evidence

| Document | What it is |
|---|---|
| [Search Quality Evidence](benchmarks/SEARCH_QUALITY_EVIDENCE.md) | Measured P@K / R@K (Tier A + B) |
| [CLAP Tier-B Runtime](benchmarks/CLAP_TIER_B_RUNTIME.md) | Reproducible CLAP evaluation run |
| [sqlite-vec Gate Evidence](benchmarks/SQLITE_VEC_GATE_EVIDENCE.md) | Latency/quality gates |
| [Key Confidence Evidence](benchmarks/KEY_CONF_EVIDENCE.md) | Key analysis confidence |
| [BPM Half/Double Evidence](benchmarks/BPM_HALF_DOUBLE_EVIDENCE.md) | BPM ambiguity evaluation |
| [AQ1 Tempo & BeatGrid KPI Contract](benchmarks/AQ1_TEMPO_BEATGRID_KPI_CONTRACT.md) | #973/#943 frozen tempo/BeatGrid KPI + partition policy (BeatGrid annotations HOLD) |
| [AQ1 Tempo Baseline](benchmarks/AQ1_TEMPO_BASELINE.md) | #975/#943 measured current-analyzer tempo baseline on FSLD (`bpm_evidence=known`) |
| [AQ1 Tempo Candidate Compare](benchmarks/AQ1_TEMPO_CANDIDATE_COMPARE.md) | #977/#943 reproducible FSLD tempo candidate comparison (`bpm_normalization` adapters; no promotion) |
| [AQ1 Tempo Decision Memo](benchmarks/AQ1_TEMPO_DECISION_MEMO.md) | #981/#943 evidence-backed keep-current tempo decision (no production switch; BeatGrid HOLD) |
| [AQ2 Key, Mode & Tonality KPI Contract](benchmarks/AQ2_KEY_TONALITY_KPI_CONTRACT.md) | #983/#944 frozen key/mode correctness + tonality claimability KPI + FSLD eligibility (AUROC/calibration HOLD) |
| [Analyzer Portable Output Baseline](benchmarks/ANALYZER_PORTABLE_OUTPUT_BASELINE.md) | #960 AQ8 audit: safe/unsafe analyzer projection inventory for #956 |
| [Validation Reports](validation/README.md) | Local validate_report how-to; committed files there are historical issue evidence |

## Operations, Process & Infrastructure (internal)

These support the development process, not the product itself:

| Document | What it is |
|---|---|
| [Operations / Capabilities](operations/README.md) | Capability registry front door (process/routing; not product canon) |
| [Pipeline runbook](PIPELINE.md) | Legacy title-suggestion pipeline |
| [CI Degraded Mode](CI_DEGRADED_MODE.md) | CI fallback policy |
| [Branch Protection](BRANCH_PROTECTION.md) | Merge governance |
| [MCP Setup](MCP_SETUP.md) | Local MCP / agent tooling |
| [Bootloader & Context Strategy](BOOTLOADER_AND_CONTEXT_STRATEGY.md) | Agent session context |
| [Issue Backlog](ISSUE_BACKLOG.md) | HISTORICAL_LEDGER only; use GitHub live for open/closed work |
| Runbooks | [Self-hosted runner](runbooks/SAMPLE_BRAIN_SELF_HOSTED_RUNNER.md) |

Historical single-documents (kept for evidence, no longer current): [`docs/archive/`](archive/).
