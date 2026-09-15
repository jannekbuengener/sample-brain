from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest

import src.workbench_library_navigation as navigation_module
from src.workbench_catalog import DEFAULT_CATALOG_LOAD_LIMIT
from src.workbench_controller import WorkbenchRow
from src.workbench_library import (
    create_playlist,
    init_workbench_library,
    register_library_folder,
    upsert_sample,
    workbench_library_db_path,
)
from src.workbench_library_navigation import (
    LibraryAvailability,
    LibraryNodeKind,
    LibraryScopeKind,
    WorkbenchLibraryNavigation,
)


@pytest.fixture
def library_db(tmp_path: Path) -> Path:
    db_path = workbench_library_db_path(state_dir=tmp_path / "state")
    init_workbench_library(db_path)
    return db_path


def _cache_row(
    folder_id: int,
    root: Path,
    relative_path: str,
    *,
    db_path: Path,
) -> None:
    sample_path = root / "cached-row.wav"
    row = WorkbenchRow(
        display_name="cached row",
        relative_path=relative_path,
        path=str(sample_path),
        bpm=120.0,
        key="C",
        key_conf=0.8,
        loudness=-10.0,
        brightness=100.0,
        sample_class="oneshot",
        pred_type="Kick",
        status="ok",
    )
    upsert_sample(folder_id, row, size_bytes=1, mtime_ns=1, db_path=db_path)


def _node(nodes, node_id: str):
    return next(node for node in nodes if node.node_id == node_id)


def test_navigation_emits_stable_taxonomy_ids_and_typed_scopes(
    library_db: Path, tmp_path: Path
) -> None:
    root = tmp_path / "sample-root"
    (root / "Drums" / "Kicks").mkdir(parents=True)
    folder_id = register_library_folder(root, db_path=library_db)
    playlist = create_playlist("Song A", db_path=library_db)
    navigation = WorkbenchLibraryNavigation(library_db_path=library_db)

    top_level = navigation.top_level_nodes()
    assert [(node.node_id, node.kind) for node in top_level] == [
        ("container:sample-sources", LibraryNodeKind.SAMPLE_SOURCES),
        ("scope:all-library", LibraryNodeKind.ALL_SAMPLES),
        ("scope:catalog-readonly", LibraryNodeKind.CATALOG),
        ("container:collections", LibraryNodeKind.COLLECTIONS),
    ]

    source_children = navigation.children("container:sample-sources")
    root_node = _node(source_children, f"root:{folder_id}")
    assert root_node.kind is LibraryNodeKind.REGISTERED_ROOT
    assert root_node.label == "sample-root"
    assert root_node.selectable and root_node.expandable
    assert root_node.availability is LibraryAvailability.AVAILABLE
    assert source_children[-1].node_id == "action:add-source"
    assert not source_children[-1].selectable

    # TEST_CONTRACT_FIX: the frozen literal encoded ``Drums`` instead of the
    # canonical ``normcase(relative_path)`` value. Product behavior is unchanged.
    canonical_drums = os.path.normcase("Drums")
    encoded_drums = base64.urlsafe_b64encode(canonical_drums.encode("utf-8")).decode(
        "ascii"
    ).rstrip("=")
    subfolder = _node(
        navigation.children(root_node.node_id),
        f"folder:{folder_id}:{encoded_drums}",
    )
    assert subfolder.kind is LibraryNodeKind.SUBFOLDER
    assert subfolder.label == "Drums"
    assert subfolder.parent_id == root_node.node_id

    root_scope = navigation.resolve_scope(root_node.node_id)
    assert root_scope is not None
    assert root_scope.kind is LibraryScopeKind.ROOT
    assert root_scope.folder_id == folder_id
    assert root_scope.folder_path == str(root.resolve())

    subfolder_scope = navigation.resolve_scope(subfolder.node_id)
    assert subfolder_scope is not None
    assert subfolder_scope.kind is LibraryScopeKind.SUBFOLDER
    assert subfolder_scope.folder_id == folder_id
    assert subfolder_scope.relative_path == canonical_drums

    all_scope = navigation.resolve_scope("scope:all-library")
    assert all_scope is not None and all_scope.kind is LibraryScopeKind.ALL_SAMPLES
    catalog_scope = navigation.resolve_scope("scope:catalog-readonly")
    assert catalog_scope is not None and catalog_scope.kind is LibraryScopeKind.CATALOG
    assert catalog_scope.catalog_limit == DEFAULT_CATALOG_LOAD_LIMIT

    collection = _node(navigation.children("container:collections"), f"collection:{playlist.id}")
    collection_scope = navigation.resolve_scope(collection.node_id)
    assert collection_scope is not None
    assert collection_scope.kind is LibraryScopeKind.COLLECTION
    assert collection_scope.playlist_id == playlist.id
    assert collection_scope.playlist_name == "Song A"

    assert navigation.resolve_scope("container:sample-sources") is None
    assert navigation.resolve_scope("action:add-source") is None
    assert navigation.resolve_scope("collection:99999") is None


