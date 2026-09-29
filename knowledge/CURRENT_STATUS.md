# CURRENT_STATUS

**Last reconciled:** 2026-09-29

## Truth Rule

This file is a durable orientation snapshot, not a substitute for live state.

Before making a current-state decision, read in this order:

1. GitHub live: open issues, PRs, checks, reviews, default branch.
2. Repo live: branch/HEAD, diff, files, tests.
3. Canonical specs and ADRs.
4. This status file and other roadmap/ledger documents.

Do **not** infer current issue counts, PR counts, or the current `main` SHA from this file. Those values change too often and previously made this document actively misleading.

## Current Operational Picture

At the 2026-09-29 reconciliation, GitHub live shows the following durable work classes. This is orientation, not a frozen issue count; query GitHub before execution.

### Active product/UI delivery

- [#691](https://github.com/jannekbuengener/sample-brain/issues/691) — **Screen 1 Calm Adaptive Workspace**. Follow-up product/UI work after the closed #503 migration baseline. Children cover compact density, clean start, elastic panel layout, waveform research, preferences and parked reordering.
- [#675](https://github.com/jannekbuengener/sample-brain/issues/675) / [#678](https://github.com/jannekbuengener/sample-brain/issues/678) — **Screen 2 Channel Rack** product track. Foundations are present; the QML UI remains **HOLD** under `PRODUCT_WORKFLOW_CANON.md` until its documented gate is explicitly lifted.
- [#679](https://github.com/jannekbuengener/sample-brain/issues/679) — **Screen 3 Arrangement** is parked/future product scope.
- [#680](https://github.com/jannekbuengener/sample-brain/issues/680) — vocal/beatbox → sample-pattern R&D is parked/future.

### Governance / audit / validation

- [#494](https://github.com/jannekbuengener/sample-brain/issues/494) — migrate the temporary active `main` ruleset to the stable canon-aligned strict ruleset. The older #405 branch-protection gap is closed and must not be treated as the current governance state.
- [#703](https://github.com/jannekbuengener/sample-brain/issues/703) — repository truth/drift/hygiene reconciliation campaign.
- [#468](https://github.com/jannekbuengener/sample-brain/issues/468) — remaining subjective listening validation for Techno performance assets.

### Parked / external-dependency / R&D tracks

- [#469](https://github.com/jannekbuengener/sample-brain/issues/469) — VST3 integration is explicitly **parked / not active**.
- [#74](https://github.com/jannekbuengener/sample-brain/issues/74) — upstream sqlite-vec ANN readiness tracker; no private ANN replacement.
- [#615](https://github.com/jannekbuengener/sample-brain/issues/615) and scoped children — Bitwig is an **R&D playground only**, not a Sample-Brain product integration decision.

Closed historical work such as #392, #405, #503, #579, #196, #198 and #73 remains useful evidence but is not active roadmap work.

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
- The original Screen-1 migration epic #503 is closed. Current Screen-1 refinement continues under #691; agents must not route new work through #503 as though it were still active.
- Screen-2 foundations now include session ownership, Pattern Core, sequencer scheduling/PCM and Channel Rack Python core; #675/#678 track the product/UI path, with QML UI still **HOLD** under the current product workflow canon.
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

**Important:** The original unprotected-`main` gap tracked by #405 is historical/closed. Current repository-governance migration is tracked by #494; always read the live Ruleset state before making a merge-policy claim.

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
