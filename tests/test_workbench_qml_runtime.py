from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_library_navigation import (
    LibraryAvailability,
    LibraryNode,
    LibraryNodeKind,
    LibraryScope,
    LibraryScopeKind,
)
from src.workbench_qml_library import LibrarySelectionIntent, WorkbenchLibraryTreeState


SAMPLE_SOURCES = "container:sample-sources"
ROOT_ID = "root:1"
SUBFOLDER_ID = "folder:1:RHJ1bXM"
COLLECTION_ID = "collection:7"
PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


def _row(name: str) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=f"{name}.wav",
        path=f"C:/samples/{name}.wav",
        bpm=132.0,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class="one_shot",
        pred_type="Kick",
        status="ok",
    )


class FakeNavigation:
    def __init__(self) -> None:
        self.root = LibraryNode(
            ROOT_ID,
            LibraryNodeKind.REGISTERED_ROOT,
            "Samples",
            SAMPLE_SOURCES,
            True,
            True,
            LibraryAvailability.AVAILABLE,
            folder_id=1,
        )
        self.subfolder = LibraryNode(
            SUBFOLDER_ID,
            LibraryNodeKind.SUBFOLDER,
            "Drums",
            ROOT_ID,
            True,
            True,
            LibraryAvailability.AVAILABLE,
            folder_id=1,
            relative_path="Drums",
        )
        self.collection = LibraryNode(
            COLLECTION_ID,
            LibraryNodeKind.COLLECTION,
            "Set A",
            "container:collections",
            True,
            False,
            LibraryAvailability.AVAILABLE,
            playlist_id=7,
        )
        self.top = (
            LibraryNode(
                SAMPLE_SOURCES,
                LibraryNodeKind.SAMPLE_SOURCES,
                "Sample Sources",
                None,
                False,
                True,
                LibraryAvailability.AVAILABLE,
            ),
            LibraryNode(
                "scope:all-library",
                LibraryNodeKind.ALL_SAMPLES,
                "All Samples",
                None,
                True,
                False,
                LibraryAvailability.AVAILABLE,
            ),
            LibraryNode(
                "scope:catalog-readonly",
                LibraryNodeKind.CATALOG,
                "Catalog",
                None,
                True,
                False,
                LibraryAvailability.AVAILABLE,
            ),
            LibraryNode(
                "container:collections",
                LibraryNodeKind.COLLECTIONS,
                "Collections",
                None,
                False,
                True,
                LibraryAvailability.AVAILABLE,
            ),
        )
        self.sample_roots = [self.root]
        self.root_children_enabled = True

    def top_level_nodes(self):
        return self.top

    def children(self, node_id: str):
        if node_id == SAMPLE_SOURCES:
            return tuple(self.sample_roots) + (
                LibraryNode(
                    "action:add-source",
                    LibraryNodeKind.ADD_SOURCE,
                    "Add Source…",
                    SAMPLE_SOURCES,
                    False,
                    False,
                    LibraryAvailability.AVAILABLE,
                ),
            )
        if node_id == ROOT_ID:
            return (self.subfolder,) if self.root_children_enabled else ()
        if node_id == "container:collections":
            return (self.collection,)
        return ()

    def resolve_scope(self, node_id: str):
        return {
            ROOT_ID: LibraryScope(LibraryScopeKind.ROOT, folder_id=1, folder_path="C:/samples"),
            SUBFOLDER_ID: LibraryScope(
                LibraryScopeKind.SUBFOLDER,
                folder_id=1,
                folder_path="C:/samples",
                relative_path="Drums",
            ),
            "scope:all-library": LibraryScope(LibraryScopeKind.ALL_SAMPLES),
            "scope:catalog-readonly": LibraryScope(
                LibraryScopeKind.CATALOG,
                catalog_limit=17,
            ),
            COLLECTION_ID: LibraryScope(
                LibraryScopeKind.COLLECTION,
                playlist_id=7,
                playlist_name="Set A",
            ),
        }.get(node_id)


def _composition(monkeypatch):
    from src import workbench_qml_runtime as runtime

    state = WorkbenchLibraryTreeState(FakeNavigation())
    composition = runtime.Screen1QmlRuntimeComposition(tree_state=state)
    return runtime, composition


def _intent(node: LibraryNode, scope: LibraryScope) -> LibrarySelectionIntent:
    return LibrarySelectionIntent(node=node, scope=scope)


