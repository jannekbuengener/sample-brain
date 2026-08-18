"""One-click Voice-to-Issue Quick Capture for the Sample-Brain Workbench.

Quick Capture reuses the existing native recording path, transcribes locally with
an explicitly configured whisper.cpp CLI, then creates a Sample-Brain GitHub
issue with ``gh issue create``. Recordings stay in user-local Workbench state and
are retained when transcription or issue creation fails so they can be retried.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

import librosa
import soundfile as sf

from .jules_dispatch import redact
from .workbench_controller import (
    start_native_recording,
    stop_native_recording,
    workbench_state_dir,
)

WHISPER_EXE_ENV = "SAMPLE_BRAIN_WHISPER_CPP"
WHISPER_MODEL_ENV = "SAMPLE_BRAIN_WHISPER_MODEL"
WHISPER_LANGUAGE_ENV = "SAMPLE_BRAIN_WHISPER_LANGUAGE"
DEFAULT_WHISPER_LANGUAGE = "auto"
DEFAULT_REPO = "jannekbuengener/sample-brain"
WHISPER_SAMPLE_RATE = 16000


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def _render_whisper_wav(src_path: Path, dst_path: Path) -> Path:
    """Render whisper.cpp's documented 16 kHz mono PCM16 WAV input."""
    audio, _sr = librosa.load(
        str(src_path),
        sr=WHISPER_SAMPLE_RATE,
        mono=True,
    )
    if audio is None or len(audio) == 0:
        raise ValueError("empty audio")
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(
        dst_path,
        audio,
        WHISPER_SAMPLE_RATE,
        format="WAV",
        subtype="PCM_16",
    )
    return dst_path


# Compatibility/injection seam used by focused tests; unlike Sample Brain's normal
# 44.1-kHz canonical renderer, this renderer follows whisper.cpp's 16-kHz contract.
render_canonical_wav = _render_whisper_wav


