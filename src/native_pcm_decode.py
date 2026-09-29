"""Offline decode of local audio to native-engine-compatible float32 PCM.

Shared by Screen-1 audition and the Sequencer PCM cache. Decode runs outside
the realtime audio callback. This module owns no cache and no playback policy.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

__all__ = ["decode_native_pcm"]


def decode_native_pcm(
    path: Path | str,
    *,
    sample_rate: int,
    start_ms: int = 0,
) -> tuple[np.ndarray, int]:
    """Decode immutable source audio to finite PCM at the engine sample rate.

    Returns a contiguous float32 array shaped ``(frames, channels)`` with
    ``channels`` in ``{1, 2}``. Sources with more than two channels are
    collapsed to mono by averaging. Raises ``ValueError`` for empty audio or
    an out-of-range ``start_ms``; I/O and decoder errors propagate to the caller.
    """
    target_rate = int(sample_rate)
    if target_rate <= 0:
        raise ValueError("sample_rate must be a positive int")

    data, source_rate = sf.read(
        str(path),
        dtype="float32",
        always_2d=True,
    )
    if data.size == 0:
        raise ValueError("Audio enthält keine Samples.")
    if data.shape[1] > 2:
        data = np.mean(data, axis=1, keepdims=True, dtype=np.float32)
    if int(source_rate) != target_rate:
        import librosa

        data = librosa.resample(
            data.T,
            orig_sr=int(source_rate),
            target_sr=target_rate,
            axis=-1,
        ).T
    start_frame = int(max(0, int(start_ms)) * target_rate / 1_000)
    if start_frame >= data.shape[0]:
        raise ValueError("Startposition liegt außerhalb der Audiodatei.")
    pcm = np.ascontiguousarray(data[start_frame:], dtype=np.float32)
    return pcm, int(pcm.shape[1])
