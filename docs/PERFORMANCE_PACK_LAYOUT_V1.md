# Performance Pack Layout v1 — Canonical Directory & File Naming Contract

**Issue:** [#258](https://github.com/jannekbuengener/sample-brain/issues/258)
**Parent:** [#231](https://github.com/jannekbuengener/sample-brain/issues/231) — Song to Sample / Performance Pack
**Depends on:** [#257](https://github.com/jannekbuengener/sample-brain/issues/257) (Performance Pack Manifest v1)
**Status on issue tracker:** `OPEN` / documented on branch `docs/performance-pack-layout-v1`
**Document type:** `sample_brain.performance_pack_layout` (process/contract doc, not a versioned schema)
**Companion machine-readable examples:** `performance_pack_layout_v1_examples.json`
**Companion tests:** `tests/test_performance_pack_layout_contract.py`

This document defines the canonical, portable **directory and file-naming
standard** for a Sample Brain Performance Pack (#231). It closes #258. It works
on top of the Performance Pack Manifest v1 (#257): the manifest references the
files described here by portable relative URI, and the layout described here
makes those references stable, deterministic, and externally consumable without
the Sample-Brain SQLite catalog.

This is a **layout contract only**. It does not implement an orchestrator
(#259), runtime integration (#260), stem runtime (#261), resume/cache (#262),
re-import (#263), or end-to-end pilot (#264). It defines where files live and
how they are named so that #259 and later slices can produce and consume them.

---

## 1. Purpose

A Performance Pack is a portable collection of files for one original track:

- a single root directory (the **pack root**),
- the Performance Pack manifest (`manifest.json`, #257),
- portable analysis documents (`analysis/`),
- rendered loop assets (`loops/`),
- rendered section assets (`sections/`),
- optional technical stem outputs (`stems/`, future, #229 / #261).

This document makes the pack **self-describing and externally readable**: an
external consumer needs only the pack root, the manifest, and the referenced
files. It never needs the SQLite DB, machine-local absolute paths, internal
worktree structure, or private model caches.

---

## 2. Design Principles

| Principle | Rule |
|-----------|------|
| **Single portable pack root** | Every pack is one directory. All references inside the pack are relative to that root. No file assumes a parent location. |
| **Relative, POSIX-like URIs** | Manifest `ref` fields and asset `file_ref` fields are relative URIs using `/` separators, resolved against the pack root (or, for `file_ref` inside an asset manifest, against the asset manifest's own directory). |
| **Deterministic, reproducible names** | The same inputs always produce the same file paths and names. No randomness, no SQLite row order, no timestamps in names. |
| **Portable IDs, not local paths** | Filenames are derived from portable IDs (`asset_id`, `stem_id`) and `asset_kind`. No private original file name is required as identity. |
| **Filename is transport, not identity** | The portable ID (`asset_id` / `stem_id`) remains the authoritative identity. The filename is a human-readable, collision-free transport handle. |
| **Separate documents stay separate** | Track Map, Arrangement Map, Asset Manifests, and Stem Manifests remain separate files (per #257 / #250). The layout only places them. |
| **Technical stems ≠ producer assets** | Stems (#229) and producer groups (#268) are distinct source kinds; the layout keeps stems in `stems/`. |
| **Case-insensitive safety** | Filenames are normalized so they cannot collide on case-insensitive filesystems (Windows/macOS). |
| **No forbidden characters** | Filenames avoid characters that are illegal or dangerous on Windows/macOS/Linux. |
| **Status, not invented data** | Missing optional results (no arrangement, no stems) are normal and represented by absence, never fabricated. |
| **Additive to #257** | This document does not change the Performance Pack Manifest schema. It only defines the relative-URI layout the manifest `ref` fields assume. |

---

## 3. Canonical Pack Layout

```
<pack_root>/
  manifest.json                      # Performance Pack manifest (#257), document_type sample_brain.performance_pack_manifest
  analysis/
    track_map.json                   # REQUIRED — Track Map (#232 / #227)
    arrangement_map.json             # OPTIONAL — Arrangement Map (#228); absent when not produced
    # further portable analysis documents as contractually provided (e.g. reanalysis summaries)
  loops/
    loop_<asset_id>.wav              # rendered loop audio (asset_kind = "loop")
    loop_<asset_id>.json             # Asset Manifest for the loop (#250)
    # one pair per loop asset
  sections/
    section_<asset_id>.wav           # rendered section audio (asset_kind = "section")
    section_<asset_id>.json          # Asset Manifest for the section (#250)
    # one pair per section asset
  stems/                            # OPTIONAL — present only when technical stems were produced (#229 / #261)
    <stem_id>.json                   # Stem Manifest for one technical stem
    # one file per technical stem; audio outputs follow the same Stem Manifest contract
```

### 3.1 Required vs optional

| Path | Required | Rule |
|------|----------|------|
| `manifest.json` | yes | The pack entry point (#257). |
| `analysis/track_map.json` | yes | Every valid pack has a resolvable, non-`failed` Track Map (#257 §10). |
| `analysis/arrangement_map.json` | no | Optional; absence is a normal, valid state. |
| `loops/`, `sections/` | yes (directory present) | At least one of the two must contain assets for a meaningful pack, but an otherwise valid pack may contain zero assets if none were produced (status `complete`/`partial` per the manifest rules). |
| `stems/` | no | Omit the directory entirely when no technical stems were produced. This is the normal, valid default. |

The minimum valid structure for a no-stem pack with assets is therefore:

```
<pack_root>/
  manifest.json
  analysis/track_map.json
  loops/...        (loop asset pairs)
  sections/...     (section asset pairs)
```

`stems/` is simply absent. This satisfies "Pack ohne Stems bleibt gültig".

---

## 4. File Naming Rules

All names are built from a single deterministic helper, `sanitize_component`,
applied to portable IDs. See Section 6 for the exact algorithm used by the
contract tests.

### 4.1 Asset files (loops and sections)

| File | Pattern | Example |
|------|---------|---------|
| Rendered audio | `<kind_dir>/<asset_kind>_<sanitized_asset_id>.wav` | `loops/loop_8bar_master_01a2b3c4.wav` |
| Asset Manifest | `<kind_dir>/<asset_kind>_<sanitized_asset_id>.json` | `loops/loop_8bar_master_01a2b3c4.json` |

where:

- `kind_dir` is `loops` when `asset_kind == "loop"`, else `sections`.
- `<asset_kind>` is literally `loop` or `section` (the authoritative kind from the Asset Manifest #250; never inferred from the file name).
- `<sanitized_asset_id>` is `sanitize_component(asset_id)` of the portable `#250` `asset_id`.

Because `asset_id` is a globally unique portable identity (#250), this naming is
collision-free by construction: two different assets always produce different
names. The kind directory (`loops`/`sections`) additionally keeps loop and
section assets physically separated.

The asset filename does **not** embed:

- arrangement role (`drop`/`build`/`intro`/…) — roles are data in the manifest, not filename identity (and `unknown`/`unavailable` roles must never be invented into a name),
- BPM, key, or tonality,
- stem type,
- confidence or score,
- private original file names.

Readable role/bar information may appear in *companion* documents (the Asset
Manifest), but the filename identity is always the portable `asset_id`.

### 4.2 Analysis documents

| File | Pattern | Required |
|------|---------|----------|
| Track Map | `analysis/track_map.json` | yes |
| Arrangement Map | `analysis/arrangement_map.json` | no |

Further portable analysis documents (e.g. an asset reanalysis summary produced
by #254) live in `analysis/` as well, named by a sanitized, stable identifier
(e.g. `analysis/asset_analysis.json`). They are referenced from the manifest or
asset manifests by their relative path.

### 4.3 Stem documents (optional, future)

| File | Pattern |
|------|---------|
| Stem Manifest | `stems/<sanitized_stem_id>.json` |

Technical stem audio outputs follow the Stem Manifest contract (#229) and are
placed in `stems/`. This layout entry is defined now so the directory and
naming are stable; the stem pipeline (#261) fills it later. No stem separation
or stem audio generation is introduced by #258.

### 4.4 Pack manifest

The pack manifest file is always named `manifest.json` at the pack root. It is
the single entry point an external consumer opens first.

---

## 5. How the Manifest References These Files (#257 → #258)

The Performance Pack Manifest v1 (#257) references files by relative URI. The
mapping from #257 fields to this layout is fixed and deterministic:

| #257 field | #258 relative reference |
|------------|--------------------------|
| `source_track.track_ref` | `analysis/track_map.json` |
| `documents.track_map.ref` | `analysis/track_map.json` |
| `documents.arrangement.ref` (optional) | `analysis/arrangement_map.json` |
| `assets[].asset_ref` (loop) | `loops/loop_<sanitized_asset_id>.json` |
| `assets[].asset_ref` (section) | `sections/section_<sanitized_asset_id>.json` |
| `assets[].rendering.output.file_ref` (inside the Asset Manifest) | `loop_<sanitized_asset_id>.wav` / `section_<sanitized_asset_id>.wav` (relative to the Asset Manifest's own directory) |
| `stems[].stem_ref` (optional) | `stems/<sanitized_stem_id>.json` |

No `#257` field changes meaning. Only the relative paths are pinned to this
layout. This is an additive precision of #257, not a schema break.

### 5.1 Relationship to the renderer (#253)

The deterministic renderer (#253, implemented) writes its per-asset output to a
pipeline working directory as `assets/<asset_kind>_<asset_id>.wav` (see
`ASSET_RENDERING_V1.md` §8). That is the **intermediate** pipeline output. The
**pack assembler** (#259, out of scope for #258) relocates those files into the
kind-segregated `loops/` and `sections/` directories defined here and rewrites
the `asset_ref` / `file_ref` values to match this layout. #258 defines the
target layout; it does not re-implement or modify the renderer.

---

## 6. Collision Policy

Asset filenames are keyed by the unique portable `asset_id`, so the common
collision cases are prevented by construction:

- **Multiple drops with the same readable role** — distinguished by `asset_id`, not by the role label. Each drop gets its own `section_<asset_id>.wav` / `.json`.
- **Multiple builds** — same rule; distinct `asset_id` ⇒ distinct name.
- **Multiple loops from the same section** — distinct `asset_id` ⇒ distinct name in `loops/`.
- **Identical roles** — role is never part of the filename, so identical roles cannot collide.
- **Master / stem / producer-group sources** — `source_kind` is data in the manifest; the filename identity is the `asset_id`, which is unique across all source kinds.

### 6.1 Deterministic residual-collision resolution

Although `asset_id` uniqueness makes collisions effectively impossible, the
layout defines a **deterministic, order-independent** fallback so that the
contract is closed even for adversarial input:

1. Compute the base name `<asset_kind>_<sanitize_component(asset_id)>.<ext>` for every asset in a kind directory.
2. Group assets that produce the **same** base name.
3. Within each colliding group, sort the members by their full `asset_id`
   (lexicographic, case-sensitive). The first member keeps the base name; the
   remaining members receive a numeric suffix `_2`, `_3`, … in that sorted order.
4. The result depends only on canonical `asset_id` values — never on processing
   order, filesystem enumeration, or a random UUID.

Because `sanitize_component` lowercases its input (Section 6.2), this rule also
resolves **case-insensitive filesystem collisions**: two `asset_id` values that
differ only in case produce the same lowercased base name and are disambiguated
by the same deterministic suffix.

### 6.2 `sanitize_component` (authoritative algorithm)

The contract tests implement exactly this algorithm; the pack assembler (#259)
must use a compatible implementation.

```
def sanitize_component(value: str) -> str:
    # 1. keep only safe characters; replace everything else with "_"
    #    safe set: ASCII letters, digits, ".", "_", "-"
    # 2. lowercase so the name is case-insensitive-safe
    # 3. collapse runs of "_" to a single "_"
    # 4. strip leading/trailing "_" and "." (Windows forbids trailing dot/space; Linux hidden-file dots avoided)
    # 5. reject empty result (caller must supply a non-empty portable id)
```

No forbidden character (see Section 7) can survive this function, and the
lowercasing step guarantees case-insensitive uniqueness of the comparison space.

---

## 7. Portability Rules

### 7.1 Forbidden in any pack path, `ref`, or `file_ref`

- absolute Windows paths (`C:\…`, `D:\…`),
- absolute POSIX paths (`/abs/…`),
- UNC paths (`\\host\share`),
- `file://` URLs,
- `..` path segments (no traversal outside the pack root or the asset's own directory),
- private sample-library roots,
- worktree / machine-local paths,
- SQLite row ids used as the sole external identity,
- characters illegal or dangerous on Windows/macOS/Linux:
  `<`, `>`, `:`, `"`, `/`, `\`, `|`, `?`, `*`, control characters, and leading/trailing dots or spaces.

### 7.2 Required

- references are relative URIs using `/` separators,
- portable IDs (`asset_id`, `stem_id`, `track_id`) remain the authoritative identity,
- file paths are a *transport reference*, never the identity,
- an external consumer can resolve every `ref` / `file_ref` from the pack root (or the asset manifest's directory) alone, with no SQLite access.

---

## 8. Examples

All IDs, hashes, and paths below are **synthetic**. No private track names,
sample names, or absolute paths are used. The machine-readable versions live in
`performance_pack_layout_v1_examples.json` and are validated by
`tests/test_performance_pack_layout_contract.py`.

### 8.1 Pack without stems

```
my_pack/
  manifest.json
  analysis/
    track_map.json
  loops/
    loop_8bar_master_01a2b3c4.wav
    loop_8bar_master_01a2b3c4.json
  sections/
    section_bridge_master_05f6e7d8.wav
    section_bridge_master_05f6e7d8.json
```

No `stems/` directory. The manifest omits the optional `stems` block. The pack
is `complete` (per #257 status rules).

### 8.2 Pack with multiple loops

```
my_pack/
  manifest.json
  analysis/track_map.json
  loops/
    loop_4bar_master_11aa.wav
    loop_4bar_master_11aa.json
    loop_8bar_master_22bb.wav
    loop_8bar_master_22bb.json
    loop_16bar_master_33cc.wav
    loop_16bar_master_33cc.json
  sections/
    section_intro_master_44dd.wav
    section_intro_master_44dd.json
```

Three loops from `master`, distinguished solely by `asset_id`. No role or
bar-count appears in the filename.

### 8.3 Pack with two drops

```
my_pack/
  manifest.json
  analysis/track_map.json
  sections/
    section_drop01_master_a1.wav
    section_drop01_master_a1.json
    section_drop02_master_b2.wav
    section_drop02_master_b2.json
```

Both sections carry `arrangement_role = "drop"` in their manifests, but the
files are uniquely named by `asset_id`. Identical readable roles never collide.

### 8.4 Pack with two builds (or equal-named sections)

```
my_pack/
  manifest.json
  analysis/track_map.json
  sections/
    section_build01_master_c3.wav
    section_build01_master_c3.json
    section_build02_master_d4.wav
    section_build02_master_d4.json
```

Two `build` sections, uniquely named by `asset_id`.

### 8.5 Assets from master only

All examples above use `source_kind = "master"`. The layout does not treat
master, stem, or producer-group assets differently in naming — the `asset_id`
is unique across all three source kinds, so filenames never collide between
them. A stem-sourced section is named `section_<asset_id>.wav` exactly like a
master-sourced one; the difference is recorded in `source.source_kind` inside
the manifest, not in the filename.

### 8.6 Portable example paths (no private data)

Every `ref` in the examples is a relative URI such as `analysis/track_map.json`
or `loops/loop_8bar_master_01a2b3c4.json`. No absolute path, drive letter,
`file://`, or `..` appears. An external tool can read the pack from any
filesystem location without SQLite or private knowledge.

---

## 9. Acceptance Mapping (Issue #258)

| #258 criterion | This document |
|----------------|---------------|
| Verzeichnisstandard dokumentiert | Section 3 (canonical layout). |
| Dateinamen reproduzierbar | Section 4 + deterministic `sanitize_component` (Section 6.2). |
| mehrere Drops/Builds/Loops eindeutig benennbar | Sections 4.1, 6, 8.2–8.4. |
| externe Tools können Pack ohne DB lesen | Sections 1, 7; #257 §13 portability contract. |

---

## 10. Related Documents

- [Performance Pack Manifest v1](PERFORMANCE_PACK_MANIFEST_V1.md) (#257) — the manifest that references these files.
- [Asset Manifest v1](ASSET_MANIFEST_V1.md) (#250) — loop/section asset contract; `asset_id` is the filename identity.
- [Asset Rendering v1](ASSET_RENDERING_V1.md) (#253) — deterministic renderer; intermediate `assets/` output relocated by the pack assembler (#259).
- [Track Map v1](TRACK_MAP_V1.md) (#232) — `analysis/track_map.json`.
- Arrangement Map (#228) — `analysis/arrangement_map.json` when present.
- Stem Manifest (#229 / #244–#249) — `stems/<stem_id>.json` when present.
- Song to Sample / Performance Pack meta (#231) — parent issue and downstream aggregation scope.

---

## 11. Non-Goals (v1)

- No headless orchestrator (#259), runtime integration (#260), stem runtime (#261), resume/cache (#262), re-import (#263), or end-to-end pilot (#264).
- No stem separation, producer-group generation (#268), audio rendering, or new analysis.
- No SQLite schema or migration.
- No new dependencies.
- No private tracks, samples, stems, or paths in the contract or its examples.
- No change to the Performance Pack Manifest schema (#257) beyond pinning the relative-URI layout its `ref` fields assume.
