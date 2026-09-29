"""Clean Start workspace contracts (#693).

Docs: docs/WORKBENCH_CLEAN_START.md
Authority: #693 supersedes auto-restore / synthetic row-0 selection on Source select.
"""

from __future__ import annotations

import importlib.util
import json
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
from src.workbench_qml_startup import (
    SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
    WorkspaceMode,
    load_startup_preset,
    resolve_launch_workspace,
    save_startup_preset_for_tests,
    workbench_startup_preset_file,
)
from src.workbench_visual_acceptance import (
    build_screen1_visual_fixture_v2,
    resolve_screen1_visual_state_v2,
)

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None
SAMPLE_SOURCES = "container:sample-sources"


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


def _intent(node: LibraryNode, scope: LibraryScope) -> LibrarySelectionIntent:
    return LibrarySelectionIntent(node=node, scope=scope)


def _register_analyzed_root(tmp_path: Path) -> tuple[Path, Path]:
    from src.workbench_controller import analyze_folder_for_workbench
    from src.workbench_library import workbench_library_db_path
    from tests.audio_fixtures import write_kick_transient_wav

    root = tmp_path / "sources"
    root.mkdir(parents=True)
    write_kick_transient_wav(root / "kick.wav", bpm=120.0, duration_sec=1.0)
    db = workbench_library_db_path()
    analyze_folder_for_workbench(root, library_db_path=db)
    return root, db


# --- Startup preset / launch resolver ---------------------------------------


def test_missing_startup_preset_resolves_to_clean_start(tmp_path: Path):
    result = load_startup_preset(state_dir=tmp_path)
    assert result.preset is None
    assert result.persistable is True
    launch = resolve_launch_workspace(preset=result.preset)
    assert launch.mode is WorkspaceMode.CLEAN_START
    assert launch.source_node_id is None
    assert launch.browser_materialized is False
    assert launch.live_kit_materialized is False
    assert launch.calm_canvas_visible is True
    assert launch.harmonic_visible is False


def test_corrupt_startup_preset_fails_closed_to_clean_start(tmp_path: Path):
    path = workbench_startup_preset_file(state_dir=tmp_path)
    path.write_text("{not-json", encoding="utf-8")
    result = load_startup_preset(state_dir=tmp_path)
    assert result.preset is None
    assert result.persistable is False
    launch = resolve_launch_workspace(preset=result.preset)
    assert launch.mode is WorkspaceMode.CLEAN_START


def test_invalid_startup_preset_version_fails_closed(tmp_path: Path):
    path = workbench_startup_preset_file(state_dir=tmp_path)
    path.write_text(
        json.dumps({"schema_version": 999, "startup_source_node_id": "root:1"}),
        encoding="utf-8",
    )
    result = load_startup_preset(state_dir=tmp_path)
    assert result.preset is None
    assert result.persistable is False
    assert resolve_launch_workspace(preset=result.preset).mode is WorkspaceMode.CLEAN_START


def test_startup_preset_missing_source_fails_closed(tmp_path: Path):
    save_startup_preset_for_tests(
        {
            "schema_version": SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
            "startup_source_node_id": "root:missing",
            "density_mode": "compact_target_30dip",
            "motion_mode": "full",
        },
        state_dir=tmp_path,
    )
    result = load_startup_preset(state_dir=tmp_path)
    assert result.preset is not None
    assert result.preset.startup_source_node_id == "root:missing"
    launch = resolve_launch_workspace(
        preset=result.preset,
        source_available=lambda _node_id: False,
    )
    assert launch.mode is WorkspaceMode.CLEAN_START
    assert launch.source_node_id is None


def test_startup_preset_with_available_source_overrides_clean_start(tmp_path: Path):
    save_startup_preset_for_tests(
        {
            "schema_version": SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
            "startup_source_node_id": "root:42",
            "density_mode": "compact_target_30dip",
            "motion_mode": "reduced",
            "panel_ratios": {"source_nav": 0.18, "browser": 0.57, "live_kit": 0.25},
        },
        state_dir=tmp_path,
    )
    result = load_startup_preset(state_dir=tmp_path)
    assert result.preset is not None
    launch = resolve_launch_workspace(
        preset=result.preset,
        source_available=lambda node_id: node_id == "root:42",
    )
    assert launch.mode is WorkspaceMode.ACTIVE_SOURCE
    assert launch.source_node_id == "root:42"
    assert launch.browser_materialized is True
    assert launch.live_kit_materialized is True
    assert launch.calm_canvas_visible is False
    assert launch.harmonic_visible is False