def test_scope_dispatch_uses_each_existing_loader_once_and_sets_visual_selection(
    monkeypatch: pytest.MonkeyPatch,
):
    runtime, composition = _composition(monkeypatch)
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        runtime,
        "load_cached_folder_rows",
        lambda folder: calls.append(("root", folder)) or [_row("root")],
    )
    monkeypatch.setattr(
        runtime,
        "load_cached_subfolder_rows",
        lambda folder_id, relative: calls.append(("subfolder", (folder_id, relative)))
        or [_row("subfolder")],
    )
    monkeypatch.setattr(
        runtime,
        "load_all_cached_rows",
        lambda: calls.append(("all", None)) or [_row("all")],
    )
    monkeypatch.setattr(
        runtime,
        "load_catalog_rows",
        lambda *, limit: calls.append(("catalog", limit)) or [_row("catalog")],
    )
    monkeypatch.setattr(
        runtime,
        "load_playlist_workbench_rows",
        lambda name: calls.append(("collection", name)) or [_row("collection")],
    )

    nav = composition.library_tree.navigation
    cases = (
        (nav.root, nav.resolve_scope(ROOT_ID), "root"),
        (nav.subfolder, nav.resolve_scope(SUBFOLDER_ID), "subfolder"),
        (nav.top[1], nav.resolve_scope("scope:all-library"), "all"),
        (nav.top[2], nav.resolve_scope("scope:catalog-readonly"), "catalog"),
        (nav.collection, nav.resolve_scope(COLLECTION_ID), "collection"),
    )

    for node, scope, expected_kind in cases:
        result = composition.dispatch_selection(_intent(node, scope))
        assert result.error is None
        assert result.selected_index == 0
        assert calls[-1][0] == expected_kind

    assert calls == [
        ("root", "C:/samples"),
        ("subfolder", (1, "Drums")),
        ("all", None),
        ("catalog", 17),
        ("collection", "Set A"),
    ]


@pytest.mark.parametrize(
    "scope",
    (
        LibraryScope(LibraryScopeKind.ROOT, folder_id=1),
        LibraryScope(LibraryScopeKind.SUBFOLDER, folder_id=1),
        LibraryScope(LibraryScopeKind.SUBFOLDER, relative_path="Drums"),
        LibraryScope(LibraryScopeKind.COLLECTION, playlist_id=7),
        LibraryScope(LibraryScopeKind.CATALOG, catalog_limit=None),
    ),
)
def test_incomplete_scope_is_fail_closed_without_loader_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    scope: LibraryScope,
):
    runtime, composition = _composition(monkeypatch)
    calls: list[str] = []
    for name in (
        "load_cached_folder_rows",
        "load_cached_subfolder_rows",
        "load_all_cached_rows",
        "load_catalog_rows",
        "load_playlist_workbench_rows",
    ):
        monkeypatch.setattr(runtime, name, lambda *args, _name=name, **kwargs: calls.append(_name))

    node = LibraryNode(
        "invalid",
        LibraryNodeKind.CATALOG,
        "Invalid",
        None,
        True,
        False,
        LibraryAvailability.AVAILABLE,
    )
    result = composition.dispatch_selection(_intent(node, scope))

    assert result.error
    assert result.rows == ()
    assert result.selected_index == -1
    assert calls == []


def test_empty_scope_load_is_no_scope_and_non_empty_load_does_not_audition(
    monkeypatch: pytest.MonkeyPatch,
):
    runtime, composition = _composition(monkeypatch)
    nav = composition.library_tree.navigation
    monkeypatch.setattr(runtime, "load_all_cached_rows", lambda: [])
    empty = composition.dispatch_selection(
        _intent(nav.top[1], nav.resolve_scope("scope:all-library"))
    )
    assert empty.rows == ()
    assert empty.selected_index == -1
    assert empty.error is None

    monkeypatch.setattr(runtime, "load_all_cached_rows", lambda: [_row("first")])
    loaded = composition.dispatch_selection(
        _intent(nav.top[1], nav.resolve_scope("scope:all-library"))
    )
    assert [row.display_name for row in loaded.rows] == ["first"]
    assert loaded.selected_index == 0
    assert composition.audition_dispatches == []


def test_removing_active_root_clears_scope_and_tree_selection(
    monkeypatch: pytest.MonkeyPatch,
):
    runtime, composition = _composition(monkeypatch)
    nav = composition.library_tree.navigation
    monkeypatch.setattr(runtime, "load_cached_folder_rows", lambda _folder: [_row("root")])
    intent = _intent(nav.root, nav.resolve_scope(ROOT_ID))
    composition.library_tree.select(ROOT_ID)
    composition.dispatch_selection(intent)
    removed: list[int] = []
    monkeypatch.setattr(
        runtime,
        "remove_workbench_library_folder",
        lambda folder_id: removed.append(int(folder_id)) or True,
    )

    assert composition.remove_source(1) is True
    assert removed == [1]
    assert composition.browser_state.rows == ()
    assert composition.browser_state.selected_index == -1
    assert composition.library_tree.selected_node_id is None
    assert composition.library_tree.selection_intent is None


