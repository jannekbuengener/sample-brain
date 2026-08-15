from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.deconstruct import RunResult, StepResult


def _fake_run(status: str) -> RunResult:
    return RunResult(
        status=status,
        track={"file_name": "x.wav", "hash": {"algorithm": "sha1", "value": "abc"}},
        pack_root="out",
        steps=[
            StepResult(step_id="track_map", required=True, status="ok"),
            StepResult(step_id="arrangement", required=False, status="ok"),
            StepResult(step_id="assets", required=False, status="ok"),
            StepResult(step_id="stems", required=False, status="not_run"),
        ],
        reason_codes=[],
    )


def _run_cli(monkeypatch, capsys, argv, status="complete"):
    captured = {}

    def fake(track_path, pack_root, **kwargs):
        captured["track_path"] = track_path
        captured["pack_root"] = pack_root
        captured["kwargs"] = kwargs
        return _fake_run(status)

    monkeypatch.setattr("src.deconstruct.run_deconstruct", fake)

    import sys

    from src import cli

    monkeypatch.setattr(sys, "argv", ["src.cli", "deconstruct", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    out = capsys.readouterr().out
    return exc.value.code, captured, out


def test_cli_deconstruct_invokes_orchestrator_exactly(tmp_path, monkeypatch, capsys):
    code, cap, _ = _run_cli(
        monkeypatch, capsys, [str(tmp_path / "x.wav"), "--pack-root", str(tmp_path / "out")]
    )
    assert code == 0
    assert cap["track_path"] == (tmp_path / "x.wav")
    assert cap["pack_root"] == (tmp_path / "out")
    # No adapters injected via CLI: real production adapters are used.
    assert cap["kwargs"].get("adapters") is None


def test_cli_exit_code_complete(tmp_path, monkeypatch, capsys):
    code, _, _ = _run_cli(
        monkeypatch,
        capsys,
        [str(tmp_path / "x.wav"), "--pack-root", str(tmp_path / "out")],
        status="complete",
    )
    assert code == 0


def test_cli_exit_code_partial(tmp_path, monkeypatch, capsys):
    code, _, _ = _run_cli(
        monkeypatch,
        capsys,
        [str(tmp_path / "x.wav"), "--pack-root", str(tmp_path / "out")],
        status="partial",
    )
    assert code == 0


def test_cli_exit_code_failed(tmp_path, monkeypatch, capsys):
    code, _, _ = _run_cli(
        monkeypatch,
        capsys,
        [str(tmp_path / "x.wav"), "--pack-root", str(tmp_path / "out")],
        status="failed",
    )
    assert code == 2


def test_cli_passes_skip_and_backend_flags(tmp_path, monkeypatch, capsys):
    code, cap, _ = _run_cli(
        monkeypatch,
        capsys,
        [
            str(tmp_path / "x.wav"),
            "--pack-root",
            str(tmp_path / "out"),
            "--skip-arrangement",
            "--skip-stems",
            "--beat-backend",
            "librosa",
            "--bpm-normalization",
            "half",
        ],
    )
    assert code == 0
    assert cap["kwargs"]["skip"] == {"arrangement", "stems"}
    assert cap["kwargs"]["beat_backend"] == "librosa"
    assert cap["kwargs"]["bpm_normalization"] == "half"


def test_cli_writes_evidence_file(tmp_path, monkeypatch, capsys):
    _run_cli(
        monkeypatch,
        capsys,
        [str(tmp_path / "x.wav"), "--pack-root", str(tmp_path / "out")],
    )
    evidence = tmp_path / "out" / "deconstruct_run.json"
    assert evidence.exists()
    data = json.loads(evidence.read_text(encoding="utf-8"))
    assert data["document_type"] == "sample_brain.deconstruct_run"
    assert data["status"] == "complete"


def test_cli_help_exits_ok(monkeypatch):
    import sys

    from src import cli

    monkeypatch.setattr(sys, "argv", ["src.cli", "deconstruct", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0


def test_cli_no_db_required(tmp_path, monkeypatch, capsys):
    # The orchestrator path must not require a catalog DB.
    code, _, _ = _run_cli(
        monkeypatch,
        capsys,
        [str(tmp_path / "x.wav"), "--pack-root", str(tmp_path / "out")],
    )
    assert code == 0


def test_cli_resume_enabled_by_default(tmp_path, monkeypatch, capsys):
    _, cap, _ = _run_cli(
        monkeypatch,
        capsys,
        [str(tmp_path / "x.wav"), "--pack-root", str(tmp_path / "out")],
    )
    assert cap["kwargs"].get("resume") is True


def test_cli_no_resume_disables_resume(tmp_path, monkeypatch, capsys):
    _, cap, _ = _run_cli(
        monkeypatch,
        capsys,
        [str(tmp_path / "x.wav"), "--pack-root", str(tmp_path / "out"), "--no-resume"],
    )
    assert cap["kwargs"].get("resume") is False