def test_last_folder_artifact_does_not_change_clean_start_resolve(tmp_path: Path):
    from src.workbench_controller import save_workbench_last_folder

    (tmp_path / "audio").mkdir()
    folder = tmp_path / "audio"
    # last-folder is Tk legacy; Clean Start resolver must ignore it.
    save_workbench_last_folder(folder, state_dir=tmp_path)
    launch = resolve_launch_workspace(preset=None)
    assert launch.mode is WorkspaceMode.CLEAN_START


# --- Runtime composition ----------------------------------------------------


def test_dispatch_selection_does_not_synthesise_sample_selection(
    monkeypatch: pytest.MonkeyPatch,
):
    from src import workbench_qml_runtime as runtime_mod
    from src.workbench_qml_runtime import Screen1QmlRuntimeComposition

    nav = _FakeNav()
    tree = WorkbenchLibraryTreeState(nav)
    composition = Screen1QmlRuntimeComposition(tree_state=tree)
    monkeypatch.setattr(
        runtime_mod,
        "load_cached_folder_rows",
        lambda _folder: [_row("a"), _row("b")],
    )
    state = composition.dispatch_selection(
        _intent(nav.root, nav.resolve_scope("root:1"))
    )
    assert state.error is None
    assert len(state.rows) == 2
    assert state.selected_index == -1
    assert composition.has_active_source is True
    assert composition.browser_materialized is True
    assert composition.live_kit_materialized is True
    assert composition.audition_dispatches == []


def test_clear_no_scope_is_clean_start_materialization():
    from src.workbench_qml_runtime import Screen1QmlRuntimeComposition

    composition = Screen1QmlRuntimeComposition(tree_state=WorkbenchLibraryTreeState(_FakeNav()))
    composition.clear_no_scope()
    assert composition.has_active_source is False
    assert composition.browser_materialized is False
    assert composition.live_kit_materialized is False
    assert composition.browser_state.selected_index == -1
    assert composition.browser_state.rows == ()


def test_clean_start_does_not_delete_registered_sources(tmp_path: Path):
    from src.workbench_controller import get_workbench_library_folders
    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml_runtime import Screen1QmlRuntimeComposition

    _root, db = _register_analyzed_root(tmp_path)
    before = get_workbench_library_folders(library_db_path=db)
    assert before
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    composition.clear_no_scope()
    after = get_workbench_library_folders(library_db_path=db)
    assert [folder.id for folder in after] == [folder.id for folder in before]
    assert composition.has_active_source is False


class _FakeNav:
    def __init__(self) -> None:
        self.root = LibraryNode(
            "root:1",
            LibraryNodeKind.REGISTERED_ROOT,
            "Samples",
            SAMPLE_SOURCES,
            True,
            True,
            LibraryAvailability.AVAILABLE,
            folder_id=1,
        )
        self._top = (
            LibraryNode(
                SAMPLE_SOURCES,
                LibraryNodeKind.SAMPLE_SOURCES,
                "Sample Sources",
                None,
                False,
                True,
                LibraryAvailability.AVAILABLE,
            ),
            self.root,
        )

    @property
    def library_db_path(self):
        return None

    def top_level_nodes(self):
        return self._top

    def children(self, node_id: str):
        if node_id == SAMPLE_SOURCES:
            return (self.root,)
        return ()

    def resolve_scope(self, node_id: str):
        if node_id == "root:1":
            return LibraryScope(
                LibraryScopeKind.ROOT,
                folder_id=1,
                folder_path="C:/samples",
            )
        return None


