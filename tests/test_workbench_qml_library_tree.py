from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

from src.workbench_library_navigation import (
    LibraryAvailability,
    LibraryNode,
    LibraryNodeKind,
    LibraryScope,
    LibraryScopeKind,
)


SAMPLE_SOURCES = "container:sample-sources"
COLLECTIONS = "container:collections"
ROOT_ID = "root:1"
OFFLINE_ROOT_ID = "root:2"
EMPTY_ROOT_ID = "root:3"
FOLDER_ID = "folder:1:RHJ1bXM"


class FakeNavigation:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_once_for: set[str] = set()
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
                COLLECTIONS,
                LibraryNodeKind.COLLECTIONS,
                "Collections",
                None,
                False,
                True,
                LibraryAvailability.AVAILABLE,
            ),
            LibraryNode(
                "scope:favorites",
                LibraryNodeKind.FAVORITES,
                "Favorites",
                None,
                True,
                False,
                LibraryAvailability.AVAILABLE,
            ),
            LibraryNode(
                "scope:recordings",
                LibraryNodeKind.RECORDINGS,
                "Recordings",
                None,
                True,
                False,
                LibraryAvailability.AVAILABLE,
            ),
        )
        self.root = LibraryNode(
            ROOT_ID,
            LibraryNodeKind.REGISTERED_ROOT,
            "Samples — one",
            SAMPLE_SOURCES,
            True,
            True,
            LibraryAvailability.AVAILABLE,
            folder_id=1,
        )
        self.offline_root = LibraryNode(
            OFFLINE_ROOT_ID,
            LibraryNodeKind.REGISTERED_ROOT,
            "Samples — two",
            SAMPLE_SOURCES,
            True,
            False,
            LibraryAvailability.OFFLINE,
            folder_id=2,
        )
        self.empty_root = LibraryNode(
            EMPTY_ROOT_ID,
            LibraryNodeKind.REGISTERED_ROOT,
            "Empty",
            SAMPLE_SOURCES,
            True,
            True,
            LibraryAvailability.AVAILABLE,
            folder_id=3,
        )
        self.children_by_parent: dict[str, tuple[LibraryNode, ...]] = {
            SAMPLE_SOURCES: (
                self.root,
                self.offline_root,
                self.empty_root,
            ),
            ROOT_ID: (
                LibraryNode(
                    FOLDER_ID,
                    LibraryNodeKind.SUBFOLDER,
                    "Drums",
                    ROOT_ID,
                    True,
                    True,
                    LibraryAvailability.AVAILABLE,
                    folder_id=1,
                    relative_path="Drums",
                ),
                LibraryNode(
                    "folder:1:U2hhcmVk",
                    LibraryNodeKind.SUBFOLDER,
                    "Shared",
                    ROOT_ID,
                    True,
                    True,
                    LibraryAvailability.AVAILABLE,
                    folder_id=1,
                    relative_path="Shared",
                ),
            ),
            FOLDER_ID: (
                LibraryNode(
                    "folder:1:S2lja3M",
                    LibraryNodeKind.SUBFOLDER,
                    "Kicks",
                    FOLDER_ID,
                    True,
                    True,
                    LibraryAvailability.AVAILABLE,
                    folder_id=1,
                    relative_path="Drums/Kicks",
                ),
            ),
            EMPTY_ROOT_ID: (),
            COLLECTIONS: (
                LibraryNode(
                    "collection:7",
                    LibraryNodeKind.COLLECTION,
                    "Set A",
                    COLLECTIONS,
                    True,
                    False,
                    LibraryAvailability.AVAILABLE,
                    playlist_id=7,
                ),
            ),
        }
        self.scopes = {
            ROOT_ID: LibraryScope(LibraryScopeKind.ROOT, folder_id=1),
            OFFLINE_ROOT_ID: LibraryScope(LibraryScopeKind.ROOT, folder_id=2),
            EMPTY_ROOT_ID: LibraryScope(LibraryScopeKind.ROOT, folder_id=3),
            FOLDER_ID: LibraryScope(
                LibraryScopeKind.SUBFOLDER, folder_id=1, relative_path="Drums"
            ),
            "scope:all-library": LibraryScope(LibraryScopeKind.ALL_SAMPLES),
            "scope:catalog-readonly": LibraryScope(
                LibraryScopeKind.CATALOG, catalog_limit=17
            ),
            "scope:favorites": LibraryScope(LibraryScopeKind.FAVORITES),
            "scope:recordings": LibraryScope(LibraryScopeKind.RECORDINGS),
            "collection:7": LibraryScope(
                LibraryScopeKind.COLLECTION, playlist_id=7, playlist_name="Set A"
            ),
        }

    def top_level_nodes(self):
        return self.top

    def children(self, node_id: str):
        self.calls.append(node_id)
        if node_id in self.fail_once_for:
            self.fail_once_for.remove(node_id)
            return (
                LibraryNode(
                    "status:error:cm9vdDox",
                    LibraryNodeKind.STATUS,
                    "Folder could not be loaded",
                    node_id,
                    False,
                    False,
                    LibraryAvailability.ERROR,
                ),
            )
        return self.children_by_parent.get(node_id, ())

    def resolve_scope(self, node_id: str):
        self.calls.append(f"scope:{node_id}")
        return self.scopes.get(node_id)


