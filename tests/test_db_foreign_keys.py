from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src import config
from src.db import init_db


def test_sqlite_foreign_keys_are_enabled_and_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "catalog.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)

    engine = init_db()

    with engine.connect() as conn:
        enabled = conn.execute(text("PRAGMA foreign_keys")).scalar_one()
    assert enabled == 1

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO sample_tags (sample_id, tag, source) "
                    "VALUES (:sample_id, :tag, :source)"
                ),
                {"sample_id": 999999, "tag": "orphan", "source": "test"},
            )
