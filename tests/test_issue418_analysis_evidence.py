from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import soundfile as sf
from sqlalchemy import text

from src.analyze import Features, estimate_key, run_analyze


def _use_temp_db(tmp_path: Path, monkeypatch) -> Path:
    import src.config as config_module
    import src.db as db_module

    db_path = tmp_path / "catalog.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    config_module.DB_PATH = db_path
    config_module.set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    return db_path


def test_init_db_upgrades_legacy_features_schema(tmp_path: Path, monkeypatch):
    import src.db as db_module

    db_path = _use_temp_db(tmp_path, monkeypatch)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE samples (id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL)"
        )
        conn.execute(
            """
            CREATE TABLE features (
                sample_id INTEGER PRIMARY KEY,
                bpm REAL,
                key TEXT,
                key_conf REAL,
                loudness REAL,
                brightness REAL,
                mfcc_mean BLOB,
                mfcc_std BLOB,
                chroma_mean BLOB,
                chroma_std BLOB,
                class TEXT,
                pred_type TEXT
            )
            """
        )

    engine = db_module.init_db()
    with engine.begin() as conn:
        names = {
            row[1] for row in conn.execute(text("PRAGMA table_info(features)")).fetchall()
        }

    assert {"quality_note", "key_mode", "key_mode_evidence"} <= names


def test_run_analyze_persists_mode_and_uncertainty_evidence(
    tmp_path: Path, monkeypatch
):
    import src.analyze as analyze_module
    import src.db as db_module

    _use_temp_db(tmp_path, monkeypatch)
    engine = db_module.init_db()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO samples (id, path, relpath, duration, hash) "
                "VALUES (1, :path, 'fixture.wav', 2.0, :hash)"
            ),
            {"path": str(tmp_path / "fixture.wav"), "hash": "0" * 40},
        )

    evidence = {
        "kind": "third_contrast",
        "major_third_energy": 0.8,
        "minor_third_energy": 0.2,
        "contrast": 0.6,
        "threshold": 0.3,
        "mode": "maj",
    }
    monkeypatch.setattr(
        analyze_module,
        "extract_features",
        lambda *_args, **_kwargs: Features(
            bpm=128.0,
            key="Cmaj",
            key_conf=0.42,
            loudness=-12.0,
            brightness=1800.0,
            mfcc_mean=None,
            mfcc_std=None,
            chroma_mean=None,
            chroma_std=None,
            clazz="loop",
            quality_note="relative evidence only",
            key_mode="maj",
            key_mode_evidence=evidence,
        ),
    )

    run_analyze(only_missing=True)

    with db_module.get_engine().begin() as conn:
        row = conn.execute(
            text(
                "SELECT quality_note, key_mode, key_mode_evidence "
                "FROM features WHERE sample_id = 1"
            )
        ).fetchone()

    assert row[0] == "relative evidence only"
    assert row[1] == "maj"
    assert json.loads(row[2]) == evidence
    assert row[2] == json.dumps(
        evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def test_run_analyze_retains_evidence_when_mode_abstains(tmp_path: Path, monkeypatch):
    import src.analyze as analyze_module
    import src.db as db_module

    _use_temp_db(tmp_path, monkeypatch)
    engine = db_module.init_db()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO samples (id, path, relpath, duration, hash) "
                "VALUES (1, :path, 'ambiguous.wav', 2.0, :hash)"
            ),
            {"path": str(tmp_path / "ambiguous.wav"), "hash": "0" * 40},
        )

    evidence = {
        "kind": "third_contrast",
        "major_third_energy": 0.5,
        "minor_third_energy": 0.5,
        "contrast": 0.0,
        "threshold": 0.3,
        "mode": None,
    }
    monkeypatch.setattr(
        analyze_module,
        "extract_features",
        lambda *_args, **_kwargs: Features(
            bpm=128.0,
            key="C",
            key_conf=0.31,
            loudness=-12.0,
            brightness=1800.0,
            mfcc_mean=None,
            mfcc_std=None,
            chroma_mean=None,
            chroma_std=None,
            clazz="loop",
            quality_note=None,
            key_mode=None,
            key_mode_evidence=evidence,
        ),
    )

    run_analyze(only_missing=True)

    with db_module.get_engine().begin() as conn:
        row = conn.execute(
            text(
                "SELECT key, key_mode, key_mode_evidence "
                "FROM features WHERE sample_id = 1"
            )
        ).fetchone()

    assert row[0] == "C"
    assert row[1] is None
    assert json.loads(row[2]) == evidence


def test_bass_dominant_root_baseline_uses_synthetic_audio(tmp_path: Path):
    sr = 44100
    duration = 2.0
    sample_count = int(sr * duration)
    t = np.linspace(0.0, duration, sample_count, endpoint=False, dtype=np.float32)

    # Tonal center C with a deliberately dominant C2 bass plus a quieter C-major
    # upper triad. This covers bass dominance without committing private audio.
    components = (
        (65.406, 0.85),
        (261.626, 0.30),
        (329.628, 0.22),
        (391.995, 0.20),
    )
    wave = sum(amp * np.sin(2.0 * np.pi * hz * t) for hz, amp in components)
    wave = np.asarray(wave, dtype=np.float32)
    wave /= max(float(np.max(np.abs(wave))), 1.0)
    path = tmp_path / "bass_dominant_c_major.wav"
    sf.write(path, wave, sr, subtype="PCM_16")

    root, evidence = estimate_key(wave, sr)

    assert root == "C"
    assert evidence is not None
    assert 0.0 < evidence <= 1.0
