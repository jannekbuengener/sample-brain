# Live Kit Export V1 Contract — Sample Brain

**Status:** ACTIVE_SUPPORTING — portable Live-Kit export contract freeze for [#1224](https://github.com/jannekbuengener/sample-brain/issues/1224).  
**Class:** ACTIVE_SUPPORTING  
**Exit marker:** `LIVE_KIT_EXPORT_V1_CONTRACT_FROZEN`  
**Parents:** [#1221](https://github.com/jannekbuengener/sample-brain/issues/1221) Live Kit product completion; [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) Edit Production Ready  
**Depends on:** [#1077](https://github.com/jannekbuengener/sample-brain/issues/1077) Live Kit Edit tool; [#1203](https://github.com/jannekbuengener/sample-brain/issues/1203) path/filename reconciliation; [#1082](https://github.com/jannekbuengener/sample-brain/issues/1082)/[#1085](https://github.com/jannekbuengener/sample-brain/issues/1085) package primitives (reuse only)  
**Historical evidence:** [#728](https://github.com/jannekbuengener/sample-brain/issues/728) local-folder export (`src/workbench_live_kit_export.py`)  
**Runtime reconciliation owner:** later bounded [#1221](https://github.com/jannekbuengener/sample-brain/issues/1221) child created only from live evidence after this freeze  
**Machine-readable companion:** [`live_kit_export_v1.json`](live_kit_export_v1.json)

This issue freezes the **smallest robust portable Live-Kit export contract**. It does **not** authorize rewriting the full exporter, Arrangement/track-package create, analyzer changes, MIDI/DAW formats, or cloud sharing.

```text
LIVE_KIT_EXPORT_V1_CONTRACT_FROZEN
```

## Normative contract vs runtime

| Plane | Authority | What it is |
|---|---|---|
| **Normative contract schema** | This document + [`live_kit_export_v1.json`](live_kit_export_v1.json) | Eligibility, layout, manifest fields, metadata authority, integrity, atomicity, confinement, expected-result vectors for later runtime acceptance |
| **Current runtime evidence** | [#728](https://github.com/jannekbuengener/sample-brain/issues/728) / `src/workbench_live_kit_export.py` | Historical local-folder exporter; reconciled below — not automatic proof that every historical detail remains V1-correct |
| **Future runtime reconciliation** | Later #1221 child | Bounded exporter alignment to this freeze; not this contract issue |

`docs/live_kit_export_v1.json` is **not** the runtime writer (`not_runtime_serialization = true`).

## Live seam inventory (evidence; do not invent a second architecture)

| Seam | Live fact |
|---|---|
| `src/workbench_live_kit.py` | Canonical `LIVE_KIT_SLOT_MAPPING` group/slot taxonomy; `LiveKitState` owns musical assignments |
| `src/workbench_controller.py` `WorkbenchRow` | Consumer-facing assignment payload: `display_name`, `path`, `bpm`, `key`, `pred_type`, `sample_class`, optional `details.duration_sec`; no portable `sample_id` |
| #728 `src/workbench_live_kit_export.py` | Kit-only folder `Sample Brain Live Kit/`; required `manifest.json`; `audio/<group>/<slot>__<stem>.ext`; sibling staging + `os.replace`; empty rejected; sparse allowed; missing source / existing dest fail-closed; per-slot byte copies |
| #1082/#1085 track package | Distinct product: `track_package.json` + `media/`; may share staging/validation/confinement **patterns**; must **not** collapse Export Kit into track-package create/bind |
| #1203 `PATH_METADATA_RECONCILIATION.md` | Resolved consumer metadata ≠ raw `features.*`; path claims are not Live Kit runtime authority |
| #1218 BPM | Authoritative BPM precision/unknown semantics for product consumers; export must not fabricate BPM |
| Edit contract | [`WORKBENCH_LIVE_KIT_EDIT_CONTRACT.md`](WORKBENCH_LIVE_KIT_EDIT_CONTRACT.md) — Export Kit is a distinct Edit action, never aliased to Arrangement Entry |

## 1. Export eligibility

Status vocabulary for preflight / result:

- `EXPORTABLE` — export may proceed
- `NOT_EXPORTABLE` — export must fail closed with a stable reason code

| INPUT CONDITION | EXPORTABLE? | FAILURE/STATUS | PARTIAL OUTPUT POLICY |
|---|---|---|---|
| Empty kit (zero assigned slots) | No | `EMPTY_KIT` | No final folder; no staging left behind |
| Sparse / intentionally incomplete kit (≥1 assigned) | Yes | — | Empty slots recorded in manifest as `assigned=false`; no audio for empty slots |
| Missing assigned source file | No | `SOURCE_MISSING` | No final folder |
| Assigned source not a regular file | No | `SOURCE_NOT_FILE` | No final folder |
| Assigned source unreadable | No | `SOURCE_UNREADABLE` | No final folder |
| Same library source assigned to multiple slots | Yes | — | Deterministic **per-slot byte copies** with distinct package-relative paths |
| Duplicate source basenames across slots | Yes | — | Slot-index + group folder + stem slug prevent silent overwrite; internal path collision → `INTERNAL_COLLISION` |
| Catalog-stale assignment whose file still exists and is readable | Yes | — | Filesystem readability is the export gate; no silent relink/substitution |
| Unknown / unsupported metadata on an assigned row | Yes | — | Unknown remains unknown; never fabricate values |
| Destination parent missing / not a directory / invalid | No | `DESTINATION_INVALID` | No final folder |
| Destination parent not writable | No | `DESTINATION_NOT_WRITABLE` | No final folder |
| Final export folder already exists | No | `OUTPUT_EXISTS` | Do not overwrite; do not merge |
| Copy / manifest write / publish interruption | No | `EXPORT_FAILED` (or more specific IO code) | Remove staging; never leave a success-looking half tree; never report success |
| Retry after failed export (final folder absent) | Yes if otherwise eligible | — | Clean retry allowed |
| Retry when final folder still present | No | `OUTPUT_EXISTS` | Operator must choose another destination or remove the prior export explicitly |

Hard rule: partial output must never be reported as successful.

## 2. Bundle topology (V1)

```text
<destination_parent>/Sample Brain Live Kit/
  manifest.json
  audio/
    <NN>_<group-slug>/
      <NN>_<slot-slug>__<source-stem-slug>.<ext>
```

Frozen decisions:

| Decision | V1 value |
|---|---|
| Root directory name | `Sample Brain Live Kit` (fixed; under caller-chosen `destination_parent`) |
| Machine entrypoint | `manifest.json` at bundle root (required) |
| Media directory | `audio/` only |
| Human-readable README/summary | **Excluded** — manifest is sufficient for standalone inspection; a README would become a second SoT |
| Path separators in manifest refs | `/` always |
| Versioning | Integer `schema_version` starting at `1`; unsupported future versions fail closed at read/inspect time |
| Collision strategy | Group folder `NN_group-slug`; file `NN_slot-slug__stem-slug.ext`; Windows reserved device names escaped; unsafe chars slugified |
| Distinct from track package | Must not use `track_package.json` or `media/` as Live-Kit export entrypoint/layout |

## 3. Media semantics

- Include every audio asset required by an **assigned** slot.
- Original Library media remains unchanged (copy only; never move/delete/modify sources).
- Exported media is independently readable without Sample Brain, DB, index, or model cache.
- Same source in multiple slots → **COPY_PER_SLOT** (distinct files; no shared hardlink/ref identity required in V1).
- Duplicate filenames cannot overwrite another asset silently.
- Missing/offline media prevents false success.
- After successful export, package-relative refs must not depend on the original Library absolute path.

## 4. Manifest identity + assignment model

Required top-level fields:

| FIELD/PATH | SOURCE AUTHORITY | REQUIRED? | UNKNOWN SEMANTICS | PORTABILITY RULE | VERSIONING/MIGRATION NOTE |
|---|---|---|---|---|---|
| `schema_version` | This contract | Yes | n/a | Integer; V1 = `1` | Bump only on breaking manifest changes |
| `kit_type` | This contract | Yes | n/a | Constant `sample_brain_live_kit` | Distinct from `sample_brain_track_package` |
| `export_type` | This contract | Yes | n/a | Constant `local_folder` | Reserved for future export surfaces |
| `groups[]` | `LIVE_KIT_SLOT_MAPPING` order | Yes | n/a | Full canonical group list | Order is identity; do not omit empty groups |
| `groups[].name` | Domain group key | Yes | n/a | Stable domain string (not display-only label) | Display renames (#1123) do not change export identity |
| `groups[].folder` | Derived slug from group index + name | Yes | n/a | Package-relative folder under `audio/` | Must match on-disk layout |
| `groups[].slots[]` | Domain slot keys in mapping order | Yes | n/a | Full canonical slot list per group | Empty slots still listed |
| `groups[].slots[].group` | Domain group key | Yes | n/a | Echo of parent group | Redundant for flat consumers |
| `groups[].slots[].slot` | Domain slot key | Yes | n/a | Stable domain string | Not display-only label |
| `groups[].slots[].assigned` | `LiveKitState` | Yes | n/a | Boolean | Authority for empty vs occupied |
| `groups[].slots[].display_name` | `WorkbenchRow.display_name` when assigned | Yes when assigned; `null` when empty | Empty → `null` | No host path | Consumer label only |
| `groups[].slots[].audio_path` | Export planner | Yes when assigned; `null` when empty | Empty → `null` | Package-relative under `audio/`; `/` separators; no `..` | Sole media locator inside the bundle |

Optional resolved metadata on **assigned** slots only (see §5):

| FIELD/PATH | SOURCE AUTHORITY | REQUIRED? | UNKNOWN SEMANTICS | PORTABILITY RULE | VERSIONING/MIGRATION NOTE |
|---|---|---|---|---|---|
| `bpm` | Resolved product consumer value on assignment row | No | Omit or `null` when unknown | No fabricated precision/confidence | Must follow #1218 unknown/precision honesty |
| `key` | Resolved product consumer key/mode claim on row | No | Omit or `null` when unknown | No fabricated confidence | Must not replace resolved claim with a conflicting filename claim at export |
| `pred_type` | Resolved product type/class consumer value on row | No | Omit or `null` when unknown | Portable string | Classifier raw columns are not re-exported as truth |
| `sample_class` | Resolved product `sample_class` on row | No | Omit or `null` when unknown | Portable string | Path claims are not re-derived at export |
| `duration_sec` | Product row `details.duration_sec` when present | No | Omit or `null` when unknown | Numeric seconds or numeric string already on row; no invention | Later runtime may normalize type; contract allows either JSON number or pre-existing string form from the row |

Identity non-goals for V1:

- No portable `kit_id` / catalog `sample_id` (not owned on the current Live Kit product surface).
- No producer host paths, DB paths, operator identity, or machine-local provenance blobs.
- Safe sample identity inside the bundle is: `(group, slot)` + package-relative `audio_path` + `display_name`.

## 5. Metadata authority

For every exportable metadata field, V1 carries **resolved product consumer metadata** from the Live Kit assignment row — the same consumer-facing values Live Kit already projects — **not** whichever representation is easiest to reach from analyzer tables or path parsers.

| Concern | V1 rule |
|---|---|
| Resolved product metadata | Export `bpm` / `key` / `pred_type` / `sample_class` / optional `duration_sec` from the assignment `WorkbenchRow` |
| Raw analyzer evidence | **Do not** export `features.*` (or equivalent raw analyzer columns) as resolved truth |
| Path/filename claim provenance | **Do not** re-parse filename/folder at export time; #1203 remains the catalog reconciliation authority |
| Combination | V1 portable manifest does **not** embed a second raw/provenance block; catalog retains provenance; portable kit stays self-describing with resolved consumer fields only |
| Unknown | Remains unknown (omit/`null`); no fabricated confidence/probability |
| Conflict | Exporter must not overwrite a resolved consumer value with a conflicting filename claim merely for export |

## 6. Human-readable documentation

**Excluded from V1.** Rationale: `manifest.json` plus the deterministic `audio/` tree are sufficient for standalone inspection; a README would duplicate authority.

## 7. Integrity

- Structural integrity only: every assigned `audio_path` exists as a regular file under `audio/`; refs are package-relative and confined; empty slots have `audio_path: null`.
- Detect incomplete/corrupt exports by structure + readability, not by a new signing subsystem.
- Content hashes are **not** required in V1.
- Reuse existing staging/copy validation patterns from #728 and confinement rules aligned with #1082; do not invent a second package framework.

## 8. Atomicity / retry / destination safety

Export transaction stages (normative):

1. Snapshot `LiveKitState` into a planned slot list
2. Evaluate eligibility (`EMPTY_KIT` / source / destination / collision / `OUTPUT_EXISTS`)
3. Create sibling staging directory on the same destination filesystem when atomic rename is the commit seam
4. Copy only required assigned media byte-identically
5. Ensure group folders exist (including empty groups)
6. Write `manifest.json`
7. Validate staged tree against the planned manifest
8. Commit staging into final `Sample Brain Live Kit` via atomic/controlled replace
9. Only then report success with the final path

Failure policy:

- Before commit success: no half-valid **visible** final folder; staging removed; kit state and library sources untouched; retry allowed when final folder absent.
- Never delete foreign files in the destination as cleanup.
- Large copies must not run on the realtime audio path.

## 9. Path confinement / privacy

The finished bundle must contain:

- no private absolute host paths
- no SQLite DB dependency
- no search/vector index dependency
- no model cache dependency
- no credentials / operator metadata
- package-relative media references confined to the bundle root (`audio/` only; no `..`, drive letters, UNC, `file://`)

Destination policy: user-chosen local folder; must not be written inside the repository checkout (align with [`DATA_AND_ARTIFACT_POLICY.md`](DATA_AND_ARTIFACT_POLICY.md)).

## 10. #728 reconcile (keep / change / defer)

| Topic | Historical #728 | V1 freeze |
|---|---|---|
| Root name + `audio/` + `manifest.json` | Present | **Keep** |
| Empty kit rejected; sparse allowed | Present | **Keep** |
| Staging + `os.replace` | Present | **Keep** |
| Per-slot copies / collision filenames | Present | **Keep** as `COPY_PER_SLOT` |
| Manifest always written | Present (no longer “optional”) | **Keep** as required entrypoint |
| Metadata fields `bpm`/`key`/`pred_type` | Present when set; omitted when absent | **Keep**, and explicitly label as **resolved consumer** metadata |
| `sample_class` / `duration_sec` | Not currently written | **Freeze as optional V1 fields**; runtime reconciliation may add them later without a second architecture |
| README | Absent | **Freeze excluded** |
| Content hashes | Absent | **Freeze not required** |
| Track-package layout merge | Not done | **Forbidden** |
| Explicit eligibility vocabulary tables | Implicit via error codes | **Freeze** tables in this contract |
| Full exporter rewrite in #1224 | n/a | **Out of scope** — later #1221 child |

## 11. Non-scope

- Implementing the entire exporter inside this contract issue
- New analyzer algorithms
- Arrangement / song export
- MIDI / DAW package formats
- Cloud sharing / publishing
- A generic archive/package framework unrelated to Live Kit
- Collapsing Export Kit into Arrangement Entry / track-package create

## 12. Acceptance

Done for #1224 when this freeze is on `main` and the exit marker is live:

- [x] exact current #728 behavior is reconciled rather than blindly copied (§10)
- [x] #1082/#1085 package primitives are reused as patterns only; layouts stay distinct
- [x] sparse/empty/missing-media export eligibility is explicitly frozen (§1)
- [x] portable bundle topology and manifest name/location/version are explicit (§2)
- [x] group/slot/sample identity semantics are deterministic (§4)
- [x] media collision/source-reuse behavior is deterministic (§3)
- [x] metadata authority is explicit for resolved values vs raw analyzer/path provenance (§5)
- [x] #1203 reconciliation semantics are not bypassed (§5)
- [x] unknown metadata remains unknown (§5)
- [x] no private absolute paths/DB/index/cache/credentials can enter the portable contract (§9)
- [x] atomic failure/retry semantics are frozen (§8)
- [x] human-readable README/summary is explicitly excluded with rationale (§6)
- [x] integrity behavior is explicitly defined without overbuilding (§7)
- [x] contract is sufficient for a later bounded implementation slice and final #1221 runtime/export acceptance

Contract tests pin the normative plane in `tests/test_live_kit_export_v1_contract.py`.

## Exit

```text
LIVE_KIT_EXPORT_V1_CONTRACT_FROZEN
```

Refs #1221 #728 #1077 #1082 #1085 #1203 #1218 #1219 #1207 #1075