def test_removing_active_subfolder_clears_root_scoped_selection(
    monkeypatch: pytest.MonkeyPatch,
):
    runtime, composition = _composition(monkeypatch)
    nav = composition.library_tree.navigation
    composition.library_tree.expand(SAMPLE_SOURCES)
    composition.library_tree.expand(ROOT_ID)
    monkeypatch.setattr(runtime, "load_cached_subfolder_rows", lambda *_args: [_row("subfolder")])
    composition.library_tree.select(SUBFOLDER_ID)
    composition.dispatch_selection(_intent(nav.subfolder, nav.resolve_scope(SUBFOLDER_ID)))
    monkeypatch.setattr(runtime, "remove_workbench_library_folder", lambda _folder_id: True)

    assert composition.remove_source(1) is True
    assert composition.browser_state.rows == ()
    assert composition.browser_state.selected_index == -1
    assert composition.library_tree.selected_node_id is None
    assert composition.library_tree.selection_intent is None


def test_empty_browser_is_fail_closed_for_arrows_and_harmony():
    from src.workbench_qml import Screen1QmlInteractionAdapter, Screen1QmlViewModel

    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    adapter = Screen1QmlInteractionAdapter(view_model=view_model)

    assert adapter.navigate_browser("next", browser_has_focus=True) is None
    assert adapter.navigate_browser("previous", browser_has_focus=True) is None
    assert adapter.toggle_harmonic_match() is False
    assert view_model.selected_browser_index == -1


