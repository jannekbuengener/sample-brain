# Analysis Consumer Contract v1

**Status:** ACTIVE_SUPPORTING
**Issues:** #1148, #1149, #1151
**Application owner:** `jannekbuengener/sample-brain`

## Authority

The versioned distribution `sample-brain-analysis` (import root
`sample_brain_analysis`) owns the public Analysis API, result types, and
computation. Its v1 manifest is canonical in the immutable
[v0.1.0 package contract](https://github.com/jannekbuengener/sample-brain-analysis/blob/v0.1.0/docs/contracts/analysis-public-api-v1.md).
This Sample Brain document defines only how the application consumes that
package and where application behavior remains owned. It does not restate the
package's symbol list or DTO fields.

Sample Brain pins the released v0.1.0 wheel by URL and SHA-256 in both
`pyproject.toml` and `requirements.txt`. The released artifact is
`sample_brain_analysis-0.1.0-py3-none-any.whl`, SHA-256
`0c49d054eda265e078b79b4170f0a572b289175177c95c9a4ce9c34fbdc621f5`.

## Consumer ownership

| Concern | Owner | Sample Brain responsibility |
|---|---|---|
| Public Analysis names, DTOs, and computation | `sample-brain-analysis` | Install the declared wheel and test compatibility against the published package |
| Profile/configuration and environment overrides | `sample-brain` (`src.config`, `src.config_loader`) | Adapt configured values into the package's narrow explicit inputs |
| Scan, catalog schema, SQLite/SQLAlchemy, reads and writes | `sample-brain` (`src.scan`, `src.db`) | Keep one persistence authority |
| Analyze batching, progress, upserts, and run accounting | `sample-brain` (`src.analyze`) | Use package computation behind the loader-compatible application facade |
| Classification seeds, indexes, `pred_type`, and DB orchestration | `sample-brain` (`src.classify`) | Keep product seed policy and persistence outside the package |
| Key V2 persistence and catalog candidate loading | `sample-brain` (`src.key_analysis_v2`, `src.matching`) | Adapt package-owned compute/results to existing DB contracts |
| Workbench, Session, QML, product cache/projection, realtime audio | `sample-brain` | Retain product and runtime ownership |
| AQ evaluation, benchmark orchestration, and promotion decisions | `sample-brain` | Keep evaluation workflows application-owned; extraction alone is not quality evidence |

There is no global `AnalysisConfig` shared with product, profile, session, or
persistence state. The application passes explicit values to the package.
`src.config` may re-export constants for compatibility, but the package remains
the sole Analysis contract owner.

## Compatibility contract

- The package-owned legacy `src.*` module paths in
  `tests/test_analysis_external_package_consumer.py` resolve to the exact
  installed `sample_brain_analysis` module objects. They are aliases, not a
  second implementation.
- `src.analyze` remains an application adapter. Patching
  `src.analyze.safe_load` must still affect
  `src.analyze.extract_features`; `tests/test_analysis_s3_boundary.py` freezes
  this #1149 compatibility behavior.
- `src.classify`, `src.key_analysis_v2`, and `src.matching` retain seed/DB,
  persistence, and catalog orchestration respectively while using the external
  compute owners through compatibility aliases.
- The Sample Brain checkout must not shadow the installed package. The
  external consumer gate verifies package module identity, installed version,
  and that package source files resolve outside the Sample Brain checkout.
- No algorithm, threshold, score ordering, cache fingerprint, persistence
  schema, or CLI behavior is intentionally changed by the extraction.

## Validation

The consumer proof is `tests/test_analysis_external_package_consumer.py`,
`tests/test_analysis_contract_boundary.py`, `tests/test_analysis_s3_boundary.py`,
`tests/test_analysis_s3_no_db.py`, and
`tests/test_analysis_public_contract.py`, together with the domain and Product
regressions referenced by [`ANALYSIS_PACKAGE_BOUNDARY_V1.md`](ANALYSIS_PACKAGE_BOUNDARY_V1.md).
The core CI installs `requirements.txt` before running the full test suite, so
the consumer gate exercises the released wheel on a fresh runner.
