# Analysis Extraction S3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver #1149 by separating reusable Analysis computation from Sample Brain application/catalog persistence while preserving current in-tree imports, algorithms, DB schema, CLI behavior, and frozen AQ surfaces.

**Architecture:** Keep SQLite, scan/catalog ingestion, CLI orchestration, seed/index loading, persistence, and Product adapters in `sample-brain`. Introduce four narrow neutral computation owners: `feature_analysis`, `classification`, `key_analysis_v2_core`, and `bpm_matching`. Existing `analyze`, `classify`, `key_analysis_v2`, and `matching` remain compatibility/application facades. No physical repository split or final external package API freeze in S3.

**Tech Stack:** Python 3.12+, NumPy, librosa/soundfile, dataclasses/typing, SQLAlchemy only in application facades, pytest, Ruff.

**Spec:** GitHub issue #1149 plus `docs/ANALYSIS_PUBLIC_CONTRACT_V1.md` from merged #1148.

**Live base:** `origin/main @ 86a1b49741e0c620bc9ec22e47e0875f99fe8172` (re-check before push/merge).

## Global Constraints

- `src.db` remains the single Sample Brain SQLite/catalog authority.
- `src.scan` remains application/catalog ingestion; no Scan extraction.
- No DB schema or query semantic changes.
- No analyzer/classifier/key/harmony algorithm, threshold, score, ordering, or frozen AQ surface changes.
- Preserve `src.analyze.extract_features`, `src.classify.rule_type`, `src.key_analysis_v2.*`, and `src.matching.*` compatibility surfaces.
- Preserve existing monkeypatch seams: application facades call locally rebound compatibility symbols where tests currently patch them.
- Neutral computation owners may not import `src.db`, SQLAlchemy, application config/path state, index/seed loading, Workbench, QML, PySide6, session/controller state.
- No private audio, local DB/index/cache/model artifacts, credentials, or machine-local paths in tracked files/tests/evidence.
- No global `AnalysisConfig`, service locator, second persistence abstraction, repo split, or #1150 public API freeze.
- AQ/benchmark automation remains evaluation/tooling; only keep existing consumers compatible.

## Task 1 — Freeze S3 boundaries (RED)

**Create:** `tests/test_analysis_s3_boundary.py`

1. Add AST/import-closure checks for `src.feature_analysis`, `src.classification`, `src.key_analysis_v2_core`, `src.bpm_matching`.
2. Fail closed on DB/SQLAlchemy/config/index/Workbench/QML/PySide6 dependencies.
3. Freeze compatibility identities:
   - `src.analyze.extract_features is src.feature_analysis.extract_features`
   - `src.classify.rule_type is src.classification.rule_type`
   - V2 result/estimator/serializer facade identity
   - matching BPM scoring facade identity
4. Freeze neutral ownership of `KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION` while preserving old exports.
5. Require Harmony to import `src.bpm_matching`, not `src.matching`.
6. Run `python -m pytest -q tests/test_analysis_s3_boundary.py` with a dedicated external `--basetemp`; verify RED before production edits.

## Task 2 — Feature-analysis seam

**Create:** `src/feature_analysis.py`
**Modify:** `src/analyze.py`

1. Move feature/DSP constants and helpers through `extract_features` without semantic edits.
2. `feature_analysis` consumes `analysis_contracts` + `key_signature` and explicit scientific/audio dependencies only.
3. Keep `_serialize_key_mode_evidence`, SQL upsert/paging/flush, `AnalyzeRunSummary`, and `run_analyze` in `src.analyze`.
4. `src.analyze` re-exports moved symbols and `Features` compatibility.
5. Keep `run_analyze` calling its local `extract_features` alias for current monkeypatch tests.
6. Validate short-audio, key/mode, batching, issue418 persistence, AQ1/AQ2 current-analyzer paths.

## Task 3 — Classification seam

**Create:** `src/classification.py`
**Modify:** `src/classify.py`

1. Move rule thresholds, `rule_type`, `_sigmoid`, and pure `_knn_predict` math without semantic edits.
2. Keep `SEED_CSV`, seed/index loading, DB queries, optional-index fail-soft behavior, and `pred_type` writes in `src.classify`.
3. Re-export neutral functions from `src.classify`; keep `write_autotype_to_db` using local aliases.
4. Preserve frozen AQ4 surface strings `src.classify.rule_type` and `src.classify.write_autotype_to_db(use_knn=True)`.
5. Validate AQ4 rule/candidate and autotype persistence parity.

