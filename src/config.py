# src/config.py
from __future__ import annotations
from pathlib import Path

# ---- Verzeichnisse (relativ zum Projekt-Root) ----
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR     = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH      = DATA_DIR / "catalog.db"

# ---- Wo liegen deine Samples? (Wurzeln – wird rekursiv gescannt) ----
# In deinem Fall ALLES unter D:\PRODUCING
SAMPLE_ROOTS = [
    Path(r"D:\PRODUCING"),
]

# ---- Audio-Dateiendungen, die wir berücksichtigen ----
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg"}

# ---- Performance/Analyzer Einstellungen ----
NUM_WORKERS = 0   # 0 = single-thread; >0 = parallel (optional)
ANALYZE_HOP_LENGTH = 512
ANALYZE_SR         = 44100  # Ziel-Samplerate für Features, wenn resample nötig

# ---- Sonstiges ----
# Optional: Regex-Map für Dateinamen → Zusatz-Tags (falls vorhanden: ./data/filename_tag_regex.json)
REGEX_MAP_PATH = DATA_DIR / "filename_tag_regex.json"
