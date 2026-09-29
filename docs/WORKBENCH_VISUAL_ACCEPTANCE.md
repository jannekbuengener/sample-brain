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

Additive contract. **No product behaviour change.** Density (#692), Clean Start
product code (#693), Elastic Solver (#694), Waveform motion (#695), and Live Kit
redesign are out of scope for this fixture layer.

Authority on conflicts for Startup / Density / Panel geometry / Persistence:

`scoped #691 child > #691 > #700 contract docs > historical #503 visual acceptance`

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
