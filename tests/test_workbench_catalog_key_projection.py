"""Frozen #661 contract tests for the Workbench V2 catalog key boundary."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import src.config as config_module
import src.db as db_module
from src.db import decode_key_analysis_feature_record
from src.key_analysis_v2 import (
    KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION,
    KeyAnalysisV2Result,
    write_key_analysis_v2_features,
)
from src.workbench_catalog import load_catalog_samples
from src.workbench_controller import (
    add_workbench_library_folder,
    import_catalog_rows_to_cache,
    workbench_scope_requires_refresh,
)
from src.workbench_harmony import HarmonyRelation, rate_harmony
from src.workbench_library import load_sample_by_path


def _result(*, root: str = "C", mode: str | None = "maj") -> KeyAnalysisV2Result:
    if mode is None:
        major, minor, contrast = 0.2, 0.2, 0.0
    elif mode == "maj":
        major, minor, contrast = 0.8, 0.2, 0.6
    else:
        major, minor, contrast = 0.2, 0.8, 0.6
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
        mode_evidence={
            "kind": "third_contrast",
            "major_third_energy": major,
            "minor_third_energy": minor,
            "contrast": contrast,
            "threshold": 0.3,
            "mode": mode,
            "root": root,
            "root_source": "joint_24_profile_pearson",
        },
        contract_version=KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION,
    )


def _use_db(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(path))
    config_module.DB_PATH = path
    config_module.set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(path)})


def _seed_current_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    sample_path: Path | None = None,
) -> Path:
    db_path = tmp_path / "catalog.db"
    _use_db(db_path, monkeypatch)
    db_module.init_db()
    path = sample_path or (tmp_path / "sample.wav")
    with db_module.get_engine().begin() as conn:
        conn.execute(
            db_module.text(
                """
                INSERT INTO samples (id, path, relpath, size_bytes, duration, hash)
                VALUES (1, :path, 'sample.wav', 4, 1.5, 'hash')
                """
            ),
            {"path": str(path)},
        )
    return db_path


def _seed_legacy_catalog(tmp_path: Path) -> Path:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE samples (
                id INTEGER PRIMARY KEY, path TEXT, relpath TEXT,
                size_bytes INTEGER, duration REAL
            );
            CREATE TABLE features (
                sample_id INTEGER PRIMARY KEY, bpm REAL, key TEXT, key_conf REAL,
                loudness REAL, brightness REAL, class TEXT, pred_type TEXT
            );
            INSERT INTO samples VALUES
                (1, '/samples/legacy.wav', 'legacy.wav', 12, 2.0);
            INSERT INTO features VALUES
                (1, 128.0, 'Amin', 0.72, -12.0, 0.4, 'loop', 'kick');
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_legacy_catalog_stays_readonly_and_v1_compatible(tmp_path: Path):
    db_path = _seed_legacy_catalog(tmp_path)
    mtime_before = db_path.stat().st_mtime_ns

    rows = load_catalog_samples(db_path)

    assert db_path.stat().st_mtime_ns == mtime_before
    assert len(rows) == 1
    row = rows[0]
    assert row.key == "Amin"
    assert row.key_conf == pytest.approx(0.72)
    assert row.key_claim == "Amin"
    assert row.key_analysis_contract_version is None
    assert row.key_claim_valid is True
    assert row.key_matching_eligible is True


@pytest.mark.parametrize("mode, expected_key", [("maj", "Cmaj"), (None, "C")])
def test_v2_claim_is_recognized_but_not_projected_downstream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str | None,
    expected_key: str,
):
    db_path = _seed_current_catalog(tmp_path, monkeypatch)
    write_key_analysis_v2_features(sample_id=1, result=_result(mode=mode))

    row = load_catalog_samples(db_path)[0]
    projected = row.to_workbench_row()

    assert row.key_claim == expected_key
    assert row.key_mode == mode
    assert row.key_analysis_contract_version == 2
    assert row.key_claim_valid is True
    assert row.key_matching_eligible is False
    assert row.key is None
    assert row.key_conf is None
    assert projected.key is None
    assert projected.key_conf is None


@pytest.mark.parametrize("case", ["unknown", "malformed", "stale"])
def test_invalid_v2_key_claim_fails_closed_without_dropping_sample(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
):
    db_path = _seed_current_catalog(tmp_path, monkeypatch)
    result = _result()
    write_key_analysis_v2_features(sample_id=1, result=result)
    with db_module.get_engine().begin() as conn:
        if case == "unknown":
            conn.execute(
                db_module.text(
                    "UPDATE features SET key_analysis_contract_version = 99 WHERE sample_id = 1"
                )
            )
        elif case == "malformed":
            conn.execute(
                db_module.text(
                    "UPDATE features SET key_root_evidence = :value WHERE sample_id = 1"
                ),
                {"value": json.dumps({"kind": "bad"})},
            )
        else:
            conn.execute(
                db_module.text(
                    """
                    UPDATE features
                    SET key = 'Amin', key_conf = 0.77, key_mode = 'min'
                    WHERE sample_id = 1
                    """
                )
            )
        conn.execute(
            db_module.text(
                """
                UPDATE features
                SET bpm = 131.0, loudness = -9.0, brightness = 0.8,
                    class = 'loop', pred_type = 'kick'
                WHERE sample_id = 1
                """
            )
        )

    row = load_catalog_samples(db_path)[0]

    assert row.key is None
    assert row.key_conf is None
    assert row.key_claim is None
    assert row.key_claim_valid is False
    assert row.key_matching_eligible is False
    assert row.bpm == pytest.approx(131.0)
    assert row.loudness == pytest.approx(-9.0)
    assert row.brightness == pytest.approx(0.8)
    assert row.sample_class == "loop"
    assert row.pred_type == "kick"
    assert row.status == "ok"


def test_pure_decoder_matches_single_and_batch_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db_path = _seed_current_catalog(tmp_path, monkeypatch)
    result = _result(root="D", mode="min")
    write_key_analysis_v2_features(sample_id=1, result=result)
    raw = {
        "sample_id": 1,
        "key": result.key,
        "key_conf": None,
        "key_mode": result.mode,
        "key_mode_evidence": json.dumps(result.mode_evidence),
        "key_analysis_contract_version": 2,
        "key_root_evidence": json.dumps(result.root_evidence),
    }

    decoded = decode_key_analysis_feature_record(raw)
    single = db_module.read_key_analysis_feature_row(sample_id=1)
    batch = db_module.read_key_analysis_feature_rows(sample_ids=[1])[1]

    assert decoded == single == batch


def test_v2_catalog_claim_does_not_activate_harmonic_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db_path = _seed_current_catalog(tmp_path, monkeypatch)
    write_key_analysis_v2_features(sample_id=1, result=_result(root="C", mode="maj"))
    candidate = load_catalog_samples(db_path)[0].to_workbench_row()
    reference = type(candidate)(
        display_name="reference",
        relative_path="reference.wav",
        path="/reference.wav",
        bpm=128.0,
        key="Cmaj",
        key_conf=0.8,
        loudness=-12.0,
        brightness=0.4,
        sample_class="loop",
        pred_type="kick",
        status="ok",
    )

    suggestion = rate_harmony(reference, candidate)

    assert suggestion.relation is HarmonyRelation.UNCERTAIN


def test_v2_catalog_import_remains_stale_for_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    target = tmp_path / "library"
    target.mkdir()
    sample = target / "v2.wav"
    sample.write_bytes(b"RIFF")
    db_path = _seed_current_catalog(tmp_path, monkeypatch, sample_path=sample)
    write_key_analysis_v2_features(sample_id=1, result=_result(root="C", mode="maj"))
    catalog_row = load_catalog_samples(db_path)[0].to_workbench_row()

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    add_workbench_library_folder(target)

    result = import_catalog_rows_to_cache([catalog_row], target)
    cached = load_sample_by_path(str(sample))

    assert result.imported == 1
    assert cached is not None
    assert cached.key is None
    assert cached.analyzer_version is None
    assert workbench_scope_requires_refresh(folder_id=None, folder_path=target) is True