def test_add_source_uses_existing_validation_and_registration_seams(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    runtime, composition = _composition(monkeypatch)
    registered: list[Path] = []
    monkeypatch.setattr(runtime, "add_workbench_library_folder", lambda path: registered.append(Path(path)) or 9)

    assert composition.add_source(tmp_path) is True
    assert registered == [tmp_path.resolve()]


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_add_source_node_is_an_action_and_replace_refresh_has_no_stale_children():
    from PySide6.QtCore import QCoreApplication

    from src.workbench_qml_library import create_qt_library_tree_model

    app = QCoreApplication.instance() or QCoreApplication([])
    del app
    navigation = FakeNavigation()
    state = WorkbenchLibraryTreeState(navigation)
    model = create_qt_library_tree_model(state)
    sample_index = model.index(0, 0)
    model.fetchMore(sample_index)
    initial_root_index = model.index(0, 0, sample_index)
    model.fetchMore(initial_root_index)
    assert model.rowCount(initial_root_index) == 1

    assert model.data(model.index(0, 0, sample_index), model.SelectableRole) is True
    action_index = model.index(model.rowCount(sample_index) - 1, 0, sample_index)
    assert model.data(action_index, model.KindRole) == LibraryNodeKind.ADD_SOURCE.value
    assert model.data(action_index, model.SelectableRole) is False
    assert model.selectNode("action:add-source") is False

    navigation.sample_roots.clear()
    navigation.root_children_enabled = False
    assert model.replaceBranch(SAMPLE_SOURCES) is True
    assert model.rowCount(sample_index) == 1
    assert model.data(model.index(0, 0, sample_index), model.KindRole) == LibraryNodeKind.ADD_SOURCE.value

    navigation.sample_roots.append(navigation.root)
    assert model.replaceBranch(SAMPLE_SOURCES) is True
    root_index = model.index(0, 0, sample_index)
    model.fetchMore(root_index)
    assert model.rowCount(root_index) == 0
    assert model.rowCount(sample_index) == 2
    assert [
        model.data(model.index(index, 0, sample_index), model.NodeIdRole)
        for index in range(model.rowCount(sample_index))
    ] == [ROOT_ID, "action:add-source"]


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_library_bridge_dispatches_selection_callback_once_without_signal_wiring():
    from PySide6.QtCore import QCoreApplication

    from src.workbench_qml import _qml_library_interaction_bridge
    from src.workbench_qml_library import create_qt_library_tree_model

    app = QCoreApplication.instance() or QCoreApplication([])
    del app
    state = WorkbenchLibraryTreeState(FakeNavigation())
    state.expand(SAMPLE_SOURCES)
    model = create_qt_library_tree_model(state)
    dispatches: list[str] = []
    bridge = _qml_library_interaction_bridge(
        model,
        on_selection=lambda: dispatches.append(state.selection_intent.node.node_id),
    )

    bridge.selectLibraryNode(ROOT_ID)

    assert dispatches == [ROOT_ID]
    assert state.selection_intent is not None


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_screen_data_bridge_notifies_dynamic_browser_properties():
    from PySide6.QtCore import QCoreApplication

    from src.workbench_qml import Screen1QmlViewModel, _qml_screen_data_bridge

    app = QCoreApplication.instance() or QCoreApplication([])
    del app
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    bridge = _qml_screen_data_bridge(view_model)
    notifications: list[bool] = []
    bridge.browserRowsChanged.connect(lambda: notifications.append(True))

    view_model.set_browser_state(
        rows=(_row("dynamic"),),
        selected_index=0,
        browser_context="Samples",
        error=None,
    )
    bridge.refresh()

    assert notifications == [True]
    assert bridge.selectedBrowserIndex == 0
    assert bridge.browserContext == "Samples"
    assert bridge.browserRows[0]["name"] == "dynamic"


def test_production_route_constructs_no_scope_without_baseline(monkeypatch: pytest.MonkeyPatch):
    from src import workbench_qml

    def fail_baseline(cls, _state_id):
        raise AssertionError("Production-QML darf baseline() nicht aufrufen")

    monkeypatch.setattr(workbench_qml.Screen1QmlViewModel, "baseline", classmethod(fail_baseline))
    captured: dict[str, object] = {}

    class FakeApp:
        def exec(self) -> int:
            return 23

    def fake_engine(view_model, *, runtime_composition):
        captured["view_model"] = view_model
        captured["composition"] = runtime_composition
        return FakeApp(), object(), object()

    monkeypatch.setattr(workbench_qml, "_qml_engine", fake_engine)

    assert workbench_qml.run_qml_screen1() == 23
    view_model = captured["view_model"]
    assert view_model.browser_rows == ()
    assert view_model.selected_browser_index == -1
    assert captured["composition"].browser_state.rows == ()


def test_production_qml_contract_has_observable_screen_state_and_action_path():
    from src import workbench_qml

    source = workbench_qml.QML_SOURCE
    assert "browserRowsChanged" in source or "screenModel" in source
    assert "addSource" in source
    assert "removeSource" in source
    assert "action:add-source" in source
    assert 'objectName: "browserPane"' in source
    assert "Layout.minimumWidth: 0" in source


class _RecordingHarmonyController:
    """Record set_anchor calls so a test can assert the exact candidate pool."""

    def __init__(self) -> None:
        self.set_anchor_calls: list[tuple[object, tuple[object, ...]]] = []
        self.anchor = None
        self.results = ()
        self.status = ""

    def set_anchor(self, anchor, candidates):
        self.set_anchor_calls.append((anchor, tuple(candidates)))
        self.anchor = anchor
        self.results = ()
        self.status = "Harmonic Match ist ausgeschaltet."


def _register_analyzed_root(
    tmp_path: Path,
) -> tuple[Path, Path]:
    """Create a real root with one nested source folder and cache its rows."""
    from src.workbench_controller import analyze_folder_for_workbench
    from src.workbench_library import workbench_library_db_path
    from tests.audio_fixtures import write_kick_transient_wav, write_major_chord_wav

    root = tmp_path / "sources"
    (root / "Drums").mkdir(parents=True)
    write_kick_transient_wav(root / "kick_b.wav", bpm=120.0, duration_sec=2.0)
    write_major_chord_wav(root / "Drums" / "chord.wav")
    write_major_chord_wav(root / "chord_root.wav")
    db = workbench_library_db_path()
    analyze_folder_for_workbench(root, library_db_path=db)
    return root, db


def test_real_library_root_scope_loads_exact_root_rows_and_candidate_pool(
    tmp_path: Path,
):
    from src.workbench_qml import (
        Screen1QmlInteractionAdapter,
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_library_navigation import (
        LibraryNodeKind,
        WorkbenchLibraryNavigation,
    )

    _root, db = _register_analyzed_root(tmp_path)
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    nodes = navigation.children("container:sample-sources")
    root_node = next(
        node for node in nodes if node.kind is LibraryNodeKind.REGISTERED_ROOT
    )
    scope = navigation.resolve_scope(root_node.node_id)
    intent = _intent(root_node, scope)

    state = composition.dispatch_selection(intent)

    assert state.error is None
    assert state.selected_index == 0
    rels = sorted(
        row.details["relative_path"].replace("\\", "/") for row in state.rows
    )
    assert rels == sorted(["kick_b.wav", "Drums/chord.wav", "chord_root.wav"])

    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    view_model.set_browser_state(
        rows=tuple(state.rows),
        selected_index=0,
        browser_context="Samples",
        error=None,
    )
    recording = _RecordingHarmonyController()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=recording,
    )

    assert adapter.toggle_harmonic_match() is True
    assert len(recording.set_anchor_calls) == 1
    _, candidates = recording.set_anchor_calls[0]
    assert candidates == tuple(row.source_row for row in view_model.browser_rows)
    assert {row.details["relative_path"].replace("\\", "/") for row in candidates} == {
        "kick_b.wav",
        "Drums/chord.wav",
        "chord_root.wav",
    }


def test_real_library_subfolder_scope_loads_exact_subtree_rows_and_candidate_pool(
    tmp_path: Path,
):
    from src.workbench_qml import (
        Screen1QmlInteractionAdapter,
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_library_navigation import (
        LibraryNodeKind,
        WorkbenchLibraryNavigation,
    )

    _root, db = _register_analyzed_root(tmp_path)
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    nodes = navigation.children("container:sample-sources")
    root_node = next(
        node for node in nodes if node.kind is LibraryNodeKind.REGISTERED_ROOT
    )
    subfolder_node = next(
        node
        for node in navigation.children(root_node.node_id)
        if node.kind is LibraryNodeKind.SUBFOLDER
    )

    scope = navigation.resolve_scope(subfolder_node.node_id)
    state = composition.dispatch_selection(_intent(subfolder_node, scope))

    assert state.error is None
    assert state.selected_index == 0
    rels = sorted(
        row.details["relative_path"].replace("\\", "/") for row in state.rows
    )
    assert rels == ["Drums/chord.wav"]

    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    view_model.set_browser_state(
        rows=tuple(state.rows),
        selected_index=0,
        browser_context="Samples",
        error=None,
    )
    recording = _RecordingHarmonyController()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=recording,
    )

    assert adapter.toggle_harmonic_match() is True
    assert len(recording.set_anchor_calls) == 1
    _, candidates = recording.set_anchor_calls[0]
    assert candidates == tuple(row.source_row for row in view_model.browser_rows)
    assert {row.details["relative_path"].replace("\\", "/") for row in candidates} == {
        "Drums/chord.wav"
    }


def test_real_library_scope_switch_swaps_candidate_pool(tmp_path: Path):
    from src.workbench_qml import (
        Screen1QmlInteractionAdapter,
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_library_navigation import (
        LibraryNodeKind,
        WorkbenchLibraryNavigation,
    )

    _root, db = _register_analyzed_root(tmp_path)
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
    recording = _RecordingHarmonyController()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=recording,
    )

    nodes = navigation.children("container:sample-sources")
    root_node = next(
        node for node in nodes if node.kind is LibraryNodeKind.REGISTERED_ROOT
    )
    root_state = composition.dispatch_selection(
        _intent(root_node, navigation.resolve_scope(root_node.node_id))
    )
    view_model.set_browser_state(
        rows=tuple(root_state.rows),
        selected_index=0,
        browser_context="Samples",
        error=None,
    )
    adapter.toggle_harmonic_match()
    root_candidates = recording.set_anchor_calls[-1][1]
    assert {
        row.details["relative_path"].replace("\\", "/") for row in root_candidates
    } == {
        "kick_b.wav",
        "Drums/chord.wav",
        "chord_root.wav",
    }
    assert adapter.toggle_harmonic_match() is False

    subfolder_node = next(
        node
        for node in navigation.children(root_node.node_id)
        if node.kind is LibraryNodeKind.SUBFOLDER
    )
    sub_state = composition.dispatch_selection(
        _intent(subfolder_node, navigation.resolve_scope(subfolder_node.node_id))
    )
    view_model.set_browser_state(
        rows=tuple(sub_state.rows),
        selected_index=0,
        browser_context="Samples",
        error=None,
    )
    adapter.toggle_harmonic_match()
    sub_candidates = recording.set_anchor_calls[-1][1]
    assert {
        row.details["relative_path"].replace("\\", "/") for row in sub_candidates
    } == {
        "Drums/chord.wav"
    }


def _seed_freshness_root(
    tmp_path: Path,
    *,
    analyzer_version: str | None,
    relative_path: str = "Drums/chord.wav",
    key: str = "C",
    bpm: float | None = None,
    source_exists: bool = True,
) -> tuple[Path, Path]:
    """Register a real root and seed one cached row with exactly *version*."""
    from src.workbench_library import upsert_folder, upsert_sample, workbench_library_db_path
    from src.workbench_qml import Screen1QmlRuntimeComposition
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from tests.audio_fixtures import write_major_chord_wav

    root = tmp_path / "sources"
    (root / "Drums").mkdir(parents=True)
    db = workbench_library_db_path()
    folder_id = upsert_folder(root, db_path=db)
    chord = write_major_chord_wav(root / "Drums" / "chord.wav")
    st = chord.stat()
    row = WorkbenchRow(
        display_name=chord.name,
        relative_path=relative_path,
        path=str(chord),
        bpm=bpm,
        key=key,
        key_conf=0.8 if key else None,
        loudness=-12.0,
        brightness=1500.0,
        sample_class="loop",
        pred_type="Keys",
        status="ok",
        details={"path": str(chord)},
    )
    upsert_sample(
        folder_id,
        row,
        size_bytes=st.st_size,
        mtime_ns=st.st_mtime_ns,
        db_path=db,
        analyzer_version=analyzer_version,
    )
    if not source_exists:
        chord.unlink()
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    return composition, root, db


def _registered_root_node(composition):
    from src.workbench_library_navigation import LibraryNodeKind

    navigation = composition.library_tree.navigation
    return next(
        node
        for node in navigation.children("container:sample-sources")
        if node.kind is LibraryNodeKind.REGISTERED_ROOT
    )


def test_refresh_target_reports_stale_v1_root_with_existing_source(tmp_path: Path):
    from src.workbench_qml import Screen1QmlRuntimeComposition  # noqa: F401

    composition, root, _db = _seed_freshness_root(tmp_path, analyzer_version="workbench_v1")
    root_node = _registered_root_node(composition)
    scope = composition.library_tree.navigation.resolve_scope(root_node.node_id)

    target = composition.refresh_target(scope)

    assert target is not None
    assert target.folder_id == root_node.folder_id
    assert str(target.normalized_path) == str(root)


def test_refresh_target_fresh_v2_root_needs_no_refresh(tmp_path: Path):
    from src.workbench_library import WORKBENCH_ANALYZER_VERSION

    composition, _root, _db = _seed_freshness_root(
        tmp_path, analyzer_version=WORKBENCH_ANALYZER_VERSION
    )
    root_node = _registered_root_node(composition)
    scope = composition.library_tree.navigation.resolve_scope(root_node.node_id)

    assert composition.refresh_target(scope) is None


def test_refresh_target_stale_subfolder_reports_target(tmp_path: Path):
    from src.workbench_library_navigation import LibraryNodeKind

    composition, _root, _db = _seed_freshness_root(
        tmp_path, analyzer_version="workbench_v1"
    )
    navigation = composition.library_tree.navigation
    root_node = _registered_root_node(composition)
    subfolder_node = next(
        node
        for node in navigation.children(root_node.node_id)
        if node.kind is LibraryNodeKind.SUBFOLDER
    )
    scope = navigation.resolve_scope(subfolder_node.node_id)

    target = composition.refresh_target(scope)

    assert target is not None
    assert target.folder_id == root_node.folder_id


def test_refresh_target_ignores_stale_rows_whose_source_was_deleted(tmp_path: Path):
    composition, _root, _db = _seed_freshness_root(
        tmp_path, analyzer_version="workbench_v1", source_exists=False
    )
    root_node = _registered_root_node(composition)
    scope = composition.library_tree.navigation.resolve_scope(root_node.node_id)

    assert composition.refresh_target(scope) is None


def test_refresh_target_treats_null_version_rows_as_stale(tmp_path: Path):
    composition, _root, _db = _seed_freshness_root(
        tmp_path, analyzer_version=None
    )
    root_node = _registered_root_node(composition)
    scope = composition.library_tree.navigation.resolve_scope(root_node.node_id)

    assert composition.refresh_target(scope) is not None


def test_refresh_target_never_targets_non_folder_scopes(tmp_path: Path):
    from src.workbench_qml import Screen1QmlRuntimeComposition  # noqa: F401

    composition, _root, _db = _seed_freshness_root(
        tmp_path, analyzer_version="workbench_v1"
    )
    all_samples = LibraryScope(LibraryScopeKind.ALL_SAMPLES)
    collection = LibraryScope(
        LibraryScopeKind.COLLECTION, playlist_name="Set A"
    )
    catalog = LibraryScope(LibraryScopeKind.CATALOG, catalog_limit=17)
    incomplete_subfolder = LibraryScope(LibraryScopeKind.SUBFOLDER, folder_id=1)

    assert composition.refresh_target(all_samples) is None
    assert composition.refresh_target(collection) is None
    assert composition.refresh_target(catalog) is None
    assert composition.refresh_target(incomplete_subfolder) is None


def test_post_analysis_node_id_preserves_active_subfolder_and_root(tmp_path: Path):
    from src.workbench_qml import Screen1QmlRuntimeComposition
    from src.workbench_library import workbench_library_db_path

    composition = Screen1QmlRuntimeComposition(
        library_db_path=workbench_library_db_path()
    )

    assert (
        composition.post_analysis_node_id(
            1, previous_selected="folder:1:RHJ1bXM"
        )
        == "folder:1:RHJ1bXM"
    )
    assert (
        composition.post_analysis_node_id(1, previous_selected="root:1")
        == "root:1"
    )
    assert (
        composition.post_analysis_node_id(
            1, previous_selected="folder:2:RHJ1bXM"
        )
        == "root:1"
    )
    assert (
        composition.post_analysis_node_id(
            1, previous_selected="scope:all-library"
        )
        == "root:1"
    )
    assert composition.post_analysis_node_id(1) == "root:1"


def test_dispatch_selection_tracks_active_node_id(monkeypatch: pytest.MonkeyPatch):
    runtime, composition = _composition(monkeypatch)
    monkeypatch.setattr(runtime, "load_cached_folder_rows", lambda _folder: [_row("root")])
    nav = composition.library_tree.navigation

    composition.dispatch_selection(_intent(nav.root, nav.resolve_scope(ROOT_ID)))

    assert composition.selected_node_id == ROOT_ID


class _ReturningHarmonyController(_RecordingHarmonyController):
    """Record set_anchor calls and produce actionable suggestions for the pool."""

    def set_anchor(self, anchor, candidates):
        from src.workbench_harmony import HarmonyRelation, HarmonySuggestion

        super().set_anchor(anchor, candidates)
        rows = tuple(candidates)
        self.results = tuple(
            HarmonySuggestion(
                row=row,
                relation=HarmonyRelation.UNCERTAIN,
                harmony_score=0.5,
                bpm_score=0.5,
                total_score=0.5,
                pitch_shift_semitones=None,
                explanation="test",
            )
            for row in rows
        )
        self.status = f"{len(rows)} sicher."


def _register_root_at(tmp_path: Path, folder_name: str) -> tuple[Path, Path]:
    from src.workbench_controller import analyze_folder_for_workbench
    from src.workbench_library import workbench_library_db_path
    from tests.audio_fixtures import write_kick_transient_wav, write_major_chord_wav

    root = tmp_path / folder_name
    root.mkdir(parents=True)
    write_kick_transient_wav(root / "kit.wav", bpm=120.0, duration_sec=2.0)
    write_major_chord_wav(root / "pad.wav")
    db = workbench_library_db_path()
    analyze_folder_for_workbench(root, library_db_path=db)
    return root, db


def _qml_adapter_for_state(state, *, recording: bool = True):
    from src.workbench_qml import (
        Screen1QmlInteractionAdapter,
        Screen1QmlViewModel,
    )

    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    view_model.set_browser_state(
        rows=tuple(state.rows),
        selected_index=0,
        browser_context="Samples",
        error=None,
    )
    controller = _ReturningHarmonyController() if recording else _RecordingHarmonyController()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=controller,
    )
    return view_model, adapter, controller


