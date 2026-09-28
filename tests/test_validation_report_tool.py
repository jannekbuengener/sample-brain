from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

import src.config as config_module
from src.key_analysis_v2 import (
    KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION,
    KeyAnalysisV2Result,
    write_key_analysis_v2_features,
)
from tools.validate_report import (
    classify_bpm_match,
    extract_bpm_hint,
    extract_instrument_hint,
    extract_key_hint,
    extract_type_hint,
    generate_report,
)


def _create_legacy_v1_catalog(path: Path) -> None:
    """Legacy features schema without V2 columns (pre-#646)."""

    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE samples (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                relpath TEXT,
                samplerate INT,
                channels INT,
                duration REAL,
                size_bytes INT,
                hash TEXT
            );
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
            );
            """
        )
        connection.executemany(
            "INSERT INTO samples (id, path, relpath, duration) VALUES (?, ?, ?, ?)",
            [
                (1, "private-a.wav", "loops/Kick_128bpm_Am_loop.wav", 4.0),
                (2, "private-b.wav", "oneshots/Snare_130bpm_Cmaj_oneshot.wav", 0.4),
            ],
        )
        connection.executemany(
            """
            INSERT INTO features
                (sample_id, bpm, key, key_conf, loudness, brightness, class, pred_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 128.2, "Amin", 0.82, -12.0, 1600.0, "loop", "Kick"),
                (2, 65.0, "Cmaj", 0.78, -10.0, 3200.0, "oneshot", "Snare"),
            ],
        )
        connection.commit()
    finally:
        connection.close()


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


def _bind_db(path: Path) -> None:
    config_module.DB_PATH = path
    config_module.set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(path)})


def _create_migrated_catalog_with_sample(
    path: Path,
    *,
    sample_id: int = 1,
    sample_path: str = "private-a.wav",
    relpath: str = "loops/Kick_128bpm_Am_loop.wav",
) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE samples (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                relpath TEXT,
                hash TEXT,
                hash_algorithm TEXT
            );
            CREATE TABLE features (
                sample_id INTEGER PRIMARY KEY,
                bpm REAL,
                key TEXT,
                key_conf REAL,
                loudness REAL,
                brightness REAL,
                class TEXT,
                pred_type TEXT,
                key_mode TEXT,
                key_mode_evidence TEXT,
                key_analysis_contract_version INTEGER,
                key_root_evidence TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO samples (id, path, relpath, hash, hash_algorithm) "
            "VALUES (?, ?, ?, ?, 'sha256')",
            (sample_id, sample_path, relpath, "a" * 64),
        )
        connection.commit()
    finally:
        connection.close()


def test_weak_label_helpers_are_conservative() -> None:
    assert extract_bpm_hint("loops/Kick_128bpm_Am_loop.wav") == 128.0
    assert classify_bpm_match(128.2, 128.0) == "match"
    assert classify_bpm_match(65.0, 130.0) == "half_time"
    assert extract_key_hint("Kick_128bpm_Am_loop.wav") == "Amin"
    assert extract_type_hint("oneshots/snare.wav") == "oneshot"
    assert extract_instrument_hint("drums/closed_hihat.wav") == "hihat"
    assert extract_key_hint("ambient_pad.wav") is None


def test_legacy_v1_only_catalog_remains_compatible(tmp_path: Path) -> None:
    db_path = tmp_path / "catalog.db"
    out_path = tmp_path / "VALIDATION_REPORT.md"
    _create_legacy_v1_catalog(db_path)

    metrics = generate_report(db_path, out_path)

    assert metrics["samples"] == 2
    assert metrics["feature_rows"] == 2
    assert metrics["catalog_consistent"] is True
    assert metrics["valid_key_claims"] == 2
    assert metrics["v1_key_claims"] == 2
    assert metrics["v2_key_claims"] == 0
    assert metrics["v2_modeful"] == 0
    assert metrics["v2_root_only"] == 0
    assert metrics["invalid_key_claims"] == 0

    report = out_path.read_text(encoding="utf-8")
    assert "Catalog consistent: **YES**" in report
    assert "Valid key claims: **2**" in report
    assert "V1 key claims: **2**" in report
    assert "V2 key claims: **0**" in report
    assert "Invalid/unreadable key claims: **0**" in report
    assert "V1 key_conf evidence" in report
    assert "key_conf min / median / max: **0.780 / 0.800 / 0.820**" in report
    assert "key_conf below FL export gate 0.55: **0/2**" in report
    assert "Weak BPM labels: **2**" in report
    assert "match: **1**" in report
    assert "half_time: **1**" in report
    assert "Weak key labels: **2**" in report
    assert "Exact signature matches: **2/2**" in report
    assert "Loop/one-shot matches: **2/2**" in report
    assert "Instrument matches: **2/2**" in report
    assert "private-a.wav" not in report
    assert "private-b.wav" not in report
    assert "0.75" not in report  # Pearson must not appear
    assert "raw_top_score" not in report


