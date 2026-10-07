# CURRENT_STATUS

**Last reconciled:** 2026-10-07

## Truth Rule

This file is a durable orientation snapshot, not a substitute for live state.

Before making a current-state decision, read in this order:

1. GitHub live: open issues, PRs, checks, reviews, default branch.
2. Repo live: branch/HEAD, diff, files, tests.
3. Canonical specs and ADRs.
4. This status file and other roadmap/ledger documents.

Do **not** infer current issue counts, PR counts, or the current `main` SHA from this file. Those values change too often and previously made this document actively misleading.

## Current Operational Picture

At the 2026-10-07 reconciliation, durable system state is as follows. This is orientation, not a frozen issue count; query GitHub before execution. Open issues are not automatically active work.

### Current product navigation (Edit → Arrangement → later Live)

- Product sequence authority: [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076) + [`docs/PRODUCT_WORKFLOW_CANON.md`](../docs/PRODUCT_WORKFLOW_CANON.md).
- Arrangement owner: [#679](https://github.com/jannekbuengener/sample-brain/issues/679) — **ACTIVE** (Owner-reactivated 2026-10-07).
- Later Live: [#1088](https://github.com/jannekbuengener/sample-brain/issues/1088) — parked until Arrangement delivery + Owner gates.
- Edit tools / Live Kit: [#1069](https://github.com/jannekbuengener/sample-brain/issues/1069)–[#1073](https://github.com/jannekbuengener/sample-brain/issues/1073), [#1077](https://github.com/jannekbuengener/sample-brain/issues/1077).
- Closed [#691](https://github.com/jannekbuengener/sample-brain/issues/691) is delivered historical authority, not an active parent. Closed [#494](https://github.com/jannekbuengener/sample-brain/issues/494) and [#703](https://github.com/jannekbuengener/sample-brain/issues/703) are historical governance evidence.
- #905 Single Workspace exclusive-nav thesis is historical / superseded on conflict; progressive disclosure evidence remains in [`docs/WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md`](../docs/WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md).

### Shipped — Workbench Library / Live Kit runtime capabilities (historical “Screen 1” delivery)

Workbench Library/Live Kit surfaces on `main` include Calm/Clean Start, compact Browser, elastic layout, Display Preferences, Browser column resize, bidirectional sample DnD (#768 DONE), Theme Authority (#785 DONE), Brand/Motion analysis surface (#786 DONE), and selection-steal hardening. `LOCK_PYSIDE6_QML` remains the renderer contract for any future Workbench visuals. Historical “Screen-1” issue/CLI naming remains delivery evidence only.

### Shipped — Channel Rack / Pattern domain (historical “Screen 2” delivery)

- [#675](https://github.com/jannekbuengener/sample-brain/issues/675) / [#678](https://github.com/jannekbuengener/sample-brain/issues/678) — Channel Rack domain foundations and QML delivery. Foundations and QML (#678 / PR #755) are **DONE**; parent epic #675 is CLOSED. Do not reopen without explicit Owner-GO. Product placement: Arrangement workflow capability (not a top-level mode).

### Parked / external-dependency / R&D tracks

- [#697](https://github.com/jannekbuengener/sample-brain/issues/697) — Panel reordering. **PARKED / RESEARCH ONLY**; explicit reactivation required. Do not implement opportunistically. (Note: Edit docking under #1069 is a separate Owner-approved Edit path.)
- Closed [#468](https://github.com/jannekbuengener/sample-brain/issues/468) — Techno listening/stem pilot. **CLOSED / not_planned** (historical). Existing canary/listening evidence remains historically valid; **do not reactivate** Listening-/Stem-/Demucs-canaries, Track-02–05 runs, or scorecard campaign without explicit Owner reactivation.
- [#469](https://github.com/jannekbuengener/sample-brain/issues/469) — VST3 integration is explicitly **parked / not active**.
- [#74](https://github.com/jannekbuengener/sample-brain/issues/74) — upstream sqlite-vec ANN readiness tracker only; no private ANN replacement.
- [#615](https://github.com/jannekbuengener/sample-brain/issues/615) / [#620](https://github.com/jannekbuengener/sample-brain/issues/620) — Bitwig is an **R&D playground only**, not a Sample-Brain product integration decision.
- [#1088](https://github.com/jannekbuengener/sample-brain/issues/1088) — later **Live** performance perspective — **PARKED** until Arrangement delivery + Owner gates.
- [#680](https://github.com/jannekbuengener/sample-brain/issues/680) — vocal/beatbox → sample-pattern is **parked / future R&D**.

Closed historical work such as #392, #405, #503, #579, #196, #198, #73, #494, #691, and #703 remains useful evidence but is not active roadmap work.

Transient PRs and exact `main` SHA are intentionally not frozen here. Query GitHub live.

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

- The local Workbench and native-audio contracts are established. Current product navigation is Edit → Arrangement → later Live (#1075/#1076), not Screen 1/2/3 pages and not exclusive Single-Workspace-only modes.
- `LOCK_PYSIDE6_QML` remains the renderer canon for new Workbench visual/product work; `src/workbench_qml.py` is the canonical QML shell and Tkinter is legacy/fallback plus behavioral reference. Historical “Screen-1” naming remains delivery evidence.
- Workbench Theme Core + QML Theme Authority (#785) is **DONE**: preset-based dark appearance (Blood A default) with local custom themes; Display Preferences hosts Appearance without a second theme store.
- Workbench Brand/Motion analysis loading (#786) is **DONE**: brain on the analysis surface only, real `AnalysisUiState` progress projection, motion `on`/`reduced`/`off` with static fallback, no permanent header brand lockup; consumes `themeAuthority` tokens (no second color authority).
- Sample DnD (#768) and selection-steal hardening are integrated on `main`.
- Migration epic #503 and Calm Adaptive Workspace epic #691 are closed/delivered. Agents must not route new Workbench work through closed #691 as an active parent; open a new scoped issue under #1075 / #679 / #1069 instead.
- Channel Rack domain delivery on `main` includes session ownership, Pattern Core, sequencer scheduling/PCM, Channel Rack Python core, and Channel Rack QML (#678 / PR #755); parent epic #675 is CLOSED (historical “Screen 2” evidence).
- native audio core and deterministic transport/key-lock test surface remain part of the shipped foundation.
- Quick Capture voice-to-issue flow uses local recording + local whisper.cpp + GitHub CLI. Private/local path and obvious secret redaction applies before public issue creation; see [`docs/QUICK_CAPTURE.md`](../docs/QUICK_CAPTURE.md).

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

**Important:** The original unprotected-`main` gap tracked by #405 and the Phase-A ruleset migration tracked by #494 are historical/closed. Always read the live Ruleset state before making a merge-policy claim.

## Known Product / Operational Constraints

- Core processing remains local-first. Private samples, recordings, databases, indexes, model caches, and local paths do not belong in Git.
- sqlite-vec remains opt-in; NumPy remains the default search path until stable ANN and measured gates justify a change.
- optional CLAP/stem dependencies must fail closed and must not make the core CLI/import path require heavy ML packages.
- current Demucs-family weight usage remains a separate licensing/commercialization concern; do not treat technical availability as commercial permission.
- #392 repository/worktree cleanup is closed; historical local branches/worktrees are still never a substitute for live `main` evidence.

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
