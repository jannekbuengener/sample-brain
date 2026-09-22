from __future__ import annotations

import importlib.util
from dataclasses import replace

import pytest

from src.workbench_harmony import (
    HarmonicMatchLibraryController,
    HarmonyRelation,
    HarmonySuggestion,
)
from src.workbench_controller import MATCHING_NO_BPM_MESSAGE, WorkbenchRow
from src.workbench_qml_spike import (
    Screen1QmlInteractionAdapter,
    Screen1QmlViewModel,
    build_qml_view_model_from_fixture,
)
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1


def _adapter(
    *,
    browse_command=None,
    preview_command=None,
    preview_stop=None,
    add_to_kit_command=None,
    harmony_controller=None,
):
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
        on_browser_selected=browse_command,
    )
    return fixture, view_model, Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=harmony_controller,
        on_preview_requested=preview_command,
        on_preview_stopped=preview_stop,
        on_add_to_kit_requested=add_to_kit_command,
    )


def _stub_harmony_finder(anchor, candidates):
    return (
        [
            HarmonySuggestion(
                row=candidate,
                relation=HarmonyRelation.DIRECT,
                harmony_score=1.0,
                bpm_score=1.0,
                total_score=round(1.0 - index * 0.01, 3),
                explanation="stub",
            )
            for index, candidate in enumerate(candidates)
        ],
        None,
    )


def _set_mode_keys(fixture, view_model, *indices):
    targets = {id(fixture.browser_rows[index]) for index in indices}
    rows = []
    for qml_row in view_model.browser_rows:
        source = qml_row.source_row
        if id(source) in targets and source.key:
            qml_row = replace(qml_row, source_row=replace(source, key=f"{source.key}min"))
        rows.append(qml_row)
    return tuple(rows)


def test_row_click_selects_exact_row_updates_view_state_and_dispatches_once():
    dispatched = []
    previews = []
    fixture, view_model, adapter = _adapter(
        browse_command=dispatched.append,
        preview_command=previews.append,
    )

    selected = adapter.select_row(4)

    assert selected is fixture.browser_rows[4]
    assert view_model.selected_browser_index == 4
    assert adapter.selected_browser_index == 4
    assert dispatched == [fixture.browser_rows[4]]
    assert previews == []


def test_waveform_intent_selects_and_dispatches_exactly_one_preview():
    dispatched = []
    previews = []
    fixture, view_model, adapter = _adapter(
        browse_command=dispatched.append,
        preview_command=previews.append,
    )

    selected = adapter.preview_row(4)

    assert selected is fixture.browser_rows[4]
    assert view_model.selected_browser_index == 4
    assert dispatched == [fixture.browser_rows[4]]
    assert previews == [fixture.browser_rows[4]]


def test_browser_arrow_navigation_reuses_single_browse_command_and_clamps_edges():
    dispatched = []
    previews = []
    fixture, view_model, adapter = _adapter(
        browse_command=dispatched.append,
        preview_command=previews.append,
    )

    assert adapter.navigate_browser("next", browser_has_focus=True) is fixture.browser_rows[3]
    assert view_model.selected_browser_index == 3
    assert dispatched == [fixture.browser_rows[3]]
    assert previews == [fixture.browser_rows[3]]

    adapter.select_row(len(fixture.browser_rows) - 1)
    dispatched.clear()
    previews.clear()
    assert adapter.navigate_browser("next", browser_has_focus=True) is fixture.browser_rows[-1]
    assert dispatched == []
    assert previews == []

    adapter.select_row(0)
    dispatched.clear()
    previews.clear()
    assert adapter.navigate_browser("previous", browser_has_focus=True) is fixture.browser_rows[0]
    assert dispatched == []
    assert previews == []


def test_browser_arrows_do_not_capture_text_field_focus():
    dispatched = []
    fixture, view_model, adapter = _adapter(browse_command=dispatched.append)
    initial_index = view_model.selected_browser_index

    assert adapter.navigate_browser("next", browser_has_focus=False) is None
    assert view_model.selected_browser_index == initial_index
    assert dispatched == []
    assert fixture.browser_rows[initial_index] is view_model.browser_rows[initial_index].source_row


