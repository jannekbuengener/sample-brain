from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from src.asset_renderer import (
    ASSETS_DIR_NAME,
    COMPONENT_NAME,
    PROVENANCE_KEY,
    RenderConfig,
    RenderRequest,
    render_asset,
    render_request_from_loop_candidate,
    render_request_from_section_candidate,
)
from src.loop_candidates import LoopCandidate, LoopSourceIdentity
from src.section_candidates import (
    SectionBoundaryContext,
    SectionCandidate,
    SectionSourceIdentity,
)


def _write_pattern_source(
    path: Path, *, sr: int = 44100, frames: int = 1000, channels: int = 2
) -> np.ndarray:
    """Write a deterministic source where sample value encodes its frame index.

    Channel 0 carries the frame index as a float ramp; channel 1 carries a
    sine offset. This makes exact-slice verification possible.
    """
    rng = np.arange(frames, dtype=np.float32).reshape(-1, 1)
    ch0 = (rng / float(frames)).astype(np.float32)
    ch1 = np.sin(2.0 * np.pi * rng / 50.0).astype(np.float32)
    if channels == 1:
        data = ch0
    else:
        data = np.concatenate([ch0, ch1], axis=1)
    sf.write(str(path), data, sr, subtype="PCM_16")
    return data


def _read_full(path: Path) -> np.ndarray:
    data, _ = sf.read(str(path), always_2d=True)
    return data


def _loop_candidate(start: int, end: int, source_kind: str = "master") -> LoopCandidate:
    source = LoopSourceIdentity(source_kind=source_kind)  # type: ignore[arg-type]
    return LoopCandidate(
        asset_kind="loop",
        bar_count=4,
        start_bar=0,
        end_bar_exclusive=4,
        start_sample=start,
        end_sample_exclusive=end,
        n_samples=end - start,
        source=source,
        downbeat_grid_ref="/analysis/timeline/downbeats",
        boundary=None,  # type: ignore[arg-type]
        candidate_status="selected",
    )


def _section_candidate(
    start: int, end: int, asset_id: str, source_kind: str = "master"
) -> SectionCandidate:
    source = SectionSourceIdentity(source_kind=source_kind)  # type: ignore[arg-type]
    return SectionCandidate(
        asset_id=asset_id,
        track_ref="track_test",
        section_ref="section_01",
        start_sample=start,
        end_sample_exclusive=end,
        n_samples=end - start,
        source=source,
        arrangement_role="groove",
        arrangement_role_status="available",
        arrangement_role_source="automatic",
        automatic_role="groove",
        boundary=SectionBoundaryContext(
            source="arrangement_map", status="ok", kind="neutral_section"
        ),
    )


# --- exact slicing -----------------------------------------------------------


def test_loop_rendered_exactly_from_start_to_end_exclusive(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000, channels=2)
    cand = _loop_candidate(100, 300)

    req = render_request_from_loop_candidate(cand, src)
    res = render_asset(req, tmp_path)

    assert res.status == "rendered"
    out = _read_full(tmp_path / ASSETS_DIR_NAME / req.file_name)
    expected = _read_full(src)[100:300]
    assert out.shape == expected.shape
    assert np.array_equal(out, expected)


def test_section_rendered_exactly_from_start_to_end_exclusive(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000, channels=1)
    cand = _section_candidate(200, 500, "asset_section_01")

    req = render_request_from_section_candidate(cand, src)
    res = render_asset(req, tmp_path)

    assert res.status == "rendered"
    out = _read_full(tmp_path / ASSETS_DIR_NAME / req.file_name)
    expected = _read_full(src)[200:500]
    assert out.shape == expected.shape
    assert np.array_equal(out, expected)


def test_output_contains_exactly_n_samples(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000, channels=2)
    cand = _loop_candidate(50, 450)
    req = render_request_from_loop_candidate(cand, src)
    res = render_asset(req, tmp_path)

    assert res.output is not None
    props = res.output["audio_properties"]  # type: ignore[index]
    assert props["n_samples"] == 400  # 450 - 50
    assert props["channels"] == 2


# --- determinism -------------------------------------------------------------


