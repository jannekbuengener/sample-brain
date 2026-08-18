from __future__ import annotations

import warnings
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import librosa
import soundfile as sf
from sqlalchemy import text
from tqdm import tqdm

from .config import ANALYZE_HOP_LENGTH, ANALYZE_SR
from .db import init_db
from .key_signature import format_key_signature


SEMITONES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

SHORT_AUDIO_DURATION_SEC = 0.5
SHORT_AUDIO_QUALITY_NOTE = "Kurzclip — BPM/Key eingeschränkt verlässlich"
SHORT_AUDIO_WARNING_CODE = "short_audio_warning"

# Analyzer contract version for the separate major/minor mode decision (#212).
# Bumped only when the mode-estimation semantics or evidence shape change.
KEY_ANALYSIS_CONTRACT_VERSION = 1

# Minimum Dur/Moll "third contrast" required to commit to a mode. The detector
# compares the chroma energy at the major third (root + 4 semitones) against the
# minor third (root + 3 semitones); see :func:`estimate_key_mode`.
#
# Threshold is derived from the deterministic synthetic fixtures in
# tests/audio_fixtures.py: clear major/minor fixtures reach a contrast >= ~0.916,
# while ambiguous fixtures (single note, octave, root+fifth, maj/min blend) stay
# <= ~0.056. 0.30 sits with a wide safety margin between the two groups, so the
# synthetic validation gate passes without overfitting. Frozen against that gate.
MODE_CONTRAST_MIN = 0.30


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
    """Rough key estimate (Krumhansl via chroma).

    Returns ``(root, key_conf)`` where ``key_conf`` is the normalized peak
    prominence ``max(chroma_mean) / sum(chroma_mean)``. This is ROOT evidence
    only and is deliberately independent of the separate major/minor decision.
    """
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


_MAJOR_THIRD_OFFSET = 4  # semitones above the root
_MINOR_THIRD_OFFSET = 3  # semitones above the root


def _chroma_mean(y: np.ndarray, sr: int) -> np.ndarray | None:
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=ANALYZE_HOP_LENGTH)
        if chroma is None or chroma.size == 0:
            return None
        chroma_mean = np.mean(chroma, axis=1)
        if not np.isfinite(chroma_mean).all():
            return None
        return chroma_mean.astype(np.float64)
    except Exception:
        return None


def estimate_key_mode(
    y: np.ndarray,
    sr: int,
    *,
    root: str | None = None,
    chroma_mean: np.ndarray | None = None,
) -> tuple[str | None, dict | None]:
    """Separate major/minor (Dur/Moll) decision via third contrast.

    The root is taken from :func:`estimate_key` unless supplied. For the detected
    root, the chroma energy at the major third (root + 4 semitones) is compared to
    the minor third (root + 3 semitones). The normalized contrast is::

        contrast = |major_third - minor_third| / (major_third + minor_third + eps)

    The mode is committed only when ``contrast >= MODE_CONTRAST_MIN``: a larger
    third wins (major third -> "maj", minor third -> "min"). Below the threshold
    the mode is ``None`` (unknown) and no mode is guessed. Single notes, octaves,
    root+fifth, and equal maj/min blends all have a near-zero contrast and abstain.

    Returns ``(mode, evidence)`` where ``mode`` is ``"maj"``/``"min"``/``None`` and
    ``evidence`` is relative analysis evidence (NOT a calibrated probability).
    """
    evidence = {
        "kind": "third_contrast",
        "major_third_energy": None,
        "minor_third_energy": None,
        "contrast": None,
        "threshold": MODE_CONTRAST_MIN,
        "mode": None,
    }
    try:
        if chroma_mean is None:
            chroma_mean = _chroma_mean(y, sr)
        if chroma_mean is None:
            return None, evidence
        if root is None:
            root, _ = estimate_key(y, sr)
        if root is None:
            return None, evidence

        idx = SEMITONES.index(root)
        minor_idx = (idx + _MINOR_THIRD_OFFSET) % 12
        major_idx = (idx + _MAJOR_THIRD_OFFSET) % 12
        minor_energy = float(chroma_mean[minor_idx])
        major_energy = float(chroma_mean[major_idx])

        denom = major_energy + minor_energy + 1e-9
        contrast = abs(major_energy - minor_energy) / denom

        evidence["major_third_energy"] = round(major_energy, 6)
        evidence["minor_third_energy"] = round(minor_energy, 6)
        evidence["contrast"] = round(contrast, 6)

        if contrast < MODE_CONTRAST_MIN:
            evidence["mode"] = None
            return None, evidence
        if major_energy >= minor_energy:
            mode = "maj"
        else:
            mode = "min"
        evidence["mode"] = mode
        return mode, evidence
    except Exception:
        return None, evidence