def test_core_import_does_not_require_pyside6() -> None:
    repo_root = Path(__file__).parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import src.workbench_library_navigation; import src.workbench_qml_library; "
            "assert 'PySide6' not in sys.modules",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_qml_library_model_uses_exact_canonical_taxonomy_without_fake_surface() -> None:
    from src import workbench_qml

    source = workbench_qml.QML_SOURCE
    assert "TreeView" in source
    assert "libraryTreeModel" in source
    assert 'objectName: "libraryScopeBar"' in source
    assert 'objectName: "librarySourcesScopeButton"' in source
    assert 'objectName: "libraryAllSamplesScopeButton"' in source
    assert 'objectName: "libraryCatalogScopeButton"' not in source
    assert 'objectName: "libraryCollectionsScopeButton"' in source
    assert 'objectName: "libraryRecordingsScopeButton"' in source
    assert 'Accessible.name: "Sample Sources"' in source
    assert 'Accessible.name: "All Samples"' in source
    assert 'Accessible.name: "Catalog"' not in source
    assert 'Accessible.name: "Favorites"' in source
    assert 'Accessible.name: "Collections"' in source
    assert 'Accessible.name: "Recordings"' in source
    assert 'model.kind === "add_source"' not in source
    assert "libraryLabels" not in source
    assert 'objectName: "libraryFavoritesScopeButton"' in source
    for forbidden in ("My Kits", "Recently Added", "Splice", "User Library"):
        assert forbidden not in source
    # Favorites belongs in the scope bar, never as a Source-tree synthetic folder label.
    tree_block = source.split('objectName: "libraryTree"', 1)[1].split(
        "delegate: TreeViewDelegate", 1
    )[0]
    assert "Favorites" not in tree_block


def test_library_scope_bar_visual_polish_contract() -> None:
    """#771 Owner Visual repair: geometric icons, theme active state, tree retreat."""
    from src import workbench_qml

    source = workbench_qml.QML_SOURCE
    scope_block = source.split('objectName: "libraryScopeBar"', 1)[1].split(
        'Item { Layout.fillWidth: true }', 1
    )[0]
    tree_block = source.split('objectName: "libraryTree"', 1)[1].split(
        "delegate: TreeViewDelegate", 1
    )[0]
    collection_block = source.split('objectName: "libraryCollectionList"', 1)[1].split(
        'objectName: "libraryTree"', 1
    )[0]
    pane_block = source.split('id: libraryPane', 1)[1].split(
        'objectName: "elasticHandleAfterLibrary"', 1
    )[0]
    assert 'objectName: "libraryScopeBar"' not in pane_block
    footer_block = source.split("footer:", 1)[1].split("header:", 1)[0]
    assert pane_block.find('objectName: "libraryContentHost"') >= 0
    assert 'objectName: "libraryScopeBar"' in footer_block

    for glyph in ("⌁", "≡", "▣"):
        assert f'text: "{glyph}"' not in source

    # #880: active scope is accent underline + ink tint (no filled toolbar chip).
    assert "theme.actionActive" in scope_block
    assert "theme.hoverSurface" in scope_block
    assert "theme.selectionSurface" not in scope_block

    assert 'visible: libraryScopeBar.mode === "sources"' in tree_block
    assert 'enabled: libraryScopeBar.mode === "sources"' in tree_block
    assert 'activeFocusOnTab: libraryScopeBar.mode === "sources"' in tree_block
    assert 'visible: libraryScopeBar.mode !== "collections"' not in tree_block
    assert 'objectName: "libraryContentHost"' in source
    assert "Layout.fillHeight: true" in source.split(
        'objectName: "libraryContentHost"', 1
    )[1].split('objectName: "libraryCollectionList"', 1)[0]
    # Tree/list fill the host via anchors; they must not be ColumnLayout fillHeight siblings of the scope bar.
    assert "Layout.fillHeight: true" not in tree_block
    assert "Layout.fillHeight: true" not in collection_block
    assert "anchors.fill: parent" in tree_block
    assert "anchors.fill: parent" in collection_block

    assert "libraryInteraction.collectionEntries" in collection_block
    assert "theme.selectionSurface" in collection_block
    assert "theme.textPrimary" in collection_block
    assert "ItemDelegate" not in collection_block