def test_same_input_bounds_config_yields_identical_samples(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000, channels=2)
    cand = _loop_candidate(100, 300)

    out1 = tmp_path / "a"
    out2 = tmp_path / "b"
    res1 = render_asset(render_request_from_loop_candidate(cand, src), out1)
    res2 = render_asset(render_request_from_loop_candidate(cand, src), out2)

    h1 = res1.output["hash"]["value"]  # type: ignore[index]
    h2 = res2.output["hash"]["value"]  # type: ignore[index]
    assert h1 == h2
    assert np.array_equal(
        _read_full(out1 / ASSETS_DIR_NAME / "loop_4bar_100_300.wav"),
        _read_full(out2 / ASSETS_DIR_NAME / "loop_4bar_100_300.wav"),
    )


# --- original untouched ------------------------------------------------------


def test_source_file_unchanged_after_render(tmp_path: Path) -> None:
    from src.utils import file_hash

    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000, channels=2)
    before = file_hash(src)
    cand = _loop_candidate(100, 300)
    render_asset(render_request_from_loop_candidate(cand, src), tmp_path)
    after = file_hash(src)
    assert before == after


# --- default no DSP ----------------------------------------------------------


def test_default_has_no_fade_crossfade_normalize(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000, channels=2)
    cand = _loop_candidate(100, 300)
    req = render_request_from_loop_candidate(cand, src)
    res = render_asset(req, tmp_path)

    out = _read_full(tmp_path / ASSETS_DIR_NAME / req.file_name)
    expected = _read_full(src)[100:300]
    # Bit-exact copy of the source slice proves no fade/crossfade/normalize/stretch/pitch.
    assert np.array_equal(out, expected)
    cfg = res.renderer["configuration"]  # type: ignore[index]
    assert cfg["fade_in_samples"] == 0
    assert cfg["fade_out_samples"] == 0
    assert cfg["normalize"] is False
    assert cfg["crossfade_samples"] == 0
    assert cfg["time_stretch"] is False
    assert cfg["pitch_shift"] is False


def test_default_preserves_source_subtype_and_channels(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000, channels=2)
    cand = _loop_candidate(100, 300)
    req = render_request_from_loop_candidate(cand, src)
    res = render_asset(req, tmp_path)

    props = res.output["audio_properties"]  # type: ignore[index]
    assert props["channels"] == 2
    assert res.output["format"] == "wav/pcm_16"  # type: ignore[index]
    assert res.renderer["configuration"]["subtype_preserved"] is True  # type: ignore[index]


# --- source traceability -----------------------------------------------------


def test_master_source_traceable(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000)
    cand = _section_candidate(0, 100, "asset_section_master", source_kind="master")
    req = render_request_from_section_candidate(cand, src)
    res = render_asset(req, tmp_path)
    assert res.status == "rendered"
    assert req.source_kind == "master"
    assert res.renderer["component"] == COMPONENT_NAME


def test_stem_source_traceable(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000)
    cand = _loop_candidate(0, 100, source_kind="stem")
    req = render_request_from_loop_candidate(cand, src)
    res = render_asset(req, tmp_path)
    assert res.status == "rendered"
    assert req.source_kind == "stem"


def test_producer_group_source_traceable(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000)
    cand = _section_candidate(0, 100, "asset_section_pg", source_kind="producer_group")
    req = render_request_from_section_candidate(cand, src)
    res = render_asset(req, tmp_path)
    assert res.status == "rendered"
    assert req.source_kind == "producer_group"


# --- asset kind separation ---------------------------------------------------


def test_loop_and_section_asset_kind_remain_separate(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000, channels=1)
    loop_req = render_request_from_loop_candidate(_loop_candidate(0, 50), src)
    section_req = render_request_from_section_candidate(
        _section_candidate(0, 50, "asset_section_01"), src
    )
    loop_res = render_asset(loop_req, tmp_path)
    section_res = render_asset(section_req, tmp_path)
    assert loop_req.asset_kind == "loop"
    assert section_req.asset_kind == "section"
    assert loop_res.output["file_name"].startswith("loop_")  # type: ignore[index]
    assert section_res.output["file_name"].startswith("section_")  # type: ignore[index]


# --- portable naming ---------------------------------------------------------


def test_portable_file_name_is_deterministic(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000)
    cand = _loop_candidate(10, 20)
    req = render_request_from_loop_candidate(cand, src)
    assert req.file_name == "loop_4bar_10_20.wav"


def test_file_name_is_not_the_only_identity(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000)
    cand = _section_candidate(0, 100, "asset_section_01")
    req = render_request_from_section_candidate(cand, src)
    res = render_asset(req, tmp_path)
    # asset_id travels independently of the file name.
    assert req.asset_id == "asset_section_01"
    assert res.output["file_ref"] == f"{ASSETS_DIR_NAME}/{req.file_name}"  # type: ignore[index]


