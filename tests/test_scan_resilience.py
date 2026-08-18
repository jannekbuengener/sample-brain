from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

import src.config as config_module
import src.db as db_module
import src.scan as scan_module
from src.config import set_db_path
from tests.audio_fixtures import write_sine_wav


@pytest.fixture
def isolated_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "catalog.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    config_module.DB_PATH = db_path
    db_module.init_db()
    return db_path


def test_scan_skips_unreadable_file_and_continues(
    tmp_path: Path,
    isolated_catalog: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    samples_dir = tmp_path / "samples"
    bad = write_sine_wav(
        samples_dir / "bad.wav", duration_sec=0.1, frequency_hz=220.0
    )
    good = write_sine_wav(
        samples_dir / "good.wav", duration_sec=0.1, frequency_hz=440.0
    )
    real_compute_file_hash = scan_module.compute_file_hash

    monkeypatch.setattr(
        scan_module,
        "iter_audio_files_stream",
        lambda _roots: iter((bad, good)),
    )

    def flaky_hash(path: Path) -> dict:
        if Path(path) == bad:
            raise PermissionError("simulated unreadable file")
        return real_compute_file_hash(path)

    monkeypatch.setattr(scan_module, "compute_file_hash", flaky_hash)

    scan_module.run_scan(custom_roots=[samples_dir], show_every=0)

    with db_module.get_engine().connect() as conn:
        rows = conn.execute(text("SELECT path FROM samples ORDER BY path")).fetchall()
    assert [row[0] for row in rows] == [str(good)]


def test_scan_hashes_before_opening_write_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = write_sine_wav(
        tmp_path / "sample.wav", duration_sec=0.1, frequency_hz=440.0
    )

    class FakeConnection:
        def __init__(self) -> None:
            self.rows: list[dict] = []

        def execute(self, _statement, params) -> None:
            if isinstance(params, list):
                self.rows.extend(params)
            else:
                self.rows.append(params)

    class BeginContext:
        def __init__(self, engine: "FakeEngine") -> None:
            self.engine = engine

        def __enter__(self) -> FakeConnection:
            self.engine.in_transaction = True
            return self.engine.connection

        def __exit__(self, *_exc) -> None:
            self.engine.in_transaction = False

    class FakeEngine:
        def __init__(self) -> None:
            self.in_transaction = False
            self.connection = FakeConnection()
            self.begin_count = 0

        def begin(self) -> BeginContext:
            self.begin_count += 1
            return BeginContext(self)

    engine = FakeEngine()
    monkeypatch.setattr(scan_module, "init_db", lambda: engine)
    monkeypatch.setattr(
        scan_module,
        "iter_audio_files_stream",
        lambda _roots: iter((sample,)),
    )
    monkeypatch.setattr(scan_module, "safe_audio_info", lambda _path: (44100, 1, 0.1))

    def assert_no_write_transaction(_path: Path) -> dict:
        assert engine.in_transaction is False
        return {"algorithm": "sha256", "value": "a" * 64}

    monkeypatch.setattr(scan_module, "compute_file_hash", assert_no_write_transaction)

    scan_module.run_scan(custom_roots=[tmp_path], show_every=0, batch_size=10)

    assert engine.begin_count == 1
    assert len(engine.connection.rows) == 1
