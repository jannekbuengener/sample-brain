"""Folder-scoped analysis for the local workbench (no DB required)."""
from __future__ import annotations

import csv
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
from .classify import rule_type
from .scan import iter_audio_files_stream, safe_audio_info
from .workbench_library import (
    WORKBENCH_ANALYZER_VERSION,
    lookup_sample,
    normalize_display_name,
    upsert_folder,
    upsert_sample,
    workbench_library_db_path,
)

ProgressPhase = Literal["scanning", "analyzing", "done", "error", "cancelled"]
ProgressCallback = Callable[[int, int, str, ProgressPhase], None]
ShouldCancel = Callable[[], bool]

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
        return " ".join(parts).casefold()

    return [row for row in rows if needle in _haystack(row)]


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
                "bpm": _format_optional(feats.bpm, digits=1),
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


__all__ = [
    "ERROR_LABELS",
    "FOLDER_ERROR_MESSAGES",
    "ProgressCallback",
    "ProgressPhase",
    "ShouldCancel",
    "WorkbenchFolderValidation",
    "WorkbenchRow",
    "WorkbenchResult",
    "analyze_folder_for_workbench",
    "error_message_for_code",
    "export_workbench_rows_to_csv",
    "filter_workbench_rows",
    "format_path_display_lines",
    "load_workbench_last_folder",
    "PLAYLIST_SORT_COLUMNS",
    "PLAYLIST_CSV_FIELDS",
    "row_as_dict",
    "save_workbench_last_folder",
    "sort_workbench_rows",
    "validate_workbench_folder",
    "workbench_last_folder_file",
    "workbench_state_dir",
]