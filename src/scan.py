# src/scan.py  (STREAMING-VERSION)
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Iterator, Optional, Set

import soundfile as sf
from sqlalchemy import text
from tqdm import tqdm

from .config import SAMPLE_ROOTS, AUDIO_EXTS, DB_PATH  # AUDIO_EXTS stammt aus config.py
from .content_hash import DEFAULT_CONTENT_HASH_ALGORITHM, compute_file_hash
from .db import init_db

# Ordner, die wir beim rekursiven Scan überspringen (Case-insensitive)
DEFAULT_IGNORE_DIRS: Set[str] = {
    ".git", "__pycache__", ".venv", "venv",
    "Ableton Projects", "Recycle Bin", "$RECYCLE.BIN",
    "System Volume Information", "Cache", "Caches"
}

_SAMPLE_UPSERT = text("""
    INSERT INTO samples (
        path, relpath, samplerate, channels, duration, size_bytes, hash,
        hash_algorithm
    )
    VALUES (
        :path, :relpath, :sr, :ch, :dur, :size_bytes, :hash,
        :hash_algorithm
    )
    ON CONFLICT(path) DO UPDATE SET
        relpath=excluded.relpath,
        samplerate=excluded.samplerate,
        channels=excluded.channels,
        duration=excluded.duration,
        size_bytes=excluded.size_bytes,
        hash=excluded.hash,
        hash_algorithm=excluded.hash_algorithm
""")


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


def _flush_scan_batch(engine, rows: list[dict]) -> None:
    """Write one prepared batch in a short transaction."""
    if not rows:
        return
    with engine.begin() as conn:
        conn.execute(_SAMPLE_UPSERT, rows)


def plan_scan(
    custom_roots: Optional[Iterable[Path]] = None,
    limit: Optional[int] = None,
) -> dict:
    """Read-only filesystem discovery for scan ``--dry-run``.

    Does not open or mutate the catalog DB. Skips hashing and audio probing so
    the preview stays cheap while still counting discoverable audio files.
    """
    selected_roots = SAMPLE_ROOTS if custom_roots is None else list(custom_roots)
    roots = [Path(r) for r in selected_roots]
    if not roots:
        return {
            "roots_configured": 0,
            "sample_upserts": 0,
            "discovered_relpaths": [],
            "warning": "no_sample_roots",
        }

    discovered: list[str] = []
    for p in iter_audio_files_stream(roots):
        rel = _relpath_against_any(p, roots)
        discovered.append(rel or p.name)
        if limit and len(discovered) >= limit:
            break

    return {
        "roots_configured": len(roots),
        "sample_upserts": len(discovered),
        "discovered_relpaths": discovered,
    }


def run_scan(
    custom_roots: Optional[Iterable[Path]] = None,
    limit: Optional[int] = None,
    show_every: int = 200,
    batch_size: int = 100,
    *,
    dry_run: bool = False,
):
    """
    Streamender Scan:
      - custom_roots: Liste von Pfaden; None -> SAMPLE_ROOTS aus config.py
      - limit: brich nach X erfolgreich vorbereiteten Dateien ab (Debug/Teillauf)
      - show_every: alle N Dateien einen kleinen Status ausgeben (zusätzlich zu tqdm)
      - batch_size: Anzahl vorbereiteter Zeilen pro kurzer DB-Schreibtransaktion
      - dry_run: discover/plan only; no catalog mutation

    Dateisystem-Probing und Hashing passieren außerhalb von SQLite-Schreibtransaktionen.
    Dateien, die zwischen Discovery und Lesen verschwinden oder nicht lesbar sind,
    werden übersprungen, ohne den restlichen Scan abzubrechen.
    """
    if dry_run:
        return plan_scan(custom_roots=custom_roots, limit=limit)

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    selected_roots = SAMPLE_ROOTS if custom_roots is None else list(custom_roots)
    roots = [Path(r) for r in selected_roots]
    if not roots:
        print("[WARN] No sample roots configured. Use --root or config/profiles.local.yaml.")
        return
    engine = init_db()

    it = iter_audio_files_stream(roots)
    processed = 0
    batch: list[dict] = []

    # tqdm ohne total (unbekannt) – zeigt laufenden Zähler
    with tqdm(desc="Scanning", unit="file") as bar:
        for p in it:
            rel = _relpath_against_any(p, roots)
            sr, ch, dur = safe_audio_info(p)
            try:
                size = p.stat().st_size
                identity = compute_file_hash(p)
            except OSError as exc:
                print(f"[WARN] Skipping unreadable sample: {p} ({exc})")
                continue

            batch.append(
                dict(
                    path=str(p),
                    relpath=rel,
                    sr=sr,
                    ch=ch,
                    dur=dur,
                    size_bytes=size,
                    hash=identity["value"],
                    hash_algorithm=DEFAULT_CONTENT_HASH_ALGORITHM,
                )
            )
            processed += 1
            bar.update(1)

            if len(batch) >= batch_size:
                _flush_scan_batch(engine, batch)
                batch.clear()

            if show_every and processed % show_every == 0:
                bar.set_postfix_str(f"{processed} files | DB: {DB_PATH.name}")

            if limit and processed >= limit:
                break

        _flush_scan_batch(engine, batch)
