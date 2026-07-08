"""Workbench audio preview — play selected samples without modifying originals."""
from __future__ import annotations

import os
import platform
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import soundfile as sf

from .workbench_waveform import read_audio_duration_ms

PreviewPlayFn = Callable[[Path, int], "PreviewResult"]
PreviewStopFn = Callable[[], None]

_PREVIEW_TEMP_PREFIX = "sample_brain_preview_"


@dataclass(frozen=True)
class PreviewResult:
    ok: bool
    message: str = ""


_process: subprocess.Popen[bytes] | None = None
_temp_wav: Path | None = None
_temp_lock = threading.Lock()


def normalize_preview_start_ms(start_ms: int) -> int:
    """Return a non-negative preview offset in milliseconds."""
    return max(0, int(start_ms))


def validate_preview_start_ms(path: Path | str, start_ms: int) -> PreviewResult:
    """Validate cue offset for preview playback."""
    offset = normalize_preview_start_ms(start_ms)
    if offset <= 0:
        return PreviewResult(ok=True)
    duration_ms = read_audio_duration_ms(path)
    if duration_ms is None:
        return PreviewResult(ok=False, message="Dauer unbekannt — Cue-Preview nicht möglich.")
    if offset >= duration_ms:
        return PreviewResult(ok=False, message="Cue liegt außerhalb der Datei.")
    return PreviewResult(ok=True)


def _write_pcm_wav_temp(source: Path) -> Path:
    """Decode *source* to a temporary 16-bit PCM WAV (original file unchanged)."""
    data, sr = sf.read(source, dtype="float32", always_2d=False)
    if getattr(data, "size", 0) == 0:
        raise ValueError("empty audio")
    fd, name = tempfile.mkstemp(suffix=".wav", prefix=_PREVIEW_TEMP_PREFIX)
    os.close(fd)
    temp = Path(name)
    sf.write(temp, data, sr, subtype="PCM_16")
    return temp


def _write_pcm_wav_temp_from_offset(source: Path, start_ms: int) -> Path:
    """Decode *source* from *start_ms* into a temporary WAV (original unchanged)."""
    start_sec = normalize_preview_start_ms(start_ms) / 1000.0
    info = sf.info(source)
    start_frame = int(start_sec * info.samplerate)
    data, sr = sf.read(source, dtype="float32", always_2d=False, start=start_frame)
    if getattr(data, "size", 0) == 0:
        raise ValueError("empty audio after cue offset")
    fd, name = tempfile.mkstemp(suffix=".wav", prefix=_PREVIEW_TEMP_PREFIX)
    os.close(fd)
    temp = Path(name)
    sf.write(temp, data, sr, subtype="PCM_16")
    return temp


def prepare_preview_playback_path(
    source: Path,
    start_ms: int = 0,
) -> tuple[Path | None, Path | None, PreviewResult]:
    """Return playback path, optional temp path, and status."""
    offset = normalize_preview_start_ms(start_ms)
    offset_check = validate_preview_start_ms(source, offset)
    if not offset_check.ok:
        return None, None, offset_check

    if offset > 0:
        try:
            temp = _write_pcm_wav_temp_from_offset(source, offset)
        except Exception as exc:
            return None, None, PreviewResult(ok=False, message=f"Preview-Vorbereitung fehlgeschlagen: {exc}")
        return temp, temp, PreviewResult(ok=True)

    if source.suffix.lower() == ".wav":
        return source, None, PreviewResult(ok=True)

    try:
        temp = _write_pcm_wav_temp(source)
    except Exception as exc:
        return None, None, PreviewResult(ok=False, message=f"Konvertierung fehlgeschlagen: {exc}")
    return temp, temp, PreviewResult(ok=True)


def _set_temp_wav(path: Path | None) -> None:
    global _temp_wav
    with _temp_lock:
        old = _temp_wav
        _temp_wav = path
    if old is not None and old != path:
        old.unlink(missing_ok=True)


def _cleanup_temp_wav() -> None:
    _set_temp_wav(None)


def _subprocess_stop() -> None:
    global _process
    proc = _process
    _process = None
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            proc.kill()
    _cleanup_temp_wav()


def _subprocess_play(cmd: list[str], *, temp_wav: Path | None) -> PreviewResult:
    global _process
    _subprocess_stop()
    try:
        _process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, FileNotFoundError) as exc:
        if temp_wav is not None:
            temp_wav.unlink(missing_ok=True)
        return PreviewResult(ok=False, message=f"Wiedergabe fehlgeschlagen: {exc}")
    if temp_wav is not None:
        _set_temp_wav(temp_wav)
    return PreviewResult(ok=True)


