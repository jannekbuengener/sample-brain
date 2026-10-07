# Track Package Ownership Contract — Sample Brain

**Status:** ACTIVE_SUPPORTING — ownership / package contract freeze for [#1082](https://github.com/jannekbuengener/sample-brain/issues/1082).  
**Class:** ACTIVE_SUPPORTING  
**Exit marker:** `TRACK_PACKAGE_OWNERSHIP_CONTRACT_FROZEN`  
**Parents:** [#1075](https://github.com/jannekbuengener/sample-brain/issues/1075) product sequence; [#679](https://github.com/jannekbuengener/sample-brain/issues/679) Arrangement owner  
**Depends on:** [#1076](https://github.com/jannekbuengener/sample-brain/issues/1076) Edit → Arrangement → later Live product canon  
**Runtime implementation owner:** [#1085](https://github.com/jannekbuengener/sample-brain/issues/1085)  
**Machine-readable companion:** [`track_package_ownership_v1.json`](track_package_ownership_v1.json)

This issue freezes the **smallest durable track-package and ownership contract**. It does **not** authorize persistence runtime, QML, Arrangement domain, Pattern-time, Browser runtime, or MIDI implementation.

```text
TRACK_PACKAGE_OWNERSHIP_CONTRACT_FROZEN
```

## Normative contract vs future runtime serialization

| Plane | Authority | What it is |
|---|---|---|
| **Normative contract schema** | This document + [`track_package_ownership_v1.json`](track_package_ownership_v1.json) | Ownership, lifecycle outcomes, confinement rules, create/migration semantics, expected-result vectors for later #1085 tests |
| **Future runtime serialization** | [#1085](https://github.com/jannekbuengener/sample-brain/issues/1085) | On-disk writer/reader, staging/copy IO, Browser registration runtime, autosave loops |

`docs/track_package_ownership_v1.json` is **not** the runtime package implementation.  
Contract decision: the future package entrypoint filename is frozen as **`track_package.json`** under the package root. #1085 implements that serialization; this contract only freezes the name and invariants.

## Live seam inventory (evidence; do not rewrite)

Verified against current `main` seams reused by this freeze:

| Seam | Live fact |
|---|---|
| [`SESSION_OWNERSHIP_CONTRACT.md`](SESSION_OWNERSHIP_CONTRACT.md) / `WorkbenchSession` | One Python-owned musical runtime; QML is projection + intent |
| `src/workbench_session_store.py` | `SCHEMA_VERSION = 2`; root keys `schema_version`, `live_kit`, `channel_rack`, `master_bpm`, `sync_enabled`; fail-closed restore; atomic write via temp + `os.replace`; honesty codes `fresh_missing` / `restored_ok` / `rejected_corrupt` / `rejected_schema` / `rejected_semantic` / `autosave_failed` |
| Legacy file | `workbench_session.json` under `workbench_state_dir()` / `SAMPLE_BRAIN_WORKBENCH_STATE_DIR` — absolute sample path refs; **not** a portable track package |
| #728 `src/workbench_live_kit_export.py` | Kit-only Demo export: source validation, sibling staging, relative `audio/...` media, complete-success publication via `os.replace`; distinct product outcome from Arrangement Entry |
| `src/pattern_core.py` | Stable Live Kit channel IDs + opaque user `ch_user_*` channel IDs |
| Library / catalog | Global system ownership; not track-owned |

Do not simply rename `workbench_session.json` → `track_package.json`. Legacy role and existing user data require explicit migration/claim semantics below.

## 1. Global vs track ownership

### Global system-owned (does not travel with the track)

- Registered sample sources
- Catalog / analysis state
- Browser organization (collections, source management)
- General application / workspace preferences (including feature settings)
- Regenerable caches (waveforms, embeddings, analysis caches)

### Track-owned after successful package commit

- Live Kit assignment identity / state (stable group/slot identities)
- Pattern / Channel Rack musical state (stable `channel_id`s, triggers, pattern length)
- Track musical clock state that is already canonical track-musical truth (`master_bpm`, `sync_enabled` as persisted musical resume fields — transport runtime remains session-owned)
- Arrangement state **once** [#1084](https://github.com/jannekbuengener/sample-brain/issues/1084) exists (opaque reserved extension ownership only here)
- Later MIDI state after its own contract (opaque reserved extension ownership only here)
- Package manifest / schema version
- Relative media references confined to the package

**No second musical state authority.** Before package commit, musical draft truth lives in the Python `WorkbenchSession` / draft session plane. After commit, durable musical truth for that track lives in the track package; the process runtime still mutates through one Python owner that writes the package. QML never owns persistence.

Waveform / analysis caches may remain regenerable. Musical truth must not depend on cache survival.

## 2. Draft-before-Arrangement semantics

Before Arrangement Entry / Create Track Package:

- There is **no** track folder
- Kit / Pattern work is **draft** state
- Sample assignment alone does **not** create a track
- App start does **not** create a track
- Demo **`Export Kit`** remains a separate command with a separate outcome (kit-only portable folder via #728 primitives)

On the **explicit** Arrangement Entry / Create Track Package command, the track package is created (transaction below). Final visible Arrangement Entry button copy remains an open product decision elsewhere; this contract owns the create/commit semantics, not the button string.

After successful create: kit / pattern / song / later MIDI mutations update the **same open track**, not a copied session.

## 3. Demo Export Kit vs Track Package

| | Demo `Export Kit` (#728) | Arrangement Entry / Create Track Package (#1082/#1085) |
|---|---|---|
| Product command | Distinct | Distinct |
| Outcome | Kit-only portable folder (`Sample Brain Live Kit` / kit `manifest.json`) | Durable track package (`track_package.json` + `media/`) that can become the active track |
| Shared primitives | May share copy / staging / source-validation patterns | Same |
| Activates durable track | **No** | **Yes**, only after create commit + bind |

#728 remains historical / reusable technical evidence. Do not collapse the two commands.

## 4. Package layout (v1)

```text
<track-package-root>/
  track_package.json    # required package entrypoint
  media/                # only media required by the track
```

- Caller / destination policy supplies `<track-package-root>`
- `track_package.json` is the sole package entrypoint
- All media live under `media/`
- All media references are package-relative paths using `/` separators
- Forbidden in stored refs: absolute Windows paths, UNC paths, `file://`, `..`, drive letters, machine-local usernames

### `track_id` (identity guardrail)

Live evidence has opaque stable string IDs (e.g. Pattern Core `channel_id` / `ch_user_*`) but **no** canonical UUID-hex track-id generator for Workbench tracks. Therefore this contract freezes properties only:

- `track_id` is **stable**
- **opaque**
- **not** derived from display name or filesystem path
- package-local and durable across serialize / restore / relocate
- must not contain private machine information

Concrete generation / encoding strategy is an **#1085 implementation decision**, unless a later owner freezes one.

### Normative package field classes (contract plane)

Required concepts the future runtime serialization must realize:

- `schema_version` (package schema int; v1 starts at `1`)
- `package_kind` = `sample_brain_track_package` (distinct from #728 `sample_brain_live_kit`)
- `track_id` (as above)
- media index: stable `media_id` + package-relative `relpath` under `media/`
- `musical` payload: portable remapping of current session-v2 musical truth (`live_kit`, optional `channel_rack`, `master_bpm`, `sync_enabled`) with absolute sample refs rewritten to package-relative media refs on successful create

Reserved optional extension ownership (opaque; no semantics here):

- `arrangement` → owned by [#1084](https://github.com/jannekbuengener/sample-brain/issues/1084)
- `midi` → future MIDI contract

Deterministic serialization where relevant (sorted keys / stable ordering) is required for comparable packages; exact writer details belong to #1085.

Unsupported future `schema_version` → fail-closed (`corrupt_or_unsupported`).

## 5. Create transaction (staged / fail-safe)

Package creation is **staged and transactional**. Stages:

1. Validate destination / package-root eligibility
2. Validate draft eligibility
3. Create sibling staging directory on the **same relevant filesystem** as the final destination when atomic rename/replace is the commit seam
4. Copy only required media
5. Validate copied media
6. Write versioned package data (`track_package.json` + media index with relative refs)
7. Validate complete package integrity
8. Commit the complete package into the final visible location (atomic/fail-safe rename or replace from staging)
9. **Only then** bind it as the active durable track

### Failure before commit (before stage 8 success / before stage 9)

- No half-valid **visible** track package
- Draft remains usable
- No false saved status
- Retry allowed
- Source samples untouched (never moved / deleted / modified)
- Foreign files must never be deleted as cleanup

Large media copies must not run on the realtime audio path or block step-toggle / audio-critical work (#1085 must honor this).

## 6. Portability and security (fail-closed)

A complete track package must open from a different Windows path even when the original library root is unavailable.

On validate / register / open:

- Resolve media relative to package root only
- Reject `..` traversal → `path_escape_rejected`
- Reject absolute media escape → `path_escape_rejected`
- Reject symlink / reparse escape outside package root → `path_escape_rejected`
- Corrupt or unsupported manifest → `corrupt_or_unsupported`
- Missing media → `missing_media` (honest; do not mutate global library originals)
- Unwritable / full destination → `destination_unavailable`
- Interrupted copy before commit → `copy_interrupted` (no visible half-package)
- Write failure after bind path → `write_failed` (never false success)

No private absolute paths in package payloads, committed fixtures, or status strings.

## 7. Legacy `workbench_session.json` migration

### Inventory (live)

Current durable resume file:

- Path: `workbench_session.json` under workbench state dir
- Schema: v1 (`schema_version`, `live_kit`, `channel_rack`) and v2 (+ `master_bpm`, `sync_enabled`)
- Media refs: **absolute** sample paths
- Honesty: fail-closed restore; atomic autosave; `PERSISTENCE_STATUS_*`

This is **draft / local resume**, not a portable track package.

### Frozen migration policy (non-destructive)

| Requirement | Rule |
|---|---|
| Detection | Supported legacy file presence + parseable schema → `migration_required` (or equivalent controlled migration outcome). Do **not** auto-create a track package on boot. |
| Claim / migrate | Explicit and deterministic (Arrangement Entry / explicit claim command owned by later implementation under #1085 / #1078 consumers) |
| Lossless claim | Assert loss-free migration **only** when every required media file copies successfully and musical payload remaps cleanly |
| Missing media | Truthful `missing_media` / controlled migration outcome — never fabricate success |
| Absolute refs | On successful package creation, rewrite to package-relative refs; never keep absolute legacy sample refs inside a supposedly portable package |
| Failure | Leave legacy file byte-identical and recoverable; no silent deletion; no silent overwrite |
| Unsupported / ambiguous | Controlled HOLD via `migration_failed` or `corrupt_or_unsupported` — not fabricated success |
| Destruction | **Forbidden** |

## 8. Draft-loss boundary

Technical contract only:

- Unsaved draft must not silently disappear
- Product close must detect draft-loss
- Any “don’t show this again” suppression may affect **only** the draft-loss warning — never general app-exit confirmation
- Switching to another package / track must not silently discard a non-exported draft

Exact UX copy / placement / interaction:

```text
OPEN_PRODUCT_GATE
```

Do not invent copy in this freeze.

## 9. Post-create write honesty

After successful track creation:

- Musical mutations go through exactly one Python-owned persistence authority
- Writes are atomic or recoverable per the frozen package format
- Write failure is observable (`write_failed`) and must never present as success
- No QML-owned persistence state
- No second parallel project / session store truth

Concrete autosave / writer implementation belongs to [#1085](https://github.com/jannekbuengener/sample-brain/issues/1085).

Relationship to existing session honesty:

- `PERSISTENCE_STATUS_*` continues to own **legacy global resume** honesty for `workbench_session.json`
- Track package lifecycle / write outcomes below own **package** create/open/write honesty
- Do not merge the two vocabularies into one ambiguous enum

## 10. Browser registration vs explicit Open

Minimal library seam (no Browser runtime in this issue):

- Valid packages may be registered / listed under a dedicated track/package scope
- Package rows are **not** normal sample rows
- Registration / docking does **not** activate the track
- Explicit **Open** binds / changes the active track
- Repeated registration / open has a deterministic outcome (idempotent same package root identity, or defined conflict)
- No multi-track Live semantics

[#1078](https://github.com/jannekbuengener/sample-brain/issues/1078) consumes package creation at the Edit → Arrangement transition; it does not redefine package ownership.

## 11. Status / outcome vocabulary

Package lifecycle / outcome codes (normative; snake_case):

```text
draft
package_creating
ready
open
missing_media
corrupt_or_unsupported
migration_required
migration_failed
destination_unavailable
copy_interrupted
write_failed
path_escape_rejected
```

These are **not** aliases of `PERSISTENCE_STATUS_*`. Documented relationship:

| Concern | Vocabulary owner |
|---|---|
| Legacy `workbench_session.json` load/autosave honesty | `PERSISTENCE_STATUS_*` in `workbench_session_store.py` |
| Track package create / open / migrate / write / escape | Package lifecycle codes above |

User-facing strings must stay safe: no private paths, secrets, or exception dumps.

## 12. Normative expected-result vectors (1–15)

These are **contract vectors** for later #1085 runtime acceptance. This freeze only defines expected outcomes; it does not implement them.

| # | Vector | Expected outcome class |
|---|---|---|
| 1 | Package round-trip from a different Windows path; original library unavailable | `open` / `ready` with media resolved from package |
| 2 | Original library unavailable on open of complete package | still `open` / `ready` (no library dependency) |
| 3 | Missing source media during create | create fails; draft usable; no visible package; `missing_media` (or create failure mapped thereto) |
| 4 | Destination full / unwritable | `destination_unavailable`; no visible half-package |
| 5 | Interrupted copy before commit | `copy_interrupted`; no visible half-package; draft usable |
| 6 | Corrupt or unsupported manifest on open/validate | `corrupt_or_unsupported`; no activation |
| 7 | Repeated create / open / register | deterministic idempotent or conflict outcome; no duplicate corrupt state |
| 8 | Path traversal (`..`) in media ref | `path_escape_rejected` |
| 9 | Absolute media escape | `path_escape_rejected` |
| 10 | Symlink / reparse escape outside package root | `path_escape_rejected` |
| 11 | Valid legacy session claim with all media | successful package; relative refs; legacy recoverable until explicit post-success policy (no silent delete required by this contract) |
| 12 | Legacy session with missing media | truthful missing-media / controlled migration outcome; legacy recoverable |
| 13 | Failed migration | legacy recoverable; `migration_failed` (or equivalent controlled HOLD) |
| 14 | Post-create musical mutation + restart | same track state restored from package |
| 15 | Save failure after create | `write_failed`; no false success |

Windows evidence for #1085 must use synthetic / repo-safe media only.

## 13. Cross-contract boundaries

| Issue | Boundary |
|---|---|
| [#1083](https://github.com/jannekbuengener/sample-brain/issues/1083) | Owns 32-field timing / musical-position mapping. Not owned here. |
| [#1084](https://github.com/jannekbuengener/sample-brain/issues/1084) | Owns Arrangement blocks / group masks / track masks / end marker. Package may reserve opaque `arrangement` extension only. |
| [#1078](https://github.com/jannekbuengener/sample-brain/issues/1078) | Owns Edit → Arrangement transition UX/command wiring; consumes this package contract for create-at-transition. |
| [#1085](https://github.com/jannekbuengener/sample-brain/issues/1085) | Sole runtime implementation owner of this contract. |

## 14. Hard out of scope (#1082)

- QML / Arrangement UI
- Pattern-time changes (#1083)
- Arrangement block/mask implementation (#1084)
- MIDI mapping / Live layout / multi-track Live
- Cloud storage / collaboration / sync engine
- Arbitrary project browser beyond minimal registration/open seam
- Runtime persistence / Browser runtime / export runtime changes
- Private samples, DBs, indexes, caches, credentials, machine-local paths in commits

## 15. Follow-up

**Runtime owner:** [#1085](https://github.com/jannekbuengener/sample-brain/issues/1085) — implement package create/open/migrate/autosave against this freeze; turn vectors 1–15 into runtime acceptance tests.

## Exit

Done for #1082 when this ownership freeze is on `main` and the exit marker is live:

```text
TRACK_PACKAGE_OWNERSHIP_CONTRACT_FROZEN
```