def test_escape_stops_only_an_active_preview():
    stops = []
    fixture, _view_model, adapter = _adapter(
        preview_command=lambda _row: None,
        preview_stop=lambda: stops.append("stop"),
    )

    assert adapter.stop_preview() is False
    adapter.preview_row(2)
    assert adapter.preview_active is True
    assert adapter.stop_preview() is True
    assert adapter.preview_active is False
    assert adapter.stop_preview() is False
    assert stops == ["stop"]
    assert fixture.browser_rows[2] is not None


def test_scope_invalidation_stops_active_preview_before_clearing_state():
    stops = []
    _fixture, _view_model, adapter = _adapter(
        preview_command=lambda _row: None,
        preview_stop=lambda: stops.append("stop"),
    )

    adapter.preview_row(2)
    assert adapter.preview_active is True

    adapter.replace_browser_scope(object())

    assert stops == ["stop"]
    assert adapter.preview_active is False


def test_add_to_kit_emits_intent_without_assigning_live_kit():
    added = []
    fixture, view_model, adapter = _adapter(add_to_kit_command=added.append)
    live_kit_before = view_model.live_kit_groups

    row = adapter.request_add_to_kit(4)

    assert row is fixture.browser_rows[4]
    assert added == [fixture.browser_rows[4]]
    assert view_model.live_kit_groups is live_kit_before


def test_browser_row_projects_real_metadata_and_empty_values_neutrally():
    fixture, view_model, _adapter_instance = _adapter()
    row = view_model.browser_rows[2]

    assert row.display_name == "TECH_BASS_01"
    assert row.sample_type == "Bass"
    assert row.bpm == "132"
    assert row.key == "F#"
    assert row.duration == "2.00s"
    assert row.waveform_envelope
    assert all(0.0 <= point <= 1.0 for point in row.waveform_envelope)

    missing = WorkbenchRow(
        display_name="UNKNOWN",
        relative_path="unknown.wav",
        path="unknown.wav",
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class="one_shot",
        pred_type=None,
        status="ok",
        details={},
    )
    from src.workbench_qml import _qml_row

    projected = _qml_row(missing)
    assert projected.sample_type == "—"
    assert projected.bpm == "—"
    assert projected.key == "—"
    assert projected.duration == "—"
    assert projected.waveform_envelope == ()


def test_browser_qml_uses_waveform_intent_and_has_no_row_play_button():
    from src.workbench_qml import QML_SOURCE

    assert "Canvas" in QML_SOURCE
    assert "previewRow(index)" in QML_SOURCE
    assert "addToKit(index)" in QML_SOURCE
    assert "stopPreview()" in QML_SOURCE
    assert 'text: "Play"' not in QML_SOURCE
    assert 'text: "▶"' not in QML_SOURCE


def test_harmonic_toggle_reuses_controller_and_preserves_browser_and_live_kit_state():
    controller_calls = []
    controller = HarmonicMatchLibraryController()
    original_set_anchor = controller.set_anchor

    def record_set_anchor(anchor, candidates):
        controller_calls.append((anchor, tuple(candidates)))
        original_set_anchor(anchor, candidates)

    controller.set_anchor = record_set_anchor
    _, view_model, adapter = _adapter(harmony_controller=controller)
    live_kit_before = view_model.live_kit_groups
    selected_before = view_model.selected_browser_index

    assert adapter.harmonic_match_open is False
    assert adapter.toggle_harmonic_match() is True
    assert controller.anchor is view_model.browser_rows[selected_before].source_row
    assert len(controller_calls) == 1
    assert adapter.harmonic_match_open is True
    assert view_model.selected_browser_index == selected_before
    assert view_model.live_kit_groups is live_kit_before
    assert adapter.toggle_harmonic_match() is False
    assert len(controller_calls) == 1
    assert view_model.selected_browser_index == selected_before
    assert view_model.live_kit_groups is live_kit_before


def test_harmonic_reopen_same_fingerprint_reuses_results_selection_and_scroll():
    calls = []
    controller = HarmonicMatchLibraryController()
    original = controller.set_anchor

    def record(anchor, candidates):
        calls.append((anchor, tuple(candidates)))
        original(anchor, candidates)

    controller.set_anchor = record
    _fixture, view_model, adapter = _adapter(harmony_controller=controller)

    assert adapter.toggle_harmonic_match() is True
    adapter.set_harmonic_match_scroll_y(42)
    if view_model.harmony_rows:
        adapter.select_harmonic_match(min(1, len(view_model.harmony_rows) - 1))
    selected = adapter.selected_harmonic_match_index
    assert adapter.toggle_harmonic_match() is False
    assert adapter.toggle_harmonic_match() is True
    assert len(calls) == 1
    assert adapter.selected_harmonic_match_index == selected
    assert adapter.harmonic_match_scroll_y == 42


