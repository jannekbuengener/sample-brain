"""Portable feature-analysis computation with no catalog/persistence ownership."""

from __future__ import annotations

import json
import warnings
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Callable, Iterator

import librosa
import numpy as np
import soundfile as sf

from .analysis_contracts import ANALYZE_HOP_LENGTH, ANALYZE_SR, Features
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
        y, sr = librosa.load(str(path), sr=target_sr, mono=True)
        if y is None or sr is None:
            return None, None
        y = np.asarray(y, dtype=np.float32)
        if y.size == 0:
            return None, None
        return y, int(sr)
    except Exception:
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
    """Estimate tonal root from the strongest mean chroma pitch class.

    Returns ``(root, key_conf)`` where ``key_conf`` is the normalized peak
    prominence ``max(chroma_mean) / sum(chroma_mean)``. This is relative ROOT
    evidence, not a calibrated probability, and is deliberately independent of
    the separate major/minor decision.
    """
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=ANALYZE_HOP_LENGTH)
        if chroma is None or chroma.size == 0:
            return None, None
        chroma_mean = np.mean(chroma, axis=1)
        if not np.isfinite(chroma_mean).all():
            return None, None
        idx = int(np.argmax(chroma_mean))
        peak = float(chroma_mean[idx])
        s = float(np.sum(chroma_mean) + 1e-9)
        conf = float(peak / s)
        return SEMITONES[idx], conf
    except Exception:
        return None, None


_MAJOR_THIRD_OFFSET = 4
_MINOR_THIRD_OFFSET = 3


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


# Frozen techno/dancefloor domain contract (#872 / PIR after #869).
# tol is half max adjacent librosa.tempo_frequencies spacing in [55, 85]
# at ANALYZE_SR=44100 with beat_track hop=512 — not testset-tuned.
_DOMAIN_110_170_LO = 110.0
_DOMAIN_110_170_HI = 170.0
_DOMAIN_110_170_TOL = 0.683232


def _bpm_in_domain_110_170(bpm: float) -> bool:
    return (
        _DOMAIN_110_170_LO - _DOMAIN_110_170_TOL
        <= bpm
        <= _DOMAIN_110_170_HI + _DOMAIN_110_170_TOL
    )


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
    if mode == "domain_110_170":
        if _bpm_in_domain_110_170(bpm):
            return bpm
        if _bpm_in_domain_110_170(2.0 * bpm):
            return 2.0 * bpm
        if _bpm_in_domain_110_170(bpm / 2.0):
            return bpm / 2.0
        return bpm
    if mode != "none":
        return None
    return bpm


def _duration_class(duration: float | None) -> str | None:
    if duration is None:
        return None
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


def _serialize_key_mode_evidence(evidence: dict | None) -> str | None:
    if evidence is None:
        return None
    # Fail closed for portable/DB evidence: never emit NaN/Inf JSON tokens (#960).
    return json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _extract_features_with_loader(
    path: Path,
    duration: float | None,
    bpm_normalization: str = "none",
    *,
    load_audio: Callable[[Path], tuple[np.ndarray | None, int | None]],
) -> Features | None:
    y, sr = load_audio(path)
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

def extract_features(
    path: Path, duration: float | None, bpm_normalization: str = "none"
) -> Features | None:
    """Extract portable features using this module's default audio loader."""

    return _extract_features_with_loader(
        path,
        duration,
        bpm_normalization,
        load_audio=safe_load,
    )

__all__ = [
    "ANALYZE_HOP_LENGTH",
    "ANALYZE_SR",
    "Features",
    "SHORT_AUDIO_DURATION_SEC",
    "SHORT_AUDIO_QUALITY_NOTE",
    "SHORT_AUDIO_WARNING_CODE",
    "KEY_ANALYSIS_CONTRACT_VERSION",
    "MODE_CONTRAST_MIN",
    "safe_load",
    "estimate_key",
    "estimate_key_mode",
    "normalize_bpm",
    "extract_features",
]