def test_output_hash_from_actual_output(tmp_path: Path) -> None:
    from src.utils import file_hash

    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000)
    cand = _loop_candidate(0, 100)
    req = render_request_from_loop_candidate(cand, src)
    res = render_asset(req, tmp_path)
    written = tmp_path / ASSETS_DIR_NAME / req.file_name
    assert res.output["hash"]["value"] == file_hash(written)  # type: ignore[index]


def test_renderer_provenance_contains_config(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000)
    cand = _loop_candidate(0, 100)
    req = render_request_from_loop_candidate(cand, src)
    res = render_asset(req, tmp_path)
    cfg = res.renderer["configuration"]  # type: ignore[index]
    assert "format" in cfg and "subtype" in cfg
    assert res.renderer["source_ref"] == PROVENANCE_KEY
    assert res.renderer["component"] == COMPONENT_NAME


# --- fail-closed boundaries --------------------------------------------------


def test_negative_start_fails_closed(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000)
    req = RenderRequest(
        asset_kind="loop",
        asset_id="x",
        source_kind="master",
        start_sample=-5,
        end_sample_exclusive=100,
        source_audio_path=src,
    )
    res = render_asset(req, tmp_path)
    assert res.status == "failed"
    assert res.output is None
    assert res.error["code"] == "INVALID_START_SAMPLE"  # type: ignore[index]


def test_end_equals_start_fails_closed(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000)
    req = RenderRequest(
        asset_kind="loop",
        asset_id="x",
        source_kind="master",
        start_sample=100,
        end_sample_exclusive=100,
        source_audio_path=src,
    )
    res = render_asset(req, tmp_path)
    assert res.status == "failed"
    assert res.error["code"] == "INVALID_RANGE"  # type: ignore[index]


def test_range_beyond_source_fails_closed(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000)
    req = render_request_from_loop_candidate(_loop_candidate(900, 1200), src)
    res = render_asset(req, tmp_path)
    assert res.status == "failed"
    assert res.error["code"] == "RANGE_BEYOND_SOURCE"  # type: ignore[index]


def test_missing_source_yields_status_error(tmp_path: Path) -> None:
    src = tmp_path / "missing.wav"
    cand = _loop_candidate(0, 100)
    req = render_request_from_loop_candidate(cand, src)
    res = render_asset(req, tmp_path)
    assert res.status == "failed"
    assert res.error["code"] == "SOURCE_NOT_FOUND"  # type: ignore[index]


def test_non_renderable_candidate_not_silently_rendered(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000)
    cand = _loop_candidate(0, 100)
    req = render_request_from_loop_candidate(cand, src, renderable=False)
    res = render_asset(req, tmp_path)
    assert res.status == "not_rendered"
    assert res.output is None
    # No asset file was written.
    assert not (tmp_path / ASSETS_DIR_NAME).exists() or not list(
        (tmp_path / ASSETS_DIR_NAME).glob("*.wav")
    )


# --- opt-in fades (provenance only, never default) ---------------------------


def test_opt_in_fade_changes_edges_and_is_recorded(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    original = _write_pattern_source(src, frames=1000, channels=1)
    cand = _loop_candidate(0, 200)
    req = render_request_from_loop_candidate(cand, src)
    res = render_asset(
        req, tmp_path, config=RenderConfig(fade_in_samples=10, fade_out_samples=10)
    )
    out = _read_full(tmp_path / ASSETS_DIR_NAME / req.file_name)
    # Faded edges differ from the verbatim slice.
    assert not np.array_equal(out, original[0:200])
    assert out[0, 0] == 0.0  # fade-in starts at zero
    cfg = res.renderer["configuration"]  # type: ignore[index]
    assert cfg["fade_in_samples"] == 10
    assert cfg["fade_out_samples"] == 10


def test_manifest_rendering_block_shape(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _write_pattern_source(src, frames=1000)
    cand = _loop_candidate(0, 100)
    req = render_request_from_loop_candidate(cand, src)
    res = render_asset(req, tmp_path)
    block = res.as_manifest_rendering()
    assert block["status"] == "rendered"
    assert "renderer" in block and "output" in block
    assert block["output"]["hash"]["algorithm"] == "sha1"  # type: ignore[index]
