"""#839 Sample context menu — frozen contracts.

Canon: docs/WORKBENCH_SAMPLE_CONTEXT_MENU_CONTRACT.md
Parent: #838. Boundaries: #840 (row Add-to-Kit removal), #842 (matching),
#843 (harmonic panel bind).

TEST_FREEZE: assertions below express the intended #839 behaviour. Do not weaken
them to fit incomplete product code. Expected RED until implementation.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_qml import QML_SOURCE, Screen1QmlInteractionAdapter
from src.workbench_qml_spike import build_qml_view_model_from_fixture
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

_WORKBENCH_QML_PY = Path(__file__).resolve().parents[1] / "src" / "workbench_qml.py"
_HEX_RE = re.compile(r'"(#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8}))"')


def _adapter(
    *,
    browse_command=None,
    preview_command=None,
    preview_stop=None,
    add_to_kit_command=None,
    context_harmonic_command=None,
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
    params = inspect.signature(Screen1QmlInteractionAdapter).parameters
    if "on_context_harmonic_match_requested" in params:
        kwargs["on_context_harmonic_match_requested"] = context_harmonic_command
    return fixture, view_model, Screen1QmlInteractionAdapter(**kwargs)


def _require_context_api(adapter: Screen1QmlInteractionAdapter) -> None:
    assert hasattr(adapter, "sample_context_target")
    assert callable(getattr(adapter, "open_sample_context", None))
    assert callable(getattr(adapter, "close_sample_context", None))
    assert callable(getattr(adapter, "request_context_add_to_kit", None))
    assert callable(getattr(adapter, "request_context_harmonic_matches", None))


# --- Adapter API / target ownership ------------------------------------------


def test_adapter_exposes_frozen_sample_context_api_without_alias():
    _fixture, _view_model, adapter = _adapter()
    _require_context_api(adapter)
    assert not hasattr(adapter, "context_sample")
    params = inspect.signature(Screen1QmlInteractionAdapter).parameters
    assert "on_context_harmonic_match_requested" in params
    assert callable(getattr(adapter, "_request_add_to_kit_row", None))


def test_open_context_on_b_keeps_selection_a_and_sets_stable_row_target():
    selected_callbacks = []
    previews = []
    fixture, view_model, adapter = _adapter(
        browse_command=selected_callbacks.append,
        preview_command=previews.append,
    )
    _require_context_api(adapter)

    adapter.select_row(0)
    selected_callbacks.clear()
    row_a = fixture.browser_rows[0]
    row_b = fixture.browser_rows[1]
    assert view_model.selected_browser_index == 0

    opened = adapter.open_sample_context(1)

    assert opened is row_b
    assert adapter.sample_context_target is row_b
    assert adapter.sample_context_target is not row_a
    assert view_model.selected_browser_index == 0
    assert selected_callbacks == []
    assert previews == []
    assert adapter.preview_active is False


def test_open_context_does_not_dispatch_audition_or_select_callbacks():
    selected_callbacks = []
    previews = []
    stops = []
    fixture, _view_model, adapter = _adapter(
        browse_command=selected_callbacks.append,
        preview_command=previews.append,
        preview_stop=stops.append,
    )
    _require_context_api(adapter)
    adapter.select_row(0)
    selected_callbacks.clear()

    adapter.open_sample_context(2)

    assert adapter.sample_context_target is fixture.browser_rows[2]
    assert selected_callbacks == []
    assert previews == []
    assert stops == []


def test_context_add_to_kit_dispatches_exactly_once_for_target_while_selection_stays():
    added = []
    fixture, view_model, adapter = _adapter(add_to_kit_command=added.append)
    _require_context_api(adapter)
    adapter.select_row(0)
    row_b = fixture.browser_rows[1]

    adapter.open_sample_context(1)
    result = adapter.request_context_add_to_kit()

    assert result is row_b
    assert added == [row_b]
    assert view_model.selected_browser_index == 0


def test_context_add_to_kit_uses_stored_row_when_visible_index_now_points_elsewhere():
    """While target is held, action must use the WorkbenchRow object — not index 1."""
    added = []
    fixture, view_model, adapter = _adapter(add_to_kit_command=added.append)
    _require_context_api(adapter)
    adapter.select_row(0)
    row_b = fixture.browser_rows[1]
    row_c = fixture.browser_rows[2]
    assert row_b is not row_c

    adapter.open_sample_context(1)
    assert adapter.sample_context_target is row_b

    # Bypass invalidation hooks: only the visible projection order changes.
    # Index 1 now resolves to C; context Add-to-Kit must still dispatch B.
    from src.workbench_qml import _qml_row

    view_model.browser_rows = (
        _qml_row(fixture.browser_rows[0]),
        _qml_row(row_c),
        _qml_row(row_b),
        *tuple(_qml_row(r) for r in fixture.browser_rows[3:]),
    )
    assert view_model.browser_rows[1].source_row is row_c
    assert adapter.sample_context_target is row_b

    result = adapter.request_context_add_to_kit()
    assert result is row_b
    assert added == [row_b]
    assert row_c not in added


def test_rows_reproject_clears_target_so_stale_index_cannot_dispatch():
    added = []
    fixture, view_model, adapter = _adapter(add_to_kit_command=added.append)
    _require_context_api(adapter)
    row_b = fixture.browser_rows[1]
    row_c = fixture.browser_rows[2]
    adapter.open_sample_context(1)
    assert adapter.sample_context_target is row_b

    reordered = (
        fixture.browser_rows[0],
        fixture.browser_rows[2],
        fixture.browser_rows[1],
        *fixture.browser_rows[3:],
    )
    view_model.set_browser_state(
        rows=reordered,
        selected_index=0,
        browser_context=view_model.browser_context,
        error=None,
    )
    assert view_model.browser_rows[1].source_row is row_c
    assert adapter.sample_context_target is None
    with pytest.raises((ValueError, LookupError, RuntimeError)):
        adapter.request_context_add_to_kit()
    assert added == []
    assert row_c not in added


def test_context_add_to_kit_never_reenters_index_based_request_add_to_kit():
    added = []
    fixture, view_model, adapter = _adapter(add_to_kit_command=added.append)
    _require_context_api(adapter)
    adapter.select_row(0)
    row_b = fixture.browser_rows[1]
    adapter.open_sample_context(1)

    calls: list[int] = []
    original = adapter.request_add_to_kit

    def _spy(index: int):
        calls.append(int(index))
        return original(index)

    adapter.request_add_to_kit = _spy  # type: ignore[method-assign]
    result = adapter.request_context_add_to_kit()

    assert result is row_b
    assert added == [row_b]
    assert calls == [], "context Add-to-Kit must not re-resolve via request_add_to_kit(index)"
    assert view_model.selected_browser_index == 0


def test_context_harmonic_matches_dispatches_one_intent_for_b_without_toggle_path():
    harmonic_intents = []
    fixture, view_model, adapter = _adapter(
        context_harmonic_command=harmonic_intents.append,
    )
    _require_context_api(adapter)
    adapter.select_row(0)
    row_b = fixture.browser_rows[1]
    open_before = bool(adapter.harmonic_match_open)

    toggle_calls = []
    original_toggle = adapter.toggle_harmonic_match

    def _spy_toggle():
        toggle_calls.append(True)
        return original_toggle()

    adapter.toggle_harmonic_match = _spy_toggle  # type: ignore[method-assign]

    adapter.open_sample_context(1)
    result = adapter.request_context_harmonic_matches()

    assert result is row_b
    assert harmonic_intents == [row_b]
    assert view_model.selected_browser_index == 0
    assert adapter.harmonic_match_open is open_before
    assert toggle_calls == []


# --- Lifecycle ----------------------------------------------------------------


def test_close_and_escape_clear_sample_context_target():
    fixture, _view_model, adapter = _adapter()
    _require_context_api(adapter)
    adapter.open_sample_context(1)
    assert adapter.sample_context_target is fixture.browser_rows[1]

    adapter.close_sample_context()
    assert adapter.sample_context_target is None


def test_open_b_then_open_c_replaces_target_with_c_only():
    fixture, _view_model, adapter = _adapter()
    _require_context_api(adapter)
    row_b = fixture.browser_rows[1]
    row_c = fixture.browser_rows[2]

    adapter.open_sample_context(1)
    assert adapter.sample_context_target is row_b
    adapter.close_sample_context()
    assert adapter.sample_context_target is None

    adapter.open_sample_context(2)
    assert adapter.sample_context_target is row_c
    assert adapter.sample_context_target is not row_b


def test_action_clears_sample_context_target():
    added = []
    fixture, _view_model, adapter = _adapter(add_to_kit_command=added.append)
    _require_context_api(adapter)
    adapter.open_sample_context(1)
    adapter.request_context_add_to_kit()
    assert added == [fixture.browser_rows[1]]
    assert adapter.sample_context_target is None


def test_browser_search_projection_clears_sample_context_target():
    fixture, view_model, adapter = _adapter()
    _require_context_api(adapter)
    row_b = fixture.browser_rows[1]
    needle = row_b.display_name
    # Ensure search will change the visible projection.
    assert any(row.display_name != needle for row in fixture.browser_rows)

    adapter.open_sample_context(1)
    assert adapter.sample_context_target is row_b

    view_model.set_browser_search_query(needle)
    assert adapter.sample_context_target is None


def test_rows_replacement_clears_sample_context_target():
    fixture, view_model, adapter = _adapter()
    _require_context_api(adapter)
    adapter.open_sample_context(1)
    assert adapter.sample_context_target is fixture.browser_rows[1]

    view_model.set_browser_state(
        rows=tuple(fixture.browser_rows[:3]),
        selected_index=0,
        browser_context="replaced",
        error=None,
    )
    assert adapter.sample_context_target is None


def test_scope_replacement_clears_sample_context_target():
    fixture, _view_model, adapter = _adapter()
    _require_context_api(adapter)
    adapter.open_sample_context(1)
    assert adapter.sample_context_target is fixture.browser_rows[1]

    adapter.replace_browser_scope(object())
    assert adapter.sample_context_target is None


def test_clean_start_clears_sample_context_target():
    fixture, _view_model, adapter = _adapter()
    _require_context_api(adapter)
    adapter.open_sample_context(1)
    assert adapter.sample_context_target is fixture.browser_rows[1]

    adapter.return_to_clean_start_action()
    assert adapter.sample_context_target is None


# --- Keyboard / bridge / presentation source contracts -----------------------


def test_keyboard_open_uses_selected_row_without_preview():
    previews = []
    selected_callbacks = []
    fixture, view_model, adapter = _adapter(
        browse_command=selected_callbacks.append,
        preview_command=previews.append,
    )
    _require_context_api(adapter)
    adapter.select_row(3)
    selected_callbacks.clear()
    row = fixture.browser_rows[3]

    # Keyboard open is modelled as open_sample_context(selected index).
    opened = adapter.open_sample_context(adapter.selected_browser_index)

    assert opened is row
    assert adapter.sample_context_target is row
    assert view_model.selected_browser_index == 3
    assert selected_callbacks == []
    assert previews == []


def test_qml_bridge_exposes_context_slots_without_domain_row_property():
    text = _WORKBENCH_QML_PY.read_text(encoding="utf-8")
    assert "def openSampleContext" in text
    assert "def closeSampleContext" in text
    assert "def contextAddToKit" in text
    assert "def contextHarmonicMatches" in text
    # No second QML authority alias for the Python target property.
    assert "context_sample" not in text
    assert "property var contextSample" not in text


def test_qml_source_has_themed_sample_context_popup_not_native_light_menu():
    assert 'objectName: "sampleContextMenu"' in QML_SOURCE
    assert "Popup" in QML_SOURCE
    menu_idx = QML_SOURCE.index('objectName: "sampleContextMenu"')
    menu_window = QML_SOURCE[menu_idx : menu_idx + 2500]
    assert "theme.selectionSurface" in menu_window
    assert "theme.textPrimary" in menu_window
    assert "theme.focusRing" in menu_window
    assert "Add to Kit" in menu_window
    assert "Harmonic Matches" in menu_window
    # Behaviour contract — do not require native MenuItem types.
    assert "Menu {" not in menu_window
    assert "NativeMenu" not in menu_window
    # No HEX literals inside the menu chrome window.
    assert _HEX_RE.search(menu_window) is None


def test_qml_source_wires_right_click_and_keyboard_context_open():
    assert "openSampleContext" in QML_SOURCE
    assert "Qt.RightButton" in QML_SOURCE or "Qt.RightButton" in _WORKBENCH_QML_PY.read_text(
        encoding="utf-8"
    )
    text = QML_SOURCE
    assert "Qt.Key_Menu" in text or "Shift+F10" in text or "Qt.Key_F10" in text
    assert "closeSampleContext" in text
    assert "CloseOnEscape" in text
    assert "CloseOnPressOutside" in text


def test_qml_source_keeps_row_add_to_kit_and_harmonic_header_button():
    """#839 must not remove chrome owned by #840 / #843."""
    assert "addToKit(index)" in QML_SOURCE
    assert 'objectName: "harmonicMatchButton"' in QML_SOURCE
    assert "reuseItems: true" in QML_SOURCE
    browser_idx = QML_SOURCE.index('objectName: "browserList"')
    browser_window = QML_SOURCE[browser_idx : browser_idx + 400]
    assert "reuseItems: true" in browser_window


def test_qml_source_preserves_845_collapse_and_846_resize_markers():
    assert "browserCollapsed" in _WORKBENCH_QML_PY.read_text(encoding="utf-8")
    assert "liveKitCollapsed" in _WORKBENCH_QML_PY.read_text(encoding="utf-8")
    assert 'objectName: "browserColumnResize_waveform"' in QML_SOURCE
    assert 'objectName: "browserColumnResize_meta"' in QML_SOURCE
    assert 'objectName: "browserColumnResize_favorite"' in QML_SOURCE
    assert 'objectName: "browserColumnResize_length"' in QML_SOURCE


def test_focus_return_contract_present_in_qml_source():
    menu_idx = QML_SOURCE.index('objectName: "sampleContextMenu"')
    menu_window = QML_SOURCE[menu_idx : menu_idx + 3000]
    assert "forceActiveFocus" in menu_window or "browser.forceActiveFocus" in QML_SOURCE
    assert "focus:" in menu_window or "activeFocus" in menu_window
