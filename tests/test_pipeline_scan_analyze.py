from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

import src.db as db_module
from src.analyze import run_analyze
from src.scan import run_scan
from tests.audio_fixtures import write_sine_wav


@pytest.fixture
def isolated_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "catalog.db"
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    return tmp_path, db_path


def test_scan_registers_synthetic_wav(isolated_catalog: tuple[Path, Path]):
    tmp_path, db_path = isolated_catalog
    samples_dir = tmp_path / "samples"
    wav_path = write_sine_wav(
        samples_dir / "tone.wav",
        duration_sec=0.5,
        frequency_hz=440.0,
    )

    run_scan(custom_roots=[samples_dir], limit=1)

    with db_module.get_engine().begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT path, hash, samplerate, channels, duration
                FROM samples
                ORDER BY id
                LIMIT 1
                """
            )
        ).fetchone()

    assert row is not None
    assert row[0] == str(wav_path)
    assert row[1] is not None and len(row[1]) > 0
    assert row[2] == 44100
    assert row[3] == 1
    assert row[4] is not None and row[4] > 0
    assert db_path.parent == tmp_path


def test_analyze_writes_features_for_scanned_sample(isolated_catalog: tuple[Path, Path]):
    tmp_path, db_path = isolated_catalog
    samples_dir = tmp_path / "samples"
    write_sine_wav(
        samples_dir / "tone.wav",
        duration_sec=0.5,
        frequency_hz=440.0,
    )

    run_scan(custom_roots=[samples_dir], limit=1)
    run_analyze(only_missing=True)

    with db_module.get_engine().begin() as conn:
        sample_row = conn.execute(
            text("SELECT id FROM samples ORDER BY id LIMIT 1")
        ).fetchone()
        features_row = conn.execute(
            text(
                'SELECT sample_id, "class" FROM features ORDER BY sample_id LIMIT 1'
            )
        ).fetchone()

    assert sample_row is not None
    assert features_row is not None
    assert features_row[0] == sample_row[0]
    assert features_row[1] in {"oneshot", "loop"}
    assert db_path.parent == tmp_path