def test_harmonic_no_browser_selection_stays_closed_without_finder_call():
    calls = []
    controller = HarmonicMatchLibraryController(finder=lambda *_args: calls.append(True))
    _fixture, view_model, adapter = _adapter(harmony_controller=controller)
    view_model.browser_rows = ()
    view_model.selected_browser_index = -1

    assert adapter.toggle_harmonic_match() is False
    assert adapter.harmonic_match_open is False
    assert calls == []
    assert view_model.harmony_rows == ()
    assert "Kein Sample" in view_model.harmony_status


def test_harmonic_open_without_reference_bpm_is_fail_closed_without_finder_call():
    calls = []

    def finder(anchor, candidates):
        calls.append(anchor)
        return _stub_harmony_finder(anchor, candidates)

    fixture, view_model, adapter = _adapter(
        harmony_controller=HarmonicMatchLibraryController(finder=finder)
    )
    selected = fixture.selected_browser_index
    view_model.browser_rows = _set_mode_keys(fixture, view_model, selected)
    anchor = view_model.browser_rows[selected].source_row
    view_model.browser_rows = tuple(
        replace(
            qml_row,
            source_row=(
                replace(anchor, bpm=None)
                if qml_row.source_row.path == anchor.path
                else qml_row.source_row
            ),
        )
        for qml_row in view_model.browser_rows
    )

    assert adapter.toggle_harmonic_match() is True
    assert view_model.harmony_status == MATCHING_NO_BPM_MESSAGE
    assert view_model.harmony_rows == ()
    assert calls == []


def test_harmonic_open_without_key_mode_is_fail_closed_without_finder_call():
    calls = []

    def finder(anchor, candidates):
        calls.append(anchor)
        return _stub_harmony_finder(anchor, candidates)

    fixture, view_model, adapter = _adapter(
        harmony_controller=HarmonicMatchLibraryController(finder=finder)
    )
    selected = fixture.selected_browser_index
    view_model.browser_rows = tuple(
        replace(qml_row, source_row=replace(qml_row.source_row, key="C"))
        for qml_row in view_model.browser_rows
    )

    assert adapter.toggle_harmonic_match() is True
    assert "Referenz-Key" in view_model.harmony_status
    assert view_model.harmony_rows == ()
    assert calls == []


def test_harmonic_match_row_actions_are_local_preview_and_existing_add_intent_only():
    previews = []
    added = []
    fixture, view_model, adapter = _adapter(
        harmony_controller=HarmonicMatchLibraryController(finder=_stub_harmony_finder),
        preview_command=previews.append,
        add_to_kit_command=added.append,
    )
    view_model.browser_rows = _set_mode_keys(
        fixture, view_model, fixture.selected_browser_index
    )
    assert adapter.toggle_harmonic_match() is True
    assert view_model.harmony_rows
    live_kit_before = view_model.live_kit_groups
    row = adapter.select_harmonic_match(0)
    assert previews == []
    assert adapter.preview_harmonic_match(0) is row
    assert previews == [row]
    assert adapter.request_add_harmonic_match_to_kit(0) is row
    assert added == [row]
    assert view_model.live_kit_groups is live_kit_before


def test_harmonic_scroll_is_ignored_while_panel_closed():
    fixture, view_model, adapter = _adapter()

    adapter.set_harmonic_match_scroll_y(42)
    assert adapter.harmonic_match_scroll_y == 0.0

    assert adapter.toggle_harmonic_match() is True
    adapter.set_harmonic_match_scroll_y(42)
    assert adapter.harmonic_match_scroll_y == 42.0


def test_harmonic_toggle_cycles_between_3_and_4_panels_without_state_drift():
    fixture, view_model, adapter = _adapter(
        harmony_controller=HarmonicMatchLibraryController(finder=_stub_harmony_finder),
    )
    view_model.browser_rows = _set_mode_keys(
        fixture, view_model, fixture.selected_browser_index
    )
    live_kit_before = view_model.live_kit_groups

    for cycle in range(4):
        assert view_model.panel_count == 3
        assert adapter.toggle_harmonic_match() is True
        assert view_model.panel_count == 4
        assert adapter.harmonic_match_open is True
        assert adapter.toggle_harmonic_match() is False
        assert view_model.panel_count == 3
        assert adapter.harmonic_match_open is False
    assert view_model.live_kit_groups is live_kit_before


