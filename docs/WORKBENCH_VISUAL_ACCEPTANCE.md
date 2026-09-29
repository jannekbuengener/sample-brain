# Screen-1 Visual Acceptance

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

The Owner must mark `PASS` or `FAIL` against `docs/assets/portfolio/mockups/ui_mockup.png` and
`docs/assets/portfolio/mockups/ui_mockup_matching.png` for hierarchy, spacing/density, typography, controls,
color/intent, discoverability, clipping/overflow, populated/empty states, and
overall producer-tool quality. Agent attestation is not an Owner PASS.

P0/P1 findings block closure. P2/P3 are recorded separately and do not trigger
automatic repair. A Screen-1 UI issue closes only after structural tests,
`VALID` runtime, both captures, automated sanity, Owner PASS, no P0/P1, and
commit/PR-bound evidence.

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

For normal launch visibility / restore specifically: `#693` supersedes historical
`#503/#518` restore behaviour (see Clean Start doc).

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
| `screen1-clean-start` | Source Navigation + Calm Canvas; no source selected; browser / harmonic / Live Kit **not** materialised as active working panes; no preview / no sample selection |
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
- `motion_mode` (`full` / `reduced` / `off`)
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
- Owner Visual Acceptance remains separate from agent self-attestation

Follow-up UI slices (#692–#696) must reference these v2 state IDs instead of
inventing parallel fixture semantics.

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
  Bildhierarchie ab; Accent `#b1122b` nur funktional (Selection / Active /
  Toggle). Kein dekoratives Rot oder Blau.
- Frozen v1 Portfolio-Screenshots unter `docs/assets/portfolio/runtime/`
  bleiben unverändert.

## Screen-1 canonical color contract

Source of truth for Screen-1 colors is the embedded `theme` QtObject in
`src/workbench_qml.py` (`QML_SOURCE`). Layers:

1. **Background reference** — unchanged PNG above; not a color palette source.
2. **Color primitives** — raw HEX values only (near-black / neutral / one accent).
3. **Semantic tokens** — meaning for UI states; components bind to these, not HEX.
4. **UI components** — use `theme.<semanticToken>` (optional thin `window.*`
   aliases may mirror tokens for runtime property reads).

### Primitive palette

| Primitive | HEX | Notes |
|-----------|-----|--------|
| `neutral000` | `#000000` | root / deepest surface |
| `neutral050` | `#050506` | header |
| `neutral075` | `#0a0b0c` | browser pane |
| `neutral100` | `#0c0d0e` | panel |
| `neutral150` | `#141516` | elevated / hover surface |
| `neutral250` | `#222426` | border / divider |
| `contentPrimary` | `#eceef1` | primary text |
| `contentSecondary` | `#8b9098` | muted / secondary text |
| `contentDisabled` | `#8b9098` | disabled/offline text (same value as secondary; no invented gray) |
| `contentOnAction` | `#ffffff` | text on solid accent control |
| `waveformNeutral` | `#6d737c` | idle waveform |
| `accentPrimary` | `#b1122b` | functional accent only |
| `accentSurface` | `#1a1012` | selection / active surface |

Do not add primitives without a real semantic consumer. Do not invent decorative
blues, neons, glows, or extra reds.

### Semantic tokens

| Token | Primitive | Use |
|-------|-----------|-----|
| `surfaceRoot` | `neutral000` | window root |
| `surfaceHeader` | `neutral050` | header bar |
| `surfaceBrowser` | `neutral075` | browser pane |
| `surfacePanel` | `neutral100` | library / harmonic / live-kit panels |
| `surfaceElevated` | `neutral150` | hover / elevated row surface |
| `borderSubtle` | `neutral250` | panel borders |
| `dividerDefault` | `neutral250` | row dividers |
| `textPrimary` | `contentPrimary` | primary labels |
| `textSecondary` | `contentSecondary` | captions / muted labels |
| `textDisabled` | `contentDisabled` | offline / unavailable |
| `textOnAction` | `contentOnAction` | label on solid accent |
| `waveformDefault` | `waveformNeutral` | idle waveform stroke |
| `waveformActive` | `accentPrimary` | selected-row waveform |
| `selectionSurface` | `accentSurface` | selected row / active kit surface |
| `selectionBorder` | `accentPrimary` | selected/active border |
| `actionActive` | `accentPrimary` | active toggle, focus, primary action, harmonic-match on |

### Functional accent rule

Red (`accentPrimary`) is functional-only: selection, active toggle, harmonic-match
active state, clear focus/active affordances, primary active action. Not for
panel fills, ambient backgrounds, decoration, or passive chrome.

### No arbitrary hardcodes rule

Screen-1 QML must not introduce new direct HEX colors outside the `theme`
primitive block. Named `transparent` remains a technical exception. Contract
tests under `tests/test_workbench_qml_screen1_color_contract.py` guard this.