class WhisperCppAdapter:
    """Thin local adapter around the official whisper.cpp CLI."""

    def __init__(
        self,
        *,
        executable: Optional[Path],
        model_path: Optional[Path],
        language: str = DEFAULT_WHISPER_LANGUAGE,
    ) -> None:
        self.executable = Path(executable) if executable is not None else None
        self.model_path = Path(model_path) if model_path is not None else None
        self.language = (
            (language or DEFAULT_WHISPER_LANGUAGE).strip()
            or DEFAULT_WHISPER_LANGUAGE
        )

    @classmethod
    def from_environment(cls) -> "WhisperCppAdapter":
        return cls(
            executable=_env_path(WHISPER_EXE_ENV),
            model_path=_env_path(WHISPER_MODEL_ENV),
            language=os.environ.get(
                WHISPER_LANGUAGE_ENV, DEFAULT_WHISPER_LANGUAGE
            ).strip()
            or DEFAULT_WHISPER_LANGUAGE,
        )

    def configured(self) -> bool:
        return bool(
            self.executable
            and self.model_path
            and self.executable.is_file()
            and self.model_path.is_file()
        )

    def transcribe(self, wav_path: Path) -> Optional[str]:
        """Return transcript text, ``""`` for no speech, or ``None`` on failure."""
        if not self.configured():
            return None

        source = Path(wav_path)
        prepared = source.with_name(f".{source.stem}.whisper.wav")
        try:
            render_canonical_wav(source, prepared)
            result = subprocess.run(
                [
                    str(self.executable),
                    "--model",
                    str(self.model_path),
                    "--language",
                    self.language,
                    "--no-timestamps",
                    "--no-prints",
                    "--file",
                    str(prepared),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception:  # noqa: BLE001 - external/local UI boundary
            return None
        finally:
            try:
                prepared.unlink(missing_ok=True)
            except Exception:
                pass

        if result.returncode != 0:
            return None
        return result.stdout.strip()


class GhIssueAdapter:
    """Minimal wrapper around the documented ``gh issue create`` command."""

    def __init__(self, repo: str = DEFAULT_REPO) -> None:
        self.repo = repo

    def create(self, title: str, body: str) -> Optional[dict]:
        try:
            result = subprocess.run(
                [
                    "gh",
                    "issue",
                    "create",
                    "--repo",
                    self.repo,
                    "--title",
                    title,
                    "--body",
                    body,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception:  # noqa: BLE001 - external CLI boundary
            return None

        if result.returncode != 0:
            return None

        stdout = result.stdout.strip()
        url_match = re.search(r"(https?://[^\s]+/issues/(\d+))\b", stdout)
        if url_match:
            return {
                "number": int(url_match.group(2)),
                "html_url": url_match.group(1),
            }

        number_match = re.search(r"#(\d+)", stdout)
        if number_match:
            number = int(number_match.group(1))
            return {
                "number": number,
                "html_url": f"https://github.com/{self.repo}/issues/{number}",
            }

        try:
            data = json.loads(stdout)
        except Exception:
            return None
        number = data.get("number") or data.get("id")
        url = data.get("html_url") or data.get("url")
        if not number:
            return None
        return {
            "number": int(number),
            "html_url": str(
                url or f"https://github.com/{self.repo}/issues/{number}"
            ),
        }


def _extract_title(transcript: str, max_chars: int = 80) -> str:
    """Create a compact issue title from the first meaningful sentence."""
    if not transcript:
        return ""
    text = " ".join(transcript.split())
    title = text
    for sep in (".", "!", "?"):
        idx = text.find(sep)
        if idx != -1:
            title = text[: idx + 1].strip()
            break
    if len(title) > max_chars:
        shortened = title[:max_chars].rsplit(" ", 1)[0].strip()
        title = (shortened or title[: max_chars - 1]).rstrip() + "…"
    return title


class QuickIssueCapture:
    """Own one complete native-recording -> transcript -> GitHub issue cycle."""

    def __init__(
        self,
        *,
        whisper_adapter: Optional[WhisperCppAdapter] = None,
        gh_adapter: Optional[GhIssueAdapter] = None,
        recordings_dir: Optional[Path] = None,
    ) -> None:
        self.whisper = whisper_adapter or WhisperCppAdapter.from_environment()
        self.gh = gh_adapter or GhIssueAdapter()
        self.recordings_dir = (
            Path(recordings_dir)
            if recordings_dir is not None
            else workbench_state_dir() / "recordings"
        )
        self._recording_id: int | None = None
        self._record_start_engine_frame = 0
        self._record_start_session_frame = 0
        self._last_result: dict | None = None

    def start_recording(
        self,
        engine,
        engine_frame: int,
        session_frame: int,
    ) -> int:
        """Start a real native recording and retain its authoritative frame state."""
        if self._recording_id is not None:
            raise RuntimeError("Quick Capture recording already active")
        recording_id = start_native_recording(engine, engine_frame, session_frame)
        self._recording_id = int(recording_id)
        self._record_start_engine_frame = int(engine_frame)
        self._record_start_session_frame = int(session_frame)
        return self._recording_id

    def stop_recording(
        self,
        engine,
        recording_id: int,
        start_engine_frame: int,
        start_session_frame: int,
        end_engine_frame: int,
        end_session_frame: int,
    ) -> Optional[Path]:
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        dest_path = self.recordings_dir / f"quick_capture_{timestamp}_{unique_id}.wav"

        try:
            take = stop_native_recording(
                engine=engine,
                recording_id=recording_id,
                engine_frame=start_engine_frame,
                session_frame=start_session_frame,
                end_engine_frame=end_engine_frame,
                end_session_frame=end_session_frame,
                destination=str(dest_path),
            )
        except RuntimeError:
            return None
        return dest_path if take is not None else None

    def _finish(self, result: dict) -> dict:
        self._last_result = result
        return result

    def process_recording(
        self,
        *,
        engine,
        end_engine_frame: int,
        end_session_frame: int,
    ) -> dict:
        """Stop the owned recording, transcribe locally, and create the issue."""
        if self._recording_id is None:
            return self._finish(
                {
                    "transcript": "",
                    "title": "",
                    "issue": None,
                    "error": "Keine Quick-Capture-Aufnahme aktiv.",
                    "wav_kept": False,
                }
            )

        recording_id = self._recording_id
        start_engine_frame = self._record_start_engine_frame
        start_session_frame = self._record_start_session_frame
        self._recording_id = None

        wav_path = self.stop_recording(
            engine=engine,
            recording_id=recording_id,
            start_engine_frame=start_engine_frame,
            start_session_frame=start_session_frame,
            end_engine_frame=int(end_engine_frame),
            end_session_frame=int(end_session_frame),
        )
        if wav_path is None:
            return self._finish(
                {
                    "transcript": "",
                    "title": "",
                    "issue": None,
                    "error": "Aufnahme konnte nicht finalisiert werden.",
                    "wav_kept": False,
                }
            )

        transcript = self.whisper.transcribe(wav_path)
        if transcript is None:
            return self._finish(
                {
                    "transcript": "",
                    "title": "",
                    "issue": None,
                    "error": (
                        "Transkription fehlgeschlagen oder whisper.cpp ist nicht "
                        "konfiguriert. Die Aufnahme bleibt für einen erneuten Versuch erhalten."
                    ),
                    "wav_kept": True,
                }
            )

        if not transcript.strip():
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass
            return self._finish(
                {
                    "transcript": "",
                    "title": "",
                    "issue": None,
                    "error": "Keine Sprache erkannt; Issue wurde nicht erstellt.",
                    "wav_kept": False,
                }
            )

        public_transcript = redact(transcript)
        title = _extract_title(public_transcript, max_chars=80)
        issue_info = self.gh.create(title=title, body=public_transcript)

        if issue_info is None:
            return self._finish(
                {
                    "transcript": public_transcript,
                    "title": title,
                    "issue": None,
                    "error": (
                        "GitHub-Issue konnte nicht erstellt werden. Die Aufnahme "
                        "bleibt für einen erneuten Versuch erhalten."
                    ),
                    "wav_kept": True,
                }
            )

        try:
            wav_path.unlink(missing_ok=True)
        except Exception:
            pass
        return self._finish(
            {
                "transcript": public_transcript,
                "title": title,
                "issue": issue_info,
                "error": None,
                "wav_kept": False,
            }
        )

    def last_result(self) -> Optional[dict]:
        return self._last_result


def trim_to_first_sentence(transcript: str) -> str:
    """Return the first whitespace-normalized sentence from *transcript*."""
    if not transcript:
        return ""
    text = " ".join(transcript.split())
    for sep in (".", "!", "?"):
        idx = text.find(sep)
        if idx != -1:
            return text[: idx + 1].strip()
    return text


__all__ = [
    "DEFAULT_WHISPER_LANGUAGE",
    "GhIssueAdapter",
    "QuickIssueCapture",
    "WHISPER_EXE_ENV",
    "WHISPER_LANGUAGE_ENV",
    "WHISPER_MODEL_ENV",
    "WhisperCppAdapter",
    "trim_to_first_sentence",
]