def test_harmonic_toggle_different_anchor_recomputes_exactly_once_per_open():
    calls = []

    def finder(anchor, candidates):
        calls.append(anchor)
        return _stub_harmony_finder(anchor, candidates)

    fixture, view_model, adapter = _adapter(
        harmony_controller=HarmonicMatchLibraryController(finder=finder),
    )
    view_model.browser_rows = _set_mode_keys(
        fixture, view_model, fixture.selected_browser_index, 0
    )

    assert adapter.toggle_harmonic_match() is True
    assert len(calls) == 1
    adapter.set_harmonic_match_scroll_y(41)
    adapter.select_harmonic_match(2)

    assert adapter.toggle_harmonic_match() is False
    view_model.select_browser_index(0)
    assert adapter.toggle_harmonic_match() is True
    assert len(calls) == 2
    assert adapter.selected_harmonic_match_index == 0
    assert adapter.harmonic_match_scroll_y == 0.0
    assert view_model.harmony_rows


def test_harmonic_same_fingerprint_survives_browser_reorder_without_refetch():
    calls = []

    def finder(anchor, candidates):
        calls.append(anchor)
        return _stub_harmony_finder(anchor, candidates)

    fixture, view_model, adapter = _adapter(
        harmony_controller=HarmonicMatchLibraryController(finder=finder),
    )
    view_model.browser_rows = _set_mode_keys(
        fixture, view_model, fixture.selected_browser_index
    )

    assert adapter.toggle_harmonic_match() is True
    assert len(calls) == 1
    adapter.set_harmonic_match_scroll_y(31)
    adapter.select_harmonic_match(1)

    assert adapter.toggle_harmonic_match() is False
    rows = list(view_model.browser_rows)
    rows[0], rows[3] = rows[3], rows[0]
    view_model.browser_rows = tuple(rows)

    assert adapter.toggle_harmonic_match() is True
    assert len(calls) == 1
    assert adapter.selected_harmonic_match_index == 1
    assert adapter.harmonic_match_scroll_y == 31.0


def test_harmonic_fingerprint_ignores_candidate_order_but_tracks_anchor_metadata():
    fixture, view_model, adapter = _adapter()
    anchor = view_model.browser_rows[2].source_row
    forward = adapter._current_harmonic_match_fingerprint(anchor)

    view_model.browser_rows = tuple(reversed(view_model.browser_rows))
    assert adapter._current_harmonic_match_fingerprint(anchor) == forward

    assert (
        adapter._current_harmonic_match_fingerprint(replace(anchor, key="Bmin"))
        != forward
    )
    assert (
        adapter._current_harmonic_match_fingerprint(replace(anchor, bpm=110.0))
        != forward
    )
    assert (
        adapter._current_harmonic_match_fingerprint(
            replace(anchor, display_name="OTHER")
        )
        != forward
    )


def test_harmonic_row_fingerprint_tracks_path_key_bpm_and_name():
    fixture, view_model, adapter = _adapter()
    row = fixture.browser_rows[2]

    fingerprint = adapter._harmonic_match_row_fingerprint(row)

    assert fingerprint == (
        row.path,
        row.key,
        ("finite", 132.0),
        row.display_name,
    )
    assert fingerprint != adapter._harmonic_match_row_fingerprint(
        replace(row, key="Bmin")
    )
    assert fingerprint != adapter._harmonic_match_row_fingerprint(
        replace(row, bpm=110.0)
    )
    assert fingerprint != adapter._harmonic_match_row_fingerprint(
        replace(row, display_name="OTHER")
    )


@pytest.mark.parametrize(
    ("bpm", "expected"),
    [
        (None, ("none", "")),
        (132.0, ("finite", 132.0)),
        (float("nan"), ("nan", "")),
        (float("inf"), ("positive-infinity", "")),
        (float("-inf"), ("negative-infinity", "")),
        ("garbage", ("invalid", "'garbage'")),
    ],
)
def test_harmonic_bpm_fingerprint_normalizes_edge_values(bpm, expected):
    fixture, _view_model, adapter = _adapter()

    assert adapter._harmonic_match_bpm_fingerprint(bpm) == expected


