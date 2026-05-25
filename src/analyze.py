from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import librosa
import soundfile as sf
from sqlalchemy import text
from tqdm import tqdm

from .config import ANALYZE_HOP_LENGTH, ANALYZE_SR
from .db import init_db


SEMITONES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def safe_load(path: Path, target_sr: int = ANALYZE_SR) -> tuple[np.ndarray | None, int | None]:
    """Best-effort audio load.

    - Returns mono float32 waveform and sample-rate.
    - Never throws; returns (None, None) on failure.
    """
    try:
        # For many formats, librosa (via soundfile/audioread) is the most robust.
        y, sr = librosa.load(str(path), sr=target_sr, mono=True)
        if y is None or sr is None:
            return None, None
        y = np.asarray(y, dtype=np.float32)
        if y.size == 0:
            return None, None
        return y, int(sr)
    except Exception:
        # As a fallback, try soundfile directly for wav/flac/etc.
        try:
            y, sr = sf.read(str(path), dtype="float32", always_2d=False)
            if y is None:
                return None, None
            if isinstance(y, np.ndarray) and y.ndim > 1:
                y = np.mean(y, axis=1)
            y = np.asarray(y, dtype=np.float32)
            if y.size == 0:
                return None, None
            if sr and target_sr and int(sr) != int(target_sr):
                y = librosa.resample(y, orig_sr=int(sr), target_sr=int(target_sr))
                sr = int(target_sr)
            return y, int(sr)
        except Exception:
            return None, None


def estimate_key(y: np.ndarray, sr: int) -> tuple[str | None, float | None]:
    """Rough key estimate (Krumhansl via chroma)."""
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=ANALYZE_HOP_LENGTH)
        if chroma is None or chroma.size == 0:
            return None, None
        chroma_mean = np.mean(chroma, axis=1)
        if not np.isfinite(chroma_mean).all():
            return None, None
        idx = int(np.argmax(chroma_mean))
        # confidence: normalized peak prominence
        peak = float(chroma_mean[idx])
        s = float(np.sum(chroma_mean) + 1e-9)
        conf = float(peak / s)
        return SEMITONES[idx], conf
    except Exception:
        return None, None


def _rms_dbfs(y: np.ndarray) -> float | None:
    try:
        rms = float(np.sqrt(np.mean(np.square(y))))
        if rms <= 0:
            return None
        return float(20.0 * np.log10(rms + 1e-12))
    except Exception:
        return None


def _duration_class(duration: float | None) -> str | None:
    if duration is None:
        return None
    # Heuristic aligned with classify.rule_type thresholds.
    return "oneshot" if duration <= 1.2 else "loop"


@dataclass(frozen=True)
class Features:
    bpm: float | None
    key: str | None
    key_conf: float | None
    loudness: float | None
    brightness: float | None
    mfcc_mean: bytes | None
    mfcc_std: bytes | None
    chroma_mean: bytes | None
    chroma_std: bytes | None
    clazz: str | None


def extract_features(path: Path, duration: float | None) -> Features | None:
    y, sr = safe_load(path)
    if y is None or sr is None:
        return None

    # Tempo (best-effort). For short one-shots this may be nonsense; that's ok.
    bpm: float | None
    try:
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo) if tempo and tempo > 0 else None
    except Exception:
        bpm = None

    key, key_conf = estimate_key(y, sr)
    loudness = _rms_dbfs(y)

    brightness: float | None
    try:
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=ANALYZE_HOP_LENGTH)
        brightness = float(np.mean(centroid)) if centroid is not None and centroid.size else None
    except Exception:
        brightness = None

    # MFCC/chroma stats
    try:
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=ANALYZE_HOP_LENGTH)
        mfcc_mean = np.mean(mfcc, axis=1).astype(np.float32).tobytes() if mfcc.size else None
        mfcc_std = np.std(mfcc, axis=1).astype(np.float32).tobytes() if mfcc.size else None
    except Exception:
        mfcc_mean = None
        mfcc_std = None

    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=ANALYZE_HOP_LENGTH)
        chroma_mean = np.mean(chroma, axis=1).astype(np.float32).tobytes() if chroma.size else None
        chroma_std = np.std(chroma, axis=1).astype(np.float32).tobytes() if chroma.size else None
    except Exception:
        chroma_mean = None
        chroma_std = None

    return Features(
        bpm=bpm,
        key=key,
        key_conf=key_conf,
        loudness=loudness,
        brightness=brightness,
        mfcc_mean=mfcc_mean,
        mfcc_std=mfcc_std,
        chroma_mean=chroma_mean,
        chroma_std=chroma_std,
        clazz=_duration_class(duration),
    )


def run_analyze(limit: int | None = None, only_missing: bool = True) -> None:
    """Compute features for samples in the catalog.

    Safe by default:
    - reads sample paths from DB (does not scan filesystem roots)
    - skips rows that already have a features row (unless only_missing=False)
    """
    engine = init_db()
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT s.id, s.path, s.duration, f.sample_id AS has_features
                FROM samples s
                LEFT JOIN features f ON f.sample_id = s.id
                ORDER BY s.id
                """
            )
        ).fetchall()

    processed = 0
    engine = init_db()
    with engine.begin() as conn:
        for sid, path_str, duration, has_features in tqdm(rows, desc="Analyzing", unit="file"):
            if only_missing and has_features is not None:
                continue

            feats = extract_features(Path(path_str), duration)
            if feats is None:
                continue

            # Upsert into features. Note: column name is `class` (reserved word), so quote it.
            conn.execute(
                text(
                    """
                    INSERT INTO features (
                        sample_id, bpm, key, key_conf, loudness, brightness,
                        mfcc_mean, mfcc_std, chroma_mean, chroma_std, "class"
                    ) VALUES (
                        :sample_id, :bpm, :key, :key_conf, :loudness, :brightness,
                        :mfcc_mean, :mfcc_std, :chroma_mean, :chroma_std, :clazz
                    )
                    ON CONFLICT(sample_id) DO UPDATE SET
                        bpm=excluded.bpm,
                        key=excluded.key,
                        key_conf=excluded.key_conf,
                        loudness=excluded.loudness,
                        brightness=excluded.brightness,
                        mfcc_mean=excluded.mfcc_mean,
                        mfcc_std=excluded.mfcc_std,
                        chroma_mean=excluded.chroma_mean,
                        chroma_std=excluded.chroma_std,
                        "class"=excluded."class"
                    """
                ),
                dict(
                    sample_id=int(sid),
                    bpm=feats.bpm,
                    key=feats.key,
                    key_conf=feats.key_conf,
                    loudness=feats.loudness,
                    brightness=feats.brightness,
                    mfcc_mean=feats.mfcc_mean,
                    mfcc_std=feats.mfcc_std,
                    chroma_mean=feats.chroma_mean,
                    chroma_std=feats.chroma_std,
                    clazz=feats.clazz,
                ),
            )

            processed += 1
            if limit is not None and processed >= int(limit):
                break


__all__ = ["run_analyze", "extract_features", "safe_load", "estimate_key"]
