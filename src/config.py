# src/config.py
from __future__ import annotations
import os
from pathlib import Path
from typing import Mapping

# ---- Verzeichnisse (relativ zum Projekt-Root) ----
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_DB_PATH = DATA_DIR / "catalog.db"


def _coerce_db_path(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (PROJECT_ROOT / path).resolve()


def _resolve_db_path(
    profile_db_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    if profile_db_path is not None:
        profile_value = str(profile_db_path).strip()
        if profile_value:
            return _coerce_db_path(profile_value)

    env_map = os.environ if env is None else env
    env_value = env_map.get("SAMPLE_BRAIN_DB_PATH")
    if env_value is not None:
        env_value = env_value.strip()
        if env_value:
            return _coerce_db_path(env_value)

    return DEFAULT_DB_PATH


def set_db_path(
    profile_db_path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    global DB_PATH
    DB_PATH = _resolve_db_path(profile_db_path=profile_db_path, env=env)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


DB_PATH = set_db_path()

# ---- Sample roots (legacy fallback) ----
# Sample roots are now resolved from config profiles or CLI overrides.
# Keep this empty as a safe legacy fallback; do not commit local paths.
SAMPLE_ROOTS: list[Path] = []

# ---- Audio-Dateiendungen, die wir berücksichtigen ----
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg"}

# ---- Performance/Analyzer Einstellungen ----
NUM_WORKERS = 0  # 0 = single-thread; >0 = parallel (optional)
ANALYZE_HOP_LENGTH = 512
ANALYZE_SR = 44100  # Ziel-Samplerate für Features, wenn resample nötig

# ---- Sonstiges ----
# Optional: Regex-Map für Dateinamen → Zusatz-Tags (falls vorhanden: ./data/filename_tag_regex.json)
REGEX_MAP_PATH = DATA_DIR / "filename_tag_regex.json"
