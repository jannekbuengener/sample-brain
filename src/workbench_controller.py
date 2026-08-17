"""Folder-scoped analysis for the local workbench (no DB required)."""

from __future__ import annotations

import csv
import json
import math
import os
import sqlite3
import textwrap
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePath
from typing import Any, Callable, Literal, Mapping

from .matching import DEFAULT_LIMIT, MatchCandidate, MatchProfile, match_candidates
from .native_audio import NativeAudioEngine

from .analyze import (
    SHORT_AUDIO_WARNING_CODE,
    extract_features,
    safe_load,
)
from .bpm_display import format_bpm_display, round_bpm_display
from .export_fl import MAX_TAGS, write_fl_tags_from_sample_rows
from .classify import rule_type
from .scan import iter_audio_files_stream, safe_audio_info
from .workbench_catalog import (
    DEFAULT_CATALOG_LOAD_LIMIT,
    catalog_available,
    count_catalog_samples,
    format_catalog_load_status,
    load_catalog_samples,
)
from .workbench_auto_metadata import apply_auto_metadata_after_analyze
from .workbench_library import (
    WORKBENCH_ANALYZER_VERSION,
    CachedWorkbenchRow,
    LibraryFolder,
    PlaylistSampleAddResult,
    WorkbenchCueMetadata,
    WorkbenchPlaylistValidationError,
    add_sample_to_playlist,
    get_or_create_playlist,
    get_playlist_by_name,
    list_library_folders,
    list_playlist_sample_paths,
    list_playlists,
    load_all_cached_samples,
    load_folder_samples,
    load_sample_by_path,
    load_sample_cue,
    lookup_sample,
    mark_folder_opened,
    normalize_display_name,
    register_library_folder,
    remove_library_folder,
    save_sample_cue,
    upsert_folder,
    upsert_sample,
    workbench_library_db_path,
)

ProgressPhase = Literal["scanning", "analyzing", "done", "error", "cancelled"]
ProgressCallback = Callable[[int, int, str, ProgressPhase], None]
ShouldCancel = Callable[[], bool]

WORKBENCH_GLOBAL_LIBRARY_TOKEN = "__workbench_all_library__"
WORKBENCH_CATALOG_LIBRARY_TOKEN = "__workbench_catalog_readonly__"
ALL_LIBRARY_VIEW_LABEL = "Alle Library-Samples"
CATALOG_VIEW_LABEL = "Catalog lesen"

ERROR_LABELS: dict[str, str] = {
    "audio_info_failed": "Datei-Metadaten konnten nicht gelesen werden",
    "unsupported_or_unreadable_audio": "Datei konnte nicht gelesen werden",
    "too_short_or_empty_audio": "Datei ist zu kurz oder leer",
    "feature_extract_failed": "Analyse fehlgeschlagen",
    "analysis_exception": "Unbekannter Analysefehler",
}

FOLDER_ERROR_MESSAGES: dict[str, str] = {
    "empty": "Kein Ordner ausgewählt",
    "not_found": "Ordner existiert nicht",
    "not_a_directory": "Pfad ist keine Ordner",
}


@dataclass
class WorkbenchFolderValidation:
    ok: bool
    normalized_path: Path | None
    error_code: str | None
    error_message: str | None


def format_path_display_lines(
    path: str,
    *,
    max_width: int = 48,
    head_segments: int = 2,
    tail_segments: int = 2,
) -> list[str]:
    """Format a filesystem path for the workbench detail panel.

    Short paths stay on one line. Longer paths collapse the middle; very long
    paths fall back to one segment per line with wrapped segment names.
    """
    stripped = path.strip()
    if not stripped:
        return ["—"]

    parts = list(PurePath(stripped).parts)
    if not parts:
        return ["—"]

    flat = "/".join(parts)
    if len(flat) <= max_width:
        return [flat]

    if len(parts) > head_segments + tail_segments:
        head = parts[:head_segments]
        tail = parts[-tail_segments:]
        collapsed = "/".join(head) + "/…/" + "/".join(tail)
        if len(collapsed) <= max_width:
            return [collapsed]

    lines: list[str] = []
    wrap_width = max(10, max_width - 2)
    for index, part in enumerate(parts):
        indent = "› " if index else "  "
        wrapped = textwrap.wrap(
            part,
            width=wrap_width,
            break_long_words=True,
            break_on_hyphens=False,
        ) or [part]
        for chunk_index, chunk in enumerate(wrapped):
            prefix = indent if chunk_index == 0 else "  "
            lines.append(f"{prefix}{chunk}")
    return lines


PATH_LIKE_DETAIL_KEYS = frozenset({"library_folder"})


def format_workbench_detail_field_lines(key: str, value: Any) -> list[str]:
    """Format one field in the workbench detail *Analyse* section."""
    if key in PATH_LIKE_DETAIL_KEYS and isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return [f"{key:16} —"]
        formatted = format_path_display_lines(stripped)
        if len(formatted) == 1:
            return [f"{key:16} {formatted[0]}"]
        return [f"{key}:", *formatted]
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    return [f"{key:16} {value}"]


def validate_workbench_folder(path_text: str) -> WorkbenchFolderValidation:
    """Validate a user-entered folder path for the workbench UI."""
    stripped = path_text.strip()
    if not stripped:
        return WorkbenchFolderValidation(
            ok=False,
            normalized_path=None,
            error_code="empty",
            error_message=FOLDER_ERROR_MESSAGES["empty"],
        )

    candidate = Path(stripped).expanduser()
    if not candidate.exists():
        return WorkbenchFolderValidation(
            ok=False,
            normalized_path=None,
            error_code="not_found",
            error_message=FOLDER_ERROR_MESSAGES["not_found"],
        )

    resolved = candidate.resolve()
    if not resolved.is_dir():
        return WorkbenchFolderValidation(
            ok=False,
            normalized_path=None,
            error_code="not_a_directory",
            error_message=FOLDER_ERROR_MESSAGES["not_a_directory"],
        )

    return WorkbenchFolderValidation(
        ok=True,
        normalized_path=resolved,
        error_code=None,
        error_message=None,
    )


@dataclass
class WorkbenchRow:
    display_name: str
    relative_path: str
    path: str
    bpm: float | None
    key: str | None
    key_conf: float | None
    loudness: float | None
    brightness: float | None
    sample_class: str | None
    pred_type: str | None
    status: str
    error: str | None = None
    error_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def playlist_fields(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "relative_path": self.relative_path,
            "bpm": self.bpm,
            "key": self.key,
            "key_conf": self.key_conf,
            "loudness": self.loudness,
            "brightness": self.brightness,
            "sample_class": self.sample_class,
            "pred_type": self.pred_type,
            "status": self.status,
            "error": self.error,
            "error_code": self.error_code,
        }


@dataclass
class WorkbenchResult:
    summary: dict[str, int]
    rows: list[WorkbenchRow]

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": dict(self.summary),
            "rows": [
                {
                    **row.playlist_fields(),
                    "path": row.path,
                    "details": dict(row.details),
                }
                for row in self.rows
            ],
        }


def error_message_for_code(code: str) -> str:
    return ERROR_LABELS.get(code, ERROR_LABELS["analysis_exception"])


def filter_workbench_rows(rows: list[WorkbenchRow], query: str) -> list[WorkbenchRow]:
    """Return rows whose playlist-visible fields match *query* (case-insensitive)."""
    needle = query.strip().casefold()
    if not needle:
        return list(rows)

    def _haystack(row: WorkbenchRow) -> str:
        parts = [
            row.display_name,
            row.relative_path,
            row.key or "",
            row.pred_type or "",
            row.sample_class or "",
            row.status,
            row.error or "",
        ]
        library_folder = row.details.get("library_folder")
        if library_folder:
            parts.append(str(library_folder))
            parts.append(Path(str(library_folder)).name)
        return " ".join(parts).casefold()

    return [row for row in rows if needle in _haystack(row)]


WorkbenchSourceFilter = Literal["all", "cache", "catalog"]
FILTER_ALL_LABEL = "alle"


