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
LoopSyncPlayFn = Callable[[Path], "PreviewResult"]

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
        return PreviewResult(
            ok=False, message="Dauer unbekannt — Cue-Preview nicht möglich."
        )
    if offset >= duration_ms:
        return PreviewResult(ok=False, message="Cue liegt außerhalb der Datei.")
    return PreviewResult(ok=True)


def validate_preview_region_ms(
    path: Path | str, start_ms: int, end_ms: int
) -> PreviewResult:
    """Validate a bounded preview region ``[start_ms, end_ms)``."""
    start = normalize_preview_start_ms(start_ms)
    end = normalize_preview_start_ms(end_ms)
    start_check = validate_preview_start_ms(path, start)
    if not start_check.ok:
        return start_check
    duration_ms = read_audio_duration_ms(path)
    if duration_ms is None:
        return PreviewResult(
            ok=False, message="Dauer unbekannt — Loop-Preview nicht möglich."
        )
    if end <= start:
        return PreviewResult(ok=False, message="Loop-Ende muss nach Loop-Start liegen.")
    if end > duration_ms:
        return PreviewResult(ok=False, message="Loop-Ende liegt außerhalb der Datei.")
    return PreviewResult(ok=True)


def validate_preview_region_frames(
    path: Path | str,
    start_frame: int,
    end_frame_exclusive: int,
) -> PreviewResult:
    """Validate an exact source-frame preview region ``[start, end)``."""
    if (
        not isinstance(start_frame, int)
        or isinstance(start_frame, bool)
        or not isinstance(end_frame_exclusive, int)
        or isinstance(end_frame_exclusive, bool)
    ):
        return PreviewResult(ok=False, message="Frame-Grenzen müssen Ganzzahlen sein.")
    if start_frame < 0:
        return PreviewResult(ok=False, message="Start-Frame darf nicht negativ sein.")
    if end_frame_exclusive <= start_frame:
        return PreviewResult(
            ok=False, message="End-Frame muss nach Start-Frame liegen."
        )
    try:
        info = sf.info(Path(path))
    except Exception:
        return PreviewResult(
            ok=False, message="Audio-Frames konnten nicht gelesen werden."
        )
    if end_frame_exclusive > int(info.frames):
        return PreviewResult(ok=False, message="End-Frame liegt außerhalb der Datei.")
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


def _write_pcm_wav_temp_from_offset(
    source: Path, start_ms: int, *, end_ms: int | None = None
) -> Path:
    """Decode *source* from *start_ms* (optionally until *end_ms*) into a temp WAV."""
    start_sec = normalize_preview_start_ms(start_ms) / 1000.0
    info = sf.info(source)
    start_frame = int(start_sec * info.samplerate)
    stop_frame: int | None = None
    if end_ms is not None:
        end_sec = normalize_preview_start_ms(end_ms) / 1000.0
        stop_frame = int(end_sec * info.samplerate)
    data, sr = sf.read(
        source,
        dtype="float32",
        always_2d=False,
        start=start_frame,
        stop=stop_frame,
    )
    if getattr(data, "size", 0) == 0:
        raise ValueError("empty audio after region slice")
    fd, name = tempfile.mkstemp(suffix=".wav", prefix=_PREVIEW_TEMP_PREFIX)
    os.close(fd)
    temp = Path(name)
    sf.write(temp, data, sr, subtype="PCM_16")
    return temp


def _write_pcm_wav_temp_from_frames(
    source: Path,
    start_frame: int,
    end_frame_exclusive: int,
) -> Path:
    """Decode exactly ``source[start_frame:end_frame_exclusive]`` to a temp WAV."""
    data, sr = sf.read(
        source,
        dtype="float32",
        always_2d=False,
        start=start_frame,
        stop=end_frame_exclusive,
    )
    if getattr(data, "size", 0) == 0:
        raise ValueError("empty audio after frame-region slice")
    fd, name = tempfile.mkstemp(suffix=".wav", prefix=_PREVIEW_TEMP_PREFIX)
    os.close(fd)
    temp = Path(name)
    sf.write(temp, data, sr, subtype="PCM_16")
    return temp


