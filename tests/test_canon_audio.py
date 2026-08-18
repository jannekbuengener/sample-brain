from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from src.canon_audio import (
    CANONICAL_SAMPLE_RATE,
    CANONICAL_CHANNELS,
    CANONICAL_SUBTYPE,
    CANONICAL_FORMAT,
    AudioTimebase,
    AudioRange,
    probe_audio,
    is_canonical_format,
    needs_conversion,
    render_canonical_wav,
    compute_range_from_seconds,
    content_hash,
    verify_provenance,
)


def _write_canonical_wav(
    path: Path, n_samples: int, sr: int = CANONICAL_SAMPLE_RATE
) -> Path:
    wave = (np.random.randn(n_samples) * 0.5).astype(np.float32)
    sf.write(path, wave, sr, subtype="PCM_16", format="WAV")
    return path


def _write_stereo_wav(
    path: Path, n_samples: int, sr: int = CANONICAL_SAMPLE_RATE
) -> Path:
    wave = (np.random.randn(n_samples, 2) * 0.5).astype(np.float32)
    sf.write(path, wave, sr, subtype="PCM_16", format="WAV")
    return path


def _write_flac_wav(
    path: Path, n_samples: int, sr: int = CANONICAL_SAMPLE_RATE
) -> Path:
    wave = (np.random.randn(n_samples) * 0.5).astype(np.float32)
    sf.write(path, wave, sr, subtype="PCM_16", format="FLAC")
    return path


def _write_float_wav(
    path: Path, n_samples: int, sr: int = CANONICAL_SAMPLE_RATE
) -> Path:
    wave = (np.random.randn(n_samples) * 0.5).astype(np.float32)
    sf.write(path, wave, sr, subtype="FLOAT", format="WAV")
    return path


def _write_wrong_sr_wav(path: Path, n_samples: int, sr: int = 22050) -> Path:
    wave = (np.random.randn(n_samples) * 0.5).astype(np.float32)
    sf.write(path, wave, sr, subtype="PCM_16", format="WAV")
    return path


# ---------------------------------------------------------------------------
# Canonical format detection
# ---------------------------------------------------------------------------


def test_is_canonical_format_wav_16bit_mono(tmp_path: Path) -> None:
    path = _write_canonical_wav(tmp_path / "canonical.wav", 44100)
    assert is_canonical_format(path) is True


def test_is_canonical_format_stereo_wav(tmp_path: Path) -> None:
    path = _write_stereo_wav(tmp_path / "stereo.wav", 44100)
    assert is_canonical_format(path) is False


def test_is_canonical_format_wrong_sr(tmp_path: Path) -> None:
    path = _write_wrong_sr_wav(tmp_path / "wrong_sr.wav", 44100)
    assert is_canonical_format(path) is False


def test_is_canonical_format_non_pcm_subtype(tmp_path: Path) -> None:
    path = _write_float_wav(tmp_path / "float.wav", 44100)
    assert is_canonical_format(path) is False


def test_is_canonical_format_flac(tmp_path: Path) -> None:
    path = _write_flac_wav(tmp_path / "test.flac", 44100)
    assert is_canonical_format(path) is False


def test_is_canonical_format_not_existing(tmp_path: Path) -> None:
    path = tmp_path / "missing.wav"
    assert is_canonical_format(path) is False


def test_is_canonical_format_no_audio(tmp_path: Path) -> None:
    path = tmp_path / "empty.dat"
    path.write_bytes(b"not audio")
    assert is_canonical_format(path) is False


def test_is_canonical_format_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.wav"
    path.write_bytes(b"")
    assert is_canonical_format(path) is False


# ---------------------------------------------------------------------------
# needs_conversion
# ---------------------------------------------------------------------------


def test_needs_conversion_canonical(tmp_path: Path) -> None:
    path = _write_canonical_wav(tmp_path / "canonical.wav", 44100)
    assert needs_conversion(path) is False


def test_needs_conversion_stereo(tmp_path: Path) -> None:
    path = _write_stereo_wav(tmp_path / "stereo.wav", 44100)
    assert needs_conversion(path) is True


def test_needs_conversion_wrong_sr(tmp_path: Path) -> None:
    path = _write_wrong_sr_wav(tmp_path / "wrong_sr.wav", 44100)
    assert needs_conversion(path) is True


def test_needs_conversion_flac(tmp_path: Path) -> None:
    path = _write_flac_wav(tmp_path / "test.flac", 44100)
    assert needs_conversion(path) is True