def test_harmonic_session_invalidated_across_root_scope_switch(tmp_path: Path):
    from src.workbench_qml import Screen1QmlRuntimeComposition
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_library_navigation import (
        LibraryNodeKind,
        WorkbenchLibraryNavigation,
    )

    _root_a, db = _register_analyzed_root(tmp_path)
    _root_b, same_db = _register_root_at(tmp_path, "bmore")
    assert same_db == db
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    roots = [
        node
        for node in navigation.children("container:sample-sources")
        if node.kind is LibraryNodeKind.REGISTERED_ROOT
    ]
    assert len(roots) == 2
    root_a, root_b = roots

    scope_a = navigation.resolve_scope(root_a.node_id)
    state_a = composition.dispatch_selection(_intent(root_a, scope_a))
    view_model, adapter, controller = _qml_adapter_for_state(state_a)
    adapter.replace_browser_scope(scope_a)

    assert adapter.toggle_harmonic_match() is True
    assert len(controller.set_anchor_calls) == 1
    assert adapter.harmonic_match_open is True
    adapter.select_harmonic_match(min(1, len(view_model.harmony_rows) - 1))
    adapter.set_harmonic_match_scroll_y(50)

    scope_b = navigation.resolve_scope(root_b.node_id)
    state_b = composition.dispatch_selection(_intent(root_b, scope_b))
    assert state_b.error is None and state_b.rows
    view_model.set_browser_state(
        rows=tuple(state_b.rows),
        selected_index=0,
        browser_context="Root B",
        error=None,
    )
    adapter.replace_browser_scope(scope_b)

    assert adapter.harmonic_match_open is False
    assert view_model.state_id == "screen1-default-3panel"
    assert view_model.browser_context == "Root B"
    assert view_model.harmony_rows == ()
    assert view_model.harmony_anchor == ""
    assert controller.anchor is None
    assert controller.results == ()
    b_paths = {str(row.path) for row in state_b.rows}
    assert {str(row.source_row.path) for row in view_model.browser_rows} == b_paths
    with pytest.raises(IndexError):
        adapter.preview_harmonic_match(0)
    with pytest.raises(IndexError):
        adapter.request_add_harmonic_match_to_kit(0)
    assert adapter.navigate_harmonic_match("next", match_has_focus=True) is None
    assert adapter.selected_harmonic_match_index == 0
    assert adapter.harmonic_match_scroll_y == 0.0

    assert adapter.toggle_harmonic_match() is True
    assert len(controller.set_anchor_calls) == 2
    anchor_b, b_candidates = controller.set_anchor_calls[-1]
    assert str(anchor_b.path) in b_paths
    assert {str(row.path) for row in b_candidates} == b_paths
    assert adapter.selected_harmonic_match_index == 0
    assert adapter.harmonic_match_scroll_y == 0.0