def prepare_preview_playback_path(
    source: Path,
    start_ms: int = 0,
    *,
    end_ms: int | None = None,
) -> tuple[Path | None, Path | None, PreviewResult]:
    """Return playback path, optional temp path, and status."""
    offset = normalize_preview_start_ms(start_ms)
    if end_ms is not None:
        region_check = validate_preview_region_ms(source, offset, end_ms)
        if not region_check.ok:
            return None, None, region_check
        try:
            temp = _write_pcm_wav_temp_from_offset(source, offset, end_ms=end_ms)
        except Exception as exc:
            return (
                None,
                None,
                PreviewResult(ok=False, message=f"Loop-Preview fehlgeschlagen: {exc}"),
            )
        return temp, temp, PreviewResult(ok=True)

    offset_check = validate_preview_start_ms(source, offset)
    if not offset_check.ok:
        return None, None, offset_check

    if offset > 0:
        try:
            temp = _write_pcm_wav_temp_from_offset(source, offset)
        except Exception as exc:
            return (
                None,
                None,
                PreviewResult(
                    ok=False, message=f"Preview-Vorbereitung fehlgeschlagen: {exc}"
                ),
            )
        return temp, temp, PreviewResult(ok=True)

    if source.suffix.lower() == ".wav":
        return source, None, PreviewResult(ok=True)

    try:
        temp = _write_pcm_wav_temp(source)
    except Exception as exc:
        return (
            None,
            None,
            PreviewResult(ok=False, message=f"Konvertierung fehlgeschlagen: {exc}"),
        )
    return temp, temp, PreviewResult(ok=True)


def prepare_preview_playback_frame_region(
    source: Path,
    start_frame: int,
    end_frame_exclusive: int,
) -> tuple[Path | None, Path | None, PreviewResult]:
    """Create a temporary preview from exact source-frame bounds."""
    validation = validate_preview_region_frames(
        source,
        start_frame,
        end_frame_exclusive,
    )
    if not validation.ok:
        return None, None, validation
    try:
        temp = _write_pcm_wav_temp_from_frames(
            source,
            start_frame,
            end_frame_exclusive,
        )
    except Exception as exc:
        return (
            None,
            None,
            PreviewResult(ok=False, message=f"Region-Preview fehlgeschlagen: {exc}"),
        )
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
    # A successful direct-WAV replacement must also retire a prior prepared
    # temporary preview.  Keep it on a failed dispatch: the prior preview may
    # still be the truthful active state.
    _set_temp_wav(temp_wav)
    return PreviewResult(ok=True)


def _windows_stop() -> None:
    import winsound

    # ``None`` stops the active waveform sound. ``SND_PURGE`` is unsupported
    # on modern Windows and adds avoidable transition jitter.
    winsound.PlaySound(None, 0)
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


def _windows_play_sync(path: Path) -> PreviewResult:
    import winsound

    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME)
    except RuntimeError as exc:
        return PreviewResult(ok=False, message=f"Wiedergabe fehlgeschlagen: {exc}")
    return PreviewResult(ok=True)


def _subprocess_play_sync(cmd: list[str]) -> PreviewResult:
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        return PreviewResult(ok=False, message=f"Wiedergabe fehlgeschlagen: {exc}")
    return PreviewResult(ok=True)


