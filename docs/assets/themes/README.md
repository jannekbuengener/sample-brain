# Theme presets (design canon)

Status: **design canon only** for #785. Not a QML runtime implementation.

## Superdesign project (canonical)

- Title: `Sample Brain — Workbench Screen 1`
- Project ID: `47e8bb1a-efce-43bd-a97f-c05c9750d726`
- Do not create a new project, remix, or clone for this track.

## Source of truth

Base tokens alone define a theme:

- `accent`
- `background`
- `foreground`

Derived tokens (`textPrimary`, `textSecondary`, `surface`, `surfaceRaised`, `divider`, `hover`, `selected`, `focusRing`) are computed from base tokens and must not be edited independently.

See `presets.v1.json` for values and derivation formulas.

## Presets

Blood (primary candidate, with A/B accent stages), Carbon, Arctic, Rose, Forest.

All presets keep the Sample Brain dark language; only base tokens vary.