def test_harmonic_session_invalidated_across_subfolder_scope_switch(tmp_path: Path):
    from src.workbench_qml import Screen1QmlRuntimeComposition
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_library_navigation import (
        LibraryNodeKind,
        WorkbenchLibraryNavigation,
    )

    _root, db = _register_analyzed_root(tmp_path)
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    nodes = navigation.children("container:sample-sources")
    root_node = next(
        node for node in nodes if node.kind is LibraryNodeKind.REGISTERED_ROOT
    )
    subfolder_node = next(
        node
        for node in navigation.children(root_node.node_id)
        if node.kind is LibraryNodeKind.SUBFOLDER
    )

    root_scope = navigation.resolve_scope(root_node.node_id)
    root_state = composition.dispatch_selection(_intent(root_node, root_scope))
    view_model, adapter, controller = _qml_adapter_for_state(root_state)
    adapter.replace_browser_scope(root_scope)
    assert adapter.toggle_harmonic_match() is True
    assert len(controller.set_anchor_calls) == 1

    sub_scope = navigation.resolve_scope(subfolder_node.node_id)
    sub_state = composition.dispatch_selection(_intent(subfolder_node, sub_scope))
    assert sub_state.error is None and sub_state.rows
    view_model.set_browser_state(
        rows=tuple(sub_state.rows),
        selected_index=0,
        browser_context="Subfolder",
        error=None,
    )
    adapter.replace_browser_scope(sub_scope)

    assert adapter.harmonic_match_open is False
    assert view_model.harmony_rows == ()
    sub_paths = {str(row.path) for row in sub_state.rows}
    assert {str(row.source_row.path) for row in view_model.browser_rows} == sub_paths

    assert adapter.toggle_harmonic_match() is True
    assert len(controller.set_anchor_calls) == 2
    _, sub_candidates = controller.set_anchor_calls[-1]
    assert {str(row.path) for row in sub_candidates} == sub_paths