def test_harmonic_single_control_button_without_secondary_close_and_on_off_controls():
    from src.workbench_qml import QML_SOURCE

    assert QML_SOURCE.count('objectName: "harmonicMatchButton"') == 1
    assert QML_SOURCE.count("toggleHarmonicMatch()") == 1
    assert "onVisibleChanged" in QML_SOURCE
    assert "Qt.callLater" in QML_SOURCE
    assert "harmonyScrollY" in QML_SOURCE
    for forbidden in ('text: "✕"', 'text: "X"', 'text: "OFF"'):
        assert forbidden not in QML_SOURCE


def test_harmonic_panel_layout_is_derived_from_a_single_visible_state():
    from src.workbench_qml import QML_SOURCE

    assert QML_SOURCE.count("visible: window.interaction.harmonicMatchOpen") == 1
    assert "Layout.preferredWidth: visible ? 360 : 0" in QML_SOURCE
    assert "screen1-default-3panel" not in QML_SOURCE
    assert "screen1-harmonic-4panel" not in QML_SOURCE


def test_harmonic_qml_forwards_only_controller_data_without_music_theory():
    from src.workbench_qml import QML_SOURCE

    for forbidden in (
        "Halbton",
        "semitones",
        "determine_relation",
        "Quinte",
        "Quarte",
        "pitchShift",
    ):
        assert forbidden not in QML_SOURCE


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_harmonic_toggle_roundtrip_restores_focus_and_scroll_without_refetch():
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame

    finder_calls = []

    def finder(anchor, candidates):
        finder_calls.append(anchor)
        return _stub_harmony_finder(anchor, candidates)

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
    )
    view_model.browser_rows = _set_mode_keys(
        fixture, view_model, fixture.selected_browser_index
    )
    anchor = view_model.browser_rows[fixture.selected_browser_index].source_row
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(finder=finder),
    )
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        toggle = window.findChild(QQuickItem, "harmonicMatchButton")
        harmony = window.findChild(QQuickItem, "harmonicMatchList")
        assert browser is not None and toggle is not None and harmony is not None

        def click_toggle():
            point = toggle.mapToScene(QPointF(8, 8)).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
            app.processEvents()

        click_toggle()
        assert adapter.harmonic_match_open is True
        assert adapter.harmony_controller.anchor is anchor
        assert len(finder_calls) == 1
        assert len(view_model.harmony_rows) == 11
        _settle_qml_frame(app)
        assert harmony.property("activeFocus") is True

        QTest.keyClick(window, Qt.Key_Down)
        app.processEvents()
        assert adapter.selected_harmonic_match_index == 1
        QTest.keyClick(window, Qt.Key_Up)
        app.processEvents()
        assert adapter.selected_harmonic_match_index == 0

        harmony.setProperty("contentY", 30.0)
        app.processEvents()
        assert adapter.harmonic_match_scroll_y > 1.0

        click_toggle()
        assert adapter.harmonic_match_open is False
        _settle_qml_frame(app)
        assert browser.property("activeFocus") is True

        before = view_model.selected_browser_index
        QTest.keyClick(window, Qt.Key_Up)
        app.processEvents()
        assert view_model.selected_browser_index == max(before - 1, 0)

        click_toggle()
        assert adapter.harmonic_match_open is True
        assert len(finder_calls) == 1
        _settle_qml_frame(app)
        assert harmony.property("activeFocus") is True
        restored = float(harmony.property("contentY"))
        assert abs(restored - adapter.harmonic_match_scroll_y) <= 2.0
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_real_interaction_smoke_click_arrows_focus_and_harmonic_toggle():
    from PySide6.QtCore import QObject, QPointF, Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame

    dispatched = []
    previews = []
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
        on_browser_selected=dispatched.append,
    )
    interaction_adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
        on_preview_requested=previews.append,
    )
    app, engine, window = _qml_engine(
        view_model,
        interaction_adapter=interaction_adapter,
    )
    window.show()
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        search = window.findChild(QObject, "browserSearch")
        toggle = window.findChild(QQuickItem, "harmonicMatchButton")
        assert browser is not None and search is not None and toggle is not None

        row_four = browser.mapToScene(QPointF(300, 4 * 66 + 33)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, row_four)
        app.processEvents()
        assert view_model.selected_browser_index == 4
        assert dispatched == [fixture.browser_rows[4]]
        assert previews == []

        waveform_four = browser.mapToScene(QPointF(40, 4 * 66 + 33)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, waveform_four)
        app.processEvents()
        assert view_model.selected_browser_index == 4
        assert previews == [fixture.browser_rows[4]]

        search.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Down)
        app.processEvents()
        assert view_model.selected_browser_index == 4

        browser.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Up)
        app.processEvents()
        assert view_model.selected_browser_index == 3
        assert dispatched == [fixture.browser_rows[4], fixture.browser_rows[3]]
        assert previews == [fixture.browser_rows[4], fixture.browser_rows[3]]

        QTest.keyClick(window, Qt.Key_Escape)
        app.processEvents()
        assert window.property("interaction").property("previewActive") is False

        add_intents = []
        engine._screen1_interaction_bridge.addToKitIntent.connect(add_intents.append)
        add_point = browser.mapToScene(
            QPointF(float(browser.property("width")) - 48, 4 * 66 + 33)
        ).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, add_point)
        app.processEvents()
        assert add_intents == [fixture.browser_rows[4].relative_path]
        assert view_model.selected_browser_index == 3

        toggle_point = toggle.mapToScene(QPointF(8, 8)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, toggle_point)
        app.processEvents()
        assert window.property("interaction").property("harmonicMatchOpen") is True
        assert engine._screen1_interaction_adapter.harmony_controller.anchor is fixture.browser_rows[3]
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()


