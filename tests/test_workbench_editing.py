from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from src.recording_take import RecordingFrameContext, finalize_recording_take
from src.session_grid import SessionTransport, compute_sync_playback_rate
from src.workbench_editing import (
    EditRegionValidationError,
    SourceEditGrid,
    WorkbenchEditRegion,
    build_edit_region,
    delete_workbench_edit_region,
    frame_from_waveform_x,
    load_workbench_edit_region,
    render_request_from_edit_region,
    render_workbench_edit_region,
    save_workbench_edit_region,
    source_edit_grid_from_details,
)
from src.workbench_preview import prepare_preview_playback_frame_region


def _write_source(path: Path, *, frames: int = 1000, sr: int = 48000) -> np.ndarray:
    data = np.linspace(-0.8, 0.8, frames, dtype=np.float32)
    sf.write(path, data, sr, subtype="FLOAT")
    return data


def test_exact_half_open_region_is_preserved() -> None:
    region = build_edit_region(
        source_ref="source.wav",
        source_start_frame=100,
        source_end_frame_exclusive=350,
        source_sample_rate=48000,
        total_source_frames=1000,
    )
    assert region.source_start_frame == 100
    assert region.source_end_frame_exclusive == 350
    assert region.frame_count == 250


@pytest.mark.parametrize(
    ("start", "end"),
    [(10, 10), (20, 10), (-1, 10), (0, 1001), (1000, 1001)],
)
def test_invalid_or_out_of_bounds_regions_are_rejected(start: int, end: int) -> None:
    with pytest.raises(EditRegionValidationError):
        build_edit_region(
            source_ref="source.wav",
            source_start_frame=start,
            source_end_frame_exclusive=end,
            source_sample_rate=48000,
            total_source_frames=1000,
        )


def test_bar_snap_is_not_invented_without_downbeats() -> None:
    with pytest.raises(EditRegionValidationError, match="bar snap unavailable"):
        build_edit_region(
            source_ref="source.wav",
            source_start_frame=90,
            source_end_frame_exclusive=410,
            source_sample_rate=48000,
            total_source_frames=1000,
            snap_mode="bar",
            grid=SourceEditGrid(beat_frames=(0, 100, 200, 300, 400, 500)),
        )


def test_reliable_source_grid_snaps_to_exact_frame_positions() -> None:
    grid = SourceEditGrid(
        beat_frames=(0, 100, 200, 300, 400, 500),
        bar_frames=(0, 400, 800),
        source_ref="beat_grid:test",
    )
    region = build_edit_region(
        source_ref="source.wav",
        source_start_frame=91,
        source_end_frame_exclusive=389,
        source_sample_rate=48000,
        total_source_frames=1000,
        snap_mode="beat",
        grid=grid,
    )
    assert (region.source_start_frame, region.source_end_frame_exclusive) == (100, 400)
    assert region.grid_source_ref == "beat_grid:test"


def test_grid_adapter_uses_sample_indices_only_and_refuses_bpm_invention() -> None:
    reliable = source_edit_grid_from_details(
        {
            "beat_grid": {
                "source_ref": "beat_grid:v1",
                "bpm": {"status": "ok", "value": 128.0},
                "beats": {"status": "ok", "sample_indices": [0, 100, 200]},
                "downbeats": {"status": "ok", "sample_indices": [0, 400, 800]},
            }
        }
    )
    assert reliable.beat_frames == (0, 100, 200)
    assert reliable.bar_frames == (0, 400, 800)

    bpm_only = source_edit_grid_from_details(
        {"beat_grid": {"bpm": {"status": "ok", "value": 128.0}}}
    )
    assert bpm_only.beat_frames == ()
    assert bpm_only.bar_frames == ()


def test_waveform_mapping_is_directly_source_frame_based() -> None:
    assert frame_from_waveform_x(0, 100, 1000) == 0
    assert frame_from_waveform_x(25, 100, 1000) == 250
    assert frame_from_waveform_x(100, 100, 1000) == 1000


