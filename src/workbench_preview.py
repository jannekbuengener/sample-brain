"""Workbench audio preview — play selected samples without modifying originals."""
from __future__ import annotations

import platform
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

import soundfile as sf

PreviewPlayFn = Callable[[Path], "PreviewResult"]
PreviewStopFn = Callable[[], None]


@dataclass(frozen=True)
class PreviewResult:
    ok: bool
    message: str = ""


class _PreviewBackend(Protocol):
    def play(self, path: Path) -> PreviewResult: ...

    def stop(self) -> None: ...


_process: subprocess.Popen[bytes] | None = None
_temp_wav: Path | None = None
_temp_lock = threading.Lock()


def _write_pcm_wav_temp(source: Path) -> Path:
    """Decode *source* to a temporary 16-bit PCM WAV (original file unchanged)."""
    data, sr = sf.read(source, dtype="float32", always_2d=False)
    if getattr(data, "size", 0) == 0:
        raise ValueError("empty audio")
    fd, name = tempfile.mkstemp(suffix=".wav", prefix="sb-preview-")
    import os

    os.close(fd)
    temp = Path(name)
    sf.write(temp, data, sr, subtype="PCM_16")
    return temp


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


def _windows_play(path: Path) -> PreviewResult:
    import winsound

    play_path = path
    temp_wav: Path | None = None
    if path.suffix.lower() != ".wav":
        try:
            temp_wav = _write_pcm_wav_temp(path)
            play_path = temp_wav
        except Exception as exc:
            return PreviewResult(ok=False, message=f"Konvertierung fehlgeschlagen: {exc}")
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


def _darwin_play(path: Path) -> PreviewResult:
    return _subprocess_play(["afplay", str(path)], temp_wav=None)


def _linux_play(path: Path) -> PreviewResult:
    play_path = path
    temp_wav: Path | None = None
    if path.suffix.lower() != ".wav":
        try:
            temp_wav = _write_pcm_wav_temp(path)
            play_path = temp_wav
        except Exception as exc:
            return PreviewResult(ok=False, message=f"Konvertierung fehlgeschlagen: {exc}")
    return _subprocess_play(["aplay", "-q", str(play_path)], temp_wav=temp_wav)


def _default_play(path: Path) -> PreviewResult:
    system = platform.system()
    if system == "Windows":
        return _windows_play(path)
    if system == "Darwin":
        return _darwin_play(path)
    return _linux_play(path)


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

    def play(self, path: str | Path) -> PreviewResult:
        validation = validate_preview_path(path)
        if not validation.ok:
            return validation
        resolved = Path(path).resolve()
        with self._lock:
            self._stop_unlocked()
            result = self._play_fn(resolved)
            if result.ok:
                self._current_path = resolved
            return result

    def stop(self) -> None:
        with self._lock:
            self._stop_unlocked()

    def _stop_unlocked(self) -> None:
        self._stop_fn()
        self._current_path = None

    @property
    def current_path(self) -> Path | None:
        return self._current_path


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
    "preview_platform_note",
    "validate_preview_path",
]
