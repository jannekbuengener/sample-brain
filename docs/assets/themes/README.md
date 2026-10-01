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

Derived tokens (`textPrimary`, `textSecondary`, `surface`, `surfaceRaised`,
`divider`, `hover`, `selected`, `focusRing`) are computed from base tokens and
must not be edited independently.

See `presets.v1.json` for values and derivation formulas.

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
