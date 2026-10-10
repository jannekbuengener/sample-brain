# Workbench Internal Sample Drag Contract (#1072)

**Status:** Implemented — Python-owned Edit/Kit internal Sample DnD contract  
**Issue:** [#1072](https://github.com/jannekbuengener/sample-brain/issues/1072)  
**Parent:** [#1069](https://github.com/jannekbuengener/sample-brain/issues/1069)  
**Product path:** Edit / Kit → Arrangement → later Live ([#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) / [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076))

## Goal

Freeze one typed, deterministic **internal Sample drag** contract shared by Browser
and Harmonic Matches. Valid drop targets are limited to **currently visible
Edit Live-Kit assignment surfaces** backed by existing Python Add/Replace seams.

This issue does **not** implement QML drag visuals (#1073).

## Ownership

| Concern | Owner |
|---------|-------|
| Descriptor parse / sample resolution | Python (`src/workbench_internal_sample_dnd.py`) |
| Target validation / eligibility | Python |
| Add / Replace routing | Existing `LiveKitState.assign` via `live_kits_registry` |
| Feature availability | `WorkbenchFeatureSettings.internal_sample_dnd_enabled` (#910) |
| Replay / duplicate delivery | Python delivery-id guard |
| QML drag ghost / hit areas / highlights | Deferred to #1073 |

QML may later start a drag, transport a typed descriptor/intent, send a target
intent, and project the result. QML does **not** own musical Kit mutation.

## Product boundary

**In scope:** internal Sample drag inside Edit/Kit only.

| V1 sources | V1 target |
|------------|-----------|
| Browser / Library sample rows | Visible Live Kit assignment target |
| Harmonic Matches sample rows | (same) |

**Explicit non-targets:** hidden Channel Rack / Step Sequencer, Arrangement
timeline/blocks, later Live performance surface, arbitrary filesystem
destinations, external file DnD payloads (#768).

## Descriptor

Typed kind: `internal_sample`

Stable identity: canonical `WorkbenchRow.relative_path` (normalized, source-
independent). Browser and Harmony produce the **same descriptor type**.

Must **not** use as primary identity:

- QML row index
- visible display text
- private absolute machine paths
- raw PCM payload

Stale / deleted / unresolvable samples → controlled reject, no musical mutation,
no exception leak into UI. User-visible failure evidence never includes a
private absolute path.

## Target contract

Required target class: `live_kit_assignment`

Python validates group/slot against `LIVE_KIT_SLOT_MAPPING`, requires Live Kit
materialization, and requires the target to be marked visible. A QML string
alone cannot authorize a drop.

Rejected target identities include (non-exhaustive): `arrangement`, `live`,
`channel_rack`, `rack`, `step_sequencer`, unknown classes, hidden / non-
materialized Live Kit slots.

## Add / Replace

No second assignment engine. Reuse:

- empty valid slot → Add/Assign (`assign_sample_to_kit`)
- occupied valid slot → Replace (`replace_sample_assignment` → same assign seam)
- invalid target / stale source → Reject
- failed mutation → prior Kit state preserved

Exactly one musical mutation per accepted non-duplicate delivery.

## Feature key — `internal_sample_dnd_enabled`

| Property | Value |
|----------|-------|
| Serialized key | `internal_sample_dnd_enabled` |
| Default | `False` (disabled) |
| Persist | yes, across restart |
| Shared with | #1073 (same key) |

**OFF:** internal Sample DnD is fully inert (no descriptor/target discovery for
drag, apply rejects). Existing non-drag Add/Replace remains fully usable.

**ON:** Browser/Harmony may send typed Sample drop intents to valid visible
Edit Live-Kit targets.

## Payload isolation

These payload classes are typed and mutually fail-closed:

1. `internal_sample` — this contract
2. `panel_move` / docking intents — #1070 (`src/workbench_edit_docking.py`)
3. External file drop — #768 (`src/workbench_sample_dnd.py`)

A panel-move descriptor must never parse as an internal Sample descriptor.
An internal Sample descriptor must never be treated as external file DnD.
No heuristic string sniffing when a typed kind field is available.

## Replay / duplicate delivery

Each drop intent carries a `delivery_id`. Replaying the same delivery id must
not assign twice. The second delivery is accepted as an idempotent no-op
(`reason=duplicate_delivery`) with Kit state unchanged.

## Public seams

```text
descriptor_from_row(row, *, source_surface) -> InternalSampleDescriptor | None
parse_internal_sample_descriptor(payload) -> InternalSampleDescriptor | None
parse_internal_sample_drop_intent(payload) -> InternalSampleDropIntent | None
list_visible_live_kit_targets(...) -> tuple[LiveKitAssignmentTarget, ...]
apply_internal_sample_drop(...) -> InternalSampleDropResult
```

## Non-goals

QML drag visuals (#1073), Arrangement DnD, later Live DnD, filesystem export,
track-package import, new audio engine, generic DnD plugin platform, complete
#1077 UI redesign.

## Acceptance tests

See `tests/test_workbench_internal_sample_dnd_1072.py`.
