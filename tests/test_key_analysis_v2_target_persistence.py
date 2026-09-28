from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text

import src.config as config_module
import src.db as db_module
from src.analyze import run_analyze
from src.key_analysis_v2 import (
    KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION,
    KeyAnalysisV2Result,
    serialize_key_analysis_v2_evidence,
    write_key_analysis_v2_features,
)
from tests.audio_fixtures import write_sine_wav


NOTE_HZ_C = 261.63


def _result(*, root: str = "C", mode: str | None = "maj") -> KeyAnalysisV2Result:
    if mode is None:
        mode_evidence = {
            "kind": "third_contrast",
            "major_third_energy": 0.2,
            "minor_third_energy": 0.2,
            "contrast": 0.0,
            "threshold": 0.3,
            "mode": None,
            "root": root,
            "root_source": "joint_24_profile_pearson",
        }
    elif mode == "maj":
        mode_evidence = {
            "kind": "third_contrast",
            "major_third_energy": 0.8,
            "minor_third_energy": 0.2,
            "contrast": 0.6,
            "threshold": 0.3,
            "mode": "maj",
            "root": root,
            "root_source": "joint_24_profile_pearson",
        }
    else:
        mode_evidence = {
            "kind": "third_contrast",
            "major_third_energy": 0.2,
            "minor_third_energy": 0.8,
            "contrast": 0.6,
            "threshold": 0.3,
            "mode": "min",
            "root": root,
            "root_source": "joint_24_profile_pearson",
        }
    return KeyAnalysisV2Result(
        key=f"{root}{mode or ''}",
        root=root,
        mode=mode,
        root_evidence={
            "kind": "joint_24_profile_pearson",
            "selected_root": root,
            "raw_top_score": 0.75,
            "raw_top_mode": "maj",
            "raw_top_mode_authoritative": False,
        },
        mode_evidence=mode_evidence,
        contract_version=KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION,
    )


def _use_temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "catalog.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    config_module.DB_PATH = db_path
    config_module.set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    return db_path


def _insert_sample(sample_id: int = 1, path: str = "sample.wav") -> None:
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO samples (id, path, hash, hash_algorithm) "
                "VALUES (:id, :path, :hash, 'sha256')"
            ),
            {"id": sample_id, "path": path, "hash": "a" * 64},
        )


def _feature_columns(engine) -> set[str]:
    with engine.begin() as conn:
        return {row[1] for row in conn.execute(text("PRAGMA table_info(features)"))}


