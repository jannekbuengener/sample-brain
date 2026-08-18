from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf
from sqlalchemy import create_engine, text

import src.config as config_module
import src.db as db_module
from src.analyze import SHORT_AUDIO_QUALITY_NOTE, extract_features, run_analyze
from src.key_signature import parse_key_signature
from tests.audio_fixtures import (
    write_key_audio_wav,
    write_major_chord_wav,
    write_major_minor_blend_wav,
    write_root_fifth_wav,
    write_sine_wav,
)


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


def _write_bass_dominant_c_major(path: Path, *, sr: int = 44100) -> Path:
    """C-major material with a deliberately dominant low G bass component."""
    duration_sec = 2.0
    n = int(sr * duration_sec)
    t = np.linspace(0.0, duration_sec, n, endpoint=False, dtype=np.float32)
    c = 261.63
    e = c * 2.0 ** (4.0 / 12.0)
    g = c * 2.0 ** (7.0 / 12.0)
    low_g = g / 2.0
    wave = (
        0.75 * np.sin(2.0 * np.pi * low_g * t)
        + 0.18 * np.sin(2.0 * np.pi * c * t)
        + 0.18 * np.sin(2.0 * np.pi * e * t)
        + 0.18 * np.sin(2.0 * np.pi * g * t)
    )
    peak = float(np.max(np.abs(wave))) or 1.0
    sf.write(path, (0.8 * wave / peak).astype(np.float32), sr, subtype="PCM_16")
    return path


def test_key_quality_baseline_records_current_bass_dominance_weakness(
    tmp_path: Path,
) -> None:
    tonal_cases = [
        (write_key_audio_wav(tmp_path / "cmaj.wav", frequency_hz=261.63, mode="maj"), "C", "maj"),
        (write_key_audio_wav(tmp_path / "emin.wav", frequency_hz=329.63, mode="min"), "E", "min"),
        (write_key_audio_wav(tmp_path / "amaj.wav", frequency_hz=440.00, mode="maj"), "A", "maj"),
        (_write_bass_dominant_c_major(tmp_path / "bass_dominant_cmaj.wav"), "C", "maj"),
    ]
    ambiguous = [
        write_sine_wav(tmp_path / "single_c.wav", duration_sec=2.0, frequency_hz=261.63),
        write_root_fifth_wav(tmp_path / "power_c.wav", frequency_hz=261.63),
        write_major_minor_blend_wav(tmp_path / "blend_c.wav", frequency_hz=261.63),
    ]

    outcomes: list[tuple[str | None, str | None]] = []
    root_correct = mode_correct = combined_correct = 0
    for path, expected_root, expected_mode in tonal_cases:
        feats = extract_features(path, 2.0)
        assert feats is not None
        parsed = parse_key_signature(feats.key)
        root = parsed.root if parsed is not None else None
        outcomes.append((root, feats.key_mode))
        root_correct += int(root == expected_root)
        mode_correct += int(feats.key_mode == expected_mode)
        combined_correct += int(root == expected_root and feats.key_mode == expected_mode)

    abstain_correct = 0
    for path in ambiguous:
        feats = extract_features(path, 2.0)
        assert feats is not None
        abstain_correct += int(feats.key_mode is None)

    assert root_correct == 3
    assert mode_correct == 3
    assert combined_correct == 3
    assert abstain_correct == 3
    assert outcomes[:3] == [("C", "maj"), ("E", "min"), ("A", "maj")]
    assert outcomes[3] == ("G", None)