def test_browser_767_column_and_favorite_wiring_preserved() -> None:
    from src import workbench_qml

    source = workbench_qml.QML_SOURCE
    assert "toggleFavorite" in source
    assert 'text: "BPM"' in source
    assert 'text: "KEY"' in source
    assert 'text: "LENGTH"' in source
    assert "waveformCanvas" in source
    assert "modelData.favorite" in source
    assert 'objectName: "browserFavoriteButton"' in source


def test_tree_state_initializes_only_top_level_and_fetches_direct_children_once() -> None:
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    navigation = FakeNavigation()
    state = WorkbenchLibraryTreeState(navigation)

    assert [node.node_id for node in state.visible_children(None)] == [
        SAMPLE_SOURCES
    ]
    assert [node.node_id for node in state.secondary_nodes()] == [
        "scope:all-library",
        COLLECTIONS,
        "scope:favorites",
        "scope:recordings",
    ]
    assert navigation.calls == []

    assert state.expand(SAMPLE_SOURCES) is True
    assert navigation.calls == [SAMPLE_SOURCES]
    assert [node.node_id for node in state.visible_children(SAMPLE_SOURCES)] == [
        ROOT_ID,
        OFFLINE_ROOT_ID,
        EMPTY_ROOT_ID,
    ]
    assert state.can_fetch_more(ROOT_ID)
    assert navigation.calls == [SAMPLE_SOURCES]

    assert state.expand(ROOT_ID) is True
    assert navigation.calls == [SAMPLE_SOURCES, ROOT_ID]
    assert [node.node_id for node in state.visible_children(ROOT_ID)] == [
        FOLDER_ID,
        "folder:1:U2hhcmVk",
    ]
    assert navigation.calls.count(FOLDER_ID) == 0


def test_expand_is_not_select_and_selection_resolves_exactly_one_scope() -> None:
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    navigation = FakeNavigation()
    state = WorkbenchLibraryTreeState(navigation)
    state.expand(SAMPLE_SOURCES)
    navigation.calls.clear()

    assert state.expand(ROOT_ID) is True
    assert state.selected_node_id is None
    assert navigation.calls == [ROOT_ID]

    intent = state.select(ROOT_ID)
    assert intent is not None
    assert intent.node.node_id == ROOT_ID
    assert intent.scope.kind is LibraryScopeKind.ROOT
    assert navigation.calls == [ROOT_ID, f"scope:{ROOT_ID}"]




def test_secondary_icon_nodes_use_the_same_typed_selection_authority() -> None:
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    navigation = FakeNavigation()
    state = WorkbenchLibraryTreeState(navigation)

    all_samples = state.select("scope:all-library")
    assert all_samples is not None
    assert all_samples.scope.kind is LibraryScopeKind.ALL_SAMPLES

    favorites = state.select("scope:favorites")
    assert favorites is not None
    assert favorites.scope.kind is LibraryScopeKind.FAVORITES

    recordings = state.select("scope:recordings")
    assert recordings is not None
    assert recordings.scope.kind is LibraryScopeKind.RECORDINGS

    # Catalog remains resolvable via navigation core even without a secondary icon.
    catalog_scope = navigation.resolve_scope("scope:catalog-readonly")
    assert catalog_scope is not None
    assert catalog_scope.kind is LibraryScopeKind.CATALOG

    state.fetch_children(COLLECTIONS)
    collection = state.select("collection:7")
    assert collection is not None
    assert collection.scope.kind is LibraryScopeKind.COLLECTION
    assert collection.scope.playlist_name == "Set A"


