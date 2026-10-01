# Theme presets (preset value authority)

Status: **ACTIVE** for #785. `presets.v1.json` is the sole preset-value authority.
Theme Core runtime: `src/workbench_theme.py` (merged via PR #796). QML consumes
tokens via `theme_tokens_to_qml_semantics` / a `themeAuthority` bridge — QML must
not invent a competing palette.

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

## Runtime / persistence seam

| Concern | Owner |
|---------|-------|
| Preset values + derivation formulas | `docs/assets/themes/presets.v1.json` |
| Resolve / derive / custom lifecycle | `src/workbench_theme.py` |
| Local theme prefs file | `screen1_theme_preferences.json` under `workbench_state_dir` |
| Display Preferences host UI (#696) | header overflow only; must not fork theme storage |
| QML colors | bind semantic names from Theme Core mapping; no second HEX truth |

Custom themes persist **only** base overrides (`name`, `base_preset`, `accent`,
`background`, `foreground`) plus schema fields. Derived tokens are recomputed.

`textOnAction` is a fixed contrast constant (`#ffffff`) for labels on solid
accent fills — not a persisted base token.

## Presets

Blood is the primary candidate. Owner-approved stage **A** (`accent #8f0e24`) is the current default Blood base. Stage **B** (`accent #d4143a`) remains a brighter-crimson comparison variant only.

Carbon, Arctic, Rose, and Forest stay in the same dark Sample Brain family; only base tokens vary. Accent is a sparse signal (selection, focus, primary action, small status), not atmosphere.
