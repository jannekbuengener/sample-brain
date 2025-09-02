# src/scan.py  (STREAMING-VERSION)
from __future__ import annotations
from pathlib import Path
from typing import Iterable, Iterator, Optional, Set
import os
import soundfile as sf
from sqlalchemy import text
from tqdm import tqdm

from .config import SAMPLE_ROOTS, AUDIO_EXTS, DB_PATH  # AUDIO_EXTS stammt aus config.py
from .db import init_db
from .utils import file_hash

# Ordner, die wir beim rekursiven Scan überspringen (Case-insensitive)
DEFAULT_IGNORE_DIRS: Set[str] = {
    ".git", "__pycache__", ".venv", "venv",
    "Ableton Projects", "Recycle Bin", "$RECYCLE.BIN",
    "System Volume Information", "Cache", "Caches"
}

def _should_ignore_dir(p: Path) -> bool:
    name = p.name.lower()
    return name in {d.lower() for d in DEFAULT_IGNORE_DIRS}

def iter_audio_files_stream(roots: Iterable[Path]) -> Iterator[Path]:
    """Liefert Audio-Dateien als Stream (keine Vorab-Liste)."""
    for root in roots:
        if not root.exists():
            continue
        # Os.walk ist schneller und gibt uns dirnames, die wir live filtern können
        for dirpath, dirnames, filenames in os.walk(root):
            # Unterordner filtern (in-place, damit os.walk sie nicht betritt)
            dirnames[:] = [d for d in dirnames if not _should_ignore_dir(Path(dirpath) / d)]
            for fn in filenames:
                p = Path(dirpath) / fn
                if p.suffix.lower() in AUDIO_EXTS:
                    yield p

def safe_audio_info(path: Path):
    sr = ch = None
    dur = None
    try:
        with sf.SoundFile(path) as f:
            sr = f.samplerate
            ch = f.channels
            dur = len(f) / float(sr)
    except Exception:
        # mp3/ogg o.ä. evtl. nicht direkt lesbar -> Werte bleiben None
        pass
    return sr, ch, dur

def _relpath_against_any(p: Path, roots: list[Path]) -> Optional[str]:
    for r in roots:
        try:
            return str(p.relative_to(r))
        except Exception:
            continue
    return None

def run_scan(custom_roots: Optional[Iterable[Path]] = None,
             limit: Optional[int] = None,
             show_every: int = 200):
    """
    Streamender Scan:
      - custom_roots: Liste von Pfaden; None -> SAMPLE_ROOTS aus config.py
      - limit: brich nach X Dateien ab (Debug/Teillauf)
      - show_every: alle N Dateien einen kleinen Status ausgeben (zusätzlich zu tqdm)
    """
    roots = [Path(r) for r in (custom_roots or SAMPLE_ROOTS)]
    engine = init_db()

    it = iter_audio_files_stream(roots)
    processed = 0

    # tqdm ohne total (unbekannt) – zeigt laufenden Zähler
    with engine.begin() as conn, tqdm(desc="Scanning", unit="file") as bar:
        for p in it:
            rel = _relpath_against_any(p, roots)
            sr, ch, dur = safe_audio_info(p)
            size = p.stat().st_size
            h = file_hash(p)

            conn.execute(text("""
                INSERT INTO samples (path, relpath, samplerate, channels, duration, size_bytes, hash)
                VALUES (:path, :relpath, :sr, :ch, :dur, :size_bytes, :hash)
                ON CONFLICT(path) DO UPDATE SET
                    relpath=excluded.relpath,
                    samplerate=excluded.samplerate,
                    channels=excluded.channels,
                    duration=excluded.duration,
                    size_bytes=excluded.size_bytes,
                    hash=excluded.hash
            """), dict(path=str(p), relpath=rel, sr=sr, ch=ch, dur=dur, size_bytes=size, hash=h))

            processed += 1
            bar.update(1)
            if show_every and processed % show_every == 0:
                bar.set_postfix_str(f"{processed} files | DB: {DB_PATH.name}")

            if limit and processed >= limit:
                break