## Task 4 — Key V2 computation seam

**Create:** `src/key_analysis_v2_core.py`
**Modify:** `src/key_analysis_v2.py`, neutral contract ownership as required.

1. Move `_ROOT_EVIDENCE_KIND`, `KeyAnalysisV2Result`, evidence serialization, and `estimate_key_v2_shadow` to the neutral owner.
2. Import `_chroma_mean` and `estimate_key_mode` from `feature_analysis`, never `src.analyze`.
3. Move the semantic V2 contract-version constant below persistence (prefer the existing neutral analysis-contract authority), preserve exact value `2`, and re-export from DB/facade as needed.
4. Keep DB read/write validation and row adapters in `src.key_analysis_v2`.
5. Preserve its current `__all__` compatibility surface.
6. Validate V2 shadow/features/read/write/hygiene and Track Map V2 activation.

## Task 5 — Minimal neutral BPM matching seam

**Create:** `src/bpm_matching.py`
**Modify:** `src/matching.py`, `src/harmony.py`

1. Move only BPM-owned constants/status/relation values needed by BPM scoring, `_BpmMatchDetails`, `_linear_decay`, `_score_bpm_details`, and `score_bpm_match`.
2. `src.matching` imports/re-exports them and retains general Match DTOs, key/type scoring, candidate DB loading, collect/run orchestration.
3. `src.harmony` imports BPM scoring/tolerance directly from `bpm_matching`.
4. Do not alter tolerance `8.0`, half/double penalty, reason strings, score formulas, ordering, or musical semantics.
5. Validate matching/hybrid/harmony and frozen AQ6 theory/ranking suites.

## Task 6 — Integration/no-DB proof + durable docs

**Modify:** `docs/ANALYSIS_PUBLIC_CONTRACT_V1.md`, `docs/TARGET_ARCHITECTURE.md`; `docs/CANON_INDEX.md` only if its S2 entry requires a narrow S3 description update.

1. Add no-catalog proof with synthetic/temp audio: neutral compute can import/run without Sample Brain catalog creation/mutation.
2. Verify scan remains unchanged with existing scan/pipeline tests.
3. Verify CLI help and analyze/autotype dispatch remain compatible; do not change CLI unless a failing compatibility test proves it necessary.
4. Update durable ownership once: neutral computation below application persistence; SQLite remains application-owned; #1150 receives S3 package-candidate handoff.
5. Do not duplicate execution history/base SHAs in durable canon or create a second `knowledge/` truth.
6. Run `python tools/check_canon_drift.py`.

## Task 7 — Validation and delivery

1. Run focused S3 boundary/feature/classification/key-v2/matching-harmony/pipeline tests.
2. Run CLI smoke: `python -m src.cli --help` and installed `sample-brain --help`; any mutating smoke uses an external/temp DB.
3. Run `python -m ruff check .`.
4. Run `python tools/check_canon_drift.py`.
5. Run `git -c core.whitespace=cr-at-eol diff origin/main...HEAD --check` without changing shared Git config.
6. Run full pytest on final branch and compare failures against the fresh unchanged-base Windows run; classify REGRESSION / BASELINE_EXISTING / ENVIRONMENT_HOST / UNKNOWN.
7. Review complete diff for scope creep, duplicate authority, import leaks, algorithm/schema/CLI drift, private paths/artifacts.
8. Fetch/recheck `origin/main` and overlapping PRs before push; integrate only verified non-overlapping base drift.
9. Push and open PR with `Fixes #1149` only when acceptance is met.
10. Inspect every final-head conversation comment, review, inline thread, bot review, and required check. Required merge gate: `unreviewed=0`, `unresolved_threads=0`.
11. Merge only when final head is clean, CI_GREEN, and review feedback is dispositioned.
12. Live-verify PR merge SHA on `main` and #1149 closed/completed; then mark #1150 `READY_FOR_IMPLEMENTATION` only, without implementing S4.

## Completion Contract

#1149 is complete only when all four neutral owners are real, legacy facades remain compatible, SQLite/scan persistence ownership is not duplicated, focused/integration/full relevant validation supports the diff, durable docs describe delivered ownership only, PR is merged, and #1149 is closed live.