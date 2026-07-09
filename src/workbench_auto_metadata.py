"""Workbench auto-metadata rules for loop regions and oneshot attack/cue (#172 / #173)."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .workbench_attack_suggest import suggest_attack_ms
from .workbench_library import (
    WorkbenchCueMetadata,
    WorkbenchCueNotFoundError,
    load_sample_cue,
    save_sample_cue,
)

if TYPE_CHECKING:
    from .workbench_controller import WorkbenchRow

LOOP_PRED_TYPES = frozenset({"Loop", "Drum Loop"})
ONESHOT_PRED_TYPE = "OneShot"


def is_definite_loop(pred_type: str | None, sample_class: str | None) -> bool:
    """Return True when classification is unambiguously loop-like (v1)."""
    if pred_type in LOOP_PRED_TYPES:
        return True
    if pred_type is None and sample_class == "loop":
        return True
    return False


def is_definite_oneshot(pred_type: str | None, sample_class: str | None) -> bool:
    """Return True when classification is unambiguously OneShot (v1, no Kick/Snare)."""
    if pred_type == ONESHOT_PRED_TYPE:
        return True
    if pred_type is None and sample_class == "oneshot":
        return True
    return False


def _has_manual_loop_fields(metadata: WorkbenchCueMetadata) -> bool:
    return metadata.loop_start_ms is not None or metadata.loop_end_ms is not None


def _has_manual_attack(metadata: WorkbenchCueMetadata) -> bool:
    return metadata.attack_ms is not None


def _has_manual_cue(metadata: WorkbenchCueMetadata) -> bool:
    if metadata.cue_source != "manual":
        return False
    if metadata.cue_start_ms != 0:
        return True
    return metadata.cue_updated_at is not None


def should_skip_auto_metadata(row: WorkbenchRow) -> bool:
    """Return True when auto-metadata must not run for *row*."""
    from .workbench_controller import is_catalog_readonly_row

    if row.status != "ok":
        return True
    if is_catalog_readonly_row(row):
        return True
    return False


def can_auto_loop(metadata: WorkbenchCueMetadata) -> bool:
    return not _has_manual_loop_fields(metadata)


def can_auto_attack(metadata: WorkbenchCueMetadata) -> bool:
    return not _has_manual_attack(metadata)


def can_auto_cue(metadata: WorkbenchCueMetadata) -> bool:
    return not _has_manual_cue(metadata)


def apply_auto_loop_metadata(
    existing: WorkbenchCueMetadata,
    *,
    duration_ms: int | None,
) -> WorkbenchCueMetadata | None:
    """Apply v1 loop region auto-fill when slots are empty."""
    if not can_auto_loop(existing):
        return None
    if duration_ms is None or duration_ms <= 0:
        return None
    return WorkbenchCueMetadata(
        cue_start_ms=existing.cue_start_ms,
        attack_ms=existing.attack_ms,
        loop_start_ms=0,
        loop_end_ms=duration_ms,
        cue_source=existing.cue_source,
        cue_updated_at=existing.cue_updated_at,
    )


def apply_auto_oneshot_metadata(
    existing: WorkbenchCueMetadata,
    path: Path | str,
    *,
    duration_ms: int | None,
) -> WorkbenchCueMetadata | None:
    """Apply v1 oneshot attack/cue auto-fill when slots are empty."""
    if not can_auto_attack(existing):
        return None
    if duration_ms is None or duration_ms <= 0:
        return None

    suggestion = suggest_attack_ms(path)
    if suggestion is None or suggestion.confidence == "low":
        return None

    attack_ms = suggestion.attack_ms
    cue_start_ms = existing.cue_start_ms
    cue_source = existing.cue_source
    if can_auto_cue(existing):
        cue_start_ms = attack_ms
        cue_source = "detected"

    return WorkbenchCueMetadata(
        cue_start_ms=cue_start_ms,
        attack_ms=attack_ms,
        loop_start_ms=existing.loop_start_ms,
        loop_end_ms=existing.loop_end_ms,
        cue_source=cue_source,
        cue_updated_at=existing.cue_updated_at,
    )


def _duration_ms_from_row(row: WorkbenchRow) -> int | None:
    dur_sec = row.details.get("duration_sec")
    if dur_sec is not None:
        try:
            ms = int(round(float(dur_sec) * 1000.0))
            if ms > 0:
                return ms
        except (TypeError, ValueError):
            pass
    from .workbench_waveform import read_audio_duration_ms

    return read_audio_duration_ms(row.path)


def apply_auto_metadata_for_row(
    row: WorkbenchRow,
    existing: WorkbenchCueMetadata,
    *,
    duration_ms: int | None = None,
) -> WorkbenchCueMetadata | None:
    """Merge loop and oneshot auto-rules; returns updated metadata or None."""
    if should_skip_auto_metadata(row):
        return None

    duration = duration_ms if duration_ms is not None else _duration_ms_from_row(row)
    updated = existing
    changed = False

    if is_definite_loop(row.pred_type, row.sample_class):
        loop_meta = apply_auto_loop_metadata(updated, duration_ms=duration)
        if loop_meta is not None:
            updated = loop_meta
            changed = True

    if is_definite_oneshot(row.pred_type, row.sample_class):
        oneshot_meta = apply_auto_oneshot_metadata(updated, row.path, duration_ms=duration)
        if oneshot_meta is not None:
            updated = oneshot_meta
            changed = True

    return updated if changed else None


def apply_auto_metadata_after_analyze(
    row: WorkbenchRow,
    *,
    library_db_path: Path | None = None,
) -> WorkbenchCueMetadata | None:
    """Persist auto-metadata after analyze cache write when rules allow."""
    if should_skip_auto_metadata(row):
        return None

    try:
        existing = load_sample_cue(row.path, db_path=library_db_path)
    except Exception:
        return None

    updated = apply_auto_metadata_for_row(row, existing)
    if updated is None:
        return None

    duration_ms = _duration_ms_from_row(row)
    try:
        save_sample_cue(row.path, updated, db_path=library_db_path, duration_ms=duration_ms)
    except WorkbenchCueNotFoundError:
        return None
    return updated


__all__ = [
    "LOOP_PRED_TYPES",
    "ONESHOT_PRED_TYPE",
    "apply_auto_loop_metadata",
    "apply_auto_metadata_after_analyze",
    "apply_auto_metadata_for_row",
    "apply_auto_oneshot_metadata",
    "can_auto_attack",
    "can_auto_cue",
    "can_auto_loop",
    "is_definite_loop",
    "is_definite_oneshot",
    "should_skip_auto_metadata",
]