def test_harmonic_same_scope_reload_and_reopen_reuse_stays_intact(tmp_path: Path):
    from src.workbench_qml import Screen1QmlRuntimeComposition
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_library_navigation import (
        LibraryNodeKind,
        WorkbenchLibraryNavigation,
    )

    _root, db = _register_analyzed_root(tmp_path)
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    nodes = navigation.children("container:sample-sources")
    root_node = next(
        node for node in nodes if node.kind is LibraryNodeKind.REGISTERED_ROOT
    )
    scope = navigation.resolve_scope(root_node.node_id)
    state = composition.dispatch_selection(_intent(root_node, scope))
    view_model, adapter, controller = _qml_adapter_for_state(state)
    adapter.replace_browser_scope(scope)

    assert adapter.toggle_harmonic_match() is True
    assert len(controller.set_anchor_calls) == 1
    assert adapter.toggle_harmonic_match() is False

    adapter.replace_browser_scope(scope)
    assert adapter.harmonic_match_open is False

    assert adapter.toggle_harmonic_match() is True
    assert len(controller.set_anchor_calls) == 1
    assert view_model.harmony_rows

    adapter.replace_browser_scope(scope)
    assert adapter.harmonic_match_open is True
    assert view_model.harmony_rows
    assert len(controller.set_anchor_calls) == 1


