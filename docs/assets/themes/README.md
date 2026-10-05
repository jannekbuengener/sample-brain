# Theme presets (design + runtime canon)

Status: **runtime-backed design canon** for #785. Theme Core
(`src/workbench_theme.py`) loads these presets; Screen-1 QML consumes them via
`themeAuthority` semantic tokens (no second hardcoded palette).

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

## Dark surface hierarchy (CURRENT → TARGET)

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
UI mass. No flat `#000000` product surfaces. No open gray tool slabs. Subtle cool /
red-blue depth from preset base tints + Theme atmosphere overlays — not a second
palette. Style intent references Superdesign cinematic noir / “Schrift und
Minimalismus”; do **not** copy-paste Superdesign layout.

### Atmosphere restraint + panel uniformity (Owner feedback on PR #889)

#### Root cause (why atmosphere-on-both still failed Owner review)

| Surface / layer | CURRENT (pre-restraint) | Why it failed |
|-----------------|-------------------------|---------------|
| Workspace root | `#050506` @ mix `0.012` | Still a touch open vs deeper noir floor |
| Atmosphere workspace core | `#1e0d11` @ accent `0.14` + fg `0.03` | Visible warm glow / light oval — reads as an effect, not depth |
| Atmosphere panel core | `#1c0d10` @ accent `0.12` + fg `0.02` | Same: Library/center mid≈`(28,13,16)` vs edge≈`(5,5,6)` |
| Library / Browser | `surface` + `atmospherePanel` | Atmosphere present but too bright |
| Live Kit / Harmonic Matching | `surfacePanel` only, **no** atmosphere | Flat / foreign vs Library+center — broken family |
| Dividers | `#19191a` @ `0.10` | Acceptable; keep fine/restrained |

Glow tokens are Theme atmosphere stop mixes (`atmosphere_*Core` / Mid / Edge) rendered
as soft-ellipse PNGs. Brighter panes were not a second palette — Live Kit and
Harmonic Matching simply lacked the shared panel atmosphere binding.

#### TARGET (subliminal glow + one panel family)

| Role | CURRENT | TARGET |
|------|---------|--------|
| Workspace root (`surfaceWorkspace`) | `#050506` @ `0.012` | `#040405` @ `0.008` — slightly deeper ink |
| Atmosphere workspace core | `#1e0d11` | `#070506` — almost subliminal depth only |
| Atmosphere panel core | `#1c0d10` | `#0a0809` — same restraint on all panels |
| Panel solids (Library / Browser / Live Kit / Harmonic) | `#080809` | unchanged family fill `#080809` |
| Dividers | `#19191a` | unchanged fine edge `#19191a` |

**Feel:** very dark, calm, deep, uniform, elegant, minimal, cinematic/noir.
Glow is **minimal depth only** — not a visible light/glow effect.

### Atmosphere on all primary surfaces (uniform family)

Solid hierarchy alone still reads as flat slabs at noir density. Soft elliptical
depth must apply across the **whole** Screen-1 panel family — not only Library
and center:

| Surface | Role fill | Atmosphere overlay |
|---------|-----------|--------------------|
| Left Library pane | `surfacePanel` → `surface` | Theme `atmospherePanel` Image (soft ellipse) |
| Center empty / calm canvas | `surfaceRoot` → `surfaceWorkspace` | Theme `atmosphereWorkspace` Image (soft ellipse) |
| Center active Browser pane | `surfaceBrowser` → `surface` | Theme `atmospherePanel` Image (same panel atmosphere) |
| Harmonic Matching pane | `surfacePanel` → `surface` | Theme `atmospherePanel` Image (same panel atmosphere) |
| Live Kit pane | `surfacePanel` → `surface` | Theme `atmospherePanel` Image (same panel atmosphere) |

**How (allowed path):** Theme Core derives stop colors from our base combo and
renders a soft elliptical PNG. QML binds `theme.atmosphereWorkspace` /
`theme.atmospherePanel` as `Image` fills. This keeps `Gradient` /
`RadialGradient` out of `QML_SOURCE` (Screen-1 background contract) while still
delivering radial depth. No Superdesign hex copy. No grain/glass.

Blood stop formulas (Theme Core only — not persisted customs) — **subliminal**:

