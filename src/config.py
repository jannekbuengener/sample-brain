# src/config.py
from __future__ import annotations
import os
from pathlib import Path

# ---- Verzeichnisse (relativ zum Projekt-Root) ----
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

_db_path_override = os.environ.get("SAMPLE_BRAIN_DB_PATH")
if _db_path_override:
    DB_PATH = Path(_db_path_override).expanduser().resolve()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
else:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH = DATA_DIR / "catalog.db"

# ---- Sample roots (legacy fallback) ----
# Sample roots are now resolved from config profiles or CLI overrides.
# Keep this empty as a safe legacy fallback; do not commit local paths.
SAMPLE_ROOTS: list[Path] = []

# ---- Audio-Dateiendungen, die wir berücksichtigen ----
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg"}

# ---- Performance/Analyzer Einstellungen ----
NUM_WORKERS = 0   # 0 = single-thread; >0 = parallel (optional)
ANALYZE_HOP_LENGTH = 512
ANALYZE_SR         = 44100  # Ziel-Samplerate für Features, wenn resample nötig

# ---- Sonstiges ----
# Optional: Regex-Map für Dateinamen → Zusatz-Tags (falls vorhanden: ./data/filename_tag_regex.json)
REGEX_MAP_PATH = DATA_DIR / "filename_tag_regex.json"
