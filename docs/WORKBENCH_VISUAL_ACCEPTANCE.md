# Screen-1 Visual Acceptance

Run only from a verified dedicated runtime:

```text
python -m src.cli workbench --visual-acceptance --runtime-root <runtime-root> --evidence-dir <local-output>
```

The command uses an isolated temporary Workbench state, loads
`screen1_visual_fixture_v1`, captures only the Windows client window at
1600×900 / 100% DPI, and writes two PNGs plus `manifest.json` outside the
repository. It fails closed unless Runtime-Provenance is `VALID`.

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
