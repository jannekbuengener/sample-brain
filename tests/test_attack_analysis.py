from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from src import attack_analysis
from src.attack_analysis import AttackSuggestion, suggest_attack_ms
from src.canon_audio import AudioTimebase, probe_audio
from tests.audio_fixtures import write_sine_wav


def _write_silence_then_tone(
    path: Path,
    *,
    silence_sec: float,
    tone_sec: float,
    frequency_hz: float = 440.0,
    sr: int = 44100,
    amplitude: float = 0.5,
) -> Path:
    silence_count = max(1, int(sr * silence_sec))
    tone_count = max(1, int(sr * tone_sec))
    silence = np.zeros(silence_count, dtype=np.float32)
    t = np.linspace(0.0, tone_sec, tone_count, endpoint=False, dtype=np.float32)
    tone = amplitude * np.sin(2.0 * np.pi * frequency_hz * t)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.concatenate([silence, tone]).astype(np.float32), sr, subtype="PCM_16")
    return path


def test_suggest_attack_ms_finds_onset_after_leading_silence(tmp_path: Path) -> None:
    wav = _write_silence_then_tone(tmp_path / "late.wav", silence_sec=0.2, tone_sec=0.3)
    suggestion = suggest_attack_ms(wav)
    assert suggestion is not None
    assert isinstance(suggestion, AttackSuggestion)
    assert suggestion.method == "energy_threshold"
    assert 150 <= suggestion.attack_ms <= 250


def test_suggest_attack_ms_immediate_start_near_zero(tmp_path: Path) -> None:
    wav = write_sine_wav(tmp_path / "immediate.wav", duration_sec=0.25, frequency_hz=220.0)
    suggestion = suggest_attack_ms(wav)
    assert suggestion is not None
    assert suggestion.attack_ms <= 30
    assert suggestion.confidence in {"high", "medium", "low"}


def test_suggest_attack_ms_very_short_signal(tmp_path: Path) -> None:
    wav = write_sine_wav(tmp_path / "short.wav", duration_sec=0.05, frequency_hz=300.0)
    suggestion = suggest_attack_ms(wav)
    assert suggestion is not None
    assert 0 <= suggestion.attack_ms < 50


def test_suggest_attack_ms_silent_signal_low_confidence(tmp_path: Path) -> None:
    wav = tmp_path / "silent.wav"
    sf.write(wav, np.zeros(4410, dtype=np.float32), 44100, subtype="PCM_16")
    suggestion = suggest_attack_ms(wav)
    assert suggestion is not None
    assert suggestion.attack_ms == 0
    assert suggestion.confidence == "low"
    assert "stumm" in suggestion.reason.lower()


def test_suggest_attack_ms_missing_file_returns_none(tmp_path: Path) -> None:
    assert suggest_attack_ms(tmp_path / "missing.wav") is None


def test_suggest_attack_ms_rejects_invalid_frame_ms(tmp_path: Path) -> None:
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.1, frequency_hz=440.0)
    with pytest.raises(ValueError, match="frame_ms"):
        suggest_attack_ms(wav, frame_ms=0)


def test_suggest_attack_ms_uses_canonical_audio_probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wav = write_sine_wav(tmp_path / "probed.wav", duration_sec=0.1, frequency_hz=440.0)
    calls: list[Path] = []

    def recording_probe(path: Path) -> AudioTimebase | None:
        calls.append(path)
        return probe_audio(path)

    monkeypatch.setattr(attack_analysis, "probe_audio", recording_probe)
    assert suggest_attack_ms(wav) is not None
    assert calls == [wav]


def test_suggest_attack_ms_nonpositive_probed_duration_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wav = write_sine_wav(tmp_path / "empty-duration.wav", duration_sec=0.1, frequency_hz=440.0)
    monkeypatch.setattr(attack_analysis, "probe_audio", lambda _: AudioTimebase(44100, 0))
    assert suggest_attack_ms(wav) is None


def test_duration_ms_rounds_positive_submillisecond_audio_up_to_one() -> None:
    assert attack_analysis._duration_ms(AudioTimebase(44100, 1)) == 1


def test_cue_clamp_matches_existing_boundaries() -> None:
    assert attack_analysis._clamp_cue_start_ms(-3, 100) == 0
    assert attack_analysis._clamp_cue_start_ms(100, 100) == 99