def test_needs_conversion_float_subtype(tmp_path: Path) -> None:
    path = _write_float_wav(tmp_path / "float.wav", 44100)
    assert needs_conversion(path) is True


# ---------------------------------------------------------------------------
# AudioTimebase
# ---------------------------------------------------------------------------


def test_audio_timebase_seconds_to_samples_floor() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    assert tb.seconds_to_samples(0.5, mode="floor") == 22050
    assert tb.seconds_to_samples(0.1, mode="floor") == 4410


def test_audio_timebase_seconds_to_samples_round() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    assert tb.seconds_to_samples(0.5, mode="round") == 22050
    assert tb.seconds_to_samples(0.1, mode="round") == 4410


def test_audio_timebase_seconds_to_samples_round_edge() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    assert tb.seconds_to_samples(0.015, mode="round") == 662


def test_audio_timebase_seconds_to_samples_floor_truncation() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    assert tb.seconds_to_samples(0.011, mode="floor") == 485
    assert tb.seconds_to_samples(0.011, mode="round") == 485


def test_audio_timebase_samples_to_seconds() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    assert tb.samples_to_seconds(1000) == pytest.approx(0.02267573696, rel=1e-6)


def test_audio_timebase_samples_to_seconds_raises_negative() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    with pytest.raises(ValueError):
        tb.samples_to_seconds(-1)


def test_audio_timebase_duration_property() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    assert tb.duration_seconds == 1.0


def test_audio_timebase_canonical_sr() -> None:
    assert CANONICAL_SAMPLE_RATE == 44100
    assert CANONICAL_CHANNELS == 1
    assert CANONICAL_SUBTYPE == "PCM_16"
    assert CANONICAL_FORMAT == "WAV"


def test_audio_timebase_raises_on_non_positive_sample_rate() -> None:
    with pytest.raises(ValueError):
        AudioTimebase(sample_rate=0, n_samples=100)


def test_audio_timebase_raises_on_negative_n_samples() -> None:
    with pytest.raises(ValueError):
        AudioTimebase(sample_rate=44100, n_samples=-1)


def test_audio_timebase_allows_zero_n_samples() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=0)
    assert tb.sample_rate == 44100
    assert tb.n_samples == 0


# ---------------------------------------------------------------------------
# probe_audio
# ---------------------------------------------------------------------------


def test_probe_audio(tmp_path: Path) -> None:
    path = _write_canonical_wav(tmp_path / "test.wav", 44100)
    tb = probe_audio(path)
    assert tb is not None
    assert tb.sample_rate == 44100
    assert tb.n_samples == 44100


def test_probe_audio_nonexistent(tmp_path: Path) -> None:
    path = tmp_path / "missing.wav"
    tb = probe_audio(path)
    assert tb is None


def test_probe_audio_no_audio(tmp_path: Path) -> None:
    path = tmp_path / "empty.dat"
    path.write_bytes(b"")
    tb = probe_audio(path)
    assert tb is None


# ---------------------------------------------------------------------------
# render_canonical_wav
# ---------------------------------------------------------------------------


def test_render_canonical_wav_preserves_original(tmp_path: Path) -> None:
    src = tmp_path / "original.wav"
    dst = tmp_path / "canonical.wav"
    _write_canonical_wav(src, 44100)

    render_canonical_wav(src, dst)

    assert src.exists()
    assert dst.exists()


def test_render_canonical_wav_produces_canonical(tmp_path: Path) -> None:
    src = tmp_path / "input.wav"
    dst = tmp_path / "output.wav"
    _write_canonical_wav(src, 44100)

    tb = render_canonical_wav(src, dst)
    assert tb.sample_rate == CANONICAL_SAMPLE_RATE
    assert tb.n_samples == 44100
    assert dst.exists()
    assert is_canonical_format(dst) is True


def test_render_canonical_wav_16bit_pcm(tmp_path: Path) -> None:
    src = tmp_path / "input.wav"
    dst = tmp_path / "output.wav"
    _write_canonical_wav(src, 44100)

    render_canonical_wav(src, dst)

    rendered, sr = sf.read(str(dst))
    assert sr == CANONICAL_SAMPLE_RATE
    assert is_canonical_format(dst) is True


