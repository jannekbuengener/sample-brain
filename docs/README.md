# Sample Brain — Documentation Index

Quick navigation for reviewing the repository. Product-facing docs are listed first;
internal agent- and process docs are clearly separated.

## Portfolio & Product Story

| Document | What it is |
|---|---|
| [Portfolio Case Study](CASE_STUDY.md) | Full product story: problem, role, decisions, evidence |
| [Screen-1 Visual Acceptance](WORKBENCH_VISUAL_ACCEPTANCE.md) | How runtime UI evidence is captured from a verified build |
| [README](../README.md) | Landing page, feature status matrix, quickstart |

## Product & Requirements

| Document | What it is |
|---|---|
| [Product Requirements](PRODUCT_REQUIREMENTS.md) | Vision, audience, MVP scope |
| [System Requirements](SYSTEM_REQUIREMENTS.md) | Functional / non-functional requirements |
| [Product Pillar Specs](product/README.md) | Index of the five VST-first pillar specs |
| [Realtime Workbench Scope](REALTIME_WORKBENCH_SCOPE.md) | Boundary of the local real-time workbench |
| [Issue Backlog](ISSUE_BACKLOG.md) | Planned work |

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
| [Validation Reports](validation/README.md) | Contract validation summaries |

## Operations, Process & Infrastructure (internal)

These support the development process, not the product itself:

| Document | What it is |
|---|---|
| [Pipeline runbook](PIPELINE.md) | Legacy title-suggestion pipeline |
| [CI Degraded Mode](CI_DEGRADED_MODE.md) | CI fallback policy |
| [Branch Protection](BRANCH_PROTECTION.md) | Merge governance |
| [MCP Setup](MCP_SETUP.md) | Local MCP / agent tooling |
| [Bootloader & Context Strategy](BOOTLOADER_AND_CONTEXT_STRATEGY.md) | Agent session context |
| Runbooks | [Self-hosted runner](runbooks/SAMPLE_BRAIN_SELF_HOSTED_RUNNER.md) |

Historical single-documents (kept for evidence, no longer current): [`docs/archive/`](archive/).