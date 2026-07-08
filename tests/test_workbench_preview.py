from __future__ import annotations

from pathlib import Path

import pytest

from src.workbench_preview import (
    PreviewResult,
    WorkbenchPreviewPlayer,
    normalize_preview_start_ms,
    prepare_preview_playback_path,
    preview_toggle_action,
    validate_preview_path,
    validate_preview_start_ms,
)
from tests.audio_fixtures import write_sine_wav


def test_validate_preview_path_rejects_empty():
    result = validate_preview_path("")
    assert not result.ok
    assert "ausgewählt" in result.message.lower()


def test_validate_preview_path_rejects_missing_file(tmp_path: Path):
    missing = tmp_path / "missing.wav"
    result = validate_preview_path(missing)
    assert not result.ok
    assert "nicht gefunden" in result.message.lower()


def test_validate_preview_path_accepts_existing_file(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.1, frequency_hz=440.0)
    result = validate_preview_path(wav)
    assert result.ok


def test_normalize_preview_start_ms_clamps_negative():
    assert normalize_preview_start_ms(-50) == 0
    assert normalize_preview_start_ms(0) == 0
    assert normalize_preview_start_ms(120) == 120


def test_validate_preview_start_ms_rejects_offset_beyond_duration(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.2, frequency_hz=440.0)
    result = validate_preview_start_ms(wav, 99999)
    assert not result.ok
    assert "außerhalb" in result.message.lower()


def test_prepare_preview_playback_path_uses_original_wav_at_zero(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.2, frequency_hz=440.0)
    play_path, temp_path, result = prepare_preview_playback_path(wav.resolve(), 0)
    assert result.ok
    assert play_path == wav.resolve()
    assert temp_path is None


def test_prepare_preview_playback_path_creates_temp_for_offset(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.4, frequency_hz=440.0)
    play_path, temp_path, result = prepare_preview_playback_path(wav.resolve(), 100)
    assert result.ok
    assert play_path is not None
    assert temp_path is not None
    assert play_path == temp_path
    assert temp_path.name.startswith("sample_brain_preview_")
    assert temp_path.is_file()
    temp_path.unlink(missing_ok=True)


def test_preview_player_play_invokes_backend(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.1, frequency_hz=440.0)
    calls: list[tuple[Path, int]] = []

    def fake_play(path: Path, start_ms: int = 0) -> PreviewResult:
        calls.append((path, start_ms))
        return PreviewResult(ok=True)

    def fake_stop() -> None:
        pass

    player = WorkbenchPreviewPlayer(play_fn=fake_play, stop_fn=fake_stop)
    result = player.play(wav)
    assert result.ok
    assert len(calls) == 1
    assert calls[0] == (wav.resolve(), 0)
    assert player.current_path == wav.resolve()
    assert player.current_start_ms == 0


def test_preview_player_play_passes_start_ms(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.4, frequency_hz=440.0)
    calls: list[int] = []

    def fake_play(_path: Path, start_ms: int = 0) -> PreviewResult:
        calls.append(start_ms)
        return PreviewResult(ok=True)

    player = WorkbenchPreviewPlayer(play_fn=fake_play, stop_fn=lambda: None)
    result = player.play(wav, start_ms=150)
    assert result.ok
    assert calls == [150]
    assert player.current_start_ms == 150


def test_preview_player_play_stops_previous(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.1, frequency_hz=440.0)
    stop_count = 0

    def fake_play(_path: Path, _start_ms: int = 0) -> PreviewResult:
        return PreviewResult(ok=True)

    def fake_stop() -> None:
        nonlocal stop_count
        stop_count += 1

    player = WorkbenchPreviewPlayer(play_fn=fake_play, stop_fn=fake_stop)
    player.play(wav)
    player.play(wav)
    assert stop_count >= 1


def test_preview_player_stop_clears_current_path(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.1, frequency_hz=440.0)
    stopped = False

    def fake_play(_path: Path, _start_ms: int = 0) -> PreviewResult:
        return PreviewResult(ok=True)

    def fake_stop() -> None:
        nonlocal stopped
        stopped = True

    player = WorkbenchPreviewPlayer(play_fn=fake_play, stop_fn=fake_stop)
    player.play(wav, start_ms=10)
    assert player.current_path is not None
    player.stop()
    assert stopped
    assert player.current_path is None
    assert player.current_start_ms == 0


def test_preview_player_returns_backend_error(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.1, frequency_hz=440.0)

    def fake_play(_path: Path, _start_ms: int = 0) -> PreviewResult:
        return PreviewResult(ok=False, message="backend down")

    player = WorkbenchPreviewPlayer(play_fn=fake_play, stop_fn=lambda: None)
    result = player.play(wav)
    assert not result.ok
    assert result.message == "backend down"
    assert player.current_path is None


def test_preview_player_stop_invokes_cleanup_fn(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.1, frequency_hz=440.0)
    cleanup_calls = 0

    def fake_play(_path: Path, _start_ms: int = 0) -> PreviewResult:
        return PreviewResult(ok=True)

    def fake_stop() -> None:
        nonlocal cleanup_calls
        cleanup_calls += 1

    player = WorkbenchPreviewPlayer(play_fn=fake_play, stop_fn=fake_stop)
    player.play(wav, start_ms=0)
    player.stop()
    assert cleanup_calls >= 1


def test_preview_toggle_action_stops_same_file(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.1, frequency_hz=440.0)
    resolved = wav.resolve()
    assert (
        preview_toggle_action(
            is_playing=True,
            current_path=resolved,
            requested_path=wav,
        )
        == "stop"
    )


def test_preview_toggle_action_plays_different_or_idle(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.1, frequency_hz=440.0)
    other = write_sine_wav(tmp_path / "other.wav", duration_sec=0.1, frequency_hz=220.0)
    assert preview_toggle_action(is_playing=False, current_path=None, requested_path=wav) == "play"
    assert (
        preview_toggle_action(
            is_playing=True,
            current_path=wav.resolve(),
            requested_path=other,
        )
        == "play"
    )
