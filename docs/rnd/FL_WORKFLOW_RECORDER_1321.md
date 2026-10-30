# FL Workflow Zero-Touch Recorder (#1321)

Durable local research observer for parent [#1319](https://github.com/jannekbuengener/sample-brain/issues/1319).  
Depends on frozen Slice-1 contract from [#1320](https://github.com/jannekbuengener/sample-brain/issues/1320): `FL_WORKFLOW_SIGNAL_CONTRACT_PROVEN`.

**Exit:** `FL_WORKFLOW_ZERO_TOUCH_RECORDER_READY`

## Role

Dumb, robust, local, deterministic raw recorder.

- Collects and persists proven FL + Windows signals.
- Owns session lifecycle, spool ingest, crash recovery, retention, health.
- Does **not** classify producer flows, hot paths, bottlenecks, Edit↔Arrangement, ML, embeddings, AI, or reports (#1322 / #1323).

## Architecture

```text
FL Studio
   ↓
FL Device Script (SBWorkflowObserver)
   ↓
spool/fl-events.jsonl
                 \
                  → Recorder service → workflow.sqlite3
                 /
Windows capture
   ↓
spool/windows-events.jsonl
```

SQLite is durable truth. JSONL is transport/spool only.

## Local storage

Default root (never inside the repo, never `catalog.db` / `measurement.db`):

`%LOCALAPPDATA%/sample-brain/workflow-observer/`

```text
workflow.sqlite3
spool/fl-events.jsonl
spool/windows-events.jsonl
state/health.json
state/recorder.pid
logs/
```

Override root with env `SAMPLE_BRAIN_WORKFLOW_OBSERVER_DIR` (tests / agents).

## V1 signal set (frozen from #1320)

**FL:** `FOCUS_SURFACE`, `FOCUS_FORM`, `TRANSPORT`, `UNDO`, `HINT`, `REFRESH`, `DIRTY_MIXER`, `DIRTY_CHANNEL` (when observed), `BEAT_INDICATOR` (optional/cheap), `CLOCK_MARKER`, `PROBE_INIT` / `RECORDER_INIT`, `PROBE_DEINIT` / `RECORDER_DEINIT`

**Windows (FL-gated):** `FG`, `CLICK`, `DRAG`, `WHEEL`, `KEY_CMD`, `TEXT_ENTRY` (redacted), `CLOCK_MARKER`

Blind spots deferred (do not REA in this slice): Playlist active tool, Browser surface label, plugin identity.

## Privacy (fail-closed)

Never persist: typed character values, clipboard, screenshots, audio, continuous mouse-move streams, passwords, system-wide keyboard outside FL context, private FL project/sample paths, window texts with private filenames, unnecessary machine identity.

`TEXT_ENTRY` stores only `{redacted: true, mods?...}` — no character value. Windows input events only while FL is the relevant context (foreground gate).

## Time model

Preserve raw evidence per event:

- `source`, `source_seq`, `t_wall_ns`, `t_utc`, `t_mono_ns` (when present), `event_type`, redacted `props`

Do not bake in a fixed ~1.4 s marker skew correction. Optional measured clock calibration may live in session metadata only. Semantic fusion belongs to #1322.

## SQLite schema (v1)

- `meta` — `schema_version`, recorder version markers
- `sessions` — id, start/end, status, FL/MIDI versions, close reason, recovery marker, activity duration counters, quality JSON
- `events` — append-oriented rows with idempotent unique key `(source, source_seq, t_wall_ns)`
- `ingest_cursors` — per-spool byte offsets (crash-safe incremental ingest)
- `spool_quarantine` — malformed lines

No `segments` / `flows` / `hot_paths` tables.

## Session lifecycle

Zero-touch after one-time install:

```text
Windows login → recorder autostart
FL start → open session
FL background → capture FG; pause input classes
FL return → continue same session
FL exit → finalize session
recorder/FL crash → recover on restart
```

Focus interruptions do not open a new session. Activity counters distinguish active / listening (transport playing without input) / idle for duration accounting only — not workflow interpretation.

## MIDI

Respect proven venue ports: IN `Sample Brain Observer`, OUT `Sample Brain Observer Out`, FL port pair `240`. Diagnose missing/silent ports fail-soft; never mutate other MIDI devices; never auto-install drivers.

## Spool / recovery / retention

- Separate writers per JSONL file
- Incremental, idempotent ingest; tolerate partial final line; quarantine malformed rows
- Rotate/compact spool only after durable SQLite commit
- Raw retention default ~90 days; never prune open session; never touch repo files

## Integration boundary

Raw observer events must not enter ADR-0006 `measurement.db` or #1241 runtime diagnostics by default.

## Package location

`tools/fl_workflow_recorder/` — research tooling, not Sample Brain core product runtime.
