"""Production PCM cache/decode provider for sequencer ``pcm_for_path``.

Owns offline decode + bounded LRU cache keyed by ``(canonical path, sample_rate)``.
Does not schedule voices and does not own Screen-1 audition playback.

``PathPcmCache`` is the plan-facing alias for ``SequencerPcmProvider``.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .native_audio import PcmBufferConfig
from .native_pcm_decode import decode_native_pcm

__all__ = [
    "PathPcmCache",
    "SequencerPcmProvider",
    "canonicalize_pcm_path",
    "decode_pcm_for_native",
]

DecodeFn = Callable[..., tuple[np.ndarray, int]]

DEFAULT_MAX_ENTRIES = 64


def canonicalize_pcm_path(path: str | Path) -> str:
    """Return a stable cache key for a filesystem path.

    Collapses ``.`` / ``..``, resolves to an absolute path, and follows
    existing symlinks when possible. The full input string is preserved —
    trailing whitespace is not stripped before resolution. On case-insensitive
    volumes, existing path components are rewritten to on-disk spelling so
    aliases that differ only by case share one cache entry.
    """
    raw = str(path)
    try:
        # os.path keeps trailing whitespace that pathlib would drop.
        resolved = os.path.realpath(raw)
    except (OSError, RuntimeError, ValueError):
        try:
            resolved = os.path.abspath(os.path.normpath(raw))
        except (OSError, RuntimeError, ValueError):
            return raw

    body = resolved.rstrip(" \t")
    trailing = resolved[len(body) :]
    try:
        body = _match_on_disk_case(body)
    except OSError:
        body = os.path.normcase(body)
    return body + trailing


def _match_on_disk_case(path: str) -> str:
    """Rewrite existing path components to the filesystem's stored spelling."""
    if not path:
        return path
    drive, tail = os.path.splitdrive(path)
    if os.name == "nt":
        drive = drive.upper()
    if not tail:
        return drive

    absolute = tail.startswith(os.sep) or tail.startswith("/")
    parts = [part for part in tail.split(os.sep) if part not in ("", ".")]
    current = drive + os.sep if absolute else (drive or ".")
    built: list[str] = []
    for part in parts:
        if part == "..":
            if built:
                built.pop()
                current = (
                    drive + os.sep + os.sep.join(built)
                    if absolute
                    else (os.sep.join(built) if built else (drive or "."))
                )
            continue
        try:
            entries = os.listdir(current)
        except OSError:
            built.append(part)
            current = os.path.join(current, part)
            continue
        match = next((entry for entry in entries if entry == part), None)
        if match is None:
            lowered = part.casefold()
            match = next(
                (entry for entry in entries if entry.casefold() == lowered),
                part,
            )
        built.append(match)
        current = os.path.join(current, match)

    if absolute:
        return drive + os.sep + os.sep.join(built)
    if drive:
        return drive + os.sep.join(built)
    return os.sep.join(built) if built else path


def decode_pcm_for_native(
    path: str | Path,
    *,
    sample_rate: int,
) -> PcmBufferConfig:
    """Full-file decode to a native-compatible ``PcmBufferConfig`` (raises on failure)."""
    pcm_array, channels = decode_native_pcm(
        path,
        sample_rate=int(sample_rate),
        start_ms=0,
    )
    config = SequencerPcmProvider._validated_buffer(pcm_array, channels)
    if config is None:
        raise ValueError("Decoded PCM is empty, non-finite, or has unsupported channels")
    return config


class SequencerPcmProvider:
    """Callable path → ``PcmBufferConfig | None`` with fail-soft LRU cache.

    Only successful decodes are cached (no durable negative cache). Call ``clear()``
    to drop entries. Decode runs outside the realtime audio callback.
    """

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

        try:
            key = (canonicalize_pcm_path(text), self._sample_rate)
        except (OSError, RuntimeError, ValueError):
            return None

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
            config = self._validated_buffer(pcm_array, channels)
        except Exception:
            return None

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

        try:
            samples = np.asarray(pcm_array, dtype=np.float32)
        except (TypeError, ValueError):
            return None
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


# Plan-facing name from the #676 session plan.
PathPcmCache = SequencerPcmProvider