def _rms_dbfs(y: np.ndarray) -> float | None:
    try:
        rms = float(np.sqrt(np.mean(np.square(y))))
        if rms <= 0:
            return None
        return float(20.0 * np.log10(rms + 1e-12))
    except Exception:
        return None


def _extract_bpm_scalar(tempo) -> float | None:
    if tempo is None:
        return None
    if isinstance(tempo, (int, float)):
        scalar = float(tempo)
    elif isinstance(tempo, np.ndarray) and tempo.size == 1:
        scalar = float(tempo.item())
    elif isinstance(tempo, np.ndarray) and tempo.ndim == 0:
        scalar = float(tempo.item())
    elif isinstance(tempo, (np.ndarray, list)) and len(tempo) > 0:
        scalar = float(tempo[0])
    else:
        return None
    return scalar if scalar > 0 else None


def normalize_bpm(bpm: float | None, mode: str = "none") -> float | None:
    if bpm is None:
        return None
    if bpm <= 0:
        return None
    if mode == "heuristic":
        if bpm < 90:
            return bpm * 2.0
        if bpm > 200:
            return bpm / 2.0
        return bpm
    if mode != "none":
        return None
    return bpm


def _duration_class(duration: float | None) -> str | None:
    if duration is None:
        return None
    # Heuristic aligned with classify.rule_type thresholds.
    return "oneshot" if duration <= 1.2 else "loop"


def _effective_n_fft(n_samples: int, *, default: int = 2048, minimum: int = 64) -> int:
    if n_samples <= minimum:
        return max(2, int(n_samples) // 2 * 2 or 2)
    cap = min(default, int(n_samples))
    n_fft = minimum
    while n_fft * 2 <= cap:
        n_fft *= 2
    return n_fft


def _is_short_clip(duration: float | None, n_samples: int, sr: int) -> bool:
    threshold_samples = int(sr * SHORT_AUDIO_DURATION_SEC)
    if n_samples < threshold_samples:
        return True
    if duration is not None and duration < SHORT_AUDIO_DURATION_SEC:
        return True
    return False


@contextmanager
def _suppress_known_short_audio_librosa_warnings() -> Iterator[None]:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"n_fft=.*is too large for input signal",
            category=UserWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message=r"Trying to estimate tuning from empty frequency set",
            category=UserWarning,
        )
        yield


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
    quality_note: str | None = None
    key_mode: str | None = None
    key_mode_evidence: dict | None = None


