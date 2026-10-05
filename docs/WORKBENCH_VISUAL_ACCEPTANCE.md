# Screen-1 Visual Acceptance

## Operative acceptance rule (current)

Owner does **not** run manual operative visual/runtime acceptance loops.
Agents own technical/runtime/visual acceptance using fixtures, screenshots,
MCP/UI automation, plugins, skills, and reviewers.

Statuses:

- `VISUAL_ACCEPT_PENDING` — agent evidence still incomplete (not an Owner wait)
- `VISUAL_ACCEPT_PASS` / `VISUAL_ACCEPT_FAIL` — agent-owned closure outcomes

Historical sections below that mention Owner PASS remain evidence contracts for
delivered slices; they do **not** authorize a new Owner acceptance gate for
active routing.

## v1 — historical #503 evidence (frozen)

Run only from a verified dedicated runtime:

```text
python -m src.cli workbench --visual-acceptance --runtime-root <runtime-root> --evidence-dir <local-output>
```

The command uses an isolated temporary Workbench state, loads
`screen1_visual_fixture_v1`, captures only the Windows client window at
1600×900 / 100% DPI, and writes two PNGs plus `manifest.json` outside the
repository. It fails closed unless Runtime-Provenance is `VALID`.

Required v1 state IDs (do **not** retarget or overwrite):

- `screen1-default-3panel`
- `screen1-harmonic-4panel`

Automated checks cover provenance, both required states, dimensions, PNG
presence, non-black pixels, panel position, hashes, and public manifest data.
They do not assess visual product quality.

The Owner historically marked `PASS` or `FAIL` against `docs/assets/portfolio/mockups/ui_mockup.png` and
`docs/assets/portfolio/mockups/ui_mockup_matching.png` for hierarchy, spacing/density, typography, controls,
color/intent, discoverability, clipping/overflow, populated/empty states, and
overall producer-tool quality. Agent attestation was not an Owner PASS under that
historical v1 gate. That Owner operative gate is **superseded** by the operative
acceptance rule above for new work.

P0/P1 findings block closure. P2/P3 are recorded separately and do not trigger
automatic repair. Under the historical v1 Owner gate, a Screen-1 UI issue closed
only after structural tests, `VALID` runtime, both captures, automated sanity,
Owner PASS, no P0/P1, and commit/PR-bound evidence. New work follows the
operative agent-owned rule above.

Committed portfolio captures under `docs/assets/portfolio/runtime/` remain v1
evidence only.

## v2 — Calm Adaptive Workspace acceptance (#700 / #691)

