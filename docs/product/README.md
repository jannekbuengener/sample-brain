# Product Pillar Specs — Sample Brain

Canonical pillar contracts for the VST-first product target ([Issue #90](https://github.com/jannekbuengener/sample-brain/issues/90)). Parent vision and MVP scope live in [`docs/PRODUCT_REQUIREMENTS.md`](../PRODUCT_REQUIREMENTS.md) §5–6; these specs add implementable contracts per pillar.

## Pillar index

| Pillar | Issue | Spec | Status |
|--------|-------|------|--------|
| Parent — VST-first producing intelligence | [#90](https://github.com/jannekbuengener/sample-brain/issues/90) | PRD §5–6, [`DAW_INTEGRATION_SPEC.md`](../DAW_INTEGRATION_SPEC.md) | Parent consolidated (PR #102); child specs in progress |
| **[LIBRARY]** Library Intelligence & Metadata/Naming | [#94](https://github.com/jannekbuengener/sample-brain/issues/94) | [`01_LIBRARY_INTELLIGENCE_SPEC.md`](01_LIBRARY_INTELLIGENCE_SPEC.md) | **Spec available** |
| **[MATCHING]** Harmonic & Rhythmic Matching | [#91](https://github.com/jannekbuengener/sample-brain/issues/91) | [`02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md`](02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md) | **Spec available** |
| **[CONTEXT]** Track Context Analysis | [#95](https://github.com/jannekbuengener/sample-brain/issues/95) | *(planned)* `03_TRACK_CONTEXT_ANALYSIS_SPEC.md` | Not started |
| **[TRANSFORM]** Realtime Fit & Transform Engine | [#92](https://github.com/jannekbuengener/sample-brain/issues/92) | *(planned)* `04_REALTIME_TRANSFORM_ENGINE_SPEC.md` | Not started |
| **[WORKSPACE]** VST-first Producing Workspace | [#93](https://github.com/jannekbuengener/sample-brain/issues/93) | *(planned)* `05_VST_PRODUCING_WORKSPACE_SPEC.md` | Not started |

## Dependency order

```text
Library (#94)  →  Matching (#91)  →  Transform (#92)
       ↓                ↓
  Context (#95)    Workspace (#93)
```

Runtime on `main` today: CLI scan → analyze → autotype → export (legacy FL); optional embed/index/search; partial matching via `sample-brain match`. VST3 plugin and transform engine are not implemented.

## Related documents

| Document | Role |
|----------|------|
| [`docs/PRODUCT_REQUIREMENTS.md`](../PRODUCT_REQUIREMENTS.md) | Vision, audience, MVP scope |
| [`docs/TARGET_ARCHITECTURE.md`](../TARGET_ARCHITECTURE.md) | Module boundaries, §10.2 VST workspace target |
| [`docs/DATA_AND_ARTIFACT_POLICY.md`](../DATA_AND_ARTIFACT_POLICY.md) | Committed vs runtime artifacts |
| [`docs/DAW_INTEGRATION_SPEC.md`](../DAW_INTEGRATION_SPEC.md) | FL export fallback + VST3 product tiers |
