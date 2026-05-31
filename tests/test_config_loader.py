from __future__ import annotations
from pathlib import Path

import pytest
import yaml

from src.config_loader import (
    ConfigError,
    _deep_merge,
    _parse_roots,
    load_profiles,
    resolve_profile,
)


def _write_yaml(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return path


def test_deep_merge_merges_nested_dicts():
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"c": 99}}
    result = _deep_merge(base, override)
    assert result == {"a": 1, "b": {"c": 99, "d": 3}}


def test_parse_roots_splits_semicolon_values():
    result = _parse_roots("<ROOT1>;<ROOT2>")
    assert result == ["<ROOT1>", "<ROOT2>"]


def test_load_profiles_reads_example_without_local(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {
                    "embedding": {"backend": "noop"},
                },
            },
        },
    )
    profiles = load_profiles(example_path=example, local_path=None)
    assert "default" in profiles
    assert profiles["default"]["embedding"]["backend"] == "noop"


def test_load_profiles_merges_local_over_example(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {
                    "export": {"max_tags": 5},
                    "embedding": {"backend": "noop"},
                },
            },
        },
    )
    local = _write_yaml(
        tmp_path / "local.yaml",
        {
            "profiles": {
                "default": {
                    "export": {"max_tags": 9},
                },
            },
        },
    )
    profiles = load_profiles(example_path=example, local_path=local)
    assert profiles["default"]["export"]["max_tags"] == 9
    assert profiles["default"]["embedding"]["backend"] == "noop"


def test_resolve_profile_default(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {
                    "library_roots": ["<ROOT>"],
                    "fl_user_data_path": "<FL>",
                    "database": {"path": "data/catalog.db"},
                    "export": {"max_tags": 5},
                    "embedding": {"backend": "noop", "model_cache_dir": "<CACHE>"},
                },
            },
        },
    )
    cfg = resolve_profile(example_path=example, local_path=None)
    assert cfg["embedding"]["backend"] == "noop"
    assert cfg["database"]["path"] == "data/catalog.db"
    assert cfg["export"]["max_tags"] == 5


def test_resolve_profile_from_env_profile_name(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {"export": {"max_tags": 5}},
                "minimal-demo": {"export": {"max_tags": 3}},
            },
        },
    )
    cfg = resolve_profile(
        example_path=example,
        local_path=None,
        env={
            "SAMPLE_BRAIN_PROFILE": "minimal-demo",
        },
    )
    assert cfg["export"]["max_tags"] == 3


def test_resolve_profile_env_overrides_embedding_backend(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {"embedding": {"backend": "noop"}},
            },
        },
    )
    cfg = resolve_profile(
        example_path=example,
        local_path=None,
        env={
            "SAMPLE_BRAIN_EMBEDDING_BACKEND": "clap",
        },
    )
    assert cfg["embedding"]["backend"] == "clap"


def test_resolve_profile_env_overrides_max_tags(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {"export": {"max_tags": 5}},
            },
        },
    )
    cfg = resolve_profile(
        example_path=example,
        local_path=None,
        env={
            "SAMPLE_BRAIN_MAX_TAGS": "10",
        },
    )
    assert cfg["export"]["max_tags"] == 10


def test_resolve_profile_rejects_invalid_max_tags(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {"export": {"max_tags": 5}},
            },
        },
    )
    with pytest.raises(ConfigError, match="Invalid integer"):
        resolve_profile(
            example_path=example,
            local_path=None,
            env={
                "SAMPLE_BRAIN_MAX_TAGS": "not-int",
            },
        )


def test_resolve_profile_rejects_unknown_profile(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {"export": {"max_tags": 5}},
            },
        },
    )
    with pytest.raises(ConfigError, match="Unknown profile"):
        resolve_profile(
            profile_name="does-not-exist",
            example_path=example,
            local_path=None,
        )


def test_resolve_profile_rejects_invalid_embedding_backend(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {"embedding": {"backend": "noop"}},
            },
        },
    )
    with pytest.raises(ConfigError, match="Invalid embedding backend"):
        resolve_profile(
            example_path=example,
            local_path=None,
            env={
                "SAMPLE_BRAIN_EMBEDDING_BACKEND": "bad",
            },
        )


def test_resolve_profile_missing_profiles_raises_error(tmp_path: Path):
    example = _write_yaml(tmp_path / "example.yaml", {"other": "data"})
    with pytest.raises(ConfigError, match="Unknown profile"):
        resolve_profile(example_path=example, local_path=None)


def test_load_profiles_missing_local_is_ok(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {"export": {"max_tags": 5}},
            },
        },
    )
    nonexistent = tmp_path / "nonexistent.yaml"
    profiles = load_profiles(example_path=example, local_path=nonexistent)
    assert "default" in profiles


def test_resolve_profile_env_overrides_library_roots(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {"library_roots": ["<OLD_ROOT>"]},
            },
        },
    )
    cfg = resolve_profile(
        example_path=example,
        local_path=None,
        env={
            "SAMPLE_BRAIN_LIBRARY_ROOTS": "<ROOT1>;<ROOT2>",
        },
    )
    assert cfg["library_roots"] == ["<ROOT1>", "<ROOT2>"]


def test_resolve_profile_strips_empty_library_roots_entries(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {"library_roots": ["<ROOT1>", " ", "", "<ROOT2>"]},
            },
        },
    )
    cfg = resolve_profile(example_path=example, local_path=None)
    assert cfg["library_roots"] == ["<ROOT1>", "<ROOT2>"]


def test_resolve_profile_rejects_non_string_library_roots_entries(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {"library_roots": ["<ROOT1>", 123]},
            },
        },
    )
    with pytest.raises(ConfigError, match="library_roots must contain only strings"):
        resolve_profile(example_path=example, local_path=None)


def test_resolve_profile_strips_database_path_from_env(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {"database": {"path": "data/catalog.db"}},
            },
        },
    )
    cfg = resolve_profile(
        example_path=example,
        local_path=None,
        env={
            "SAMPLE_BRAIN_DB_PATH": "  custom/catalog.db  ",
        },
    )
    assert cfg["database"]["path"] == "custom/catalog.db"


def test_resolve_search_backend_defaults_to_numpy(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {
                    "search": {"backend": "numpy"},
                },
            },
        },
    )
    cfg = resolve_profile(example_path=example, local_path=None)
    from src.config_loader import resolve_search_backend

    assert (
        resolve_search_backend(cli_value=None, config=cfg, env={}) == "numpy"
    )


def test_resolve_search_backend_cli_overrides_profile(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {
                    "search": {"backend": "numpy"},
                },
            },
        },
    )
    cfg = resolve_profile(example_path=example, local_path=None)
    from src.config_loader import resolve_search_backend

    assert (
        resolve_search_backend(
            cli_value="sqlite-vec", config=cfg, env={}
        )
        == "sqlite-vec"
    )


def test_resolve_profile_rejects_invalid_search_backend(tmp_path: Path):
    example = _write_yaml(
        tmp_path / "example.yaml",
        {
            "profiles": {
                "default": {
                    "search": {"backend": "faiss"},
                },
            },
        },
    )
    with pytest.raises(ConfigError, match="Invalid search backend"):
        resolve_profile(example_path=example, local_path=None)
