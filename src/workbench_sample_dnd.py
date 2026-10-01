"""Bidirectional sample-file Drag & Drop contracts for Screen-1 (#768).

Python owns destination validation, safe COPY, collision policy, targeted
analysis reuse, and refresh/error results. QML only initiates drag/drop intents
and displays status.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import threading
from typing import Literal, Sequence
from urllib.parse import unquote, urlparse

from .config import AUDIO_EXTS
from .workbench_controller import (
    WorkbenchResult,
    analyze_audio_paths_for_workbench,
)
from .workbench_library_navigation import (
    LibraryScopeKind,
    WorkbenchLibraryNavigation,
    _directory_is_safe,
    _is_link_or_junction_path,
)


InboundStatus = Literal["imported", "skipped_conflict", "failed", "rejected"]

# Serialize inbound COPY jobs in-process so overlapping workers cannot race the
# same destination basename before exclusive create settles the winner.
_INBOUND_COPY_LOCK = threading.Lock()


def _copy_file_exclusive(source: Path, destination: Path) -> None:
    """COPY *source* to *destination* using exclusive create (no overwrite).

    Raises ``FileExistsError`` when *destination* already exists (EEXIST).
    Partial destinations created during a failed write are removed.
    """
    created = False
    try:
        with open(destination, "xb") as out_f, open(source, "rb") as in_f:
            created = True
            shutil.copyfileobj(in_f, out_f)
        shutil.copystat(source, destination, follow_symlinks=True)
    except FileExistsError:
        raise
    except Exception:
        if created:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
        raise


@dataclass(frozen=True)
class DropDestination:
    folder_id: int
    source_root: Path
    destination_dir: Path
    node_id: str
    relative_path: str | None = None


@dataclass(frozen=True)
class DestinationResolution:
    ok: bool
    destination: DropDestination | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class InboundFileResult:
    source_path: Path
    status: InboundStatus
    destination_path: Path | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class InboundImportResult:
    imported: tuple[InboundFileResult, ...] = ()
    skipped_conflict: tuple[InboundFileResult, ...] = ()
    failed: tuple[InboundFileResult, ...] = ()
    destination: DropDestination | None = None
    error_code: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None and bool(self.imported)


@dataclass(frozen=True)
class ImportAnalyzeResult:
    import_result: InboundImportResult
    analysis: WorkbenchResult | None = None
    should_refresh_browser: bool = False
    should_auto_audition: bool = False


def outbound_local_file_url(sample_path: Path | str) -> str | None:
    """Return a standard local ``file:`` URL for an existing original sample."""
    path = Path(sample_path).expanduser()
    try:
        resolved = path.resolve()
    except OSError:
        return None
    if not resolved.is_file():
        return None
    if _is_link_or_junction_path(resolved):
        # Outbound still exposes the real file path via resolve(); junctions on
        # the file itself are rare. Keep fail-soft for unreadable entries.
        pass
    return resolved.as_uri()


def _local_path_from_url(value: str) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("file:"):
        parsed = urlparse(text)
        if parsed.scheme != "file":
            return None
        # Reject non-local / remote file URLs in v1.
        if parsed.netloc and parsed.netloc not in {"", "localhost"}:
            # Windows file:///C:/... has empty netloc; file://server/share is rejected.
            if not (os.name == "nt" and len(parsed.netloc) == 1):
                return None
        raw_path = unquote(parsed.path or "")
        if os.name == "nt" and raw_path.startswith("/") and len(raw_path) >= 3 and raw_path[2] == ":":
            raw_path = raw_path[1:]
        elif os.name == "nt" and parsed.netloc and len(parsed.netloc) == 1:
            raw_path = f"{parsed.netloc}:{raw_path}"
        candidate = Path(raw_path)
    else:
        candidate = Path(text)
    try:
        resolved = candidate.expanduser().resolve()
    except OSError:
        return None
    return resolved


def _is_supported_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTS


def _destination_under_source(source_root: Path, destination_dir: Path) -> bool:
    try:
        destination_dir.relative_to(source_root)
    except ValueError:
        return False
    return True


def _path_chain_safe(source_root: Path, destination_dir: Path) -> bool:
    if _is_link_or_junction_path(source_root):
        return False
    if not _destination_under_source(source_root, destination_dir):
        return False
    try:
        relative = destination_dir.relative_to(source_root)
    except ValueError:
        return False
    relative_text = None if str(relative) in {".", ""} else str(relative)
    if not _directory_is_safe(str(source_root), relative_text):
        return False
    if _is_link_or_junction_path(destination_dir):
        return False
    return True


def resolve_drop_destination(
    node_id: str,
    *,
    library_db_path: Path | None = None,
) -> DestinationResolution:
    """Resolve a uniquely writable registered Source root or real Source subfolder."""
    navigation = WorkbenchLibraryNavigation(library_db_path=library_db_path)
    scope = navigation.resolve_scope(str(node_id or ""))
    if scope is None:
        return DestinationResolution(
            ok=False,
            error_code="invalid_destination",
            error_message="Drop-Ziel ist ungültig oder nicht schreibbar.",
        )
    if scope.kind not in {LibraryScopeKind.ROOT, LibraryScopeKind.SUBFOLDER}:
        return DestinationResolution(
            ok=False,
            error_code="invalid_destination",
            error_message="Nur registrierte Sources/Unterordner akzeptieren Datei-Drops.",
        )
    if not isinstance(scope.folder_id, int) or isinstance(scope.folder_id, bool):
        return DestinationResolution(
            ok=False,
            error_code="invalid_destination",
            error_message="Drop-Ziel ohne Source-Identität.",
        )
    if not isinstance(scope.folder_path, str) or not scope.folder_path.strip():
        return DestinationResolution(
            ok=False,
            error_code="invalid_destination",
            error_message="Drop-Ziel ohne Source-Pfad.",
        )

    source_root = Path(scope.folder_path).expanduser().resolve()
    if not source_root.is_dir():
        return DestinationResolution(
            ok=False,
            error_code="destination_offline",
            error_message="Source ist offline oder nicht erreichbar.",
        )
    if not os.access(source_root, os.W_OK):
        return DestinationResolution(
            ok=False,
            error_code="invalid_destination",
            error_message="Source ist nicht schreibbar.",
        )

    relative_path = scope.relative_path if scope.kind is LibraryScopeKind.SUBFOLDER else None
    if relative_path is not None:
        if ".." in Path(relative_path).parts:
            return DestinationResolution(
                ok=False,
                error_code="invalid_destination",
                error_message="Pfad-Traversal im Drop-Ziel abgelehnt.",
            )
        destination_dir = source_root.joinpath(*Path(relative_path).parts)
    else:
        destination_dir = source_root

    try:
        destination_dir = destination_dir.resolve()
    except OSError:
        return DestinationResolution(
            ok=False,
            error_code="destination_offline",
            error_message="Drop-Ziel konnte nicht aufgelöst werden.",
        )

    if not destination_dir.is_dir():
        return DestinationResolution(
            ok=False,
            error_code="destination_offline",
            error_message="Drop-Ziel ist offline oder kein Ordner.",
        )
    if not os.access(destination_dir, os.W_OK):
        return DestinationResolution(
            ok=False,
            error_code="invalid_destination",
            error_message="Drop-Ziel ist nicht schreibbar.",
        )
    if not _path_chain_safe(source_root, destination_dir):
        return DestinationResolution(
            ok=False,
            error_code="invalid_destination",
            error_message="Drop-Ziel verletzt die Source-Pfadgrenze.",
        )

    return DestinationResolution(
        ok=True,
        destination=DropDestination(
            folder_id=int(scope.folder_id),
            source_root=source_root,
            destination_dir=destination_dir,
            node_id=str(node_id),
            relative_path=relative_path,
        ),
    )


def copy_files_into_destination(
    source_paths: Sequence[Path],
    destination: DropDestination,
) -> InboundImportResult:
    """COPY sources into *destination* without move/delete/overwrite."""
    if not _path_chain_safe(destination.source_root, destination.destination_dir):
        return InboundImportResult(
            error_code="path_escape",
            error_message="Drop-Ziel verletzt die Source-Pfadgrenze.",
            destination=destination,
        )
    if not destination.destination_dir.is_dir():
        return InboundImportResult(
            error_code="destination_offline",
            error_message="Drop-Ziel ist offline oder kein Ordner.",
            destination=destination,
        )

    imported: list[InboundFileResult] = []
    skipped: list[InboundFileResult] = []
    failed: list[InboundFileResult] = []

    # Hold the lock across the full inbound batch so concurrent same-name imports
    # cannot both pass a pre-check and race the exclusive create.
    with _INBOUND_COPY_LOCK:
        for source in source_paths:
            try:
                resolved = Path(source).expanduser().resolve()
            except OSError as exc:
                failed.append(
                    InboundFileResult(
                        source_path=Path(source),
                        status="failed",
                        error_code="unreadable_source",
                        error_message=str(exc),
                    )
                )
                continue
            if not resolved.is_file():
                failed.append(
                    InboundFileResult(
                        source_path=resolved,
                        status="failed",
                        error_code="unreadable_source",
                        error_message="Quelldatei fehlt oder ist kein File.",
                    )
                )
                continue
            if not _is_supported_audio(resolved):
                failed.append(
                    InboundFileResult(
                        source_path=resolved,
                        status="failed",
                        error_code="unsupported_audio",
                        error_message="Dateityp wird nicht unterstützt.",
                    )
                )
                continue

            dest = destination.destination_dir / resolved.name
            try:
                dest_resolved = dest.resolve()
            except OSError as exc:
                failed.append(
                    InboundFileResult(
                        source_path=resolved,
                        status="failed",
                        error_code="destination_error",
                        error_message=str(exc),
                    )
                )
                continue
            if not _destination_under_source(destination.source_root, dest_resolved.parent):
                failed.append(
                    InboundFileResult(
                        source_path=resolved,
                        status="failed",
                        error_code="path_escape",
                        error_message="Zieldatei außerhalb der Source.",
                    )
                )
                continue
            # Fast-path collision check; exclusive create below is the real guard
            # against TOCTOU races between exists() and write.
            if dest_resolved.exists():
                skipped.append(
                    InboundFileResult(
                        source_path=resolved,
                        status="skipped_conflict",
                        destination_path=dest_resolved,
                        error_code="collision",
                        error_message="Datei existiert bereits; kein Überschreiben.",
                    )
                )
                continue
            try:
                _copy_file_exclusive(resolved, dest_resolved)
            except FileExistsError:
                skipped.append(
                    InboundFileResult(
                        source_path=resolved,
                        status="skipped_conflict",
                        destination_path=dest_resolved,
                        error_code="collision",
                        error_message="Datei existiert bereits; kein Überschreiben.",
                    )
                )
                continue
            except OSError as exc:
                failed.append(
                    InboundFileResult(
                        source_path=resolved,
                        status="failed",
                        error_code="copy_failed",
                        error_message=str(exc),
                    )
                )
                continue
            imported.append(
                InboundFileResult(
                    source_path=resolved,
                    status="imported",
                    destination_path=dest_resolved,
                )
            )

    return InboundImportResult(
        imported=tuple(imported),
        skipped_conflict=tuple(skipped),
        failed=tuple(failed),
        destination=destination,
    )


def import_dropped_files(
    urls: Sequence[str],
    *,
    destination_node_id: str,
    library_db_path: Path | None = None,
) -> InboundImportResult:
    """Validate destination and COPY dropped local file URLs (no analysis)."""
    resolution = resolve_drop_destination(
        destination_node_id, library_db_path=library_db_path
    )
    if not resolution.ok or resolution.destination is None:
        return InboundImportResult(
            error_code=resolution.error_code or "invalid_destination",
            error_message=resolution.error_message
            or "Drop-Ziel ist ungültig oder nicht schreibbar.",
        )

    paths: list[Path] = []
    failed: list[InboundFileResult] = []
    for raw in urls:
        parsed = _local_path_from_url(str(raw))
        if parsed is None:
            failed.append(
                InboundFileResult(
                    source_path=Path(str(raw)),
                    status="failed",
                    error_code="unsupported_url",
                    error_message="Nur lokale file:-URLs werden akzeptiert.",
                )
            )
            continue
        paths.append(parsed)

    result = copy_files_into_destination(paths, resolution.destination)
    if not failed:
        return result
    return InboundImportResult(
        imported=result.imported,
        skipped_conflict=result.skipped_conflict,
        failed=tuple(failed) + result.failed,
        destination=result.destination,
        error_code=result.error_code,
        error_message=result.error_message,
    )


def import_and_analyze_dropped_files(
    urls: Sequence[str],
    *,
    destination_node_id: str,
    library_db_path: Path | None = None,
    progress_callback=None,
    should_cancel=None,
) -> ImportAnalyzeResult:
    """COPY dropped files then analyze ONLY the newly imported destinations."""
    import_result = import_dropped_files(
        urls,
        destination_node_id=destination_node_id,
        library_db_path=library_db_path,
    )
    if import_result.destination is None or not import_result.imported:
        return ImportAnalyzeResult(
            import_result=import_result,
            analysis=None,
            should_refresh_browser=False,
            should_auto_audition=False,
        )

    imported_paths = [
        item.destination_path
        for item in import_result.imported
        if item.destination_path is not None
    ]
    analysis = analyze_audio_paths_for_workbench(
        import_result.destination.source_root,
        imported_paths,
        progress_callback=progress_callback,
        should_cancel=should_cancel,
        use_cache=True,
        library_db_path=library_db_path,
        folder_id=import_result.destination.folder_id,
    )
    return ImportAnalyzeResult(
        import_result=import_result,
        analysis=analysis,
        should_refresh_browser=True,
        should_auto_audition=False,
    )


def format_inbound_status(result: ImportAnalyzeResult | InboundImportResult) -> str:
    """Human-readable inbound status without invented percentage claims."""
    inbound = result.import_result if isinstance(result, ImportAnalyzeResult) else result
    if inbound.error_code and not inbound.imported:
        return inbound.error_message or "Drop abgelehnt."
    parts = [
        f"Importiert: {len(inbound.imported)}",
        f"Konflikt: {len(inbound.skipped_conflict)}",
        f"Fehler: {len(inbound.failed)}",
    ]
    return " · ".join(parts)


def can_accept_sample_drop(
    node_id: str,
    *,
    library_db_path: Path | None = None,
) -> bool:
    return resolve_drop_destination(node_id, library_db_path=library_db_path).ok


__all__ = [
    "DestinationResolution",
    "DropDestination",
    "ImportAnalyzeResult",
    "InboundFileResult",
    "InboundImportResult",
    "can_accept_sample_drop",
    "copy_files_into_destination",
    "format_inbound_status",
    "import_and_analyze_dropped_files",
    "import_dropped_files",
    "outbound_local_file_url",
    "resolve_drop_destination",
]
