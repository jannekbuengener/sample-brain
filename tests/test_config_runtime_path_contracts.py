from __future__ import annotations

from pathlib import Path

from src.config import DEFAULT_DB_PATH, PROJECT_ROOT, set_db_path


def test_set_db_path_uses_default_when_no_profile_or_env():
    resolved = set_db_path(profile_db_path=None, env={})
    assert resolved == DEFAULT_DB_PATH


def test_set_db_path_uses_env_override_when_profile_missing(tmp_path: Path):
    env_path = tmp_path / "env" / "catalog.db"
    resolved = set_db_path(
        profile_db_path=None, env={"SAMPLE_BRAIN_DB_PATH": str(env_path)}
    )
    assert resolved == env_path.resolve()


def test_set_db_path_prefers_profile_path_over_env(tmp_path: Path):
    profile_path = tmp_path / "profile" / "catalog.db"
    env_path = tmp_path / "env" / "catalog.db"
    resolved = set_db_path(
        profile_db_path=str(profile_path),
        env={"SAMPLE_BRAIN_DB_PATH": str(env_path)},
    )
    assert resolved == profile_path.resolve()


def test_set_db_path_resolves_relative_profile_path():
    resolved = set_db_path(profile_db_path="custom/catalog.db", env={})
    assert resolved == (PROJECT_ROOT / "custom/catalog.db").resolve()
