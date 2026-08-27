from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from src.fit_variants import (
    ERR_CACHE_INSIDE_GIT,
    ERR_INVALID_SEMITONE_SHIFT,
    ERR_INVALID_TARGET_BPM,
    ERR_SOURCE_BPM_UNAVAILABLE,
    ERR_SOURCE_NOT_FOUND,
    VariantParams,
    prepare_fit_variant,
    prepare_fit_variant_from_match,
)
from src.matching import MatchResult


SAMPLE_RATE = 16000
DURATION_SECONDS = 1.0
N_FRAMES = SAMPLE_RATE


def _write_sine(
    path: Path,
    *,
    frequency: float = 440.0,
    channels: int = 1,
    phase: float = 0.0,
) -> bytes:
    t = np.arange(N_FRAMES, dtype=np.float32) / SAMPLE_RATE
    base = (0.25 * np.sin((2.0 * np.pi * frequency * t) + phase)).astype(np.float32)
    if channels == 1:
        data = base
    else:
        data = np.column_stack([base, 0.5 * base]).astype(np.float32)
    sf.write(str(path), data, SAMPLE_RATE, format="WAV", subtype="FLOAT")
    return path.read_bytes()


def _render(
    tmp_path: Path,
    *,
    source_bpm: float | None = 128.0,
    target_bpm: float | None = 128.0,
    tempo_multiplier: float = 1.0,
    semitone_shift: int = 0,
    channels: int = 1,
):
    source = tmp_path / "source.wav"
    _write_sine(source, channels=channels)
    cache = tmp_path / "cache"
    result = prepare_fit_variant(
        source,
        VariantParams(
            source_bpm=source_bpm,
            target_bpm=target_bpm,
            tempo_multiplier=tempo_multiplier,
            semitone_shift=semitone_shift,
        ),
        cache_dir=cache,
    )
    return source, cache, result


def _peak_frequency(path: Path) -> float:
    data, sr = sf.read(str(path), dtype="float32")
    if data.ndim > 1:
        data = data[:, 0]
    spectrum = np.abs(np.fft.rfft(data))
    frequencies = np.fft.rfftfreq(len(data), d=1.0 / sr)
    return float(frequencies[int(np.argmax(spectrum))])


