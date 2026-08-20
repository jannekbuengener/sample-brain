from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from src.content_hash import compute_file_hash


def _write_stereo_wav(path: Path) -> Path:
    sample_rate = 44100
    t = np.arange(sample_rate, dtype=np.float32) / sample_rate
    mono = (0.05 * np.sin(2.0 * np.pi * 220.0 * t)).astype(np.float32)
    sf.write(str(path), np.repeat(mono[:, None], 2, axis=1), sample_rate, subtype="PCM_16")
    return path


def _track_map(path: Path) -> dict:
    return {
        "document_type": "sample_brain.track_map",
        "schema_version": "1.1.0",
        "source": {
            "original": {
                "file_name": path.name,
                "size_bytes": path.stat().st_size,
                "hash": compute_file_hash(path),
                "audio_properties": {
                    "duration_sec": 1.0,
                    "sample_rate_hz": 44100,
                    "channels": 2,
                },
            }
        },
    }


def _semantic() -> dict:
    return {
        "document_type": "sample_brain.stock_music_analysis",
        "schema_version": "1.0.0",
        "semantic": {
            "status": "partial",
            "pace_character": {
                "status": "ok",
                "value": "upbeat",
                "source_ref": "rule_engine",
                "evidence_refs": ["track_map.analysis.musical.bpm"],
            },
        },
    }


def test_pond5_prepare_cli_writes_ready_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from src import context_analyze, stock_music_analysis
    from src.cli import main

    source = _write_stereo_wav(tmp_path / "My Track.wav")
    output = tmp_path / "bundle"
    config = tmp_path / "profiles.yaml"
    config.write_text(
        """profiles:\n  default:\n    pond5:\n      contributor:\n        composer: Example Composer\n        ipi: null\n        pro: null\n        publisher: null\n        copyright_owner: Example Owner\n      rights:\n        ownership_authorized: true\n        third_party_elements_cleared_for_resale: true\n        cleared_for_sampling: false\n      listing:\n        default_price_usd: 19\n""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        context_analyze,
        "analyze_context_file_cached",
        lambda *args, **kwargs: SimpleNamespace(track_map=_track_map(source)),
    )
    monkeypatch.setattr(
        stock_music_analysis,
        "produce_stock_music_analysis",
        lambda *args, **kwargs: _semantic(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sample-brain",
            "--config",
            str(config),
            "pond5",
            "prepare",
            str(source),
            "--output",
            str(output),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["document_type"] == "sample_brain.pond5_readiness"
    assert payload["readiness"]["status"] == "POND5_READY"
    assert sorted(path.name for path in output.iterdir()) == [
        "pond5.csv",
        "pond5_metadata.json",
        "pond5_readiness.json",
    ]
    metadata_text = (output / "pond5_metadata.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in metadata_text
    assert "Example Composer" in metadata_text


def test_pond5_prepare_rejects_invalid_override_shape_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from src import context_analyze, stock_music_analysis
    from src.cli import main

    source = _write_stereo_wav(tmp_path / "Track.wav")
    config = tmp_path / "profiles.yaml"
    config.write_text("profiles:\n  default: {}\n", encoding="utf-8")
    overrides = tmp_path / "overrides.json"
    overrides.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(
        context_analyze,
        "analyze_context_file_cached",
        lambda *args, **kwargs: SimpleNamespace(track_map=_track_map(source)),
    )
    monkeypatch.setattr(
        stock_music_analysis,
        "produce_stock_music_analysis",
        lambda *args, **kwargs: _semantic(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sample-brain",
            "--config",
            str(config),
            "pond5",
            "prepare",
            str(source),
            "--output",
            str(tmp_path / "bundle"),
            "--overrides-json",
            str(overrides),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2
    payload = json.loads(capsys.readouterr().err)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "POND5_PREPARE_FAILED"


def test_pond5_prepare_help_is_available(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from src.cli import main

    monkeypatch.setattr(sys, "argv", ["sample-brain", "pond5", "prepare", "--help"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--output" in out
    assert "--overrides-json" in out
