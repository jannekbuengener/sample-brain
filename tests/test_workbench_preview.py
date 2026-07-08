from __future__ import annotations

from pathlib import Path

import pytest

from src.workbench_preview import (
    PreviewResult,
    WorkbenchPreviewPlayer,
    preview_toggle_action,
    validate_preview_path,
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


def test_preview_player_play_invokes_backend(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.1, frequency_hz=440.0)
    calls: list[Path] = []

    def fake_play(path: Path) -> PreviewResult:
        calls.append(path)
        return PreviewResult(ok=True)

    def fake_stop() -> None:
        pass

    player = WorkbenchPreviewPlayer(play_fn=fake_play, stop_fn=fake_stop)
    result = player.play(wav)
    assert result.ok
    assert len(calls) == 1
    assert calls[0] == wav.resolve()
    assert player.current_path == wav.resolve()


def test_preview_player_play_stops_previous(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.1, frequency_hz=440.0)
    stop_count = 0

    def fake_play(_path: Path) -> PreviewResult:
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

    def fake_play(_path: Path) -> PreviewResult:
        return PreviewResult(ok=True)

    def fake_stop() -> None:
        nonlocal stopped
        stopped = True

    player = WorkbenchPreviewPlayer(play_fn=fake_play, stop_fn=fake_stop)
    player.play(wav)
    assert player.current_path is not None
    player.stop()
    assert stopped
    assert player.current_path is None


def test_preview_player_returns_backend_error(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.1, frequency_hz=440.0)

    def fake_play(_path: Path) -> PreviewResult:
        return PreviewResult(ok=False, message="backend down")

    player = WorkbenchPreviewPlayer(play_fn=fake_play, stop_fn=lambda: None)
    result = player.play(wav)
    assert not result.ok
    assert result.message == "backend down"
    assert player.current_path is None


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
