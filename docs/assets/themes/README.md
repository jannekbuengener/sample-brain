# Theme presets (design + runtime canon)

Status: **runtime-backed design canon** for #785. Theme Core
(`src/workbench_theme.py`) loads these presets; Screen-1 QML consumes them via
`themeAuthority` semantic tokens (no second hardcoded palette).

## Asset Foundation — Token Freeze V7

**Status:** `TOKEN_FREEZE_PASS`

**Owner visual acceptance:** `PASS`
**Scope:** Default Blood-A foundation for the global Single Workspace background
and depth hierarchy. This is a bounded visual foundation, not a layout or
component redesign.

### Approved traceability

- Superdesign project: `47e8bb1a-efce-43bd-a97f-c05c9750d726`
- Draft: `2fa91842-f07f-4d70-9d12-de9622744191`
- Accepted version: `7`

### Locked V7 tokens

| Semantic role | Theme Core token | Exact value |
|---|---|---|
| Chrome / background | `background` | `#020203` |
| Workspace | `surfaceWorkspace` | `#040405` |
| Surface / panel | `surface` | `#080809` |
| Raised | `surfaceRaised` | `#101011` |
| Hover | `hover` | `#131314` |
| Hairline | `divider` | `#19191a` |
| Blood-A accent | `accent` / `focusRing` | `#8f0e24` |
| Selected deep red | `selected` | `#21050a` |
| Primary foreground | `foreground` / `textPrimary` | `#e4e6ea` |
| Muted foreground | `textSecondary` | `#68696b` |

These values are exact for the default Blood-A foundation. Their runtime source
remains `presets.v1.json` plus the deterministic derivation in
`src/workbench_theme.py`; QML consumes only the semantic `themeAuthority`
facade. Existing preference infrastructure is not a second V7 authority and is
not migrated by this background/depth slice.

### V7 color and atmosphere rule

- Alpha-derived colors may use only the RGB sources in the locked table.
- The only approved atmospheric treatment is:

  ```text
  linear-gradient(
    120deg,
    rgba(143,14,36,.015),
    transparent 38%
  ),
  #020203
  ```

  Its shadow source, if an explicitly scoped future slice needs one, is
  `rgba(2,2,3,x)`. This V7 runtime slice deliberately uses the simpler solid
  chrome/workspace hierarchy and adds neither a gradient nor an alpha layer.
- Do not introduce `rgba(0,0,0,...)`, `#6f9fbf`, arbitrary blue tints, a new
  gray palette, a new accent, neon/glow, glass, or a decorative asset to this
  foundation.

### V7 visual principles and slice boundary

The application reads almost black at first glance. Depth comes from quiet
chrome → workspace → surface → raised separation, restrained hairlines, and
hover weaker than selected. Blood-A is a sparse semantic signal, never a broad
panel fill or ambient red wash.

This slice changes only the global root/background depth contract. It must not
change Library, Browser, Harmony, Bottom Rack, component styling, typography,
navigation, docking, audio, persistence, or interaction behavior. The existing
background reference asset remains untouched; V7 adds no image asset and does
not derive its palette from that reference.

## Superdesign project (canonical)

- Title: `Sample Brain — Workbench Screen 1`
- Project ID: `47e8bb1a-efce-43bd-a97f-c05c9750d726`
- Do not create a new project, remix, or clone for this track.

## Source of truth

Base tokens alone define a theme:

- `accent`
- `background`
- `foreground`

Derived tokens (`textPrimary`, `textSecondary`, `surfaceWorkspace`, `surface`,
`surfaceRaised`, `divider`, `hover`, `selected`, `focusRing`) are computed from
base tokens and must not be edited independently.

See `presets.v1.json` for values and derivation formulas.

## Dark surface hierarchy (historical transition → V7 applied result)

Authority for hierarchy is Theme Core + this canon — not screenshot pixels.

### Root cause (why the first polish still read bright / open-gray)

Blood example after the first hierarchy pass (still too open for Owner noir review):