def test_render_canonical_wav_same_path_raises(tmp_path: Path) -> None:
    path = tmp_path / "same.wav"
    _write_canonical_wav(path, 44100)
    with pytest.raises(ValueError):
        render_canonical_wav(path, path)


def test_render_canonical_wav_creates_nested_output(tmp_path: Path) -> None:
    src = tmp_path / "input.wav"
    dst = tmp_path / "nested" / "dir" / "output.wav"
    _write_canonical_wav(src, 44100)

    tb = render_canonical_wav(src, dst)
    assert tb.n_samples == 44100
    assert dst.exists()


def test_render_canonical_wav_nonexistent_source_raises(tmp_path: Path) -> None:
    src = tmp_path / "missing.wav"
    dst = tmp_path / "output.wav"
    with pytest.raises((ValueError, FileNotFoundError)):
        render_canonical_wav(src, dst)


def test_render_canonical_wav_from_stereo(tmp_path: Path) -> None:
    src = tmp_path / "stereo.wav"
    dst = tmp_path / "mono.wav"
    _write_stereo_wav(src, 44100)

    tb = render_canonical_wav(src, dst)
    assert tb.n_samples == 44100
    assert tb.sample_rate == CANONICAL_SAMPLE_RATE
    assert is_canonical_format(dst) is True


def test_render_canonical_wav_from_wrong_sr(tmp_path: Path) -> None:
    src = tmp_path / "wrong_sr.wav"
    dst = tmp_path / "canonical.wav"
    _write_wrong_sr_wav(src, 44100, sr=22050)

    tb = render_canonical_wav(src, dst)
    assert tb.sample_rate == CANONICAL_SAMPLE_RATE


# ---------------------------------------------------------------------------
# compute_range_from_seconds
# ---------------------------------------------------------------------------


def test_compute_range_from_seconds_round_floor() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    rng = compute_range_from_seconds(tb, 0.0, 0.5, rounding="floor")
    assert rng.start_sample == 0
    assert rng.end_sample == 22050
    assert rng.n_samples == 22050


def test_compute_range_from_seconds_round_round() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    rng = compute_range_from_seconds(tb, 0.5, 1.0, rounding="round")
    assert rng.start_sample == 22050
    assert rng.end_sample == 44100
    assert rng.n_samples == 22050


def test_compute_range_from_seconds_full_duration() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    rng = compute_range_from_seconds(tb, 0.0, 44100 / 44100, rounding="round")
    assert rng.start_sample == 0
    assert rng.end_sample == 44100


def test_compute_range_from_seconds_negative_start_raises() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    with pytest.raises(ValueError):
        compute_range_from_seconds(tb, -0.1, 1.0, rounding="round")


def test_compute_range_from_seconds_end_leq_start_raises() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    with pytest.raises(ValueError):
        compute_range_from_seconds(tb, 0.0, 0.0, rounding="round")
    with pytest.raises(ValueError):
        compute_range_from_seconds(tb, 0.5, 0.4, rounding="round")


def test_compute_range_from_seconds_exceeds_duration() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    with pytest.raises(ValueError):
        compute_range_from_seconds(tb, 0.0, 2.0, rounding="round")


def test_compute_range_from_seconds_floor_truncates() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    rng = compute_range_from_seconds(tb, 0.0, 22050.5 / 44100, rounding="floor")
    # 22050.5/44100 ≈ 0.50001... * 44100 = 22050.49995 -> floor = 22050
    assert rng.end_sample == 22050


# ---------------------------------------------------------------------------
# AudioRange
# ---------------------------------------------------------------------------


def test_audio_range_to_seconds() -> None:
    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    rng = AudioRange(start_sample=22050, end_sample=44100)
    start_sec, end_sec = rng.to_seconds(tb)
    assert start_sec == pytest.approx(0.5, rel=1e-10)
    assert end_sec == pytest.approx(1.0, rel=1e-10)


def test_audio_range_contains_sample() -> None:
    rng = AudioRange(start_sample=1000, end_sample=2000)
    assert rng.contains_sample(1000)
    assert rng.contains_sample(1500)
    assert rng.contains_sample(1999)
    assert not rng.contains_sample(999)
    assert not rng.contains_sample(2000)


def test_audio_range_n_samples() -> None:
    rng = AudioRange(start_sample=1000, end_sample=2000)
    assert rng.n_samples == 1000


def test_audio_range_raises_on_negative_start() -> None:
    with pytest.raises(ValueError):
        AudioRange(start_sample=-1, end_sample=10)


