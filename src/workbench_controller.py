"""Folder-scoped analysis for the local workbench (no DB required)."""
from __future__ import annotations

import csv
import json
import os
import textwrap
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePath
from typing import Any, Callable, Literal, Mapping

from .analyze import (
    SHORT_AUDIO_WARNING_CODE,
    extract_features,
    safe_load,
)
from .bpm_display import format_bpm_display, round_bpm_display
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
    LibraryFolder,
    WorkbenchCueMetadata,
    list_library_folders,
    load_all_cached_samples,
    load_folder_samples,
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
                {**row.playlist_fields(), "path": row.path, "details": dict(row.details)}
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
        return (row.brightness is None, row.brightness if row.brightness is not None else 0.0)
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
    return sorted(rows, key=lambda row: _sort_key_for_column(row, column), reverse=reverse)


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

    cache_db = library_db_path if library_db_path is not None else workbench_library_db_path()
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
            writer.writerow({field: data.get(field, "") for field in PLAYLIST_CSV_FIELDS})
    return len(rows)


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


@dataclass(frozen=True)
class WorkbenchViewSettings:
    show_search: bool = True
    show_filters: bool = True
    show_library_manage: bool = True
    show_waveform_tools: bool = True


DEFAULT_WORKBENCH_VIEW_SETTINGS = WorkbenchViewSettings()

VIEW_SECTION_SEARCH = "search"
VIEW_SECTION_FILTERS = "filters"
VIEW_SECTION_LIBRARY_MANAGE = "library_manage"
VIEW_SECTION_WAVEFORM_TOOLS = "waveform_tools"

WORKBENCH_VIEW_TOGGLE_HELP = (
    "Suche, Filter, Library-Verwaltung und Waveform-Werkzeuge können ein- und ausgeblendet werden."
)


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
    "WorkbenchResult",
    "add_workbench_library_folder",
    "analyze_folder_for_workbench",
    "apply_workbench_filters",
    "apply_workbench_structured_filters",
    "catalog_available",
    "catalog_row_display_name",
    "CATALOG_READONLY_EDIT_MESSAGE",
    "CATALOG_READONLY_STATUS_HINT",
    "count_catalog_samples",
    "DEFAULT_CATALOG_LOAD_LIMIT",
    "DEFAULT_WORKBENCH_VIEW_SETTINGS",
    "error_message_for_code",
    "effective_workbench_row_filters",
    "effective_workbench_text_query",
    "export_workbench_rows_to_csv",
    "filter_workbench_rows",
    "format_catalog_load_status",
    "format_workbench_active_filter_summary",
    "format_workbench_search_status",
    "format_workbench_view_restore_status",
    "format_workbench_view_section_hidden_status",
    "is_catalog_readonly_row",
    "WorkbenchSearchMode",
    "WorkbenchSearchStatusContext",
    "row_source_kind",
    "workbench_filter_options",
    "WorkbenchRowFilters",
    "FILTER_ALL_LABEL",
    "format_metadata_provenance_hint",
    "format_metadata_provenance_label",
    "format_path_display_lines",
    "get_workbench_library_folders",
    "get_preview_start_ms",
    "preview_start_ms_from_waveform_x",
    "load_all_cached_rows",
    "load_cached_folder_rows",
    "load_catalog_rows",
    "load_workbench_last_folder",
    "load_workbench_view_settings",
    "load_workbench_sample_cue",
    "parse_workbench_bpm_bound",
    "PLAYLIST_CSV_FIELDS",
    "remove_workbench_library_folder",
    "row_as_dict",
    "save_workbench_last_folder",
    "save_workbench_view_settings",
    "save_workbench_sample_cue",
    "sort_workbench_rows",
    "validate_workbench_folder",
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