| Role | Token | Value | Why it failed noir |
|------|-------|-------|--------------------|
| Program Chrome | `background` | `#050506` | Near-black but not ink-dense enough as the family floor |
| Workspace | `surfaceWorkspace` @ mix `0.025` | `#0b0b0c` | Large calm canvas read as open charcoal / gray field |
| Panels (Library / Browser) | `surface` @ mix `0.045` | `#0f0f11` | Visible gray boxes / card mass |
| Dividers | `divider` @ mix `0.16` | `#2a2a2c` | Relatively bright tool-frame edges |
| Primary text | `foreground` | `#eceef1` | High-luma white-gray; less “Schrift und Minimalismus” |
| Secondary text | mix `0.45` | `#848587` | Mid-gray labels add visual noise |

Hierarchy order was correct (`chrome < workspace < panels`), but **absolute density**
was still too bright/gray for cinematic noir.

### TARGET (cinematic noir — same hierarchy, deeper)

| Role | QML semantic | Theme Core token | CURRENT (pre-noir) | TARGET (noir) |
|------|--------------|------------------|--------------------|---------------|
| Program Chrome (header / footer band) | `surfaceHeader` | `background` | `#050506` (Blood) | ink floor `#020203` (Blood); deepest role short of pure black |
| Main Workspace (root / calm canvas) | `surfaceRoot` | `surfaceWorkspace` | `#0b0b0c` @ `0.025` → mid `#050506` @ `0.012` | `#040405` @ `0.008` — deeper ink workspace |
| Panels (Library / Browser / Live Kit / Harmonic) | `surfacePanel` / `surfaceBrowser` | `surface` | `#0f0f11` @ `0.045` | `#080809` @ `0.028` — one panel family, near zinc-black |
| Elevated / hover lifts | `surfaceElevated` / `hoverSurface` | `surfaceRaised` / `hover` | `0.09` / `0.11` | `0.06` / `0.075` — quieter lifts |
| Borders / dividers | `borderSubtle` / `dividerDefault` | `divider` | `#2a2a2c` @ `0.16` | `#19191a` @ `0.10` — fine restrained edges |
| Typography | `textPrimary` / `textSecondary` | `foreground` / mix | `#eceef1` / `#848587` @ `0.45` | `#e4e6ea` / `#68696b` @ `0.55` — calmer, finer mood |

**Feel:** cinematic noir — very dark, elegant, deep, premium, calm, little visible
UI mass. No flat `#000000` product surfaces. No open gray tool slabs. Depth comes
from Theme solid hierarchy + preset base tints only — not a second palette and
**not** soft-ellipse / glow overlays. Style intent references Superdesign
cinematic noir / “Schrift und Minimalismus”; do **not** copy-paste Superdesign
layout.

### No glow / atmosphere overlays (Owner: remove lighting completely)

Owner feedback on PR #889: even subliminal soft-ellipse atmosphere still reads as
unwanted lighting. TARGET for this slice is **complete removal** of cinematic
atmosphere overlays — not a weaker opacity.

| Layer | PREVIOUS (rejected) | TARGET |
|-------|---------------------|--------|
| Soft-ellipse PNG overlays | Theme `atmosphereWorkspace` / `atmospherePanel` Images | **Removed** — no PNG cache, no stop mixes, no QML Image bindings |
| Accent bleed into atmosphere cores | tiny accent/fg mixes | **Removed** — no atmosphere exception |
| Library / Browser / Live Kit / Harmonic / calm canvas | solid fill + atmosphere Image | **Solid Theme fills only** (`surface` / `surfaceWorkspace`) |
| Workspace root | `#040405` @ `0.008` | keep solid hierarchy |
| Panel solids | `#080809` family | keep one panel family via solids |
| Dividers | `#19191a` | keep fine/restrained edges |

**Feel:** very dark, calm, deep, uniform, elegant, minimal, cinematic/noir —
depth from chrome → workspace → panel solids only. No visible glow, no
subliminal oval, no atmosphere machinery left in Theme Core / QML for this slice.

