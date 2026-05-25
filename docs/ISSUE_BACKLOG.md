# Issue Backlog

Prepared backlog only. No GitHub issues have been created yet.

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
- **Status:** ❌ open (not yet written)
- Labels: `docs`, `mcp`, `onboarding`
- Goal: Document how `sample-brain` is exposed to the local ChatGPT MCP workflow.
- Context: The repo is being added as a dedicated MCP root/target in the local server.
- Acceptance criteria:
  - Guide names canonical local checkout path
  - Guide shows MCP root key and validation commands
  - Guide warns against indexing sample libraries or committing generated artifacts during setup
- Technical notes: Keep the guide local-only and Windows-aware first.
- Dependencies: none
- Priority: P0

### 4. chore: remove generated/local artifacts from repository tracking
- **Status:** ✅ completed
- Labels: `chore`, `repo-hygiene`, `high-priority`
- Goal: Stop tracking generated, local-only, and environment-specific artifacts.
- Acceptance criteria: ✅ All met — `.venv/`, `data/catalog.db`, reports untracked; `.gitignore` tightened.
- Dependencies: none
- Priority: P0

### 5. chore: validate repository bootstrap from fresh clone
- **Status:** ❌ open (prerequisites #1 and #4 now done; ready to execute)
- Labels: `chore`, `setup`, `testing`
- Goal: Ensure a fresh clone can be set up deterministically.
- Context: Current repo state includes hygiene issues and unverified bootstrap assumptions.
- Acceptance criteria:
  - Fresh clone setup steps are documented
  - Required Python version and dependency install path are verified
  - Minimal happy-path commands run successfully or known gaps are documented
- Technical notes: Prefer Windows-first instructions, note cross-platform caveats separately.
- Dependencies: Issues 1 and 4 (both completed)
- Priority: P1

### 6. bug: verify and repair src/analyze.py if it contains patch/diff artifacts
- **Status:** ✅ completed
- Labels: `bug`, `python`, `high-priority`
- Goal: Restore `src/analyze.py` to a valid Python module.
- Acceptance criteria: ✅ All met — `src/analyze.py` is clean Python; BPM normalization and CLI integration work.
- Dependencies: none
- Priority: P0

## EPIC 1: Config & Project Setup

### 7. refactor: replace hardcoded sample roots with configurable library profiles
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
- Labels: `db`, `embeddings`, `foundation`
- Goal: Extend the catalog schema for embeddings and model metadata.
- Context: Semantic search requires persistent embedding storage and versioning.
- Acceptance criteria:
  - schema includes embedding metadata and per-sample embeddings
  - model/version provenance is stored
  - migration path is documented
- Technical notes: Keep SQLite as the catalog source of truth.
- Dependencies: Issue 8
- Priority: P1

### 11. feat: implement CLAP embedding backend abstraction
- Labels: `feat`, `embeddings`, `ml`
- Goal: Add a backend abstraction for audio/text embeddings with CLAP as the primary candidate.
- Context: The target architecture calls for local-first semantic search.
- Acceptance criteria:
  - backend interface supports text and audio embedding
  - CLAP-backed implementation exists behind the abstraction
  - config can select or disable the backend
- Technical notes: Design for later model substitution.
- Dependencies: Issues 8 and 10
- Priority: P1

### 12. feat: implement batch embedding worker
- Labels: `feat`, `embeddings`, `pipeline`
- Goal: Generate embeddings in batches for analyzed samples.
- Context: Embedding generation should be decoupled from scan/analyze steps.
- Acceptance criteria:
  - worker can process pending samples in batches
  - failures are recorded and resumable
  - progress is observable through logs or status output
- Technical notes: Avoid loading entire libraries into memory.
- Dependencies: Issues 10 and 11
- Priority: P1

### 13. feat: implement FAISS index build module
- Labels: `feat`, `search`, `indexing`
- Goal: Build a local FAISS index from stored embeddings.
- Context: Local-first search needs a performant local vector index.
- Acceptance criteria:
  - index build command/module exists
  - index can be rebuilt from embedding tables
  - index location and lifecycle are documented as local artifacts
- Technical notes: FAISS index files should not be committed.
- Dependencies: Issue 12
- Priority: P1

### 14. feat: implement text-to-sample semantic search
- Labels: `feat`, `search`, `ml`
- Goal: Support natural-language search over the sample catalog.
- Context: This is a core step toward a semantic sample copilot.
- Acceptance criteria:
  - text query embeds through the selected backend
  - FAISS returns ranked sample candidates
  - result set includes enough metadata for producer workflows
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
- **Status:** ❌ open
- Labels: `docs`, `architecture`, `planning`
- Goal: Define how `sample-brain` bootstraps context and handles available tools, knowledge files, and MCP capabilities.
- Context: The project works through multiple MCP gateways; the bootloader decides what context to inject before any command runs.
- Acceptance criteria:
  - Strategy document names the bootloader layer and its responsibilities
  - Context-injection pipeline is described (global, repo, command-level)
  - Relationship to AGENTS.md and SKILL.md conventions is documented
- Priority: P2

### 30. docs: write sample-brain skills spec
- **Status:** ❌ open
- Labels: `docs`, `skills`, `planning`
- Goal: Define custom skills that `sample-brain` exposes to MCP agents for common operations (scan, analyze, search, export).
- Context: Skills provide structured tool definitions and instructions for LLM agents working with the repo.
- Acceptance criteria:
  - Skill categories and scope are named (scanning, analysis, search, maintenance)
  - Each skill has defined inputs, outputs, and guardrails
  - Relationship to checklists/workflows and the AGENTS.md contract is documented
- Priority: P2