def test_same_inputs_produce_same_variant_identity_and_cache_hit(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _write_sine(source)
    cache = tmp_path / "cache"
    params = VariantParams(128.0, 140.0, 1.0, 2)

    first = prepare_fit_variant(source, params, cache_dir=cache)
    second = prepare_fit_variant(source, params, cache_dir=cache)

    assert first.status == "ready"
    assert second.status == "cached"
    assert first.variant_id == second.variant_id
    assert len(first.variant_id or "") == 64
    assert second.output_path == first.output_path


def test_different_transform_params_produce_different_variant_ids(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _write_sine(source)
    cache = tmp_path / "cache"

    direct = prepare_fit_variant(
        source, VariantParams(128.0, 128.0, 1.0, 0), cache_dir=cache
    )
    shifted = prepare_fit_variant(
        source, VariantParams(128.0, 128.0, 1.0, 1), cache_dir=cache
    )

    assert direct.status == "ready"
    assert shifted.status == "ready"
    assert direct.variant_id != shifted.variant_id


def test_source_hash_change_invalidates_variant_identity(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _write_sine(source, phase=0.0)
    cache = tmp_path / "cache"
    params = VariantParams(128.0, 128.0, 1.0, 0)

    first = prepare_fit_variant(source, params, cache_dir=cache)
    _write_sine(source, phase=0.7)
    second = prepare_fit_variant(source, params, cache_dir=cache)

    assert first.status == "ready"
    assert second.status == "ready"
    assert first.variant_id != second.variant_id


@pytest.mark.parametrize(
    ("target_bpm", "expected_frames"),
    [
        (128.0, N_FRAMES),
        (64.0, N_FRAMES * 2),
        (140.0, round(N_FRAMES / (140.0 / 128.0))),
    ],
)
def test_tempo_render_produces_expected_frame_length(
    tmp_path: Path, target_bpm: float, expected_frames: int
) -> None:
    _, _, result = _render(tmp_path, target_bpm=target_bpm)

    assert result.status == "ready"
    assert result.output_path is not None
    info = sf.info(str(result.output_path))
    assert abs(info.frames - expected_frames) <= 1


def test_half_time_multiplier_uses_effective_source_bpm_without_double_speed(
    tmp_path: Path,
) -> None:
    _, _, result = _render(
        tmp_path,
        source_bpm=64.0,
        target_bpm=128.0,
        tempo_multiplier=2.0,
    )

    assert result.status == "ready"
    assert result.manifest is not None
    assert result.manifest["transform"]["effective_source_bpm"] == pytest.approx(128.0)
    assert result.manifest["transform"]["render_rate"] == pytest.approx(1.0)
    assert sf.info(str(result.output_path)).frames == N_FRAMES


def test_double_time_multiplier_uses_effective_source_bpm(tmp_path: Path) -> None:
    _, _, result = _render(
        tmp_path,
        source_bpm=256.0,
        target_bpm=128.0,
        tempo_multiplier=0.5,
    )

    assert result.status == "ready"
    assert result.manifest is not None
    assert result.manifest["transform"]["effective_source_bpm"] == pytest.approx(128.0)
    assert result.manifest["transform"]["render_rate"] == pytest.approx(1.0)
    assert sf.info(str(result.output_path)).frames == N_FRAMES


def test_semitone_zero_keeps_audio_when_tempo_is_unchanged(tmp_path: Path) -> None:
    source, _, result = _render(tmp_path, semitone_shift=0)

    assert result.status == "ready"
    assert result.output_path is not None
    original, _ = sf.read(str(source), dtype="float32")
    rendered, _ = sf.read(str(result.output_path), dtype="float32")
    np.testing.assert_allclose(rendered, original, atol=1e-7)


def test_plus_twelve_semitones_doubles_sine_frequency(tmp_path: Path) -> None:
    _, _, result = _render(tmp_path, semitone_shift=12)

    assert result.status == "ready"
    assert result.output_path is not None
    assert _peak_frequency(result.output_path) == pytest.approx(880.0, abs=8.0)


def test_stereo_channels_and_sample_rate_are_preserved(tmp_path: Path) -> None:
    _, _, result = _render(tmp_path, target_bpm=140.0, semitone_shift=-2, channels=2)

    assert result.status == "ready"
    assert result.output_path is not None
    info = sf.info(str(result.output_path))
    assert info.channels == 2
    assert info.samplerate == SAMPLE_RATE
    assert result.manifest is not None
    assert result.manifest["audio_properties"]["channels"] == 2
    assert result.manifest["audio_properties"]["sample_rate_hz"] == SAMPLE_RATE


def test_invalid_target_bpm_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _write_sine(source)

    result = prepare_fit_variant(
        source,
        VariantParams(128.0, 0.0, 1.0, 0),
        cache_dir=tmp_path / "cache",
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error["code"] == ERR_INVALID_TARGET_BPM


def test_invalid_semitone_range_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _write_sine(source)

    result = prepare_fit_variant(
        source,
        VariantParams(128.0, 128.0, 1.0, 13),
        cache_dir=tmp_path / "cache",
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error["code"] == ERR_INVALID_SEMITONE_SHIFT


def test_target_bpm_without_source_bpm_is_no_result(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _write_sine(source)

    result = prepare_fit_variant(
        source,
        VariantParams(None, 128.0, 1.0, 0),
        cache_dir=tmp_path / "cache",
    )

    assert result.status == "no_result"
    assert result.error is not None
    assert result.error["code"] == ERR_SOURCE_BPM_UNAVAILABLE


def test_pitch_only_variant_does_not_require_bpm(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _write_sine(source)

    result = prepare_fit_variant(
        source,
        VariantParams(None, None, 1.0, 1),
        cache_dir=tmp_path / "cache",
    )

    assert result.status == "ready"
    assert result.manifest is not None
    assert result.manifest["transform"]["render_rate"] == pytest.approx(1.0)


def test_missing_source_file_fails_closed(tmp_path: Path) -> None:
    result = prepare_fit_variant(
        tmp_path / "missing.wav",
        VariantParams(128.0, 128.0, 1.0, 0),
        cache_dir=tmp_path / "cache",
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error["code"] == ERR_SOURCE_NOT_FOUND


def test_cache_manifest_contains_no_absolute_paths_and_cache_is_external(
    tmp_path: Path,
) -> None:
    source, cache, result = _render(tmp_path, target_bpm=140.0)

    assert result.status == "ready"
    assert result.manifest is not None
    serialized = json.dumps(result.manifest, sort_keys=True)
    assert str(source.resolve()) not in serialized
    assert str(cache.resolve()) not in serialized
    assert result.manifest["output"]["file_ref"] == "prepared.wav"
    assert not (Path.cwd().resolve() in cache.resolve().parents)


def test_cache_inside_git_worktree_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _write_sine(source)

    result = prepare_fit_variant(
        source,
        VariantParams(128.0, 128.0, 1.0, 0),
        cache_dir=Path.cwd() / ".fit-variant-test-cache",
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error["code"] == ERR_CACHE_INSIDE_GIT
    assert not (Path.cwd() / ".fit-variant-test-cache").exists()


def test_stale_output_hash_forces_rerender(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _write_sine(source)
    cache = tmp_path / "cache"
    params = VariantParams(128.0, 128.0, 1.0, 0)

    first = prepare_fit_variant(source, params, cache_dir=cache)
    assert first.status == "ready"
    assert first.output_path is not None
    first.output_path.write_bytes(b"stale")

    second = prepare_fit_variant(source, params, cache_dir=cache)

    assert second.status == "ready"
    assert second.variant_id == first.variant_id
    assert second.output_path is not None
    assert second.output_path.read_bytes() != b"stale"
    assert sf.info(str(second.output_path)).frames == N_FRAMES


def test_original_source_bytes_are_never_modified(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    before = _write_sine(source)

    result = prepare_fit_variant(
        source,
        VariantParams(128.0, 140.0, 1.0, 4),
        cache_dir=tmp_path / "cache",
    )

    assert result.status == "ready"
    assert source.read_bytes() == before


def test_match_result_hints_flow_into_prepared_variant(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    _write_sine(source)
    match = MatchResult(
        sample_id=7,
        path="portable/sample.wav",
        bpm=64.0,
        key="C",
        pred_type="loop",
        bpm_score=0.9,
        key_score=1.0,
        type_score=1.0,
        total_score=0.95,
        reasons=("bpm half-time fit", "key root match"),
        bpm_relation="half_time",
        tempo_multiplier=2.0,
        semitone_hint=1,
    )

    result = prepare_fit_variant_from_match(
        source,
        match,
        target_bpm=128.0,
        cache_dir=tmp_path / "cache",
    )

    assert result.status == "ready"
    assert result.manifest is not None
    transform = result.manifest["transform"]
    assert transform["source_bpm"] == pytest.approx(64.0)
    assert transform["target_bpm"] == pytest.approx(128.0)
    assert transform["tempo_multiplier"] == pytest.approx(2.0)
    assert transform["effective_source_bpm"] == pytest.approx(128.0)
    assert transform["render_rate"] == pytest.approx(1.0)
    assert transform["semitone_shift"] == 1
    assert math.isfinite(float(result.manifest["audio_properties"]["n_samples"]))