def test_audio_range_raises_on_empty_range() -> None:
    with pytest.raises(ValueError):
        AudioRange(start_sample=10, end_sample=10)


def test_audio_range_raises_on_end_lt_start() -> None:
    with pytest.raises(ValueError):
        AudioRange(start_sample=20, end_sample=10)


# ---------------------------------------------------------------------------
# content_hash and verify_provenance
# ---------------------------------------------------------------------------


def test_content_hash_returns_sha256(tmp_path: Path) -> None:
    path = _write_canonical_wav(tmp_path / "test.wav", 44100)
    h = content_hash(path)
    assert isinstance(h, str)
    assert len(h) == 64


def test_content_hash_deterministic(tmp_path: Path) -> None:
    path = _write_canonical_wav(tmp_path / "test.wav", 44100, sr=44100)
    h1 = content_hash(path)
    h2 = content_hash(path)
    assert h1 == h2


def test_content_hash_different_for_different_content(tmp_path: Path) -> None:
    p1 = tmp_path / "a.wav"
    p2 = tmp_path / "b.wav"
    # Deterministic but different content
    sf.write(
        p1,
        np.linspace(-0.5, 0.5, 4410, dtype=np.float32),
        44100,
        subtype="PCM_16",
        format="WAV",
    )
    sf.write(
        p2,
        np.linspace(0.5, -0.5, 4410, dtype=np.float32),
        44100,
        subtype="PCM_16",
        format="WAV",
    )
    assert content_hash(p1) != content_hash(p2)


def test_content_hash_same_for_same_content(tmp_path: Path) -> None:
    p1 = tmp_path / "a.wav"
    p2 = tmp_path / "b.wav"
    wave = np.linspace(-0.5, 0.5, 4410, dtype=np.float32)
    sf.write(p1, wave, 44100, subtype="PCM_16", format="WAV")
    sf.write(p2, wave, 44100, subtype="PCM_16", format="WAV")
    assert content_hash(p1) == content_hash(p2)


def test_verify_provenance_same_file(tmp_path: Path) -> None:
    path = _write_canonical_wav(tmp_path / "test.wav", 44100)
    orig_hash, work_hash, same = verify_provenance(path, path)
    assert same is True
    # When comparing same file, hashes should be equal
    assert orig_hash == work_hash


def test_verify_provenance_different_files(tmp_path: Path) -> None:
    p1 = tmp_path / "a.wav"
    p2 = tmp_path / "b.wav"
    # Generate clearly different content
    wave1 = np.linspace(-0.5, 0.5, 4410, dtype=np.float32)
    wave2 = np.linspace(0.5, -0.5, 4410, dtype=np.float32)
    sf.write(p1, wave1, 44100, subtype="PCM_16", format="WAV")
    sf.write(p2, wave2, 44100, subtype="PCM_16", format="WAV")
    orig_hash, work_hash, same = verify_provenance(p1, p2)
    assert same is False
    assert orig_hash != work_hash


def test_verify_provenance_does_not_modify_originals(tmp_path: Path) -> None:
    # First, create an original file
    original_path = tmp_path / "original.wav"
    _write_stereo_wav(original_path, 44100)

    # Store original hash before conversion
    orig_hash_before = content_hash(original_path)

    # Convert to canonical format
    dst_path = tmp_path / "canonical.wav"
    render_canonical_wav(original_path, dst_path)

    # After conversion, original file should still exist and have same hash
    orig_hash_after = content_hash(original_path)
    assert orig_hash_before == orig_hash_after
    assert orig_hash_before is not None


def test_verify_provenance_requires_existing_paths(tmp_path: Path) -> None:
    path = tmp_path / "missing.wav"
    with pytest.raises((FileNotFoundError, OSError)):
        verify_provenance(path, path)


def test_content_hash_deterministic_identical_bytes(tmp_path: Path) -> None:
    p1 = tmp_path / "a.wav"
    p2 = tmp_path / "b.wav"
    n = 4410
    t_arr = np.linspace(0.0, n / 44100.0, n, endpoint=False, dtype=np.float32)
    wave = (np.sin(2 * np.pi * 5 * t_arr) * 0.5).astype(np.float32)
    sf.write(p1, wave, 44100, subtype="PCM_16", format="WAV")
    sf.write(p2, wave, 44100, subtype="PCM_16", format="WAV")
    assert content_hash(p1) == content_hash(p2)
