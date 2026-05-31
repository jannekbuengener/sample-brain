from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import sqlite3

import src.db as db_module
from src.config import set_db_path
from src.db import (
    get_vector_index_state,
    init_db,
    insert_sample_embedding,
    upsert_embedding_model,
)
from src.index import decode_embedding_blob
from src.vec_availability import is_sqlite_vec_available
from src.vec_index import (
    VEC_SAMPLE_CURRENT_TABLE,
    VecIndexUnavailableError,
    compute_source_fingerprint,
    open_vec_connection,
    rebuild_vec0_cache,
    require_sqlite_vec,
)


def _make_vector(seed: int, dim: int = 8) -> np.ndarray:
    rng = np.random.default_rng(seed)
    vector = rng.standard_normal(dim, dtype=np.float32)
    return vector / (np.linalg.norm(vector) or 1.0)


@pytest.fixture
def vec_rebuild_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "vec_rebuild.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    init_db()

    model_id = upsert_embedding_model(
        provider="test",
        model_name="noop",
        model_version="1",
        embedding_dim=8,
        modality="audio+text",
    )

    engine = db_module.get_engine()
    with engine.begin() as conn:
        conn.execute(
            db_module.text(
                """
                INSERT INTO samples (id, path, hash) VALUES
                    (1, '/a.wav', 'hash-a'),
                    (2, '/b.wav', 'hash-b'),
                    (3, '/stale.wav', 'hash-new')
                """
            )
        )

    for sample_id, seed, source_hash in (
        (1, 1, "hash-a"),
        (2, 2, "hash-b"),
        (3, 3, "hash-old"),
    ):
        vector = _make_vector(seed, dim=8)
        insert_sample_embedding(
            sample_id=sample_id,
            model_id=model_id,
            embedding=vector.tobytes(),
            embedding_format="float32",
            source_hash=source_hash,
        )

    return db_path, model_id


class TestVecIndexHelpers:
    def test_compute_source_fingerprint_is_order_stable(self):
        rows = [(2, "b"), (1, "a")]
        assert compute_source_fingerprint(rows) == compute_source_fingerprint(
            [(1, "a"), (2, "b")]
        )

    def test_require_sqlite_vec_raises_when_unavailable(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "src.vec_index.probe_sqlite_vec",
            lambda: type(
                "Report",
                (),
                {"available": False, "reason": "not_installed"},
            )(),
        )
        monkeypatch.setattr(
            "src.vec_index.format_availability_message",
            lambda _report: "[ERROR] sqlite-vec unavailable",
        )
        with pytest.raises(VecIndexUnavailableError):
            require_sqlite_vec()


@pytest.mark.skipif(
    not is_sqlite_vec_available(),
    reason="sqlite-vec optional extra not installed in this environment",
)
class TestRebuildVec0Cache:
    def test_rebuild_vec0_cache_is_idempotent(self, vec_rebuild_db):
        db_path, model_id = vec_rebuild_db
        first = rebuild_vec0_cache(model_id, db_path=db_path)
        second = rebuild_vec0_cache(model_id, db_path=db_path)
        assert first.sample_count == 2
        assert second.sample_count == 2
        assert first.source_fingerprint == second.source_fingerprint

        state = get_vector_index_state(model_id, "sqlite-vec")
        assert state is not None
        assert state["sample_count"] == 2
        assert state["vec_table_name"] == VEC_SAMPLE_CURRENT_TABLE

    def test_rebuild_skips_stale_embeddings(self, vec_rebuild_db):
        db_path, model_id = vec_rebuild_db
        result = rebuild_vec0_cache(model_id, db_path=db_path)
        assert result.sample_count == 2

        conn = open_vec_connection(db_path)
        try:
            row = conn.execute(
                f"SELECT COUNT(*) FROM {VEC_SAMPLE_CURRENT_TABLE}"
            ).fetchone()
        finally:
            conn.close()
        assert row[0] == 2

    def test_rebuilt_vectors_are_normalized(self, vec_rebuild_db):
        db_path, model_id = vec_rebuild_db
        rebuild_vec0_cache(model_id, db_path=db_path)

        engine = db_module.get_engine()
        with engine.begin() as conn:
            blob = conn.execute(
                db_module.text(
                    """
                    SELECT embedding FROM sample_embeddings
                    WHERE sample_id = 1 AND model_id = :model_id
                    """
                ),
                {"model_id": model_id},
            ).fetchone()[0]

        original = decode_embedding_blob(blob, 8)
        conn = open_vec_connection(db_path)
        try:
            conn.row_factory = sqlite3.Row
            match_blob = original / (np.linalg.norm(original) or 1.0)
            import sqlite_vec

            row = conn.execute(
                f"""
                SELECT rowid, distance
                FROM {VEC_SAMPLE_CURRENT_TABLE}
                WHERE embedding MATCH ?
                ORDER BY distance
                LIMIT 1
                """,
                (sqlite_vec.serialize_float32(match_blob.astype(np.float32)),),
            ).fetchone()
        finally:
            conn.close()
        assert row["rowid"] == 1
        assert row["distance"] == pytest.approx(0.0, abs=1e-5)
