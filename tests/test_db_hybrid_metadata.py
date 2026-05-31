from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from src.db import ensure_features_pred_type_column, load_hybrid_metadata


@pytest.fixture
def legacy_features_engine():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE features (
                    sample_id INTEGER PRIMARY KEY,
                    bpm REAL,
                    key TEXT,
                    class TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO features (sample_id, bpm, key, class)
                VALUES (1, 128.0, 'Am', 'percussive')
                """
            )
        )
    return engine


def _feature_column_names(engine) -> set[str]:
    with engine.begin() as conn:
        cols = conn.execute(text("PRAGMA table_info(features)")).fetchall()
    return {column[1] for column in cols}


class TestLoadHybridMetadataLegacySchema:
    def test_load_hybrid_metadata_on_legacy_features_without_pred_type(
        self,
        legacy_features_engine,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr("src.db.get_engine", lambda: legacy_features_engine)

        result = load_hybrid_metadata([1])

        assert 1 in result
        assert result[1].sample_id == 1
        assert result[1].bpm == 128.0
        assert result[1].key == "Am"
        assert result[1].pred_type is None
        assert result[1].audio_class == "percussive"
        assert "pred_type" in _feature_column_names(legacy_features_engine)

    def test_ensure_features_pred_type_column_is_idempotent(
        self,
        legacy_features_engine,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr("src.db.get_engine", lambda: legacy_features_engine)

        ensure_features_pred_type_column()
        ensure_features_pred_type_column()

        assert "pred_type" in _feature_column_names(legacy_features_engine)
