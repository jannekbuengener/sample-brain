# ACTIVE_ROADMAP

**Last reconciled:** 2026-08-18

## How to Use This Roadmap

This file describes durable priorities and sequencing. It deliberately does not mirror every GitHub issue, PR, commit SHA, or historical child issue.

For execution state, fetch GitHub and repo live first. If this roadmap conflicts with live evidence, live evidence wins.

## Current Priority Order

### P0 — Repository safety

**[#405 — Enforce branch protection on `main`](https://github.com/jannekbuengener/sample-brain/issues/405)**

Desired protection is already defined:

- PR required before merge.
- required checks enforced and branch kept up to date.
- admin/owner bypass prevented.
- force push and branch deletion blocked.
- conversation resolution / normal review hygiene enforced.

The current bounded operator cannot mutate repository protection settings. Do not redesign this issue; execute it when an appropriate repository-admin mutation surface is available.

### P1 — Repository hygiene

**[#392 — Branch/worktree cleanup](https://github.com/jannekbuengener/sample-brain/issues/392)**

Decisions are already locked. The remaining work is execution against validated local worktrees/branches without discarding unique dirty state.

Target state:

- canonical checkout on current `main`.
- only intentionally active worktrees/branches remain.
- historical remote branches removed after verification.
- stale/prunable worktree registrations cleaned normally, not forcibly.
- automatic post-merge branch cleanup enabled when repository settings can be changed safely.

### P1 — Upstream ANN watch only

**[#74 — sqlite-vec ANN readiness](https://github.com/jannekbuengener/sample-brain/issues/74)**

Current decision remains:

- stable NumPy search is the default.
- sqlite-vec remains optional.
- do not build a private ANN substitute merely to close this tracker.
- reopen implementation work only after upstream ships a stable, documented, benchmarkable ANN path for target platforms.

### Future — optional deeper performance detail

**[#375 — Hidden hierarchical element layer](https://github.com/jannekbuengener/sample-brain/issues/375)**

This is future product scope, not a current reliability blocker. The simple top-level producer view remains the default; deeper element separation must be evidence-based and truthful when eventually implemented.

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

- local tkinter Workbench.
- preview/waveform/cue/loop/attack workflows.
- playlists/library views/matching helpers.
- native audio transport and recording path.
- Quick Capture local voice-to-GitHub-issue flow.

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
