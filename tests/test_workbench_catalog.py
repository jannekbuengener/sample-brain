from __future__ import annotations

from pathlib import Path

import pytest

import src.config as config_module
import src.db as db_module
from src.config import set_db_path
from src.db import init_db
from src.workbench_catalog import (
    CATALOG_LIBRARY_FOLDER_LABEL,
    CATALOG_SOURCE,
    catalog_available,
    catalog_db_path,
    count_catalog_samples,
    format_catalog_load_status,
    load_catalog_samples,
)


@pytest.fixture
def catalog_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "catalog.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    config_module.DB_PATH = db_path
    init_db()

    engine = db_module.get_engine()
    with engine.begin() as conn:
        conn.execute(
            db_module.text(
                """
                INSERT INTO samples (id, path, relpath, size_bytes, duration, hash) VALUES
                    (1, '/samples/kick.wav', 'kick.wav', 1024, 0.5, 'hash-kick'),
                    (2, '/samples/snare.wav', 'snare.wav', 2048, 1.0, 'hash-snare'),
                    (3, '/samples/unanalyzed.wav', 'unanalyzed.wav', 512, 0.2, 'hash-none')
                """
            )
        )
        conn.execute(
            db_module.text(
                """
                INSERT INTO features
                    (sample_id, bpm, key, key_conf, loudness, brightness, class, pred_type)
                VALUES
                    (1, 128.0, 'Am', 0.9, -12.0, 0.4, 'percussive', 'kick'),
                    (2, 90.0, 'C', 0.8, -10.0, 0.5, 'percussive', 'snare')
                """
            )
        )
    return db_path


class TestCatalogDbPath:
    def test_defaults_to_config_db_path(self, catalog_db: Path):
        assert catalog_db_path() == catalog_db

    def test_explicit_path_override(self, tmp_path: Path):
        explicit = tmp_path / "other.db"
        assert catalog_db_path(explicit) == explicit.resolve()


class TestCatalogAvailable:
    def test_true_for_seeded_catalog(self, catalog_db: Path):
        assert catalog_available(catalog_db) is True

    def test_false_for_missing_file(self, tmp_path: Path):
        assert catalog_available(tmp_path / "missing.db") is False

    def test_false_for_empty_file(self, tmp_path: Path):
        empty = tmp_path / "empty.db"
        empty.write_bytes(b"")
        assert catalog_available(empty) is False


class TestLoadCatalogSamples:
    def test_loads_mapped_fields(self, catalog_db: Path):
        rows = load_catalog_samples(catalog_db)
        assert len(rows) == 3

        kick = next(row for row in rows if row.path.endswith("kick.wav"))
        assert kick.display_name == "kick"
        assert kick.relative_path == "kick.wav"
        assert kick.bpm == 128.0
        assert kick.key == "Am"
        assert kick.sample_class == "percussive"
        assert kick.pred_type == "kick"
        assert kick.status == "ok"
        assert kick.source == CATALOG_SOURCE

    def test_pending_without_features(self, catalog_db: Path):
        rows = load_catalog_samples(catalog_db)
        pending = next(row for row in rows if row.path.endswith("unanalyzed.wav"))
        assert pending.status == "pending"
        assert pending.bpm is None
        assert pending.pred_type is None

    def test_to_workbench_row_marks_readonly(self, catalog_db: Path):
        row = load_catalog_samples(catalog_db)[0].to_workbench_row()
        assert row.details["source"] == CATALOG_SOURCE
        assert row.details["catalog_readonly"] is True
        assert row.details["library_folder"] == CATALOG_LIBRARY_FOLDER_LABEL

    def test_missing_db_returns_empty(self, tmp_path: Path):
        assert load_catalog_samples(tmp_path / "nope.db") == []

    def test_limit(self, catalog_db: Path):
        rows = load_catalog_samples(catalog_db, limit=1)
        assert len(rows) == 1

    def test_negative_limit_raises(self, catalog_db: Path):
        with pytest.raises(ValueError, match="non-negative"):
            load_catalog_samples(catalog_db, limit=-1)

    def test_filter_haystack_includes_catalog_folder(self, catalog_db: Path):
        from src.workbench_controller import filter_workbench_rows

        rows = [r.to_workbench_row() for r in load_catalog_samples(catalog_db)]
        filtered = filter_workbench_rows(rows, "catalog")
        assert len(filtered) == 3


