# Workbench Waveform Rendering Spike (#695)

**Status:** RESEARCH — not a production renderer switch  
**Issue:** [#695](https://github.com/jannekbuengener/sample-brain/issues/695)  
**Parent:** [#691](https://github.com/jannekbuengener/sample-brain/issues/691) Screen 1 Calm Adaptive Workspace  
**Harness:** `src/workbench_waveform_research.py`  
**Tests:** `tests/test_workbench_waveform_research_spike.py`

## Scope

Isolated Research-/Performance-Spike comparing four waveform rendering
strategies for Screen-1 browser rows. Production `QML_SOURCE` in
`src/workbench_qml.py` is **not** rewritten by this slice.

Protected contracts remain in force:

- PySide6 / Qt Quick / QML
- Compact Density (#692)
- Elastic Geometry (#694)
- Clean Start (#693/#725)
- Background (#731) / Color Tokens (#733/#734)
- Browser/Harmony virtualization (`reuseItems`)
- Existing preview/audio state and waveform envelope/cache contracts

Audio safety: the research renderer consumes synthetic envelopes only. It does
not own an audio clock, playback state, or analysis jobs.

## Candidates

| ID | Strategy | Spike implementation |
|----|----------|----------------------|
| A | CURRENT CANVAS BASELINE | QML `Canvas` vertical bars (matches production drawing model) |
| B | QT QUICK SHAPE | `Shape` + `PathSvg` bar path |
| C | CACHED STATIC | `QQuickImageProvider` bitmaps + separate playhead `Rectangle` |
| D | SCENE GRAPH GEOMETRY | Python `QQuickItem` + `QSGGeometry` lines |

Motion modes exercised in the harness (no Settings UI):

- `off` — static rows, no timer
- `reduced` — slower playhead interval
- `on` — playhead + light intensity modulation on the **active** row only

State rules enforced in the harness:

- normal / pooled / offscreen → no animation, no continuous repaint
- selected → quiet highlight
- playing → may own motion

## How to measure

```bash
# From a checkout that contains the research module:
set QT_QUICK_BACKEND=software
set SAMPLE_BRAIN_695_EVIDENCE=%TEMP%\sample-brain-695-evidence
python -m src.workbench_waveform_research
```

Focused pytest (no full 50k suite):

```bash
python -m pytest -q tests/test_workbench_waveform_research_spike.py
```

Evidence lands outside the repo by default (`%TEMP%/sample-brain-695-evidence`):

- `manifest-695.json` — timings, 50k probes, scorecard, EXIT classification
- `visuals/<renderer>/*.png` — normal / hovered / selected / active-preview

## Measurement matrix

For each candidate (where applicable):

- Initial render, scroll, scroll-burst
- Selection + keyboard navigation
- Preview start + active motion frame cost
- Delegate creation / reuse (`reuseItems`)
- 50k synthetic list virtualization (Canvas / Cached / QSG)
- Window sizes 1600×900, 1280×720, 1120×640
- Density: compact baseline from #692 (row height aligned to research harness)

## Measured results (local suite, `QT_QUICK_BACKEND=software`)

Representative medians from `manifest-695.json` (400-row window 1600×900 unless noted):

| Path | Initial ms | Scroll ms | Scroll-burst ms | Preview start ms | Active motion frame ms | 50k virt |
|------|------------|-----------|-----------------|------------------|------------------------|----------|
| Canvas | 153 / 79 | 44 / 61 | 314 / 296 | 22 / 63 | 0 / 0.12 | yes (39 delegates / 50k) |
| Shape | 305 / 283 | 61 / 67 | 445 / 405 | 22 / 22 | 0 / 1.95 | n/a (rejected early) |
| Cached static | 66 / 81 | 56 / 39 | 252 / 209 | 21 / 22 | 0 / 0.14 | yes (39 / 50k) |
| QSG geometry | 69 / … | 42 / … | 290 / … | 27 / … | 0 / 0.76 | yes (39 / 50k) |

Values shown as `motion=off / motion=on` where both were measured.

50k scroll (motion off): Canvas **42.6 ms**, Cached **60.1 ms**, QSG **60.6 ms** — all virtualized.

### Scorecard (from suite)

| | Canvas | Shape | Cached | QSG |
|--|--------|-------|--------|-----|
| PERFORMANCE | gut | schlecht | schlecht* | gut |
| SCROLL | gut | schlecht | schlecht* | gut |
| ACTIVE MOTION COST | gut | schlecht | mittel | schlecht |
| POOLING SAFETY | gut | gut | gut | gut |
| IMPLEMENTATION COMPLEXITY | niedrig | mittel | niedrig | hoch |
| MAINTAINABILITY | gut | mittel | gut | schlecht |
| VISUAL POTENTIAL | mittel | hoch | hoch | hoch |
| PRODUCTION RISK | niedrig | mittel | niedrig | hoch |

\*Cached scroll was competitive in some runs but slower than Canvas on the
50k and off-motion medians used for classification — not a clear upgrade.

Visual evidence (local, outside repo):
`%TEMP%/sample-brain-695-evidence/visuals/<renderer>/{normal,hovered,selected,active-preview}.png`

## EXIT CLASSIFICATION

**`KEEP_CANVAS_PLUS_ACTIVE_OVERLAY`**

Chosen by `classify_from_results` from measured evidence (not preference).
Post-sync onto current `main` does not reopen this classification unless new
live measurements refute it — they do not.

Rationale:

- Shape: higher scroll/initial cost and ~16× worse active-motion frame cost vs Canvas → rejected.
- Cached static: virtualizes cleanly and motion overlay is cheap, but did **not** beat Canvas scroll on the measured matrix / 50k probe → not selected as full-body replacement.
- QSG geometry: no ≥25% scroll win vs Canvas+Cached; higher maintainability/production risk → rejected for production now.
- Canvas remains the least-risk body renderer; active-row motion belongs in a thin overlay.

### Production recommendation (binding for follow-up)

- Existing Canvas waveform **body** stays for normal / selected / pooled rows.
- Separate **active preview overlay** layer for the playing row only.
- **Playhead** is the first production step (no intensity/glow in that first slice).
- Optional subtle intensity may come later on the same overlay mechanism.
- Motion only on the Playing row; offscreen/pooled → no timers, no continuous repaints.
- Modes `on` / `reduced` / `off` remain architecturally possible.
- No Settings UI in the follow-up slice; Motion Off must be able to disable the overlay.

## Recommended follow-up (smallest production slice — NOT in this PR)

**Screen-1 active waveform overlay — playhead on playing row**

Scope:

1. Production Canvas body unchanged.
2. Existing preview/audition state is the sole playback truth (no new audio clock, no new analysis).
3. Thin playhead overlay only on the active preview row.
4. Pooled/offscreen fail-closed (no animation / no timers).
5. Motion Off disables the overlay; Reduced can later reuse the same mechanism.
6. No intensity/glow scope in this first production slice unless technically required for the playhead itself.
7. No Settings UI.

## Non-scope (explicit for #695 research)

Final production renderer, spectrogram/FFT features, Live Kit redesign,
Screen 2, Settings/Motion Preference UI, panel reordering, audio engine
rewrite, heavy new dependencies, and the playhead overlay production slice above.