def _click_item(app, window, item):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    point = item.mapToScene(QPointF(8, 8)).toPoint()
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
    app.processEvents()


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_harmonic_button_background_uses_accent_when_open_and_panel_alt_when_closed():
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
    )
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(finder=_stub_harmony_finder),
    )
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        toggle = window.findChild(QQuickItem, "harmonicMatchButton")
        assert toggle is not None
        background = toggle.property("background")
        assert background is not None
        closed_color = background.property("color").name()
        assert closed_color == "#15181c"

        _click_item(app, window, toggle)
        _settle_qml_frame(app)
        assert window.property("interaction").property("harmonicMatchOpen") is True
        assert background.property("color").name() == "#b1122b"

        _click_item(app, window, toggle)
        _settle_qml_frame(app)
        assert window.property("interaction").property("harmonicMatchOpen") is False
        assert background.property("color").name() == "#15181c"
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()


def _seed_v1_library_root(tmp_path, db):
    """Create real files and seed matching ``workbench_v1`` cache rows."""
    from src.workbench_controller import WorkbenchRow
    from src.workbench_library import upsert_folder, upsert_sample
    from tests.audio_fixtures import write_kick_transient_wav, write_major_chord_wav

    root = tmp_path / "sources"
    (root / "Drums").mkdir(parents=True)
    folder_id = upsert_folder(root, db_path=db)
    written = [
        write_major_chord_wav(root / "chord_root.wav"),
        write_kick_transient_wav(root / "kick_b.wav", bpm=120.0, duration_sec=2.0),
        write_major_chord_wav(root / "Drums" / "chord.wav"),
    ]
    for audio in written:
        st = audio.stat()
        row = WorkbenchRow(
            display_name=audio.name,
            relative_path=str(audio.relative_to(root)).replace("\\", "/"),
            path=str(audio),
            bpm=None,
            key="C",
            key_conf=0.8,
            loudness=-12.0,
            brightness=1500.0,
            sample_class="loop",
            pred_type="Keys",
            status="ok",
            details={"path": str(audio)},
        )
        upsert_sample(
            folder_id,
            row,
            size_bytes=st.st_size,
            mtime_ns=st.st_mtime_ns,
            db_path=db,
            analyzer_version="workbench_v1",
        )
    return root, folder_id


def _wait_for_analysis(app, coordinator, folder_id, view_model, timeout_sec=90):
    import time

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        app.processEvents()
        if (
            coordinator._core.current_token(folder_id) is None
            and view_model.browser_rows
        ):
            return True
        time.sleep(0.02)
    return False


