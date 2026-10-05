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

| Role | QML semantic | Theme Core token | CURRENT (pre-polish) | TARGET |
|------|--------------|------------------|----------------------|--------|
| Program Chrome (header / footer band) | `surfaceHeader` | `background` | darkest base | darkest — unchanged role |
| Main Workspace (root / calm canvas / analysis deep surface) | `surfaceRoot` | `surfaceWorkspace` | same as chrome (`background`) — **flat** | minimally lighter than chrome |
| Panels (Library / Browser / Harmony / status cards) | `surfacePanel` / `surfaceBrowser` | `surface` | slightly above chrome; equal to each other | subtly above workspace |
| Elevated / hover lifts | `surfaceElevated` / `hoverSurface` | `surfaceRaised` / `hover` | raised overlays | unchanged role |
| Borders / dividers | `borderSubtle` / `dividerDefault` | `divider` | quiet separation | quiet separation; not a gray-tool frame |

**Feel:** very dark, elegant, deep, premium, calm. No flat `#000000` product
surfaces. No gray “tool” look. Subtle cool / red-blue depth comes from existing
preset base tints + foreground mixes — not from a second colorful palette.

**OUT of this polish:** chrome geometry, footer-context behavior, nav, list
layout, Live Kit IA, Add Source styling, general buttons, Pattern/Bars/Song,
audio, new presets unless required for hierarchy tokens.

## Presets

Blood is the primary default. Owner-approved stage **A** (`accent #8f0e24`) is
the product default Blood base. Stage **B** (`accent #d4143a`) remains a
brighter-crimson comparison variant only.

Carbon, Arctic, Rose, and Forest stay in the same dark Sample Brain family;
only base tokens vary. Accent is a sparse signal (selection, focus, primary
action, small status), not atmosphere.

## Runtime wiring

- Python Theme Core resolves presets/customs and persists base tokens only in
  `workbench_state_dir` (`screen1_theme_preferences.json`).
- QML `theme` QtObject is a thin facade over `themeAuthority` semantic colors.
- Display Preferences hosts Appearance controls; it does not own a second theme
  store.
- Corrupt preference payloads fail closed to Blood A.
