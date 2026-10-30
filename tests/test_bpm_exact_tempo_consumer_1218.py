"""#1218 consumer precision: analysis → persistence → Browser → SYNC/Harmony."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from sqlalchemy import text

import src.config as config_module
import src.db as db_module
from src.analyze import extract_features
from src.session_grid import compute_sync_playback_rate
from src.workbench_catalog import load_catalog_samples
from src.workbench_qml import _qml_row


FRACTIONAL_BPMS = (127.37, 128.25, 132.47, 139.83)


def _use_db(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(path))
    config_module.DB_PATH = path
    config_module.set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(path)})


def _write_pulse_wav(path: Path, *, bpm: float, duration_sec: float = 12.0, sr: int = 44100) -> Path:
    """Deterministic pulse train; interval from integer sample period."""
    n_total = int(sr * duration_sec)
    y = np.zeros(n_total, dtype=np.float32)
    interval = max(1, int(round((60.0 / bpm) * sr)))
    pulse_n = max(1, int(0.005 * sr))
    t = np.linspace(0.0, 0.005, pulse_n, dtype=np.float32)
    pulse = 0.8 * np.sin(2.0 * np.pi * 800.0 * t) * (np.linspace(1.0, 0.0, pulse_n) ** 2)
    for i in range(n_total // interval):
        start = i * interval
        if start + pulse_n <= n_total:
            y[start : start + pulse_n] += pulse
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.clip(y, -1.0, 1.0), sr, subtype="PCM_16")
    return path


def test_fractional_bpm_persists_and_projects_to_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "catalog.db"
    _use_db(db_path, monkeypatch)
    engine = db_module.init_db()

    for index, bpm in enumerate(FRACTIONAL_BPMS, start=1):
        wav = _write_pulse_wav(tmp_path / f"exact_{bpm:.2f}.wav", bpm=bpm)
        feats = extract_features(wav, duration=12.0, bpm_normalization="none")
        assert feats is not None
        assert feats.bpm is not None
        assert abs(feats.bpm - bpm) <= 0.005
        assert round(feats.bpm, 2) == round(bpm, 2)

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO samples (id, path, relpath, size_bytes, duration, hash)
                    VALUES (:id, :path, :relpath, 4, 12.0, :hash)
                    """
                ),
                {
                    "id": index,
                    "path": str(wav),
                    "relpath": wav.name,
                    "hash": f"h{index}",
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO features (sample_id, bpm, key, key_conf, loudness, brightness)
                    VALUES (:sample_id, :bpm, NULL, NULL, NULL, NULL)
                    """
                ),
                {"sample_id": index, "bpm": feats.bpm},
            )

    # Reload from a fresh engine handle (roundtrip).
    config_module.set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    rows = load_catalog_samples(db_path)
    assert len(rows) == len(FRACTIONAL_BPMS)

    for row, expected in zip(
        sorted(rows, key=lambda r: r.bpm or 0.0),
        sorted(FRACTIONAL_BPMS),
        strict=True,
    ):
        assert row.bpm is not None
        assert abs(row.bpm - expected) <= 0.005
        assert round(row.bpm, 2) == round(expected, 2)
        wb = row.to_workbench_row()
        qml = _qml_row(wb)
        assert qml.bpm != "—"
        # Display may use :g formatting; hundredths must still match contract.
        assert round(float(qml.bpm), 2) == round(expected, 2)
        assert round(float(qml.bpm), 2) == round(row.bpm, 2)


def test_unknown_bpm_stays_unknown_through_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "catalog.db"
    _use_db(db_path, monkeypatch)
    engine = db_module.init_db()
    wav = tmp_path / "silence.wav"
    sf.write(wav, np.zeros(44100, dtype=np.float32), 44100, subtype="PCM_16")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO samples (id, path, relpath, size_bytes, duration, hash)
                VALUES (1, :path, 'silence.wav', 4, 1.0, 'h1')
                """
            ),
            {"path": str(wav)},
        )
        conn.execute(
            text(
                """
                INSERT INTO features (sample_id, bpm, key, key_conf, loudness, brightness)
                VALUES (1, NULL, NULL, NULL, NULL, NULL)
                """
            )
        )

    row = load_catalog_samples(db_path)[0]
    assert row.bpm is None
    qml = _qml_row(row.to_workbench_row())
    assert qml.bpm == "—"


def test_fractional_sync_ratio_not_integer_rounded() -> None:
    rate, status = compute_sync_playback_rate(132.0, 127.37, sync_enabled=True)
    assert status == "sync"
    assert rate == pytest.approx(132.0 / 127.37)
    assert rate != pytest.approx(132.0 / 127.0)


def test_sample_switch_browser_bpm_not_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "catalog.db"
    _use_db(db_path, monkeypatch)
    engine = db_module.init_db()
    values = (127.37, None, 139.83)
    with engine.begin() as conn:
        for index, bpm in enumerate(values, start=1):
            conn.execute(
                text(
                    """
                    INSERT INTO samples (id, path, relpath, size_bytes, duration, hash)
                    VALUES (:id, :path, :relpath, 4, 1.0, :hash)
                    """
                ),
                {
                    "id": index,
                    "path": str(tmp_path / f"s{index}.wav"),
                    "relpath": f"s{index}.wav",
                    "hash": f"h{index}",
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO features (sample_id, bpm, key, key_conf, loudness, brightness)
                    VALUES (:sample_id, :bpm, NULL, NULL, NULL, NULL)
                    """
                ),
                {"sample_id": index, "bpm": bpm},
            )

    qml_bpms = [_qml_row(r.to_workbench_row()).bpm for r in load_catalog_samples(db_path)]
    assert "127.37" in qml_bpms or any(
        b not in {"—", ""} and abs(float(b) - 127.37) < 1e-9 for b in qml_bpms if b != "—"
    )
    assert "—" in qml_bpms
    assert any(
        b != "—" and abs(float(b) - 139.83) < 1e-9 for b in qml_bpms
    )