def _stop_engine(app, engine, window, coordinator=None):
    window.close()
    app.processEvents()
    timer = getattr(engine, "_screen1_waveform_timer", None)
    if timer is not None:
        timer.stop()
    loader = getattr(engine, "_screen1_waveform_loader", None)
    if loader is not None:
        loader.close()
    if coordinator is not None:
        coordinator.close()


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_stale_v1_root_selection_starts_one_refresh_and_reloads_v2(tmp_path):
    from src.workbench_library import workbench_library_db_path
    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import Screen1QmlRuntimeComposition, Screen1QmlViewModel
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_qml_spike import _qml_engine

    db = workbench_library_db_path()
    _root, folder_id = _seed_v1_library_root(tmp_path, db)
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    coordinator = engine._screen1_analysis_coordinator
    bridge = engine._screen1_library_bridge
    library_model = engine._screen1_library_model
    root_id = f"root:{folder_id}"

    try:
        library_model.state.fetch_children("container:sample-sources")
        bridge.selectLibraryNode(root_id)
        assert composition.selected_node_id == root_id
        token1 = coordinator._core.current_token(folder_id)
        assert token1 is not None

        bridge.selectLibraryNode(root_id)
        assert composition.selected_node_id == root_id
        assert coordinator._core.current_token(folder_id) == token1

        assert _wait_for_analysis(app, coordinator, folder_id, view_model)
        app.processEvents()

        assert coordinator._core.current_token(folder_id) is None
        assert len(view_model.browser_rows) == 3
        assert all(row.source_row.key for row in view_model.browser_rows)
        assert "Cmaj" in {row.source_row.key for row in view_model.browser_rows}

        bridge.selectLibraryNode(root_id)
        assert composition.selected_node_id == root_id
        assert coordinator._core.current_token(folder_id) is None
    finally:
        _stop_engine(app, engine, window, coordinator)


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_refresh_finishes_back_on_active_subfolder_scope(tmp_path):
    from src.workbench_library import workbench_library_db_path
    from src.workbench_library_navigation import (
        LibraryNodeKind,
        LibraryScopeKind,
        WorkbenchLibraryNavigation,
    )
    from src.workbench_qml import Screen1QmlRuntimeComposition, Screen1QmlViewModel
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_qml_spike import _qml_engine

    db = workbench_library_db_path()
    _root, folder_id = _seed_v1_library_root(tmp_path, db)
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    coordinator = engine._screen1_analysis_coordinator
    bridge = engine._screen1_library_bridge
    library_model = engine._screen1_library_model

    root_node = next(
        node
        for node in navigation.children("container:sample-sources")
        if node.kind is LibraryNodeKind.REGISTERED_ROOT
    )
    subfolder_node = next(
        node
        for node in navigation.children(root_node.node_id)
        if node.kind is LibraryNodeKind.SUBFOLDER
    )
    subfolder_id = subfolder_node.node_id

    try:
        library_model.state.fetch_children("container:sample-sources")
        library_model.state.fetch_children(root_node.node_id)
        bridge.selectLibraryNode(subfolder_id)
        assert composition.selected_node_id == subfolder_id
        token1 = coordinator._core.current_token(folder_id)
        assert token1 is not None

        assert _wait_for_analysis(app, coordinator, folder_id, view_model)
        app.processEvents()

        assert coordinator._core.current_token(folder_id) is None
        assert composition.selected_node_id == subfolder_id
        scope = composition.browser_state.scope
        assert scope is not None
        assert scope.kind is LibraryScopeKind.SUBFOLDER
        assert scope.relative_path == "drums"
        rels = [
            row.source_row.relative_path.replace("\\", "/")
            for row in view_model.browser_rows
        ]
        assert len(rels) == 1
        assert rels[0] == "sources/Drums/chord.wav"
        assert "Cmaj" in {row.source_row.key for row in view_model.browser_rows}
    finally:
        _stop_engine(app, engine, window, coordinator)


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_fresh_v2_root_selection_starts_no_analysis_job(tmp_path):
    from src.workbench_controller import analyze_folder_for_workbench
    from src.workbench_library import upsert_folder, workbench_library_db_path
    from src.workbench_library_navigation import (
        LibraryNodeKind,
        WorkbenchLibraryNavigation,
    )
    from src.workbench_qml import Screen1QmlRuntimeComposition, Screen1QmlViewModel
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_qml_spike import _qml_engine
    from tests.audio_fixtures import write_major_chord_wav

    db = workbench_library_db_path()
    root = tmp_path / "sources"
    root.mkdir()
    write_major_chord_wav(root / "chord.wav")
    analyze_folder_for_workbench(root, library_db_path=db)
    folder_id = upsert_folder(root, db_path=db)
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    coordinator = engine._screen1_analysis_coordinator
    bridge = engine._screen1_library_bridge
    root_node = next(
        node
        for node in navigation.children("container:sample-sources")
        if node.kind is LibraryNodeKind.REGISTERED_ROOT
    )
    try:
        engine._screen1_library_model.state.fetch_children(
            "container:sample-sources"
        )
        bridge.selectLibraryNode(root_node.node_id)
        assert composition.selected_node_id == root_node.node_id
        assert coordinator._core.current_token(folder_id) is None
        assert len(view_model.browser_rows) == 1
        assert view_model.browser_rows[0].source_row.key == "Cmaj"
    finally:
        _stop_engine(app, engine, window, coordinator)


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_scope_switch_closes_harmonic_panel_and_reopens_with_new_scope(tmp_path):
    from src.workbench_controller import WorkbenchRow
    from src.workbench_library import (
        upsert_folder,
        upsert_sample,
        workbench_library_db_path,
    )
    from src.workbench_library_navigation import (
        LibraryNodeKind,
        WorkbenchLibraryNavigation,
    )
    from src.workbench_qml import Screen1QmlRuntimeComposition, Screen1QmlViewModel
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame
    from tests.audio_fixtures import write_major_chord_wav

    def seed_root(folder_name: str, samples: list[str]) -> tuple[Path, int]:
        root = tmp_path / folder_name
        root.mkdir(parents=True)
        folder_id = upsert_folder(root, db_path=db)
        for name in samples:
            audio = write_major_chord_wav(root / name)
            st = audio.stat()
            upsert_sample(
                folder_id,
                WorkbenchRow(
                    display_name=audio.name,
                    relative_path=str(audio.relative_to(root)).replace("\\", "/"),
                    path=str(audio),
                    bpm=132.0,
                    key="Cmaj",
                    key_conf=0.9,
                    loudness=-12.0,
                    brightness=1500.0,
                    sample_class="loop",
                    pred_type="Keys",
                    status="ok",
                    details={"path": str(audio)},
                ),
                size_bytes=st.st_size,
                mtime_ns=st.st_mtime_ns,
                db_path=db,
                analyzer_version="workbench_v2",
            )
        return root, folder_id

    db = workbench_library_db_path()
    _root_a, folder_id_a = seed_root("sources", ["lead_a.wav", "bass_a.wav"])
    _root_b, folder_id_b = seed_root("bmore", ["pad_b.wav", "bell_b.wav"])

    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    adapter = engine._screen1_interaction_adapter
    coordinator = engine._screen1_analysis_coordinator
    bridge = engine._screen1_library_bridge
    library_model = engine._screen1_library_model
    try:
        library_model.state.fetch_children("container:sample-sources")
        roots = [
            node
            for node in navigation.children("container:sample-sources")
            if node.kind is LibraryNodeKind.REGISTERED_ROOT
        ]
        assert len(roots) == 2
        root_x, root_y = roots

        bridge.selectLibraryNode(root_x.node_id)
        assert composition.selected_node_id == root_x.node_id
        assert view_model.browser_rows
        assert coordinator._core.current_token(folder_id_a) is None
        a_paths = {str(row.source_row.path) for row in view_model.browser_rows}

        assert adapter.toggle_harmonic_match() is True
        assert adapter.harmonic_match_open is True
        assert view_model.state_id == "screen1-harmonic-4panel"

        bridge.selectLibraryNode(root_y.node_id)
        _settle_qml_frame(app)
        assert composition.selected_node_id == root_y.node_id
        assert coordinator._core.current_token(folder_id_b) is None
        assert adapter.harmonic_match_open is False
        assert view_model.state_id == "screen1-default-3panel"
        assert view_model.harmony_rows == ()
        assert adapter.harmony_controller.anchor is None
        assert window.property("interaction").property("harmonicMatchOpen") is False
        b_paths = {str(row.source_row.path) for row in view_model.browser_rows}
        assert b_paths and a_paths != b_paths

        assert adapter.toggle_harmonic_match() is True
        assert view_model.state_id == "screen1-harmonic-4panel"
        assert adapter.harmony_controller.anchor is not None
        assert str(adapter.harmony_controller.anchor.path) in b_paths
        assert view_model.harmony_rows
        assert {str(row.source_row.path) for row in view_model.harmony_rows} <= b_paths
    finally:
        _stop_engine(app, engine, window, coordinator)
