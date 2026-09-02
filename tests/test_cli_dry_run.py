"""CLI --dry-run contract tests for potentially destructive headless commands (#487)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.cli_dry_run import DRY_RUN_CONTRACT_VERSION, build_dry_run_preview
from tests.audio_fixtures import write_sine_wav


def _run_main(monkeypatch, argv: list[str]):
    import sys

    from src import cli

    monkeypatch.setattr(sys, "argv", ["src.cli", *argv])
    try:
        cli.main()
        return 0
    except SystemExit as exc:
        return int(exc.code or 0)


def _parse_json_out(capsys) -> dict:
    out = capsys.readouterr().out
    return json.loads(out)


def _assert_preview_shape(payload: dict, *, command: str) -> None:
    assert payload["contract_version"] == DRY_RUN_CONTRACT_VERSION
    assert payload["command"] == command
    assert payload["dry_run"] is True
    assert payload["write_performed"] is False
    assert isinstance(payload["action"], str) and payload["action"]
    assert isinstance(payload["target_kind"], str) and payload["target_kind"]
    assert "planned_mutations" in payload
    assert isinstance(payload["skipped_or_prevented_writes"], list)
    assert payload["skipped_or_prevented_writes"]
    assert payload["validation"]["status"] == "ok"


def test_build_dry_run_preview_contract_defaults():
    preview = build_dry_run_preview(
        command="scan",
        action="catalog_upsert",
        target_kind="sqlite_catalog",
        planned_mutations={"sample_upserts": 2},
        skipped_or_prevented_writes=["samples_table_upsert"],
    )
    assert preview["dry_run"] is True
    assert preview["write_performed"] is False
    assert preview["contract_version"] == DRY_RUN_CONTRACT_VERSION


def test_scan_dry_run_discovers_without_db_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    samples = tmp_path / "samples"
    write_sine_wav(samples / "a.wav", duration_sec=0.2, frequency_hz=440.0)
    write_sine_wav(samples / "b.wav", duration_sec=0.2, frequency_hz=440.0)
    db_path = tmp_path / "catalog.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    from src.config import set_db_path
    import src.config as config_module

    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    config_module.DB_PATH = db_path

    flush_calls: list[int] = []

    def boom(*_a, **_k):
        flush_calls.append(1)
        raise AssertionError("_flush_scan_batch must not run in dry-run")

    monkeypatch.setattr("src.scan._flush_scan_batch", boom)
    monkeypatch.setattr(
        "src.scan.init_db",
        lambda: (_ for _ in ()).throw(AssertionError("init_db must not run in dry-run")),
    )

    code = _run_main(
        monkeypatch,
        ["scan", "--root", str(samples), "--dry-run"],
    )
    assert code == 0
    payload = _parse_json_out(capsys)
    _assert_preview_shape(payload, command="scan")
    assert payload["planned_mutations"]["sample_upserts"] == 2
    assert flush_calls == []
    assert not db_path.exists()


def test_scan_without_dry_run_still_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    samples = tmp_path / "samples"
    write_sine_wav(samples / "tone.wav", duration_sec=0.2, frequency_hz=440.0)
    db_path = tmp_path / "catalog.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    from src.config import set_db_path
    import src.config as config_module
    import src.db as db_module

    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    config_module.DB_PATH = db_path
    db_module.init_db()

    code = _run_main(monkeypatch, ["scan", "--root", str(samples)])
    assert code == 0
    assert "Scan completed." in capsys.readouterr().out
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    assert count == 1


def test_export_fl_dry_run_no_tags_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    fl_user = tmp_path / "fl-user-data"
    db_path = tmp_path / "catalog.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    from src.config import set_db_path
    import src.config as config_module
    import src.db as db_module
    from sqlalchemy import text

    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    config_module.DB_PATH = db_path
    db_module.init_db()
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO samples (path, relpath, samplerate, channels, duration, "
                "size_bytes, hash) VALUES ('tone.wav', 'tone.wav', 44100, 1, 0.2, 100, 'abc')"
            )
        )

    write_calls: list[str] = []

    def boom(*_a, **_k):
        write_calls.append("write")
        raise AssertionError("export write must not run in dry-run")

    monkeypatch.setattr("src.export_fl.write_fl_tags_from_sample_rows", boom)
    monkeypatch.setattr("src.export_fl._atomic_write_text", boom)

    code = _run_main(
        monkeypatch,
        ["export_fl", "--fl-user-data", str(fl_user), "--dry-run"],
    )
    assert code == 0
    payload = _parse_json_out(capsys)
    _assert_preview_shape(payload, command="export_fl")
    assert payload["planned_mutations"]["sample_rows"] == 1
    assert write_calls == []
    tags = fl_user / "FL Studio" / "Settings" / "Browser" / "Tags"
    assert not tags.exists()
    assert not (fl_user / "FL Studio").exists()


def test_export_fl_dry_run_missing_fl_user_data_keeps_exit(
    monkeypatch: pytest.MonkeyPatch, capsys, tmp_path: Path
):
    db_path = tmp_path / "catalog.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    from src.config import set_db_path
    import src.config as config_module

    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    config_module.DB_PATH = db_path
    monkeypatch.setattr(
        "src.cli._resolve_profile_or_exit",
        lambda *_a, **_k: {"library_roots": [], "export": {"max_tags": 5}},
    )

    code = _run_main(monkeypatch, ["export_fl", "--dry-run"])
    err = capsys.readouterr().err
    assert code == 1
    assert "FL Studio User Data" in err


def test_pack_import_dry_run_validates_without_db_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    from src.config import set_db_path
    import src.config as config_module
    import src.db as db_module

    db_path = tmp_path / "catalog.db"
    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    config_module.DB_PATH = db_path
    db_module.init_db()

    pack = tmp_path / "pack"
    pack.mkdir()
    code = _run_main(monkeypatch, ["pack-import", str(pack), "--dry-run"])
    err = capsys.readouterr().err
    assert code == 2
    assert "MANIFEST_NOT_FOUND" in err


def test_pack_import_dry_run_preview_on_valid_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    from src.config import set_db_path
    import src.config as config_module
    from tests.test_performance_pack_import import build_synthetic_pack

    db_path = tmp_path / "catalog.db"
    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    config_module.DB_PATH = db_path

    pack = tmp_path / "pack"
    build_synthetic_pack(pack, with_stem=False)

    register_calls: list[str] = []

    def boom(*_a, **_k):
        register_calls.append("register")
        raise AssertionError("_register_sample must not run in dry-run")

    monkeypatch.setattr("src.performance_pack_import._register_sample", boom)
    monkeypatch.setattr(
        "src.performance_pack_import.init_db",
        lambda: (_ for _ in ()).throw(AssertionError("init_db must not run in dry-run")),
    )

    code = _run_main(monkeypatch, ["pack-import", str(pack), "--dry-run"])
    assert code == 0
    payload = _parse_json_out(capsys)
    _assert_preview_shape(payload, command="pack-import")
    assert payload["planned_mutations"]["assets_importable"] == 2
    assert register_calls == []
    assert not db_path.exists()


def test_deconstruct_dry_run_no_pack_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    track = write_sine_wav(tmp_path / "track.wav", duration_sec=0.3, frequency_hz=440.0)
    pack_root = tmp_path / "pack-out"

    def boom(*_a, **_k):
        raise AssertionError("run_deconstruct must not execute in dry-run")

    monkeypatch.setattr("src.deconstruct.run_deconstruct", boom)
    monkeypatch.setattr(
        "src.performance_pack.finalize_performance_pack",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("finalize_performance_pack must not run")
        ),
    )

    code = _run_main(
        monkeypatch,
        [
            "deconstruct",
            str(track),
            "--pack-root",
            str(pack_root),
            "--skip-arrangement",
            "--skip-stems",
            "--dry-run",
        ],
    )
    assert code == 0
    payload = _parse_json_out(capsys)
    _assert_preview_shape(payload, command="deconstruct")
    assert payload["planned_mutations"]["steps"]
    assert not pack_root.exists()
    assert not (tmp_path / "deconstruct_run.json").exists()


def test_deconstruct_dry_run_keeps_stems_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    track = write_sine_wav(tmp_path / "track.wav", duration_sec=0.2, frequency_hz=440.0)
    pack_root = tmp_path / "out"
    code = _run_main(
        monkeypatch,
        [
            "deconstruct",
            str(track),
            "--pack-root",
            str(pack_root),
            "--stems",
            "--dry-run",
        ],
    )
    err = capsys.readouterr().err
    assert code == 2
    assert "--stem-model" in err
    assert not pack_root.exists()


def test_deconstruct_without_dry_run_still_writes_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    from src.deconstruct import RunResult, StepResult

    track = tmp_path / "track.wav"
    track.write_bytes(b"RIFF")
    pack_root = tmp_path / "out"

    def fake_run(track_path, pack_root, **kwargs):
        return RunResult(
            status="complete",
            track={"file_name": "track.wav"},
            pack_root=str(pack_root),
            steps=[StepResult(step_id="track_map", required=True, status="ok")],
            reason_codes=[],
        )

    monkeypatch.setattr("src.deconstruct.run_deconstruct", fake_run)
    monkeypatch.setattr(
        "src.performance_pack.finalize_performance_pack", lambda *a, **k: None
    )

    code = _run_main(
        monkeypatch,
        ["deconstruct", str(track), "--pack-root", str(pack_root)],
    )
    assert code == 0
    assert (pack_root / "deconstruct_run.json").exists()
