"""Lazy renderer state and optional Qt model for the Screen-1 Library tree.

The state layer deliberately depends only on the renderer-neutral navigation
contract.  PySide6 is imported only by :func:`create_qt_library_tree_model`,
so normal Sample-Brain imports remain Qt-free.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from typing import Any

from .workbench_library_navigation import (
    LibraryAvailability,
    LibraryNode,
    LibraryNodeKind,
    LibraryScope,
    WorkbenchLibraryNavigation,
)


@dataclass(frozen=True)
class LibrarySelectionIntent:
    """Typed presentation intent; #576 owns Browser loader composition."""

    node: LibraryNode
    scope: LibraryScope


def _error_node(parent_id: str) -> LibraryNode:
    return LibraryNode(
        node_id=f"status:error:{parent_id.encode('utf-8').hex()}",
        kind=LibraryNodeKind.STATUS,
        label="Folder could not be loaded",
        parent_id=parent_id,
        selectable=False,
        expandable=False,
        availability=LibraryAvailability.ERROR,
    )


class WorkbenchLibraryTreeState:
    """Qt-free lazy state over ``WorkbenchLibraryNavigation``.

    Only ``top_level_nodes`` runs during construction.  Direct children are
    fetched once per branch, retained by stable node ID, and reset only by an
    explicit retry.
    """

    def __init__(self, navigation: Any | None = None) -> None:
        self.navigation = navigation or WorkbenchLibraryNavigation()
        top_level = tuple(self.navigation.top_level_nodes())
        self._nodes: dict[str, LibraryNode] = {}
        self._children: dict[str | None, tuple[str, ...]] = {None: ()}
        self._loaded: set[str] = set()
        self._loading: set[str] = set()
        self._expanded: set[str] = set()
        self.selected_node_id: str | None = None
        self.selection_intent: LibrarySelectionIntent | None = None
        self._remember_nodes(top_level)
        self._children[None] = tuple(node.node_id for node in top_level)

    def _remember_nodes(self, nodes: tuple[LibraryNode, ...]) -> None:
        for node in nodes:
            self._nodes.setdefault(node.node_id, node)

    def node(self, node_id: str) -> LibraryNode | None:
        return self._nodes.get(node_id)

    def visible_children(self, parent_id: str | None) -> tuple[LibraryNode, ...]:
        return tuple(
            self._nodes[node_id]
            for node_id in self._children.get(parent_id, ())
            if node_id in self._nodes
        )

    def is_loaded(self, node_id: str) -> bool:
        return node_id in self._loaded

    def is_loading(self, node_id: str) -> bool:
        return node_id in self._loading

    def is_expanded(self, node_id: str) -> bool:
        return node_id in self._expanded

    def can_fetch_more(self, node_id: str) -> bool:
        node = self.node(node_id)
        return bool(
            node is not None
            and node.expandable
            and node_id not in self._loaded
            and node_id not in self._loading
        )

    def fetch_children(self, node_id: str) -> tuple[LibraryNode, ...]:
        if not self.can_fetch_more(node_id):
            return self.visible_children(node_id)
        self._loading.add(node_id)
        try:
            try:
                children = tuple(self.navigation.children(node_id))
            except OSError:
                children = (_error_node(node_id),)
            except Exception:
                children = (_error_node(node_id),)
            self._remember_nodes(children)
            self._children[node_id] = tuple(child.node_id for child in children)
            self._loaded.add(node_id)
            return self.visible_children(node_id)
        finally:
            self._loading.discard(node_id)

    def expand(self, node_id: str) -> bool:
        node = self.node(node_id)
        if node is None or not node.expandable:
            return False
        if node_id in self._expanded:
            return False
        self.fetch_children(node_id)
        self._expanded.add(node_id)
        return True

    def collapse(self, node_id: str) -> bool:
        if node_id not in self._expanded:
            return False
        self._expanded.remove(node_id)
        return True

    def toggle_expanded(self, node_id: str) -> bool:
        return self.collapse(node_id) if self.is_expanded(node_id) else self.expand(node_id)

    def reset_branch(self, node_id: str) -> bool:
        node = self.node(node_id)
        if node is None or not node.expandable:
            return False
        self._loaded.discard(node_id)
        self._loading.discard(node_id)
        self._expanded.discard(node_id)
        self._children.pop(node_id, None)
        return True

    def retry(self, node_id: str) -> bool:
        if not self.reset_branch(node_id):
            return False
        self.fetch_children(node_id)
        self._expanded.add(node_id)
        return True

    def select(self, node_id: str) -> LibrarySelectionIntent | None:
        node = self.node(node_id)
        if node is None or not node.selectable:
            return None
        scope = self.navigation.resolve_scope(node_id)
        if scope is None:
            return None
        intent = LibrarySelectionIntent(node=node, scope=scope)
        self.selected_node_id = node_id
        self.selection_intent = intent
        return intent


