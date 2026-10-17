# Analysis Package Boundary v1

**Status:** ACTIVE_SUPPORTING<br>
**Issue:** #1150 under #1147<br>
**Code owner:** `src.analysis`<br>
**Contract owner:** this document; shared config/DTO semantics remain in [`ANALYSIS_PUBLIC_CONTRACT_V1.md`](ANALYSIS_PUBLIC_CONTRACT_V1.md)

## Purpose and import roots

This freezes the package-ready Analysis boundary inside `sample-brain`. It does not create the future repository or duplicate implementation source.

- Current monorepo consumer import root: `src.analysis`.
- Future distribution name for #1151: `sample-brain-analysis`.
- Future Python import root for #1151: `sample_brain_analysis`.
- #1151 maps the same frozen symbols and contracts to that root while moving their canonical implementation owners; existing `src.*` paths remain Sample Brain compatibility/application surfaces where required.

The executable public manifest is `src.analysis.__all__`; `tests/test_analysis_contract_boundary.py::test_analysis_public_api_manifest_is_frozen` freezes both the names and their canonical owners.

## Frozen public API

| Domain | Public names |
|---|---|
| Shared contract | `ANALYZE_HOP_LENGTH`, `ANALYZE_SR`, `BPMNormalizationMode`, `Features`, `validate_bpm_normalization` |
| Feature analysis | `extract_features`, `normalize_bpm` |
| Attack analysis | `AttackSuggestion`, `suggest_attack_ms` |
| Gesture analysis | `GestureAnalysis`, `GestureEvent`, `analyze_gesture_audio` |
| Harmony | `HarmonyInput`, `HarmonyRelation`, `HarmonySuggestion`, `determine_relation`, `rate_harmony`, `find_harmony_matches` |
| Key signatures | `ParsedKey`, `parse_key_signature`, `format_key_signature`, `is_same_root`, `is_same_mode`, `key_distance_semitones` |
| Key V2 | `KeyAnalysisV2Result`, `estimate_key_v2_shadow` |
| Classification | `rule_type` |
| BPM matching | `score_bpm_match` |

The surface contains no database rows, catalog queries, seed/index loaders, product caches, benchmark runners, UI state, or Workbench DTOs. `AudioTimebase`, canonical rendering/provenance, joint-profile ranking helpers, serialization internals, and the kNN vector helper remain package-internal unless a later consumer contract proves otherwise.

## Result, status, and error semantics

| Operation | Frozen behavior |
|---|---|
| `validate_bpm_normalization` | Returns one of `none`, `heuristic`, or `domain_110_170`; otherwise raises `ValueError`. |
| `extract_features` | Reads only its explicit audio path and returns `Features` or `None` for unreadable/unsupported input. |
| `suggest_attack_ms` | Reads only its explicit audio path and returns `AttackSuggestion` or `None`; non-positive `frame_ms` raises `ValueError`. |
| `analyze_gesture_audio` | Returns `GestureAnalysis`; statuses remain `ok`, `empty`, `too_short`, and `unreadable`. Ordinary file/DSP failures are fail-soft. |
| `rule_type` | Returns the deterministic ordered tag list; default thresholds and behavior remain owned by `src.classification`. |
| `score_bpm_match` | Returns a score in `[0, 1]`; missing or invalid BPM produces `0.0`. |
| `find_harmony_matches` | Returns `(suggestions, error)`; unusable reference BPM or an empty loaded candidate set returns no suggestions and the existing explanatory error. |
| `parse_key_signature` | Returns `ParsedKey` or `None` for missing/unparseable text. |
| `estimate_key_v2_shadow` | Returns `KeyAnalysisV2Result` or `None` when the current estimator cannot produce a result. V2 remains shadow evidence and does not become product key authority. |

These are existing contracts, not behavior changes introduced by this boundary. Golden and domain tests remain the behavior evidence.

## Surface and ownership inventory

