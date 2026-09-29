# ACTIVE_ROADMAP

**Last reconciled:** 2026-09-29

## How to Use This Roadmap

This file describes durable priorities and sequencing. It deliberately does not mirror every GitHub issue, PR, commit SHA, or historical child issue.

For execution state, fetch GitHub and repo live first. If this roadmap conflicts with live evidence, live evidence wins.

## Current Priority Order

This roadmap intentionally groups durable work rather than mirroring every open issue.

### Active — Screen 1 product refinement

**[#691 — Calm Adaptive Workspace](https://github.com/jannekbuengener/sample-brain/issues/691)**

Current sequence is owned by #691 and its scoped children: shared visual acceptance, compact Browser/Harmonic density, elastic coupled panels, Clean Start/progressive disclosure, waveform rendering research, then display/startup preferences. Panel reordering remains parked until the layout foundation is accepted.

### Foundations ready / UI HOLD — Screen 2 Channel Rack

**[#675 — Live Kit → Channel Rack](https://github.com/jannekbuengener/sample-brain/issues/675)**  
**[#678 — Screen-2 QML Channel Rack](https://github.com/jannekbuengener/sample-brain/issues/678)**

The Python/session/sequencer foundations are already present. **Screen-2 QML #678 remains HOLD** under `docs/PRODUCT_WORKFLOW_CANON.md` until that gate is explicitly lifted. Keep Screen 2 distinct from the parked Screen-3 arrangement timeline (#679).

### Active — repository governance and reconciliation

- [#494](https://github.com/jannekbuengener/sample-brain/issues/494) — move from the temporary active main ruleset to the stable canon-aligned strict model without a protection gap.
- [#703](https://github.com/jannekbuengener/sample-brain/issues/703) — reconcile repository truth, docs, status, agents, CI, validation evidence and artifact hygiene.

### Active validation

- [#468](https://github.com/jannekbuengener/sample-brain/issues/468) — subjective listening validation for the existing Techno pilot assets.

### Watch / parked — do not promote implicitly

- [#74](https://github.com/jannekbuengener/sample-brain/issues/74) — wait for a stable documented sqlite-vec ANN release; NumPy remains the default search backend.
- [#469](https://github.com/jannekbuengener/sample-brain/issues/469) — VST3 product integration is parked.
- [#615](https://github.com/jannekbuengener/sample-brain/issues/615) — Bitwig work is R&D/playground only.
- [#679](https://github.com/jannekbuengener/sample-brain/issues/679) / [#680](https://github.com/jannekbuengener/sample-brain/issues/680) — future arrangement and input-mode ideas, not current delivery blockers.

Closed #392/#405/#503/#579/#196/#198/#73 are historical evidence, not current roadmap items.

## Shipped Foundations

The following are no longer roadmap work and should not be represented as open epics unless a new regression or extension is discovered.

### Library / analysis foundation

- profile-based local configuration.
- local SQLite catalog.
- sample scan and audio feature analysis.
- rule-based/autotype classification.
- FL Browser export as legacy/fallback integration.

### Search foundation

- CLAP adapter as an optional heavy backend.
- NumPy vector search as default.
- optional sqlite-vec cache/backend.
- search-quality fixtures and regression gates.
- DB/vector diagnostics and benchmark tooling.

### Workbench / realtime foundation

- local Tkinter Workbench as the shipped functional default and legacy/fallback path.
- preview/waveform/cue/loop/attack workflows.
- playlists/library views/matching helpers.
- native audio transport and recording path.
- Quick Capture local voice-to-GitHub-issue flow.

### Screen-1 QML foundation and current refinement

- `LOCK_PYSIDE6_QML` remains the decided renderer contract for new Screen-1 visual/product work.
- `src/workbench_qml.py` is the production QML shell and remains a thin renderer/intent layer over Python-authoritative Core/Controller/Audio/Catalog contracts.
- The original migration epic #503 is closed. Current refinement is tracked under #691; Tkinter remains legacy/fallback and behavioral reference, not the target for new Screen-1 visuals.

### Screen-2 foundation

- Session ownership, Pattern Core, sequencer scheduling/PCM and Channel Rack Python core are established.
- Product/UI delivery is tracked under #675/#678; the QML UI remains **HOLD** until the canonical gate is explicitly lifted.
- Screen 3 arrangement remains separately parked under #679; do not pull arrangement/timeline scope into Screen 2.

### Track deconstruction / performance packs

The former #227–#268 planning cluster has been implemented far beyond its old docs-only state. Runtime/contracts now cover the track-to-pack chain:

```text
canonical audio / Track Map
  -> BeatGrid + StructureV1
  -> arrangement signals / roles
  -> loop + section candidates / scoring
  -> deterministic rendered assets
  -> optional technical stems + cache/provenance
  -> headless deconstruction + resume
  -> Performance Pack layout / manifest / import
```

Use the current code and canonical contract docs as truth; do not resurrect the historical issue hierarchy as an active roadmap.

## Reliability Baseline Added 2026-08-18

The audit hardening campaign established a stronger operating baseline:

- SQLite foreign keys are enforced.
- Quick Capture is wired to real local recording/transcription and safer public issue creation.
- Jules REST create prompts are redacted before external submission.
- optional CLAP/PyTorch health checks cannot crash the core process during availability probing.
- missing canonical-audio sources fail with the Sample Brain contract before third-party loaders reinterpret the error.
- pull requests run **Full core pytest** under Linux/Xvfb and verify the repo remains clean after tests.
- scanning no longer holds a write transaction while probing/hashing files and no longer aborts on an unreadable sample.
- analysis reads are primary-key paged; expensive feature extraction runs outside SQLite write transactions and results are written in short batches.

Anything newer than this list must be verified live before being described as shipped.

## Product Direction

Sample Brain remains local-first. Product direction and product-body decisions are governed by the current canonical product documents, especially:

- [`knowledge/project/PROJECT_META.md`](project/PROJECT_META.md)
- [`docs/PRODUCT_REQUIREMENTS.md`](../docs/PRODUCT_REQUIREMENTS.md)
- [`docs/REALTIME_WORKBENCH_SCOPE.md`](../docs/REALTIME_WORKBENCH_SCOPE.md)
- [`docs/product/README.md`](../docs/product/README.md)

FL Browser export is a useful fallback path, not a reason to constrain the architecture to the old offline-only target. Conversely, the current Workbench/native-audio work does not authorize unrelated DAW/plugin scope expansion by itself.

## Constraints That Must Stay Visible

- private samples, recordings, DBs, indexes, model caches, embeddings, and local paths stay out of Git.
- optional ML/audio backends remain optional and fail closed.
- technical availability of stem models does not prove commercial licensing suitability.
- upstream dependency behavior must be checked against official docs before integration changes.
- repository hygiene and branch protection are operational gates, not cosmetic cleanup.

## When to Add New Roadmap Work

Create or promote a new roadmap item only when it is an independent work object with evidence and a clear exit condition. Do not reopen old epics merely because they contain useful historical discussion.
