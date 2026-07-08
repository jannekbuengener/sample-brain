"""Folder-scoped analysis for the local workbench (no DB required)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from .analyze import (
    SHORT_AUDIO_WARNING_CODE,
    extract_features,
    safe_load,
)
from .classify import rule_type
from .scan import iter_audio_files_stream, safe_audio_info

ProgressPhase = Literal["scanning", "analyzing", "done", "error"]
ProgressCallback = Callable[[int, int, str, ProgressPhase], None]

ERROR_LABELS: dict[str, str] = {
    "audio_info_failed": "Datei-Metadaten konnten nicht gelesen werden",
    "unsupported_or_unreadable_audio": "Datei konnte nicht gelesen werden",
    "too_short_or_empty_audio": "Datei ist zu kurz oder leer",
    "feature_extract_failed": "Analyse fehlgeschlagen",
    "analysis_exception": "Unbekannter Analysefehler",
}


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


def analyze_folder_for_workbench(
    folder: Path | str,
    limit: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> WorkbenchResult:
    """Scan *folder* for audio files, analyze each, and return playlist rows."""
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    _emit_progress(progress_callback, 0, 0, "", "scanning")
    audio_paths = _collect_audio_paths(root, limit)
    total = len(audio_paths)

    rows: list[WorkbenchRow] = []
    analyzed_count = 0
    error_count = 0

    for index, audio_path in enumerate(audio_paths, start=1):
        rel = str(audio_path.relative_to(root))
        display_name = audio_path.name
        _emit_progress(progress_callback, index, total, display_name, "analyzing")

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

            rows.append(
                WorkbenchRow(
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
            )
            analyzed_count += 1
            _emit_progress(progress_callback, index, total, display_name, "done")
        except Exception as exc:
            error_count += 1
            detail = str(exc).strip() or "unexpected exception"
            rows.append(
                _make_error_row(
                    display_name=display_name,
                    rel=rel,
                    path=audio_path,
                    error_code="analysis_exception",
                    error_detail=detail[:200],
                )
            )
            _emit_progress(progress_callback, index, total, display_name, "error")

    return WorkbenchResult(
        summary={
            "files_found": total,
            "analyzed_count": analyzed_count,
            "error_count": error_count,
        },
        rows=rows,
    )


def row_as_dict(row: WorkbenchRow) -> dict[str, Any]:
    return asdict(row)


__all__ = [
    "ERROR_LABELS",
    "ProgressCallback",
    "ProgressPhase",
    "WorkbenchRow",
    "WorkbenchResult",
    "analyze_folder_for_workbench",
    "error_message_for_code",
    "row_as_dict",
]