def test_region_persistence_roundtrip_and_delete(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _write_source(source)
    state = tmp_path / "workbench_edit_regions.json"

    region = WorkbenchEditRegion(
        source_ref=str(source.resolve()),
        source_start_frame=120,
        source_end_frame_exclusive=620,
        source_sample_rate=48000,
        snap_mode="none",
        label="slice a",
        region_id="slice_a",
    )
    stored = save_workbench_edit_region(region, state_path=state)
    loaded = load_workbench_edit_region(source, state_path=state)

    assert loaded == stored
    assert delete_workbench_edit_region(source, state_path=state) is True
    assert load_workbench_edit_region(source, state_path=state) is None


def test_tempo_and_sync_state_do_not_change_source_region() -> None:
    region = WorkbenchEditRegion(
        source_ref="source.wav",
        source_start_frame=100,
        source_end_frame_exclusive=500,
        source_sample_rate=48000,
    )
    original_bounds = (
        region.source_start_frame,
        region.source_end_frame_exclusive,
    )

    transport = SessionTransport(sample_rate=48000, bpm=128)
    transport.set_tempo(140)
    assert compute_sync_playback_rate(140, 128, False)[0] == 1.0
    assert compute_sync_playback_rate(140, 128, True)[0] != 1.0
    assert (
        region.source_start_frame,
        region.source_end_frame_exclusive,
    ) == original_bounds


def test_preview_temp_uses_exact_source_frame_count(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _write_source(source, frames=1000)
    before = source.read_bytes()

    play_path, temp_path, result = prepare_preview_playback_frame_region(
        source.resolve(),
        123,
        789,
    )

    assert result.ok
    assert play_path is not None
    assert temp_path is not None
    assert sf.info(play_path).frames == 666
    assert source.read_bytes() == before
    temp_path.unlink(missing_ok=True)


def test_renderer_adapter_passes_exact_integer_bounds() -> None:
    region = WorkbenchEditRegion(
        source_ref="source.wav",
        source_start_frame=111,
        source_end_frame_exclusive=444,
        source_sample_rate=48000,
        region_id="slice_a",
    )
    request = render_request_from_edit_region(
        region,
        source_audio_path=Path("source.wav"),
    )
    assert request.start_sample == 111
    assert request.end_sample_exclusive == 444
    assert request.n_samples == 333


def test_rendered_frame_count_exact_and_original_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _write_source(source, frames=1000)
    before = source.read_bytes()
    region = WorkbenchEditRegion(
        source_ref=str(source.resolve()),
        source_start_frame=123,
        source_end_frame_exclusive=789,
        source_sample_rate=48000,
        region_id="slice_exact",
    )

    result = render_workbench_edit_region(region, tmp_path / "rendered")

    assert result.status == "rendered"
    assert result.output is not None
    assert result.output["audio_properties"]["n_samples"] == 666
    rendered = tmp_path / "rendered" / "assets" / result.request.file_name
    assert sf.info(rendered).frames == 666
    assert source.read_bytes() == before


def test_fresh_recording_take_can_be_used_as_edit_source(tmp_path: Path) -> None:
    db = tmp_path / "workbench_library.db"
    frames = 128
    pcm = np.zeros(frames, dtype="<f4").tobytes()
    take = finalize_recording_take(
        pcm,
        captured_frames=frames,
        context=RecordingFrameContext(
            record_start_engine_frame=1000,
            record_start_session_frame=2000,
            record_end_engine_frame_exclusive=1128,
            record_end_session_frame_exclusive=2128,
            sample_rate=48000,
            channels=1,
        ),
        destination=tmp_path / "recordings" / "take.wav",
        db_path=db,
    )

    region = WorkbenchEditRegion(
        source_ref=str(take.path),
        source_start_frame=16,
        source_end_frame_exclusive=96,
        source_sample_rate=take.context.sample_rate,
    )
    state = tmp_path / "workbench_edit_regions.json"
    stored = save_workbench_edit_region(region, state_path=state)
    assert load_workbench_edit_region(take.path, state_path=state) == stored
