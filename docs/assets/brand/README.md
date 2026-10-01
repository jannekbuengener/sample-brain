# Brand asset slots

Status: **ACTIVE** Python Brand/Motion Presentation Core for #786
(merged Core `#795` + presentation seam). Theme color authority remains #785 /
`workbench_theme` — this layer does not invent a second palette.

QML wiring of this contract is a **Parent handoff** (see below). This document
does not claim Screen-1 QML already visualizes the brand layer.

## Superdesign project (canonical)

- Title: `Sample Brain — Workbench Screen 1`
- Project ID: `47e8bb1a-efce-43bd-a97f-c05c9750d726`
- Do not create a new project, remix, or clone for this track.

## Slots

| Slot | Resolver key | Asset file | Screen-1 header |
|------|--------------|------------|-----------------|
| Brain Symbol | `brain_symbol` | `sample_brain_logo_primary.png` | No |
| Wordmark `SAMPLE BRAIN` | `wordmark` (= `splash_typography`) | `sample_brain_splash_typography.png` | No |
| Symbol + Wordmark Lockup | compose both keys | no separate file | No |
| Splash / Loading | surfaces on slots | same refs | No |
| Analysis Motion Reference | `project_analysis_motion` / `brand_runtime_payload` | consumes real analysis state | No |

## Presentation API (`src/workbench_brand_motion.py`)

| Symbol | Role |
|--------|------|
| `resolve_brand_slots(repo_root=…)` | Owner-approved refs only; pinned SHA-256 |
| `project_analysis_motion(state, motion_mode, expected_token=…)` | Pure projection from `AnalysisUiState` |
| `brand_runtime_payload(state, motion_mode, …)` | QML-safe dict (camelCase + URL sentinels) |
| `BRAND_CLAIM` | `Sample Brain — Frech aber im Flow.` |
| `SCREEN1_HEADER_PERMITS_PERMANENT_BRANDING` | always `False` |
| `WORKING_PHASES` | `{scanning, analyzing}` — only phases that may animate |

### `brand_runtime_payload` keys

| Key | Type | Notes |
|-----|------|-------|
| `phase` | str | From `AnalysisUiState.phase` |
| `progressKind` | `none` \| `indeterminate` \| `determinate` | `total<=0` → indeterminate while working |
| `progressRatio` | float | Clamped `current/total`, or `-1.0` sentinel when none/indeterminate |
| `sampleName` | str | Only from real `display_name` (empty when stale) |
| `motionMode` | `on` \| `reduced` \| `off` | Via `normalize_motion_mode` |
| `motionActive` | bool | True only while working + mode in `{on,reduced}` + not stale |
| `reducedMotion` | bool | `motionMode == reduced` |
| `staticFallback` | bool | True for `off`, non-working phases, or stale |
| `jobToken` | int | Real token, or `-1` when absent |
| `stale` | bool | Token mismatch vs `expected_token` |
| `brainUrl` | str | `file:` URI of primary brain PNG |
| `wordmarkUrl` | str | `file:` URI of splash typography PNG (splash/external only) |
| `headerPermitsPermanentBranding` | bool | Always `False` |
| `claim` | str | Splash/external only — never permanent Screen-1 header chrome |

## Runtime contract (#786)

- Python owns analysis truth (`AnalysisUiState` + `AnalysisJobCoordinator`) and
  projects motion hints via `src/workbench_brand_motion.py`.
- QML must **visualize** the projection only — no second progress clock, no
  Timer-based fake %, no DSP/re-analysis in the brand layer.
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

## QML integration handoff (Parent / Agent C)

**Do not invent a second analysis owner.** Wire existing analysis authority into
the brand presentation seam, then bind QML.

### 1. Analysis authority (already on main)

- Source of truth: `src/workbench_qml_analysis.py` → `AnalysisUiState`
- Production surface: `analysisWorkingSurface` in `src/workbench_qml.py`
  (`objectName: "analysisWorkingSurface"`)
- Existing bindings already expose `analysisStatus` / `analysisSource` /
  `analysisCurrent` / `analysisTotal` / `analysisError` from real state

### 2. Motion mode

- Prefer display-preferences authority: `load_display_preferences().motion_mode`
  and/or adapter `waveform_motion_mode` (`on` | `reduced` | `off`)
- Pass that mode into `brand_runtime_payload(state, motion_mode, expected_token=…)`
- `expected_token` = `AnalysisJobCoordinator.current_token(folder_id)` when live

### 3. Asset resolver

```python
from src.workbench_brand_motion import brand_runtime_payload, resolve_brand_slots

payload = brand_runtime_payload(state, motion_mode, expected_token=token)
# payload["brainUrl"] → Image.source on analysis surface only
# payload["wordmarkUrl"] → splash/external only (NOT analysisWorkingSurface chrome)
```

- Reuse exact files under `docs/assets/portfolio/references/brand/`
- No redraw / recolor / resize / re-export / compress

### 4. Suggested QML objectNames (analysis surface only)

| objectName | Bind from payload |
|------------|-------------------|
| `analysisBrandBrain` | `Image { source: brand.brainUrl }` — visible only on analysis/loading |
| `brandMotionLayer` | Opacity/scale breathe gated by `brand.motionActive` |
| `analysisBrandSampleName` | `brand.sampleName` (optional stream through brain) |
| existing `analysisProgressFill` | width from `brand.progressRatio` when determinate; indeterminate cue when `progressKind === "indeterminate"` — **no** `Behavior on width` / progress Timer |

### 5. Hard rules for QML edit

- Header must stay brand-clean: no `analysisBrandBrain`, no `SAMPLE BRAIN`, no claim, no primary PNG in `screen1Header`
- `motionActive === false` → static high-quality brain (or hide motion layer); status text still clear
- `reducedMotion === true` → distinct quieter path (not merely slower full motion)
- `stale === true` → ignore sample-name / progress motion
- Claim / wordmark stay off the analysis status card unless a dedicated splash route is in scope

### 6. Out of scope for this handoff

- Theme system (#785)
- Permanent header logo
- Screen 2/3 branding
- Packaging / installer icon wiring

## Rules

- Do **not** commit fake or placeholder SVG/PNG logos.
- Owner-approved reference assets already exist under `docs/assets/portfolio/references/brand/`; reuse those exact files instead of duplicating, recoloring, resizing, compressing, or re-exporting them.
- Primary brain reference: `sample_brain_logo_primary.png` — SHA-256 `6e8ba304d216e8f1ba0e819603388dc37ff18491fe1a3e22b985513258882605`.
- Splash / hero typography reference: `sample_brain_splash_typography.png` — SHA-256 `eb130874c65ce8c1e36500b56e3cb1328318d6ac439fd13305547949994a83f6`.
- These files are reference assets, not authorization to add permanent branding to the Screen-1 header.
- Direction: clear brain · black/anthracite · controlled red inner lines/glow · organic · surreal · calm.
- Wordmark: uppercase, geometric, light gray/white; not required as red letters.
- Claim: `Sample Brain — Frech aber im Flow.`