Additive **fixture** contract for calm-workspace state IDs. Product Clean Start
behaviour is owned by [#693](https://github.com/jannekbuengener/sample-brain/issues/693)
/ [`WORKBENCH_CLEAN_START.md`](WORKBENCH_CLEAN_START.md). Density (#692), Elastic
Solver (#694), Waveform motion (#695), and Live Kit redesign remain separate
slices.

Authority on conflicts for Startup / Density / Panel geometry / Persistence:

`scoped #691 child > #691 > #700 contract docs > historical #503 visual acceptance`

For normal launch visibility / restore specifically:
`#725` (collapsed First View) supersedes `#693` Source-Navigation-visible launch,
which supersedes historical `#503/#518` restore behaviour (see Clean Start doc).

Module: `src/workbench_visual_acceptance.py`

- Fixture version: `screen1_visual_fixture_v2`
- Builder: `build_screen1_visual_fixture_v2()`
- Resolve: `resolve_screen1_visual_state_v2(fixture, state_id)`
- Validate: `validate_screen1_visual_fixture_v2(fixture)`
- Manifest: `build_visual_evidence_manifest_v2(...)` (parallel to v1; does not
  replace v1 manifests)

### Required v2 state IDs

| State ID | Intent |
|----------|--------|
| `screen1-clean-start` | Collapsed Source Navigation (#725); Calm Canvas + primary Add Source + edge affordance; no source selected; browser / harmonic / Live Kit **not** materialised; no preview / no sample selection |
| `screen1-active-source` | Explicit synthetic source selected; browser materialised; harmonic closed; Live Kit may be materialised; no auto-audition |
| `screen1-harmonic-open` | Like active-source + Harmonic Match visible via existing toggle/anchor contract |
| `screen1-elastic-resized` | Like active-source with **deterministic non-default** panel ratios (acceptance representation only; no solver) |

Each state declares:

- source selected or not (+ optional source label)
- selected browser index or `None`
- panel visibility flags
- panel ratios (positive entries sum to `1.0`)
- browser / harmony fixture row counts
- `density_mode` (declared; default acceptance target `compact_target_30dip`)
- `motion_mode` (canonical `on` / `reduced` / `off`; historical fixture token
  `full` means `on` and must not be written by new code — see
  [`WORKBENCH_DISPLAY_PREFERENCES.md`](WORKBENCH_DISPLAY_PREFERENCES.md) #696)
- `preview_active` / `auto_audition` (both false in these baseline states)

Canonical ratio constants (for later #694 comparison):

- active-source: `CANONICAL_ACTIVE_SOURCE_RATIOS_V2`
- harmonic-open: `CANONICAL_HARMONIC_OPEN_RATIOS_V2`
- elastic-resized: `ELASTIC_RESIZED_RATIOS_V2`

### Evidence rules (v2)

Same capture baseline as v1 when screenshots are produced later:

- exact implementation HEAD
- `RuntimeStatus.VALID`
- 1600×900 / 100% DPI primary reference
- screenshots/manifests **outside** the repository
- synthetic fixture paths only
- Historical Owner Visual Acceptance remained separate from agent self-attestation
  for delivered #691-era slices; new work follows the operative agent-owned rule above.

Follow-up UI slices (#692–#696, #725) must reference these v2 state IDs instead of
inventing parallel fixture semantics.

### #725 Runtime-/Interaction-Captures

Do **not** add competing REQUIRED_STATE_IDS_V2 entries. Additional evidence
filenames for historical Owner Visual Acceptance evidence may include:

- `clean-start-collapsed` — product projection of `screen1-clean-start`
- `clean-start-reveal-hover` — same collapsed layout with edge-affordance hover
- `opened-no-source` — Library revealed, no Source selected (interaction capture)
- `active-source` — product projection of `screen1-active-source`

These are capture labels only. Historical v1 evidence under
`docs/assets/portfolio/runtime/` remains untouched.

### #744 Analysis loading Runtime-Evidence

Do **not** add competing `REQUIRED_STATE_IDS_V2` entries. Additive historical Owner Visual
Acceptance captures for the Source analysis loading experience (#744) use these
labels only (real `AnalysisUiState` phases; no fake progress clock):

| Evidence ID | Intent |
|-------------|--------|
| `01-scanning-early` | Analysis surface visible; phase `scanning`; early / indeterminate or low progress |
| `02-analyzing-mid` | Phase `analyzing`; mid `current/total` |
| `03-analyzing-near-complete` | Phase `analyzing`; near-complete `current/total` |
| `04-cancelled` | After cancel → fail-closed idle; loading surface gone; no optional pane leaks |
| `05-error` | Real `error` phase presentation; Browser/Harmony/Live Kit unusable; Cancel not active |
| `06-success-transition-browser` | Overlay gone; Browser-first; Harmony closed; Live Kit hidden; no auto-selection / auto-audition |
| `07-100pct` | Same loading surface at 100% Windows / Qt scale |
| `08-125pct` | Same at 125% scale |
| `09-150pct` | Same at 150% scale |

#### #744 loading progress contract

- Progress bar = **folder-level** `processed / total` (`analysisCurrent` /
  `analysisTotal`). `current` means completed files in this folder (success,
  cache hit, or controlled per-sample error), not the ordinal of the sample
  currently in flight.
- Display name = **currently processed sample** (`analysisSource`); independent
  of the completed count.
- No per-sample progress bar and no second bar. No fake progress / timer.

Example mid-folder: label `Analysiere hit.wav`, count `2 / 5 Samples`, bar ~40%
means two files finished and `hit.wav` is the third file currently analyzing.

Evidence stays **outside** the repository. Synthetic fixture paths only.
Historical Owner Visual Acceptance for delivered #744 evidence remained separate
from agent self-attestation; new work follows the operative agent-owned rule.
Capture helper: `run_qml_visual_acceptance_744` in `src/workbench_qml_spike.py`.

### #786 Brand / analysis motion Runtime-Evidence

Additive capture labels for the analysis brand/motion layer (real
`AnalysisUiState` + `project_analysis_motion` only; no second progress clock).
Do **not** add competing `REQUIRED_STATE_IDS_V2` entries.

| Evidence ID | Intent |
|-------------|--------|
| `786-idle-header-clean` | Clean start; Screen-1 header has no brain logo / SAMPLE BRAIN wordmark / claim |
| `786-scanning-indeterminate` | Phase `scanning`; indeterminate progress; brain on analysis surface |
| `786-analyzing-determinate-mid` | Phase `analyzing`; mid `current/total`; real `display_name` |
| `786-analyzing-full` | Determinate near/full progress |
| `786-motion-on` | Motion `on`; calm organic activity only while analyzing |
| `786-motion-reduced` | Motion `reduced`; distinct reduced path (not merely slower full motion) |
| `786-motion-off` | Motion `off`; static high-quality fallback; status still clear |
| `786-error` | Error phase; no decorative motion requirement |
| `786-stale-ignored` | Stale token projection does not drive sample-name / progress motion |

Evidence stays **outside** the repository. Synthetic fixture paths only.
Capture helper: `run_qml_visual_acceptance_786` in `src/workbench_qml_spike.py`
(`tools/screen1_brand_motion_786_evidence.py`).

## Global program chrome reference (#830)

Design authority for the top program bar and the footer band only:

`docs/assets/portfolio/references/program_chrome/owner_program_chrome_ba928fbe.jpg`

Contract: `docs/PROGRAM_CHROME_CONTRACT.md`. Pattern, Bars, Song, channel rows,
and the rest of that image are not acceptance targets. Do not invent pixel or
hex values from the screenshot. Agent-owned visual acceptance still applies.

## Brand identity references

Byte-identische Owner Brand-Assets. Analysis/loading runtime may bind the
primary brain symbol via `workbench_brand_motion.resolve_brand_slots` —
never as permanent Screen-1 header chrome:

| Role | Repo path | SHA-256 |
|------|-----------|---------|
| Primary (reduced brain signet) | `docs/assets/portfolio/references/brand/sample_brain_logo_primary.png` | `6e8ba304d216e8f1ba0e819603388dc37ff18491fe1a3e22b985513258882605` |
| Splash / Hero typography | `docs/assets/portfolio/references/brand/sample_brain_splash_typography.png` | `eb130874c65ce8c1e36500b56e3cb1328318d6ac439fd13305547949994a83f6` |

- Primary: matte black organic form with controlled functional red glow.
- Splash: expressive hero/loading reference; embedded SAMPLE typography is part
  of the illustration (motion of that type is a later slice).
- Brand Brain is not a Library scope icon. Do not recolor, resize, compress, or
  re-export these files when updating the reference tree.

## Screen-1 canonical background reference

Kanonische visuelle Referenz (Reference = Runtime-Asset, eine Datei):

`docs/assets/portfolio/references/screen1_background_reference.png`

- Byte-identische Owner-Freigabe; Datei darf nicht neu gerendert, skaliert,
  komprimiert, recolored oder sonst verändert werden.
- Erwartete SHA-256:
  `2c799440a7b2c9d6e20e8163378ddcbecd29478d76ad8d7ee74835d3b60a47ae`
- QML bindet dasselbe Asset als Root-Background über `screen1BackgroundUrl`
  mit `Image.Stretch` (vollständiges Bild über die verfügbare Screen-1-Fläche;
  **kein** Crop, kein Tint/Colorize/Blur, keine Ambient-Gradient-/Glow-Layer).
- UI-Palette bleibt near-black / neutral und leitet Surfaces aus der
  Bildhierarchie ab; Accent (Blood A `#8f0e24`) nur funktional (Selection /
  Active / Toggle / Focus). Kein dekoratives Rot oder Blau.
- Frozen v1 Portfolio-Screenshots unter `docs/assets/portfolio/runtime/`
  bleiben unverändert.

## Screen-1 canonical color contract

Source of truth for Screen-1 colors is **Theme Core**
(`src/workbench_theme.py` + `docs/assets/themes/presets.v1.json`), exposed to
QML as `themeAuthority`. The embedded `theme` QtObject in
`src/workbench_qml.py` (`QML_SOURCE`) is a thin semantic facade only.

Layers:

1. **Background reference** — unchanged PNG above; not a color palette source.
2. **Theme Core base tokens** — `accent` / `background` / `foreground` (Blood A
   default `#8f0e24` / `#020203` / `#e4e6ea`).
3. **Derived Theme Core tokens** — deterministic mixes (`textPrimary`,
   `textSecondary`, `surfaceWorkspace`, `surface`, `surfaceRaised`, `divider`,
   `hover`, `selected`, `focusRing`).
4. **QML semantic facade** — `theme.<semanticToken>` binds `themeAuthority.*`
   (mapped via `theme_tokens_to_qml_semantics`).
5. **UI components** — use `theme.<semanticToken>` only (optional thin
   `window.*` aliases may mirror tokens for runtime property reads).

### Dark surface hierarchy (semantic, not screenshot pixels)

Dark Screen-1 must read as cinematic noir depth, not one flat black slab and not
an open gray tool UI. Theme Core owns the steps; QML only binds semantics.

| Step | Role | Semantic → token |
|------|------|------------------|
| 1 | Program Chrome (darkest / ink floor) | `surfaceHeader` → `background` |
| 2 | Main Workspace (barely raised charcoal/ink) | `surfaceRoot` → `surfaceWorkspace` |
| 3 | Panels (subtly separated, low mass, one family) | `surfacePanel` / `surfaceBrowser` → `surface` |

**Atmosphere (uniform panel family + calm workspace):** Library (`libraryPane`),
center workspace (`calmCanvas` empty; `browserPane` when active), Live Kit
(`liveKitPane`), and Harmonic Matching (`harmonyPane`) must paint Theme
soft-ellipse overlays (`theme.atmospherePanel` / `theme.atmosphereWorkspace`) so
depth is **subliminal** — not a visible glow effect and not a foreign brighter
pane. Overlays are Theme-rendered PNGs (no QML `Gradient`). See
`docs/assets/themes/README.md` atmosphere restraint + stop table.

Borders use `divider` / `borderSubtle` for fine restrained edges. Product
surfaces must not collapse chrome and workspace to the same fill. No flat
`#000000` hierarchy base. Typography mood stays calm/minimal (`textPrimary` /
`textSecondary` from Theme Core only). Feel: noir, deep, elegant, premium,
restrained — little visible UI mass. See `docs/assets/themes/README.md`
CURRENT→TARGET table (root cause + Blood noir example values).

### Functional accent rule

Accent is functional-only for controls: selection, active toggle, harmonic-match
active state, clear focus/active affordances, primary active action. Not for
solid panel fills, decoration, or passive chrome. Default Blood A accent is
`#8f0e24` (Blood B `#d4143a` is comparison-only).

**Narrow Theme exception:** cinematic-noir atmosphere stop mixes may include a
tiny accent bleed into ink (Theme Core only) so Library/center/Live Kit/Harmonic
read cool red-blue depth at **subliminal** strength. That is not a colorful
ambient wash or visible glow and must stay near-black.

### No arbitrary hardcodes rule

Screen-1 QML must not introduce direct HEX colors outside Theme Core /
`themeAuthority`. Named `transparent` remains a technical exception. Contract
tests under `tests/test_workbench_qml_screen1_color_contract.py` and
`tests/test_workbench_qml_theme_runtime.py` guard this. Hierarchy relations are
covered by `tests/test_workbench_dark_surface_hierarchy.py`.
