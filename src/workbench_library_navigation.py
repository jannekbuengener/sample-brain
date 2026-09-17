"""Renderer-neutral navigation over the persisted Workbench Library state."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path

from .workbench_catalog import DEFAULT_CATALOG_LOAD_LIMIT, catalog_available
from .workbench_library import (
    LibraryFolder,
    WorkbenchPlaylist,
    list_library_folders,
    list_playlists,
    workbench_library_db_path,
)


class LibraryNodeKind(str, Enum):
    SAMPLE_SOURCES = "sample_sources"
    REGISTERED_ROOT = "registered_root"
    SUBFOLDER = "subfolder"
    ALL_SAMPLES = "all_samples"
    CATALOG = "catalog"
    COLLECTIONS = "collections"
    COLLECTION = "collection"
    ADD_SOURCE = "add_source"
    STATUS = "status"


class LibraryAvailability(str, Enum):
    AVAILABLE = "available"
    OFFLINE = "offline"
    LOADING = "loading"
    ERROR = "error"


class LibraryScopeKind(str, Enum):
    ROOT = "root"
    SUBFOLDER = "subfolder"
    ALL_SAMPLES = "all_samples"
    CATALOG = "catalog"
    COLLECTION = "collection"


@dataclass(frozen=True)
class LibraryNode:
    node_id: str
    kind: LibraryNodeKind
    label: str
    parent_id: str | None
    selectable: bool
    expandable: bool
    availability: LibraryAvailability
    folder_id: int | None = None
    relative_path: str | None = None
    playlist_id: int | None = None


@dataclass(frozen=True)
class LibraryScope:
    kind: LibraryScopeKind
    folder_id: int | None = None
    folder_path: str | None = None
    relative_path: str | None = None
    playlist_id: int | None = None
    playlist_name: str | None = None
    catalog_limit: int | None = None


_SAMPLE_SOURCES_ID = "container:sample-sources"
_ALL_SAMPLES_ID = "scope:all-library"
_CATALOG_ID = "scope:catalog-readonly"
_COLLECTIONS_ID = "container:collections"
_ADD_SOURCE_ID = "action:add-source"


def _canonical_relative_path(relative_path: str) -> str | None:
    text = str(relative_path).strip()
    if not text:
        return None
    native_path = text.replace("/", os.sep).replace("\\", os.sep)
    normalized = os.path.normcase(os.path.normpath(native_path))
    if normalized in {"", "."} or os.path.isabs(normalized):
        return None
    parts = Path(normalized).parts
    if any(part == ".." for part in parts):
        return None
    return normalized


def _encode_relative_path(relative_path: str) -> str:
    return base64.urlsafe_b64encode(relative_path.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_relative_path(payload: str) -> str | None:
    try:
        padded = payload + "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return None
    normalized = _canonical_relative_path(decoded)
    if normalized is None or _encode_relative_path(normalized) != payload:
        return None
    return normalized


def _folder_name(path: str) -> str:
    resolved = Path(path)
    return resolved.name or resolved.anchor.rstrip("\\/") or path


def _parent_suffix(path: str, depth: int) -> str:
    parent_parts = Path(path).parent.parts
    if not parent_parts:
        return ""
    return "/".join(parent_parts[-depth:])


def _root_labels(folders: list[LibraryFolder]) -> dict[int, str]:
    labels = {folder.id: _folder_name(folder.path) for folder in folders}
    groups: dict[str, list[LibraryFolder]] = {}
    for folder in folders:
        groups.setdefault(os.path.normcase(labels[folder.id]), []).append(folder)

    for duplicate_folders in groups.values():
        if len(duplicate_folders) == 1:
            continue
        max_depth = max(len(Path(folder.path).parent.parts) for folder in duplicate_folders)
        suffixes: dict[int, str] = {}
        for depth in range(1, max_depth + 1):
            candidate = {
                folder.id: _parent_suffix(folder.path, depth)
                for folder in duplicate_folders
            }
            if len({os.path.normcase(value) for value in candidate.values()}) == len(
                duplicate_folders
            ):
                suffixes = candidate
                break
        for folder in duplicate_folders:
            suffix = suffixes.get(folder.id) or _parent_suffix(folder.path, max_depth)
            labels[folder.id] = f"{labels[folder.id]} — {suffix}"
    return labels


def _is_link_or_junction(entry: os.DirEntry[str]) -> bool:
    if entry.is_symlink():
        return True
    path = Path(entry.path)
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _is_link_or_junction_path(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        return bool(is_junction and is_junction())
    except OSError:
        return True


def _directory_is_safe(folder_path: str, relative_path: str | None) -> bool:
    current = Path(folder_path)
    if _is_link_or_junction_path(current):
        return False
    if not relative_path:
        return True
    for component in relative_path.replace("\\", "/").split("/"):
        if not component:
            continue
        current /= component
        if _is_link_or_junction_path(current):
            return False
    return True


class WorkbenchLibraryNavigation:
    """Expose cached Library navigation without owning any renderer or loader."""

    def __init__(
        self,
        *,
        library_db_path: Path | None = None,
        catalog_path: Path | str | None = None,
    ) -> None:
        self._library_db_path = (
            library_db_path if library_db_path is not None else workbench_library_db_path()
        )
        self._catalog_path = catalog_path

    def top_level_nodes(self) -> tuple[LibraryNode, ...]:
        catalog_state = (
            LibraryAvailability.AVAILABLE
            if catalog_available(self._catalog_path)
            else LibraryAvailability.OFFLINE
        )
        return (
            LibraryNode(
                _SAMPLE_SOURCES_ID,
                LibraryNodeKind.SAMPLE_SOURCES,
                "Sample Sources",
                None,
                False,
                True,
                LibraryAvailability.AVAILABLE,
            ),
            LibraryNode(
                _ALL_SAMPLES_ID,
                LibraryNodeKind.ALL_SAMPLES,
                "All Samples",
                None,
                True,
                False,
                LibraryAvailability.AVAILABLE,
            ),
            LibraryNode(
                _CATALOG_ID,
                LibraryNodeKind.CATALOG,
                "Catalog",
                None,
                True,
                False,
                catalog_state,
            ),
            LibraryNode(
                _COLLECTIONS_ID,
                LibraryNodeKind.COLLECTIONS,
                "Collections",
                None,
                False,
                True,
                LibraryAvailability.AVAILABLE,
            ),
        )

    def children(self, node_id: str) -> tuple[LibraryNode, ...]:
        if node_id == _SAMPLE_SOURCES_ID:
            return self._source_children()
        if node_id == _COLLECTIONS_ID:
            return self._collection_children()
        directory = self._directory_for_node(node_id)
        if directory is None:
            return ()
        folder, relative_path = directory
        path = Path(folder.path)
        if relative_path:
            path = path.joinpath(*relative_path.replace("\\", "/").split("/"))
        if not _directory_is_safe(folder.path, relative_path):
            return ()
        if not path.is_dir():
            return ()
        try:
            with os.scandir(path) as entries:
                direct_children = [
                    entry
                    for entry in entries
                    if not _is_link_or_junction(entry)
                    and entry.is_dir(follow_symlinks=False)
                ]
        except OSError:
            return (self._error_status(node_id),)

        direct_children.sort(key=lambda entry: (os.path.normcase(entry.name), entry.name))
        return tuple(
            self._subfolder_node(folder, relative_path, entry.name, node_id)
            for entry in direct_children
        )

    def resolve_scope(self, node_id: str) -> LibraryScope | None:
        if node_id == _ALL_SAMPLES_ID:
            return LibraryScope(LibraryScopeKind.ALL_SAMPLES)
        if node_id == _CATALOG_ID:
            return LibraryScope(
                LibraryScopeKind.CATALOG,
                catalog_limit=DEFAULT_CATALOG_LOAD_LIMIT,
            )
        if node_id.startswith("root:"):
            folder = self._folder_for_id(node_id.removeprefix("root:"))
            if folder is not None:
                return LibraryScope(
                    LibraryScopeKind.ROOT,
                    folder_id=folder.id,
                    folder_path=folder.path,
                )
            return None
        directory = self._directory_for_node(node_id)
        if directory is not None and node_id.startswith("folder:"):
            folder, relative_path = directory
            return LibraryScope(
                LibraryScopeKind.SUBFOLDER,
                folder_id=folder.id,
                folder_path=folder.path,
                relative_path=relative_path,
            )
        if node_id.startswith("collection:"):
            playlist = self._playlist_for_id(node_id.removeprefix("collection:"))
            if playlist is not None:
                return LibraryScope(
                    LibraryScopeKind.COLLECTION,
                    playlist_id=playlist.id,
                    playlist_name=playlist.name,
                )
        return None

    def _source_children(self) -> tuple[LibraryNode, ...]:
        folders = list_library_folders(db_path=self._library_db_path)
        labels = _root_labels(folders)
        roots = [
            LibraryNode(
                node_id=f"root:{folder.id}",
                kind=LibraryNodeKind.REGISTERED_ROOT,
                label=labels[folder.id],
                parent_id=_SAMPLE_SOURCES_ID,
                selectable=True,
                expandable=Path(folder.path).is_dir(),
                availability=(
                    LibraryAvailability.AVAILABLE
                    if Path(folder.path).is_dir()
                    else LibraryAvailability.OFFLINE
                ),
                folder_id=folder.id,
            )
            for folder in folders
        ]
        roots.sort(key=lambda node: (os.path.normcase(node.label), node.node_id))
        roots.append(
            LibraryNode(
                _ADD_SOURCE_ID,
                LibraryNodeKind.ADD_SOURCE,
                "Add Source…",
                _SAMPLE_SOURCES_ID,
                False,
                False,
                LibraryAvailability.AVAILABLE,
            )
        )
        return tuple(roots)

    def _collection_children(self) -> tuple[LibraryNode, ...]:
        return tuple(
            LibraryNode(
                node_id=f"collection:{playlist.id}",
                kind=LibraryNodeKind.COLLECTION,
                label=playlist.name,
                parent_id=_COLLECTIONS_ID,
                selectable=True,
                expandable=False,
                availability=LibraryAvailability.AVAILABLE,
                playlist_id=playlist.id,
            )
            for playlist in list_playlists(db_path=self._library_db_path)
        )

    def _subfolder_node(
        self,
        folder: LibraryFolder,
        parent_relative_path: str | None,
        name: str,
        parent_id: str,
    ) -> LibraryNode:
        joined = os.path.join(parent_relative_path or "", name)
        relative_path = _canonical_relative_path(joined)
        assert relative_path is not None
        return LibraryNode(
            node_id=f"folder:{folder.id}:{_encode_relative_path(relative_path)}",
            kind=LibraryNodeKind.SUBFOLDER,
            label=name,
            parent_id=parent_id,
            selectable=True,
            expandable=True,
            availability=LibraryAvailability.AVAILABLE,
            folder_id=folder.id,
            relative_path=relative_path,
        )

    def _directory_for_node(
        self, node_id: str
    ) -> tuple[LibraryFolder, str | None] | None:
        if node_id.startswith("root:"):
            folder = self._folder_for_id(node_id.removeprefix("root:"))
            return (folder, None) if folder is not None else None
        if not node_id.startswith("folder:"):
            return None
        parts = node_id.split(":", 2)
        if len(parts) != 3:
            return None
        _, folder_id_text, payload = parts
        folder = self._folder_for_id(folder_id_text)
        relative_path = _decode_relative_path(payload)
        if folder is None or relative_path is None:
            return None
        return folder, relative_path

    def _folder_for_id(self, value: str) -> LibraryFolder | None:
        try:
            folder_id = int(value)
        except ValueError:
            return None
        return next(
            (
                folder
                for folder in list_library_folders(db_path=self._library_db_path)
                if folder.id == folder_id
            ),
            None,
        )

    def _playlist_for_id(self, value: str) -> WorkbenchPlaylist | None:
        try:
            playlist_id = int(value)
        except ValueError:
            return None
        return next(
            (
                playlist
                for playlist in list_playlists(db_path=self._library_db_path)
                if playlist.id == playlist_id
            ),
            None,
        )

    @staticmethod
    def _error_status(parent_id: str) -> LibraryNode:
        encoded_parent = _encode_relative_path(parent_id)
        return LibraryNode(
            node_id=f"status:error:{encoded_parent}",
            kind=LibraryNodeKind.STATUS,
            label="Folder could not be loaded",
            parent_id=parent_id,
            selectable=False,
            expandable=False,
            availability=LibraryAvailability.ERROR,
        )


__all__ = [
    "LibraryAvailability",
    "LibraryNode",
    "LibraryNodeKind",
    "LibraryScope",
    "LibraryScopeKind",
    "WorkbenchLibraryNavigation",
]
