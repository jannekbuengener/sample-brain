from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

import src.db as db_module
from src.config import set_db_path
from src.db import (
    get_vector_index_state,
    init_db,
    list_sample_tags,
    replace_sample_tags,
    upsert_embedding_model,
    upsert_vector_index_state,
)


@pytest.fixture
def vec_schema_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "vec_schema.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    import src.config as config_module

    config_module.DB_PATH = db_path
    init_db()
    model_id = upsert_embedding_model(
        provider="test",
        model_name="noop",
        model_version="1",
        embedding_dim=512,
        modality="audio+text",
    )
    return db_path, model_id


class TestVectorIndexStateSchema:
    def test_init_db_creates_vector_index_state(self, vec_schema_db):
        db_path, _model_id = vec_schema_db
        engine = db_module.get_engine()
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='vector_index_state'"
                )
            ).fetchone()
        assert row is not None
        assert db_path.exists()

    def test_upsert_vector_index_state_is_idempotent(self, vec_schema_db):
        _db_path, model_id = vec_schema_db
        upsert_vector_index_state(
            model_id=model_id,
            backend="sqlite-vec",
            embedding_dim=512,
            sample_count=10,
            vec_table_name="vec_sample_current",
            source_fingerprint="abc",
        )
        upsert_vector_index_state(
            model_id=model_id,
            backend="sqlite-vec",
            embedding_dim=512,
            sample_count=12,
            vec_table_name="vec_sample_current",
            source_fingerprint="def",
        )
        state = get_vector_index_state(model_id, "sqlite-vec")
        assert state is not None
        assert state["sample_count"] == 12
        assert state["source_fingerprint"] == "def"

    def test_vector_index_state_unique_per_model_backend(self, vec_schema_db):
        _db_path, model_id = vec_schema_db
        upsert_vector_index_state(
            model_id=model_id,
            backend="numpy",
            embedding_dim=512,
            sample_count=3,
        )
        upsert_vector_index_state(
            model_id=model_id,
            backend="sqlite-vec",
            embedding_dim=512,
            sample_count=4,
        )
        numpy_state = get_vector_index_state(model_id, "numpy")
        vec_state = get_vector_index_state(model_id, "sqlite-vec")
        assert numpy_state["sample_count"] == 3
        assert vec_state["sample_count"] == 4


class TestSampleTagsSchema:
    def test_init_db_creates_sample_tags(self, vec_schema_db):
        engine = db_module.get_engine()
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='sample_tags'"
                )
            ).fetchone()
        assert row is not None

    def test_replace_and_list_sample_tags(self, vec_schema_db):
        engine = db_module.get_engine()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO samples (id, path, hash) VALUES (1, '/a.wav', 'h1')"
                )
            )
        replace_sample_tags(
            1,
            [("kick", "pred_type"), ("drums", "class"), ("kick", "pred_type")],
        )
        tags = list_sample_tags(sample_id=1)
        assert len(tags) == 2
        assert {entry["tag"] for entry in tags} == {"kick", "drums"}

    def test_init_db_twice_is_idempotent(self, vec_schema_db):
        init_db()
        init_db()
        _db_path, model_id = vec_schema_db
        upsert_vector_index_state(
            model_id=model_id,
            backend="sqlite-vec",
            embedding_dim=512,
            sample_count=1,
        )
        assert get_vector_index_state(model_id, "sqlite-vec") is not None
