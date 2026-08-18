from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src import quick_issue_capture as qic


class _FakeWhisper:
    def __init__(self, transcript: str | None) -> None:
        self.transcript = transcript

    def transcribe(self, _wav_path: Path) -> str | None:
        return self.transcript


class _FakeGh:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def create(self, title: str, body: str) -> dict:
        self.calls.append((title, body))
        return {
            "number": 123,
            "html_url": "https://github.com/jannekbuengener/sample-brain/issues/123",
        }


def test_default_recording_dir_is_user_local_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))

    capture = qic.QuickIssueCapture(
        whisper_adapter=_FakeWhisper("hello"),
        gh_adapter=_FakeGh(),
    )

    assert capture.recordings_dir == state_dir / "recordings"


def test_start_recording_delegates_and_process_uses_owned_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[object, int, int]] = []

    def fake_start(engine, engine_frame: int, session_frame: int) -> int:
        calls.append((engine, engine_frame, session_frame))
        return 77

    monkeypatch.setattr(qic, "start_native_recording", fake_start)
    capture = qic.QuickIssueCapture(
        whisper_adapter=_FakeWhisper("Issue body"),
        gh_adapter=_FakeGh(),
        recordings_dir=tmp_path,
    )
    engine = object()

    recording_id = capture.start_recording(engine, 100, 200)
    assert recording_id == 77
    assert calls == [(engine, 100, 200)]

    wav_path = tmp_path / "recording.wav"
    wav_path.write_bytes(b"wav")
    monkeypatch.setattr(capture, "stop_recording", lambda **_kwargs: wav_path)

    result = capture.process_recording(
        engine=engine,
        end_engine_frame=300,
        end_session_frame=400,
    )

    assert result["issue"]["number"] == 123
    assert not wav_path.exists()


def test_gh_issue_adapter_parses_official_url_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://github.com/jannekbuengener/sample-brain/issues/456"

    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=url + "\n", stderr="")

    monkeypatch.setattr(qic.subprocess, "run", fake_run)

    result = qic.GhIssueAdapter().create("Title", "Body")

    assert result == {"number": 456, "html_url": url}


def test_whisper_adapter_uses_documented_cli_contract_and_pcm16_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "whisper-cli.exe"
    model = tmp_path / "ggml-base.bin"
    wav = tmp_path / "recording.wav"
    executable.write_bytes(b"")
    model.write_bytes(b"")
    wav.write_bytes(b"")

    converted: list[tuple[Path, Path]] = []
    command: list[str] = []

    def fake_render(src: Path, dst: Path):
        converted.append((Path(src), Path(dst)))
        Path(dst).write_bytes(b"pcm16")
        return dst

    def fake_run(args, **_kwargs):
        command.extend(args)
        return SimpleNamespace(returncode=0, stdout="Hallo Welt\n", stderr="")

    monkeypatch.setattr(qic, "render_canonical_wav", fake_render, raising=False)
    monkeypatch.setattr(qic.subprocess, "run", fake_run)

    adapter = qic.WhisperCppAdapter(
        executable=executable,
        model_path=model,
        language="auto",
    )
    transcript = adapter.transcribe(wav)

    assert transcript == "Hallo Welt"
    assert converted and converted[0][0] == wav
    assert "--model" in command
    assert "--language" in command
    assert command[command.index("--language") + 1] == "auto"
    assert "--file" in command
    assert "--no-timestamps" in command
    assert "--no-prints" in command


def test_public_issue_body_redacts_secret_and_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(qic, "start_native_recording", lambda *_args: 11)
    gh = _FakeGh()
    capture = qic.QuickIssueCapture(
        whisper_adapter=_FakeWhisper(
            r"Bitte pruefen C:\Users\me\private.wav API_TOKEN=super-secret"
        ),
        gh_adapter=gh,
        recordings_dir=tmp_path,
    )
    engine = object()
    capture.start_recording(engine, 10, 20)
    wav_path = tmp_path / "recording.wav"
    wav_path.write_bytes(b"wav")
    monkeypatch.setattr(capture, "stop_recording", lambda **_kwargs: wav_path)

    result = capture.process_recording(
        engine=engine,
        end_engine_frame=30,
        end_session_frame=40,
    )

    assert result["issue"]["number"] == 123
    assert len(gh.calls) == 1
    _title, body = gh.calls[0]
    assert "C:\\Users" not in body
    assert "super-secret" not in body
    assert "<REDACTED_PATH>" in body
    assert "<REDACTED_SECRET>" in body


def test_transcription_failure_keeps_recording_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(qic, "start_native_recording", lambda *_args: 12)
    capture = qic.QuickIssueCapture(
        whisper_adapter=_FakeWhisper(None),
        gh_adapter=_FakeGh(),
        recordings_dir=tmp_path,
    )
    engine = object()
    capture.start_recording(engine, 10, 20)
    wav_path = tmp_path / "recording.wav"
    wav_path.write_bytes(b"wav")
    monkeypatch.setattr(capture, "stop_recording", lambda **_kwargs: wav_path)

    result = capture.process_recording(
        engine=engine,
        end_engine_frame=30,
        end_session_frame=40,
    )

    assert result["issue"] is None
    assert result["error"]
    assert result["wav_kept"] is True
    assert wav_path.exists()
