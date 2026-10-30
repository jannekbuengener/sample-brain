# FL Workflow Deterministic Reconstruction (#1322)

Post-session analyzer for parent [#1319](https://github.com/jannekbuengener/sample-brain/issues/1319).  
Consumes the durable raw store from [#1321](https://github.com/jannekbuengener/sample-brain/issues/1321) (`FL_WORKFLOW_ZERO_TOUCH_RECORDER_READY`).  
Does **not** produce rolling product reports ([#1323](https://github.com/jannekbuengener/sample-brain/issues/1323)).

**Exit:** `FL_WORKFLOW_RECONSTRUCTION_READY`

## Role

Deterministic, offline, reproducible, re-runnable reconstruction:

```text
RAW EVENTS
→ NORMALIZED EVENTS
→ CORRELATED ACTIONS
→ ACTIVITY SEGMENTS
→ TRANSITIONS / PATHS / LOOPS / CHURN / UNDO / BOTTLENECK CANDIDATES
```

No ML, embeddings, LLM classification, cloud, screenshots/OCR, or FL reverse engineering.

## Truth levels

| Level | Meaning |
|-------|---------|
| `measured` | Directly observed in recorder (focus, transport, click, undo, …) |
| `correlated` | Multiple nearby measured events support one action/segment hypothesis |
| `interpreted` | Higher workflow meaning (browse, edit, arrangement, audition, …) |

Interpreted labels are **never** emitted as measured.

## Confidence

Deterministic rule outputs only: `high` | `medium` | `low`.

- **high** — measured FL surface + matching Windows action (or unambiguous transport/FG/undo)
- **medium** — strong temporal correlation without full semantic hint
- **low** — plausible interpretation with blind spots / missing surface

Low-confidence evidence must not be silently treated as hard truth downstream.

## Time correlation

Uses raw `t_wall_ns` (wall-clock cross-process authority from #1320).  
Does **not** apply a global ~1.4 s CLOCK_MARKER skew shift.

Versioned windows live in `fl_workflow_analyzer.rules` (`RULE_VERSION`):

- `CORRELATION_WINDOW_NS` = 500 ms (sized from nearest-event p50≈73 ms)
- `SURFACE_CONTEXT_STALE_NS` = 30 s (soft confidence downgrade; surface persists until next FOCUS / FL background)
- `IDLE_QUIET_NS` = 2 min (mirrors recorder)
- `BACKTRACK_MAX_RETURN_NS` = 30 s
- `CHURN_WINDOW_NS` = 60 s

## Idle / listening

```text
no relevant input + no relevant FL state change + transport not active → idle
transport playing + no mouse/keyboard → transport_listening (NOT idle)
```

Idle intervals are excluded from workflow path mining; listening remains production time.

## Blind spots (#1320)

Always retained in derived metrics:

1. Playlist active tool
2. Browser surface label
3. Plugin identity

Ambiguity → lower confidence + reason; never optimistic invention.

## Derived schema

Written into the same local `workflow.sqlite3` beside immutable raw tables:

- `analysis_runs` (analyzer version + rule version + source fingerprint)
- `derived_actions`, `derived_segments`, `derived_transitions`
- `derived_path_counts`, `derived_loops`, `derived_metrics`

Raw `events` / `sessions` are never updated by the analyzer. Reprocessing clears derived rows only.

## Package

`tools/fl_workflow_analyzer/` — research tooling, not Sample Brain core product runtime.

```powershell
cd <repo>\tools\fl_workflow_analyzer
python -m fl_workflow_analyzer analyze --clear-previous
python -m fl_workflow_analyzer status
```

## Privacy

Derived props keep only safe projections (surface names, booleans, hint classes, counts).  
No typed text, paths, project names, clipboard, or screenshots.

## Non-scope

- #1323 rolling reports / executive summaries
- Automatic product decisions
- Recorder redesign (#1321)
- UI/dashboard
- Sample Brain product behavior changes
