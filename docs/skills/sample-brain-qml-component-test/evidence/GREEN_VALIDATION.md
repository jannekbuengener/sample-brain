# GREEN validation — `sample-brain-qml-component-test` (#1305)

**Status:** after skill body  
**Same prompt as RED:** right-click unselected browser row → Add to Kit
exactly once; selection unchanged; distinguish Menu key selected-index path.  
**Skill used:** `docs/skills/sample-brain-qml-component-test/SKILL.md`

## Compact test design produced with the skill

```text
Behavior/authority:
  Right-click opens sample context for the clicked row without changing
  selection; Add to Kit emits exactly one intent for sample_context_target.
  Python adapter owns target identity; QML owns gesture/Popup/focus.

Why QML component coverage required:
  Adapter + QML_SOURCE substring asserts stay green while MouseArea right-click,
  Popup activation, or Menu-key index source can still regress.

Layer decision: mixed

Fixture/boundary:
  build_screen1_visual_fixture_v1 → build_qml_view_model_from_fixture →
  Screen1QmlInteractionAdapter → _qml_engine; QTest on the live window.

Inputs/events:
  select row 0 via adapter/bridge; QTest RightButton on row-1 scene point;
  click context Add-to-Kit item once; separately Key_Menu on focused browserList.

Observable assertions:
  addToKitIntent / callback length == 1 and targets row 1 path;
  selected_browser_index remains 0 across right-click open;
  Menu path opens context for selected index (0), not hover/delegate confusion;
  Popup visible then closed; browser regains focus after Escape/close.

Async/wait strategy:
  qWaitForWindowExposed + _settle_qml_frame / processEvents until Popup
  property visible / intent observed — no multi-second sleep.

Lifecycle/virtualization:
  Do not keep a stale QQuickItem delegate identity across scroll; re-map
  scene points from browserList geometry (reuseItems: true).

Companion tests:
  Keep tests/test_workbench_qml_sample_context_menu_839.py Python contracts.

Non-goals:
  Screenshots; audition PCM; product redesign of the context menu.
```

## Material improvement vs RED

| RED miss | GREEN closure |
|----------|---------------|
| Python-only layer | Explicit `mixed` with real QML events |
| Static `RightButton` as proof | QTest RightButton + menu activation |
| No keyboard vs pointer index | Separate Menu-key assertion |
| No wait strategy | Frame settle / condition wait |
| Virtualization ignored | Explicit reuseItems / re-map note |
| Exactly-once only in adapter | Bridge intent count after QML path |

## Focused executable pattern

`tests/test_qml_component_context_menu_pattern_1305.py` implements the pointer
exactly-once + selection invariance path as a non-mutating product regression
guard demonstrating the skill pattern.

## Verdict

`SAMPLE_BRAIN_QML_COMPONENT_TEST_SKILL_EFFECTIVE` for scenario A (same RED
prompt).
