# Brand asset slots

Status: **ACTIVE** Screen-1 analysis/loading brand + motion runtime for #786
(Python Core `#795` + QML visualization). Theme color authority remains #785 /
`workbench_theme` — this layer does not invent a second palette.

## Superdesign project (canonical)

- Title: `Sample Brain — Workbench Screen 1`
- Project ID: `47e8bb1a-efce-43bd-a97f-c05c9750d726`
- Do not create a new project, remix, or clone for this track.

## Slots

| Slot | Intended use | Screen-1 header |
|------|--------------|-----------------|
| Brain Symbol | Splash / Loading / Motion / external | No |
| Wordmark `SAMPLE BRAIN` | External / splash | No |
| Symbol + Wordmark Lockup | Presentation / website | No |
| Splash / Loading | Brand layer | No |
| Analysis Motion Reference | Consumes real analysis/progress state | No |

## Runtime contract (#786)

- Python owns analysis truth (`AnalysisUiState` + `AnalysisJobCoordinator`) and
  projects motion hints via `src/workbench_brand_motion.py`.
- QML visualizes the projection on the analysis/loading surface only.
- No permanent brain logo / `SAMPLE BRAIN` wordmark / claim in the Screen-1
  header chrome. Product identity text (`Sample Brain`) remains header copy,
  not brand-lockup chrome.
- Claim `Sample Brain — Frech aber im Flow.` is allowed on splash/external
  surfaces only — not as permanent Screen-1 header chrome.
- Progress: `total <= 0` → indeterminate (no fake %); `total > 0` →
  `current/total` clamped. Sample name only from real `display_name`.
- Motion preferences `on` / `reduced` / `off` must all be real paths:
  reduced is not merely slower full motion; off uses a clear static fallback.
- Subtle breathe/flow only while phase is `scanning` or `analyzing` and motion
  is not off. Status text remains understandable without animation.

## Rules

- Do **not** commit fake or placeholder SVG/PNG logos.
- Owner-approved reference assets already exist under `docs/assets/portfolio/references/brand/`; reuse those exact files instead of duplicating, recoloring, resizing, compressing, or re-exporting them.
- Primary brain reference: `sample_brain_logo_primary.png` — SHA-256 `6e8ba304d216e8f1ba0e819603388dc37ff18491fe1a3e22b985513258882605`.
- Splash / hero typography reference: `sample_brain_splash_typography.png` — SHA-256 `eb130874c65ce8c1e36500b56e3cb1328318d6ac439fd13305547949994a83f6`.
- These files are reference assets, not authorization to add permanent branding to the Screen-1 header.
- Direction: clear brain · black/anthracite · controlled red inner lines/glow · organic · surreal · calm.
- Wordmark: uppercase, geometric, light gray/white; not required as red letters.
- Claim: `Sample Brain — Frech aber im Flow.`
