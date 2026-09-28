"""Version-aware features.key read foundation (#650).

Additive reader only — no consumer migration, no analyzer mutation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

import src.config as config_module
import src.db as db_module
from src.key_analysis_v2 import (
    KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION,
    KeyAnalysisV2Result,
    write_key_analysis_v2_features,
)


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


def test_fresh_null_contract_reads_as_v1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()
    _insert_sample()
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO features (
                    sample_id, key, key_conf, key_mode, key_mode_evidence
                ) VALUES (
                    1, 'Cmaj', 0.62, 'maj', :mode_evidence
                )
                """
            ),
            {
                "mode_evidence": json.dumps(
                    {"kind": "third_contrast", "mode": "maj"},
                    sort_keys=True,
                    separators=(",", ":"),
                )
            },
        )

    record = db_module.read_key_analysis_feature_row(sample_id=1)

    assert record is not None
    assert record.sample_id == 1
    assert record.key == "Cmaj"
    assert record.key_conf == pytest.approx(0.62)
    assert record.key_mode == "maj"
    assert record.key_mode_evidence == {"kind": "third_contrast", "mode": "maj"}
    assert record.key_analysis_contract_version is None
    assert record.key_root_evidence is None


def test_legacy_null_contract_ignores_stale_root_evidence_column(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """NULL contract is V1 even if a stale root-evidence blob is present."""

    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()
    _insert_sample()
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO features (
                    sample_id, key, key_conf, key_mode,
                    key_analysis_contract_version, key_root_evidence
                ) VALUES (
                    1, 'G', 0.41, NULL, NULL, :root_evidence
                )
                """
            ),
            {
                "root_evidence": json.dumps(
                    {
                        "kind": "joint_24_profile_pearson",
                        "selected_root": "G",
                        "raw_top_score": 0.5,
                        "raw_top_mode": "maj",
                        "raw_top_mode_authoritative": False,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            },
        )

    record = db_module.read_key_analysis_feature_row(sample_id=1)

    assert record is not None
    assert record.key == "G"
    assert record.key_conf == pytest.approx(0.41)
    assert record.key_analysis_contract_version is None
    assert record.key_root_evidence is None


def test_valid_v2_row_reads_with_null_key_conf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()
    _insert_sample()
    result = _result(root="C", mode="maj")
    write_key_analysis_v2_features(sample_id=1, result=result)

    record = db_module.read_key_analysis_feature_row(sample_id=1)

    assert record is not None
    assert record.key == "Cmaj"
    assert record.key_conf is None
    assert record.key_mode == "maj"
    assert record.key_analysis_contract_version == 2
    assert record.key_root_evidence == result.root_evidence
    assert record.key_mode_evidence == result.mode_evidence


def test_unknown_contract_version_fails_closed(
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
                    sample_id, key, key_conf, key_mode,
                    key_analysis_contract_version, key_root_evidence
                ) VALUES (1, 'Cmaj', NULL, 'maj', 99, NULL)
                """
            )
        )

    assert db_module.read_key_analysis_feature_row(sample_id=1) is None


def test_malformed_v2_root_evidence_fails_closed(
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
                    sample_id, key, key_conf, key_mode, key_mode_evidence,
                    key_analysis_contract_version, key_root_evidence
                ) VALUES (
                    1, 'Cmaj', NULL, 'maj', :mode_evidence, 2, :root_evidence
                )
                """
            ),
            {
                "mode_evidence": json.dumps(_result().mode_evidence, sort_keys=True),
                "root_evidence": json.dumps({"kind": "not-v2"}, sort_keys=True),
            },
        )

    assert db_module.read_key_analysis_feature_row(sample_id=1) is None


def test_malformed_v2_mode_evidence_fails_closed(
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
                    sample_id, key, key_conf, key_mode, key_mode_evidence,
                    key_analysis_contract_version, key_root_evidence
                ) VALUES (
                    1, 'Cmaj', NULL, 'maj', :mode_evidence, 2, :root_evidence
                )
                """
            ),
            {
                "mode_evidence": json.dumps({"kind": "not-third-contrast"}, sort_keys=True),
                "root_evidence": json.dumps(_result().root_evidence, sort_keys=True),
            },
        )

    assert db_module.read_key_analysis_feature_row(sample_id=1) is None


def test_inconsistent_v2_key_vs_evidence_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()
    _insert_sample()
    result = _result(root="C", mode="maj")
    write_key_analysis_v2_features(sample_id=1, result=result)
    with db_module.get_engine().begin() as conn:
        conn.execute(text("UPDATE features SET key = 'Gmaj' WHERE sample_id = 1"))

    assert db_module.read_key_analysis_feature_row(sample_id=1) is None


def test_v1_overwrite_leaving_stale_contract_version_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """V1 upsert can refresh key/key_conf while leaving V2 columns untouched."""

    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()
    _insert_sample()
    write_key_analysis_v2_features(sample_id=1, result=_result())
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE features
                SET key = 'Amin', key_conf = 0.77, key_mode = 'min'
                WHERE sample_id = 1
                """
            )
        )
        row = conn.execute(
            text(
                """
                SELECT key, key_conf, key_analysis_contract_version, key_root_evidence
                FROM features WHERE sample_id = 1
                """
            )
        ).one()
    assert row[0] == "Amin"
    assert row[1] == pytest.approx(0.77)
    assert row[2] == 2
    assert row[3] is not None

    assert db_module.read_key_analysis_feature_row(sample_id=1) is None


def test_missing_features_row_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()
    _insert_sample()

    assert db_module.read_key_analysis_feature_row(sample_id=1) is None


def test_read_key_analysis_feature_rows_maps_hits_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()
    _insert_sample(1, "a.wav")
    _insert_sample(2, "b.wav")
    _insert_sample(3, "c.wav")
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO features (sample_id, key, key_conf) VALUES (1, 'C', 0.5)"
            )
        )
    write_key_analysis_v2_features(sample_id=2, result=_result(root="D", mode="min"))
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO features (
                    sample_id, key, key_conf, key_analysis_contract_version
                ) VALUES (3, 'E', NULL, 7)
                """
            )
        )

    rows = db_module.read_key_analysis_feature_rows(sample_ids=[1, 2, 3, 99])

    assert set(rows) == {1, 2}
    assert rows[1].key_analysis_contract_version is None
    assert rows[1].key_conf == pytest.approx(0.5)
    assert rows[2].key_analysis_contract_version == 2
    assert rows[2].key_conf is None
    assert rows[2].key == "Dmin"