| SURFACE | CURRENT OWNER | PUBLIC CANDIDATE | INTERNAL | APP ADAPTER | SIDE EFFECTS | IMPORT CLOSURE | DECISION |
|---|---|---|---|---|---|---|---|
| shared contracts | `src.analysis_contracts` | shared constants, `BPMNormalizationMode`, `Features`, validator | none beyond declared contract | `src.config`, `src.config_loader` | none | stdlib | public; neutral owner remains canonical |
| feature compute | `src.feature_analysis` | `extract_features`, `normalize_bpm` | loader, key/chroma/DSP helpers, constants | `src.analyze` | explicit audio-file read; no catalog writes | stdlib, NumPy, librosa, SoundFile; local key contracts | public functions; helpers stay internal |
| classification | `src.classification` | `rule_type` | sigmoid and vector kNN helper | `src.classify` | none | stdlib, NumPy | rule API public; kNN helper private |
| key V2 | `src.key_analysis_v2_core` | result DTO and estimator | serializer and private dependency-injection seam | `src.key_analysis_v2` | none | stdlib, NumPy, neutral feature/key modules | result/compute public; persistence adapter stays outside |
| joint key profile | `src.joint_key_profile` | none | profiles, ranking and numeric helpers | benchmark/evaluation consumers | none | stdlib, NumPy | internal algorithm dependency |
| BPM matching | `src.bpm_matching` | `score_bpm_match` | detailed score/status result and constants | `src.matching`, `src.harmony` | none | stdlib, local display formatter | score public; detail helper private |
| attack | `src.attack_analysis` | `AttackSuggestion`, `suggest_attack_ms` | framing, thresholds, confidence helpers | Workbench suggestion adapter | explicit audio-file read | stdlib, NumPy, SoundFile, internal canonical-audio helpers | public compute; UI remains outside |
| gesture | `src.gesture_analysis` | result/event DTOs and `analyze_gesture_audio` | onset/DSP/clustering helpers and thresholds | gesture catalog/rack adapters | explicit audio-file read | stdlib, NumPy, librosa, neutral feature/contracts modules | public compute; catalog/rack adapters stay outside |
| harmony | `src.harmony` | input/result DTOs and relation/rating/ranking calls | relation/scoring helpers | Workbench/Product adapters | pure computation on supplied values | stdlib, neutral BPM/key modules | public compute; no candidate loading |
| key signature | `src.key_signature` | parser, formatter, relation/distance helpers and `ParsedKey` | pitch-class tables | export/search/product consumers | pure computation | stdlib | public shared domain contract |
| canonical audio | `src.canon_audio` | none | explicit timebase/probe/render/provenance helpers | Workbench, Track Map, asset/product flows | explicit file read/write/hash calls; no import-time state | stdlib, NumPy, SoundFile, librosa, `src.utils` | internal dependency; no full-module export |
| catalog matching | `src.matching` | none from this module | DB-backed candidate matching orchestration | CLI/Product | catalog read and candidate loading | SQLAlchemy, `src.db` | application adapter; forbidden in package closure |
| analyze/classify/key persistence | `src.analyze`, `src.classify`, `src.key_analysis_v2` | none from these modules | batching, seed/index/DB and run orchestration | CLI/catalog | SQLite reads/writes, progress | SQLAlchemy, `src.db`, application configuration | application-owned compatibility facades |
| scan/catalog | `src.scan`, `src.db` | none | ingestion, schema and catalog persistence | CLI/Product | filesystem discovery and SQLite | application stack | stays exclusively in `sample-brain` |
| product projection/cache/session/UI | `src.context_analyze`, `src.asset_analysis`, `src.workbench_*`, QML/PySide6 | none | product maps, cache/state, controller/session/UI logic | Product/Workbench | product state, UI/runtime and cache effects | app/runtime stack | stays exclusively in `sample-brain` |

The candidate closure test walks the facade and every listed neutral owner transitively. It rejects DB/SQLAlchemy, CLI/config/profile/state, catalog, Product, Workbench, QML/PySide6, Tk, packaging, and installer imports. Current third-party imports are limited to the existing Analysis needs (`numpy`, `librosa`, `soundfile`); SciPy is allowed only if a future directly used Analysis implementation needs it and the manifest/gate is deliberately updated.

## Dependency and clean-consumer contract

Package candidates may use Python standard library and the directly required Analysis libraries above. They must not read Product environment/profile variables, derive paths from repository cwd, create directories on import, load local seeds/indexes, or create DB/cache/session state.

`tests/test_analysis_contract_boundary.py` enforces the public manifest, canonical object identity, transitive import allowlist, environment/import-time state rules, and a wheel install smoke. The consumer subprocess runs from a separate temporary cwd with Sample Brain environment variables removed, imports the installed wheel, exercises deterministic contract/classification/matching/key/harmony calls, and asserts that the cwd remains unchanged. The existing neutral feature, attack, gesture, key, and harmony tests remain the behavioral proof for file-based APIs.

No dependency-linter framework is introduced. SQLite and SQLAlchemy remain exclusively application/catalog persistence authority in `sample-brain` per the #1149 handoff.

## Compatibility surfaces

The package facade is one-way: it imports canonical neutral owners. Existing product imports remain available:

- `src.analyze` keeps its loader-bound `extract_features` facade. Patching `src.analyze.safe_load` must still affect the facade call and remains covered by the S3 regression test.
- `src.classify.rule_type` remains the `src.classification.rule_type` object.
- `src.key_analysis_v2` retains its persistence facade while exposing the DB-free V2 result/compute owner.
- `src.matching.score_bpm_match` remains a compatibility import of `src.bpm_matching.score_bpm_match`.

No algorithm, threshold, score ordering, cache fingerprint, persistence schema, or CLI behavior change is intended.

## #1151 knowledge handoff