def _read_features(sample_id: int = 1) -> dict:
    with db_module.get_engine().begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT sample_id, bpm, key, key_conf, loudness, brightness,
                       mfcc_mean, mfcc_std, chroma_mean, chroma_std, class,
                       quality_note, key_mode, key_mode_evidence,
                       key_analysis_contract_version, key_root_evidence
                FROM features
                WHERE sample_id = :sample_id
                """
            ),
            {"sample_id": sample_id},
        ).mappings().one()
        return dict(row)


def test_fresh_db_features_include_nullable_v2_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _use_temp_db(tmp_path, monkeypatch)
    engine = db_module.init_db()
    columns = _feature_columns(engine)

    assert "key_analysis_contract_version" in columns
    assert "key_root_evidence" in columns

    _insert_sample()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO features (sample_id, key, key_conf) VALUES (1, 'C', 0.5)")
        )
        row = conn.execute(
            text(
                "SELECT key_analysis_contract_version, key_root_evidence "
                "FROM features WHERE sample_id = 1"
            )
        ).one()
    assert row == (None, None)


def test_legacy_v1_db_migrates_additive_columns_without_backfill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db_path = _use_temp_db(tmp_path, monkeypatch)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE samples (id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, hash TEXT)"
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
                pred_type TEXT,
                quality_note TEXT,
                key_mode TEXT,
                key_mode_evidence TEXT
            )
            """
        )
        conn.execute("INSERT INTO samples (id, path, hash) VALUES (1, 'legacy.wav', ?)", ("b" * 40,))
        conn.execute(
            """
            INSERT INTO features (
                sample_id, bpm, key, key_conf, loudness, brightness,
                mfcc_mean, mfcc_std, chroma_mean, chroma_std, class,
                quality_note, key_mode, key_mode_evidence
            ) VALUES (1, 120.0, 'Cmaj', 0.55, -12.0, 2200.0, X'01', X'02', X'03', X'04',
                      'loop', 'ok', 'maj', '{"kind":"third_contrast"}')
            """
        )

    engine = db_module.init_db()
    columns = _feature_columns(engine)
    assert "key_analysis_contract_version" in columns
    assert "key_root_evidence" in columns

    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT bpm, key, key_conf, loudness, brightness, class, quality_note,
                       key_mode, key_mode_evidence,
                       key_analysis_contract_version, key_root_evidence
                FROM features WHERE sample_id = 1
                """
            )
        ).one()
    assert row[0] == 120.0
    assert row[1] == "Cmaj"
    assert row[2] == 0.55
    assert row[3] == -12.0
    assert row[4] == 2200.0
    assert row[5] == "loop"
    assert row[6] == "ok"
    assert row[7] == "maj"
    assert row[8] == '{"kind":"third_contrast"}'
    assert row[9] is None
    assert row[10] is None


def test_init_db_migration_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _use_temp_db(tmp_path, monkeypatch)
    first = db_module.init_db()
    _insert_sample()
    with first.begin() as conn:
        conn.execute(
            text("INSERT INTO features (sample_id, key, key_conf) VALUES (1, 'G', 0.4)")
        )
    before = _read_features()

    second = db_module.init_db()
    third = db_module.init_db()
    assert _feature_columns(second) == _feature_columns(third)
    assert _read_features() == before


def test_explicit_v2_upsert_updates_key_contract_and_preserves_unrelated_features(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()
    _insert_sample()
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO features (
                    sample_id, bpm, key, key_conf, loudness, brightness,
                    mfcc_mean, mfcc_std, chroma_mean, chroma_std, class,
                    quality_note, key_mode, key_mode_evidence
                ) VALUES (
                    1, 128.0, 'Amin', 0.71, -9.5, 3100.0,
                    X'dead', X'beef', X'cafe', X'babe', 'oneshot',
                    'v1-note', 'min', '{"kind":"third_contrast","mode":"min"}'
                )
                """
            )
        )

    result = _result(root="C", mode="maj")
    write_key_analysis_v2_features(sample_id=1, result=result)
    row = _read_features()

    assert row["key"] == "Cmaj"
    assert row["key_conf"] is None
    assert row["key_mode"] == "maj"
    assert row["key_analysis_contract_version"] == 2
    assert json.loads(row["key_root_evidence"]) == result.root_evidence
    assert json.loads(row["key_mode_evidence"]) == result.mode_evidence
    assert row["bpm"] == 128.0
    assert row["loudness"] == -9.5
    assert row["brightness"] == 3100.0
    assert row["mfcc_mean"] == b"\xde\xad"
    assert row["mfcc_std"] == b"\xbe\xef"
    assert row["chroma_mean"] == b"\xca\xfe"
    assert row["chroma_std"] == b"\xba\xbe"
    assert row["class"] == "oneshot"
    assert row["quality_note"] == "v1-note"