def _windows_play(path: Path, start_ms: int = 0) -> PreviewResult:
    import winsound

    play_path, temp_wav, prep = prepare_preview_playback_path(path, start_ms)
    if not prep.ok or play_path is None:
        return prep
    try:
        winsound.PlaySound(str(play_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except RuntimeError as exc:
        if temp_wav is not None:
            temp_wav.unlink(missing_ok=True)
        return PreviewResult(ok=False, message=f"Wiedergabe fehlgeschlagen: {exc}")
    if temp_wav is not None:
        _set_temp_wav(temp_wav)
    return PreviewResult(ok=True)


def _windows_stop() -> None:
    import winsound

    winsound.PlaySound(None, winsound.SND_PURGE)
    _cleanup_temp_wav()


def _darwin_play(path: Path, start_ms: int = 0) -> PreviewResult:
    play_path, temp_wav, prep = prepare_preview_playback_path(path, start_ms)
    if not prep.ok or play_path is None:
        return prep
    return _subprocess_play(["afplay", str(play_path)], temp_wav=temp_wav)


def _linux_play(path: Path, start_ms: int = 0) -> PreviewResult:
    play_path, temp_wav, prep = prepare_preview_playback_path(path, start_ms)
    if not prep.ok or play_path is None:
        return prep
    return _subprocess_play(["aplay", "-q", str(play_path)], temp_wav=temp_wav)


def _default_play(path: Path, start_ms: int = 0) -> PreviewResult:
    system = platform.system()
    if system == "Windows":
        return _windows_play(path, start_ms)
    if system == "Darwin":
        return _darwin_play(path, start_ms)
    return _linux_play(path, start_ms)


def _default_stop() -> None:
    system = platform.system()
    if system == "Windows":
        _windows_stop()
    else:
        _subprocess_stop()


def validate_preview_path(path: str | Path) -> PreviewResult:
    """Check whether *path* can be attempted for preview playback."""
    resolved = Path(path)
    if not str(path).strip():
        return PreviewResult(ok=False, message="Kein Sample ausgewählt.")
    if not resolved.is_file():
        return PreviewResult(ok=False, message="Datei nicht gefunden.")
    return PreviewResult(ok=True)


class WorkbenchPreviewPlayer:
    """Play local audio files for workbench preview. Does not modify originals."""

    def __init__(
        self,
        *,
        play_fn: PreviewPlayFn | None = None,
        stop_fn: PreviewStopFn | None = None,
    ) -> None:
        self._play_fn = play_fn or _default_play
        self._stop_fn = stop_fn or _default_stop
        self._lock = threading.Lock()
        self._current_path: Path | None = None
        self._current_start_ms: int = 0

    def play(self, path: str | Path, *, start_ms: int = 0) -> PreviewResult:
        validation = validate_preview_path(path)
        if not validation.ok:
            return validation
        resolved = Path(path).resolve()
        offset = normalize_preview_start_ms(start_ms)
        offset_validation = validate_preview_start_ms(resolved, offset)
        if not offset_validation.ok:
            return offset_validation
        with self._lock:
            self._stop_unlocked()
            result = self._play_fn(resolved, offset)
            if result.ok:
                self._current_path = resolved
                self._current_start_ms = offset
            return result

    def stop(self) -> None:
        with self._lock:
            self._stop_unlocked()

    def _stop_unlocked(self) -> None:
        self._stop_fn()
        self._current_path = None
        self._current_start_ms = 0

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    @property
    def current_start_ms(self) -> int:
        return self._current_start_ms


def preview_toggle_action(
    *,
    is_playing: bool,
    current_path: Path | None,
    requested_path: Path,
) -> str:
    """Return ``stop`` when the same file is already playing, else ``play``."""
    if is_playing and current_path is not None and current_path == requested_path.resolve():
        return "stop"
    return "play"


def preview_platform_note() -> str:
    """Short note on preview playback support for the current platform."""
    system = platform.system()
    if system == "Windows":
        return "Windows: WAV direkt; andere Formate werden temporär konvertiert."
    if system == "Darwin":
        return "macOS: afplay (System-Player)."
    return "Linux: aplay; nicht-WAV wird temporär konvertiert."


__all__ = [
    "PreviewResult",
    "WorkbenchPreviewPlayer",
    "normalize_preview_start_ms",
    "prepare_preview_playback_path",
    "preview_platform_note",
    "preview_toggle_action",
    "validate_preview_path",
    "validate_preview_start_ms",
]
