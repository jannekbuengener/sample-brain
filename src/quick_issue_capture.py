"""One-click Voice-to-Issue Quick Capture for the Sample-Brain Workbench.

This module orchestrates the quick capture workflow:
  1. Start/stop native recording via existing workbench recording path
  2. Transcribe the recorded WAV using an external whisper.cpp executable
  3. Create a GitHub issue via `gh issue create`
  4. Display the issue number/URL and handle cleanup

All external dependencies (whisper.cpp, gh CLI) are configured via
paths and are optional ÔÇö the app starts normally even if they are
missing; quick capture simply reports appropriate status messages.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from .workbench_controller import start_native_recording, stop_native_recording


# ---------------------------------------------------------------------------
# Transcription adapter ÔÇö external whisper.cpp
# ---------------------------------------------------------------------------


class WhisperCppAdapter:
    """Thin adapter around an external ``whisper.cpp`` executable.

    The executable and model path are configurable. If either is missing
    or the command fails, ``transcribe()`` returns ``None`` so that the
    calling code can gracefully fall back (no issue created, status
    reported, retry possible).
    """

    def __init__(self, *, executable: Optional[Path], model_path: Optional[Path]) -> None:
        self.executable = executable
        self.model_path = model_path

    def transcribe(self, wav_path: Path) -> Optional[str]:
        """Return the full transcript for *wav_path*, or ``None`` on error.

        The transcript is the raw output of ``whisper.cpp``; callers may
        slice it for a title later.
        """
        if not self.executable or not self.model_path:
            return None

        exe = str(self.executable)
        mdl = str(self.model_path)
        wav = str(wav_path)

        try:
            result = subprocess.run(
                [exe, "--model", mdl, "--language", "en", wav],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception:  # noqa: BLE001
            return None

        if result.returncode != 0:
            return None

        transcript = result.stdout.strip()
        if not transcript:
            return None

        return transcript


# ---------------------------------------------------------------------------
# GitHub issue adapter ÔÇö thin ``gh`` CLI wrapper
# ---------------------------------------------------------------------------


class GhIssueAdapter:
    """Thin wrapper around ``gh issue create``.

    Only the essential flags are supported; no general GitHub client is
    required. If ``gh`` is not installed or not authenticated, ``create()``
    returns ``None`` so the UI can show a friendly status without crashing.
    """

    def __init__(self, repo: str = "jannekbuengener/sample-brain") -> None:
        self.repo = repo

    def create(self, title: str, body: str) -> Optional[dict]:
        """Run ``gh issue create`` and return ``{"number": N, "html_url": URL}``.

        Returns ``None`` when ``gh`` is missing, not authenticated, or the
        command fails ÔÇö the caller must not crash.
        """
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
        except Exception:  # noqa: BLE001
            return None

        if result.returncode != 0:
            # gh may print a helpful message to stderr; we swallow it.
            return None

        # Parse gh output: "Created issue #N"
        stdout = result.stdout.strip()
        # Heuristic: look for "#N" in output
        import re
        m = re.search(r"#(\d+)", stdout)
        if not m:
            # Some gh versions output JSON; try to parse it
            try:
                import json as _json
                data = _json.loads(stdout)
                number = data.get("number") or data.get("id")
                url = data.get("html_url")
                if number:
                    return {"number": int(number), "html_url": url or ""}
            except Exception:
                pass
            return None

        number = int(m.group(1))
        # Construct html_url if not in output
        url = f"https://github.com/{self.repo}/issues/{number}"
        # Also try to extract from output
        url_match = re.search(r"https?://[^\s]+", stdout)
        if url_match:
            url = url_match.group(0)

        return {"number": number, "html_url": url}


# ---------------------------------------------------------------------------
# Title extraction from transcript
# ---------------------------------------------------------------------------


def _extract_title(transcript: str, max_chars: int = 80) -> str:
    """Create a short title from the first meaningful sentence.

    - Whitespace is normalised.
    - The first sentence (up to the first period, exclamation or question
      mark) is taken.
    - The result is trimmed to *max_chars* characters.
    - If no sentence boundary is found, the transcript is trimmed directly.
    """
    if not transcript:
        return ""

    # Normalise whitespace
    text = " ".join(transcript.split())

    # Find first sentence boundary
    for sep in (".", "!", "?"):
        idx = text.find(sep)
        if idx != -1:
            title = text[: idx + 1].strip()
            break
    else:
        title = text

    # Trim to max_chars
    if len(title) > max_chars:
        title = title[:max_chars].rsplit(" ", 1)[0] + "ÔÇª"

    return title


# ---------------------------------------------------------------------------
# Core quickÔÇæcapture orchestration
# ---------------------------------------------------------------------------


class QuickIssueCapture:
    """Orchestrate one complete quickÔÇæcapture cycle.

    Workflow:
      1. Ensure native recording engine is running (reuses existing
         workbench recording path).
      2. User clicks Stop ÔåÆ WAV is finalised via the native path.
      3. Transcribe the WAV via whisper.cpp adapter.
      4. If transcript is empty ÔåÆ no issue, return.
      5. Extract title from first sentence.
      6. Build issue body = full transcript.
      7. Create GitHub issue via gh CLI adapter.
      8. On success: show number/URL, delete temp WAV.
         On error: keep temp WAV for retry, show status.

    The recording steps (start/stop) are delegated to the existing
    workbench recording infrastructure; this class only owns the
    postÔÇærecording processing pipeline.
    """

    def __init__(
        self,
        *,
        whisper_adapter: Optional[WhisperCppAdapter] = None,
        gh_adapter: Optional[GhIssueAdapter] = None,
        recordings_dir: Optional[Path] = None,
    ) -> None:
        self.whisper = whisper_adapter or WhisperCppAdapter(
            executable=None, model_path=None
        )
        self.gh = gh_adapter or GhIssueAdapter()
        self.recordings_dir = recordings_dir or Path.cwd() / "recordings"
        self._temp_wav: Optional[Path] = None

    # ------------------------------------------------------------------
    # Recording lifecycle ÔÇö delegates to workbench native path
    # ------------------------------------------------------------------

    def start_recording(self) -> None:
        """Initiate a new native recording session.

        In the workbench context this starts the native recording via
        the existing workbench recording path (``start_native_recording``).
        The recording ID and frames are stored for later finalisation.
        """
        # No-op at this layer ÔÇö the UI controller handles engine startup.
        # This method exists so the UI can call it and conceptually
        # pair with a later ``stop_recording()``.
        pass

    def stop_recording(
        self,
        engine,
        recording_id: int,
        start_engine_frame: int,
        start_session_frame: int,
        end_engine_frame: int,
        end_session_frame: int,
    ) -> Optional[Path]:
        """Stop the native recording and finalise the WAV.

        Delegates to the workbench native recording path
        ``stop_native_recording`` / ``finalize_native_recording``.

        Returns the path to the finalised WAV, or ``None`` if recording
        was not in progress or the finalisation failed.
        """
        destination = self.recordings_dir / f"quick_capture_"
        destination.mkdir(parents=True, exist_ok=True)
        import time, uuid
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        dest_path = str(
            destination / f"recording_{timestamp}_{unique_id}.wav"
        )

        try:
            take = stop_native_recording(
                engine=engine,
                recording_id=recording_id,
                engine_frame=start_engine_frame,
                session_frame=start_session_frame,
                end_engine_frame=end_engine_frame,
                end_session_frame=end_session_frame,
                destination=dest_path,
            )
        except RuntimeError:
            take = None

        if take is not None:
            # finalize_native_recording returns a Take-like object;
            # the WAV is at take.context.record_path or we use dest_path
            return Path(dest_path)
        return None

    # ------------------------------------------------------------------
    # PostÔÇærecording pipeline
    # ------------------------------------------------------------------

    def process_recording(
        self,
        engine,
        recording_id: int,
        start_engine_frame: int,
        start_session_frame: int,
        end_engine_frame: int,
        end_session_frame: int,
    ) -> dict:
        """Run the full postÔÇærecording pipeline.

        Delegates the stop to the native recording path;
        all other steps (transcribe, title, gh issue) remain the same.

        Returns a dict with status information for the UI:
          - ``"transcript"``: full transcript text (or ``""``)
          - ``"title"``: extracted title
          - ``"issue"``: ``{"number": N, "html_url": URL}`` or ``None``
          - ``"error"``: humanÔÇæreadable error string (or ``None``)
          - ``"wav_kept"``: ``True`` if temp WAV should be retained
            (``True`` = error path, ``False`` = success cleanup)

        The method is intentionally pure (no side effects other than
        creating/deleting the temp WAV) so it can be called from UI
        callbacks without hidden state.
        """
        error: Optional[str] = None
        wav_kept = False

        # Step 1: stop native recording & finalise WAV
        wav_path = self.stop_recording(
            engine=engine,
            recording_id=recording_id,
            start_engine_frame=start_engine_frame,
            start_session_frame=start_session_frame,
            end_engine_frame=end_engine_frame,
            end_session_frame=end_session_frame,
        )
        if wav_path is None:
            return {
                "transcript": "",
                "title": "",
                "issue": None,
                "error": "Keine Aufnahme gefunden ÔÇö bitte Quick Capture starten und stoppen.",
                "wav_kept": False,
            }

        # Step 2: transcribe
        transcript = self.whisper.transcribe(Path(wav_path)) or ""
        if not transcript.strip():
            # Empty transcript ÔåÆ no issue, clean up, report status
            try:
                Path(wav_path).unlink(missing_ok=True)
            except Exception:
                pass
            return {
                "transcript": transcript,
                "title": "",
                "issue": None,
                "error": "Transkript ist leer ÔÇö Issue wurde nicht erstellt.",
                "wav_kept": False,
            }

        # Step 3: extract title
        title = _extract_title(transcript, max_chars=80)

        # Step 4: create GitHub issue
        issue_info = self.gh.create(title=title, body=transcript)

        if issue_info is None:
            # gh failed or not available ÔÇö keep WAV for retry, report status
            wav_kept = True
            error = (
                "GitHub-Issue konnte nicht erstellt werden "
                "(gh CLI nicht verf├╝gbar oder nicht authententisiert). "
                "Die tempor├ñre Aufnahme bleibt erhalten zum erneuten Versuch."
            )
        else:
            # Success ÔÇö delete temp WAV
            try:
                Path(wav_path).unlink(missing_ok=True)
            except Exception:
                pass

        return {
            "transcript": transcript,
            "title": title,
            "issue": issue_info,  # type: ignore[return-value]
            "error": error,
            "wav_kept": wav_kept,
        }

    # ------------------------------------------------------------------
    # Public state for UI
    # ------------------------------------------------------------------

    def last_result(self) -> Optional[dict]:
        """Return the most recent ``process_recording()`` result dict.

        Convenience property for the UI to query after a capture cycle.
        """
        # We store the last result as an attribute set by the UI caller.
        # The UI can also call process_recording() directly if it prefers.
        return getattr(self, "_last_result", None)


# ---------------------------------------------------------------------------
# Helper ÔÇö trim transcript to first sentence (shared by _extract_title)
# ---------------------------------------------------------------------------


def trim_to_first_sentence(transcript: str) -> str:
    """Return the first sentence of *transcript*, whitespaceÔÇænormalised.

    Used by the UI status display when a full transcript isn't needed.
    """
    if not transcript:
        return ""
    text = " ".join(transcript.split())
    for sep in (".", "!", "?"):
        idx = text.find(sep)
        if idx != -1:
            return text[: idx + 1].strip()
    return text