@dataclass(frozen=True)
class WorkbenchRowFilters:
    source: WorkbenchSourceFilter = "all"
    pred_type: str | None = None
    key: str | None = None
    status: str | None = None
    min_bpm: float | None = None
    max_bpm: float | None = None

    def active(self) -> bool:
        return (
            self.source != "all"
            or _normalize_filter_value(self.pred_type) is not None
            or _normalize_filter_value(self.key) is not None
            or _normalize_filter_value(self.status) is not None
            or self.min_bpm is not None
            or self.max_bpm is not None
        )


def parse_workbench_bpm_bound(value: str | None) -> float | None:
    """Parse a BPM filter bound from user input; invalid values return None."""
    normalized = (value or "").strip()
    if not normalized:
        return None
    try:
        parsed = float(normalized.replace(",", "."))
    except ValueError:
        return None
    if parsed < 0:
        return None
    return parsed


def _normalize_filter_value(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or normalized.casefold() == FILTER_ALL_LABEL:
        return None
    return normalized


def row_source_kind(row: WorkbenchRow) -> Literal["cache", "catalog"]:
    """Return whether *row* came from catalog.db (read-only) or workbench cache."""
    if row.details.get("catalog_readonly"):
        return "catalog"
    return "cache"


def workbench_filter_options(rows: list[WorkbenchRow]) -> dict[str, tuple[str, ...]]:
    """Distinct type/class and key values from *rows* for filter dropdowns."""
    types: set[str] = set()
    keys: set[str] = set()
    for row in rows:
        for candidate in (row.pred_type, row.sample_class):
            if candidate and str(candidate).strip():
                types.add(str(candidate).strip())
        if row.key and str(row.key).strip():
            keys.add(str(row.key).strip())
    return {
        "types": tuple(sorted(types, key=str.casefold)),
        "keys": tuple(sorted(keys, key=str.casefold)),
    }


def apply_workbench_structured_filters(
    rows: list[WorkbenchRow],
    filters: WorkbenchRowFilters | None,
) -> list[WorkbenchRow]:
    """Return rows matching structured metadata filters (AND)."""
    if filters is None or not filters.active():
        return list(rows)

    pred_type = _normalize_filter_value(filters.pred_type)
    key = _normalize_filter_value(filters.key)
    status = _normalize_filter_value(filters.status)

    def _matches(row: WorkbenchRow) -> bool:
        if filters.source == "cache" and row_source_kind(row) != "cache":
            return False
        if filters.source == "catalog" and row_source_kind(row) != "catalog":
            return False
        if pred_type is not None:
            row_types = {
                value.strip().casefold()
                for value in (row.pred_type, row.sample_class)
                if value and str(value).strip()
            }
            if pred_type.casefold() not in row_types:
                return False
        if key is not None:
            row_key = (row.key or "").strip()
            if not row_key or row_key.casefold() != key.casefold():
                return False
        if status is not None:
            if row.status.casefold() != status.casefold():
                return False
        if filters.min_bpm is not None or filters.max_bpm is not None:
            if row.bpm is None:
                return False
            if filters.min_bpm is not None and row.bpm < filters.min_bpm:
                return False
            if filters.max_bpm is not None and row.bpm > filters.max_bpm:
                return False
        return True

    return [row for row in rows if _matches(row)]


def apply_workbench_filters(
    rows: list[WorkbenchRow],
    text_query: str,
    filters: WorkbenchRowFilters | None = None,
) -> list[WorkbenchRow]:
    """Apply text search then structured filters (AND composition)."""
    filtered = filter_workbench_rows(rows, text_query)
    return apply_workbench_structured_filters(filtered, filters)


def format_workbench_active_filter_summary(
    text_query: str,
    filters: WorkbenchRowFilters | None,
) -> str:
    """Return a compact active-filter hint, or empty string when none apply."""
    parts: list[str] = []
    text = (text_query or "").strip()
    if text:
        parts.append(f'Text="{text}"')
    if filters is not None:
        if filters.source == "cache":
            parts.append("Quelle=Cache")
        elif filters.source == "catalog":
            parts.append("Quelle=Catalog")
        pred_type = _normalize_filter_value(filters.pred_type)
        if pred_type is not None:
            parts.append(f"Type={pred_type}")
        key = _normalize_filter_value(filters.key)
        if key is not None:
            parts.append(f"Key={key}")
        status = _normalize_filter_value(filters.status)
        if status is not None:
            parts.append(f"Status={status}")
        if filters.min_bpm is not None or filters.max_bpm is not None:
            if filters.min_bpm is not None and filters.max_bpm is not None:
                parts.append(
                    f"BPM {format_bpm_display(filters.min_bpm)}–{format_bpm_display(filters.max_bpm)}"
                )
            elif filters.min_bpm is not None:
                parts.append(f"BPM ab {format_bpm_display(filters.min_bpm)}")
            elif filters.max_bpm is not None:
                parts.append(f"BPM bis {format_bpm_display(filters.max_bpm)}")
    if not parts:
        return ""
    return "Aktive Filter: " + " · ".join(parts)


PLAYLIST_SORT_COLUMNS = frozenset(
    {"name", "bpm", "key", "key_conf", "loudness", "brightness", "pred_type", "status"}
)


def _sort_key_for_column(row: WorkbenchRow, column: str) -> tuple:
    if column == "name":
        return (row.display_name.casefold(),)
    if column == "bpm":
        return (row.bpm is None, row.bpm if row.bpm is not None else 0.0)
    if column == "key":
        return (row.key is None, (row.key or "").casefold())
    if column == "key_conf":
        return (row.key_conf is None, row.key_conf if row.key_conf is not None else 0.0)
    if column == "loudness":
        return (row.loudness is None, row.loudness if row.loudness is not None else 0.0)
    if column == "brightness":
        return (
            row.brightness is None,
            row.brightness if row.brightness is not None else 0.0,
        )
    if column == "pred_type":
        value = row.pred_type or row.sample_class or ""
        return (not value, value.casefold())
    if column == "status":
        return (row.status.casefold(),)
    raise ValueError(f"Unsupported sort column: {column}")


def sort_workbench_rows(
    rows: list[WorkbenchRow],
    column: str,
    *,
    reverse: bool = False,
) -> list[WorkbenchRow]:
    """Return a new list sorted by playlist column *column*."""
    if column not in PLAYLIST_SORT_COLUMNS:
        raise ValueError(f"Unsupported sort column: {column}")
    return sorted(
        rows, key=lambda row: _sort_key_for_column(row, column), reverse=reverse
    )


def _format_optional(value: float | None, *, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _collect_audio_paths(root: Path, limit: int | None) -> list[Path]:
    paths: list[Path] = []
    for audio_path in iter_audio_files_stream([root]):
        paths.append(audio_path)
        if limit is not None and len(paths) >= limit:
            break
    return paths


def _diagnose_failure(path: Path) -> tuple[str, str]:
    try:
        if not path.is_file():
            return "unsupported_or_unreadable_audio", "file not found"
        if path.stat().st_size == 0:
            return "too_short_or_empty_audio", "file size is zero"
    except OSError as exc:
        return "analysis_exception", str(exc)

    sr, ch, dur = safe_audio_info(path)
    if sr is None and ch is None and dur is None:
        y, _load_sr = safe_load(path)
        if y is None:
            return "unsupported_or_unreadable_audio", "audio decode failed"
        if y.size == 0:
            return "too_short_or_empty_audio", "empty waveform"
        return "audio_info_failed", "metadata unreadable"

    y, _load_sr = safe_load(path)
    if y is None:
        return "unsupported_or_unreadable_audio", "audio decode failed"
    if y.size == 0:
        return "too_short_or_empty_audio", "empty waveform"
    return "feature_extract_failed", "feature pipeline returned no result"


def _make_error_row(
    *,
    display_name: str,
    rel: str,
    path: Path,
    error_code: str,
    error_detail: str,
) -> WorkbenchRow:
    details = {
        "path": str(path),
        "relative_path": rel,
        "error_code": error_code,
        "error_detail": error_detail,
    }
    return WorkbenchRow(
        display_name=display_name,
        relative_path=rel,
        path=str(path),
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class=None,
        pred_type=None,
        status="error",
        error=error_message_for_code(error_code),
        error_code=error_code,
        details=details,
    )


def _emit_progress(
    callback: ProgressCallback | None,
    current: int,
    total: int,
    display_name: str,
    phase: ProgressPhase,
) -> None:
    if callback is not None:
        callback(current, total, display_name, phase)


def _file_stat(audio_path: Path) -> tuple[int, int] | None:
    try:
        st = audio_path.stat()
        return st.st_size, st.st_mtime_ns
    except OSError:
        return None


def analyze_folder_for_workbench(
    folder: Path | str,
    limit: int | None = None,
    progress_callback: ProgressCallback | None = None,
    should_cancel: ShouldCancel | None = None,
    *,
    use_cache: bool = True,
    library_db_path: Path | None = None,
) -> WorkbenchResult:
    """Scan *folder* for audio files, analyze each, and return playlist rows."""
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    def _cancelled() -> bool:
        return should_cancel is not None and should_cancel()

    cache_db = (
        library_db_path if library_db_path is not None else workbench_library_db_path()
    )
    folder_id: int | None = None
    if use_cache:
        folder_id = upsert_folder(root, db_path=cache_db)

    _emit_progress(progress_callback, 0, 0, "", "scanning")
    if _cancelled():
        _emit_progress(progress_callback, 0, 0, "", "cancelled")
        return WorkbenchResult(
            summary={
                "files_found": 0,
                "analyzed_count": 0,
                "error_count": 0,
                "cache_hits": 0,
                "cache_misses": 0,
                "cancelled": 1,
            },
            rows=[],
        )

    audio_paths = _collect_audio_paths(root, limit)
    total = len(audio_paths)

    rows: list[WorkbenchRow] = []
    analyzed_count = 0
    error_count = 0
    cache_hits = 0
    cache_misses = 0

    for index, audio_path in enumerate(audio_paths, start=1):
        if _cancelled():
            _emit_progress(progress_callback, index - 1, total, "", "cancelled")
            break
        rel = str(audio_path.relative_to(root))
        display_name = normalize_display_name(audio_path.name)
        _emit_progress(progress_callback, index, total, display_name, "analyzing")

        stat = _file_stat(audio_path)
        if use_cache and folder_id is not None and stat is not None:
            size_bytes, mtime_ns = stat
            cached = lookup_sample(audio_path, size_bytes, mtime_ns, db_path=cache_db)
            if cached is not None:
                row = cached.to_workbench_row()
                rows.append(row)
                cache_hits += 1
                if row.status == "error":
                    error_count += 1
                else:
                    analyzed_count += 1
                phase: ProgressPhase = "error" if row.status == "error" else "done"
                _emit_progress(progress_callback, index, total, display_name, phase)
                continue

        if use_cache:
            cache_misses += 1

        try:
            sr, ch, dur = safe_audio_info(audio_path)
            feats = extract_features(audio_path, dur)
            if feats is None:
                error_code, error_detail = _diagnose_failure(audio_path)
                error_count += 1
                row = _make_error_row(
                    display_name=display_name,
                    rel=rel,
                    path=audio_path,
                    error_code=error_code,
                    error_detail=error_detail,
                )
                rows.append(row)
                if use_cache and folder_id is not None and stat is not None:
                    upsert_sample(
                        folder_id,
                        row,
                        size_bytes=stat[0],
                        mtime_ns=stat[1],
                        db_path=cache_db,
                        analyzer_version=WORKBENCH_ANALYZER_VERSION,
                    )
                _emit_progress(progress_callback, index, total, display_name, "error")
                continue

            tags = rule_type(
                dur, feats.loudness, feats.brightness, feats.mfcc_mean, feats.clazz
            )
            pred_type = tags[0] if tags else None
            details: dict[str, Any] = {
                "path": str(audio_path),
                "relative_path": rel,
                "duration_sec": _format_optional(dur, digits=3),
                "samplerate": sr,
                "channels": ch,
                "bpm": round_bpm_display(feats.bpm),
                "key": feats.key,
                "key_conf": _format_optional(feats.key_conf, digits=3),
                "loudness_dbfs": _format_optional(feats.loudness, digits=2),
                "brightness_hz": _format_optional(feats.brightness, digits=1),
                "class": feats.clazz,
                "pred_type": pred_type,
                "tags": tags,
            }
            if feats.quality_note:
                details["short_audio_warning"] = feats.quality_note
                details["short_audio_warning_code"] = SHORT_AUDIO_WARNING_CODE

            row = WorkbenchRow(
                display_name=display_name,
                relative_path=rel,
                path=str(audio_path),
                bpm=feats.bpm,
                key=feats.key,
                key_conf=feats.key_conf,
                loudness=feats.loudness,
                brightness=feats.brightness,
                sample_class=feats.clazz,
                pred_type=pred_type,
                status="ok",
                details=details,
            )
            rows.append(row)
            analyzed_count += 1
            if use_cache and folder_id is not None and stat is not None:
                upsert_sample(
                    folder_id,
                    row,
                    size_bytes=stat[0],
                    mtime_ns=stat[1],
                    db_path=cache_db,
                    analyzer_version=WORKBENCH_ANALYZER_VERSION,
                )
                apply_auto_metadata_after_analyze(row, library_db_path=cache_db)
            _emit_progress(progress_callback, index, total, display_name, "done")
        except Exception as exc:
            error_count += 1
            detail = str(exc).strip() or "unexpected exception"
            row = _make_error_row(
                display_name=display_name,
                rel=rel,
                path=audio_path,
                error_code="analysis_exception",
                error_detail=detail[:200],
            )
            rows.append(row)
            if use_cache and folder_id is not None and stat is not None:
                upsert_sample(
                    folder_id,
                    row,
                    size_bytes=stat[0],
                    mtime_ns=stat[1],
                    db_path=cache_db,
                    analyzer_version=WORKBENCH_ANALYZER_VERSION,
                )
            _emit_progress(progress_callback, index, total, display_name, "error")

    summary: dict[str, int] = {
        "files_found": total,
        "analyzed_count": analyzed_count,
        "error_count": error_count,
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
    }
    if _cancelled():
        summary["cancelled"] = 1
    return WorkbenchResult(summary=summary, rows=rows)


def row_as_dict(row: WorkbenchRow) -> dict[str, Any]:
    return asdict(row)


PLAYLIST_CSV_FIELDS: tuple[str, ...] = (
    "display_name",
    "relative_path",
    "path",
    "bpm",
    "key",
    "key_conf",
    "loudness",
    "brightness",
    "sample_class",
    "pred_type",
    "status",
    "error",
    "error_code",
)


def export_workbench_rows_to_csv(rows: list[WorkbenchRow], destination: Path) -> int:
    """Write playlist rows to a UTF-8 CSV file. Returns the number of rows written."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAYLIST_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            data = row_as_dict(row)
            displayed_bpm = round_bpm_display(data.get("bpm"))
            if displayed_bpm is not None:
                data["bpm"] = displayed_bpm
            writer.writerow(
                {field: data.get(field, "") for field in PLAYLIST_CSV_FIELDS}
            )
    return len(rows)


@dataclass(frozen=True)
class WorkbenchFlExportResult:
    ok: bool
    exported_count: int = 0
    skipped_count: int = 0
    tags_path: Path | None = None
    error_message: str | None = None
    warnings: tuple[str, ...] = ()


def _workbench_row_duration_sec(row: WorkbenchRow) -> float | None:
    raw = row.details.get("duration_sec")
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def workbench_row_to_fl_sample_row(row: WorkbenchRow) -> tuple | None:
    """Map a workbench row to the export_fl sample-row tuple, or None if not exportable."""
    if row.status != "ok" or not row.path:
        return None
    return (
        row.path,
        row.relative_path or None,
        _workbench_row_duration_sec(row),
        row.brightness,
        row.loudness,
        row.sample_class,
        row.key,
        row.key_conf,
        row.bpm,
        row.pred_type,
    )


def workbench_rows_for_fl_export(rows: list[WorkbenchRow]) -> list[WorkbenchRow]:
    """Return playlist rows eligible for FL tag export."""
    return [row for row in rows if workbench_row_to_fl_sample_row(row) is not None]


def _configured_path_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.startswith("<"):
        return None
    return text


def resolve_workbench_fl_user_data_path(
    *,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Resolve FL Studio user data path from env override or profile config."""
    env_map = os.environ if env is None else env
    override = _configured_path_value(env_map.get("SAMPLE_BRAIN_FL_USER_DATA"))
    if override:
        return override
    try:
        from .config_loader import resolve_profile

        cfg = resolve_profile(env=env_map)
    except Exception:
        return None
    return _configured_path_value(cfg.get("fl_user_data_path"))


def resolve_workbench_fl_export_roots(
    *,
    env: Mapping[str, str] | None = None,
) -> list[Path]:
    """Resolve library roots used for FL export path resolution."""
    env_map = os.environ if env is None else env
    try:
        from .config_loader import resolve_profile

        cfg = resolve_profile(env=env_map)
        roots = cfg.get("library_roots", [])
        if isinstance(roots, list):
            return [Path(root) for root in roots if str(root).strip()]
    except Exception:
        pass
    from .config import SAMPLE_ROOTS

    return [Path(root) for root in SAMPLE_ROOTS]


def resolve_workbench_fl_export_max_tags(
    *,
    env: Mapping[str, str] | None = None,
) -> int:
    env_map = os.environ if env is None else env
    override = env_map.get("SAMPLE_BRAIN_MAX_TAGS")
    if override and str(override).strip().isdigit():
        return int(str(override).strip())
    try:
        from .config_loader import resolve_profile

        cfg = resolve_profile(env=env_map)
        configured = cfg.get("export", {}).get("max_tags")
        if isinstance(configured, int) and configured > 0:
            return configured
    except Exception:
        pass
    return MAX_TAGS


def export_workbench_rows_to_fl_tags(
    rows: list[WorkbenchRow],
    fl_user_data: str | Path,
    *,
    roots: list[Path] | None = None,
    max_tags: int | None = None,
) -> WorkbenchFlExportResult:
    """Export visible workbench rows to FL Studio Browser tags."""
    fl_path_text = str(fl_user_data).strip()
    if not fl_path_text:
        return WorkbenchFlExportResult(
            ok=False,
            error_message="FL User Data Pfad fehlt.",
        )

    exportable = workbench_rows_for_fl_export(rows)
    if not exportable:
        return WorkbenchFlExportResult(
            ok=False,
            error_message="Keine exportierbaren Playlist-Zeilen vorhanden.",
        )

    sample_rows = []
    for row in exportable:
        mapped = workbench_row_to_fl_sample_row(row)
        if mapped is not None:
            sample_rows.append(mapped)
    if not sample_rows:
        return WorkbenchFlExportResult(
            ok=False,
            error_message="Keine exportierbaren Playlist-Zeilen vorhanden.",
        )

    resolved_roots = (
        list(roots) if roots is not None else resolve_workbench_fl_export_roots()
    )
    tag_limit = (
        max_tags if max_tags is not None else resolve_workbench_fl_export_max_tags()
    )
    try:
        tags_path, exported_count, warnings = write_fl_tags_from_sample_rows(
            sample_rows,
            Path(fl_path_text),
            resolved_roots,
            max_tags=tag_limit,
        )
    except OSError as exc:
        return WorkbenchFlExportResult(
            ok=False,
            error_message=f"FL-Export fehlgeschlagen: {exc}",
        )

    return WorkbenchFlExportResult(
        ok=True,
        exported_count=exported_count,
        skipped_count=len(rows) - exported_count,
        tags_path=tags_path,
        warnings=tuple(warnings),
    )


def workbench_state_dir(*, env: Mapping[str, str] | None = None) -> Path:
    """Return the user-local directory for workbench UI state."""
    env_map = os.environ if env is None else env
    override = env_map.get("SAMPLE_BRAIN_WORKBENCH_STATE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".sample-brain").resolve()


def workbench_last_folder_file(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return base / "workbench_last_folder.txt"


def load_workbench_last_folder(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> str | None:
    """Load the last validated workbench folder path, or None if missing/invalid."""
    path_file = workbench_last_folder_file(state_dir=state_dir, env=env)
    if not path_file.is_file():
        return None
    try:
        text = path_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    validation = validate_workbench_folder(text)
    if not validation.ok:
        return None
    assert validation.normalized_path is not None
    return str(validation.normalized_path)


def save_workbench_last_folder(
    folder: str | Path,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Persist the last workbench folder path after validation."""
    validation = validate_workbench_folder(str(folder))
    if not validation.ok:
        return False
    assert validation.normalized_path is not None
    path_file = workbench_last_folder_file(state_dir=state_dir, env=env)
    try:
        path_file.parent.mkdir(parents=True, exist_ok=True)
        path_file.write_text(str(validation.normalized_path), encoding="utf-8")
    except OSError:
        return False
    return True


DEFAULT_WORKBENCH_ANALYSIS_LIMIT_TEXT = "50"


def workbench_analysis_limit_file(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return base / "workbench_analysis_limit.txt"


def normalize_workbench_analysis_limit_text(raw: str) -> str:
    """Return UI-safe analysis limit text: empty for no limit, else a positive int string."""
    text = raw.strip()
    if not text:
        return ""
    try:
        value = int(text)
    except ValueError:
        return DEFAULT_WORKBENCH_ANALYSIS_LIMIT_TEXT
    if value <= 0:
        return DEFAULT_WORKBENCH_ANALYSIS_LIMIT_TEXT
    return str(value)


def load_workbench_analysis_limit(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """Load persisted analysis limit for the workbench UI; invalid/missing falls back to default."""
    path_file = workbench_analysis_limit_file(state_dir=state_dir, env=env)
    if not path_file.is_file():
        return DEFAULT_WORKBENCH_ANALYSIS_LIMIT_TEXT
    try:
        text = path_file.read_text(encoding="utf-8")
    except OSError:
        return DEFAULT_WORKBENCH_ANALYSIS_LIMIT_TEXT
    return normalize_workbench_analysis_limit_text(text)


def save_workbench_analysis_limit(
    limit_text: str,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Persist analysis limit field value when empty or a positive integer."""
    text = limit_text.strip()
    if not text:
        persisted = ""
    else:
        try:
            value = int(text)
        except ValueError:
            return False
        if value <= 0:
            return False
        persisted = str(value)
    path_file = workbench_analysis_limit_file(state_dir=state_dir, env=env)
    try:
        path_file.parent.mkdir(parents=True, exist_ok=True)
        path_file.write_text(persisted, encoding="utf-8")
    except OSError:
        return False
    return True


@dataclass(frozen=True)
class WorkbenchViewSettings:
    show_view_toolbar: bool = True
    show_search: bool = True
    show_filters: bool = True
    show_library_manage: bool = True
    show_waveform_tools: bool = True


DEFAULT_WORKBENCH_VIEW_SETTINGS = WorkbenchViewSettings()

VIEW_SECTION_SEARCH = "search"
VIEW_SECTION_FILTERS = "filters"
VIEW_SECTION_LIBRARY_MANAGE = "library_manage"
VIEW_SECTION_WAVEFORM_TOOLS = "waveform_tools"

WORKBENCH_VIEW_TOGGLE_HELP = "Suche, Filter, Library-Verwaltung und Waveform-Werkzeuge können ein- und ausgeblendet werden."


def workbench_view_settings_file(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return base / "workbench_view_settings.json"


def _view_settings_from_mapping(data: Mapping[str, Any]) -> WorkbenchViewSettings:
    def _bool(key: str, default: bool) -> bool:
        value = data.get(key, default)
        return default if not isinstance(value, bool) else value

    return WorkbenchViewSettings(
        show_view_toolbar=_bool("show_view_toolbar", True),
        show_search=_bool("show_search", True),
        show_filters=_bool("show_filters", True),
        show_library_manage=_bool("show_library_manage", True),
        show_waveform_tools=_bool("show_waveform_tools", True),
    )


def load_workbench_view_settings(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> WorkbenchViewSettings:
    """Load persisted view visibility; invalid files fall back to defaults."""
    path_file = workbench_view_settings_file(state_dir=state_dir, env=env)
    if not path_file.is_file():
        return DEFAULT_WORKBENCH_VIEW_SETTINGS
    try:
        raw = json.loads(path_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return DEFAULT_WORKBENCH_VIEW_SETTINGS
    if not isinstance(raw, dict):
        return DEFAULT_WORKBENCH_VIEW_SETTINGS
    return _view_settings_from_mapping(raw)


def save_workbench_view_settings(
    settings: WorkbenchViewSettings,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Persist workbench view visibility to user-local state."""
    path_file = workbench_view_settings_file(state_dir=state_dir, env=env)
    try:
        path_file.parent.mkdir(parents=True, exist_ok=True)
        path_file.write_text(
            json.dumps(asdict(settings), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return False
    return True


def effective_workbench_text_query(raw_query: str, *, search_visible: bool) -> str:
    """Return text query only when the search bar is visible."""
    if not search_visible:
        return ""
    return raw_query


def effective_workbench_row_filters(
    filters: WorkbenchRowFilters | None,
    *,
    filters_visible: bool,
) -> WorkbenchRowFilters | None:
    """Return structured filters only when the filter bar is visible."""
    if not filters_visible:
        return None
    return filters


def format_workbench_view_section_hidden_status(section: str) -> str:
    """Status line after hiding a view section."""
    messages = {
        VIEW_SECTION_SEARCH: "Suche ausgeblendet und zurückgesetzt",
        VIEW_SECTION_FILTERS: "Filter ausgeblendet und zurückgesetzt",
        VIEW_SECTION_LIBRARY_MANAGE: "Library-Verwaltung ausgeblendet",
        VIEW_SECTION_WAVEFORM_TOOLS: "Waveform-Werkzeuge ausgeblendet",
    }
    return messages.get(section, "Ansicht aktualisiert")


def format_workbench_view_restore_status() -> str:
    return "Standardansicht wiederhergestellt"


def format_workbench_view_toolbar_hidden_status() -> str:
    return "Ansichtsleiste ausgeblendet"


def format_workbench_view_toolbar_shown_status() -> str:
    return "Ansichtsleiste eingeblendet"


def get_workbench_library_folders(
    *,
    library_db_path: Path | None = None,
) -> list[LibraryFolder]:
    """Return folders registered in the workbench library cache."""
    db = library_db_path if library_db_path is not None else workbench_library_db_path()
    return list_library_folders(db_path=db)


def add_workbench_library_folder(
    folder: Path | str,
    *,
    library_db_path: Path | None = None,
) -> int:
    """Register a folder in the workbench library without analyzing it."""
    db = library_db_path if library_db_path is not None else workbench_library_db_path()
    return register_library_folder(folder, db_path=db)


def remove_workbench_library_folder(
    folder_id_or_path: int | str | Path,
    *,
    library_db_path: Path | None = None,
) -> bool:
    """Remove folder metadata and cached samples from the workbench library."""
    db = library_db_path if library_db_path is not None else workbench_library_db_path()
    return remove_library_folder(folder_id_or_path, db_path=db)


def load_cached_folder_rows(
    folder: Path | str,
    *,
    library_db_path: Path | None = None,
) -> list[WorkbenchRow]:
    """Load cached analysis rows for a library folder, if any."""
    db = library_db_path if library_db_path is not None else workbench_library_db_path()
    mark_folder_opened(folder, db_path=db)
    cached = load_folder_samples(folder, db_path=db)
    return [row.to_workbench_row() for row in cached]


def load_all_cached_rows(
    *,
    library_db_path: Path | None = None,
) -> list[WorkbenchRow]:
    """Load cached analysis rows from every registered workbench library folder."""
    db = library_db_path if library_db_path is not None else workbench_library_db_path()
    cached = load_all_cached_samples(db_path=db)
    return [row.to_workbench_row() for row in cached]


def is_catalog_readonly_row(row: WorkbenchRow) -> bool:
    """Return True when *row* was loaded from catalog.db (no cue/loop writes)."""
    return bool(row.details.get("catalog_readonly"))


CATALOG_READONLY_EDIT_MESSAGE = (
    "Catalog-Zeile read-only — Cue/Loop/Attack werden hier nicht gespeichert."
)
CATALOG_READONLY_STATUS_HINT = (
    "Catalog read-only — Cue/Loop/Attack werden hier nicht gespeichert."
)


def catalog_row_display_name(row: WorkbenchRow) -> str:
    """Playlist label for catalog rows (visual distinction without changing filter keys)."""
    if is_catalog_readonly_row(row):
        return f"⧉ {row.display_name}"
    return row.display_name


def append_catalog_readonly_status_hint(message: str) -> str:
    """Append the standard catalog read-only edit hint to a load status line."""
    if CATALOG_READONLY_STATUS_HINT in message:
        return message
    return f"{message} {CATALOG_READONLY_STATUS_HINT}"


WorkbenchSearchMode = Literal["folder", "global_library", "catalog"]


@dataclass(frozen=True)
class WorkbenchSearchStatusContext:
    mode: WorkbenchSearchMode
    loaded_count: int
    visible_count: int
    filters_active: bool = False
    catalog_total: int | None = None
    catalog_load_limit: int | None = None
    folder_count: int | None = None


def format_workbench_search_status(ctx: WorkbenchSearchStatusContext) -> str:
    """Build a unified workbench search/filter status line for the status bar."""
    if ctx.mode == "catalog":
        return _format_catalog_search_status(ctx)
    if ctx.mode == "global_library":
        return _format_global_library_search_status(ctx)
    return _format_folder_search_status(ctx)


def _format_folder_search_status(ctx: WorkbenchSearchStatusContext) -> str:
    if ctx.filters_active:
        return f"Ordner: {ctx.visible_count} von {ctx.loaded_count} Treffer"
    return f"Ordner: {ctx.loaded_count} Samples"


def _format_global_library_search_status(ctx: WorkbenchSearchStatusContext) -> str:
    if ctx.filters_active:
        return (
            f"Alle Library-Samples: {ctx.visible_count} von {ctx.loaded_count} Treffer"
        )
    if ctx.folder_count and ctx.folder_count > 0:
        return (
            f"Alle Library-Samples: {ctx.loaded_count} Samples "
            f"aus {ctx.folder_count} Ordner(n)"
        )
    return f"Alle Library-Samples: {ctx.loaded_count} Samples"


def _format_catalog_search_status(ctx: WorkbenchSearchStatusContext) -> str:
    loaded = ctx.loaded_count
    total = ctx.catalog_total if ctx.catalog_total is not None else loaded
    limit_active = (
        ctx.catalog_load_limit is not None
        and ctx.catalog_total is not None
        and ctx.catalog_total > ctx.catalog_load_limit
    )
    if ctx.filters_active:
        base = f"Catalog-Samples: {loaded}"
        if total > loaded:
            base += f" von {total}"
        base += f" geladen, {ctx.visible_count} Treffer"
        hints = ["read-only"]
        if limit_active:
            hints.append("Limit aktiv")
        return f"{base} ({', '.join(hints)})"
    return format_catalog_load_status(
        loaded,
        total,
        limit=ctx.catalog_load_limit if limit_active else None,
    )


CatalogImportConflictPolicy = Literal[
    "skip_existing", "overwrite_analysis_only", "cancel_on_conflict"
]

CatalogImportAction = Literal[
    "import", "skip_up_to_date", "skip_existing", "conflict", "error"
]


@dataclass(frozen=True)
class CatalogImportPreviewItem:
    path: str
    display_name: str
    action: CatalogImportAction
    message: str | None = None


@dataclass
class CatalogImportPreview:
    items: list[CatalogImportPreviewItem]
    target_folder: str | None
    folder_registered: bool
    error_message: str | None = None

    @property
    def import_count(self) -> int:
        return sum(1 for item in self.items if item.action == "import")

    @property
    def skip_count(self) -> int:
        return sum(
            1
            for item in self.items
            if item.action in ("skip_up_to_date", "skip_existing")
        )

    @property
    def conflict_count(self) -> int:
        return sum(1 for item in self.items if item.action == "conflict")

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.items if item.action == "error")


@dataclass
class CatalogImportResult:
    imported: int = 0
    skipped: int = 0
    conflicts: int = 0
    errors: int = 0
    cancelled: bool = False
    error_message: str | None = None


def _resolve_registered_folder_id(
    folder: Path | str,
    *,
    library_db_path: Path,
) -> int | None:
    path = str(Path(folder).expanduser().resolve())
    for entry in list_library_folders(db_path=library_db_path):
        if entry.path == path:
            return entry.id
    return None


def _file_stat_for_import(path: str) -> tuple[int, int]:
    candidate = Path(path).expanduser()
    if candidate.is_file():
        stat = candidate.stat()
        return stat.st_size, stat.st_mtime_ns
    return 0, 0


def _analysis_fields_equal(
    catalog_row: WorkbenchRow,
    cached_row: CachedWorkbenchRow,
) -> bool:
    if catalog_row.status != cached_row.status:
        return False
    if catalog_row.pred_type != cached_row.pred_type:
        return False
    if catalog_row.sample_class != cached_row.sample_class:
        return False
    if catalog_row.key != cached_row.key:
        return False
    if catalog_row.bpm is None and cached_row.bpm is None:
        pass
    elif catalog_row.bpm is not None and cached_row.bpm is not None:
        if abs(catalog_row.bpm - cached_row.bpm) > 0.05:
            return False
    else:
        return False
    return True


def _catalog_row_for_cache_import(
    row: WorkbenchRow,
    *,
    target_folder: Path,
) -> WorkbenchRow:
    sample_path = Path(row.path).expanduser().resolve()
    try:
        relative_path = str(sample_path.relative_to(target_folder.resolve()))
    except ValueError:
        relative_path = row.relative_path or sample_path.name
    details = {
        key: value
        for key, value in row.details.items()
        if key not in ("source", "catalog_readonly", "library_folder")
    }
    return WorkbenchRow(
        display_name=row.display_name,
        relative_path=relative_path,
        path=str(sample_path),
        bpm=row.bpm,
        key=row.key,
        key_conf=row.key_conf,
        loudness=row.loudness,
        brightness=row.brightness,
        sample_class=row.sample_class,
        pred_type=row.pred_type,
        status=row.status,
        error=row.error,
        error_code=row.error_code,
        details=details,
    )


def _classify_catalog_import_item(
    row: WorkbenchRow,
    *,
    library_db_path: Path,
) -> CatalogImportPreviewItem:
    if not is_catalog_readonly_row(row):
        return CatalogImportPreviewItem(
            path=row.path,
            display_name=row.display_name,
            action="error",
            message="Keine Catalog-Zeile",
        )
    cached = load_sample_by_path(row.path, db_path=library_db_path)
    if cached is None:
        return CatalogImportPreviewItem(
            path=row.path,
            display_name=row.display_name,
            action="import",
        )
    if _analysis_fields_equal(row, cached):
        return CatalogImportPreviewItem(
            path=row.path,
            display_name=row.display_name,
            action="skip_up_to_date",
            message="Bereits im Cache",
        )
    return CatalogImportPreviewItem(
        path=row.path,
        display_name=row.display_name,
        action="conflict",
        message="Abweichende Analyse im Cache",
    )


def preview_catalog_import(
    rows: list[WorkbenchRow],
    target_folder: Path | str,
    *,
    library_db_path: Path | None = None,
) -> CatalogImportPreview:
    """Preview catalog→cache import without writing."""
    db = library_db_path if library_db_path is not None else workbench_library_db_path()
    folder = Path(target_folder).expanduser().resolve()
    folder_id = _resolve_registered_folder_id(folder, library_db_path=db)
    if folder_id is None:
        return CatalogImportPreview(
            items=[],
            target_folder=str(folder),
            folder_registered=False,
            error_message=(
                "Zielordner ist nicht in der Workbench-Library registriert."
            ),
        )
    if not rows:
        return CatalogImportPreview(
            items=[],
            target_folder=str(folder),
            folder_registered=True,
            error_message="Keine Catalog-Zeilen zum Importieren.",
        )
    items = [_classify_catalog_import_item(row, library_db_path=db) for row in rows]
    return CatalogImportPreview(
        items=items,
        target_folder=str(folder),
        folder_registered=True,
    )


def format_catalog_import_preview_message(preview: CatalogImportPreview) -> str:
    """User-facing confirmation text for catalog import."""
    if preview.error_message:
        return preview.error_message
    lines = [
        f"Zielordner: {preview.target_folder}",
        f"Importieren: {preview.import_count}",
        f"Überspringen (aktuell): {preview.skip_count}",
        f"Konflikte: {preview.conflict_count}",
    ]
    if preview.error_count:
        lines.append(f"Ungültige Zeilen: {preview.error_count}")
    lines.append("")
    lines.append(
        "Cue/Loop/Attack im Cache bleiben erhalten. " "catalog.db wird nicht verändert."
    )
    lines.append("")
    lines.append("Import starten?")
    return "\n".join(lines)


def format_catalog_import_result_message(result: CatalogImportResult) -> str:
    """User-facing summary after catalog import."""
    if result.cancelled:
        base = "Import abgebrochen."
        if result.error_message:
            return f"{base}\n{result.error_message}"
        return base
    return (
        f"Importiert: {result.imported}\n"
        f"Übersprungen: {result.skipped}\n"
        f"Konflikte (nicht importiert): {result.conflicts}\n"
        f"Fehler: {result.errors}"
    )


def import_catalog_rows_to_cache(
    rows: list[WorkbenchRow],
    target_folder: Path | str,
    *,
    conflict_policy: CatalogImportConflictPolicy = "overwrite_analysis_only",
    library_db_path: Path | None = None,
) -> CatalogImportResult:
    """Copy catalog metadata rows into workbench_library.db (cache only)."""
    preview = preview_catalog_import(
        rows,
        target_folder,
        library_db_path=library_db_path,
    )
    if preview.error_message and not preview.items:
        return CatalogImportResult(
            cancelled=True,
            error_message=preview.error_message,
        )
    if preview.conflict_count > 0 and conflict_policy == "cancel_on_conflict":
        return CatalogImportResult(
            cancelled=True,
            conflicts=preview.conflict_count,
            error_message="Import wegen Konflikten abgebrochen.",
        )

    db = library_db_path if library_db_path is not None else workbench_library_db_path()
    folder = Path(target_folder).expanduser().resolve()
    folder_id = _resolve_registered_folder_id(folder, library_db_path=db)
    if folder_id is None:
        return CatalogImportResult(
            cancelled=True,
            error_message=preview.error_message,
        )

    imported = 0
    skipped = 0
    conflicts = 0
    errors = 0

    for item in preview.items:
        if item.action == "error":
            errors += 1
            continue
        if item.action == "skip_up_to_date":
            skipped += 1
            continue
        if item.action == "skip_existing":
            skipped += 1
            continue
        if item.action == "conflict":
            if conflict_policy == "skip_existing":
                conflicts += 1
                skipped += 1
                continue
            if conflict_policy == "cancel_on_conflict":
                conflicts += 1
                continue

        source_row = next((row for row in rows if row.path == item.path), None)
        if source_row is None:
            errors += 1
            continue

        cache_row = _catalog_row_for_cache_import(
            source_row,
            target_folder=folder,
        )
        size_bytes, mtime_ns = _file_stat_for_import(cache_row.path)
        if size_bytes == 0 and source_row.details.get("size_bytes") is not None:
            size_bytes = int(source_row.details["size_bytes"])
        try:
            upsert_sample(
                folder_id,
                cache_row,
                size_bytes=size_bytes,
                mtime_ns=mtime_ns,
                db_path=db,
                analyzer_version=WORKBENCH_ANALYZER_VERSION,
            )
        except (TypeError, sqlite3.Error, OSError):
            errors += 1
            continue
        imported += 1

    return CatalogImportResult(
        imported=imported,
        skipped=skipped,
        conflicts=conflicts,
        errors=errors,
    )


def load_catalog_rows(
    *,
    catalog_path: Path | str | None = None,
    limit: int | None = None,
) -> list[WorkbenchRow]:
    """Load read-only catalog samples for workbench display."""
    catalog_rows = load_catalog_samples(catalog_path, limit=limit)
    return [row.to_workbench_row() for row in catalog_rows]


_PROVENANCE_SOURCE_UI: dict[str, str] = {
    "detected": "erkannt",
    "manual": "manuell",
}


def format_metadata_provenance_label(source: str | None) -> str | None:
    """Map provenance source token to German UI label, or None when not shown."""
    if source is None:
        return None
    key = str(source).strip().lower()
    if not key:
        return None
    return _PROVENANCE_SOURCE_UI.get(key)


def _should_show_cue_provenance(metadata: WorkbenchCueMetadata) -> bool:
    if metadata.cue_source == "detected":
        return True
    return metadata.cue_source == "manual" and bool(metadata.cue_updated_at)


def format_metadata_provenance_hint(metadata: WorkbenchCueMetadata) -> str:
    """Compact German provenance hint for loop/attack/cue metadata."""
    parts: list[str] = []
    loop_label = format_metadata_provenance_label(metadata.loop_source)
    if loop_label:
        parts.append(f"Loop: {loop_label}")
    attack_label = format_metadata_provenance_label(metadata.attack_source)
    if attack_label:
        parts.append(f"Attack: {attack_label}")
    if _should_show_cue_provenance(metadata):
        cue_label = format_metadata_provenance_label(metadata.cue_source)
        if cue_label:
            parts.append(f"Cue: {cue_label}")
    return " · ".join(parts)


def load_workbench_sample_cue(
    path: Path | str,
    *,
    library_db_path: Path | None = None,
) -> WorkbenchCueMetadata:
    """Load cue metadata for a sample path from the workbench library cache."""
    db = library_db_path if library_db_path is not None else workbench_library_db_path()
    return load_sample_cue(path, db_path=db)


def save_workbench_sample_cue(
    path: Path | str,
    metadata: WorkbenchCueMetadata,
    *,
    library_db_path: Path | None = None,
    duration_ms: int | None = None,
) -> None:
    """Persist cue metadata for a sample already stored in the workbench library."""
    db = library_db_path if library_db_path is not None else workbench_library_db_path()
    save_sample_cue(path, metadata, db_path=db, duration_ms=duration_ms)


def get_preview_start_ms(
    path: Path | str,
    *,
    library_db_path: Path | None = None,
) -> int:
    """Return saved cue start for preview playback (0 when unset or unknown)."""
    cue = load_workbench_sample_cue(path, library_db_path=library_db_path)
    return max(0, int(cue.cue_start_ms))


def preview_start_ms_from_waveform_x(x: int, width: int, duration_ms: int) -> int:
    """Map waveform canvas x coordinate to preview start offset in milliseconds."""
    from .workbench_waveform import cue_ms_from_x

    return cue_ms_from_x(x, width, duration_ms)


@dataclass(frozen=True)
class WorkbenchPlaylistAddOutcome:
    result: PlaylistSampleAddResult
    playlist_name: str


def list_workbench_playlists(*, library_db_path: Path | None = None) -> list[str]:
    """Return song-context playlist names from the workbench library."""
    db = library_db_path if library_db_path is not None else workbench_library_db_path()
    return [playlist.name for playlist in list_playlists(db_path=db)]


def add_workbench_row_to_playlist(
    row: WorkbenchRow,
    playlist_name: str,
    *,
    library_db_path: Path | None = None,
) -> WorkbenchPlaylistAddOutcome:
    """Assign a workbench row to a song-context playlist."""
    if not row.path:
        raise WorkbenchPlaylistValidationError("sample path is missing")
    db = library_db_path if library_db_path is not None else workbench_library_db_path()
    playlist = get_or_create_playlist(playlist_name, db_path=db)
    result = add_sample_to_playlist(playlist.id, row.path, db_path=db)
    return WorkbenchPlaylistAddOutcome(result=result, playlist_name=playlist.name)


def format_playlist_add_status(outcome: WorkbenchPlaylistAddOutcome) -> str:
    """Format a user-facing status message after playlist assignment."""
    if outcome.result == "added":
        return f'Sample zu Playlist "{outcome.playlist_name}" hinzugefügt'
    return f'Sample ist bereits in Playlist "{outcome.playlist_name}"'


def _workbench_row_for_playlist_sample_path(
    sample_path: str,
    *,
    playlist_name: str,
    library_db_path: Path,
) -> WorkbenchRow:
    """Resolve a playlist sample path to a workbench row without raising."""
    cached = load_sample_by_path(sample_path, db_path=library_db_path)
    if cached is not None:
        row = cached.to_workbench_row()
        details = dict(row.details)
        details["song_playlist"] = playlist_name
        return WorkbenchRow(
            display_name=row.display_name,
            relative_path=row.relative_path,
            path=row.path,
            bpm=row.bpm,
            key=row.key,
            key_conf=row.key_conf,
            loudness=row.loudness,
            brightness=row.brightness,
            sample_class=row.sample_class,
            pred_type=row.pred_type,
            status=row.status,
            error=row.error,
            error_code=row.error_code,
            details=details,
        )

    path = Path(sample_path)
    display = normalize_display_name(path.name) if path.name else sample_path
    if path.is_file():
        return WorkbenchRow(
            display_name=display,
            relative_path=path.name,
            path=str(path.resolve()),
            bpm=None,
            key=None,
            key_conf=None,
            loudness=None,
            brightness=None,
            sample_class=None,
            pred_type=None,
            status="ok",
            details={"song_playlist": playlist_name},
        )

    return _make_error_row(
        display_name=display,
        rel=path.name or sample_path,
        path=path,
        error_code="unsupported_or_unreadable_audio",
        error_detail="file not found",
    )


def load_playlist_workbench_rows(
    playlist_name: str,
    *,
    library_db_path: Path | None = None,
) -> list[WorkbenchRow]:
    """Load workbench rows for all samples assigned to a song-context playlist."""
    db = library_db_path if library_db_path is not None else workbench_library_db_path()
    playlist = get_playlist_by_name(playlist_name, db_path=db)
    if playlist is None:
        return []
    paths = list_playlist_sample_paths(playlist.id, db_path=db)
    return [
        _workbench_row_for_playlist_sample_path(
            sample_path,
            playlist_name=playlist.name,
            library_db_path=db,
        )
        for sample_path in paths
    ]


def format_playlist_load_status(playlist_name: str, rows: list[WorkbenchRow]) -> str:
    """Format a user-facing status message after loading a playlist."""
    return f'Playlist "{playlist_name}" geladen: {len(rows)} Samples'


MATCHING_NO_SELECTION_MESSAGE = "Kein Sample ausgewählt."
MATCHING_NO_BPM_MESSAGE = "Ähnliche Samples benötigen ein analysiertes BPM."
MATCHING_NO_SUGGESTIONS_MESSAGE = "Keine Vorschläge in geladener Ansicht."


@dataclass(frozen=True)
class WorkbenchSuggestion:
    row: WorkbenchRow
    total_score: float
    reason: str


def workbench_row_sample_id(path: str) -> int:
    """Stable in-memory ID for matching tie-breaks (no catalog.db join)."""
    return zlib.crc32(path.encode("utf-8")) & 0x7FFFFFFF


def workbench_row_to_match_candidate(
    row: WorkbenchRow,
    *,
    sample_id: int | None = None,
) -> MatchCandidate:
    sid = workbench_row_sample_id(row.path) if sample_id is None else sample_id
    return MatchCandidate(
        sample_id=sid,
        path=row.path,
        bpm=row.bpm,
        key=row.key,
        pred_type=row.pred_type,
    )


def _reference_bpm_usable(bpm: float | None) -> bool:
    return bpm is not None and math.isfinite(bpm) and bpm > 0


def validate_workbench_matching_reference(reference: WorkbenchRow | None) -> str | None:
    """Return a user-facing error when *reference* cannot drive matching."""
    if reference is None:
        return MATCHING_NO_SELECTION_MESSAGE
    if not _reference_bpm_usable(reference.bpm):
        return MATCHING_NO_BPM_MESSAGE
    return None


def format_workbench_suggestion_reason(reasons: tuple[str, ...]) -> str:
    """Compact German-friendly reason line from ``MatchResult.reasons``."""
    positive = [
        reason
        for reason in reasons
        if "missing" not in reason and "mismatch" not in reason
    ]
    chosen = positive if positive else list(reasons)
    return "; ".join(chosen)


def suggest_similar_workbench_rows(
    reference: WorkbenchRow,
    candidates: list[WorkbenchRow],
    *,
    limit: int = DEFAULT_LIMIT,
) -> list[WorkbenchSuggestion]:
    """Score loaded workbench rows against *reference* using ``src.matching``."""
    if limit <= 0:
        return []

    profile = MatchProfile(
        target_bpm=float(reference.bpm),  # validated by caller
        target_key=reference.key,
        desired_type=reference.pred_type,
        limit=None,
    )

    pool = [
        row
        for row in candidates
        if row.status == "ok" and row.path and row.path != reference.path
    ]
    if not pool:
        return []

    match_candidates_list = [workbench_row_to_match_candidate(row) for row in pool]
    results = match_candidates(match_candidates_list, profile)

    suggestions: list[WorkbenchSuggestion] = []
    for result in results:
        if result.total_score <= 0:
            continue
        row = next(item for item in pool if item.path == result.path)
        suggestions.append(
            WorkbenchSuggestion(
                row=row,
                total_score=result.total_score,
                reason=format_workbench_suggestion_reason(result.reasons),
            )
        )
        if len(suggestions) >= limit:
            break
    return suggestions


def compute_workbench_similar_suggestions(
    reference: WorkbenchRow | None,
    candidates: list[WorkbenchRow],
    *,
    limit: int = DEFAULT_LIMIT,
) -> tuple[list[WorkbenchSuggestion], str | None]:
    """UI entry point: validate reference, compute suggestions, return status."""
    error = validate_workbench_matching_reference(reference)
    if error is not None:
        return [], error
    assert reference is not None
    suggestions = suggest_similar_workbench_rows(reference, candidates, limit=limit)
    if not suggestions:
        return [], MATCHING_NO_SUGGESTIONS_MESSAGE
    return suggestions, None


def start_native_recording(
    engine: "NativeAudioEngine",
    engine_frame: int,
    session_frame: int,
) -> int:
    """Start native audio recording through the audio core."""
    if engine is None or not engine.is_available():
        raise RuntimeError("Native audio engine not available")
    return engine.start_recording(engine_frame)


def stop_native_recording(
    engine: "NativeAudioEngine",
    recording_id: int,
    engine_frame: int,
    session_frame: int,
    destination: str,
    db_path: Path | None = None,
):
    """Stop native audio recording and finalize the take."""
    if engine is None or not engine.is_available():
        raise RuntimeError("Native audio engine not available")
    audio_data, frames = engine.stop_recording(recording_id)
    # Import here to avoid circular imports
    from .recording_take import finalize_recording_take
    return finalize_recording_take(
        audio_data=audio_data,
        frames=frames,
        engine_frame=engine_frame,
        session_frame=session_frame,
        destination=destination,
        db_path=db_path,
    )



__all__ = [
    "ALL_LIBRARY_VIEW_LABEL",
    "CATALOG_VIEW_LABEL",
    "ERROR_LABELS",
    "FOLDER_ERROR_MESSAGES",
    "WORKBENCH_GLOBAL_LIBRARY_TOKEN",
    "WORKBENCH_CATALOG_LIBRARY_TOKEN",
    "ProgressCallback",
    "ProgressPhase",
    "ShouldCancel",
    "WorkbenchFolderValidation",
    "WorkbenchRow",
    "WorkbenchCueMetadata",
    "WorkbenchPlaylistAddOutcome",
    "WorkbenchPlaylistValidationError",
    "WorkbenchResult",
    "add_workbench_library_folder",
    "add_workbench_row_to_playlist",
    "analyze_folder_for_workbench",
    "apply_workbench_filters",
    "apply_workbench_structured_filters",
    "catalog_available",
    "catalog_row_display_name",
    "CatalogImportConflictPolicy",
    "CatalogImportPreview",
    "CatalogImportPreviewItem",
    "CatalogImportResult",
    "CATALOG_READONLY_EDIT_MESSAGE",
    "CATALOG_READONLY_STATUS_HINT",
    "count_catalog_samples",
    "DEFAULT_CATALOG_LOAD_LIMIT",
    "DEFAULT_WORKBENCH_ANALYSIS_LIMIT_TEXT",
    "DEFAULT_WORKBENCH_VIEW_SETTINGS",
    "error_message_for_code",
    "effective_workbench_row_filters",
    "effective_workbench_text_query",
    "export_workbench_rows_to_csv",
    "export_workbench_rows_to_fl_tags",
    "filter_workbench_rows",
    "format_catalog_import_preview_message",
    "format_catalog_import_result_message",
    "format_catalog_load_status",
    "format_playlist_add_status",
    "format_playlist_load_status",
    "format_workbench_active_filter_summary",
    "format_workbench_search_status",
    "format_workbench_view_restore_status",
    "format_workbench_view_section_hidden_status",
    "format_workbench_view_toolbar_hidden_status",
    "format_workbench_view_toolbar_shown_status",
    "import_catalog_rows_to_cache",
    "is_catalog_readonly_row",
    "WorkbenchSearchMode",
    "WorkbenchSearchStatusContext",
    "row_source_kind",
    "workbench_filter_options",
    "workbench_row_to_fl_sample_row",
    "workbench_rows_for_fl_export",
    "WorkbenchFlExportResult",
    "WorkbenchRowFilters",
    "WorkbenchSuggestion",
    "FILTER_ALL_LABEL",
    "MATCHING_NO_BPM_MESSAGE",
    "MATCHING_NO_SELECTION_MESSAGE",
    "MATCHING_NO_SUGGESTIONS_MESSAGE",
    "compute_workbench_similar_suggestions",
    "format_workbench_suggestion_reason",
    "suggest_similar_workbench_rows",
    "validate_workbench_matching_reference",
    "workbench_row_sample_id",
    "workbench_row_to_match_candidate",
    "format_metadata_provenance_hint",
    "format_metadata_provenance_label",
    "format_path_display_lines",
    "format_workbench_detail_field_lines",
    "get_workbench_library_folders",
    "get_preview_start_ms",
    "preview_catalog_import",
    "preview_start_ms_from_waveform_x",
    "list_workbench_playlists",
    "load_all_cached_rows",
    "load_cached_folder_rows",
    "load_catalog_rows",
    "load_playlist_workbench_rows",
    "load_workbench_analysis_limit",
    "load_workbench_last_folder",
    "load_workbench_view_settings",
    "load_workbench_sample_cue",
    "normalize_workbench_analysis_limit_text",
    "parse_workbench_bpm_bound",
    "PLAYLIST_CSV_FIELDS",
    "resolve_workbench_fl_export_max_tags",
    "resolve_workbench_fl_export_roots",
    "resolve_workbench_fl_user_data_path",
    "remove_workbench_library_folder",
    "row_as_dict",
    "save_workbench_analysis_limit",
    "save_workbench_last_folder",
    "save_workbench_view_settings",
    "save_workbench_sample_cue",
    "sort_workbench_rows",
    "validate_workbench_folder",
    "workbench_analysis_limit_file",
    "workbench_last_folder_file",
    "workbench_state_dir",
    "workbench_view_settings_file",
    "WORKBENCH_VIEW_TOGGLE_HELP",
    "VIEW_SECTION_FILTERS",
    "VIEW_SECTION_LIBRARY_MANAGE",
    "VIEW_SECTION_SEARCH",
    "VIEW_SECTION_WAVEFORM_TOOLS",
    "WorkbenchViewSettings",
]
