"""Exact-frame, non-destructive Workbench edit regions (issue #326).

The stored source-frame range is authoritative. Milliseconds and session-time
values are display/preview helpers only and are never persisted as edit bounds.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Sequence

import soundfile as sf

from .asset_renderer import RenderRequest, RenderResult, render_asset
from .haeftig import (
    HaeftigRegion,
    HaeftigSelection,
    add_haeftig_region,
    select_haeftig_region,
)
from .workbench_library import workbench_library_db_path

SnapMode = Literal["none", "beat", "bar"]
SNAP_MODES: tuple[SnapMode, ...] = ("none", "beat", "bar")

EDIT_REGION_STATE_FILE_NAME = "workbench_edit_regions.json"
EDIT_REGION_STATE_VERSION = 2


class EditRegionValidationError(ValueError):
    """Raised when an edit region violates the exact-frame contract."""


@dataclass(frozen=True)
class WorkbenchEditRegion:
    source_ref: str
    source_start_frame: int
    source_end_frame_exclusive: int
    source_sample_rate: int
    snap_mode: SnapMode = "none"
    grid_source_ref: str | None = None
    label: str | None = None
    region_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_ref, str) or not self.source_ref.strip():
            raise EditRegionValidationError("source_ref must be a non-empty string")
        for name, value in (
            ("source_start_frame", self.source_start_frame),
            ("source_end_frame_exclusive", self.source_end_frame_exclusive),
        ):
            if not isinstance(value, int) or isinstance(value, bool):
                raise EditRegionValidationError(f"{name} must be an integer")
            if value < 0:
                raise EditRegionValidationError(f"{name} must be non-negative")
        if self.source_end_frame_exclusive <= self.source_start_frame:
            raise EditRegionValidationError(
                "source_end_frame_exclusive must be greater than source_start_frame"
            )
        if (
            not isinstance(self.source_sample_rate, int)
            or isinstance(self.source_sample_rate, bool)
            or self.source_sample_rate <= 0
        ):
            raise EditRegionValidationError(
                "source_sample_rate must be a positive integer"
            )
        if self.snap_mode not in SNAP_MODES:
            raise EditRegionValidationError("snap_mode must be none, beat, or bar")

    @property
    def frame_count(self) -> int:
        return self.source_end_frame_exclusive - self.source_start_frame


@dataclass(frozen=True)
class SourceEditGrid:
    """Reliable source-grid frame positions usable for snapping."""

    beat_frames: tuple[int, ...] = ()
    bar_frames: tuple[int, ...] = ()
    source_ref: str | None = None

    def __post_init__(self) -> None:
        _validate_grid_frames(self.beat_frames, name="beat_frames")
        _validate_grid_frames(self.bar_frames, name="bar_frames")


def _validate_grid_frames(values: Sequence[int], *, name: str) -> None:
    previous: int | None = None
    for value in values:
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise EditRegionValidationError(
                f"{name} must contain non-negative integer source frames"
            )
        if previous is not None and value <= previous:
            raise EditRegionValidationError(f"{name} must be strictly increasing")
        previous = value


def audio_source_frame_info(path: Path | str) -> tuple[int, int]:
    """Return ``(total_frames, sample_rate)`` without decoding or modifying audio."""
    resolved = Path(path)
    if not resolved.is_file():
        raise EditRegionValidationError("source audio file does not exist")
    try:
        info = sf.info(resolved)
    except Exception as exc:
        raise EditRegionValidationError(
            f"source audio metadata unavailable: {exc}"
        ) from exc
    frames = int(info.frames)
    sample_rate = int(info.samplerate)
    if frames <= 0:
        raise EditRegionValidationError("source audio has no frames")
    if sample_rate <= 0:
        raise EditRegionValidationError("source audio has invalid sample rate")
    return frames, sample_rate


def frame_from_waveform_x(x: int, width: int, total_frames: int) -> int:
    """Map a canvas x coordinate directly to source frames using integer arithmetic."""
    if not isinstance(width, int) or isinstance(width, bool) or width <= 0:
        raise EditRegionValidationError("waveform width must be a positive integer")
    if (
        not isinstance(total_frames, int)
        or isinstance(total_frames, bool)
        or total_frames <= 0
    ):
        raise EditRegionValidationError("total_frames must be a positive integer")
    clamped_x = max(0, min(int(x), width))
    return (clamped_x * total_frames) // width


def _nearest_frame(frame: int, candidates: Sequence[int]) -> int:
    if not candidates:
        raise EditRegionValidationError("snap grid is empty")
    return min(candidates, key=lambda candidate: (abs(candidate - frame), candidate))


def build_edit_region(
    *,
    source_ref: str,
    source_start_frame: int,
    source_end_frame_exclusive: int,
    source_sample_rate: int,
    total_source_frames: int,
    snap_mode: SnapMode = "none",
    grid: SourceEditGrid | None = None,
    label: str | None = None,
    region_id: str | None = None,
) -> WorkbenchEditRegion:
    """Validate and optionally snap an exact source-frame region.

    Snapping only uses provided, reliable source beat/downbeat frame positions.
    BPM, session tempo, GUI time, and milliseconds are intentionally ignored.
    """
    if (
        not isinstance(total_source_frames, int)
        or isinstance(total_source_frames, bool)
        or total_source_frames <= 0
    ):
        raise EditRegionValidationError(
            "total_source_frames must be a positive integer"
        )

    start = source_start_frame
    end = source_end_frame_exclusive
    grid_source_ref: str | None = None

    if snap_mode == "beat":
        if grid is None or not grid.beat_frames:
            raise EditRegionValidationError(
                "beat snap unavailable: no reliable source beat grid"
            )
        start = _nearest_frame(start, grid.beat_frames)
        end = _nearest_frame(end, grid.beat_frames)
        grid_source_ref = grid.source_ref
    elif snap_mode == "bar":
        if grid is None or not grid.bar_frames:
            raise EditRegionValidationError(
                "bar snap unavailable: no reliable source downbeat/bar grid"
            )
        start = _nearest_frame(start, grid.bar_frames)
        end = _nearest_frame(end, grid.bar_frames)
        grid_source_ref = grid.source_ref
    elif snap_mode != "none":
        raise EditRegionValidationError("snap_mode must be none, beat, or bar")

    region = WorkbenchEditRegion(
        source_ref=source_ref,
        source_start_frame=start,
        source_end_frame_exclusive=end,
        source_sample_rate=source_sample_rate,
        snap_mode=snap_mode,
        grid_source_ref=grid_source_ref,
        label=label,
        region_id=region_id,
    )
    if region.source_start_frame >= total_source_frames:
        raise EditRegionValidationError("source_start_frame lies outside source audio")
    if region.source_end_frame_exclusive > total_source_frames:
        raise EditRegionValidationError(
            "source_end_frame_exclusive lies outside source audio"
        )
    return region


def _series_sample_indices(payload: object) -> tuple[int, ...]:
    if not isinstance(payload, Mapping):
        return ()
    if payload.get("status") != "ok":
        return ()
    values = payload.get("sample_indices")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        return ()
    frames: list[int] = []
    previous: int | None = None
    for raw in values:
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
            return ()
        if previous is not None and raw <= previous:
            return ()
        frames.append(raw)
        previous = raw
    return tuple(frames)


def source_edit_grid_from_details(details: Mapping[str, object]) -> SourceEditGrid:
    """Extract only exact source-frame beat/downbeat evidence from Workbench details.

    The helper deliberately refuses to derive snap points from BPM or seconds.
    """
    container: Mapping[str, object] = details
    nested = details.get("beat_grid")
    if isinstance(nested, Mapping):
        container = nested

    beats = _series_sample_indices(container.get("beats"))
    downbeats = _series_sample_indices(container.get("downbeats"))
    source_ref_raw = container.get("source_ref")
    source_ref = (
        str(source_ref_raw).strip()
        if isinstance(source_ref_raw, str) and source_ref_raw.strip()
        else None
    )
    return SourceEditGrid(
        beat_frames=beats,
        bar_frames=downbeats,
        source_ref=source_ref,
    )


def workbench_edit_region_state_path(
    *,
    state_path: Path | None = None,
) -> Path:
    """Return the user-local JSON state file for exact edit regions."""
    if state_path is not None:
        return Path(state_path)
    return workbench_library_db_path().parent / EDIT_REGION_STATE_FILE_NAME


def _normalized_source_ref(source_ref: Path | str) -> str:
    text = str(source_ref).strip()
    if not text:
        raise EditRegionValidationError("source_ref must not be empty")
    return str(Path(text).expanduser().resolve())


def _region_to_payload(region: WorkbenchEditRegion) -> dict[str, object]:
    return {
        "source_ref": region.source_ref,
        "source_start_frame": region.source_start_frame,
        "source_end_frame_exclusive": region.source_end_frame_exclusive,
        "source_sample_rate": region.source_sample_rate,
        "snap_mode": region.snap_mode,
        "grid_source_ref": region.grid_source_ref,
        "label": region.label,
        "region_id": region.region_id,
    }


def _region_from_payload(payload: object) -> WorkbenchEditRegion:
    if not isinstance(payload, Mapping):
        raise EditRegionValidationError("stored edit region must be an object")
    try:
        return WorkbenchEditRegion(
            source_ref=str(payload["source_ref"]),
            source_start_frame=int(payload["source_start_frame"]),
            source_end_frame_exclusive=int(payload["source_end_frame_exclusive"]),
            source_sample_rate=int(payload["source_sample_rate"]),
            snap_mode=str(payload.get("snap_mode", "none")),  # type: ignore[arg-type]
            grid_source_ref=(
                None
                if payload.get("grid_source_ref") is None
                else str(payload["grid_source_ref"])
            ),
            label=None if payload.get("label") is None else str(payload["label"]),
            region_id=(
                None if payload.get("region_id") is None else str(payload["region_id"])
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EditRegionValidationError(
            f"stored edit region is invalid: {exc}"
        ) from exc


def _load_state(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {
            "version": EDIT_REGION_STATE_VERSION,
            "regions": {},
            "haeftig_regions": {},
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EditRegionValidationError(
            f"edit-region state is unreadable: {exc}"
        ) from exc
    if not isinstance(raw, dict):
        raise EditRegionValidationError("edit-region state root must be an object")

    version = raw.get("version")
    # Backward-compatible migration: version 1 carried only the #326 edit regions.
    # HÄFTIG regions (#327) are added as a sibling key and never replace them.
    if version == 1:
        regions = raw.get("regions")
        if not isinstance(regions, dict):
            raise EditRegionValidationError(
                "edit-region state regions must be an object"
            )
        return {
            "version": EDIT_REGION_STATE_VERSION,
            "regions": regions,
            "haeftig_regions": {},
        }
    if version != EDIT_REGION_STATE_VERSION:
        raise EditRegionValidationError("unsupported edit-region state version")

    regions = raw.get("regions")
    if not isinstance(regions, dict):
        raise EditRegionValidationError("edit-region state regions must be an object")
    haeftig_regions = raw.get("haeftig_regions")
    if not isinstance(haeftig_regions, dict):
        haeftig_regions = {}
    return {
        "version": EDIT_REGION_STATE_VERSION,
        "regions": regions,
        "haeftig_regions": haeftig_regions,
    }


def _write_state(path: Path, state: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    try:
        temp.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, path)
    except Exception:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def load_workbench_edit_region(
    source_ref: Path | str,
    *,
    state_path: Path | None = None,
) -> WorkbenchEditRegion | None:
    normalized = _normalized_source_ref(source_ref)
    path = workbench_edit_region_state_path(state_path=state_path)
    state = _load_state(path)
    regions = state["regions"]
    assert isinstance(regions, dict)
    payload = regions.get(normalized)
    if payload is None:
        return None
    region = _region_from_payload(payload)
    if region.source_ref != normalized:
        raise EditRegionValidationError("stored edit-region source_ref mismatch")
    return region


def save_workbench_edit_region(
    region: WorkbenchEditRegion,
    *,
    state_path: Path | None = None,
) -> WorkbenchEditRegion:
    """Persist one exact-frame region in user-local Workbench metadata."""
    normalized = _normalized_source_ref(region.source_ref)
    stored = WorkbenchEditRegion(
        source_ref=normalized,
        source_start_frame=region.source_start_frame,
        source_end_frame_exclusive=region.source_end_frame_exclusive,
        source_sample_rate=region.source_sample_rate,
        snap_mode=region.snap_mode,
        grid_source_ref=region.grid_source_ref,
        label=region.label,
        region_id=region.region_id,
    )
    path = workbench_edit_region_state_path(state_path=state_path)
    state = _load_state(path)
    regions = state["regions"]
    assert isinstance(regions, dict)
    regions[normalized] = _region_to_payload(stored)
    _write_state(path, state)
    return stored


def delete_workbench_edit_region(
    source_ref: Path | str,
    *,
    state_path: Path | None = None,
) -> bool:
    normalized = _normalized_source_ref(source_ref)
    path = workbench_edit_region_state_path(state_path=state_path)
    state = _load_state(path)
    regions = state["regions"]
    assert isinstance(regions, dict)
    if normalized not in regions:
        return False
    del regions[normalized]
    _write_state(path, state)
    return True


# ---------------------------------------------------------------------------
# HÄFTIG regions (#327) — stored in the SAME user-local JSON file as the #326
# edit regions, under a separate ``haeftig_regions`` key. Reuses the existing
# atomic writer, source-ref normalization, and load/store helpers. HÄFTIG is the
# only manual region type; no further manual categories are introduced.
# ---------------------------------------------------------------------------


def _haeftig_region_to_payload(region: HaeftigRegion) -> dict[str, object]:
    return {
        "region_type": region.region_type,
        "source_ref": region.source_ref,
        "source_start_frame": region.source_start_frame,
        "source_end_frame_exclusive": region.source_end_frame_exclusive,
        "source_start_bar_index": region.source_start_bar_index,
        "source_end_bar_index_exclusive": region.source_end_bar_index_exclusive,
        "trigger_source_frame": region.trigger_source_frame,
        "trigger_session_frame": region.trigger_session_frame,
        "grid_source_ref": region.grid_source_ref,
    }


def _haeftig_region_from_payload(payload: object) -> HaeftigRegion:
    if not isinstance(payload, Mapping):
        raise EditRegionValidationError("stored HÄFTIG region must be an object")
    try:
        trigger_session_frame = payload.get("trigger_session_frame")
        return HaeftigRegion(
            region_type=str(payload["region_type"]),
            source_ref=str(payload["source_ref"]),
            source_start_frame=int(payload["source_start_frame"]),
            source_end_frame_exclusive=int(payload["source_end_frame_exclusive"]),
            source_start_bar_index=int(payload["source_start_bar_index"]),
            source_end_bar_index_exclusive=int(
                payload["source_end_bar_index_exclusive"]
            ),
            trigger_source_frame=int(payload["trigger_source_frame"]),
            trigger_session_frame=(
                None
                if trigger_session_frame is None
                else int(trigger_session_frame)
            ),
            grid_source_ref=(
                None
                if payload.get("grid_source_ref") is None
                else str(payload["grid_source_ref"])
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EditRegionValidationError(
            f"stored HÄFTIG region is invalid: {exc}"
        ) from exc


def load_haeftig_regions(
    source_ref: Path | str,
    *,
    state_path: Path | None = None,
) -> tuple[HaeftigRegion, ...]:
    """Return all persisted HÄFTIG regions for ``source_ref`` (may be empty)."""
    normalized = _normalized_source_ref(source_ref)
    path = workbench_edit_region_state_path(state_path=state_path)
    state = _load_state(path)
    haeftig_regions = state["haeftig_regions"]
    assert isinstance(haeftig_regions, dict)
    payloads = haeftig_regions.get(normalized)
    if not isinstance(payloads, list):
        return ()
    regions: list[HaeftigRegion] = []
    for payload in payloads:
        try:
            region = _haeftig_region_from_payload(payload)
        except EditRegionValidationError:
            continue
        if region.source_ref != normalized:
            raise EditRegionValidationError("stored HÄFTIG source_ref mismatch")
        regions.append(region)
    return tuple(regions)


def save_haeftig_region(
    region: HaeftigRegion,
    *,
    state_path: Path | None = None,
) -> tuple[HaeftigRegion, bool]:
    """Persist a HÄFTIG region for its source_ref, deduplicating identical bounds.

    Returns the (possibly de-duplicated) stored region and whether it was newly
    added. Identical source-boundary regions are not stored twice.
    """
    normalized = _normalized_source_ref(region.source_ref)
    stored = HaeftigRegion(
        region_type=region.region_type,
        source_ref=normalized,
        source_start_frame=region.source_start_frame,
        source_end_frame_exclusive=region.source_end_frame_exclusive,
        source_start_bar_index=region.source_start_bar_index,
        source_end_bar_index_exclusive=region.source_end_bar_index_exclusive,
        trigger_source_frame=region.trigger_source_frame,
        trigger_session_frame=region.trigger_session_frame,
        grid_source_ref=region.grid_source_ref,
    )
    path = workbench_edit_region_state_path(state_path=state_path)
    state = _load_state(path)
    haeftig_regions = state["haeftig_regions"]
    assert isinstance(haeftig_regions, dict)
    existing = haeftig_regions.get(normalized)
    current: tuple[HaeftigRegion, ...] = ()
    if isinstance(existing, list):
        loaded: list[HaeftigRegion] = []
        for payload in existing:
            try:
                loaded.append(_haeftig_region_from_payload(payload))
            except EditRegionValidationError:
                continue
        current = tuple(loaded)
    updated, added = add_haeftig_region(current, stored)
    haeftig_regions[normalized] = [
        _haeftig_region_to_payload(region) for region in updated
    ]
    _write_state(path, state)
    return stored, added


def delete_haeftig_regions(
    source_ref: Path | str,
    *,
    state_path: Path | None = None,
) -> bool:
    """Delete every persisted HÄFTIG region for ``source_ref``. Returns True if any existed."""
    normalized = _normalized_source_ref(source_ref)
    path = workbench_edit_region_state_path(state_path=state_path)
    state = _load_state(path)
    haeftig_regions = state["haeftig_regions"]
    assert isinstance(haeftig_regions, dict)
    if normalized not in haeftig_regions:
        return False
    del haeftig_regions[normalized]
    _write_state(path, state)
    return True


def load_source_downbeats(
    path: Path | str,
    *,
    details: Mapping[str, object] | None = None,
) -> tuple[tuple[int, ...], bool, str | None]:
    """Return ``(downbeat_frames, grid_reliable, grid_source_ref)`` for a source.

    Prefers the row's existing analysis ``details`` (the only place where real
    sample indices live). The helper deliberately refuses to invent grid points
    from BPM or seconds: ``grid_reliable`` is True only when a status-"ok" source
    downbeat series is present. A missing/unreliable grid yields an empty tuple
    and ``grid_reliable=False`` so the HÄFTIG core fails closed.
    """
    if details is not None:
        grid = source_edit_grid_from_details(details)
        if grid.bar_frames:
            return tuple(grid.bar_frames), True, grid.source_ref
    # Fallback: tolerate a bare beat_grid payload passed directly.
    if isinstance(path, (str, Path)):
        pass
    return (), False, None


def trigger_haeftig_region(
    adapter: object,
    row: object,
    *,
    downbeat_frames: Sequence[int],
    grid_reliable: bool,
    grid_source_ref: str | None = None,
) -> HaeftigSelection | None:
    """Orchestrate a HÄFTIG selection at the current audible playhead (#327).

    Returns the ``HaeftigSelection`` from the existing deterministic core, or
    ``None`` when the session->source mapping is not unambiguous (fail closed:
    no HÄFTIG region is produced). The audible position is mapped to a nominal
    source frame via the adapter's authoritative, piecewise-integrated playhead
    (never ``session_frame * rate``).
    """
    source_ref = _normalized_source_ref(getattr(row, "path", row))
    get_context = getattr(adapter, "get_haeftig_trigger_context", None)
    if get_context is None:
        return None
    context = get_context(source_ref)
    if context is None:
        return None
    trigger_source_frame, trigger_session_frame = context
    return select_haeftig_region(
        downbeat_frames=downbeat_frames,
        trigger_source_frame=trigger_source_frame,
        source_ref=source_ref,
        grid_reliable=grid_reliable,
        trigger_session_frame=trigger_session_frame,
        grid_source_ref=grid_source_ref,
    )


def capture_haeftig_region_at_playhead(
    adapter: object,
    row: object,
) -> HaeftigSelection | None:
    """UI-independent core of the Ctrl+H handler (#327).

    Maps the audible playhead to a nominal source frame via the adapter's
    authoritative source playhead, selects the enclosing 16-bar HÄFTIG region,
    and persists it. Returns the ``HaeftigSelection`` (or ``None`` when the
    session->source mapping is not unambiguous / the grid is unreliable). This is
    deliberately free of any tkinter dependency so it can be exercised headlessly.
    """
    from pathlib import Path as _Path

    source_ref = _normalized_source_ref(getattr(row, "path", row))
    downbeat_frames, grid_reliable, grid_source_ref = load_source_downbeats(
        _Path(source_ref), details=getattr(row, "details", None)
    )
    selection = trigger_haeftig_region(
        adapter,
        row,
        downbeat_frames=downbeat_frames,
        grid_reliable=grid_reliable,
        grid_source_ref=grid_source_ref,
    )
    if selection is None or selection.status != "ok" or selection.region is None:
        return selection
    save_haeftig_region(selection.region)
    return selection


def render_request_from_edit_region(
    region: WorkbenchEditRegion,
    *,
    source_audio_path: Path | str | None = None,
    asset_id: str | None = None,
) -> RenderRequest:
    """Adapt a Workbench edit region to the existing exact-range renderer."""
    source = (
        Path(source_audio_path).expanduser().resolve()
        if source_audio_path is not None
        else Path(region.source_ref).expanduser().resolve()
    )
    resolved_asset_id = (
        asset_id
        or region.region_id
        or (f"edit_{region.source_start_frame}_{region.source_end_frame_exclusive}")
    )
    return RenderRequest(
        asset_kind="section",
        asset_id=resolved_asset_id,
        source_kind="master",
        start_sample=region.source_start_frame,
        end_sample_exclusive=region.source_end_frame_exclusive,
        source_audio_path=source,
        renderable=True,
        source_identity={"workbench_edit_region": True},
    )


def render_workbench_edit_region(
    region: WorkbenchEditRegion,
    output_dir: Path | str,
    *,
    source_audio_path: Path | str | None = None,
    asset_id: str | None = None,
) -> RenderResult:
    request = render_request_from_edit_region(
        region,
        source_audio_path=source_audio_path,
        asset_id=asset_id,
    )
    return render_asset(request, Path(output_dir))


__all__ = [
    "EDIT_REGION_STATE_FILE_NAME",
    "EDIT_REGION_STATE_VERSION",
    "EditRegionValidationError",
    "SNAP_MODES",
    "SnapMode",
    "SourceEditGrid",
    "WorkbenchEditRegion",
    "audio_source_frame_info",
    "build_edit_region",
    "delete_workbench_edit_region",
    "frame_from_waveform_x",
    "load_haeftig_regions",
    "load_source_downbeats",
    "capture_haeftig_region_at_playhead",
    "load_workbench_edit_region",
    "render_request_from_edit_region",
    "render_workbench_edit_region",
    "save_haeftig_region",
    "save_workbench_edit_region",
    "delete_haeftig_regions",
    "source_edit_grid_from_details",
    "trigger_haeftig_region",
    "workbench_edit_region_state_path",
]
