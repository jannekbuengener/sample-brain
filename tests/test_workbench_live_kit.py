"""RED contracts for #512 minimal Live Kit V1.

The production surface is intentionally absent during this test-only phase.
Each helper delays imports and missing attributes so pytest collection remains
healthy and every RED names the exact missing #512 capability.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

import pytest

from src.workbench import WorkbenchApp
from src.workbench_controller import WorkbenchRow


def _surface(missing: str):
    try:
        return importlib.import_module("src.workbench_live_kit")
    except ModuleNotFoundError as exc:
        if exc.name == "src.workbench_live_kit":
            pytest.fail(f"MISSING_PRODUCTION_SURFACE: {missing}")
        raise


def _require(surface, name: str, missing: str):
    value = getattr(surface, name, None)
    if value is None:
        pytest.fail(f"MISSING_PRODUCTION_SURFACE: {missing}")
    return value


def _require_method(target, name: str, missing: str):
    method = getattr(target, name, None)
    if method is None:
        pytest.fail(f"MISSING_PRODUCTION_SURFACE: {missing}")
    return method


def _require_app_method(app: WorkbenchApp, name: str, missing: str):
    return _require_method(app, name, missing)


def _row() -> WorkbenchRow:
    """A valid synthetic row using the current WorkbenchRow signature."""
    return WorkbenchRow(
        display_name="closed_hat_01.wav",
        relative_path="synthetic/closed_hat_01.wav",
        path="synthetic/closed_hat_01.wav",
        bpm=128.0,
        key="Am",
        key_conf=0.91,
        loudness=-13.5,
        brightness=3200.0,
        sample_class="one_shot",
        pred_type="Closed Hat",
        status="ok",
        details={"duration_sec": "0.25", "source": "synthetic"},
    )


def _state(missing: str):
    surface = _surface(missing)
    return surface, _require(surface, "LiveKitState", missing)()


def _groups(state, missing: str):
    return _require_method(state, "groups", missing)()


def _slots(state, group: str, missing: str):
    return _require_method(state, "slots_for", missing)(group)


def _assignment(state, group: str, slot: str, missing: str):
    return _require_method(state, "assignment_for", missing)(group, slot)


def _assign(state, group: str, slot: str, row: WorkbenchRow, missing: str):
    return _require_method(state, "assign", missing)(group, slot, row)


def test_live_kit_state_has_only_the_canonical_musical_structure():
    _surface_module, state = _state("canonical LiveKitState")

    missing = "canonical LiveKitState"
    assert _groups(state, missing) == ("Kick + Bass", "Drums", "Melodic", "Atmos / FX")
    assert _slots(state, "Drums", missing) == (
        "Main Drum",
        "Closed Hat",
        "Open Hat",
        "Percussion",
        "Additional",
    )
    for slot in _slots(state, "Drums", missing):
        assert _assignment(state, "Drums", slot, missing) is None
    for group in ("Kick + Bass", "Melodic", "Atmos / FX"):
        assert _slots(state, group, missing) == ()


def test_closed_hat_assignment_preserves_the_workbench_row_identity():
    _surface_module, state = _state("live-kit slot assignment")
    row = _row()

    _assign(state, "Drums", "Closed Hat", row, "live-kit slot assignment")

    assigned = _assignment(state, "Drums", "Closed Hat", "live-kit slot assignment")
    assert assigned is row
    assert assigned.path == row.path
    assert assigned.display_name == row.display_name
    assert assigned.details == row.details


def test_missing_selection_rejects_without_mutating_the_kit():
    _surface_module, state = _state("selected-row live-kit assignment route")
    app = WorkbenchApp.__new__(WorkbenchApp)
    app._live_kit_state = state
    app._selected_row = lambda: None
    statuses: list[str] = []
    app._set_status = lambda message, **_kwargs: statuses.append(message)
    route = _require_app_method(
        app, "_assign_selected_row_to_live_kit", "selected-row live-kit assignment route"
    )

    outcome = route("Drums", "Closed Hat")

    assert not outcome
    assert statuses and statuses[-1].strip()
    assert _assignment(state, "Drums", "Closed Hat", "selected-row live-kit assignment route") is None


def test_successful_assignment_never_opens_a_playlist_route():
    _surface_module, state = _state("isolated live-kit action route")
    row = _row()
    app = WorkbenchApp.__new__(WorkbenchApp)
    app._live_kit_state = state
    app._selected_row = lambda: row
    app._set_status = lambda *_args, **_kwargs: None
    playlist_calls: list[WorkbenchRow] = []
    app._open_add_to_playlist_dialog = playlist_calls.append
    route = _require_app_method(
        app, "_assign_selected_row_to_live_kit", "isolated live-kit action route"
    )

    assert route("Drums", "Closed Hat")
    assert playlist_calls == []
    assert _assignment(state, "Drums", "Closed Hat", "isolated live-kit action route") is row


def test_successful_assignment_never_dispatches_preview():
    _surface_module, state = _state("isolated live-kit action route")
    row = _row()
    app = WorkbenchApp.__new__(WorkbenchApp)
    app._live_kit_state = state
    app._selected_row = lambda: row
    app._set_status = lambda *_args, **_kwargs: None
    preview_calls: list[object] = []
    app._play_preview = lambda *args, **kwargs: preview_calls.append((args, kwargs))
    route = _require_app_method(
        app, "_assign_selected_row_to_live_kit", "isolated live-kit action route"
    )

    assert route("Drums", "Closed Hat")
    assert preview_calls == []
    assert _assignment(state, "Drums", "Closed Hat", "isolated live-kit action route") is row


@dataclass
class _TransportSpy:
    calls: list[str]

    def __getattr__(self, name: str):
        def record(*_args, **_kwargs):
            self.calls.append(name)

        return record


def test_successful_assignment_never_mutates_transport():
    _surface_module, state = _state("transport-independent live-kit assignment")
    row = _row()
    app = WorkbenchApp.__new__(WorkbenchApp)
    app._live_kit_state = state
    app._selected_row = lambda: row
    app._set_status = lambda *_args, **_kwargs: None
    transport = _TransportSpy(calls=[])
    app._transport_adapter = transport
    route = _require_app_method(
        app,
        "_assign_selected_row_to_live_kit",
        "transport-independent live-kit assignment",
    )

    assert route("Drums", "Closed Hat")
    assert transport.calls == []
    assert _assignment(state, "Drums", "Closed Hat", "transport-independent live-kit assignment") is row


def test_disclosure_state_is_separate_from_musical_state():
    surface, state = _state("live-kit presentation disclosure state")
    missing = "live-kit presentation disclosure state"
    _assign(state, "Drums", "Closed Hat", _row(), missing)
    before = (
        _groups(state, missing),
        _slots(state, "Drums", missing),
        _assignment(state, "Drums", "Closed Hat", missing),
    )
    presentation_type = _require(
        surface, "LiveKitPresentationState", "live-kit presentation disclosure state"
    )
    presentation = presentation_type(state)

    assert _require_method(presentation, "toggle_group", missing)("Drums") is True
    assert _require_method(presentation, "is_collapsed", missing)("Drums") is True
    assert _require_method(presentation, "toggle_group", missing)("Drums") is False
    assert _require_method(presentation, "toggle_group", missing)("Drums") is True

    assert (
        _groups(state, missing),
        _slots(state, "Drums", missing),
        _assignment(state, "Drums", "Closed Hat", missing),
    ) == before


def test_both_right_pane_views_are_explicitly_reachable():
    surface = _surface("right-pane Live Kit / Sample Details routing")
    right_pane_type = _require(
        surface, "RightPanePresentation", "right-pane Live Kit / Sample Details routing"
    )
    right_pane = right_pane_type()

    missing = "right-pane Live Kit / Sample Details routing"
    assert _require_method(right_pane, "show_live_kit", missing)() == "Live Kit"
    assert _require_method(right_pane, "active_view", missing)() == "Live Kit"
    assert _require_method(right_pane, "show_sample_details", missing)() == "Sample Details"
    assert _require_method(right_pane, "active_view", missing)() == "Sample Details"


def test_sample_details_surface_survives_a_live_kit_round_trip():
    surface = _surface("right-pane view preservation")
    right_pane_type = _require(
        surface, "RightPanePresentation", "right-pane view preservation"
    )
    details_surface = object()
    waveform_surface = object()
    edit_controls = object()
    right_pane = right_pane_type(
        detail_text=details_surface,
        detail_waveform=waveform_surface,
        edit_controls=edit_controls,
    )

    missing = "right-pane view preservation"
    _require_method(right_pane, "show_sample_details", missing)()
    _require_method(right_pane, "show_live_kit", missing)()
    _require_method(right_pane, "show_sample_details", missing)()

    assert getattr(right_pane, "detail_text", None) is details_surface
    assert getattr(right_pane, "detail_waveform", None) is waveform_surface
    assert getattr(right_pane, "edit_controls", None) is edit_controls


def test_live_kit_presentation_exposes_canonical_visible_structure():
    surface, state = _state("live-kit right-pane presentation")
    presentation_type = _require(
        surface, "LiveKitPresentationState", "live-kit right-pane presentation"
    )
    presentation = presentation_type(state)

    missing = "live-kit right-pane presentation"
    empty = _require_method(presentation, "visible_structure", missing)()
    assert tuple(group.name for group in empty) == _groups(state, missing)
    assert tuple(slot.name for slot in empty[1].slots) == _slots(state, "Drums", missing)
    assert empty[1].slots[1].assignment is None

    row = _row()
    _assign(state, "Drums", "Closed Hat", row, missing)
    assigned = _require_method(presentation, "visible_structure", missing)()
    assert assigned[1].slots[1].assignment is row
