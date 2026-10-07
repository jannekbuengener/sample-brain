# ACTIVE_ROADMAP

**Last reconciled:** 2026-10-07

## How to Use This Roadmap

This file describes durable priorities and sequencing. It deliberately does not mirror every GitHub issue, PR, commit SHA, or historical child issue.

For execution state, fetch GitHub and repo live first. If this roadmap conflicts with live evidence, live evidence wins. Open issues are not automatically active work.

## Current Priority Order

This roadmap intentionally groups durable work rather than mirroring every open issue.

### Active — Edit → Arrangement → later Live product track

Product-navigation authority is Edit → Arrangement → later Live ([#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076), [`PRODUCT_WORKFLOW_CANON.md`](../docs/PRODUCT_WORKFLOW_CANON.md)). Arrangement owner [#679](https://github.com/jannekbuengener/sample-brain/issues/679) is **ACTIVE**. Next Arrangement contract wave: [#1082](https://github.com/jannekbuengener/sample-brain/issues/1082)–[#1084](https://github.com/jannekbuengener/sample-brain/issues/1084). Later Live stays parked under [#1088](https://github.com/jannekbuengener/sample-brain/issues/1088).

Authorized historical Workbench UI delivery under [#691](https://github.com/jannekbuengener/sample-brain/issues/691) is complete on `main`. Closed #691 / #905-era exclusive Single Workspace nav are **historical evidence**, not the current exclusive product route. New Workbench product work requires a scoped child under [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#679](https://github.com/jannekbuengener/sample-brain/issues/679) / [#1069](https://github.com/jannekbuengener/sample-brain/issues/1069) plus live GitHub confirmation.

Closed governance/audit campaigns [#494](https://github.com/jannekbuengener/sample-brain/issues/494) and [#703](https://github.com/jannekbuengener/sample-brain/issues/703) are historical evidence, not active campaigns.

Do not restore Screen 1/2/3 page navigation or exclusive Single-Workspace-only modes as current authority.

### Shipped — Workbench Library / Live Kit cluster (historical “Screen 1”)

**[#691 — Calm Adaptive Workspace](https://github.com/jannekbuengener/sample-brain/issues/691)** (CLOSED / delivered)

Shipped Library/Live Kit runtime capabilities on `main` include Clean Start, compact Browser density, elastic coupled panels, Display Preferences, Browser column resize, bidirectional sample DnD (#768), Theme Authority (#785), Brand/Motion analysis surface (#786), and selection-steal hardening. Treat #691 as historical delivery authority only.

### Shipped — Channel Rack / Pattern domain (historical “Screen 2”)

**[#675 — Live Kit → Channel Rack](https://github.com/jannekbuengener/sample-brain/issues/675)**  
**[#678 — Screen-2 QML Channel Rack](https://github.com/jannekbuengener/sample-brain/issues/678)** (historical issue title)

Python/session/sequencer foundations and Channel Rack QML are **DONE** on `main` (PR #755; epic #675 CLOSED). Current product model places Channel Rack / Step Sequencer as Arrangement workflow capabilities (not top-level modes). Closed #908 is historical projection evidence. Arrangement owner [#679](https://github.com/jannekbuengener/sample-brain/issues/679) is **ACTIVE**; do not reopen Channel Rack product work without explicit Owner-GO.

### Watch / parked — do not promote implicitly

- [#697](https://github.com/jannekbuengener/sample-brain/issues/697) — **PARKED / RESEARCH ONLY**. Panel reordering research; no implementation without explicit reactivation. Do not treat open research as an Active product track.
- Closed [#468](https://github.com/jannekbuengener/sample-brain/issues/468) — **CLOSED / not_planned** (historical). Existing canary/listening evidence remains historically valid; do not reactivate Listening-/Stem-validation without explicit Owner GO.
- [#74](https://github.com/jannekbuengener/sample-brain/issues/74) — external upstream sqlite-vec ANN tracker only; NumPy remains the default search backend; no private ANN substitute.
- [#469](https://github.com/jannekbuengener/sample-brain/issues/469) — VST3 product integration is parked.
- [#615](https://github.com/jannekbuengener/sample-brain/issues/615) / [#620](https://github.com/jannekbuengener/sample-brain/issues/620) — Bitwig work is R&D/playground only; no product integration.
- [#1088](https://github.com/jannekbuengener/sample-brain/issues/1088) — later Live is **PARKED** until Arrangement delivery + Owner gates.
- [#680](https://github.com/jannekbuengener/sample-brain/issues/680) — vocal/beatbox input-mode remains future R&D — not a current delivery blocker.

Closed #392/#405/#503/#579/#196/#198/#73/#494/#703/#468 are historical evidence, not current roadmap items.

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

### Workbench QML foundation (delivered)

- `LOCK_PYSIDE6_QML` remains the decided renderer contract for new Workbench visual/product work.
- `src/workbench_qml.py` is the production QML shell and remains a thin renderer/intent layer over Python-authoritative Core/Controller/Audio/Catalog contracts.
- Migration epic #503 and follow-up epic #691 are both closed/delivered. New Workbench product visuals still use QML; Tkinter remains legacy/fallback and behavioral reference. Do not route new work through closed #691 as though it were still an active parent. Historical “Screen-1” naming remains evidence only.

### Channel Rack / Pattern foundation

- Session ownership, Pattern Core, sequencer scheduling/PCM, Channel Rack Python core, and Channel Rack QML are established on `main`.
- Product/UI tracks #675/#678 are **DONE** (PR #755; epic CLOSED). Do not reopen without explicit Owner-GO. Historical “Screen 2” wording is delivery evidence; current navigation is Edit → Arrangement → later Live.
- Arrangement owner [#679](https://github.com/jannekbuengener/sample-brain/issues/679) is **ACTIVE**; do not pull Arrangement timeline/domain into Rack foundation slices without the #679 child contracts.

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
