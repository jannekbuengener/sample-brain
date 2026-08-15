# Product Pillar Specs — Sample Brain

Canonical pillar contracts for the VST-first product target ([Issue #90](https://github.com/jannekbuengener/sample-brain/issues/90)). Parent vision and MVP scope live in [`docs/PRODUCT_REQUIREMENTS.md`](../PRODUCT_REQUIREMENTS.md) §5–6; these specs add implementable contracts per pillar.

## Pillar index

| Pillar | Issue | Spec | Status |
|--------|-------|------|--------|
| Parent — VST-first producing intelligence | [#90](https://github.com/jannekbuengener/sample-brain/issues/90) | PRD §5–6, [`DAW_INTEGRATION_SPEC.md`](../DAW_INTEGRATION_SPEC.md) | **Parent spec complete** — PR #102 consolidated; all child specs done; parent closes via reconcile PR |
| **[LIBRARY]** Library Intelligence & Metadata/Naming | [#94](https://github.com/jannekbuengener/sample-brain/issues/94) | [`01_LIBRARY_INTELLIGENCE_SPEC.md`](01_LIBRARY_INTELLIGENCE_SPEC.md) | **Done** (PR #105) |
| **[MATCHING]** Harmonic & Rhythmic Matching | [#91](https://github.com/jannekbuengener/sample-brain/issues/91) | [`02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md`](02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md) | **Done** (PR #105) |
| **[CONTEXT]** Track Context Analysis | [#95](https://github.com/jannekbuengener/sample-brain/issues/95) | [`03_TRACK_CONTEXT_ANALYSIS_SPEC.md`](03_TRACK_CONTEXT_ANALYSIS_SPEC.md) | **Done** (PR #106) |
| **[TRANSFORM]** Realtime Fit & Transform Engine | [#92](https://github.com/jannekbuengener/sample-brain/issues/92) | [`04_REALTIME_FIT_TRANSFORM_SPEC.md`](04_REALTIME_FIT_TRANSFORM_SPEC.md) | **Done** (PR #106) |
| **[WORKSPACE]** VST-first Producing Workspace | [#93](https://github.com/jannekbuengener/sample-brain/issues/93) | [`05_VST_PRODUCING_WORKSPACE_SPEC.md`](05_VST_PRODUCING_WORKSPACE_SPEC.md) | **Done** (PR #106) |

## Dependency order

Recommended build and documentation order:

```text
1. Library (#94)     →  catalog + features
2. Matching (#91)    →  fit scoring
3. Context (#95)     →  track profile
4. Transform (#92)   →  playable variants
5. Workspace (#93)   →  VST3 UI + host integration
```

Context and Transform can be developed in parallel after Library + Matching; Workspace integrates all pillars.

Runtime on `main` today: CLI scan → analyze → autotype → export_fl (legacy FL); optional embed/index/search; matching via `sample-brain match`; track context analysis via `sample-brain context analyze` (Track Map v1 + Track Analysis Cache); track deconstruction via `sample-brain deconstruct` (Track Map, Arrangement, Loop/Section Assets, Performance Pack layout); pack import via `sample-brain pack-import`. VST3 plugin and transform engine are not implemented.

## Related documents

| Document | Role |
|----------|------|
| [`docs/PRODUCT_REQUIREMENTS.md`](../PRODUCT_REQUIREMENTS.md) | Vision, audience, MVP scope |
| [`docs/TARGET_ARCHITECTURE.md`](../TARGET_ARCHITECTURE.md) | Module boundaries, §10.2 VST workspace target |
| [`docs/DATA_AND_ARTIFACT_POLICY.md`](../DATA_AND_ARTIFACT_POLICY.md) | Committed vs runtime artifacts |
| [`docs/DAW_INTEGRATION_SPEC.md`](../DAW_INTEGRATION_SPEC.md) | FL export fallback + VST3 product tiers |
