# Analysis Package Boundary v1

**Status:** ACTIVE_SUPPORTING — post-extraction consumer boundary
**Issue:** #1151 under #1147
**Package owner:** [`jannekbuengener/sample-brain-analysis`](https://github.com/jannekbuengener/sample-brain-analysis)
**Consumer owner:** `jannekbuengener/sample-brain`

## Authority and release identity

The physical Analysis extraction is complete at the package boundary. The
versioned distribution is `sample-brain-analysis`, imported as
`sample_brain_analysis`. Release `v0.1.1` provides
`sample_brain_analysis-0.1.1-py3-none-any.whl` with SHA-256
`3c5d3d97dbc5d171b65c19a56bba2317f64ebcbaaf6dcd075c836b8b29385da7`.
Sample Brain declares that exact wheel in both `pyproject.toml` and
`requirements.txt`.

The package owns its public manifest, result contracts, reusable algorithms,
package architecture, and independent validation. The
[v0.1.1 API contract](https://github.com/jannekbuengener/sample-brain-analysis/blob/v0.1.1/docs/contracts/analysis-public-api-v1.md)
and [package architecture](https://github.com/jannekbuengener/sample-brain-analysis/blob/v0.1.1/ARCHITECTURE.md)
are the canonical package documents. This Sample Brain document owns only the
consumer boundary and application ownership below; it does not copy the API
manifest or analysis semantics.

## Ownership after extraction

| Concern | Canonical owner | Sample Brain role |
|---|---|---|
| Public Analysis API, DTOs, feature/classification/key/BPM/attack/gesture/harmony computation, canonical audio helpers | `sample-brain-analysis` | Install the versioned wheel; call through the public API or temporary legacy aliases |
| Historical `src.*` paths for package-owned modules | External module objects from `sample_brain_analysis` | Thin compatibility aliases only; no local compute implementation |
| Scan, catalog DB/schema, SQLAlchemy/SQLite, batches/upserts, CLI accounting | `sample-brain` | Sole application persistence/orchestration owner |
| Classification seeds/index loading and `pred_type` persistence | `sample-brain` | Application adapter around package computation |
| Key V2 persistence and DB candidate loading | `sample-brain` | Application adapter around package result/compute owners |
| Catalog matching and candidate loading | `sample-brain` | DB-owning matching adapter; shared score semantics come from the package |
| Workbench, Session, QML, UI, caches, Track Map/Context/Asset projections, realtime audio, installers | `sample-brain` | Remain Product/runtime owners |
| AQ/quality-loop and benchmark orchestration, evidence, promotion decisions | `sample-brain` | Remain evaluation owners; extraction makes no quality claim |

The package-owned compatibility import map is executable in
`tests/test_analysis_external_package_consumer.py`. It covers `src.analysis`,
`src.analysis_contracts`, `src.attack_analysis`, `src.bpm_display`,
`src.bpm_matching`, `src.canon_audio`, `src.classification`,
`src.content_hash`, `src.feature_analysis`, `src.gesture_analysis`,
`src.harmony`, `src.joint_key_profile`, `src.key_analysis_v2_core`,
`src.key_signature`, and `src.utils`. Every path resolves to the same module
object as its installed package owner, and its source file resolves outside the
Sample Brain checkout. The test rejects local function/class definitions in
those shims.

## Application compatibility

- `src.analyze` remains an application loader/persistence adapter. Its
  `extract_features` facade calls package computation through the
  loader-injection seam. Patching `src.analyze.safe_load` must continue to
  affect that call; `tests/test_analysis_s3_boundary.py` freezes this behavior.
- `src.classify` keeps seed/index/catalog handling and `pred_type` writes.
- `src.key_analysis_v2` keeps V2 persistence and catalog integration.
- `src.matching` keeps catalog candidate loading and matching orchestration;
  its score functions resolve to the package owner through legacy aliases.
- `src.db` remains the only SQLite/SQLAlchemy schema and persistence owner.
- Workbench, Session, QML, Product state/caches, AQ workflows, and real-time
  audio do not move into the package.

No algorithm, threshold, score ordering, cache fingerprint, DB schema, or CLI
behavior is intentionally changed in this consumer migration. The separate
package issue [#2](https://github.com/jannekbuengener/sample-brain-analysis/issues/2)
tracks a pre-existing non-finite-reference-BPM Harmony bug; it is outside
#1151 and must not be folded into this behavior-preserving extraction.

## Consumer and duplicate-authority gates

The existing core CI jobs install `requirements.txt` before running tests. The
full-core job runs the consumer gate on a fresh runner against the exact
released wheel. No sibling checkout, editable path, local file URL, submodule,
or `PYTHONPATH` package dependency is used.

The Sample Brain gates prove:

- `tests/test_analysis_external_package_consumer.py` checks the exact version
  and URL/hash pin in both dependency manifests, alias/module identity,
  external installed source paths, and absence of implementation definitions
  in legacy shims;
- `tests/test_analysis_contract_boundary.py` runs the public package API from
  a clean non-repository working directory;
- `tests/test_analysis_s3_boundary.py` checks external package import closure,
  legacy monkeypatch/identity contracts, and that Harmony imports neutral
  package BPM scoring rather than catalog matching;
- `tests/test_analysis_s3_no_db.py` and application regression tests keep DB
  creation and persistence in Sample Brain.

Package-independent behavior, package-content, Knowledge Standard, and wheel
release gates remain owned by the Analysis repository and its CI.

## Durable knowledge handoff

| Fact | Owner in the extracted system |
|---|---|
| Package API names and module owners | Analysis v1 API contract in `sample-brain-analysis` |
| Analysis algorithms, thresholds, and result contracts | Package modules/tests in `sample-brain-analysis` |
| Package Knowledge Standard and checker | `sample-brain-analysis` canon and `tools/check_knowledge_graph.py` |
| Consumer pin and installed-package compatibility | This repository's dependency manifests, consumer tests, and CI |
| Product adapters, DB/session persistence, UI/runtime, AQ orchestration | Sample Brain code and its local canonical docs |
| Live branch/PR/release/check state | GitHub live state and Issue/PR history |

One fact has one owner; the other repository links to that owner. #1151
delivery and review evidence remains in the GitHub issue and consumer PR.
