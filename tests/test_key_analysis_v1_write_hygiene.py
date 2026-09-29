"""Catalog V1 write hygiene: real producer path clears V2 provenance (#688).

RED-test gate: these tests exercise ``_FEATURE_UPSERT`` / ``_flush_feature_batch``
/ ``run_analyze``, not a simulated SQL UPDATE of key columns alone.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

import src.analyze as analyze_module
import src.config as config_module
import src.db as db_module
from src.analyze import (
    KEY_ANALYSIS_CONTRACT_VERSION,
    Features,
    _flush_feature_batch,
    _serialize_key_mode_evidence,
    run_analyze,
)
from src.key_analysis_v2 import (
    KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION,
    KeyAnalysisV2Result,
    write_key_analysis_v2_features,
)


def _v1_mode_evidence(*, root: str = "A", mode: str = "min") -> dict:
    return {
        "kind": "third_contrast",
        "major_third_energy": 0.1,
        "minor_third_energy": 0.9,
        "contrast": 0.8,
        "threshold": 0.3,
        "mode": mode,
        "root": root,
    }


def _v1_features(
    *,
    bpm: float = 120.0,
    key: str = "Amin",
    key_conf: float = 0.77,
    key_mode: str = "min",
    loudness: float = -11.0,
    brightness: float = 1800.0,
    clazz: str = "loop",
) -> Features:
    return Features(
        bpm=bpm,
        key=key,
        key_conf=key_conf,
        loudness=loudness,
        brightness=brightness,
        mfcc_mean=b"\x01\x02",
        mfcc_std=b"\x03\x04",
        chroma_mean=b"\x05\x06",
        chroma_std=b"\x07\x08",
        clazz=clazz,
        quality_note=None,
        key_mode=key_mode,
        key_mode_evidence=_v1_mode_evidence(root=key.rstrip("majmin") or "A", mode=key_mode),
    )


def _v2_result(*, root: str = "C", mode: str | None = "maj") -> KeyAnalysisV2Result:
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


def _insert_sample(
    sample_id: int = 1,
    path: str = "sample.wav",
    *,
    duration: float = 2.0,
) -> None:
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO samples (id, path, duration, hash, hash_algorithm) "
                "VALUES (:id, :path, :duration, :hash, 'sha256')"
            ),
            {
                "id": sample_id,
                "path": path,
                "duration": duration,
                "hash": "a" * 64,
            },
        )


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


def _flush_row_from_features(sample_id: int, feats: Features) -> dict:
    return {
        "sample_id": sample_id,
        "bpm": feats.bpm,
        "key": feats.key,
        "key_conf": feats.key_conf,
        "loudness": feats.loudness,
        "brightness": feats.brightness,
        "mfcc_mean": feats.mfcc_mean,
        "mfcc_std": feats.mfcc_std,
        "chroma_mean": feats.chroma_mean,
        "chroma_std": feats.chroma_std,
        "clazz": feats.clazz,
        "quality_note": feats.quality_note,
        "key_mode": feats.key_mode,
        "key_mode_evidence": _serialize_key_mode_evidence(feats.key_mode_evidence),
    }


def test_production_default_remains_v1() -> None:
    assert KEY_ANALYSIS_CONTRACT_VERSION == 1


def test_fresh_v1_flush_writes_null_contract_and_no_root_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_temp_db(tmp_path, monkeypatch)
    engine = db_module.init_db()
    _insert_sample()
    feats = _v1_features()

    _flush_feature_batch(engine, [_flush_row_from_features(1, feats)])
    row = _read_features()

    assert row["key"] == "Amin"
    assert row["key_conf"] == pytest.approx(0.77)
    assert row["key_mode"] == "min"
    assert json.loads(row["key_mode_evidence"]) == feats.key_mode_evidence
    assert row["key_analysis_contract_version"] is None
    assert row["key_root_evidence"] is None

    record = db_module.read_key_analysis_feature_row(sample_id=1)
    assert record is not None
    assert record.key_analysis_contract_version is None
    assert record.key_root_evidence is None
    assert record.key == "Amin"
    assert record.key_conf == pytest.approx(0.77)
    assert record.key_mode == "min"


def test_v1_reanalyze_via_flush_clears_stale_v2_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real ``_flush_feature_batch`` path must clear V2 markers (not SQL UPDATE)."""

    _use_temp_db(tmp_path, monkeypatch)
    engine = db_module.init_db()
    _insert_sample()
    write_key_analysis_v2_features(sample_id=1, result=_v2_result())
    before = _read_features()
    assert before["key_analysis_contract_version"] == 2
    assert before["key_root_evidence"] is not None
    assert before["key_conf"] is None

    feats = _v1_features(
        bpm=132.0,
        key="Amin",
        key_conf=0.81,
        loudness=-8.5,
        brightness=2400.0,
        clazz="oneshot",
    )
    _flush_feature_batch(engine, [_flush_row_from_features(1, feats)])
    row = _read_features()

    assert row["key"] == "Amin"
    assert row["key_conf"] == pytest.approx(0.81)
    assert row["key_mode"] == "min"
    assert json.loads(row["key_mode_evidence"]) == feats.key_mode_evidence
    assert row["key_analysis_contract_version"] is None
    assert row["key_root_evidence"] is None
    assert row["bpm"] == pytest.approx(132.0)
    assert row["loudness"] == pytest.approx(-8.5)
    assert row["brightness"] == pytest.approx(2400.0)
    assert row["class"] == "oneshot"
    assert row["mfcc_mean"] == b"\x01\x02"

    record = db_module.read_key_analysis_feature_row(sample_id=1)
    assert record is not None
    assert record.key_analysis_contract_version is None
    assert record.key_root_evidence is None
    assert record.key == "Amin"
    assert record.key_conf == pytest.approx(0.81)
    assert record.key_mode == "min"
    assert record.key_mode_evidence == feats.key_mode_evidence


