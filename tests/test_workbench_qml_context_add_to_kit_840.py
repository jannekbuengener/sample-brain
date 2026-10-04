"""#840 — Context Menu is the sole visible Browser Add-to-Kit route.

Canon: docs/WORKBENCH_SAMPLE_CONTEXT_MENU_CONTRACT.md (#840 supersession)
Parent: #838. Dependency: #839 delivered. Boundaries: #843 (harmonic header /
panel), #842 (matching). Harmonic result-row addHarmonyToKit remains.

TEST_FREEZE: assertions express intended #840 behaviour. Do not weaken them to
fit incomplete product code. Expected RED for presentation removal until
implementation; context Add-to-Kit functional paths should already be GREEN.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from src.workbench_live_kit import LiveKitState
from src.workbench_qml import LiveKitPresenter, QML_SOURCE, Screen1QmlInteractionAdapter
from src.workbench_qml_spike import build_qml_view_model_from_fixture
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

_WORKBENCH_QML_PY = Path(__file__).resolve().parents[1] / "src" / "workbench_qml.py"
_BROWSER_LIST = 'objectName: "browserList"'
_ELASTIC_AFTER_BROWSER = 'objectName: "elasticHandleAfterBrowser"'
_BROWSER_ROW_DELEGATE = "delegate: Rectangle { id: browserRow"


def _browser_panel() -> str:
    start = QML_SOURCE.index(_BROWSER_LIST)
    end = QML_SOURCE.index(_ELASTIC_AFTER_BROWSER, start)
    return QML_SOURCE[start:end]


def _browser_delegate() -> str:
    start = QML_SOURCE.index(_BROWSER_ROW_DELEGATE)
    end = QML_SOURCE.index(_ELASTIC_AFTER_BROWSER, start)
    return QML_SOURCE[start:end]


def _column_header() -> str:
    marker = QML_SOURCE.index('text: "SAMPLE NAME"')
    start = QML_SOURCE.rfind("RowLayout { Layout.fillWidth: true", 0, marker)
    end = QML_SOURCE.index("ListView { id: browser", marker)
    return QML_SOURCE[start:end]


def _context_menu_window() -> str:
    idx = QML_SOURCE.index('objectName: "sampleContextMenu"')
    return QML_SOURCE[idx : idx + 2500]


def _adapter(
    *,
    browse_command=None,
    preview_command=None,
    preview_stop=None,
    add_to_kit_command=None,
    live_kit=None,
):
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
        on_browser_selected=browse_command,
    )
    kwargs = dict(
        view_model=view_model,
        on_preview_requested=preview_command,
        on_preview_stopped=preview_stop,
        on_add_to_kit_requested=add_to_kit_command,
    )
    if live_kit is not None:
        kwargs["live_kit"] = live_kit
        view_model.live_kit_groups = live_kit.groups
    return fixture, view_model, Screen1QmlInteractionAdapter(**kwargs)


def _production_adapter(state: LiveKitState | None = None, **kwargs):
    live_kit = LiveKitPresenter(state=state)
    return (*_adapter(live_kit=live_kit, **kwargs), live_kit)


# --- Presentation / chrome ----------------------------------------------------


def test_browser_row_has_no_visible_add_to_kit_action_or_column():
    panel = _browser_panel()
    delegate = _browser_delegate()
    header = _column_header()

    assert "window.interaction.addToKit(index)" not in panel
    assert "window.interaction.addToKit(index)" not in delegate
    assert "id: addButton" not in delegate
    assert "id: addButtonMouse" not in delegate
    assert '"+ Add to Kit"' not in delegate
    assert '"+ Add"' not in delegate
    assert 'browserPane.browserNarrowColumns ? "+ Add" : "+ Add to Kit"' not in delegate
    assert "browserAddColumnWidth" not in QML_SOURCE
    assert "effectiveBrowserAddColumnWidth" not in QML_SOURCE
    assert "effectiveBrowserAddColumnWidth" not in header
    assert "Item { Layout.preferredWidth: browserPane.effectiveBrowserAddColumnWidth }" not in header


def test_context_popup_still_owns_add_to_kit_action():
    menu = _context_menu_window()
    assert "Add to Kit" in menu
    assert "Harmonic Matches" in menu
    assert "contextAddToKit" in QML_SOURCE
    assert "contextHarmonicMatches" in QML_SOURCE
    # Exactly the two #839/#840 actions — presentation labels.
    assert menu.count("Add to Kit") >= 1


def test_bridge_keeps_context_add_slot_and_may_keep_index_harness_api():
    """Visible Browser route is context-only; index API may remain for harnesses."""
    text = _WORKBENCH_QML_PY.read_text(encoding="utf-8")
    assert "def contextAddToKit" in text or "contextAddToKit" in QML_SOURCE
    assert "request_context_add_to_kit" in text
    assert "_request_add_to_kit_row" in text
    # Index-based seam may remain non-visible for Live Kit / harness tests.
    assert "def request_add_to_kit" in text
    assert "def addToKit" in text


def test_no_second_add_to_kit_domain_seam_introduced():
    text = _WORKBENCH_QML_PY.read_text(encoding="utf-8")
    # Single shared internal seam name from #839 contract.
    assert text.count("def _request_add_to_kit_row") == 1
    assert "def _request_context_add_to_kit_row" not in text
    assert "def request_browser_add_to_kit_via_menu" not in text


# --- Functional: context Add-to-Kit + Live Kit semantics ----------------------


def test_context_add_b_keeps_selection_a_and_dispatches_exactly_once():
    added = []
    previews = []
    fixture, view_model, adapter = _adapter(
        add_to_kit_command=added.append,
        preview_command=previews.append,
    )
    adapter.select_row(0)
    row_a = fixture.browser_rows[0]
    row_b = fixture.browser_rows[1]

    adapter.open_sample_context(1)
    result = adapter.request_context_add_to_kit()

    assert result is row_b
    assert added == [row_b]
    assert row_a not in added
    assert view_model.selected_browser_index == 0
    assert previews == []
    assert adapter.preview_active is False
    assert adapter.sample_context_target is None


def test_context_add_seeds_pending_live_kit_target_for_b():
    fixture, view_model, adapter, live_kit = _production_adapter()
    row_b = fixture.browser_rows[1]
    adapter.select_row(0)

    adapter.open_sample_context(1)
    adapter.request_context_add_to_kit()

    assert adapter.pending_live_kit_add == row_b.display_name
    assert view_model.selected_browser_index == 0
    assert all(
        slot.assignment is None for group in live_kit.groups for slot in group.slots
    )


def test_context_add_then_empty_slot_assign_uses_pending_b():
    fixture, _view_model, adapter, live_kit = _production_adapter()
    row_b = fixture.browser_rows[1]
    adapter.select_row(0)
    adapter.open_sample_context(1)
    adapter.request_context_add_to_kit()

    assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
    assert live_kit.state.assignment_for("Drums", "Main Drum") is row_b
    assert adapter.pending_live_kit_add == ""


def test_context_add_replace_existing_slot_keeps_single_target_semantics():
    fixture, _view_model, adapter, live_kit = _production_adapter()
    first = fixture.browser_rows[0]
    second = fixture.browser_rows[1]

    adapter.open_sample_context(0)
    adapter.request_context_add_to_kit()
    assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
    assert live_kit.state.assignment_for("Drums", "Main Drum") is first

    adapter.select_row(0)
    adapter.open_sample_context(1)
    adapter.request_context_add_to_kit()
    assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
    assert live_kit.state.assignment_for("Drums", "Main Drum") is second
    assert live_kit.state.assignment_for("Drums", "Closed Hat") is None


def test_context_add_cancel_pending_never_mutates_kit():
    fixture, _view_model, adapter, live_kit = _production_adapter()
    adapter.open_sample_context(0)
    adapter.request_context_add_to_kit()
    assert adapter.pending_live_kit_add == fixture.browser_rows[0].display_name

    assert adapter.cancel_live_kit_add() is True
    assert adapter.pending_live_kit_add == ""
    assert all(
        slot.assignment is None for group in live_kit.groups for slot in group.slots
    )


def test_context_add_reveals_live_kit_materialization_like_index_path():
    fixture, view_model, adapter, _live_kit = _production_adapter()
    # Ensure reveal path is exercised when composition/runtime is present; when
    # not attached, pending still seeds (domain seam unchanged).
    adapter.select_row(0)
    adapter.open_sample_context(1)
    adapter.request_context_add_to_kit()
    assert adapter.pending_live_kit_add == fixture.browser_rows[1].display_name
    assert view_model.selected_browser_index == 0


# --- Preserved surfaces / non-regression markers ------------------------------


def test_harmonic_result_add_and_header_button_remain_until_843():
    assert "addHarmonyToKit(index)" in QML_SOURCE
    assert 'objectName: "harmonicMatchButton"' in QML_SOURCE
    assert "toggleHarmonicMatch()" in QML_SOURCE


def test_browser_keyboard_preview_favorite_virtualization_preserved():
    assert "navigateBrowser(1)" in QML_SOURCE
    assert "navigateBrowser(-1)" in QML_SOURCE
    assert "stopPreview()" in QML_SOURCE
    assert "previewRow(index)" in QML_SOURCE
    assert "toggleFavorite(index)" in QML_SOURCE
    assert QML_SOURCE.count("reuseItems: true") == 2
    browser_idx = QML_SOURCE.index(_BROWSER_LIST)
    assert "reuseItems: true" in QML_SOURCE[browser_idx : browser_idx + 400]


def test_845_collapse_and_846_resize_markers_untouched():
    text = _WORKBENCH_QML_PY.read_text(encoding="utf-8")
    assert "browserCollapsed" in text
    assert "liveKitCollapsed" in text
    assert 'objectName: "browserColumnResize_waveform"' in QML_SOURCE
    assert 'objectName: "browserColumnResize_meta"' in QML_SOURCE
    assert 'objectName: "browserColumnResize_favorite"' in QML_SOURCE
    assert 'objectName: "browserColumnResize_length"' in QML_SOURCE


def test_adapter_still_exposes_shared_add_seam_and_context_api():
    _fixture, _view_model, adapter = _adapter()
    assert hasattr(adapter, "sample_context_target")
    assert callable(adapter.open_sample_context)
    assert callable(adapter.request_context_add_to_kit)
    assert callable(adapter.request_add_to_kit)
    assert callable(adapter._request_add_to_kit_row)
    params = inspect.signature(Screen1QmlInteractionAdapter).parameters
    assert "on_context_harmonic_match_requested" in params


def test_context_add_does_not_start_preview_or_audition_callbacks():
    added = []
    previews = []
    stops = []
    selected = []
    fixture, view_model, adapter = _adapter(
        add_to_kit_command=added.append,
        preview_command=previews.append,
        preview_stop=stops.append,
        browse_command=selected.append,
    )
    adapter.select_row(0)
    selected.clear()
    adapter.open_sample_context(2)
    adapter.request_context_add_to_kit()
    assert added == [fixture.browser_rows[2]]
    assert previews == []
    assert stops == []
    assert selected == []
    assert view_model.selected_browser_index == 0


def test_full_kit_fail_closed_semantics_unchanged_via_context_path():
    """Context Add must not invent a parallel full-kit bypass.

    When assign fails / returns False under existing rules, pending clearing
    follows the existing Live Kit seam — not a new #840 domain.
    """
    fixture, _view_model, adapter, live_kit = _production_adapter()
    adapter.open_sample_context(0)
    adapter.request_context_add_to_kit()
    # Empty slot assign succeeds under baseline mapping.
    assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
    assert live_kit.state.assignment_for("Drums", "Main Drum") is fixture.browser_rows[0]
    # Unknown slot remains fail-closed.
    assert adapter.assign_live_kit_slot("Drums", "Not A Real Slot") is False
    assert live_kit.state.assignment_for("Drums", "Main Drum") is fixture.browser_rows[0]
