"""Production Screen-1 composition over the existing Workbench loaders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .workbench_controller import (
    WorkbenchRow,
    add_workbench_library_folder,
    get_workbench_library_folders,
    load_all_cached_rows,
    load_cached_folder_rows,
    load_cached_subfolder_rows,
    load_catalog_rows,
    load_playlist_workbench_rows,
    preview_workbench_library_folder_removal,
    remove_workbench_library_folder,
    validate_workbench_folder,
    workbench_scope_requires_refresh,
)
from .workbench_library import WORKBENCH_ANALYZER_VERSION, workbench_library_db_path
from .workbench_library_navigation import WorkbenchLibraryNavigation
from .workbench_qml_library import LibrarySelectionIntent, WorkbenchLibraryTreeState
from .workbench_library_navigation import LibraryScope, LibraryScopeKind


@dataclass(frozen=True)
class SourceRegistration:
    folder_id: int
    normalized_path: Path


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

    def __init__(
        self,
        *,
        library_db_path: Path | str | None = None,
        tree_state: WorkbenchLibraryTreeState | None = None,
    ) -> None:
        explicit_db_path = (
            Path(library_db_path).expanduser().resolve()
            if library_db_path is not None
            else None
        )
        tree_db_path = (
            Path(tree_state.library_db_path).expanduser().resolve()
            if tree_state is not None and tree_state.library_db_path is not None
            else None
        )
        if explicit_db_path is not None and tree_state is not None:
            if tree_db_path is None or tree_db_path != explicit_db_path:
                raise ValueError("Runtime, Navigation und Tree müssen dieselbe Library-DB verwenden.")
        self.library_db_path = (
            explicit_db_path or tree_db_path or workbench_library_db_path()
        ).expanduser().resolve()
        self._explicit_library_db_path = (
            explicit_db_path is not None or tree_db_path is not None
        )
        if tree_state is None:
            navigation = WorkbenchLibraryNavigation(library_db_path=self.library_db_path)
            tree_state = WorkbenchLibraryTreeState(navigation)
        self.library_tree = tree_state
        self.browser_state = Screen1BrowserState()
        self.audition_dispatches: list[WorkbenchRow] = []
        self._selected_node_id: str | None = None

    @property
    def selected_node_id(self) -> str | None:
        """Node id of the last successfully dispatched selection."""
        return self._selected_node_id

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
        self._selected_node_id = intent.node.node_id
        return self.browser_state

    def add_source(self, folder: Path | str) -> bool:
        return self.register_source_for_analysis(folder) is not None

    def register_source_for_analysis(self, folder: Path | str) -> SourceRegistration | None:
        validation = validate_workbench_folder(str(folder))
        if not validation.ok or validation.normalized_path is None:
            self._set_no_scope(validation.error_message or "Ungültiger Library-Ordner.")
            return None
        try:
            folder_id = self._register_library_folder(validation.normalized_path)
        except Exception:
            self._set_no_scope("Library-Quelle konnte nicht registriert werden.")
            return None
        self.browser_state = Screen1BrowserState(
            rows=self.browser_state.rows,
            selected_index=self.browser_state.selected_index,
            browser_context=self.browser_state.browser_context,
            scope=self.browser_state.scope,
            error=None,
        )
        return SourceRegistration(
            folder_id=int(folder_id),
            normalized_path=validation.normalized_path,
        )

    def _register_library_folder(self, folder: Path) -> int:
        if self._explicit_library_db_path:
            result = add_workbench_library_folder(
                folder,
                library_db_path=self.library_db_path,
            )
            if isinstance(result, bool):
                if not result:
                    raise LookupError("Library-Quelle wurde nicht registriert.")
                folders = get_workbench_library_folders(
                    library_db_path=self.library_db_path,
                )
                return self._lookup_registered_folder_id(folder, folders)
            return int(result)
        result = add_workbench_library_folder(folder)
        if isinstance(result, bool):
            if not result:
                raise LookupError("Library-Quelle wurde nicht registriert.")
            return self._lookup_registered_folder_id(folder, get_workbench_library_folders())
        return int(result)

    @staticmethod
    def _lookup_registered_folder_id(folder: Path, folders) -> int:
        normalized = str(folder.expanduser().resolve())
        for registered in folders:
            if str(Path(registered.path).expanduser().resolve()) == normalized:
                return int(registered.id)
        raise LookupError("Registrierte Library-Quelle konnte nicht aufgelöst werden.")

    def remove_source(self, folder_id: int) -> bool:
        try:
            if self._explicit_library_db_path:
                removed = bool(
                    remove_workbench_library_folder(
                        folder_id,
                        library_db_path=self.library_db_path,
                    )
                )
            else:
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
            if self._explicit_library_db_path:
                return preview_workbench_library_folder_removal(
                    folder_id,
                    library_db_path=self.library_db_path,
                )
            return preview_workbench_library_folder_removal(folder_id)
        except Exception:
            return None

    def clear_no_scope(self, error: str | None = None) -> Screen1BrowserState:
        return self._set_no_scope(error)

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

    def _load_scope(self, scope: LibraryScope) -> list[WorkbenchRow]:
        if scope.kind is LibraryScopeKind.ROOT:
            assert scope.folder_path is not None
            if self._explicit_library_db_path:
                return load_cached_folder_rows(
                    scope.folder_path,
                    library_db_path=self.library_db_path,
                )
            return load_cached_folder_rows(scope.folder_path)
        if scope.kind is LibraryScopeKind.SUBFOLDER:
            assert scope.folder_id is not None
            assert scope.relative_path is not None
            if self._explicit_library_db_path:
                return load_cached_subfolder_rows(
                    scope.folder_id,
                    scope.relative_path,
                    library_db_path=self.library_db_path,
                )
            return load_cached_subfolder_rows(scope.folder_id, scope.relative_path)
        if scope.kind is LibraryScopeKind.ALL_SAMPLES:
            if self._explicit_library_db_path:
                return load_all_cached_rows(library_db_path=self.library_db_path)
            return load_all_cached_rows()
        if scope.kind is LibraryScopeKind.CATALOG:
            assert scope.catalog_limit is not None
            return load_catalog_rows(limit=scope.catalog_limit)
        if scope.kind is LibraryScopeKind.COLLECTION:
            assert scope.playlist_name is not None
            if self._explicit_library_db_path:
                return load_playlist_workbench_rows(
                    scope.playlist_name,
                    library_db_path=self.library_db_path,
                )
            return load_playlist_workbench_rows(scope.playlist_name)
        raise ValueError("Unbekannter Library-Scope.")

    def refresh_target(self, scope: LibraryScope) -> SourceRegistration | None:
        """Return the registered source a ROOT/SUBFOLDER scope must refresh.

        Returns ``None`` when the scope is not a library folder scope or when all
        relevant cached rows already match ``WORKBENCH_ANALYZER_VERSION``.  The
        caller decides whether to start exactly one analysis job.
        """
        if scope.kind is LibraryScopeKind.ROOT:
            folder_id = scope.folder_id
            folder_path = scope.folder_path
            relative_path = None
        elif scope.kind is LibraryScopeKind.SUBFOLDER:
            if not isinstance(scope.relative_path, str) or not scope.relative_path.strip():
                return None
            folder_id = scope.folder_id
            folder_path = scope.folder_path
            relative_path = scope.relative_path
        else:
            return None
        if folder_id is None:
            if folder_path is None:
                return None
            try:
                if self._explicit_library_db_path:
                    folders = get_workbench_library_folders(
                        library_db_path=self.library_db_path
                    )
                else:
                    folders = get_workbench_library_folders()
                folder_id = self._lookup_registered_folder_id(Path(folder_path), folders)
            except LookupError:
                return None
        if self.browser_state.scope == scope and self.browser_state.error is None:
            needs_refresh = any(
                row.details.get("analyzer_version") != WORKBENCH_ANALYZER_VERSION
                and Path(row.path).is_file()
                for row in self.browser_state.rows
            )
        else:
            needs_refresh = workbench_scope_requires_refresh(
                folder_id=folder_id,
                folder_path=folder_path,
                relative_path=relative_path,
                library_db_path=self.library_db_path,
            )
        if not needs_refresh:
            return None
        return SourceRegistration(
            folder_id=int(folder_id),
            normalized_path=Path(folder_path),
        )

    def post_analysis_node_id(
        self,
        folder_id: int,
        *,
        previous_selected: str | None = None,
    ) -> str:
        """Deterministic reload target for a completed analysis job.

        Keeps an active subfolder scope of the analyzed root selected and falls
        back to that root when nothing (or another source) was selected.
        """
        if previous_selected:
            folder_prefix = f"{folder_id}:"
            if previous_selected == f"root:{folder_id}":
                return previous_selected
            if previous_selected.startswith(f"folder:{folder_prefix}"):
                return previous_selected
        return f"root:{folder_id}"

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


__all__ = [
    "Screen1BrowserState",
    "Screen1QmlRuntimeComposition",
    "SourceRegistration",
]
