"""Production Screen-1 composition over the existing Workbench loaders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .workbench_controller import (
    WorkbenchRow,
    add_workbench_library_folder,
    load_all_cached_rows,
    load_cached_folder_rows,
    load_cached_subfolder_rows,
    load_catalog_rows,
    load_playlist_workbench_rows,
    preview_workbench_library_folder_removal,
    remove_workbench_library_folder,
    validate_workbench_folder,
)
from .workbench_qml_library import LibrarySelectionIntent, WorkbenchLibraryTreeState
from .workbench_library_navigation import LibraryScope, LibraryScopeKind


@dataclass(frozen=True)
class Screen1BrowserState:
    rows: tuple[WorkbenchRow, ...] = ()
    selected_index: int = -1
    browser_context: str = "No library selected"
    scope: LibraryScope | None = None
    error: str | None = None


class Screen1QmlRuntimeComposition:
    """Own the single Library-selection-to-Browser dispatch path.

    This class deliberately owns no rendering and no audio behavior.  It only
    validates a resolved ``LibraryScope``, calls the canonical existing loader,
    and exposes an immutable browser projection for the QML adapter.
    """

    def __init__(self, *, tree_state: WorkbenchLibraryTreeState | None = None) -> None:
        self.library_tree = tree_state or WorkbenchLibraryTreeState()
        self.browser_state = Screen1BrowserState()
        self.audition_dispatches: list[WorkbenchRow] = []

    def dispatch_selection(self, intent: LibrarySelectionIntent) -> Screen1BrowserState:
        """Load exactly once for a valid intent, or fail closed."""
        scope = getattr(intent, "scope", None)
        error = self._validate_scope(scope)
        if error is not None:
            return self._set_no_scope(error)

        try:
            rows = tuple(self._load_scope(scope))
        except Exception:
            return self._set_no_scope("Library-Scope konnte nicht geladen werden.")

        selected_index = 0 if rows else -1
        self.browser_state = Screen1BrowserState(
            rows=rows,
            selected_index=selected_index,
            browser_context=self._browser_context(intent),
            scope=scope,
            error=None,
        )
        return self.browser_state

    def add_source(self, folder: Path | str) -> bool:
        validation = validate_workbench_folder(str(folder))
        if not validation.ok or validation.normalized_path is None:
            self._set_no_scope(validation.error_message or "Ungültiger Library-Ordner.")
            return False
        try:
            add_workbench_library_folder(validation.normalized_path)
        except Exception:
            self._set_no_scope("Library-Quelle konnte nicht registriert werden.")
            return False
        self.browser_state = Screen1BrowserState(
            rows=self.browser_state.rows,
            selected_index=self.browser_state.selected_index,
            browser_context=self.browser_state.browser_context,
            scope=self.browser_state.scope,
            error=None,
        )
        return True

    def remove_source(self, folder_id: int) -> bool:
        try:
            removed = bool(remove_workbench_library_folder(folder_id))
        except Exception:
            self._set_no_scope("Library-Quelle konnte nicht entfernt werden.")
            return False
        if not removed:
            return False

        selected_intent = self.library_tree.selection_intent
        active_scope = self.browser_state.scope
        selected_node = self.library_tree.node(self.library_tree.selected_node_id or "")
        selected_folder_id = selected_node.folder_id if selected_node is not None else None
        selected_scope_folder_id = (
            selected_intent.scope.folder_id if selected_intent is not None else None
        )
        active_scope_folder_id = active_scope.folder_id if active_scope is not None else None
        if folder_id in {
            selected_folder_id,
            selected_scope_folder_id,
            active_scope_folder_id,
        }:
            self.library_tree.clear_selection()
            self._set_no_scope()
        return True

    def preview_remove_source(self, folder_id: int):
        """Return the existing metadata-only removal confirmation seam."""
        try:
            return preview_workbench_library_folder_removal(folder_id)
        except Exception:
            return None

    def clear_no_scope(self) -> Screen1BrowserState:
        return self._set_no_scope()

    @staticmethod
    def _validate_scope(scope: LibraryScope) -> str | None:
        if not isinstance(scope, LibraryScope):
            return "Ungültiger Library-Scope."
        kind = scope.kind
        if kind is LibraryScopeKind.ROOT:
            if not isinstance(scope.folder_path, str) or not scope.folder_path.strip():
                return "Library-Root ohne folder_path."
        elif kind is LibraryScopeKind.SUBFOLDER:
            if not isinstance(scope.folder_id, int) or isinstance(scope.folder_id, bool):
                return "Subfolder ohne folder_id."
            if not isinstance(scope.relative_path, str) or not scope.relative_path.strip():
                return "Subfolder ohne relative_path."
        elif kind is LibraryScopeKind.COLLECTION:
            if not isinstance(scope.playlist_name, str) or not scope.playlist_name.strip():
                return "Collection ohne playlist_name."
        elif kind is LibraryScopeKind.CATALOG:
            if (
                not isinstance(scope.catalog_limit, int)
                or isinstance(scope.catalog_limit, bool)
                or scope.catalog_limit < 0
            ):
                return "Catalog ohne gültiges catalog_limit."
        elif kind is not LibraryScopeKind.ALL_SAMPLES:
            return "Unbekannter Library-Scope."
        return None

    @staticmethod
    def _load_scope(scope: LibraryScope) -> list[WorkbenchRow]:
        if scope.kind is LibraryScopeKind.ROOT:
            assert scope.folder_path is not None
            return load_cached_folder_rows(scope.folder_path)
        if scope.kind is LibraryScopeKind.SUBFOLDER:
            assert scope.folder_id is not None
            assert scope.relative_path is not None
            return load_cached_subfolder_rows(scope.folder_id, scope.relative_path)
        if scope.kind is LibraryScopeKind.ALL_SAMPLES:
            return load_all_cached_rows()
        if scope.kind is LibraryScopeKind.CATALOG:
            assert scope.catalog_limit is not None
            return load_catalog_rows(limit=scope.catalog_limit)
        if scope.kind is LibraryScopeKind.COLLECTION:
            assert scope.playlist_name is not None
            return load_playlist_workbench_rows(scope.playlist_name)
        raise ValueError("Unbekannter Library-Scope.")

    @staticmethod
    def _browser_context(intent: LibrarySelectionIntent) -> str:
        scope = intent.scope
        if scope.kind is LibraryScopeKind.CATALOG:
            return "Catalog · read-only"
        if scope.kind is LibraryScopeKind.COLLECTION:
            return f"Collection · {scope.playlist_name}"
        if scope.kind is LibraryScopeKind.ALL_SAMPLES:
            return "All Samples"
        return intent.node.label

    def _set_no_scope(self, error: str | None = None) -> Screen1BrowserState:
        self.browser_state = Screen1BrowserState(error=error)
        return self.browser_state


__all__ = ["Screen1BrowserState", "Screen1QmlRuntimeComposition"]
