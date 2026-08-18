from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf

from .utils import file_hash
from .config import ANALYZE_SR

RoundingMode = Literal["floor", "round"]

CANONICAL_SAMPLE_RATE = ANALYZE_SR
CANONICAL_CHANNELS = 1
CANONICAL_SUBTYPE = "PCM_16"
CANONICAL_FORMAT = "WAV"


@dataclass(frozen=True)
class AudioTimebase:
    sample_rate: int
    n_samples: int

    def __post_init__(self):
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        # Allow n_samples=0 for edge cases like empty tracks
        if self.n_samples < 0:
            raise ValueError("n_samples must be non-negative")

    def seconds_to_samples(self, seconds: float, mode: RoundingMode = "round") -> int:
        raw = seconds * self.sample_rate
        if mode == "floor":
            return int(np.floor(raw))
        return int(np.round(raw))

    def samples_to_seconds(self, samples: int) -> float:
        if samples < 0:
            raise ValueError("samples must be non-negative")
        return samples / self.sample_rate

    @property
    def duration_seconds(self) -> float:
        return self.n_samples / self.sample_rate


@dataclass(frozen=True)
class AudioRange:
    start_sample: int
    end_sample: int

    def __post_init__(self):
        if self.start_sample < 0:
            raise ValueError("start_sample must be non-negative")
        if self.end_sample <= self.start_sample:
            raise ValueError(
                "end_sample must be greater than start_sample (exclusive end)"
            )

    @property
    def n_samples(self) -> int:
        return self.end_sample - self.start_sample

    def to_seconds(self, tb: AudioTimebase) -> tuple[float, float]:
        return (
            tb.samples_to_seconds(self.start_sample),
            tb.samples_to_seconds(self.end_sample),
        )

    def contains_sample(self, sample: int) -> bool:
        return self.start_sample <= sample < self.end_sample


def probe_audio(path: Path) -> AudioTimebase | None:
    try:
        with sf.SoundFile(str(path)) as f:
            sr = f.samplerate
            n_samples = len(f)
            return AudioTimebase(sample_rate=sr, n_samples=n_samples)
    except Exception:
        return None


def _is_pcm_subtype(subtype: str | None) -> bool:
    if subtype is None:
        return False
    return subtype == "PCM_16"


def is_canonical_format(path: Path) -> bool:
    try:
        with sf.SoundFile(str(path)) as f:
            if f.samplerate != CANONICAL_SAMPLE_RATE:
                return False
            if f.channels != CANONICAL_CHANNELS:
                return False
            if f.format != "WAV":
                return False
            if not _is_pcm_subtype(f.subtype):
                return False
        return True
    except Exception:
        return False


def needs_conversion(path: Path) -> bool:
    return not is_canonical_format(path)


def _load_audio_mono(path: Path, target_sr: int) -> tuple[np.ndarray, int]:
    if not path.is_file():
        raise FileNotFoundError(path)

    try:
        y, sr = sf.read(str(path), dtype="float32", always_2d=False)
        if y is None:
            raise ValueError("empty audio")
        if isinstance(y, np.ndarray) and y.ndim > 1:
            y = np.mean(y, axis=1)
        y = np.asarray(y, dtype=np.float32)
        if y.size == 0:
            raise ValueError("empty audio")
        if sr != target_sr:
            import librosa

            y = librosa.resample(y, orig_sr=sr, target_sr=target_sr)
            sr = target_sr
        return y, int(sr)
    except Exception:
        import librosa

        y, sr = librosa.load(str(path), sr=target_sr, mono=True)
        if y is None or sr is None:
            raise ValueError("failed to load audio")
        y = np.asarray(y, dtype=np.float32)
        if y.size == 0:
            raise ValueError("empty audio")
        return y, int(sr)


def render_canonical_wav(src_path: Path, dst_path: Path) -> AudioTimebase:
    if src_path.resolve() == dst_path.resolve():
        raise ValueError("source and destination must be different paths")

    y, sr = _load_audio_mono(src_path, CANONICAL_SAMPLE_RATE)
    if sr != CANONICAL_SAMPLE_RATE:
        raise ValueError(f"resample failed: expected {CANONICAL_SAMPLE_RATE}, got {sr}")

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(
        dst_path,
        y,
        CANONICAL_SAMPLE_RATE,
        subtype=CANONICAL_SUBTYPE,
        format=CANONICAL_FORMAT,
    )

    n_samples = len(y)
    return AudioTimebase(sample_rate=CANONICAL_SAMPLE_RATE, n_samples=n_samples)


def compute_range_from_seconds(
    tb: AudioTimebase,
    start_sec: float,
    end_sec: float,
    rounding: RoundingMode = "round",
) -> AudioRange:
    if start_sec < 0:
        raise ValueError("start_sec must be non-negative")
    if end_sec <= start_sec:
        raise ValueError("end_sec must be greater than start_sec")
    if end_sec > tb.duration_seconds + 1e-9:
        raise ValueError("end_sec exceeds audio duration")

    start = tb.seconds_to_samples(start_sec, rounding)
    end = tb.seconds_to_samples(end_sec, rounding)

    if end <= start:
        end = start + 1

    return AudioRange(start_sample=start, end_sample=end)


def content_hash(path: Path) -> str:
    return file_hash(path)


def verify_provenance(original_path: Path, working_path: Path) -> tuple[str, str, bool]:
    """Verify portable hash-based provenance link between original and working audio.

    Returns (original_hash, working_hash, identical_content).
    ``identical_content`` is True when both paths point to byte-identical files
    (e.g. Bypass case where the original is used directly as the working file).
    When a canonical conversion has been performed, the hashes differ and
    ``identical_content`` is False — the link is then established by recording
    both hashes in the Track Map ``source`` block, never by absolute paths.
    """
    original_hash = content_hash(original_path)
    working_hash = content_hash(working_path)
    return original_hash, working_hash, original_hash == working_hash


__all__ = [
    "CANONICAL_SAMPLE_RATE",
    "CANONICAL_CHANNELS",
    "CANONICAL_SUBTYPE",
    "CANONICAL_FORMAT",
    "RoundingMode",
    "AudioTimebase",
    "AudioRange",
    "probe_audio",
    "is_canonical_format",
    "needs_conversion",
    "render_canonical_wav",
    "compute_range_from_seconds",
    "content_hash",
    "verify_provenance",
]