class TestCountCatalogSamples:
    def test_count_matches_rows(self, catalog_db: Path):
        assert count_catalog_samples(catalog_db) == 3

    def test_missing_db_returns_zero(self, tmp_path: Path):
        assert count_catalog_samples(tmp_path / "nope.db") == 0


class TestFormatCatalogLoadStatus:
    def test_all_loaded_no_limit_hint(self):
        msg = format_catalog_load_status(3, 3)
        assert "3" in msg
        assert "read-only" in msg.lower()
        assert "Limit aktiv" not in msg

    def test_truncated_shows_total_and_limit(self):
        msg = format_catalog_load_status(500, 12000, limit=5000)
        assert "500" in msg
        assert "12000" in msg
        assert "Limit aktiv" in msg


class TestCatalogReadonlyGuards:
    def test_is_catalog_readonly_row(self, catalog_db: Path):
        from src.workbench_controller import is_catalog_readonly_row

        row = load_catalog_samples(catalog_db)[0].to_workbench_row()
        assert is_catalog_readonly_row(row) is True

    def test_catalog_row_display_name_prefix(self, catalog_db: Path):
        from src.workbench_controller import catalog_row_display_name

        row = load_catalog_samples(catalog_db)[0].to_workbench_row()
        assert catalog_row_display_name(row).startswith("⧉ ")

    def test_cache_display_name_unprefixed(self) -> None:
        from src.workbench_controller import WorkbenchRow, catalog_row_display_name

        row = WorkbenchRow(
            display_name="kick",
            relative_path="kick.wav",
            path="/samples/kick.wav",
            bpm=120.0,
            key="C",
            key_conf=0.9,
            loudness=-10.0,
            brightness=0.5,
            sample_class="perc",
            pred_type="kick",
            status="ok",
        )
        assert catalog_row_display_name(row) == "kick"

    def test_append_catalog_readonly_status_hint(self):
        from src.workbench_controller import (
            CATALOG_READONLY_STATUS_HINT,
            append_catalog_readonly_status_hint,
        )

        base = "Catalog-Samples: 3 geladen (read-only)."
        msg = append_catalog_readonly_status_hint(base)
        assert CATALOG_READONLY_STATUS_HINT in msg
        assert append_catalog_readonly_status_hint(msg) == msg

    def test_cache_row_is_not_catalog_readonly(self) -> None:
        from src.workbench_controller import WorkbenchRow, is_catalog_readonly_row

        row = WorkbenchRow(
            display_name="kick",
            relative_path="kick.wav",
            path="/samples/kick.wav",
            bpm=120.0,
            key="C",
            key_conf=0.9,
            loudness=-10.0,
            brightness=0.5,
            sample_class="perc",
            pred_type="kick",
            status="ok",
        )
        assert is_catalog_readonly_row(row) is False

    def test_load_catalog_rows_controller(self, catalog_db: Path):
        from src.workbench_controller import load_catalog_rows

        rows = load_catalog_rows(catalog_path=catalog_db)
        assert len(rows) == 3
        assert all(row.details.get("catalog_readonly") for row in rows)

    def test_sort_catalog_rows_stable(self, catalog_db: Path):
        from src.workbench_controller import load_catalog_rows, sort_workbench_rows

        rows = load_catalog_rows(catalog_path=catalog_db)
        sorted_rows = sort_workbench_rows(rows, "name")
        names = [row.display_name for row in sorted_rows]
        assert names == sorted(names, key=str.casefold)