def qt_library_model_available() -> bool:
    """Return whether the optional Qt model can be constructed."""

    return importlib.util.find_spec("PySide6") is not None


def create_qt_library_tree_model(state: WorkbenchLibraryTreeState, parent=None):
    """Create the optional real ``QAbstractItemModel`` adapter."""

    try:
        from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt, Signal, Slot
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Der Lazy Library Tree benötigt die optionale Abhängigkeit: "
            "pip install -e '.[qtquick]'"
        ) from exc

    class LibraryTreeQtModel(QAbstractItemModel):
        selection_changed = Signal()

        DisplayRole = int(Qt.ItemDataRole.DisplayRole)
        NodeIdRole = int(Qt.ItemDataRole.UserRole) + 1
        ParentNodeIdRole = int(Qt.ItemDataRole.UserRole) + 2
        KindRole = int(Qt.ItemDataRole.UserRole) + 3
        SelectableRole = int(Qt.ItemDataRole.UserRole) + 4
        ExpandableRole = int(Qt.ItemDataRole.UserRole) + 5
        AvailabilityRole = int(Qt.ItemDataRole.UserRole) + 6
        LoadingRole = int(Qt.ItemDataRole.UserRole) + 7
        ErrorRole = int(Qt.ItemDataRole.UserRole) + 8
        SelectedRole = int(Qt.ItemDataRole.UserRole) + 9
        HasChildrenRole = int(Qt.ItemDataRole.UserRole) + 10

        def __init__(self, tree_state: WorkbenchLibraryTreeState, qt_parent=None):
            super().__init__(qt_parent)
            self.state = tree_state
            self._items: dict[str | None, list[dict[str, object]]] = {None: []}
            for node in self.state.visible_children(None):
                self._items[None].append({"node_id": node.node_id, "parent_id": None})

        def _item(self, index: QModelIndex) -> dict[str, object] | None:
            if not index.isValid():
                return None
            value = index.internalPointer()
            return value if isinstance(value, dict) else None

        def _parent_id(self, item: dict[str, object]) -> str | None:
            value = item.get("parent_id")
            return value if isinstance(value, str) else None

        def _node_id(self, item: dict[str, object]) -> str:
            return str(item["node_id"])

        def _parent_index(self, node_id: str) -> QModelIndex:
            item = next(
                (
                    child
                    for children in self._items.values()
                    for child in children
                    if child.get("node_id") == node_id
                ),
                None,
            )
            if item is None:
                return QModelIndex()
            parent_id = self._parent_id(item)
            if parent_id is None:
                return QModelIndex()
            parent_item = next(
                (
                    child
                    for children in self._items.values()
                    for child in children
                    if child.get("node_id") == parent_id
                ),
                None,
            )
            if parent_item is None:
                return QModelIndex()
            siblings = self._items.get(self._parent_id(parent_item), [])
            return self.createIndex(siblings.index(parent_item), 0, parent_item)

        def _sync_children(self, parent_id: str) -> None:
            existing = self._items.setdefault(parent_id, [])
            existing_ids = {str(item["node_id"]) for item in existing}
            for node in self.state.visible_children(parent_id):
                if node.node_id not in existing_ids:
                    existing.append({"node_id": node.node_id, "parent_id": parent_id})

        def index(self, row, column, parent=QModelIndex()):
            if column != 0 or row < 0:
                return QModelIndex()
            parent_item = self._item(parent)
            parent_id = self._node_id(parent_item) if parent_item else None
            children = self._items.get(parent_id, [])
            if row >= len(children):
                return QModelIndex()
            return self.createIndex(row, column, children[row])

        def parent(self, child):
            item = self._item(child)
            if item is None:
                return QModelIndex()
            parent_id = self._parent_id(item)
            if parent_id is None:
                return QModelIndex()
            return self._parent_index(parent_id)

        def rowCount(self, parent=QModelIndex()):
            if parent.isValid() and parent.column() != 0:
                return 0
            item = self._item(parent)
            parent_id = self._node_id(item) if item else None
            return len(self._items.get(parent_id, []))

        def columnCount(self, _parent=QModelIndex()):
            return 1

        def hasChildren(self, parent=QModelIndex()):
            if parent.isValid() and parent.column() != 0:
                return False
            item = self._item(parent)
            if item is None:
                return bool(self._items.get(None))
            node_id = self._node_id(item)
            return bool(self._items.get(node_id)) or self.state.can_fetch_more(node_id)

        def canFetchMore(self, parent=QModelIndex()):
            item = self._item(parent)
            return bool(item and self.state.can_fetch_more(self._node_id(item)))

        def fetchMore(self, parent=QModelIndex()):
            item = self._item(parent)
            if item is None:
                return
            parent_id = self._node_id(item)
            before = len(self._items.get(parent_id, []))
            self.state.fetch_children(parent_id)
            after = len(self.state.visible_children(parent_id))
            if after > before:
                self.beginInsertRows(parent, before, after - 1)
                self._sync_children(parent_id)
                self.endInsertRows()
            self.dataChanged.emit(parent, parent, [])

        def data(self, index, role=DisplayRole):
            item = self._item(index)
            if item is None:
                return None
            node = self.state.node(self._node_id(item))
            if node is None:
                return None
            values = {
                self.DisplayRole: node.label,
                self.NodeIdRole: node.node_id,
                self.ParentNodeIdRole: node.parent_id or "",
                self.KindRole: node.kind.value,
                self.SelectableRole: node.selectable,
                self.ExpandableRole: node.expandable,
                self.AvailabilityRole: node.availability.value,
                self.LoadingRole: self.state.is_loading(node.node_id),
                self.ErrorRole: node.availability is LibraryAvailability.ERROR,
                self.SelectedRole: self.state.selected_node_id == node.node_id,
                self.HasChildrenRole: self.hasChildren(index),
            }
            return values.get(int(role))

        def roleNames(self):
            return {
                self.NodeIdRole: b"nodeId",
                self.ParentNodeIdRole: b"parentNodeId",
                self.KindRole: b"kind",
                self.SelectableRole: b"selectable",
                self.ExpandableRole: b"expandable",
                self.AvailabilityRole: b"availability",
                self.LoadingRole: b"loading",
                self.ErrorRole: b"error",
                self.SelectedRole: b"selected",
                self.HasChildrenRole: b"hasChildren",
            }

        def flags(self, index):
            if not index.isValid():
                return Qt.ItemFlag.NoItemFlags
            item = self._item(index)
            node = self.state.node(self._node_id(item)) if item else None
            flags = Qt.ItemFlag.ItemIsEnabled
            if node is not None and node.selectable:
                flags |= Qt.ItemFlag.ItemIsSelectable
            return flags

        def node_id_for_index(self, index) -> str | None:
            item = self._item(index)
            return self._node_id(item) if item else None

        @Slot(str, result=bool)
        def selectNode(self, node_id: str) -> bool:
            intent = self.state.select(node_id)
            if intent is None:
                return False
            self.selection_changed.emit()
            if self.rowCount() > 0:
                top_left = self.index(0, 0)
                bottom_right = self.index(self.rowCount() - 1, 0)
                self.dataChanged.emit(top_left, bottom_right, [self.SelectedRole])
            return True

        @Slot(str, result=bool)
        def retryNode(self, node_id: str) -> bool:
            if not self.state.reset_branch(node_id):
                return False
            item = next(
                (
                    child
                    for children in self._items.values()
                    for child in children
                    if child.get("node_id") == node_id
                ),
                None,
            )
            if item is None:
                return False
            parent_index = self._parent_index(node_id)
            children = self._items.get(node_id, [])
            if children:
                self.beginRemoveRows(parent_index, 0, len(children) - 1)
                self._items[node_id] = []
                self.endRemoveRows()
            self.fetchMore(parent_index)
            return True

        @Slot(str, result=bool)
        def toggleExpanded(self, node_id: str) -> bool:
            return self.state.toggle_expanded(node_id)

    return LibraryTreeQtModel(state, parent)


__all__ = [
    "LibrarySelectionIntent",
    "WorkbenchLibraryTreeState",
    "create_qt_library_tree_model",
    "qt_library_model_available",
]
