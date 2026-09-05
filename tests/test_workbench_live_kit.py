"""RED contracts for #512 minimal Live Kit V1.

The production surface is intentionally absent during this test-only phase.
Each helper delays imports and missing attributes so pytest collection remains
healthy and every RED names the exact missing #512 capability.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

from src.workbench import WorkbenchApp
from src import workbench
from src.workbench_live_kit import LiveKitState, LiveKitPresentationState, RightPanePresentation
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


def test_right_pane_presentation_defaults_to_live_kit():
    surface = _surface("Live Kit default right-pane presentation")
    right_pane_type = _require(
        surface, "RightPanePresentation", "Live Kit default right-pane presentation"
    )

    assert right_pane_type().active_view() == "Live Kit"


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


class _ChooserWidget:
    """Small Tk double: exercise production callbacks without opening a window."""

    def __init__(self, parent=None, **options):
        self.parent = parent
        self.options = options
        self.bindings = {}
        self.protocols = {}
        self.children = []
        self.grabbed = False
        self.destroyed = False
        self.focused = False
        if parent is not None:
            parent.children.append(self)

    def pack(self, **_options):
        pass

    def title(self, _text):
        pass

    def configure(self, **options):
        self.options.update(options)

    def transient(self, _parent):
        pass

    def resizable(self, *_args):
        pass

    def grab_set(self):
        self.grabbed = True

    def grab_release(self):
        self.grabbed = False

    def destroy(self):
        self.destroyed = True

    def winfo_exists(self):
        return not self.destroyed

    def focus_set(self):
        self.focused = True

    def bind(self, event, callback):
        self.bindings[event] = callback

    def protocol(self, event, callback):
        self.protocols[event] = callback

    def invoke(self):
        return self.options["command"]()


def _browser_kit_app(monkeypatch, *, state=None):
    app = WorkbenchApp.__new__(WorkbenchApp)
    row_a = replace(_row(), display_name="sample_a.wav", path="synthetic/a.wav")
    row_b = replace(_row(), display_name="sample_b.wav", path="synthetic/b.wav")
    app._visible_rows = [row_a, row_b]
    app._busy = False
    app._browser_row_height_px = 20
    app.root = _ChooserWidget()
    focused = []
    app._browser_canvas = SimpleNamespace(
        canvasy=lambda y: y, winfo_width=lambda: 200,
        focus_set=lambda: focused.append("browser"),
    )
    selected = ["0"]
    app._tree = SimpleNamespace(selection=lambda: tuple(selected))
    app._live_kit_state = state if state is not None else LiveKitState()
    app._live_kit_presentation = LiveKitPresentationState(app._live_kit_state)
    app._right_pane_presentation = RightPanePresentation()
    app._right_pane_presentation.show_sample_details()
    app._live_kit_frame = object()
    active = ["details"]

    def select(frame=None):
        if frame is not None:
            active[0] = frame
        return active[0]

    app._right_pane = SimpleNamespace(
        select=select,
        tab=lambda frame, _option: "Live Kit" if frame is app._live_kit_frame else "Sample Details",
    )
    refreshes = []
    app._refresh_live_kit_view = lambda: refreshes.append(app._live_kit_presentation.visible_structure())
    app._set_status = lambda *_args, **_kwargs: None
    playlists = []
    side_effects = []
    app._open_add_to_playlist_dialog = playlists.append
    for name in ("_audition_browser_row", "_play_preview", "_stop_preview", "_set_tempo", "_toggle_sync"):
        setattr(app, name, lambda *args, _name=name, **kwargs: side_effects.append(_name))
    app._transport_adapter = _TransportSpy(side_effects)
    monkeypatch.setattr(workbench, "add_workbench_row_to_playlist", lambda *args, **kwargs: side_effects.append("playlist-write"))
    buttons = []

    def button(parent, **options):
        widget = _ChooserWidget(parent, **options)
        buttons.append(widget)
        return widget

    monkeypatch.setattr(workbench.tk, "Toplevel", _ChooserWidget)
    monkeypatch.setattr(workbench.ttk, "Frame", _ChooserWidget)
    monkeypatch.setattr(workbench.ttk, "Label", _ChooserWidget)
    monkeypatch.setattr(workbench.ttk, "Button", button)
    return SimpleNamespace(
        app=app, row_a=row_a, row_b=row_b, selected=selected,
        playlists=playlists, side_effects=side_effects, buttons=buttons,
        refreshes=refreshes, focused=focused,
    )


def _click_browser_add(harness):
    assert harness.app._on_browser_canvas_click(SimpleNamespace(x=190, y=20)) == "break"
    # Assert the existing product gap before looking for any new chooser API.
    assert harness.playlists == [], "Browser Add still routes to Playlist instead of Live Kit"
    assert harness.app.root.children, "Browser Add must expose a Live-Kit target chooser"
    assert harness.side_effects == []
    return harness.app.root.children[-1]


def _target_button(harness, slot):
    matches = [button for button in harness.buttons if slot in button.options.get("text", "")]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.parametrize("selection_after_open", ["0", "1"])
def test_browser_add_uses_clicked_row_despite_stale_or_changed_selection(monkeypatch, selection_after_open):
    harness = _browser_kit_app(monkeypatch)
    assert harness.app._selected_row() is harness.row_a
    dialog = _click_browser_add(harness)
    harness.selected[:] = [selection_after_open]

    _target_button(harness, "Closed Hat").invoke()

    state = harness.app._live_kit_state
    assert state.assignment_for("Drums", "Closed Hat") is harness.row_b
    assert all(state.assignment_for("Drums", slot) is not harness.row_a for slot in state.slots_for("Drums"))
    assert harness.refreshes[-1][1].slots[1].assignment is harness.row_b
    assert harness.app._right_pane.select() is harness.app._live_kit_frame
    assert harness.app._right_pane_presentation.active_view() == "Live Kit"
    assert harness.playlists == []
    assert harness.side_effects == []
    assert dialog.destroyed and not dialog.grabbed


@pytest.mark.parametrize("restricted", [False, True])
def test_browser_add_targets_are_derived_from_current_state(monkeypatch, restricted):
    class RestrictedState(LiveKitState):
        def slots_for(self, group):
            return ("Closed Hat",) if group == "Drums" else ()

    state = RestrictedState() if restricted else LiveKitState()
    harness = _browser_kit_app(monkeypatch, state=state)
    _click_browser_add(harness)
    expected = [(group, slot) for group in state.groups() for slot in state.slots_for(group)]
    targets = [button for button in harness.buttons if button.options.get("text") != "Abbrechen"]
    assert len(targets) == len(expected)
    for button, (group, slot) in zip(targets, expected):
        assert group in button.options["text"]
        assert slot in button.options["text"]
    assert all(state.assignment_for(group, slot) is None for group, slot in expected)


@pytest.mark.parametrize("dismiss", ["cancel", "escape", "window-close"])
def test_browser_add_dismiss_has_no_mutation_and_restores_browser(monkeypatch, dismiss):
    harness = _browser_kit_app(monkeypatch)
    dialog = _click_browser_add(harness)
    assert dialog.grabbed
    assert any(button.focused for button in harness.buttons) or dialog.focused
    focus_count = len(harness.focused)
    if dismiss == "cancel":
        _target_button(harness, "Abbrechen").invoke()
    elif dismiss == "escape":
        assert dialog.bindings["<Escape>"](SimpleNamespace()) == "break"
    else:
        dialog.protocols["WM_DELETE_WINDOW"]()
    assert dialog.destroyed and not dialog.grabbed
    assert len(harness.focused) > focus_count
    state = harness.app._live_kit_state
    assert all(state.assignment_for("Drums", slot) is None for slot in state.slots_for("Drums"))
    assert harness.refreshes == []
    assert harness.playlists == []
    assert harness.side_effects == []
    assert harness.app._right_pane_presentation.active_view() == "Sample Details"
    _click_browser_add(harness)


def test_browser_add_replaces_only_the_explicit_existing_slot(monkeypatch):
    harness = _browser_kit_app(monkeypatch)
    state = harness.app._live_kit_state
    state.assign("Drums", "Closed Hat", harness.row_a)
    state.assign("Drums", "Main Drum", harness.row_a)
    _click_browser_add(harness)
    _target_button(harness, "Closed Hat").invoke()
    assert state.assignment_for("Drums", "Closed Hat") is harness.row_b
    assert state.assignment_for("Drums", "Main Drum") is harness.row_a
    assert sum(state.assignment_for("Drums", slot) is harness.row_b for slot in state.slots_for("Drums")) == 1


def test_direct_selected_live_kit_assignment_still_uses_current_selection(monkeypatch):
    harness = _browser_kit_app(monkeypatch)
    assert harness.app._assign_selected_row_to_live_kit("Drums", "Closed Hat")
    harness.selected[:] = ["1"]
    assert harness.app._assign_selected_row_to_live_kit("Drums", "Closed Hat")
    assert harness.app._live_kit_state.assignment_for("Drums", "Closed Hat") is harness.row_b
    assert len(harness.refreshes) == 2
    assert harness.playlists == [] and harness.side_effects == []
