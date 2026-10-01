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

Blood is the primary candidate. Owner-approved stage **A** (`accent #8f0e24`) is the current default Blood base. Stage **B** (`accent #d4143a`) remains a brighter-crimson comparison variant only.

Carbon, Arctic, Rose, and Forest stay in the same dark Sample Brain family; only base tokens vary. Accent is a sparse signal (selection, focus, primary action, small status), not atmosphere.
