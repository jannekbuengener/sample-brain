from __future__ import annotations

from pathlib import Path

import pytest

import src.db as db_module
from src.config import set_db_path
from src.db import init_db
from src.db_doctor import run_db_doctor
from src.vec_availability import is_sqlite_vec_available


@pytest.fixture
def doctor_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "doctor.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    import src.config as config_module

    config_module.DB_PATH = db_path
    init_db()
    return db_path


def test_db_doctor_reports_ok(doctor_db):
    report = run_db_doctor()
    assert report.quick_check_ok
    assert report.foreign_keys_ok
    assert report.db_path.endswith("doctor.db")


@pytest.mark.skipif(
    not is_sqlite_vec_available(),
    reason="sqlite-vec optional extra not installed in this environment",
)
def test_vec_benchmark_mini(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    work_dir = tmp_path / "bench"
    monkeypatch.chdir(tmp_path)
    from src.benchmark_vec import run_vec_benchmark

    results = run_vec_benchmark(sample_counts=[200], work_dir=work_dir)
    assert len(results) == 1
    assert results[0].sample_count == 200
    assert results[0].warm_p95_ms >= 0.0
    assert 0.0 <= results[0].overlap_k10 <= 1.0


@pytest.mark.skipif(
    not is_sqlite_vec_available(),
    reason="sqlite-vec optional extra not installed in this environment",
)
def test_vec_benchmark_mini_int8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    work_dir = tmp_path / "bench-int8"
    monkeypatch.chdir(tmp_path)
    from src.benchmark_vec import run_vec_benchmark

    results = run_vec_benchmark(
        sample_counts=[200], quantization="int8", work_dir=work_dir
    )
    assert len(results) == 1
    assert results[0].sample_count == 200
    assert results[0].warm_p95_ms >= 0.0
    assert results[0].warm_p99_ms >= 0.0
    assert 0.0 <= results[0].overlap_k10 <= 1.0
    assert 0.0 <= results[0].precision_at_1 <= 1.0
