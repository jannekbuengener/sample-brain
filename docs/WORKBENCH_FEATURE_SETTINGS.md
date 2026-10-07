# Workbench Functional Feature Settings — Architecture Enabler (#910)

**Status:** Implemented — `CANONICAL_FUNCTIONAL_SETTINGS_OWNER_VIABLE`  
**Issue:** [#910](https://github.com/jannekbuengener/sample-brain/issues/910)  
**Parent:** [#680](https://github.com/jannekbuengener/sample-brain/issues/680)  
**Unblocks:** guarded gesture→Rack apply (historical blocker [#904](https://github.com/jannekbuengener/sample-brain/issues/904) / `FEATURE_SETTINGS_OWNER_BLOCKED`)

## Goal

Establish one canonical, reusable **functional feature settings** owner and one
minimal user-accessible Settings control path for Workbench product behavior.

This is an architecture enabler, not a gesture workflow slice and not a
gesture→Rack mutation slice.

## Motivation (live finding from #904)

Appearance/layout-scoped owners are not functional toggle authority:

| Owner | Scope | Functional toggle owner? |
|-------|-------|--------------------------|
| `WorkbenchViewSettings` | `show_*` visibility | No |
| Display Preferences / workspace presets | density, motion, layout | No |
| Theme / layout preference files | appearance / geometry | No |

#904 correctly stopped with `FEATURE_SETTINGS_OWNER_BLOCKED` rather than
overloading those owners or inventing a gesture-specific ad-hoc store.

## Design boundary

- Do **not** add functional flags to `WorkbenchViewSettings`
- Do **not** hide flags inside gesture modules
- Do **not** create one settings file per feature
- Do **not** create a second musical session/persistence owner
- Do **not** redesign the entire Preferences experience
- Do **not** implement `ChannelRackController.apply_gesture_integration_plan`
- Do **not** mutate Rack / Pattern / session musical state from settings changes

## Canonical owner

| Concern | Decision |
|---------|----------|
| Python value model | frozen `WorkbenchFeatureSettings` |
| Module | `src/workbench_feature_settings.py` |
| Persisted document | `workbench_feature_settings.json` under `workbench_state_dir()` |
| Schema | `schema_version: 1` (integer) |
| Defaults | deterministic; `gesture_rack_apply_enabled=False` |
| Malformed / wrong version | fail closed to defaults; do not crash startup |
| Unknown keys | ignored; must not silently enable known behavior |
| Cloud / accounts | none |

### Frozen model

```python
@dataclass(frozen=True)
class WorkbenchFeatureSettings:
    gesture_rack_apply_enabled: bool = False
    schema_version: int = 1  # FEATURE_SETTINGS_SCHEMA_VERSION
```

### Public seams

```text
load_workbench_feature_settings(*, state_dir=None, env=None) -> WorkbenchFeatureSettings
save_workbench_feature_settings(settings, *, state_dir=None, env=None) -> bool
replace_workbench_feature_settings(settings, /, **changes) -> WorkbenchFeatureSettings
workbench_feature_settings_path(*, state_dir=None, env=None) -> Path
```

Consumers (future #904-style apply) must read through these public seams or an
injected settings value — not by opening the JSON file from controller/gesture
code.

### Initial key — `gesture_rack_apply_enabled`

| Property | Value |
|----------|-------|
| Serialized key | `gesture_rack_apply_enabled` |
| Default | `False` (disabled) |
| Persist | yes, across restart |
| User control | yes, through canonical Settings surface |
| Disabled meaning | downstream feature code observes `False`; no hidden enable |

This slice only establishes/configures the flag. It does **not** wire apply
mutation.

### Product-path key — `arrangement_mode_enabled` (#1076 docs freeze)

| Property | Value |
|----------|-------|
| Serialized key | `arrangement_mode_enabled` |
| Default | `False` (disabled) |
| Persist | yes, across restart (when runtime field is implemented) |
| User control | yes, through the canonical Functional Settings surface (when wired) |
| Slice status | **Contract/docs-frozen only** in #1076 — not yet a runtime field on `WorkbenchFeatureSettings` |

This key is the sole Arrangement product rollout gate for the Edit → Arrangement path.
Do **not** introduce `performance_mode_enabled`. Do **not** invent a Live feature key here;
[#1088](https://github.com/jannekbuengener/sample-brain/issues/1088) owns later Live settings when reactivated.

**OFF (`False`) means:**

- no active Arrangement navigation / Arrangement Entry action;
- no UI-triggered hidden Arrangement scene or domain initialization from product navigation;
- no track folder merely because the app starts;
- no track folder merely because a sample is selected or the Live Kit is edited;
- Edit / Kit remains usable;
- Demo `Export Kit` remains separately usable under its existing contract.

**ON (`True`) means:**

- full-version Arrangement Entry **may** be offered later, subject to package/state/eligibility
  contracts ([#1082](https://github.com/jannekbuengener/sample-brain/issues/1082),
  [#1078](https://github.com/jannekbuengener/sample-brain/issues/1078)).

Runtime implementation of the field on `src/workbench_feature_settings.py` is deferred to the
first real consumer slice. Group A / #1076 must not claim the Python dataclass already contains
this key.

Internal Arrangement helpers (#1082–#1087) do not each need duplicate product toggles while this
gate remains OFF and product UI cannot reach them.

## User-accessible surface

Host a compact **Functional** section inside the existing Screen-1 header
preferences popover (`displayPreferencesPopover`), visually/semantically
distinct from Appearance / Density / Motion / layout actions.

| Requirement | Decision |
|-------------|----------|
| Product UI path | PySide6 / Qt Quick / QML |
| Entry point | existing `displayPreferencesOverflow` popover |
| Control | checkable toggle for Gesture → Rack apply |
| New Screen-1 workflow | no |
| Microphone / gesture record / generated-pattern button | no |
| Permanent settings bar / Tools panel | no |
| App-wide Preferences redesign | no |

Display/view preferences remain owned by #696 / `WorkbenchViewSettings` /
theme/layout modules. Functional toggles must not be mixed into those schemas.

## State ownership

Functional settings are **configuration**, not musical session state.

Do not store them in:

- `ChannelRackState`
- `WorkbenchSession` musical snapshot
- Pattern Core
- Live Kit state
- `GestureRackIntegrationPlan`

Changing a functional setting must not by itself stop playback, notify musical
autosave, or mutate Rack/Pattern state.

## Relationship to #904 evidence

`docs/GESTURE_RACK_CONTROLLER_APPLY_RND_SLICE8.md` remains historical evidence
of `FEATURE_SETTINGS_OWNER_BLOCKED` at the time of #904.

This enabler is the separate owner #904 required. A later #680 apply slice may
consume `gesture_rack_apply_enabled` through the public seams above. Do not
rewrite #904's historical exit into a fake pass.

## R&D / architecture exit

Exactly one:

- `CANONICAL_FUNCTIONAL_SETTINGS_OWNER_VIABLE`
- `SETTINGS_ARCHITECTURE_CONFLICT`
- `INSUFFICIENT_EVIDENCE`

`CANONICAL_FUNCTIONAL_SETTINGS_OWNER_VIABLE` means only:

A reusable Python-owned functional feature settings model exists, persists
deterministically, has a minimal user-accessible control path, keeps
display/view settings separate, and exposes a stable disabled-by-default
`gesture_rack_apply_enabled` flag that a later apply slice can consume.

It does **not** mean gesture→Rack mutation is implemented.

## Acceptance tests

See `tests/test_workbench_feature_settings_910.py`.

## Non-goals

Gesture→Rack apply seam, Rack musical mutation, playback stop, session autosave
mutation, pattern creation, microphone UI, gesture recording flow, off-grid
editor, Arrangement runtime/UI implementation, Live feature keys, general Preferences redesign.
