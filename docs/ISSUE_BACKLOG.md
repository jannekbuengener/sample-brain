# Issue Backlog

Prepared backlog with GitHub issue/PR cross-reference. See **GitHub board reality** below for live state.

## GitHub Board Reality (2026-06-22)

| Item | Status | Notes |
|------|--------|-------|
| Open issues | 🔶 9 total | #72 (key confidence), #73 (CLAP Tier-B), #74 (sqlite-vec ANN), **#90–#95 (VST-first product target)** |
| VST-first product target | ✅ Defined | Issues #90 (Parent) + #91–#95 (5 product pillars) |
| Open PRs | 🔶 5 Dependabot | #85 (sqlalchemy 2.0.51), #86 (scipy 1.18.0), #87 (checkout v7), #88 (numpy 2.5.0), #89 (tqdm 4.68.3) |
| `main` HEAD | ✅ Current | See latest `git log` |
| sqlite-vec campaign (PRs #47–#53) | ✅ Closed | Phases 1–8 complete |
| search-quality campaign (PR #54) | ✅ Closed | Merged 2026-05-31 |
| GitHub #27 | ✅ Closed | Implemented via PR #32 (`9d41782`) |
| GitHub #28 | ✅ Closed | Implemented via PR #34 (`31fc3f1`) |
| GitHub #29 | ✅ Closed | Implemented via PR #36 (`e7d59c7`) |
| GitHub #30 | ✅ Closed | Implemented via PR #35 (`05135a1`) |
| PR #33 | ✅ Merged | Bugfix follow-up for hybrid metadata (`f12a962`) |
| PR #37 | ✅ Merged | Config-/Export-contract stabilization (`cfd6e63`) |
| GitHub #11 | ✅ Closed | M1 — isolated CLAP runtime environment (PASS) |
| GitHub #12 | ✅ Closed | M2 — real CLAP text embedding smoke (PASS) |
| GitHub #14 | ✅ Closed | M5 hygiene — docs drift, Dependabot triage, stale PR cleanup |
| PR #13 | ✅ Merged | `SAMPLE_BRAIN_DB_PATH` external runtime DB (`8046816`) |
| PR #15 | ✅ Merged | EPIC-2 post-E2E docs sync (`134c462`) |
| PR #16 | ✅ Merged | SkillForge integration plan + routing rule (`cc61eea`) |
| PR #17 | ✅ Merged | Cursor Cloud dev environment instructions (`c5f623a`) |
| PR #19 | ✅ Merged | Skill routing discoverability + audit entry (`eb0e37e`) |
| PR #20 | ✅ Merged | Bootstrap validation path docs (`2f9d258`) |
| PR #21 | ✅ Merged | Issue backlog board sync (`e0d7745`) |
| PR #22 | ✅ Merged | CLAP unavailable search test hardening (`f87c696`) |
| PR #23 | ✅ Merged | EPIC-3 hybrid ranking score contract (`e981a53`) |
| PR #24 | ✅ Merged | Issue backlog board sync (`6a37b78`) |
| PR #25 | ✅ Merged | SampleBrain Cursor subagents (`33f1e3c`) |
| PR #26 | ✅ Merged | Backlog board sync baseline before this reconcile |
| PR #2 | ✅ Merged | `dependency-review-action` v4→v5 |
| PR #3 | ✅ Merged | `github/codeql-action` v3→v4 |
| PR #4 | ✅ Merged | `actions/checkout` v4→v6 |
| PR #5 | ✅ Merged | `numba` 0.59.1→0.65.1 (Librosa/numba risk check) |
| PR #6 | ✅ Merged | `pooch` 1.8.2→1.9.0 |
| PR #7 | ✅ Merged | `audioread` 3.0.1→3.1.0 |
| PR #8 | ✅ Merged | `tqdm` 4.66.4→4.67.3 |
| PR #9 | ✅ Merged | `soundfile` 0.12.1→0.13.1 |
| PR #10 | ✅ Closed | Superseded by incremental EPIC-2 work on `main` |
| PR #1 | ✅ Closed | Stale Claude review branch (2025) |
| M3 persistence smoke | ✅ Done | Documented in `CURRENT_STATUS.md`; no retro issue |
| M4 NumPy search E2E | ✅ Done | Documented in `CURRENT_STATUS.md`; no retro issue |
| FAISS adapter | ❌ Deferred | M6 — not started; requires explicit scoped approval |

## Post-cleanup board state

As of `main` at `b096fcb`:

- **EPIC 2 runtime and E2E proof** — completed and documented (`CURRENT_STATUS.md`, `EPIC_2_SEMANTIC_SEARCH_SPEC.md`)
- **sqlite-vec campaign** — Phases 1–8 closed (PRs #47–#53); default backend remains `numpy`
- **Search quality campaign** — closed (PR #54, merged 2026-05-31); Tier A gates PASS
- **EPIC 3 foundation** — hybrid ranking score contract merged via PR #23
- **Docs sync** — SkillForge routing via PRs #16/#19; bootstrap validation via PR #20; backlog board via PRs #21/#24/#26
- **Test hardening** — CLAP unavailable-backend search path via PR #22 (`tests/test_search.py`)
- **Dependabot backlog** — PRs #2–#9 merged with CI validation; audio-related bumps (#6, #7, #9, #5) validated with synthetic WAV smoke where applicable
- **Cursor Cloud onboarding** — PR #17 merged (`AGENTS.md` dev environment instructions)
- **Cursor subagents** — PR #25 merged (`.cursor/agents/sample-brain-*.md`)
- **E2E milestone closures** — #27/#28/#29/#30 are closed via PR #32/#34/#36/#35; PR #33 merged as schema bugfix follow-up; PR #37 merged as config/export contract fix
- **Current board reality** — no open product issues; 2 open Dependabot PRs (#63, #64)

Local backlog item numbers below are **planning IDs**, not GitHub issue numbers (except where cross-referenced).

## EPIC 0: Repository Hygiene & Documentation

### 1. docs: rewrite README for sample-brain product vision
- **Status:** ✅ completed (EPIC 0, further expanded in Documentation Architecture Sprint)
- Labels: `docs`, `product`, `high-priority`
- Goal: Reposition `sample-brain` as a local-first AI sample intelligence tool for producers.
- Context: Current README is incomplete, links to missing files, and ends with placeholder text.
- Acceptance criteria: ✅ All met — README describes current pipeline in quickstart, target pipeline via doc links, no overclaims, no broken links.
- Dependencies: none
- Priority: P0

### 2. docs: add architecture overview and module boundaries
- **Status:** ✅ completed (via `docs/TARGET_ARCHITECTURE.md`)
- Labels: `docs`, `architecture`, `high-priority`
- Goal: Document current module boundaries and target local-first architecture.
- Acceptance criteria: ✅ All met — current and target architecture documented, SQLite/FAISS/CLAP/FastAPI stack named, FL Studio export as near-term core.
- Dependencies: Issue 1
- Priority: P0

### 3. docs: add local MCP setup guide
- **Status:** ✅ completed (via `docs/MCP_SETUP.md`)
- Labels: `docs`, `mcp`, `onboarding`
- Goal: Document how `sample-brain` is exposed to the local ChatGPT MCP workflow.
- Context: The repo is being added as a dedicated MCP root/target in the local server.
- Acceptance criteria: ✅ All met — canonical checkout path, MCP root key, validation commands, and safety notes documented in `docs/MCP_SETUP.md`.

### 4. chore: remove generated/local artifacts from repository tracking
- **Status:** ✅ completed
- Labels: `chore`, `repo-hygiene`, `high-priority`
- Goal: Stop tracking generated, local-only, and environment-specific artifacts.
- Acceptance criteria: ✅ All met — `.venv/`, `data/catalog.db`, reports untracked; `.gitignore` tightened.
- Dependencies: none
- Priority: P0

### 5. chore: validate repository bootstrap from fresh clone
- **Status:** ✅ completed (via PR #20 — `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, bootstrap validation in `CURRENT_STATUS.md`)
- Labels: `chore`, `setup`, `testing`
- Goal: Ensure a fresh clone can be set up deterministically.
- Acceptance criteria: ✅ All met — fresh-clone setup, dependency path, and contributor verification commands documented; bootstrap validation evidence recorded.

### 6. bug: verify and repair src/analyze.py if it contains patch/diff artifacts
- **Status:** ✅ completed
- Labels: `bug`, `python`, `high-priority`
- Goal: Restore `src/analyze.py` to a valid Python module.
- Acceptance criteria: ✅ All met — `src/analyze.py` is clean Python; BPM normalization and CLI integration work.
- Dependencies: none
- Priority: P0

## EPIC 1: Config & Project Setup

### 7. refactor: replace hardcoded sample roots with configurable library profiles
- **Status:** ✅ completed on `main` (profile-based config active)
- Labels: `refactor`, `config`, `pipeline`
- Goal: Make sample library roots configurable through named profiles.
- Context: Current scan flow appears to rely on hardcoded or fragile path assumptions.
- Acceptance criteria:
  - library roots move out of hardcoded logic
  - named profiles can be selected without code edits
  - existing scan flow still works with a default profile
- Technical notes: Keep local-first behavior; avoid cloud config dependencies.
- Dependencies: Issue 5
- Priority: P1

### 8. feat: add project configuration file for library roots, FL Studio path and model settings
- **Status:** ✅ completed on `main` (config profiles + CLI/env precedence)
- Labels: `feat`, `config`, `mvp`
- Goal: Introduce a project-level configuration file.
- Context: The tool needs explicit configuration for libraries, export paths, and future model settings.
- Acceptance criteria:
  - config file schema is documented
  - library roots and FL Studio export path are configurable
  - placeholder model settings for future embedding backend exist
- Technical notes: Prefer a simple local-first format such as YAML or TOML.
- Dependencies: Issue 7
- Priority: P1

### 9. test: add minimal audio fixture set for scanner/analyzer tests
- Labels: `test`, `audio`, `pipeline`
- Goal: Add a tiny, legally safe fixture set for repeatable tests.
- Context: Scanner and analyzer work is difficult to validate without stable fixtures.
- Acceptance criteria:
  - small fixture set exists in repo or reproducible fixture generation is documented
  - fixtures cover at least one loop, one one-shot, and one tonal sample
  - fixtures are used by at least one scanner/analyzer test path
- Technical notes: Avoid large binaries.
- Dependencies: Issues 5 and 6
- Priority: P1

## EPIC 2: Semantic Search Foundation

### 10. db: add embedding model and sample embedding tables
- **Status:** ✅ completed on `main`
- Context: Semantic search requires persistent embedding storage and versioning.
- Acceptance criteria:
  - schema includes embedding metadata and per-sample embeddings
  - model/version provenance is stored
  - migration path is documented
- Technical notes: Keep SQLite as the catalog source of truth.
- Dependencies: Issue 8
- Priority: P1

### 11. feat: implement CLAP embedding backend abstraction
- **Status:** ✅ completed — GitHub #11 (runtime env) and #12 (text embed smoke) closed; backend on `main`
- Context: The target architecture calls for local-first semantic search.
- Acceptance criteria:
  - backend interface supports text and audio embedding
  - CLAP-backed implementation exists behind the abstraction
  - config can select or disable the backend
- Technical notes: Design for later model substitution.
- Dependencies: Issues 8 and 10
- Priority: P1

### 12. feat: implement batch embedding worker
- **Status:** ✅ completed on `main` — M3 persistence smoke PASS (external DB via `SAMPLE_BRAIN_DB_PATH`)
- Context: Embedding generation should be decoupled from scan/analyze steps.
- Acceptance criteria:
  - worker can process pending samples in batches
  - failures are recorded and resumable
  - progress is observable through logs or status output
- Technical notes: Avoid loading entire libraries into memory.
- Dependencies: Issues 10 and 11
- Priority: P1

### 13. feat: implement vector index build module
- **Status:** ✅ NumPy `.npz` default + sqlite-vec `vec0` opt-in on `main` (PRs #49–#51); FAISS superseded by ADR-0004
- Labels: `feat`, `search`, `indexing`
- Goal: Build a local vector index from stored embeddings.
- Context: Local-first search needs a performant local vector index.
- Acceptance criteria:
  - index build command/module exists — ✅ `index_build` with NumPy `.npz`
  - index can be rebuilt from embedding tables — ✅
  - index location and lifecycle documented — ✅ artifact policy
- Technical notes: NumPy is default search backend; sqlite-vec via `index_build --search-backend sqlite-vec`. FAISS not implemented; ADR-0004 is index strategy.
- Dependencies: Issue 12
- Priority: P1

### 14. feat: implement text-to-sample semantic search
- **Status:** ✅ NumPy E2E smoke PASS (M4) — production hardening remains future work
- Context: This is a core step toward a semantic sample copilot.
- Acceptance criteria:
  - text query embeds through selected backend — ✅ CLAP smoke
  - index returns ranked sample candidates — ✅ NumPy search
  - result set includes metadata for producer workflows — 🔶 partial
- Technical notes: Keep API/UI assumptions minimal in first iteration.
- Dependencies: Issues 11, 12, 13
- Priority: P1

### 15. feat: implement audio-to-audio similarity search
- Labels: `feat`, `search`, `audio`
- Goal: Find similar samples from an input audio reference.
- Context: Producer workflow benefits from matching by sound, not just text.
- Acceptance criteria:
  - input audio can be embedded and searched
  - similarity results are returned from local index
  - unsupported input cases fail clearly
- Technical notes: Reuse backend abstraction and index path from text search.
- Dependencies: Issues 11, 12, 13
- Priority: P2

## EPIC 3: Hybrid Ranking & Recommendation

### 16. feat: combine vector similarity with BPM, key, type and duration filters
- Labels: `feat`, `ranking`, `search`
- Goal: Blend semantic similarity with structured music metadata.
- Context: Producers need more than nearest-neighbor vectors.
- Acceptance criteria:
  - filters for BPM, key, type, and duration influence ranking or selection
  - search behavior is documented and testable
  - semantic-only and hybrid modes are distinguishable
- Technical notes: Start simple and make weighting configurable later.
- Dependencies: Issues 14 and 15
- Priority: P2

### 17. feat: add recommendation mode for compatible samples
- Labels: `feat`, `recommendation`, `producer-workflow`
- Goal: Suggest compatible samples for a given context or reference sample.
- Context: Long-term positioning includes a sample copilot, not just search.
- Acceptance criteria:
  - recommendation mode accepts sample or project context
  - results consider compatibility signals
  - output is distinguishable from direct search results
- Technical notes: Keep first version deterministic and local-first.
- Dependencies: Issue 16
- Priority: P2

### 18. feat: add search logging and feedback signals
- Labels: `feat`, `observability`, `search`
- Goal: Capture local feedback signals to improve ranking later.
- Context: Recommendation quality needs usage feedback over time.
- Acceptance criteria:
  - local search interactions can be logged safely
  - feedback model is documented
  - logging remains local-only by default
- Technical notes: Avoid network assumptions and personal data leakage.
- Dependencies: Issues 14 and 16
- Priority: P3

## EPIC 4: Local API & UI

### 19. feat: add FastAPI local service
- Labels: `feat`, `api`, `local-first`
- Goal: Introduce a local service layer around catalog and search operations.
- Context: The target architecture calls for FastAPI as the local interface.
- Acceptance criteria:
  - FastAPI app can boot locally
  - health endpoint exists
  - service can be configured without cloud dependencies
- Technical notes: Keep API narrow and local-first.
- Dependencies: Issues 8 and 10
- Priority: P2

### 20. feat: expose scan/analyze/embed/search endpoints
- Labels: `feat`, `api`, `pipeline`
- Goal: Expose the main pipeline capabilities through local endpoints.
- Context: A UI or other local clients need stable access paths.
- Acceptance criteria:
  - endpoints exist for scan, analyze, embed, and search
  - long-running operations have a clear status strategy
  - API contracts are documented
- Technical notes: Avoid mixing orchestration with UI assumptions.
- Dependencies: Issues 19, 12, 14
- Priority: P2

### 21. ui: define first desktop UI concept for search and preview
- Labels: `ui`, `design`, `planning`
- Goal: Define the first viable local desktop UI concept.
- Context: A later React/Tauri UI should follow a clear producer workflow.
- Acceptance criteria:
  - user flows for search, inspect, preview, and export are documented
  - scope boundaries for first UI are explicit
  - non-goals are listed
- Technical notes: Stay aligned with local-first constraints.
- Dependencies: Issues 1, 2, 20
- Priority: P3

### 22. ui: implement local sample preview and result inspector
- Labels: `ui`, `feat`, `desktop`
- Goal: Provide a first local result inspector with sample preview.
- Context: Search becomes much more useful when results can be auditioned quickly.
- Acceptance criteria:
  - result metadata can be inspected locally
  - sample preview works for supported formats
  - implementation remains local-first
- Technical notes: Defer advanced DAW coupling.
- Dependencies: Issues 20 and 21
- Priority: P3

## EPIC 5: FL Studio / DAW Workflow

### 23. feat: improve FL Studio tag export documentation and tests
- Labels: `feat`, `docs`, `fl-studio`
- Goal: Stabilize the current strongest integration point.
- Context: FL Studio export is the current near-term product anchor.
- Acceptance criteria:
  - export behavior is documented clearly
  - basic tests or validation fixtures cover export output
  - edge cases are listed
- Technical notes: Keep FL Studio as short-term primary DAW integration.
- Dependencies: Issues 5 and 9
- Priority: P1

### 24. feat: add project-context search fields: BPM, key, target type
- Labels: `feat`, `search`, `fl-studio`
- Goal: Support search constrained by active project needs.
- Context: Producer workflow often starts from target BPM/key/type.
- Acceptance criteria:
  - BPM, key, and target type can be passed into search or recommendation flow
  - behavior is documented and testable
  - defaults are sensible when fields are missing
- Technical notes: This should integrate with hybrid ranking.
- Dependencies: Issues 16 and 20
- Priority: P2

### 25. research: evaluate DAW integration paths for FL Studio, Ableton and Reaper
- Labels: `research`, `integration`, `daw`
- Goal: Compare realistic local integration approaches across DAWs.
- Context: FL Studio is near-term core, but future workflow may span other DAWs.
- Acceptance criteria:
  - research note compares viable integration paths
  - risks, complexity, and sequencing are documented
  - near-term recommendation is explicit
- Technical notes: No plugin claims before validation.
- Dependencies: Issue 23
- Priority: P3

## EPIC 6: Re-imagine Light

### 26. research: define DSP-based re-imagine scope
- Labels: `research`, `dsp`, `creative-tools`
- Goal: Define a bounded first scope for local variant generation.
- Context: "Re-imagine" should start as a focused local augmentation tool, not an overclaimed co-producer.
- Acceptance criteria:
  - first candidate transformations are listed and justified
  - constraints and non-goals are explicit
  - relationship to the main catalog pipeline is documented
- Technical notes: Keep it separate from semantic search foundation work.
- Dependencies: none
- Priority: P3

### 27. feat: prototype pitch/time/stretch/reverse/slice variant generator
- Labels: `feat`, `dsp`, `prototype`
- Goal: Build a narrow prototype for generated sample variants.
- Context: This is the smallest practical step toward a "re-imagine" workflow.
- Acceptance criteria:
  - at least a small set of DSP transforms is implemented
  - outputs are deterministic enough to review
  - generation can be run locally on demand
- Technical notes: Avoid committing generated audio outputs.
- Dependencies: Issue 26
- Priority: P3

### 28. feat: cache and export generated variants
- Labels: `feat`, `dsp`, `export`
- Goal: Persist useful generated variants and route them into existing workflows.
- Context: Generated audio is only useful if it can be reused and exported cleanly.
- Acceptance criteria:
  - generated variants can be cached locally
  - export path is documented
  - local cache/artifact rules are defined to avoid accidental commits
- Technical notes: Align artifact handling with Epic 0 hygiene rules.
- Dependencies: Issue 27
- Priority: P3

## Future Documentation (vorgemerkt)

### 29. docs: write bootloader and context strategy
- **Status:** ✅ closed (GitHub #29; implemented and merged via PR #36 `e7d59c7`)
- Labels: `docs`, `architecture`, `planning`
- Goal: Define how `sample-brain` bootstraps context and handles available tools, knowledge files, and MCP capabilities.
- Context: The project works through multiple MCP gateways; the bootloader decides what context to inject before any command runs.
- Acceptance criteria:
  - Strategy document names the bootloader layer and its responsibilities
  - Context-injection pipeline is described (global, repo, command-level)
  - Relationship to AGENTS.md and SKILL.md conventions is documented
- Priority: P2

### 30. docs: write sample-brain skills spec
- **Status:** ✅ closed (GitHub #30; implemented and merged via PR #35 `05135a1`)
- Labels: `docs`, `skills`, `planning`
- Goal: Define custom skills that `sample-brain` exposes to MCP agents for common operations (scan, analyze, search, export).
- Context: Skills provide structured tool definitions and instructions for LLM agents working with the repo.
- Acceptance criteria:
  - Skill categories and scope are named (scanning, analysis, search, maintenance)
  - Each skill has defined inputs, outputs, and guardrails
  - Relationship to checklists/workflows and the AGENTS.md contract is documented
- Priority: P2
