# CURRENT_STATUS

**Last reconciled:** 2026-08-18

## Truth Rule

This file is a durable orientation snapshot, not a substitute for live state.

Before making a current-state decision, read in this order:

1. GitHub live: open issues, PRs, checks, reviews, default branch.
2. Repo live: branch/HEAD, diff, files, tests.
3. Canonical specs and ADRs.
4. This status file and other roadmap/ledger documents.

Do **not** infer current issue counts, PR counts, or the current `main` SHA from this file. Those values change too often and previously made this document actively misleading.

## Current Operational Picture

At the 2026-08-18 reconciliation, the durable open work was:

- [#405](https://github.com/jannekbuengener/sample-brain/issues/405) — **P0 repository safety:** enforce technical protection for `main`. The desired rules are decided; the current bounded operator cannot mutate repository protection settings.
- [#392](https://github.com/jannekbuengener/sample-brain/issues/392) — **repository hygiene:** remove validated historical branches/worktrees and restore a clean canonical `main` checkout without discarding unique local work.
- [#74](https://github.com/jannekbuengener/sample-brain/issues/74) — **upstream tracker:** wait for a stable, documented sqlite-vec ANN release. Do not build a private ANN replacement merely to close this tracker.
- [#375](https://github.com/jannekbuengener/sample-brain/issues/375) — **future product work:** optional hidden hierarchical element detail below simple performance groups. It is intentionally not a current blocker.

Transient PRs are intentionally not frozen into this document. Query GitHub live.

## Shipped System on `main`

### Core library pipeline

- `scan` — recursively discovers local audio and registers catalog metadata.
- `analyze` — extracts BPM/key/loudness/brightness/MFCC/chroma-style feature data from catalog entries.
- rule-based/autotype classification.
- FL Browser tag export as a legacy/fallback integration path.
- profile/config resolution and local SQLite catalog support.

### Search and retrieval

- optional CLAP text/audio embeddings.
- NumPy search backend as the default.
- optional sqlite-vec backend/cache.
- search-quality fixtures, benchmarks, and regression gates.
- DB integrity/diagnostic tooling.

### Workbench and native audio

- local tkinter Workbench with library browsing, analysis, preview, waveform, cue/loop/attack editing, playlists, matching helpers, recording, and native transport integration.
- native audio core and deterministic transport/key-lock test surface.
- Quick Capture voice-to-issue flow using local recording + local whisper.cpp + GitHub CLI. Private/local path and obvious secret redaction is applied before public issue creation; see [`docs/QUICK_CAPTURE.md`](../docs/QUICK_CAPTURE.md).

### Track deconstruction and performance packs

The old statement that Track Deconstruction had "no runtime implementation on `main`" is obsolete.

Runtime/contracts now exist for the deconstruction chain, including:

- canonical audio/timebase and Track Map.
- BeatGrid, StructureV1, section signals, arrangement classification.
- loop/section candidate generation and scoring.
- deterministic asset rendering/re-analysis.
- optional stem runtime/cache/provenance.
- headless deconstruction orchestration and resume.
- Performance Pack manifest/layout/import integration.

Relevant current code includes `src/deconstruct.py`, `src/deconstruct_resume.py`, `src/performance_pack.py`, `src/performance_pack_import.py`, `src/structure_v1.py`, `src/loop_candidates.py`, `src/section_candidates.py`, and the stem modules. The canonical contracts live under `docs/`.

## Reliability and Security Hardening — 2026-08-18

Recent verified deliveries include:

- PR #406 — SQLite foreign-key enforcement on every connection.
- PR #408 — Quick Capture runtime repaired and aligned with local whisper.cpp / `gh` contracts.
- PR #409 — Jules REST session-create prompts redacted before external submission.
- PR #410 — canonical-audio missing-source error normalized before third-party loaders.
- PR #411 — optional CLAP/PyTorch availability probing isolated from the core process.
- PR #412 — **Full core pytest** PR gate added, including GUI execution under Xvfb and a post-test dirty-tree guard.
- PR #413 — scan filesystem/hash work moved outside long write transactions; unreadable files no longer abort the whole scan.
- PR #414 — analysis candidates are primary-key paged and expensive feature extraction runs outside SQLite write transactions before short batch upserts.

For anything newer, query GitHub live rather than extending this list from memory.

## CI / Validation Contract

Pull requests now have a repository-wide `Full core pytest` job in addition to focused jobs and security checks. The full job:

- installs the normal core runtime/test dependencies,
- verifies Tk under a virtual display,
- runs the complete `tests/` suite,
- fails if tests leave tracked or unignored repository state behind.

CodeQL, Gitleaks, Dependency Review, Python smoke, and focused Core pytest jobs remain part of the normal GitHub evidence surface.

**Important:** CI existence is not the same as branch protection. Until #405 is completed, the repository still lacks the intended technical enforcement preventing a direct bypass of PR/check gates.

## Known Product / Operational Constraints

- Core processing remains local-first. Private samples, recordings, databases, indexes, model caches, and local paths do not belong in Git.
- sqlite-vec remains opt-in; NumPy remains the default search path until stable ANN and measured gates justify a change.
- optional CLAP/stem dependencies must fail closed and must not make the core CLI/import path require heavy ML packages.
- current Demucs-family weight usage remains a separate licensing/commercialization concern; do not treat technical availability as commercial permission.
- repository/worktree cleanup remains open under #392; do not use old local branches as current truth.

## Key Canonical References

- [`knowledge/project/PROJECT_META.md`](project/PROJECT_META.md)
- [`docs/PRODUCT_REQUIREMENTS.md`](../docs/PRODUCT_REQUIREMENTS.md)
- [`docs/SYSTEM_REQUIREMENTS.md`](../docs/SYSTEM_REQUIREMENTS.md)
- [`docs/TARGET_ARCHITECTURE.md`](../docs/TARGET_ARCHITECTURE.md)
- [`docs/DATA_AND_ARTIFACT_POLICY.md`](../docs/DATA_AND_ARTIFACT_POLICY.md)
- [`docs/adr/ADR-0004-sqlite-vec-search-backend.md`](../docs/adr/ADR-0004-sqlite-vec-search-backend.md)
- [`docs/adr/ADR-0005-search-quality-evaluation.md`](../docs/adr/ADR-0005-search-quality-evaluation.md)
- [`docs/REALTIME_WORKBENCH_SCOPE.md`](../docs/REALTIME_WORKBENCH_SCOPE.md)

## Agent Guidance

If this file conflicts with live GitHub or repo evidence, **live evidence wins**. Update this file only when the durable system picture changes; do not turn it back into a historical issue dump.
