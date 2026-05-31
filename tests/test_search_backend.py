from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import src.db as db_module
from src.config import set_db_path
from src.db import init_db, insert_sample_embedding, upsert_embedding_model
from src.index import SearchHit, VectorIndex, search_index
from src.search_backend import (
    NumpySearchBackend,
    SearchBackendError,
    StaleVecCacheError,
    get_search_backend,
)
from src.vec_availability import is_sqlite_vec_available
from src.vec_index import rebuild_vec0_cache


def _install_search_index(monkeypatch: pytest.MonkeyPatch, index: VectorIndex) -> None:
    class Backend:
        def search(
            self,
            query_vector,
            model_id,
            topk,
            *,
            index_path=None,
            candidate_sample_ids=None,
        ):
            hits = search_index(query_vector, index, topk=topk)
            if candidate_sample_ids is None:
                return hits
            filtered = [hit for hit in hits if hit.sample_id in candidate_sample_ids]
            return filtered[:topk]

    monkeypatch.setattr("src.search.get_search_backend", lambda _name: Backend())


@pytest.fixture
def search_backend_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "search_backend.db"
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


class TestSearchBackendFactory:
    def test_get_search_backend_numpy(self):
        backend = get_search_backend("numpy")
        assert isinstance(backend, NumpySearchBackend)

    def test_get_search_backend_invalid(self):
        with pytest.raises(ValueError):
            get_search_backend("faiss")


class TestNumpySearchBackend:
    def test_search_returns_ranked_hits(self, search_backend_db):
        _, model_id, vectors = search_backend_db
        backend = NumpySearchBackend()
        hits = backend.search(vectors[0], model_id, topk=2)
        assert hits[0].sample_id == 1
        assert hits[0].score > hits[1].score


@pytest.mark.skipif(
    not is_sqlite_vec_available(),
    reason="sqlite-vec optional extra not installed in this environment",
)
class TestSqliteVecSearchBackend:
    def test_sqlite_vec_matches_numpy_top1(self, search_backend_db):
        db_path, model_id, vectors = search_backend_db
        rebuild_vec0_cache(model_id, db_path=db_path)

        numpy_hits = NumpySearchBackend().search(vectors[0], model_id, topk=1)
        sqlite_hits = get_search_backend("sqlite-vec").search(
            vectors[0], model_id, topk=1
        )
        assert numpy_hits[0].sample_id == sqlite_hits[0].sample_id

    def test_stale_cache_error_when_state_missing(self, search_backend_db):
        _, model_id, vectors = search_backend_db
        with pytest.raises(StaleVecCacheError):
            get_search_backend("sqlite-vec").search(vectors[0], model_id, topk=1)

    def test_rejects_index_path(self, search_backend_db):
        db_path, model_id, vectors = search_backend_db
        rebuild_vec0_cache(model_id, db_path=db_path)
        with pytest.raises(SearchBackendError):
            get_search_backend("sqlite-vec").search(
                vectors[0],
                model_id,
                topk=1,
                index_path="legacy.npz",
            )