def test_duplicate_root_labels_use_shortest_unique_parent_suffix(
    library_db: Path, tmp_path: Path
) -> None:
    first = tmp_path / "one" / "Samples"
    second = tmp_path / "two" / "Samples"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    first_id = register_library_folder(first, db_path=library_db)
    second_id = register_library_folder(second, db_path=library_db)

    nodes = WorkbenchLibraryNavigation(library_db_path=library_db).children(
        "container:sample-sources"
    )
    assert _node(nodes, f"root:{first_id}").label == "Samples — one"
    assert _node(nodes, f"root:{second_id}").label == "Samples — two"
    assert str(first.resolve()) not in {node.label for node in nodes}


@pytest.mark.parametrize("name", ["tmp", "pytest", "worktree"])
def test_temp_like_roots_remain_registered_sources(
    library_db: Path, tmp_path: Path, name: str
) -> None:
    root = tmp_path / name
    root.mkdir()
    folder_id = register_library_folder(root, db_path=library_db)

    node = _node(
        WorkbenchLibraryNavigation(library_db_path=library_db).children(
            "container:sample-sources"
        ),
        f"root:{folder_id}",
    )
    assert node.label == name
    assert node.selectable


def test_favorites_are_not_emitted_without_a_persistent_contract(
    library_db: Path,
) -> None:
    navigation = WorkbenchLibraryNavigation(library_db_path=library_db)
    node_ids = [node.node_id for node in navigation.top_level_nodes()]
    node_ids.extend(node.node_id for node in navigation.children("container:sample-sources"))
    node_ids.extend(node.node_id for node in navigation.children("container:collections"))

    assert not any("favorite" in node_id.lower() for node_id in node_ids)


def test_offline_root_stays_visible_cache_selectable_and_not_expandable(
    library_db: Path, tmp_path: Path
) -> None:
    missing_root = tmp_path / "offline-library"
    folder_id = register_library_folder(missing_root, db_path=library_db)
    _cache_row(folder_id, missing_root, "Drums\\kick.wav", db_path=library_db)
    navigation = WorkbenchLibraryNavigation(library_db_path=library_db)

    root = _node(navigation.children("container:sample-sources"), f"root:{folder_id}")
    assert root.availability is LibraryAvailability.OFFLINE
    assert root.selectable and not root.expandable
    assert navigation.children(root.node_id) == ()
    scope = navigation.resolve_scope(root.node_id)
    assert scope is not None and scope.folder_id == folder_id


def test_expansion_returns_only_direct_non_symlink_children_without_side_effects(
    library_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "source"
    (root / "direct").mkdir(parents=True)
    (root / "nested" / "child").mkdir(parents=True)
    (root / "audio.wav").write_bytes(b"not audio")
    link_target = root / "link-target"
    link_target.mkdir()
    link = root / "linked"
    try:
        link.symlink_to(link_target, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this host")
    folder_id = register_library_folder(root, db_path=library_db)
    navigation = WorkbenchLibraryNavigation(library_db_path=library_db)

    scandir_calls: list[Path] = []
    original_scandir = navigation_module.os.scandir

    def direct_scandir(path):
        scandir_calls.append(Path(path))
        return original_scandir(path)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("expansion must not invoke this operation")

    monkeypatch.setattr(navigation_module.os, "scandir", direct_scandir)
    monkeypatch.setattr(navigation_module.os, "walk", forbidden)
    monkeypatch.setattr(navigation_module, "load_catalog_samples", forbidden, raising=False)
    monkeypatch.setattr(navigation_module, "analyze_folder_for_workbench", forbidden, raising=False)
    monkeypatch.setattr(navigation_module, "safe_load", forbidden, raising=False)

    children = navigation.children(f"root:{folder_id}")
    assert [child.label for child in children] == ["direct", "link-target", "nested"]
    assert scandir_calls == [root]


def test_expansion_reports_a_path_free_error_status(
    library_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    folder_id = register_library_folder(root, db_path=library_db)
    navigation = WorkbenchLibraryNavigation(library_db_path=library_db)

    def unreadable(_path):
        raise OSError("private path must not leak")

    monkeypatch.setattr(navigation_module.os, "scandir", unreadable)
    status_nodes = navigation.children(f"root:{folder_id}")

    assert len(status_nodes) == 1
    status = status_nodes[0]
    assert status.kind is LibraryNodeKind.STATUS
    assert status.availability is LibraryAvailability.ERROR
    assert not status.selectable and not status.expandable
    assert str(root) not in status.label