def test_v1_reanalyze_via_run_analyze_clears_stale_v2_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``run_analyze(only_missing=False)`` must use the hygienic upsert path."""

    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()
    _insert_sample(path=str(tmp_path / "reanalyze.wav"))
    write_key_analysis_v2_features(sample_id=1, result=_v2_result(root="D", mode="min"))
    before = _read_features()
    assert before["key_analysis_contract_version"] == 2
    assert before["key"] == "Dmin"
    assert before["key_conf"] is None

    feats = _v1_features(key="Gmaj", key_conf=0.66, key_mode="maj")
    monkeypatch.setattr(
        analyze_module,
        "extract_features",
        lambda *_args, **_kwargs: feats,
    )

    run_analyze(only_missing=False)

    row = _read_features()
    assert row["key"] == "Gmaj"
    assert row["key_conf"] == pytest.approx(0.66)
    assert row["key_mode"] == "maj"
    assert json.loads(row["key_mode_evidence"]) == feats.key_mode_evidence
    assert row["key_analysis_contract_version"] is None
    assert row["key_root_evidence"] is None

    record = db_module.read_key_analysis_feature_row(sample_id=1)
    assert record is not None
    assert record.key_analysis_contract_version is None
    assert record.key == "Gmaj"
    assert record.key_conf == pytest.approx(0.66)


def test_v2_writer_still_correct_after_v1_hygiene_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_temp_db(tmp_path, monkeypatch)
    engine = db_module.init_db()
    _insert_sample()
    _flush_feature_batch(engine, [_flush_row_from_features(1, _v1_features())])

    result = _v2_result(root="E", mode=None)
    write_key_analysis_v2_features(sample_id=1, result=result)
    row = _read_features()

    assert row["key"] == "E"
    assert row["key_conf"] is None
    assert row["key_mode"] is None
    assert row["key_analysis_contract_version"] == 2
    assert json.loads(row["key_root_evidence"]) == result.root_evidence
    assert json.loads(row["key_mode_evidence"]) == result.mode_evidence
    # Unrelated non-key columns preserved by V2 writer
    assert row["bpm"] == pytest.approx(120.0)
    assert row["loudness"] == pytest.approx(-11.0)