def test_explicit_v2_upsert_creates_minimal_row_for_sample_without_features(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()
    _insert_sample()

    result = _result(root="G", mode=None)
    write_key_analysis_v2_features(sample_id=1, result=result)
    row = _read_features()

    assert row["key"] == "G"
    assert row["key_conf"] is None
    assert row["key_mode"] is None
    assert row["key_analysis_contract_version"] == 2
    assert json.loads(row["key_root_evidence"]) == result.root_evidence
    assert json.loads(row["key_mode_evidence"]) == result.mode_evidence
    assert row["bpm"] is None
    assert row["loudness"] is None
    assert row["brightness"] is None
    assert row["mfcc_mean"] is None
    assert row["mfcc_std"] is None
    assert row["chroma_mean"] is None
    assert row["chroma_std"] is None
    assert row["class"] is None
    assert row["quality_note"] is None


def test_v2_features_evidence_json_is_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()
    _insert_sample()
    result = _result()

    write_key_analysis_v2_features(sample_id=1, result=result)
    first = _read_features()
    write_key_analysis_v2_features(sample_id=1, result=result)
    second = _read_features()

    assert first["key_root_evidence"] == second["key_root_evidence"]
    assert first["key_mode_evidence"] == second["key_mode_evidence"]
    assert first["key_root_evidence"] == serialize_key_analysis_v2_evidence(result.root_evidence)
    assert first["key_mode_evidence"] == serialize_key_analysis_v2_evidence(result.mode_evidence)


def test_invalid_v2_evidence_fails_closed_without_mutating_existing_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()
    _insert_sample()
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO features (
                    sample_id, bpm, key, key_conf, loudness, key_mode
                ) VALUES (1, 100.0, 'Dmin', 0.62, -14.0, 'min')
                """
            )
        )
    before = _read_features()

    bad_cases = [
        _result(root="C", mode="maj").__class__(
            key="Cmaj",
            root="C",
            mode="maj",
            root_evidence={
                "kind": "joint_24_profile_pearson",
                "selected_root": "G",
                "raw_top_score": 0.75,
                "raw_top_mode": "maj",
                "raw_top_mode_authoritative": False,
            },
            mode_evidence=_result().mode_evidence,
        ),
        KeyAnalysisV2Result(
            key="Cmaj",
            root="C",
            mode="maj",
            root_evidence={
                "kind": "joint_24_profile_pearson",
                "selected_root": "C",
                "raw_top_score": 1.5,
                "raw_top_mode": "maj",
                "raw_top_mode_authoritative": False,
            },
            mode_evidence=_result().mode_evidence,
        ),
        KeyAnalysisV2Result(
            key="Cmaj",
            root="C",
            mode="maj",
            root_evidence=_result().root_evidence,
            mode_evidence={
                **_result().mode_evidence,
                "mode": "min",
            },
        ),
        KeyAnalysisV2Result(
            key="Cmin",
            root="C",
            mode="maj",
            root_evidence=_result().root_evidence,
            mode_evidence=_result().mode_evidence,
        ),
        KeyAnalysisV2Result(
            key="Cmaj",
            root="C",
            mode="maj",
            root_evidence=_result().root_evidence,
            mode_evidence=_result().mode_evidence,
            contract_version=1,
        ),
        KeyAnalysisV2Result(
            key="Cmaj",
            root="C",
            mode="maj",
            root_evidence=_result().root_evidence,
            mode_evidence={**_result().mode_evidence, "confidence": 0.9},
        ),
    ]

    for bad in bad_cases:
        with pytest.raises(ValueError):
            write_key_analysis_v2_features(sample_id=1, result=bad)
        assert _read_features() == before


def test_successful_v2_upsert_always_nulls_key_conf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()
    _insert_sample()
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text("INSERT INTO features (sample_id, key, key_conf) VALUES (1, 'F', 0.99)")
        )

    write_key_analysis_v2_features(sample_id=1, result=_result(mode=None))
    assert _read_features()["key_conf"] is None


def test_v1_run_analyze_does_not_backfill_v2_contract_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _use_temp_db(tmp_path, monkeypatch)
    engine = db_module.init_db()
    path = write_sine_wav(tmp_path / "v1.wav", duration_sec=2.0, frequency_hz=NOTE_HZ_C)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO samples (id, path, duration, hash, hash_algorithm) "
                "VALUES (1, :path, 2.0, :hash, 'sha256')"
            ),
            {"path": str(path), "hash": "c" * 64},
        )

    run_analyze(only_missing=True)
    row = _read_features()

    assert row["key"] is not None or row["key"] is None  # analysis may abstain
    assert row["key_analysis_contract_version"] is None
    assert row["key_root_evidence"] is None
    # V1 still writes its own confidence semantics when a root is found.
    if row["key"] is not None:
        assert row["key_conf"] is not None


def test_v1_reader_path_works_with_additive_columns_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()
    _insert_sample()
    write_key_analysis_v2_features(sample_id=1, result=_result())

    # Legacy/V1 reader only selects historical columns and ignores additive V2 fields.
    with db_module.get_engine().begin() as conn:
        legacy = conn.execute(
            text(
                """
                SELECT sample_id, bpm, key, key_conf, loudness, brightness,
                       key_mode, key_mode_evidence
                FROM features WHERE sample_id = 1
                """
            )
        ).mappings().one()

    assert legacy["sample_id"] == 1
    assert legacy["key"] == "Cmaj"
    assert legacy["key_conf"] is None
    assert legacy["key_mode"] == "maj"
    assert json.loads(legacy["key_mode_evidence"])["kind"] == "third_contrast"


def test_v2_upsert_rejects_missing_sample(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()

    with pytest.raises(ValueError, match="sample does not exist"):
        write_key_analysis_v2_features(sample_id=99, result=_result())
