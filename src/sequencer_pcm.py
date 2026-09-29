"""Production PCM cache/decode provider for sequencer ``pcm_for_path``.

Owns offline decode + bounded LRU cache keyed by ``(path, sample_rate)``.
Does not schedule voices and does not own Screen-1 audition playback.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .native_audio import PcmBufferConfig
from .native_pcm_decode import decode_native_pcm

__all__ = ["SequencerPcmProvider", "canonicalize_pcm_path"]

DecodeFn = Callable[..., tuple[np.ndarray, int]]

DEFAULT_MAX_ENTRIES = 64


def canonicalize_pcm_path(path: str | Path) -> str:
    """Return a stable cache key for a filesystem path.

    Collapses ``.`` / ``..``, resolves to an absolute path, and follows
    existing symlinks when possible. Trailing whitespace from the original
    string is preserved (``Path`` would otherwise drop it on some platforms).
    """
    raw = str(path)
    body = raw.rstrip(" \t")
    trailing = raw[len(body) :]
    candidate = Path(body) if body else Path(".")
    try:
        resolved = str(candidate.resolve(strict=False))
    except OSError:
        try:
            resolved = str(candidate.absolute())
        except OSError:
            resolved = str(candidate)
    return resolved + trailing


class SequencerPcmProvider:
    """Callable path → ``PcmBufferConfig | None`` with fail-soft LRU cache."""

    def __init__(
        self,
        sample_rate: int,
        *,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        decode_fn: DecodeFn | None = None,
    ) -> None:
        rate = int(sample_rate)
        if rate <= 0:
            raise ValueError("sample_rate must be a positive int")
        entries = int(max_entries)
        if entries <= 0:
            raise ValueError("max_entries must be a positive int")
        self._sample_rate = rate
        self._max_entries = entries
        self._decode_fn: DecodeFn = decode_fn or decode_native_pcm
        self._cache: OrderedDict[tuple[str, int], PcmBufferConfig] = OrderedDict()

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def max_entries(self) -> int:
        return self._max_entries

    def cache_size(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        self._cache.clear()

    def pcm_for_path(self, path: str) -> PcmBufferConfig | None:
        if path is None:
            return None
        text = str(path)
        # Reject empty / all-whitespace only — do not strip meaningful trailing spaces.
        if text == "" or text.isspace():
            return None

        key = (canonicalize_pcm_path(text), self._sample_rate)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached

        try:
            # Pass the original string so trailing whitespace is not lost via Path().
            pcm_array, channels = self._decode_fn(
                text,
                sample_rate=self._sample_rate,
                start_ms=0,
            )
        except Exception:
            return None

        config = self._validated_buffer(pcm_array, channels)
        if config is None:
            return None

        self._cache[key] = config
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)
        return config

    def __call__(self, path: str) -> PcmBufferConfig | None:
        return self.pcm_for_path(path)

    @staticmethod
    def _validated_buffer(
        pcm_array: object,
        channels: object,
    ) -> PcmBufferConfig | None:
        try:
            channel_count = int(channels)
        except (TypeError, ValueError):
            return None
        if channel_count not in (1, 2):
            return None

        samples = np.asarray(pcm_array, dtype=np.float32)
        if samples.size == 0:
            return None
        if not np.isfinite(samples).all():
            return None
        if samples.ndim == 2:
            if samples.shape[1] != channel_count:
                return None
        else:
            if samples.ndim != 1:
                return None
            if samples.size % channel_count:
                return None
        samples = np.ascontiguousarray(samples, dtype=np.float32)
        return PcmBufferConfig(samples=samples, channels=channel_count)
