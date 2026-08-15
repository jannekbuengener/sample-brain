# Performance Pack Re-import v1 — Catalog Registration & Library Compatibility

**Issue:** [#263](https://github.com/jannekbuengener/sample-brain/issues/263)
**Parent:** [#231](https://github.com/jannekbuengener/sample-brain/issues/231) — Song to Sample / Performance Pack
**Depends on:** [#257](https://github.com/jannekbuengener/sample-brain/issues/257) (Performance Pack Manifest v1), [#260](https://github.com/jannekbuengener/sample-brain/issues/260) (Track Map / arrangement / asset integration)
**Status:** implemented on `feat/performance-pack-reimport-v1`
**Reader module:** `src/performance_pack_import.py`
**CLI:** `sample-brain pack-import <pack-root>`

This document defines how an already-produced Performance Pack is re-imported into
the normal Sample-Brain catalog so its Loops, Sections, and (optional) technical
Stems are analyzed, searched, and matched exactly like ordinary samples.

---

## 1. Purpose

A Producer finishes a track and renders a Performance Pack (#257/#260). Later they
want those pack assets back in the catalog as first-class samples, without a
second search system, a second matching model, or any SQLite-internal identity
leaking into the pack.

The re-import reader:

- loads the pack manifest,
- validates every reference and audio file fail-closed,
- registers each declared, usable audio asset as a normal `samples` row,
- avoids duplicates by audio content hash,
- records lineage via `sample_tags` (source `performance_pack`),
- and hands the assets back to the existing `analyze` / `autotype` / `match` /
  `search` paths unchanged.

---

## 2. External Truth, Local Index

- **The Performance Pack manifest is the external truth.** SQLite is only a local
  search/working index. No pack contract field becomes part of the catalog schema.
- The importer writes **no** row id, path, or hash back into the pack. `manifest.json`
  and every referenced document are read-only.
- No new table and no new `samples` column are introduced. Lineage lives entirely
  in `sample_tags` (keyed by `source = "performance_pack"`).

---

## 3. Import Flow

```
pack-import <pack-root>
  1. resolve pack root or direct manifest.json
  2. load + validate root manifest (document_type, schema_version major == 1)
  3. load + validate Track Map (required anchor)
  4. for each asset entry:
       - locate Asset Manifest via asset_ref (portable, in-pack)
       - verify asset_id / track_ref / asset_kind
       - import ONLY when rendering.status == "rendered" and output present
       - audio integrity gate (exists, hash, sample_rate, channels, n_samples)
       - register sample (dedup by content hash) + lineage tags
  5. for each stems[] entry (optional):
       - locate Stem Manifest via stem_ref
       - import ONLY when status in (ok, partial) and output present
       - same audio integrity gate + register + tags
  6. return deterministic ImportResult
```

`failed` / `not_run` / `no_result` optional items are **not** turned into fake
samples; they are counted as `skipped` and reported in `errors`.

---

## 4. Reference Safety (hard rule)

Every manifest/audio reference is validated, then resolved against the pack root
(or, for `file_ref` inside an Asset/Stem Manifest, against that manifest's own
directory):

- Reject: absolute paths (`/abs`, `C:\`, `D:\`), UNC (`\\host\share`),
  `file://`, and `..` traversal.
- After resolution, the absolute path **must** stay inside the pack root. Anything
  escaping it is rejected fail-closed.

---

## 5. Audio Integrity Gate

For every importable asset/stem output:

1. `rendering.output.file_ref` (or Stem Manifest `output.file_ref`) resolves to a
   file that exists.
2. Actual file `sha1` equals `output.hash.value`.
3. Actual `sample_rate_hz` / `channels` / `n_samples` equal
   `output.audio_properties`.

Any mismatch is fail-closed with a stable code.

---

## 6. Hash-based Deduplication

`catalog` fact: `samples.path` is `UNIQUE`, `samples.hash` is **not** unique.

Resolution order (never overwrites an existing row with new content):

1. **Search by path.** If a `samples` row exists at the same path:
   - same path **and** same hash → reuse (idempotent re-import).
   - same path **and** different hash → **fail closed** (path conflict; never
     silently reinterpret an existing identity).
2. Otherwise **search by hash.** If a row exists with the same content hash →
   reuse the existing `sample_id` (different path, identical content).
   When several historic rows share the hash, the **smallest `sample_id`** wins
   (deterministic).
3. Otherwise → normal `INSERT` (new `sample_id`).

Re-importing the same pack therefore creates no second `samples` row.

---

## 7. Parent-Track Lineage (`sample_tags`, source = `performance_pack`)

Per imported item:

| Tag | Value |
|-----|-------|
| `pack:<pack_id>` | pack identity |
| `parent_track:<source_track.track_id>` | original-track grouping key |
| `item_kind:loop \| section \| stem` | asset kind |
| `item_id:<asset_id>` (or `<stem_id>`) | item identity |
| `source_kind:master \| stem \| producer_group` | only for assets |

Tags use `INSERT OR IGNORE`, so a repeated import is idempotent and never
duplicates tags. All assets of one original track share `parent_track:<track_id>`,
so they are groupable through the existing tag filter (`search --tag`).

---

## 8. Normal Analyze / Match / Search afterward

The importer registers the sample + lineage **only**. It does **not** pre-fill
`features` (otherwise `run_analyze(only_missing=True)` would skip a full analysis).

After `pack-import`:

- `sample-brain analyze` computes normal full features for the imported rows.
- `sample-brain autotype` sets `features.pred_type`.
- `sample-brain match ...` treats imported assets as normal candidates.
- `sample-brain search --tag pack:<pack_id>` selects them through the existing
  filter/backend path. No pack-specific search or matching code exists.

---

## 9. Optional Stem Compatibility

If a valid foreign or later pack already contains a Stem Manifest 1.x, the reader
imports usable stems (`status` `ok`/`partial`, `output` present) the same way as
loop/section assets. #263 produces no stems itself and requires no stem
separation. Stems receive `item_kind:stem` and `item_id:<stem_id>` tags.

---

## 10. Privacy

- Only synthetic temp WAVs are used in tests (`tests/audio_fixtures.py`,
  `tmp_path`, isolated test DB).
- No private packs, private audio, private library roots, model caches, or SQLite
  files are committed.

---

## 11. Boundary to #262 / #264

- **#262 (resume/cache/idempotency):** #263 is idempotent via hash dedup + tag
  `INSERT OR IGNORE`, but owns no cache or resume layer. #262 may later add
  caching on top without changing this contract.
- **#264 (private end-to-end pilot):** a real private library may later be
  imported locally using this command; no private artifact enters the repo.
- **Out of scope:** #246 stem benchmark, #247 backend selection, #249 stem
  deconstruct wiring, #261 stem-pack generation, any new search/matching model,
  GUI, or new dependency.

---

## 12. Acceptance Mapping (Issue #263)

| #263 criterion | This document / module |
|----------------|-----------------------|
| Pack wieder einlesbar | §3 `run_pack_import` + `pack-import` |
| Assets zum Originaltrack gruppierbar | §7 `parent_track:<track_id>` |
| normale Suche/Matching nutzbar | §8 |
| Manifest bleibt externe Wahrheit, keine privaten DB-Strukturen | §2 |
| spätere private Library-Evaluation lokal möglich, ohne Artefakte ins Repo | §10 / §11 |
