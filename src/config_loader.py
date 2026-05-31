from __future__ import annotations
from pathlib import Path
from typing import Any, Optional

import yaml


class ConfigError(Exception): ...


DEFAULT_PROFILE_NAME = "default"
DEFAULT_EXAMPLE_CONFIG = Path("config/profiles.example.yaml")
DEFAULT_LOCAL_CONFIG = Path("config/profiles.local.yaml")

_ENV_VARS = {
    "profile": "SAMPLE_BRAIN_PROFILE",
    "library_roots": "SAMPLE_BRAIN_LIBRARY_ROOTS",
    "fl_user_data": "SAMPLE_BRAIN_FL_USER_DATA",
    "model_cache_dir": "SAMPLE_BRAIN_MODEL_CACHE_DIR",
    "db_path": "SAMPLE_BRAIN_DB_PATH",
    "max_tags": "SAMPLE_BRAIN_MAX_TAGS",
}

_ENV_KEY_MAP: dict[str, tuple[str, ...]] = {
    "SAMPLE_BRAIN_LIBRARY_ROOTS": ("library_roots",),
    "SAMPLE_BRAIN_FL_USER_DATA": ("fl_user_data_path",),
    "SAMPLE_BRAIN_MODEL_CACHE_DIR": ("embedding", "model_cache_dir"),
    "SAMPLE_BRAIN_DB_PATH": ("database", "path"),
    "SAMPLE_BRAIN_MAX_TAGS": ("export", "max_tags"),
    "SAMPLE_BRAIN_EMBEDDING_BACKEND": ("embedding", "backend"),
    "SAMPLE_BRAIN_SEARCH_BACKEND": ("search", "backend"),
}

_VALID_EMBEDDING_BACKENDS = {"noop", "clap"}
_VALID_SEARCH_BACKENDS = {"numpy", "sqlite-vec"}


def load_profiles(
    example_path: Path = DEFAULT_EXAMPLE_CONFIG,
    local_path: Optional[Path] = DEFAULT_LOCAL_CONFIG,
) -> dict[str, dict]:
    if not example_path.is_file():
        raise ConfigError(f"Example config not found: {example_path}")

    try:
        with open(example_path, "r", encoding="utf-8") as f:
            example_data: dict = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Error parsing example config {example_path}: {e}")

    profiles: dict[str, dict] = example_data.get("profiles", {})
    if not isinstance(profiles, dict):
        raise ConfigError(f"'profiles' key is not a dict in {example_path}")

    if local_path is not None and local_path.is_file():
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                local_data: dict = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"Error parsing local config {local_path}: {e}")

        local_profiles = local_data.get("profiles", {})
        if isinstance(local_profiles, dict):
            profiles = _deep_merge(profiles, local_profiles)

    return profiles


def resolve_profile(
    profile_name: Optional[str] = None,
    example_path: Path = DEFAULT_EXAMPLE_CONFIG,
    local_path: Optional[Path] = DEFAULT_LOCAL_CONFIG,
    env: Optional[dict[str, str]] = None,
) -> dict:
    if env is None:
        env = {}

    profiles = load_profiles(example_path=example_path, local_path=local_path)

    name = profile_name or env.get(_ENV_VARS["profile"]) or DEFAULT_PROFILE_NAME

    if name not in profiles:
        available = ", ".join(sorted(profiles.keys()))
        raise ConfigError(f"Unknown profile: {name}. Available: {available}")

    resolved = _deep_merge({}, profiles[name])
    resolved = _apply_env_overrides(resolved, env)
    resolved = _normalize_resolved_config(resolved)
    _validate_resolved_config(resolved)
    return resolved


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _apply_env_overrides(profile: dict, env: dict[str, str]) -> dict:
    for env_var, keys in _ENV_KEY_MAP.items():
        value = env.get(env_var)
        if value is None or value == "":
            continue
        target = profile
        for key in keys[:-1]:
            if not isinstance(target.get(key), dict):
                target[key] = {}
            target = target[key]
        target[keys[-1]] = _parse_value(value, keys[-1])
    return profile


def _parse_value(value: str, key: str) -> Any:
    if key == "library_roots":
        return _parse_roots(value)
    if key == "max_tags":
        try:
            return int(value.strip())
        except ValueError:
            raise ConfigError(f"Invalid integer for {key}: {value}")
    return value.strip()


def _parse_roots(value: str) -> list[str]:
    return [p.strip() for p in value.split(";") if p.strip()]


def _normalize_resolved_config(config: dict) -> dict:
    roots = config.get("library_roots", [])
    if roots is None:
        normalized_roots: list[str] = []
    elif isinstance(roots, str):
        normalized_roots = _parse_roots(roots)
    elif isinstance(roots, list):
        normalized_roots = []
        for root in roots:
            if not isinstance(root, str):
                raise ConfigError("library_roots must contain only strings")
            stripped = root.strip()
            if stripped:
                normalized_roots.append(stripped)
    else:
        raise ConfigError(
            f"library_roots must be a list[str] or ';'-separated string, got {type(roots).__name__}"
        )
    config["library_roots"] = normalized_roots

    database = config.get("database")
    if database is None:
        return config
    if not isinstance(database, dict):
        raise ConfigError("database config must be a dict")

    db_path = database.get("path")
    if db_path is None:
        return config
    if not isinstance(db_path, str):
        raise ConfigError("database.path must be a string")
    db_path = db_path.strip()
    if not db_path:
        raise ConfigError("database.path must not be empty")
    database["path"] = db_path
    return config


def _validate_resolved_config(config: dict) -> None:
    backend = config.get("embedding", {}).get("backend")
    if backend is not None and backend not in _VALID_EMBEDDING_BACKENDS:
        raise ConfigError(
            f"Invalid embedding backend: {backend!r}. "
            f"Must be one of: {', '.join(sorted(_VALID_EMBEDDING_BACKENDS))}"
        )

    search_backend = config.get("search", {}).get("backend")
    if search_backend is not None and search_backend not in _VALID_SEARCH_BACKENDS:
        raise ConfigError(
            f"Invalid search backend: {search_backend!r}. "
            f"Must be one of: {', '.join(sorted(_VALID_SEARCH_BACKENDS))}"
        )

    roots = config.get("library_roots")
    if roots is not None:
        if not isinstance(roots, list) or any(
            not isinstance(root, str) or not root for root in roots
        ):
            raise ConfigError("library_roots must be a list of non-empty strings")


def resolve_search_backend(
    *,
    cli_value: str | None,
    config: dict,
    env: dict[str, str],
) -> str:
    if cli_value is not None:
        backend = cli_value
    else:
        env_value = env.get("SAMPLE_BRAIN_SEARCH_BACKEND")
        if env_value:
            backend = env_value.strip()
        else:
            backend = config.get("search", {}).get("backend", "numpy")

    if backend not in _VALID_SEARCH_BACKENDS:
        raise ConfigError(
            f"Invalid search backend: {backend!r}. "
            f"Must be one of: {', '.join(sorted(_VALID_SEARCH_BACKENDS))}"
        )
    return backend