def test_harmonic_session_closes_when_browser_scope_becomes_unresolved():
    from src.workbench_qml import (
        Screen1QmlInteractionAdapter,
        Screen1QmlViewModel,
    )

    rows = (_row("A1"), _row("A2"), _row("A3"))
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    view_model.set_browser_state(
        rows=rows,
        selected_index=0,
        browser_context="A",
        error=None,
    )
    controller = _ReturningHarmonyController()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=controller,
    )
    adapter.replace_browser_scope(LibraryScope(LibraryScopeKind.ROOT, folder_id=1))

    assert adapter.toggle_harmonic_match() is True
    assert len(controller.set_anchor_calls) == 1

    adapter.replace_browser_scope(None)

    assert adapter.harmonic_match_open is False
    assert view_model.state_id == "screen1-default-3panel"
    assert view_model.harmony_rows == ()
    assert controller.anchor is None


def test_refresh_target_reuses_already_loaded_rows_without_second_db_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    runtime, composition = _composition(monkeypatch)
    nav = composition.library_tree.navigation
    scope = nav.resolve_scope(ROOT_ID)
    audio = tmp_path / "fresh.wav"
    audio.write_bytes(b"RIFF")
    fresh = WorkbenchRow(
        display_name="fresh",
        relative_path="fresh.wav",
        path=str(audio),
        bpm=120.0,
        key="Cmaj",
        key_conf=0.8,
        loudness=None,
        brightness=None,
        sample_class="loop",
        pred_type="Loop",
        status="ok",
        details={"analyzer_version": runtime.WORKBENCH_ANALYZER_VERSION},
    )
    monkeypatch.setattr(runtime, "load_cached_folder_rows", lambda _folder: [fresh])
    composition.dispatch_selection(_intent(nav.root, scope))
    monkeypatch.setattr(
        runtime,
        "workbench_scope_requires_refresh",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("already-loaded scope must not be reloaded for freshness")
        ),
    )

    assert composition.refresh_target(scope) is None


def test_refresh_target_detects_stale_loaded_row_without_second_db_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    runtime, composition = _composition(monkeypatch)
    nav = composition.library_tree.navigation
    scope = nav.resolve_scope(ROOT_ID)
    audio = tmp_path / "stale.wav"
    audio.write_bytes(b"RIFF")
    stale = WorkbenchRow(
        display_name="stale",
        relative_path="stale.wav",
        path=str(audio),
        bpm=120.0,
        key="C",
        key_conf=0.8,
        loudness=None,
        brightness=None,
        sample_class="loop",
        pred_type="Loop",
        status="ok",
        details={"analyzer_version": "workbench_v1"},
    )
    monkeypatch.setattr(runtime, "load_cached_folder_rows", lambda _folder: [stale])
    composition.dispatch_selection(_intent(nav.root, scope))
    monkeypatch.setattr(
        runtime,
        "workbench_scope_requires_refresh",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("already-loaded scope must not be reloaded for freshness")
        ),
    )

    target = composition.refresh_target(scope)

    assert target is not None
    assert target.folder_id == 1