| Overlay | Stop | Derivation | Blood example |
|---------|------|------------|---------------|
| Workspace | core | `mix(mix(surfaceWorkspace, accent, 0.015), foreground, 0.003)` | `#070506` |
| Workspace | mid | `surfaceWorkspace` | `#040405` |
| Workspace | edge | `mix(surfaceWorkspace, background, 0.65)` | `#030304` |
| Panel | core | `mix(mix(surface, accent, 0.012), foreground, 0.002)` | `#0a0809` |
| Panel | mid | `surface` | `#080809` |
| Panel | edge | `mix(surface, background, 0.50)` | `#050506` |

Atmosphere uses a **tiny accent bleed into ink** for cool red-blue noir depth.
That is not functional accent chrome and must stay near-black (never colorful
panel fills). Accent control states remain selection / focus / primary action.
Core luminance must stay close to mid (subliminal) — prior visible cores
`#1e0d11` / `#1c0d10` are rejected.

### Superdesign cinematic noir reference (style intent, not layout)

Source: `https://superdesign.dev/library/cinematic-noir-style` (prompt-library
slug `cinematic-noir-style`, fetched via `api.superdesign.dev`).

How that page builds background / atmosphere (concrete tokens):

| Technique | Reference values | Map into Sample Brain? |
|-----------|------------------|------------------------|
| Deep black floor | `#000000` | Yes → Theme `background` ink floor `#020203` (never pure `#000000`) |
| Zinc / mid dark | `#09090b` | Yes → panels land near this via `surface` mix (`#080809` Blood) |
| Surface gray (cards) | `#18181b` | Partial → `surfaceRaised` stays darker/quieter (`#101011`) for low UI mass |
| Warm radial atmosphere | `radial-gradient(ellipse at center, rgba(139,69,69,0.4) 0%, rgba(20,20,20,0.8) 60%, rgba(0,0,0,0.95) 100%)` | Yes — **technique only** via Theme-owned soft-ellipse PNG overlays using our Blood/Theme stop mixes (above). Not QML `Gradient`/`RadialGradient`. Not their rgba/hex. |
| Grain / noise overlay | 15% opacity, `mix-blend-overlay` | No — landing-page film grain; not Workbench surface hierarchy |
| Glass / blur | not a core requirement; sharp architectural edges | No |
| Typography mood | fg `#e5e5e5`, muted `#888`, extreme display scale | Partial → Theme `foreground` `#e4e6ea` + calmer `textSecondary` `#68696b` (Schrift / Minimalismus); no display-font / layout copy |
| Selection red | `#ef4444` | No — Blood accent remains `#8f0e24` (product accent contract) |

**Mapped in this slice:** deeper Theme-owned solid hierarchy (chrome → workspace →
panels) **plus** Theme atmosphere overlays on Library, center workspace, Live Kit,
and Harmonic Matching — subliminal core strength only.
**Not mapped:** QML `Gradient`/`RadialGradient`, grain/glass, layout/parallax,
second palette / Superdesign hex.

**OUT of this polish:** chrome geometry (#880), footer-context behavior (#885),
nav, list layout, Live Kit IA, Add Source control redesign, Pattern/Bars/Song,
audio, Screen-2/3, broad Secondary-Control polish.

## Presets

Blood is the primary default. Owner-approved stage **A** (`accent #8f0e24`) is
the product default Blood base. Stage **B** (`accent #d4143a`) remains a
brighter-crimson comparison variant only.

Carbon, Arctic, Rose, and Forest stay in the same dark Sample Brain family;
only base tokens vary. Accent remains a sparse control signal (selection, focus,
primary action, small status). Theme atmosphere may use a tiny accent bleed into
ink for noir depth (see atmosphere stop table).

## Runtime wiring

- Python Theme Core resolves presets/customs and persists base tokens only in
  `workbench_state_dir` (`screen1_theme_preferences.json`).
- Atmosphere PNGs are runtime Theme artifacts (cache under state dir); not
  persisted theme preference keys.
- QML `theme` QtObject is a thin facade over `themeAuthority` semantic colors
  and atmosphere URLs.
- Display Preferences hosts Appearance controls; it does not own a second theme
  store.
- Corrupt preference payloads fail closed to Blood A.