def extract_features(
    path: Path, duration: float | None, bpm_normalization: str = "none"
) -> Features | None:
    y, sr = safe_load(path)
    if y is None or sr is None:
        return None

    short_clip = _is_short_clip(duration, y.size, sr)
    quality_note = SHORT_AUDIO_QUALITY_NOTE if short_clip else None
    n_fft = _effective_n_fft(y.size)
    warning_ctx = (
        _suppress_known_short_audio_librosa_warnings()
        if short_clip
        else nullcontext()
    )

    with warning_ctx:
        bpm: float | None
        if short_clip:
            bpm = None
        else:
            try:
                tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
                bpm = _extract_bpm_scalar(tempo)
            except Exception:
                bpm = None
            bpm = normalize_bpm(bpm, mode=bpm_normalization)

        if short_clip:
            key, key_conf = None, None
            key_mode, key_mode_evidence = None, None
        else:
            key, key_conf = estimate_key(y, sr)
            if key is not None:
                key_mode, key_mode_evidence = estimate_key_mode(y, sr, root=key)
                key = format_key_signature(key, key_mode)
            else:
                key_mode, key_mode_evidence = None, None

        loudness = _rms_dbfs(y)

        brightness: float | None
        try:
            centroid = librosa.feature.spectral_centroid(
                y=y, sr=sr, hop_length=ANALYZE_HOP_LENGTH, n_fft=n_fft
            )
            brightness = (
                float(np.mean(centroid)) if centroid is not None and centroid.size else None
            )
        except Exception:
            brightness = None

        try:
            mfcc = librosa.feature.mfcc(
                y=y,
                sr=sr,
                n_mfcc=13,
                hop_length=ANALYZE_HOP_LENGTH,
                n_fft=n_fft,
            )
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
        quality_note=quality_note,
        key_mode=key_mode,
        key_mode_evidence=key_mode_evidence,
    )


_FEATURE_UPSERT = text(
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
)


def _load_analyze_batch(
    engine,
    *,
    last_id: int,
    batch_size: int,
    only_missing: bool,
) -> list[tuple]:
    missing_clause = "AND f.sample_id IS NULL" if only_missing else ""
    query = text(
        f"""
        SELECT s.id, s.path, s.duration, f.sample_id AS has_features
        FROM samples s
        LEFT JOIN features f ON f.sample_id = s.id
        WHERE s.id > :last_id
          {missing_clause}
        ORDER BY s.id
        LIMIT :batch_size
        """
    )
    with engine.connect() as conn:
        return conn.execute(
            query,
            {"last_id": int(last_id), "batch_size": int(batch_size)},
        ).fetchall()


def _flush_feature_batch(engine, rows: list[dict]) -> None:
    if not rows:
        return
    with engine.begin() as conn:
        conn.execute(_FEATURE_UPSERT, rows)


def run_analyze(
    limit: int | None = None,
    only_missing: bool = True,
    bpm_normalization: str = "none",
    batch_size: int = 100,
) -> None:
    """Compute features for samples in bounded batches.

    Safe by default:
    - reads sample paths from DB (does not scan filesystem roots)
    - skips rows that already have a features row in SQL when only_missing=True
    - performs expensive audio analysis outside DB write transactions
    - keeps catalog reads bounded by primary-key pages
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    engine = init_db()
    processed = 0
    last_id = 0
    done = False

    with tqdm(desc="Analyzing", unit="file") as bar:
        while not done:
            rows = _load_analyze_batch(
                engine,
                last_id=last_id,
                batch_size=batch_size,
                only_missing=only_missing,
            )
            if not rows:
                break

            last_id = int(rows[-1][0])
            writes: list[dict] = []

            for sid, path_str, duration, _has_features in rows:
                bar.update(1)
                feats = extract_features(
                    Path(path_str),
                    duration,
                    bpm_normalization=bpm_normalization,
                )
                if feats is None:
                    continue

                writes.append(
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
                    )
                )
                processed += 1
                if limit is not None and processed >= int(limit):
                    done = True
                    break

            _flush_feature_batch(engine, writes)


__all__ = [
    "SHORT_AUDIO_DURATION_SEC",
    "SHORT_AUDIO_QUALITY_NOTE",
    "SHORT_AUDIO_WARNING_CODE",
    "KEY_ANALYSIS_CONTRACT_VERSION",
    "MODE_CONTRAST_MIN",
    "run_analyze",
    "extract_features",
    "safe_load",
    "estimate_key",
    "estimate_key_mode",
]
