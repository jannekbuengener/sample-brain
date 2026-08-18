from __future__ import annotations

import sqlite3
from pathlib import Path

from tools.validate_report import (
    classify_bpm_match,
    extract_bpm_hint,
    extract_instrument_hint,
    extract_key_hint,
    extract_type_hint,
    generate_report,
)


def _create_catalog(path: Path) -> None:
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


def test_weak_label_helpers_are_conservative() -> None:
    assert extract_bpm_hint("loops/Kick_128bpm_Am_loop.wav") == 128.0
    assert classify_bpm_match(128.2, 128.0) == "match"
    assert classify_bpm_match(65.0, 130.0) == "half_time"
    assert extract_key_hint("Kick_128bpm_Am_loop.wav") == "Amin"
    assert extract_type_hint("oneshots/snare.wav") == "oneshot"
    assert extract_instrument_hint("drums/closed_hihat.wav") == "hihat"
    assert extract_key_hint("ambient_pad.wav") is None


def test_generate_report_covers_project_meta_validation_contract(tmp_path: Path) -> None:
    db_path = tmp_path / "catalog.db"
    out_path = tmp_path / "VALIDATION_REPORT.md"
    _create_catalog(db_path)

    metrics = generate_report(db_path, out_path)

    assert metrics["samples"] == 2
    assert metrics["feature_rows"] == 2
    assert metrics["catalog_consistent"] is True

    report = out_path.read_text(encoding="utf-8")
    assert "Catalog consistent: **YES**" in report
    assert "Weak BPM labels: **2**" in report
    assert "match: **1**" in report
    assert "half_time: **1**" in report
    assert "Weak key labels: **2**" in report
    assert "Exact signature matches: **2/2**" in report
    assert "Loop/one-shot matches: **2/2**" in report
    assert "Instrument matches: **2/2**" in report
    assert "private-a.wav" not in report
    assert "private-b.wav" not in report
