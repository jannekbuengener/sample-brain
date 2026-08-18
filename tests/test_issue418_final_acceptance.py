from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, text

import src.config as config_module
import src.db as db_module
from src.analyze import SHORT_AUDIO_QUALITY_NOTE, run_analyze
from tests.audio_fixtures import write_major_chord_wav, write_sine_wav


def _bind_db(monkeypatch, db_path: Path) -> None:
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    config_module.DB_PATH = db_path
    config_module.set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})


def _insert_sample(sample_id: int, audio: Path, duration: float) -> None:
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO samples (id, path, relpath, duration, hash) "
                "VALUES (:id, :path, :relpath, :duration, :hash)"
            ),
            {
                "id": sample_id,
                "path": str(audio),
                "relpath": audio.name,
                "duration": duration,
                "hash": "a" * 40,
            },
        )


def test_init_db_adds_evidence_columns_without_losing_legacy_feature_row(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    with engine.begin() as conn:
        conn.execute(
            text("CREATE TABLE samples (id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL)")
        )
        conn.execute(
            text(
                "CREATE TABLE features ("
                "sample_id INTEGER PRIMARY KEY, bpm REAL, key TEXT, key_conf REAL, "
                "loudness REAL, brightness REAL, mfcc_mean BLOB, mfcc_std BLOB, "
                "chroma_mean BLOB, chroma_std BLOB, class TEXT, pred_type TEXT)"
            )
        )
        conn.execute(text("INSERT INTO samples(id, path) VALUES (1, 'legacy.wav')"))
        conn.execute(
            text("INSERT INTO features(sample_id, bpm, key) VALUES (1, 128.0, 'C')")
        )

    _bind_db(monkeypatch, db_path)
    db_module.init_db()

    with db_module.get_engine().begin() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(features)"))}
        row = conn.execute(
            text("SELECT bpm, key FROM features WHERE sample_id = 1")
        ).fetchone()

    assert {"quality_note", "key_mode", "key_mode_evidence"} <= columns
    assert row == (128.0, "C")


def test_run_analyze_persists_real_known_mode_and_evidence(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "catalog.db"
    _bind_db(monkeypatch, db_path)
    db_module.init_db()
    audio = write_major_chord_wav(tmp_path / "cmaj.wav", frequency_hz=261.63)
    _insert_sample(1, audio, 2.0)

    run_analyze(only_missing=True)

    with db_module.get_engine().begin() as conn:
        row = conn.execute(
            text(
                "SELECT key, quality_note, key_mode, key_mode_evidence "
                "FROM features WHERE sample_id = 1"
            )
        ).fetchone()

    assert row[0] == "Cmaj"
    assert row[1] is None
    assert row[2] == "maj"
    evidence = json.loads(row[3])
    assert evidence["kind"] == "third_contrast"
    assert evidence["mode"] == "maj"
    assert evidence["contrast"] >= evidence["threshold"]


def test_run_analyze_persists_real_abstention_evidence(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "catalog.db"
    _bind_db(monkeypatch, db_path)
    db_module.init_db()
    audio = write_sine_wav(tmp_path / "c.wav", duration_sec=2.0, frequency_hz=261.63)
    _insert_sample(1, audio, 2.0)

    run_analyze(only_missing=True)

    with db_module.get_engine().begin() as conn:
        row = conn.execute(
            text(
                "SELECT key, quality_note, key_mode, key_mode_evidence "
                "FROM features WHERE sample_id = 1"
            )
        ).fetchone()

    assert row[0] == "C"
    assert row[1] is None
    assert row[2] is None
    evidence = json.loads(row[3])
    assert evidence["kind"] == "third_contrast"
    assert evidence["mode"] is None
    assert evidence["contrast"] < evidence["threshold"]


def test_run_analyze_persists_short_clip_quality_note(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "catalog.db"
    _bind_db(monkeypatch, db_path)
    db_module.init_db()
    audio = write_sine_wav(
        tmp_path / "short.wav", duration_sec=0.1, frequency_hz=440.0
    )
    _insert_sample(1, audio, 0.1)

    run_analyze(only_missing=True)

    with db_module.get_engine().begin() as conn:
        row = conn.execute(
            text(
                "SELECT key, quality_note, key_mode, key_mode_evidence "
                "FROM features WHERE sample_id = 1"
            )
        ).fetchone()

    assert row[0] is None
    assert row[1] == SHORT_AUDIO_QUALITY_NOTE
    assert row[2] is None
    assert row[3] is None
