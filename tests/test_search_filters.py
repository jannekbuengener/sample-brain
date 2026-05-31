from __future__ import annotations

from pathlib import Path

import pytest

import src.db as db_module
from src.config import set_db_path
from src.db import init_db, list_sample_tags, replace_sample_tags
from src.search_filters import (
    SearchFilters,
    key_matches_scale,
    resolve_filtered_sample_ids,
    sync_pred_type_tags,
)


@pytest.fixture
def filter_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "filters.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    import src.config as config_module

    config_module.DB_PATH = db_path
    init_db()

    engine = db_module.get_engine()
    with engine.begin() as conn:
        conn.execute(
            db_module.text(
                """
                INSERT INTO samples (id, path, hash, duration) VALUES
                    (1, '/kick.wav', 'hash-1', 0.5),
                    (2, '/snare.wav', 'hash-2', 1.5)
                """
            )
        )
        conn.execute(
            db_module.text(
                """
                INSERT INTO features (sample_id, bpm, key, pred_type, class) VALUES
                    (1, 128.0, 'Am', 'kick', 'percussive'),
                    (2, 90.0, 'C', 'snare', 'percussive')
                """
            )
        )
    replace_sample_tags(1, [("kick", "pred_type")])
    return db_path


class TestSearchFilters:
    def test_key_matches_scale_minor(self):
        assert key_matches_scale("Am", "minor")
        assert not key_matches_scale("C", "minor")

    def test_resolve_filtered_sample_ids_by_pred_type(self, filter_db):
        sample_ids = resolve_filtered_sample_ids(
            SearchFilters(pred_type="kick")
        )
        assert sample_ids == {1}

    def test_resolve_filtered_sample_ids_by_tag(self, filter_db):
        sample_ids = resolve_filtered_sample_ids(SearchFilters(tags=("kick",)))
        assert sample_ids == {1}

    def test_resolve_filtered_sample_ids_by_duration(self, filter_db):
        sample_ids = resolve_filtered_sample_ids(
            SearchFilters(min_duration=1.0, max_duration=2.0)
        )
        assert sample_ids == {2}

    def test_sync_pred_type_tags(self, filter_db):
        synced = sync_pred_type_tags()
        assert synced >= 1
        kick_tags = list_sample_tags(sample_id=1)
        assert any(row["tag"] == "kick" for row in kick_tags)
        snare_tags = list_sample_tags(sample_id=2)
        assert any(row["tag"] == "snare" for row in snare_tags)