def _default_sync_play(path: Path) -> PreviewResult:
    system = platform.system()
    if system == "Windows":
        return _windows_play_sync(path)
    if system == "Darwin":
        return _subprocess_play_sync(["afplay", str(path)])
    return _subprocess_play_sync(["aplay", "-q", str(path)])


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
        loop_sync_play_fn: LoopSyncPlayFn | None = None,
    ) -> None:
        self._play_fn = play_fn or _default_play
        self._stop_fn = stop_fn or _default_stop
        self._loop_sync_play_fn = loop_sync_play_fn or _default_sync_play
        self._lock = threading.Lock()
        self._current_path: Path | None = None
        self._current_start_ms: int = 0
        self._loop_stop_event = threading.Event()
        self._loop_thread: threading.Thread | None = None
        self._loop_temp_path: Path | None = None

    def _finalize_stop_side_effects(
        self,
        loop_thread: threading.Thread | None,
        loop_temp: Path | None,
    ) -> None:
        if loop_thread is not None:
            loop_thread.join(timeout=2.0)
        if loop_temp is not None:
            loop_temp.unlink(missing_ok=True)

    def _begin_stop_unlocked(self) -> tuple[threading.Thread | None, Path | None]:
        self._loop_stop_event.set()
        loop_thread = self._loop_thread
        loop_temp = self._loop_temp_path
        self._loop_thread = None
        self._loop_temp_path = None
        self._stop_fn()
        self._current_path = None
        self._current_start_ms = 0
        return loop_thread, loop_temp

    def _stop_active_loop_for_replacement(
        self,
    ) -> tuple[threading.Thread | None, Path | None]:
        """Stop a repeating preview before a normal replacement dispatch."""
        with self._lock:
            if self._loop_thread is None:
                return None, None
            return self._begin_stop_unlocked()

    def play(self, path: str | Path, *, start_ms: int = 0) -> PreviewResult:
        validation = validate_preview_path(path)
        if not validation.ok:
            return validation
        resolved = Path(path).resolve()
        offset = normalize_preview_start_ms(start_ms)
        offset_validation = validate_preview_start_ms(resolved, offset)
        if not offset_validation.ok:
            return offset_validation
        loop_thread, loop_temp = self._stop_active_loop_for_replacement()
        self._finalize_stop_side_effects(loop_thread, loop_temp)
        with self._lock:
            result = self._play_fn(resolved, offset)
            if result.ok:
                self._current_path = resolved
                self._current_start_ms = offset
            return result

    def play_region(
        self,
        path: str | Path,
        *,
        start_ms: int,
        end_ms: int,
    ) -> PreviewResult:
        """Play a bounded region once via temporary slice; original file unchanged."""
        validation = validate_preview_path(path)
        if not validation.ok:
            return validation
        resolved = Path(path).resolve()
        region_validation = validate_preview_region_ms(resolved, start_ms, end_ms)
        if not region_validation.ok:
            return region_validation
        play_path, temp_path, prep = prepare_preview_playback_path(
            resolved,
            normalize_preview_start_ms(start_ms),
            end_ms=normalize_preview_start_ms(end_ms),
        )
        if not prep.ok or play_path is None:
            return prep
        loop_thread, loop_temp = self._stop_active_loop_for_replacement()
        self._finalize_stop_side_effects(loop_thread, loop_temp)
        with self._lock:
            result = self._play_fn(play_path, 0)
            if result.ok:
                self._current_path = resolved
                self._current_start_ms = normalize_preview_start_ms(start_ms)
            elif temp_path is not None:
                temp_path.unlink(missing_ok=True)
            return result

    def play_frame_region(
        self,
        path: str | Path,
        *,
        start_frame: int,
        end_frame_exclusive: int,
    ) -> PreviewResult:
        """Play one exact source-frame region; original file remains unchanged."""
        validation = validate_preview_path(path)
        if not validation.ok:
            return validation
        resolved = Path(path).resolve()
        play_path, temp_path, prep = prepare_preview_playback_frame_region(
            resolved,
            start_frame,
            end_frame_exclusive,
        )
        if not prep.ok or play_path is None:
            return prep
        loop_thread, loop_temp = self._stop_active_loop_for_replacement()
        self._finalize_stop_side_effects(loop_thread, loop_temp)
        with self._lock:
            result = self._play_fn(play_path, 0)
            if result.ok:
                self._current_path = resolved
                self._current_start_ms = 0
            elif temp_path is not None:
                temp_path.unlink(missing_ok=True)
            return result

    def play_region_loop(
        self,
        path: str | Path,
        *,
        start_ms: int,
        end_ms: int,
    ) -> PreviewResult:
        """Repeat a bounded loop region until ``stop()``; original file unchanged."""
        validation = validate_preview_path(path)
        if not validation.ok:
            return validation
        resolved = Path(path).resolve()
        region_validation = validate_preview_region_ms(resolved, start_ms, end_ms)
        if not region_validation.ok:
            return region_validation
        play_path, temp_path, prep = prepare_preview_playback_path(
            resolved,
            normalize_preview_start_ms(start_ms),
            end_ms=normalize_preview_start_ms(end_ms),
        )
        if not prep.ok or play_path is None:
            return prep
        with self._lock:
            loop_thread, loop_temp = self._begin_stop_unlocked()
        self._finalize_stop_side_effects(loop_thread, loop_temp)
        self._loop_stop_event.clear()
        with self._lock:
            self._loop_temp_path = temp_path
            self._current_path = resolved
            self._current_start_ms = normalize_preview_start_ms(start_ms)
            self._loop_thread = threading.Thread(
                target=self._loop_region_worker,
                args=(play_path,),
                daemon=True,
                name="workbench-loop-repeat",
            )
            self._loop_thread.start()
        return PreviewResult(ok=True)

    def play_frame_region_loop(
        self,
        path: str | Path,
        *,
        start_frame: int,
        end_frame_exclusive: int,
    ) -> PreviewResult:
        """Repeat an exact source-frame region until ``stop()``."""
        validation = validate_preview_path(path)
        if not validation.ok:
            return validation
        resolved = Path(path).resolve()
        play_path, temp_path, prep = prepare_preview_playback_frame_region(
            resolved,
            start_frame,
            end_frame_exclusive,
        )
        if not prep.ok or play_path is None:
            return prep
        with self._lock:
            loop_thread, loop_temp = self._begin_stop_unlocked()
        self._finalize_stop_side_effects(loop_thread, loop_temp)
        self._loop_stop_event.clear()
        with self._lock:
            self._loop_temp_path = temp_path
            self._current_path = resolved
            self._current_start_ms = 0
            self._loop_thread = threading.Thread(
                target=self._loop_region_worker,
                args=(play_path,),
                daemon=True,
                name="workbench-frame-region-repeat",
            )
            self._loop_thread.start()
        return PreviewResult(ok=True)

    def _loop_region_worker(self, play_path: Path) -> None:
        while not self._loop_stop_event.is_set():
            result = self._loop_sync_play_fn(play_path)
            if not result.ok:
                break
        loop_temp: Path | None = None
        with self._lock:
            if self._loop_thread is threading.current_thread():
                self._loop_thread = None
            loop_temp = self._loop_temp_path
            self._loop_temp_path = None
            self._current_path = None
            self._current_start_ms = 0
        if loop_temp is not None:
            loop_temp.unlink(missing_ok=True)

    def stop(self) -> None:
        with self._lock:
            loop_thread, loop_temp = self._begin_stop_unlocked()
        self._finalize_stop_side_effects(loop_thread, loop_temp)

    @property
    def is_loop_repeating(self) -> bool:
        thread = self._loop_thread
        return thread is not None and thread.is_alive()

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
    if (
        is_playing
        and current_path is not None
        and current_path == requested_path.resolve()
    ):
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
    "prepare_preview_playback_frame_region",
    "prepare_preview_playback_path",
    "preview_platform_note",
    "preview_toggle_action",
    "validate_preview_path",
    "validate_preview_region_frames",
    "validate_preview_region_ms",
    "validate_preview_start_ms",
]
