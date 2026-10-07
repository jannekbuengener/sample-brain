# Product Pillar Specs — Sample Brain

Capability specs for library, matching, context, and transform cores that feed the **local Workbench**. Primary producing path: [`docs/PRODUCT_WORKFLOW_CANON.md`](../PRODUCT_WORKFLOW_CANON.md). Parent vision: [`docs/PRODUCT_REQUIREMENTS.md`](../PRODUCT_REQUIREMENTS.md) §5–6.

**Supersession:** The historical “VST-first producing workspace” framing (#90 / #93) is **parked** (historical #469; issue record deleted). Pillar specs remain useful for **core capability contracts**; they do **not** authorize VST as the main product interface.

## Pillar index

| Pillar | Issue | Spec | Status |
|--------|-------|------|--------|
| Parent — producing intelligence cores | [#90](https://github.com/jannekbuengener/sample-brain/issues/90) | PRD §5–6, workflow canon, [`DAW_INTEGRATION_SPEC.md`](../DAW_INTEGRATION_SPEC.md) | Spec set complete; VST-first parent framing superseded |
| **[LIBRARY]** Library Intelligence & Metadata/Naming | [#94](https://github.com/jannekbuengener/sample-brain/issues/94) | [`01_LIBRARY_INTELLIGENCE_SPEC.md`](01_LIBRARY_INTELLIGENCE_SPEC.md) | **Done** (PR #105) |
| **[MATCHING]** Harmonic & Rhythmic Matching | [#91](https://github.com/jannekbuengener/sample-brain/issues/91) | [`02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md`](02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md) | **Done** (PR #105) |
| **[CONTEXT]** Track Context Analysis | [#95](https://github.com/jannekbuengener/sample-brain/issues/95) | [`03_TRACK_CONTEXT_ANALYSIS_SPEC.md`](03_TRACK_CONTEXT_ANALYSIS_SPEC.md) | **Done** (PR #106) |
| **[TRANSFORM]** Realtime Fit & Transform Engine | [#92](https://github.com/jannekbuengener/sample-brain/issues/92) | [`04_REALTIME_FIT_TRANSFORM_SPEC.md`](04_REALTIME_FIT_TRANSFORM_SPEC.md) | **Done** (PR #106) |
| **[WORKSPACE]** Producing Workspace | [#93](https://github.com/jannekbuengener/sample-brain/issues/93) | [`05_VST_PRODUCING_WORKSPACE_SPEC.md`](05_VST_PRODUCING_WORKSPACE_SPEC.md) | Spec exists; **VST UI parked** (historical #469) — active product path is Edit → Arrangement → later Live (#1075/#1076); Arrangement owner #679 ACTIVE; later Live parked under #1088 |

## Dependency order

```text
1. Library (#94)     →  catalog + features
2. Matching (#91)    →  fit scoring
3. Context (#95)     →  track profile
4. Transform (#92)   →  playable variants (optional for Pattern/Rack foundation)
5. Workbench UI      →  Edit (incl. Live Kit tool) → Arrangement → later Live
   (VST shell #93 UI remains parked; historical #469)
```

Runtime on `main` today: CLI scan → analyze → autotype → export_fl (legacy FL); optional embed/index/search; matching / context / deconstruct / pack-import as documented; Workbench Edit surface + Live Kit tool (QML production path; Tk legacy/fallback); Pattern Core, the sequencer scheduling seam, Channel Rack Python core, the production sequencer PCM cache/decode provider (#676), and Channel Rack QML (#678 / PR #755). Arrangement owner [#679](https://github.com/jannekbuengener/sample-brain/issues/679) is **ACTIVE** (contracts/domain/UI via children); later Live remains parked under [#1088](https://github.com/jannekbuengener/sample-brain/issues/1088). Historical “Screen 3” wording is evidence only. VST3 plugin remains parked.

## Related documents

| Document | Role |
|----------|------|
| [`docs/PRODUCT_WORKFLOW_CANON.md`](../PRODUCT_WORKFLOW_CANON.md) | Primary producing workflow + build order |
| [`docs/PRODUCT_REQUIREMENTS.md`](../PRODUCT_REQUIREMENTS.md) | Vision, audience, MVP scope |
| [`docs/TARGET_ARCHITECTURE.md`](../TARGET_ARCHITECTURE.md) | Module boundaries, Workbench-first §10.2 |
| [`docs/DATA_AND_ARTIFACT_POLICY.md`](../DATA_AND_ARTIFACT_POLICY.md) | Committed vs runtime artifacts |
| [`docs/DAW_INTEGRATION_SPEC.md`](../DAW_INTEGRATION_SPEC.md) | FL export fallback + parked VST notes |
| [`docs/PATTERN_CORE_CONTRACT.md`](../PATTERN_CORE_CONTRACT.md) | Minimal Channel / Pattern / Trigger contract — implemented in `src/pattern_core.py` (#656) |
| [`docs/SEQUENCER_PLAYBACK_CONTRACT.md`](../SEQUENCER_PLAYBACK_CONTRACT.md) | Pattern → TempoMap → native scheduling (#663) + production PCM cache/decode provider (#676) |
| [`docs/SESSION_OWNERSHIP_CONTRACT.md`](../SESSION_OWNERSHIP_CONTRACT.md) | Single Live Kit + QML→native audio ownership (completed on `main`) |
| [`docs/TRACK_PACKAGE_OWNERSHIP_CONTRACT.md`](../TRACK_PACKAGE_OWNERSHIP_CONTRACT.md) | #1082 track package / portability / legacy-session migration freeze (`TRACK_PACKAGE_OWNERSHIP_CONTRACT_FROZEN`); runtime #1085 |
| [`docs/ARRANGEMENT_32_FIELD_TIME_CONTRACT.md`](../ARRANGEMENT_32_FIELD_TIME_CONTRACT.md) | #1083 32-field / 8-bar sequencer time freeze (`ARRANGEMENT_32_FIELD_TIME_CONTRACT_FROZEN`); runtime #1086 |
