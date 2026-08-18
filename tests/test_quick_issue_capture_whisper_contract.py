from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from src.quick_issue_capture import _render_whisper_wav


def test_render_whisper_wav_matches_official_cli_input_contract(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    target = tmp_path / "whisper.wav"
    samples = np.zeros((48000, 2), dtype=np.float32)
    sf.write(source, samples, 48000, format="WAV", subtype="FLOAT")

    _render_whisper_wav(source, target)

    info = sf.info(target)
    assert info.samplerate == 16000
    assert info.channels == 1
    assert info.subtype == "PCM_16"
    assert info.format == "WAV"