def test_offline_root_is_visible_selectable_and_not_expandable() -> None:
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    navigation = FakeNavigation()
    state = WorkbenchLibraryTreeState(navigation)
    state.expand(SAMPLE_SOURCES)

    offline = state.node(OFFLINE_ROOT_ID)
    assert offline is not None
    assert offline.availability is LibraryAvailability.OFFLINE
    assert offline.selectable and not offline.expandable
    assert state.expand(OFFLINE_ROOT_ID) is False
    assert navigation.calls == [SAMPLE_SOURCES]
    assert state.select(OFFLINE_ROOT_ID).scope.folder_id == 2


def test_empty_branch_is_loaded_once_without_fake_child_or_endless_fetch() -> None:
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    navigation = FakeNavigation()
    state = WorkbenchLibraryTreeState(navigation)
    state.expand(SAMPLE_SOURCES)

    assert state.expand(EMPTY_ROOT_ID) is True
    assert state.visible_children(EMPTY_ROOT_ID) == ()
    assert not state.can_fetch_more(EMPTY_ROOT_ID)
    assert state.expand(EMPTY_ROOT_ID) is False
    assert navigation.calls.count(EMPTY_ROOT_ID) == 1


def test_error_state_is_path_free_and_retry_is_bounded_to_one_branch() -> None:
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    navigation = FakeNavigation()
    navigation.fail_once_for.add(ROOT_ID)
    state = WorkbenchLibraryTreeState(navigation)
    state.expand(SAMPLE_SOURCES)

    assert state.expand(ROOT_ID) is True
    status = state.visible_children(ROOT_ID)
    assert len(status) == 1
    assert status[0].availability is LibraryAvailability.ERROR
    assert str(Path.cwd()) not in status[0].label
    assert not state.can_fetch_more(ROOT_ID)

    assert state.retry(ROOT_ID) is True
    assert [node.node_id for node in state.visible_children(ROOT_ID)] == [
        FOLDER_ID,
        "folder:1:U2hhcmVk",
    ]
    assert navigation.calls == [SAMPLE_SOURCES, ROOT_ID, ROOT_ID]


def test_duplicate_labels_are_not_used_as_identity() -> None:
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    navigation = FakeNavigation()
    duplicate_a = LibraryNode(
        "root:4", LibraryNodeKind.REGISTERED_ROOT, "Samples — one", SAMPLE_SOURCES,
        True, True, LibraryAvailability.AVAILABLE, folder_id=4,
    )
    duplicate_b = LibraryNode(
        "root:5", LibraryNodeKind.REGISTERED_ROOT, "Samples — one", SAMPLE_SOURCES,
        True, True, LibraryAvailability.AVAILABLE, folder_id=5,
    )
    navigation.children_by_parent[SAMPLE_SOURCES] = (duplicate_a, duplicate_b)
    state = WorkbenchLibraryTreeState(navigation)
    state.expand(SAMPLE_SOURCES)

    nodes = state.visible_children(SAMPLE_SOURCES)
    assert [node.node_id for node in nodes] == ["root:4", "root:5"]
    assert nodes[0].label == nodes[1].label


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qabstract_item_model_fetches_only_the_expanded_branch() -> None:
    from PySide6.QtCore import QAbstractItemModel, QCoreApplication

    from src.workbench_qml_library import (
        WorkbenchLibraryTreeState,
        create_qt_library_tree_model,
    )

    app = QCoreApplication.instance() or QCoreApplication([])
    del app
    navigation = FakeNavigation()
    state = WorkbenchLibraryTreeState(navigation)
    model = create_qt_library_tree_model(state)
    assert isinstance(model, QAbstractItemModel)
    assert model.rowCount() == 1
    assert navigation.calls == []

    sample_index = model.index(0, 0)
    assert model.canFetchMore(sample_index)
    model.fetchMore(sample_index)
    assert navigation.calls == [SAMPLE_SOURCES]
    assert model.rowCount(sample_index) == 3
    assert model.canFetchMore(model.index(0, 0, sample_index))
    assert navigation.calls == [SAMPLE_SOURCES]


def test_focus_contract_is_explicit_and_browser_owns_escape() -> None:
    from src import workbench_qml

    source = workbench_qml.QML_SOURCE
    assert "Key_Return" in source or "Key_Enter" in source
    assert "browser.forceActiveFocus()" in source
    assert "Key_Escape" in source
    assert "elide: Text.ElideRight" in source
    assert "ScrollBar.vertical" in source
    assert "minimumWidth: 1120" in source
    assert "minimumHeight: 640" in source
