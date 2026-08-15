from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.audio_fixtures import write_sine_wav


def test_context_analyze_cli_prints_deterministic_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from src.cli import main

    source = write_sine_wav(
        tmp_path / "path with spaces.wav", duration_sec=2.0, frequency_hz=440.0
    )
    monkeypatch.setattr(
        sys, "argv", ["sample-brain", "context", "analyze", str(source), "--json"]
    )

    main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["source"]["original"]["file_name"] == "path with spaces.wav"
    assert payload["analysis"]["status"] in {"ok", "partial"}


def test_context_analyze_cli_returns_json_error_and_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from src.cli import main

    monkeypatch.setattr(
        sys,
        "argv",
        ["sample-brain", "context", "analyze", str(tmp_path / "missing.wav"), "--json"],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2
    payload = json.loads(capsys.readouterr().err)
    assert payload == {
        "error": {"code": "FILE_NOT_FOUND", "message": "Audio file does not exist."},
        "status": "error",
    }


def test_context_analyze_help_is_available(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from src.cli import main

    monkeypatch.setattr(sys, "argv", ["sample-brain", "context", "analyze", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    assert "--json" in capsys.readouterr().out


def test_context_analyze_cli_uses_track_cache_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from src.cli import main

    source = write_sine_wav(
        tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0
    )
    cache_dir = tmp_path / "cache"
    argv = [
        "sample-brain",
        "context",
        "analyze",
        str(source),
        "--json",
        "--track-cache-dir",
        str(cache_dir),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    main()
    # first run writes exactly one cache entry (miss)
    assert len(list(cache_dir.glob("*.json"))) == 1
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", argv)
    main()
    # second identical run hits the cache; no new entry written
    assert len(list(cache_dir.glob("*.json"))) == 1


def test_context_analyze_cli_no_track_cache_disables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from src.cli import main

    source = write_sine_wav(
        tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0
    )
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sample-brain",
            "context",
            "analyze",
            str(source),
            "--json",
            "--no-track-cache",
            "--track-cache-dir",
            str(cache_dir),
        ],
    )
    main()
    # disabled cache writes nothing
    assert len(list(cache_dir.glob("*.json"))) == 0


def test_context_analyze_cli_stdout_valid_json_no_private_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from src.cli import main

    source = write_sine_wav(
        tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0
    )
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sample-brain",
            "context",
            "analyze",
            str(source),
            "--json",
            "--track-cache-dir",
            str(cache_dir),
        ],
    )
    main()
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["document_type"] == "sample_brain.track_map"
    assert str(tmp_path) not in out
    assert str(cache_dir) not in out