| KNOWLEDGE ITEM | CURRENT OWNER | FUTURE OWNER | TYPE | AUTHORITATIVE? | VERIFYING TEST/GATE | ACTION IN #1151 |
|---|---|---|---|---|---|---|
| Analysis architecture boundary | this document; `docs/TARGET_ARCHITECTURE.md` links the application-wide map | `docs/architecture/boundaries.md` and `ARCHITECTURE.md` in `sample-brain-analysis` | architecture | yes, this document for the internal boundary | package import-closure gate | move only package ownership and dependency direction; keep app composition in Sample Brain |
| public API and future import name | `src.analysis.__all__`; this document | `sample_brain_analysis.__init__` and `docs/contracts/` | API contract | yes, this document; code is executable projection | frozen manifest/owner-identity test | map every frozen name; do not expand exports during relocation |
| config and DTO contracts | `src.analysis_contracts.py`; `docs/ANALYSIS_PUBLIC_CONTRACT_V1.md` | package contracts docs and moved neutral owner | contract | yes, the existing contract document | S2/S3 contract tests | move neutral constants/DTO only; retain one owner |
| import/dependency rules | this document; `tests/test_analysis_contract_boundary.py` | package architecture docs and `tests/`/CI | architecture/validation | yes, this document and executable test | closure, allowlist, environment and wheel smoke | carry gates into the new repo and add Sample Brain consumer compatibility CI |
| durable Analysis decision provenance | `docs/ANALYSIS_PUBLIC_CONTRACT_V1.md` (`NO_GLOBAL_ANALYSIS_CONFIG`); #1147/#1148/#1149 issues and merged PRs are decision history | `docs/decisions/` only for decisions with lasting alternatives/trade-offs | decision provenance | current contract is authoritative for current semantics; issues/PRs are history | contract and compatibility tests | restate only durable decisions as ADRs with provenance links; do not copy execution history |
| Analysis validation contract | this document, focused tests, `AGENTS.md` quality gates and CI workflows | `docs/validation/` and package CI | validation | yes for boundary acceptance; tests are executable proof | focused Analysis suite, Ruff, canon drift, wheel smoke, required CI | move package tests/fixtures only when synthetic and safe; create consumer tests in Sample Brain |
| offline-first and private-data policy | `docs/TARGET_ARCHITECTURE.md`, `docs/DATA_AND_ARTIFACT_POLICY.md`, #1147 | package `AGENTS.md` and `docs/canon/README.md` | policy | current monorepo docs remain authority until extraction | offline local test commands; no private fixtures in package | carry the relevant local-only/no-private-data rule; do not copy broad Product policy |
| package build/release knowledge | current `pyproject.toml` builds the Sample Brain monorepo; no Analysis release procedure exists yet | new package `pyproject.toml`, `CONTRIBUTING.md`, and workflow only as needed | operational | no package release authority exists yet | installed-wheel smoke now; package build/CI in #1151 | define the minimal version/build/release contract in the new repo; do not invent a release process here |
| application persistence and Sample Brain DB authority | `src.db`, application facades, `docs/TARGET_ARCHITECTURE.md` | remains in `sample-brain`; new package architecture records the exclusion | application/persistence | yes, Sample Brain remains sole owner | S3 no-DB and import-closure tests | leave schema, queries, adapters, run orchestration and `pred_type` persistence in Sample Brain |
| Workbench/session/product projection | `src.workbench_*`, session/controller modules and their active contracts | remains in `sample-brain` | Product/application | yes, Sample Brain remains owner | existing Product adapter regression suite | do not move UI, session, cache, Track Map, or Product projections |
| product cache/projection policy | `src.track_analysis_cache.py`, `src.context_analyze.py`, `src.asset_analysis.py` and linked contracts | remains in `sample-brain` | Product/application | yes, Sample Brain remains owner | existing cache/projection tests | keep path-bound cache, Product documents and projection behavior in the app |

The new repository starts with the #1147 minimal document metadata core (`doc_id`, `doc_type`, `lifecycle`, `authority`, `scope`); optional relation fields are used only when needed. `PROJECT_META.yaml` owns machine-needed repo/package entry paths, not architecture rationale. No second `knowledge/` tree or broad Sample Brain metadata migration is part of this slice.

### Future `check_knowledge_graph.py` acceptance

The #1151 checker is deterministic, offline, read-only and returns a stable CI exit code. It must check:

- required frontmatter fields and the #1147 enums: `doc_type` = `architecture | contract | decision | spec | runbook | validation | reference`; `lifecycle` = `draft | active | superseded | historical`; `authority` = `canonical | supporting | operational | generated | historical`;
- unique `doc_id`, internal relative Markdown links, and existing metadata path references;
- consistent `supersedes`/`superseded_by` relations and acyclic `depends_on` when used;
- reachability of active canonical docs from `docs/README.md`;
- existing `generated_from` sources and canonical paths declared in `PROJECT_META.yaml`;
- obvious machine-local/private absolute paths.

It must not require network access or implement LLM staleness scoring, embeddings, vector/graph databases, automatic rewrites, or a cloud service. #1151 owns its implementation; no checker framework is added to `sample-brain` in #1150.