def test_v2_modeful_and_root_only_are_counted_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "catalog.db"
    out_path = tmp_path / "out.md"
    _create_migrated_catalog_with_sample(db_path, sample_id=1, relpath="loops/Kick_120bpm_Cmaj_loop.wav")
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO samples (id, path, relpath, hash, hash_algorithm) "
            "VALUES (2, 'private-b.wav', 'loops/Pad_120bpm_G_loop.wav', ?, 'sha256')",
            ("b" * 64,),
        )
        connection.commit()
    finally:
        connection.close()

    previous = config_module.DB_PATH
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    _bind_db(db_path)
    try:
        from src.db import init_db

        init_db()
        write_key_analysis_v2_features(sample_id=1, result=_v2_result(root="C", mode="maj"))
        write_key_analysis_v2_features(sample_id=2, result=_v2_result(root="G", mode=None))
    finally:
        config_module.DB_PATH = previous

    metrics = generate_report(db_path, out_path)
    report = out_path.read_text(encoding="utf-8")

    assert metrics["valid_key_claims"] == 2
    assert metrics["v1_key_claims"] == 0
    assert metrics["v2_key_claims"] == 2
    assert metrics["v2_modeful"] == 1
    assert metrics["v2_root_only"] == 1
    assert metrics["invalid_key_claims"] == 0
    assert "V2 key claims: **2**" in report
    assert "V2 modeful: **1**" in report
    assert "V2 root-only / mode unresolved: **1**" in report
    assert "V1 key_conf evidence" not in report
    assert "key_conf min / median / max" not in report
    assert "0.75" not in report
    assert "raw_top_score" not in report
    assert "missing confidence" not in report.casefold()


def test_mixed_v1_v2_keeps_v1_conf_stats_unpolluted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "catalog.db"
    out_path = tmp_path / "out.md"
    _create_migrated_catalog_with_sample(
        db_path, sample_id=1, relpath="loops/Kick_128bpm_Am_loop.wav"
    )
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO samples (id, path, relpath, hash, hash_algorithm) "
            "VALUES (2, 'private-b.wav', 'oneshots/Snare_130bpm_Cmaj_oneshot.wav', ?, 'sha256')",
            ("b" * 64,),
        )
        connection.execute(
            """
            INSERT INTO features (
                sample_id, bpm, key, key_conf, class, pred_type,
                key_mode, key_analysis_contract_version
            ) VALUES (1, 128.2, 'Amin', 0.82, 'loop', 'Kick', 'min', NULL)
            """
        )
        connection.commit()
    finally:
        connection.close()

    previous = config_module.DB_PATH
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    _bind_db(db_path)
    try:
        from src.db import init_db

        init_db()
        write_key_analysis_v2_features(sample_id=2, result=_v2_result(root="C", mode="maj"))
    finally:
        config_module.DB_PATH = previous

    metrics = generate_report(db_path, out_path)
    report = out_path.read_text(encoding="utf-8")

    assert metrics["valid_key_claims"] == 2
    assert metrics["v1_key_claims"] == 1
    assert metrics["v2_key_claims"] == 1
    assert metrics["v2_modeful"] == 1
    assert metrics["invalid_key_claims"] == 0
    assert "V1 key_conf evidence" in report
    assert "key_conf min / median / max: **0.820 / 0.820 / 0.820**" in report
    assert "key_conf below FL export gate 0.55: **0/1**" in report
    assert "0.75" not in report


