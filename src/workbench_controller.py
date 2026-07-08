"""Folder-scoped analysis for the local workbench (no DB required)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .analyze import extract_features
from .classify import rule_type
from .scan import iter_audio_files_stream, safe_audio_info


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


def _format_optional(value: float | None, *, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def analyze_folder_for_workbench(
    folder: Path | str,
    limit: int | None = None,
) -> WorkbenchResult:
    """Scan *folder* for audio files, analyze each, and return playlist rows."""
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    rows: list[WorkbenchRow] = []
    files_found = 0
    analyzed_count = 0
    error_count = 0

    for audio_path in iter_audio_files_stream([root]):
        files_found += 1
        if limit is not None and len(rows) >= limit:
            break

        rel = str(audio_path.relative_to(root))
        display_name = audio_path.name

        try:
            sr, ch, dur = safe_audio_info(audio_path)
            feats = extract_features(audio_path, dur)
            if feats is None:
                error_count += 1
                rows.append(
                    WorkbenchRow(
                        display_name=display_name,
                        relative_path=rel,
                        path=str(audio_path),
                        bpm=None,
                        key=None,
                        key_conf=None,
                        loudness=None,
                        brightness=None,
                        sample_class=None,
                        pred_type=None,
                        status="error",
                        error="Could not extract features",
                        details={"path": str(audio_path), "relative_path": rel},
                    )
                )
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
        except Exception as exc:
            error_count += 1
            rows.append(
                WorkbenchRow(
                    display_name=display_name,
                    relative_path=rel,
                    path=str(audio_path),
                    bpm=None,
                    key=None,
                    key_conf=None,
                    loudness=None,
                    brightness=None,
                    sample_class=None,
                    pred_type=None,
                    status="error",
                    error=str(exc),
                    details={"path": str(audio_path), "relative_path": rel},
                )
            )

    effective_found = files_found
    if limit is not None and files_found > limit:
        effective_found = limit

    return WorkbenchResult(
        summary={
            "files_found": effective_found,
            "analyzed_count": analyzed_count,
            "error_count": error_count,
        },
        rows=rows,
    )


def row_as_dict(row: WorkbenchRow) -> dict[str, Any]:
    return asdict(row)


__all__ = [
    "WorkbenchRow",
    "WorkbenchResult",
    "analyze_folder_for_workbench",
    "row_as_dict",
]
