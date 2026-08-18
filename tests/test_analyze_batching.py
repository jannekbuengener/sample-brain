from __future__ import annotations

from pathlib import Path

import src.analyze as analyze_module
from src.analyze import Features


class _FakeResult:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return list(self._rows)


class _FakeConnection:
    def __init__(self, engine: "_FakeEngine") -> None:
        self.engine = engine

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        if "SELECT" in sql.upper():
            self.engine.select_calls.append((sql, dict(params)))
            last_id = int(params.get("last_id", 0))
            batch_size = int(params.get("batch_size", len(self.engine.rows) or 1))
            rows = [row for row in self.engine.rows if row[0] > last_id][:batch_size]
            return _FakeResult(rows)
        self.engine.write_calls.append((sql, params))
        return _FakeResult([])


class _Context:
    def __init__(self, engine: "_FakeEngine", *, write: bool) -> None:
        self.engine = engine
        self.write = write

    def __enter__(self) -> _FakeConnection:
        if self.write:
            self.engine.in_write_transaction = True
        return _FakeConnection(self.engine)

    def __exit__(self, *_exc) -> None:
        if self.write:
            self.engine.in_write_transaction = False


class _FakeEngine:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows
        self.in_write_transaction = False
        self.select_calls: list[tuple[str, dict]] = []
        self.write_calls: list[tuple[str, object]] = []

    def connect(self) -> _Context:
        return _Context(self, write=False)

    def begin(self) -> _Context:
        return _Context(self, write=True)


def _features() -> Features:
    return Features(
        bpm=128.0,
        key="Amin",
        key_conf=0.8,
        loudness=-12.0,
        brightness=2000.0,
        mfcc_mean=None,
        mfcc_std=None,
        chroma_mean=None,
        chroma_std=None,
        clazz="loop",
    )


def test_run_analyze_extracts_audio_outside_write_transaction(monkeypatch) -> None:
    engine = _FakeEngine([(1, "sample.wav", 2.0, None)])
    monkeypatch.setattr(analyze_module, "init_db", lambda: engine)

    def checked_extract(path: Path, duration: float | None, bpm_normalization: str = "none"):
        assert path == Path("sample.wav")
        assert duration == 2.0
        assert engine.in_write_transaction is False
        return _features()

    monkeypatch.setattr(analyze_module, "extract_features", checked_extract)

    analyze_module.run_analyze(only_missing=True)

    assert len(engine.write_calls) == 1


def test_run_analyze_pages_catalog_and_filters_missing_in_sql(monkeypatch) -> None:
    engine = _FakeEngine(
        [
            (1, "one.wav", 1.0, None),
            (2, "two.wav", 1.0, None),
        ]
    )
    monkeypatch.setattr(analyze_module, "init_db", lambda: engine)
    monkeypatch.setattr(analyze_module, "extract_features", lambda *_args, **_kwargs: _features())

    analyze_module.run_analyze(only_missing=True, batch_size=1)

    assert len(engine.select_calls) == 3  # ids 1, 2, then empty page
    for sql, params in engine.select_calls:
        assert "s.id > :last_id" in sql
        assert "LIMIT :batch_size" in sql
        assert "f.sample_id IS NULL" in sql
        assert params["batch_size"] == 1
    assert len(engine.write_calls) == 2