def test_unknown_and_malformed_and_stale_hybrid_are_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "catalog.db"
    out_path = tmp_path / "out.md"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE samples (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                relpath TEXT,
                hash TEXT,
                hash_algorithm TEXT
            );
            CREATE TABLE features (
                sample_id INTEGER PRIMARY KEY,
                bpm REAL,
                key TEXT,
                key_conf REAL,
                class TEXT,
                pred_type TEXT,
                key_mode TEXT,
                key_mode_evidence TEXT,
                key_analysis_contract_version INTEGER,
                key_root_evidence TEXT
            );
            """
        )
        connection.executemany(
            "INSERT INTO samples (id, path, relpath, hash, hash_algorithm) "
            "VALUES (?, ?, ?, ?, 'sha256')",
            [
                (1, "private-a.wav", "loops/Kick_120bpm_Cmaj_loop.wav", "a" * 64),
                (2, "private-b.wav", "loops/Pad_120bpm_Dmaj_loop.wav", "b" * 64),
                (3, "private-c.wav", "loops/Bass_120bpm_Emaj_loop.wav", "c" * 64),
                (4, "private-d.wav", "loops/Hat_120bpm_F_loop.wav", "d" * 64),
            ],
        )
        # unknown version
        connection.execute(
            """
            INSERT INTO features (
                sample_id, key, key_conf, key_mode, key_analysis_contract_version
            ) VALUES (1, 'Cmaj', NULL, 'maj', 99)
            """
        )
        # malformed V2 root evidence
        connection.execute(
            """
            INSERT INTO features (
                sample_id, key, key_conf, key_mode, key_mode_evidence,
                key_analysis_contract_version, key_root_evidence
            ) VALUES (
                2, 'Dmaj', NULL, 'maj', :mode_evidence, 2, :root_evidence
            )
            """,
            {
                "mode_evidence": json.dumps(_v2_result(root="D", mode="maj").mode_evidence),
                "root_evidence": json.dumps({"kind": "not-v2"}),
            },
        )
        connection.commit()
    finally:
        connection.close()

    previous = config_module.DB_PATH
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    _bind_db(db_path)
    try:
        from src.db import init_db

        init_db()
        write_key_analysis_v2_features(sample_id=3, result=_v2_result(root="E", mode="maj"))
        # stale hybrid: V1 rewrite leaving V2 metadata
        connection = sqlite3.connect(db_path)
        try:
            connection.execute(
                """
                UPDATE features
                SET key = 'Amin', key_conf = 0.71, key_mode = 'min'
                WHERE sample_id = 3
                """
            )
            # sample 4 has features but no key fields — valid V1 empty claim, not invalid
            connection.execute(
                "INSERT INTO features (sample_id, bpm) VALUES (4, 120.0)"
            )
            connection.commit()
        finally:
            connection.close()
    finally:
        config_module.DB_PATH = previous

    metrics = generate_report(db_path, out_path)
    report = out_path.read_text(encoding="utf-8")

    assert metrics["invalid_key_claims"] == 3
    assert metrics["valid_key_claims"] == 0
    assert metrics["v1_key_claims"] == 0
    assert metrics["v2_key_claims"] == 0
    assert "Invalid/unreadable key claims: **3**" in report
    assert "Exact signature matches: **0/3**" in report or "Exact signature matches: **0/" in report
    assert "private-a.wav" not in report
    assert "private-c.wav" not in report


def test_weak_labels_ignore_invalid_predictions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "catalog.db"
    out_path = tmp_path / "out.md"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE samples (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                relpath TEXT,
                hash TEXT,
                hash_algorithm TEXT
            );
            CREATE TABLE features (
                sample_id INTEGER PRIMARY KEY,
                bpm REAL,
                key TEXT,
                key_conf REAL,
                class TEXT,
                pred_type TEXT,
                key_mode TEXT,
                key_mode_evidence TEXT,
                key_analysis_contract_version INTEGER,
                key_root_evidence TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO samples (id, path, relpath, hash, hash_algorithm) "
            "VALUES (1, 'private-a.wav', 'loops/Kick_128bpm_Am_loop.wav', ?, 'sha256')",
            ("a" * 64,),
        )
        # Raw key would match Am, but unknown contract → fail closed / not a prediction
        connection.execute(
            """
            INSERT INTO features (
                sample_id, key, key_conf, key_mode, key_analysis_contract_version
            ) VALUES (1, 'Amin', NULL, 'min', 7)
            """
        )
        connection.commit()
    finally:
        connection.close()

    previous = config_module.DB_PATH
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    _bind_db(db_path)
    try:
        from src.db import init_db

        init_db()
    finally:
        config_module.DB_PATH = previous

    metrics = generate_report(db_path, out_path)
    report = out_path.read_text(encoding="utf-8")

    assert metrics["invalid_key_claims"] == 1
    assert metrics["valid_key_claims"] == 0
    assert metrics["key_weak_labels"] == 1
    assert "Root matches: **0/1**" in report
    assert "Exact signature matches: **0/1**" in report


def test_db_path_restored_after_success_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = tmp_path / "sentinel.db"
    report_db = tmp_path / "report.db"
    out_ok = tmp_path / "ok.md"
    out_fail = tmp_path / "fail.md"
    _create_legacy_v1_catalog(report_db)
    sentinel.write_bytes(b"")

    previous = config_module.DB_PATH
    config_module.DB_PATH = sentinel
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(sentinel))
    try:
        metrics = generate_report(report_db, out_ok)
        assert metrics["valid_key_claims"] == 2
        assert config_module.DB_PATH == sentinel

        with patch(
            "tools.validate_report.read_key_analysis_feature_rows",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                generate_report(report_db, out_fail)
        assert config_module.DB_PATH == sentinel
    finally:
        config_module.DB_PATH = previous


def test_generate_report_covers_project_meta_validation_contract(tmp_path: Path) -> None:
    """Compatibility alias for the legacy project-meta contract name."""

    test_legacy_v1_only_catalog_remains_compatible(tmp_path)
