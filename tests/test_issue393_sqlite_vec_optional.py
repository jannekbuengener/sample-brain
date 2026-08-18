from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pytest

import src.db as db_module
from src.config import set_db_path
from src.db import init_db, insert_sample_embedding, upsert_embedding_model


@pytest.fixture
def test_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "issue393_test.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    import src.config as config_module

    config_module.DB_PATH = db_path
    init_db()
    model_id = upsert_embedding_model(
        provider="test",
        model_name="noop",
        model_version="1",
        embedding_dim=4,
        modality="audio+text",
    )
    engine = db_module.get_engine()
    with engine.begin() as conn:
        conn.execute(
            db_module.text(
                """
                INSERT INTO samples (id, path, hash) VALUES
                    (1, '/a.wav', 'hash-a'),
                    (2, '/b.wav', 'hash-b')
                """
            )
        )
    vectors = [
        np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32),
    ]
    for sample_id, vector, source_hash in (
        (1, vectors[0], "hash-a"),
        (2, vectors[1], "hash-b"),
    ):
        insert_sample_embedding(
            sample_id=sample_id,
            model_id=model_id,
            embedding=vector.tobytes(),
            embedding_format="float32",
            source_hash=source_hash,
        )
    return db_path, model_id, vectors


def test_search_and_vec_modules_importable_without_sqlite_vec(monkeypatch: pytest.MonkeyPatch):
    """Verify that src.search_backend and src.vec_index import without error when sqlite_vec is not installed."""
    monkeypatch.setitem(sys.modules, "sqlite_vec", None)

    # Force re-import or module loading check
    if "src.search_backend" in sys.modules:
        monkeypatch.delitem(sys.modules, "src.search_backend", raising=False)
    if "src.vec_index" in sys.modules:
        monkeypatch.delitem(sys.modules, "src.vec_index", raising=False)

    import src.search_backend as sb
    import src.vec_index as vi

    assert hasattr(sb, "get_search_backend")
    assert hasattr(vi, "rebuild_vec0_cache")


def test_numpy_backend_works_without_sqlite_vec(test_db, monkeypatch: pytest.MonkeyPatch):
    """Verify that NumPy search backend can be loaded and executed when sqlite_vec is missing."""
    monkeypatch.setitem(sys.modules, "sqlite_vec", None)

    from src.search_backend import get_search_backend

    _, model_id, vectors = test_db
    backend = get_search_backend("numpy")
    hits = backend.search(vectors[0], model_id, topk=2)

    assert len(hits) == 2
    assert hits[0].sample_id == 1


def test_sqlite_vec_operations_fail_closed_without_sqlite_vec(test_db, monkeypatch: pytest.MonkeyPatch):
    """Verify that sqlite-vec specific operations raise VecIndexUnavailableError when sqlite_vec is missing."""
    monkeypatch.setitem(sys.modules, "sqlite_vec", None)

    from src.search_backend import get_search_backend
    from src.vec_index import VecIndexUnavailableError, rebuild_vec0_cache

    db_path, model_id, vectors = test_db

    # Search backend fail closed
    vec_backend = get_search_backend("sqlite-vec")
    with pytest.raises(VecIndexUnavailableError) as exc_info:
        vec_backend.search(vectors[0], model_id, topk=1)
    assert "[ERROR] sqlite-vec unavailable" in str(exc_info.value)

    # Rebuild cache fail closed
    with pytest.raises(VecIndexUnavailableError) as exc_info:
        rebuild_vec0_cache(model_id, db_path=db_path)
    assert "[ERROR] sqlite-vec unavailable" in str(exc_info.value)
