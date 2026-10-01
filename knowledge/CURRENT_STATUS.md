# CURRENT_STATUS

**Last reconciled:** 2026-10-01

## Truth Rule

This file is a durable orientation snapshot, not a substitute for live state.

Before making a current-state decision, read in this order:

1. GitHub live: open issues, PRs, checks, reviews, default branch.
2. Repo live: branch/HEAD, diff, files, tests.
3. Canonical specs and ADRs.
4. This status file and other roadmap/ledger documents.

Do **not** infer current issue counts, PR counts, or the current `main` SHA from this file. Those values change too often and previously made this document actively misleading.

## Current Operational Picture

At the 2026-10-01 reconciliation, durable system state is as follows. This is orientation, not a frozen issue count; query GitHub before execution. Open issues are not automatically active work.

### No currently authorized product implementation slice

- There is **no active Screen-1 product epic**. Closed [#691](https://github.com/jannekbuengener/sample-brain/issues/691) is delivered historical authority, not an active parent for new work. New Screen-1 work needs a **new scoped issue**.
- Closed [#494](https://github.com/jannekbuengener/sample-brain/issues/494) and [#703](https://github.com/jannekbuengener/sample-brain/issues/703) are historical governance/audit evidence, not active campaigns.
- Parked/open research issues (#697, #679, #680, #469, #615/#620, #74) are **not** Active product tracks.

### Shipped — Screen 1 runtime capabilities

Screen-1 on `main` includes Calm/Clean Start, compact Browser, elastic layout, Display Preferences, Browser column resize, bidirectional sample DnD (#768 DONE), Theme Authority (#785 DONE), Brand/Motion analysis surface (#786 DONE), and selection-steal hardening. `LOCK_PYSIDE6_QML` remains the renderer contract for any future Screen-1 visuals.

### Shipped — Screen 2 Channel Rack

- [#675](https://github.com/jannekbuengener/sample-brain/issues/675) / [#678](https://github.com/jannekbuengener/sample-brain/issues/678) — Screen 2 Channel Rack. Foundations and Screen-2 QML (#678 / PR #755) are **DONE**; parent epic #675 is CLOSED. Do not reopen without explicit Owner-GO.

### Parked / external-dependency / R&D tracks

- [#697](https://github.com/jannekbuengener/sample-brain/issues/697) — Panel reordering. **PARKED / RESEARCH ONLY**; explicit reactivation required. Do not implement opportunistically.
- [#468](https://github.com/jannekbuengener/sample-brain/issues/468) — Techno listening/stem pilot. Existing canary/listening evidence remains historically valid; the track is **PARKED / NOT ACTIVE**. No further Listening-/Stem-/Demucs-canaries, Track-02–05 runs, or scorecard campaign without explicit Owner reactivation.
- [#469](https://github.com/jannekbuengener/sample-brain/issues/469) — VST3 integration is explicitly **parked / not active**.
- [#74](https://github.com/jannekbuengener/sample-brain/issues/74) — upstream sqlite-vec ANN readiness tracker only; no private ANN replacement.
- [#615](https://github.com/jannekbuengener/sample-brain/issues/615) / [#620](https://github.com/jannekbuengener/sample-brain/issues/620) — Bitwig is an **R&D playground only**, not a Sample-Brain product integration decision.
- [#679](https://github.com/jannekbuengener/sample-brain/issues/679) — Screen 3 Arrangement is **parked / future product scope**.
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

- The local Workbench and native-audio contracts are established.
- `LOCK_PYSIDE6_QML` remains the renderer canon for new Screen-1 visual/product work; `src/workbench_qml.py` is the canonical QML Screen-1 shell and Tkinter is legacy/fallback plus behavioral reference.
- Screen-1 Theme Core + QML Theme Authority (#785) is **DONE**: preset-based dark appearance (Blood A default) with local custom themes; Display Preferences hosts Appearance without a second theme store.
- Screen-1 Brand/Motion analysis loading (#786) is **DONE**: brain on the analysis surface only, real `AnalysisUiState` progress projection, motion `on`/`reduced`/`off` with static fallback, no permanent header brand lockup; consumes `themeAuthority` tokens (no second color authority).
- Sample DnD (#768) and selection-steal hardening are integrated on `main`.
- Migration epic #503 and Calm Adaptive Workspace epic #691 are closed/delivered. Agents must not route new Screen-1 work through closed #691 as an active parent; open a new scoped issue instead.
- Screen-2 delivery on `main` includes session ownership, Pattern Core, sequencer scheduling/PCM, Channel Rack Python core, and Screen-2 QML Channel Rack (#678 / PR #755); parent epic #675 is CLOSED.
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