# --- QML production shell ---------------------------------------------------


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_qml_launch_with_sources_stays_clean_start(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import (
        LibraryNodeKind,
        WorkbenchLibraryNavigation,
    )
    from src.workbench_qml import (
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
        _qml_engine,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState

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
        library_tree=composition.library_tree,
    )
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        app.processEvents()
        library_model = engine._screen1_library_model
        adapter = engine._screen1_interaction_adapter
        assert library_model.state.selected_node_id is None
        assert composition.has_active_source is False
        assert composition.browser_materialized is False
        assert composition.live_kit_materialized is False
        assert view_model.browser_rows == ()
        assert view_model.selected_browser_index == -1
        assert adapter.harmonic_match_open is False
        assert adapter.preview_active is False
        library_model.state.fetch_children(SAMPLE_SOURCES)
        roots = [
            node
            for node in navigation.children(SAMPLE_SOURCES)
            if node.kind is LibraryNodeKind.REGISTERED_ROOT
        ]
        assert roots
        calm = window.findChild(QQuickItem, "calmCanvas")
        browser = window.findChild(QQuickItem, "browserPane")
        live_kit = window.findChild(QQuickItem, "liveKitPane")
        assert calm is not None and calm.isVisible()
        assert browser is not None and not browser.isVisible()
        assert live_kit is not None and not live_kit.isVisible()
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_qml_source_select_materialises_browser_without_selection_or_audition(
    tmp_path: Path,
):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import (
        LibraryNodeKind,
        WorkbenchLibraryNavigation,
    )
    from src.workbench_qml import (
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
        _qml_engine,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState

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
        library_tree=composition.library_tree,
    )
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        library_model = engine._screen1_library_model
        library_bridge = engine._screen1_library_bridge
        adapter = engine._screen1_interaction_adapter
        library_model.state.fetch_children(SAMPLE_SOURCES)
        root_node = next(
            node
            for node in navigation.children(SAMPLE_SOURCES)
            if node.kind is LibraryNodeKind.REGISTERED_ROOT
        )
        library_bridge.selectLibraryNode(root_node.node_id)
        app.processEvents()
        assert composition.has_active_source is True
        assert composition.browser_materialized is True
        assert composition.live_kit_materialized is True
        assert view_model.browser_rows
        assert view_model.selected_browser_index == -1
        assert adapter.harmonic_match_open is False
        assert adapter.preview_active is False
        assert composition.audition_dispatches == []
        calm = window.findChild(QQuickItem, "calmCanvas")
        browser = window.findChild(QQuickItem, "browserPane")
        live_kit = window.findChild(QQuickItem, "liveKitPane")
        assert calm is not None and not calm.isVisible()
        assert browser is not None and browser.isVisible()
        assert live_kit is not None and live_kit.isVisible()
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_qml_add_source_may_activate_new_source(tmp_path: Path):
    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import (
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
        _qml_engine,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from tests.audio_fixtures import write_kick_transient_wav

    db = tmp_path / "library.db"
    source = tmp_path / "new-source"
    source.mkdir()
    write_kick_transient_wav(source / "hit.wav", bpm=120.0, duration_sec=1.0)
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
        library_tree=composition.library_tree,
    )
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        library_bridge = engine._screen1_library_bridge
        assert composition.has_active_source is False
        library_bridge.registerSourceUrl(str(source))
        app.processEvents()
        assert composition.has_active_source is True
        assert composition.browser_materialized is True
        assert library_bridge.selectedLibraryNodeId.startswith("root:")
        assert view_model.selected_browser_index == -1
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_qml_does_not_restore_prior_session_selection_harmony_or_preview(
    tmp_path: Path, isolated_workbench_state_dir: Path
):
    from src.workbench_controller import save_workbench_last_folder
    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import (
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
        _qml_engine,
        apply_clean_start_launch,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    root, db = _register_analyzed_root(tmp_path)
    save_workbench_last_folder(root, state_dir=isolated_workbench_state_dir)
    workbench_startup_preset_file(state_dir=isolated_workbench_state_dir).write_text(
        '{"schema_version":1,"startup_source_node_id":',
        encoding="utf-8",
    )
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    view_model = Screen1QmlViewModel(
        state_id="screen1-harmonic-4panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=3,
        harmony_rows=(),
        live_kit_groups=(),
        library_tree=composition.library_tree,
    )
    apply_clean_start_launch(
        view_model, composition, state_dir=isolated_workbench_state_dir
    )
    assert view_model.selected_browser_index == -1
    assert composition.has_active_source is False

    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        adapter = engine._screen1_interaction_adapter
        assert adapter.harmonic_match_open is False
        assert adapter.preview_active is False
        assert view_model.browser_rows == ()
        assert view_model.selected_browser_index == -1
    finally:
        _shutdown_engine(app, engine, window)


def test_qml_source_declares_calm_canvas_and_progressive_disclosure():
    from src.workbench_qml import QML_SOURCE

    assert 'objectName: "calmCanvas"' in QML_SOURCE
    assert 'objectName: "libraryRevealAffordance"' in QML_SOURCE
    assert "revealLibrary()" in QML_SOURCE
    assert "libraryRevealed" in QML_SOURCE
    assert "hasActiveSource" in QML_SOURCE
    assert "browserPane" in QML_SOURCE
    assert "liveKitPane" in QML_SOURCE
    assert 'objectName: "calmCanvasAddSource"' in QML_SOURCE
    assert 'objectName: "calmCanvasAddSourceLabel"' in QML_SOURCE
    assert 'text: "+"' in QML_SOURCE
    assert 'text: "Add Source"' in QML_SOURCE
    assert 'Accessible.name: "Add Source"' in QML_SOURCE
    assert 'ToolTip.text: "Add Source"' in QML_SOURCE
    assert "Add Source to begin." not in QML_SOURCE
    assert "Select a Source, or Add Source to begin." not in QML_SOURCE
    assert "onClicked: addSourceDialog.open()" in QML_SOURCE
    # Calm Canvas primary copy is Add Source — brand headline stays in header only.
    calm_block = QML_SOURCE.split('objectName: "calmCanvas"', 1)[1].split(
        'objectName: "browserPane"', 1
    )[0]
    assert 'text: "Sample Brain"' not in calm_block
    assert 'text: "Add Source"' in calm_block
    assert "implicitWidth: 96" in calm_block
    assert "font.pixelSize: 64" in calm_block
    label_idx = calm_block.index('objectName: "calmCanvasAddSourceLabel"')
    plus_idx = calm_block.index('objectName: "calmCanvasAddSource"')
    assert label_idx < plus_idx
    assert "font.pixelSize: 15" in calm_block[label_idx:plus_idx]
    assert "font.weight: Font.Light" in calm_block
    assert "font.bold: true" not in calm_block.split('objectName: "calmCanvasAddSource"', 1)[1].split("background:", 1)[0]


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_qml_clean_start_add_source_cta_is_primary_focus(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import (
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
        _qml_engine,
        apply_clean_start_launch,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState

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
        library_tree=composition.library_tree,
    )
    apply_clean_start_launch(view_model, composition)
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        app.processEvents()
        label = window.findChild(QQuickItem, "calmCanvasAddSourceLabel")
        add_source = window.findChild(QQuickItem, "calmCanvasAddSource")
        affordance = window.findChild(QQuickItem, "libraryRevealAffordance")
        assert label is not None and label.isVisible()
        assert str(label.property("text")) == "Add Source"
        assert add_source is not None and add_source.isVisible()
        assert str(add_source.property("text")) == "+"
        assert add_source.width() >= 88
        assert add_source.height() >= 88
        assert affordance is not None and affordance.isVisible()
        assert add_source.width() > affordance.width() * 2
        # Label sits above the plus.
        assert label.y() + label.height() <= add_source.y()
        accessible = add_source.property("Accessible.name")
        if accessible is None:
            from src.workbench_qml import QML_SOURCE

            assert 'Accessible.name: "Add Source"' in QML_SOURCE
        else:
            assert str(accessible) == "Add Source"
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_qml_clean_start_library_collapsed_with_reveal_affordance(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import (
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
        _qml_engine,
        apply_clean_start_launch,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState

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
        library_tree=composition.library_tree,
    )
    apply_clean_start_launch(view_model, composition)
    assert view_model.library_revealed is False
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        app.processEvents()
        layout = engine._screen1_layout_model
        calm = window.findChild(QQuickItem, "calmCanvas")
        library = window.findChild(QQuickItem, "libraryPane")
        affordance = window.findChild(QQuickItem, "libraryRevealAffordance")
        add_source = window.findChild(QQuickItem, "calmCanvasAddSource")
        browser = window.findChild(QQuickItem, "browserPane")
        live_kit = window.findChild(QQuickItem, "liveKitPane")
        assert calm is not None and calm.isVisible()
        assert add_source is not None and add_source.isVisible()
        assert affordance is not None and affordance.isVisible()
        assert browser is not None and not browser.isVisible()
        assert live_kit is not None and not live_kit.isVisible()
        assert layout.libraryWidth == 0.0
        if library is not None:
            assert not library.isVisible() or library.width() == 0
        assert composition.has_active_source is False
        assert view_model.library_revealed is False
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_qml_reveal_opens_library_without_source_audition_or_harmony(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_layout_solver import CANONICAL_DEFAULT_RATIOS
    from src.workbench_qml import (
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
        _qml_engine,
        apply_clean_start_launch,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState

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
        library_tree=composition.library_tree,
    )
    apply_clean_start_launch(view_model, composition)
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        app.processEvents()
        bridge = engine._screen1_interaction_bridge
        adapter = engine._screen1_interaction_adapter
        layout = engine._screen1_layout_model
        ratios_before = dict(layout.current_ratios())
        assert ratios_before == dict(CANONICAL_DEFAULT_RATIOS)
        bridge.revealLibrary()
        app.processEvents()
        assert view_model.library_revealed is True
        assert composition.has_active_source is False
        assert view_model.selected_browser_index == -1
        assert view_model.browser_rows == ()
        assert adapter.preview_active is False
        assert adapter.harmonic_match_open is False
        assert composition.audition_dispatches == []
        assert view_model.harmony_rows == ()
        assert dict(layout.current_ratios()) == ratios_before
        assert layout.libraryWidth == 300.0
        calm = window.findChild(QQuickItem, "calmCanvas")
        library = window.findChild(QQuickItem, "libraryPane")
        affordance = window.findChild(QQuickItem, "libraryRevealAffordance")
        browser = window.findChild(QQuickItem, "browserPane")
        assert calm is not None and calm.isVisible()
        assert library is not None and library.isVisible()
        assert affordance is not None and not affordance.isVisible()
        assert browser is not None and not browser.isVisible()
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_qml_restart_resets_reveal_to_collapsed(tmp_path: Path):
    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import (
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
        apply_clean_start_launch,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState

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
        library_tree=composition.library_tree,
    )
    apply_clean_start_launch(view_model, composition)
    view_model.reveal_library()
    assert view_model.library_revealed is True
    apply_clean_start_launch(view_model, composition)
    assert view_model.library_revealed is False
    assert composition.has_active_source is False


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_qml_source_select_after_reveal_uses_elastic_not_reveal_flag(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import (
        LibraryNodeKind,
        WorkbenchLibraryNavigation,
    )
    from src.workbench_qml import (
        Screen1QmlRuntimeComposition,
        Screen1QmlViewModel,
        _qml_engine,
        apply_clean_start_launch,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState

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
        library_tree=composition.library_tree,
    )
    apply_clean_start_launch(view_model, composition)
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        library_model = engine._screen1_library_model
        library_bridge = engine._screen1_library_bridge
        bridge = engine._screen1_interaction_bridge
        layout = engine._screen1_layout_model
        bridge.revealLibrary()
        app.processEvents()
        library_model.state.fetch_children(SAMPLE_SOURCES)
        root_node = next(
            node
            for node in navigation.children(SAMPLE_SOURCES)
            if node.kind is LibraryNodeKind.REGISTERED_ROOT
        )
        library_bridge.selectLibraryNode(root_node.node_id)
        app.processEvents()
        assert composition.has_active_source is True
        assert layout.libraryWidth > 0
        assert layout.browserWidth > 0
        assert layout.liveKitWidth > 0
        # Reveal flag is not a second Active-Source authority.
        calm = window.findChild(QQuickItem, "calmCanvas")
        browser = window.findChild(QQuickItem, "browserPane")
        assert calm is not None and not calm.isVisible()
        assert browser is not None and browser.isVisible()
    finally:
        _shutdown_engine(app, engine, window)


# --- Visual acceptance product apply ----------------------------------------


def test_apply_v2_clean_start_and_active_source_projection():
    from src.workbench_qml import Screen1QmlInteractionAdapter, Screen1QmlViewModel
    from src.workbench_qml_spike import apply_screen1_visual_state_v2

    fixture = build_screen1_visual_fixture_v2()
    clean = resolve_screen1_visual_state_v2(fixture, "screen1-clean-start")
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    adapter = Screen1QmlInteractionAdapter(view_model=view_model)
    apply_screen1_visual_state_v2(view_model, adapter, fixture, clean)
    assert view_model.has_active_source is False
    assert view_model.library_revealed is False
    assert view_model.calm_canvas_visible is True
    assert view_model.browser_materialized is False
    assert view_model.live_kit_materialized is False
    assert view_model.selected_browser_index == -1
    assert adapter.harmonic_match_open is False
    assert adapter.preview_active is False

    active = resolve_screen1_visual_state_v2(fixture, "screen1-active-source")
    apply_screen1_visual_state_v2(view_model, adapter, fixture, active)
    assert view_model.has_active_source is True
    assert view_model.library_revealed is False
    assert view_model.calm_canvas_visible is False
    assert view_model.browser_materialized is True
    assert view_model.live_kit_materialized is True
    assert view_model.browser_rows
    # Visual fixture may declare a row for capture; product launch still uses -1
    # unless the acceptance state explicitly sets an index.
    assert view_model.selected_browser_index == (
        -1 if active.selected_browser_index is None else active.selected_browser_index
    )
    assert adapter.harmonic_match_open is False
    assert adapter.preview_active is False


def _shutdown_engine(app, engine, window) -> None:
    window.close()
    app.processEvents()
    timer = getattr(engine, "_screen1_waveform_timer", None)
    if timer is not None:
        timer.stop()
    loader = getattr(engine, "_screen1_waveform_loader", None)
    if loader is not None:
        loader.close()
    coordinator = getattr(engine, "_screen1_analysis_coordinator", None)
    if coordinator is not None:
        coordinator.close()
