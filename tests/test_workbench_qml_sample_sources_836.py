"""#836 Sample Sources expand / refresh / browser-scope regressions.

Frozen before implementation. Protects the production launch order where
``apply_clean_start_launch`` prefetches Sample Sources into Python tree state
before ``create_qt_library_tree_model`` constructs the Qt item index.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from src.workbench_library import init_workbench_library, register_library_folder
from src.workbench_library_navigation import (
    LibraryAvailability,
    LibraryNodeKind,
    WorkbenchLibraryNavigation,
)
from src.workbench_qml_library import WorkbenchLibraryTreeState
from src.workbench_qml_runtime import Screen1QmlRuntimeComposition

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None
SAMPLE_SOURCES = "container:sample-sources"


def _write_synth_wav(path: Path) -> None:
    from tests.audio_fixtures import write_kick_transient_wav

    write_kick_transient_wav(path, bpm=120.0, duration_sec=0.4)


def _isolated_db(tmp_path: Path) -> Path:
    db = tmp_path / "library.db"
    init_workbench_library(db)
    return db


def _source_tree(tmp_path: Path, name: str, *, with_child: bool = True) -> Path:
    root = tmp_path / name
    if with_child:
        (root / "Child").mkdir(parents=True)
    else:
        root.mkdir(parents=True)
    return root


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_qt_model_hydrates_sources_prefetched_before_construction(tmp_path: Path) -> None:
    """Production launch prefetches Sources before the Qt model exists."""
    from PySide6.QtCore import QCoreApplication

    from src.workbench_qml import Screen1QmlViewModel, apply_clean_start_launch
    from src.workbench_qml_library import create_qt_library_tree_model

    app = QCoreApplication.instance() or QCoreApplication([])
    del app

    db = _isolated_db(tmp_path)
    source = _source_tree(tmp_path, "source_a")
    register_library_folder(source, db_path=db)

    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    tree = WorkbenchLibraryTreeState(navigation)
    composition = Screen1QmlRuntimeComposition(library_db_path=db, tree_state=tree)
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    view_model.library_tree = tree
    apply_clean_start_launch(view_model, composition, state_dir=tmp_path / "state")

    assert tree.is_loaded(SAMPLE_SOURCES)
    assert [node.node_id for node in tree.visible_children(SAMPLE_SOURCES)] == ["root:1"]

    model = create_qt_library_tree_model(tree)
    sample_index = model.index(0, 0)
    assert model.rowCount(sample_index) == 1
    assert model.hasChildren(sample_index) is True
    assert model.canFetchMore(sample_index) is False
    root_index = model.index(0, 0, sample_index)
    assert model.data(root_index, model.NodeIdRole) == "root:1"
    assert model.data(root_index, model.DisplayRole) == source.name
    assert model.data(root_index, model.ExpandableRole) is True


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_add_source_replace_branch_shows_new_root_without_restart(tmp_path: Path) -> None:
    from PySide6.QtCore import QCoreApplication

    from src.workbench_qml_library import create_qt_library_tree_model

    app = QCoreApplication.instance() or QCoreApplication([])
    del app

    db = _isolated_db(tmp_path)
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    tree = WorkbenchLibraryTreeState(navigation)
    # Match empty-library launch: prefetch empty Sample Sources before model.
    tree.fetch_children(SAMPLE_SOURCES)
    model = create_qt_library_tree_model(tree)
    sample_index = model.index(0, 0)
    assert model.rowCount(sample_index) == 0

    composition = Screen1QmlRuntimeComposition(library_db_path=db, tree_state=tree)
    source = _source_tree(tmp_path, "added_source")
    registration = composition.register_source_for_analysis(source)
    assert registration is not None
    assert model.replaceBranch(SAMPLE_SOURCES) is True

    assert model.rowCount(sample_index) == 1
    root_index = model.index(0, 0, sample_index)
    assert model.data(root_index, model.NodeIdRole) == f"root:{registration.folder_id}"
    assert model.hasChildren(root_index) is True
    model.fetchMore(root_index)
    assert model.rowCount(root_index) == 1
    assert model.data(model.index(0, 0, root_index), model.DisplayRole) == "Child"


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_restart_composition_shows_persisted_sources(tmp_path: Path) -> None:
    from PySide6.QtCore import QCoreApplication

    from src.workbench_qml import Screen1QmlViewModel, apply_clean_start_launch
    from src.workbench_qml_library import create_qt_library_tree_model

    app = QCoreApplication.instance() or QCoreApplication([])
    del app

    db = _isolated_db(tmp_path)
    source_a = _source_tree(tmp_path, "alpha")
    source_b = _source_tree(tmp_path, "beta")
    register_library_folder(source_a, db_path=db)
    register_library_folder(source_b, db_path=db)

    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    tree = WorkbenchLibraryTreeState(navigation)
    composition = Screen1QmlRuntimeComposition(library_db_path=db, tree_state=tree)
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    view_model.library_tree = tree
    apply_clean_start_launch(view_model, composition, state_dir=tmp_path / "state")
    model = create_qt_library_tree_model(tree)
    sample_index = model.index(0, 0)
    labels = {
        model.data(model.index(i, 0, sample_index), model.DisplayRole)
        for i in range(model.rowCount(sample_index))
    }
    assert labels == {"alpha", "beta"}


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_source_switch_clears_stale_browser_rows_and_selection(tmp_path: Path) -> None:
    from PySide6.QtCore import QCoreApplication

    from src.workbench_controller import analyze_folder_for_workbench
    from src.workbench_qml_library import create_qt_library_tree_model

    app = QCoreApplication.instance() or QCoreApplication([])
    del app

    db = _isolated_db(tmp_path)
    source_a = tmp_path / "scope_a"
    source_b = tmp_path / "scope_b"
    source_a.mkdir()
    source_b.mkdir()
    _write_synth_wav(source_a / "kick_a.wav")
    _write_synth_wav(source_b / "kick_b.wav")
    analyze_folder_for_workbench(source_a, library_db_path=db)
    analyze_folder_for_workbench(source_b, library_db_path=db)

    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    tree = WorkbenchLibraryTreeState(navigation)
    tree.fetch_children(SAMPLE_SOURCES)
    model = create_qt_library_tree_model(tree)
    composition = Screen1QmlRuntimeComposition(library_db_path=db, tree_state=tree)

    roots = {
        node.label: node.node_id
        for node in tree.visible_children(SAMPLE_SOURCES)
        if node.kind is LibraryNodeKind.REGISTERED_ROOT
    }
    assert set(roots) == {"scope_a", "scope_b"}

    assert model.selectNode(roots["scope_a"]) is True
    composition.dispatch_selection(tree.selection_intent)
    assert len(composition.browser_state.rows) >= 1
    assert all("scope_a" in row.path.replace("\\", "/") for row in composition.browser_state.rows)
    # Simulate a prior Browser sample selection that must not survive a source switch.
    composition.browser_state = type(composition.browser_state)(
        rows=composition.browser_state.rows,
        selected_index=0,
        browser_context=composition.browser_state.browser_context,
        scope=composition.browser_state.scope,
        error=None,
    )

    assert model.selectNode(roots["scope_b"]) is True
    composition.dispatch_selection(tree.selection_intent)
    assert composition.browser_state.selected_index == -1
    assert composition.browser_state.rows
    assert all("scope_b" in row.path.replace("\\", "/") for row in composition.browser_state.rows)
    assert not any("scope_a" in row.path.replace("\\", "/") for row in composition.browser_state.rows)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_empty_offline_and_error_source_states_are_honest(tmp_path: Path) -> None:
    from PySide6.QtCore import QCoreApplication

    from src.workbench_qml_library import create_qt_library_tree_model

    app = QCoreApplication.instance() or QCoreApplication([])
    del app

    db = _isolated_db(tmp_path)
    empty = _source_tree(tmp_path, "empty_source", with_child=False)
    missing = tmp_path / "missing_source"
    missing.mkdir()
    register_library_folder(empty, db_path=db)
    register_library_folder(missing, db_path=db)
    missing.rmdir()

    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    tree = WorkbenchLibraryTreeState(navigation)
    tree.fetch_children(SAMPLE_SOURCES)
    model = create_qt_library_tree_model(tree)
    composition = Screen1QmlRuntimeComposition(library_db_path=db, tree_state=tree)

    by_label = {node.label: node for node in tree.visible_children(SAMPLE_SOURCES)}
    assert by_label["empty_source"].availability is LibraryAvailability.AVAILABLE
    assert by_label["empty_source"].expandable is True
    assert by_label["missing_source"].availability is LibraryAvailability.OFFLINE
    assert by_label["missing_source"].expandable is False

    empty_id = by_label["empty_source"].node_id
    assert model.selectNode(empty_id) is True
    composition.dispatch_selection(tree.selection_intent)
    assert composition.browser_state.rows == ()
    assert composition.browser_state.error is None
    assert composition.browser_state.selected_index == -1

    offline_id = by_label["missing_source"].node_id
    offline_intent = tree.select(offline_id)
    assert offline_intent is not None
    assert offline_intent.scope.folder_id == by_label["missing_source"].folder_id
    # Offline roots are selectable but not expandable (no phantom branch).
    assert tree.expand(offline_id) is False

    sample_index = model.index(0, 0)
    empty_index = None
    for row in range(model.rowCount(sample_index)):
        idx = model.index(row, 0, sample_index)
        if model.data(idx, model.NodeIdRole) == empty_id:
            empty_index = idx
            break
    assert empty_index is not None
    model.fetchMore(empty_index)
    assert model.rowCount(empty_index) == 0
    assert model.canFetchMore(empty_index) is False
