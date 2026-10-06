# Sample Brain Design Asset Foundation

This document is the catalog for reusable visual assets and their canonical
locations. It does not change the Screen-1 layout or introduce product
behavior. Runtime theme values remain owned by
[`themes/presets.v1.json`](themes/presets.v1.json) and
`src/workbench_theme.py`.

## Design canon (Superdesign)

- Superdesign project: `47e8bb1a-efce-43bd-a97f-c05c9750d726`
- Canonical draft: `2fa91842-f07f-4d70-9d12-de9622744191`
  ("Asset Foundation — Token Freeze"), accepted version **7**
- No new project, remix, or clone for this track.

## Direction

- Keep the canvas very dark and near-black, with restrained low-saturation
  red and cool undertones. Blood red is a sparse signal, not ambient lighting.
- Use the existing semantic theme surfaces for hierarchy. The V7 token freeze in
  [`themes/README.md`](themes/README.md) is a hard ban on atmospheric layers:
  solid fills only, no `Gradient`/`RadialGradient`, no soft-ellipse PNGs, no
  grain, no glow, no glass, no arbitrary ambient light fields, no decorative
  background assets. Texture and depth studies are **not** open exploration for
  the foundation; they would require a new Owner-approved token freeze.
- Depth comes only from the solid hierarchy:
  chrome → workspace → surface → raised.
- Do not invent or add fonts, SVG icon sets, texture packs, or additional
  decorative assets while no separate Owner-approved contract exists. The
  Screen-1 QML renders UI and vector content itself.
- Preserve the minimal default, waveform-first hierarchy, and the current
  QML/Python ownership boundary. Reusable UI states should be rendered from
  runtime state, not frozen into decorative screenshots.
- Extract principles from Sample Vault, ADSR Sample Manager, XO, and Sononym;
  do not copy their assets or layouts.

## Canonical catalog

Existing canonical locations only:

| Category | Canonical location | Current contents and rule |
|---|---|---|
| 01 Brand | [`brand/`](brand/) and [`portfolio/references/brand/`](portfolio/references/brand/) | Existing owner-approved logo and splash references. Reuse byte-for-byte; do not redraw, recolor, resize, or duplicate. |
| 06 References | [`portfolio/references/`](portfolio/references/) | Curated approved background, brand, and owner chrome references; not a general screenshot dump. |
| Runtime captures | [`portfolio/runtime/`](portfolio/runtime/) | Captured implementation evidence with provenance in `manifest.json`; keep distinct from design references. |
| Theme system | [`themes/`](themes/) | Runtime-backed palette and presets. Base tokens are authoritative; derived tokens are calculated. |

### Categories with no canonized assets

These categories have **no** canonical location yet, because no asset in them has
been approved. Do not create `backgrounds/`, `textures/`, `icons/`, or `ui/`
until an asset with a clear role, provenance, and consumer exists.

| Category | Status |
|---|---|
| 02 Backgrounds | None canonized. The existing Screen-1 background PNG is a reference only, is not rendered by the current QML, and is not a reusable output asset. |
| 03 Textures | None approved, and none permitted under V7. |
| 04 Icons | No standalone icon pack. Icon rendering stays with the runtime implementation; the QML draws its vectors in code. |
| 05 UI assets | Waveform, slot/browser/empty/overlay states are runtime visuals drawn by the QML, not stored files. |

## Current source of truth

- Base colors and derivation rules: [`themes/presets.v1.json`](themes/presets.v1.json).
- Theme resolution and persistence: `src/workbench_theme.py`.
- Screen-1 QML consumes semantic `themeAuthority` values; it does not own a
  second palette.
- Brand use and immutable reference hashes: [`brand/README.md`](brand/README.md).
- Screen-1 structure and owner-approved chrome: `docs/SCREEN1_UI_ACCEPTANCE.md`
  and `docs/PROGRAM_CHROME_CONTRACT.md`.
- Runtime visual evidence and its capture provenance:
  [`portfolio/runtime/manifest.json`](portfolio/runtime/manifest.json).

## Inventory decisions

Executed 2026-10-05/06:

- **KEEP:** all versioned files in `docs/assets/`, including approved brand
  references, the owner chrome capture, runtime screenshots, and the theme
  presets. They are current references or evidence and remain in the repository.
- **DELETED:** the local `.superdesign/tmp/` scratch tree. It held HTML exports,
  board-regeneration scripts, node snapshots, and validation reports for the
  nine imported drafts. Every generator hardcoded the **pre-V7, rejected** Blood
  palette (`#050506` / `#0f0f11` / `#eceef1`), one script embedded a
  machine-local absolute output path, and the validation reports still listed
  issues #785/#786 as OPEN after those issues were closed. None of it was
  tracked, tested, or referenced.
- **DELETED:** the local `.tmp-qml-map/` scratch tree, an untracked QML
  extraction area not imported by any module in `src/`.
- The local Superdesign embed-link files are gone as well; their embedded
  session link expired on 2026-10-01.

### Working set outside version control

`.superdesign/` is excluded via `.git/info/exclude` and is **scratch/tooling
context, not design input** — never a higher design authority than the tracked
canon. It retains `design-system.md` and the six `init/*.md` files as
working notes for future agents; the theme-facing files
(`init/theme.md`, `design-system.md`) were locally repaired to the V7
contract. Wherever the scratch set disagrees with
[`themes/presets.v1.json`](themes/presets.v1.json),
[`themes/README.md`](themes/README.md), and `src/workbench_theme.py`, the
tracked canon wins.