### Primary surfaces (solid fills only — uniform panel family)

| Surface | Role fill | Overlay |
|---------|-----------|---------|
| Left Library pane | `surfacePanel` → `surface` | none |
| Center empty / calm canvas | `surfaceRoot` → `surfaceWorkspace` | none |
| Center active Browser pane | `surfaceBrowser` → `surface` | none |
| Harmonic Matching pane | `surfacePanel` → `surface` | none |
| Live Kit pane | `surfacePanel` → `surface` | none |

No QML `Gradient` / `RadialGradient`. No Theme soft-ellipse PNGs. No Superdesign
hex copy. No grain/glass.

### Superdesign cinematic noir reference (style intent, not layout)

Source: `https://superdesign.dev/library/cinematic-noir-style` (prompt-library
slug `cinematic-noir-style`, fetched via `api.superdesign.dev`).

How that page builds background / atmosphere (concrete tokens):

| Technique | Reference values | Map into Sample Brain? |
|-----------|------------------|------------------------|
| Deep black floor | `#000000` | Yes → Theme `background` ink floor `#020203` (never pure `#000000`) |
| Zinc / mid dark | `#09090b` | Yes → panels land near this via `surface` mix (`#080809` Blood) |
| Surface gray (cards) | `#18181b` | Partial → `surfaceRaised` stays darker/quieter (`#101011`) for low UI mass |
| Warm radial atmosphere | `radial-gradient(ellipse at center, …)` | **No** — Owner rejected glow/atmosphere lighting; solids only |
| Grain / noise overlay | 15% opacity, `mix-blend-overlay` | No — landing-page film grain; not Workbench surface hierarchy |
| Glass / blur | not a core requirement; sharp architectural edges | No |
| Typography mood | fg `#e5e5e5`, muted `#888`, extreme display scale | Partial → Theme `foreground` `#e4e6ea` + calmer `textSecondary` `#68696b` (Schrift / Minimalismus); no display-font / layout copy |
| Selection red | `#ef4444` | No — Blood accent remains `#8f0e24` (product accent contract) |

**Mapped in this slice:** deeper Theme-owned solid hierarchy (chrome → workspace →
panels) only.
**Not mapped:** soft-ellipse / atmosphere PNG overlays, QML `Gradient` /
`RadialGradient`, grain/glass, layout/parallax, second palette / Superdesign hex.

**OUT of this polish (#894 hierarchy):** chrome geometry (#880), footer-context
behavior (#885), nav, list layout, Live Kit IA, Pattern/Bars/Song, audio,
Screen-2/3.

**Secondary control chrome (#895):** Add Source / Remove / Search / Live Kit
slot cards / Harmonic secondary row chrome reuse existing Theme semantics
(`hoverSurface`, `borderSubtle`, `focusRing`, `surfaceElevated`, text tokens,
`actionActive` for focus/active only). No second QML palette and no new Theme
base tokens unless reuse is insufficient. See
`docs/WORKBENCH_VISUAL_ACCEPTANCE.md` § Secondary control and panel chrome.

## Presets

Blood is the primary default. Owner-approved stage **A** (`accent #8f0e24`) is
the product default Blood base. Stage **B** (`accent #d4143a`) remains a
brighter-crimson comparison variant only.

Carbon, Arctic, Rose, and Forest stay in the same dark Sample Brain family;
only base tokens vary. Accent remains a sparse control signal (selection, focus,
primary action, small status). No atmosphere accent bleed — accent is
functional-only.

## Runtime wiring

- Python Theme Core resolves presets/customs and persists base tokens only in
  `workbench_state_dir` (`screen1_theme_preferences.json`).
- QML `theme` QtObject is a thin facade over `themeAuthority` semantic colors.
- No atmosphere PNG cache, stop derivation, or overlay URLs in Theme Authority.
- Display Preferences hosts Appearance controls; it does not own a second theme
  store.
- Corrupt preference payloads fail closed to Blood A.
