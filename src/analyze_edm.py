# src/analyze_edm.py
"""
EDM-optimized audio analysis module.
Enhanced precision for electronic dance music genres.
"""
from __future__ import annotations
import numpy as np
import librosa
from pathlib import Path
from typing import Any


# ===== Camelot Wheel Mapping =====

CAMELOT_WHEEL = {
    # Major keys
    "C": "8B", "G": "9B", "D": "10B", "A": "11B", "E": "12B", "B": "1B",
    "F#": "2B", "Gb": "2B", "C#": "3B", "Db": "3B", "G#": "4B", "Ab": "4B",
    "D#": "5B", "Eb": "5B", "A#": "6B", "Bb": "6B", "F": "7B",

    # Minor keys
    "Am": "8A", "Em": "9A", "Bm": "10A", "F#m": "11A", "C#m": "12A",
    "G#m": "1A", "Abm": "1A", "D#m": "2A", "Ebm": "2A", "A#m": "3A",
    "Bbm": "3A", "Fm": "4A", "Cm": "5A", "Gm": "6A", "Dm": "7A"
}


def key_to_camelot(key: str | None) -> str | None:
    """
    Convert musical key to Camelot Wheel notation.

    Args:
        key: Musical key (e.g., "Am", "C", "F#m")

    Returns:
        Camelot notation (e.g., "8A", "8B")
    """
    if not key:
        return None

    # Normalize key
    key_normalized = key.strip()

    # Try direct lookup
    if key_normalized in CAMELOT_WHEEL:
        return CAMELOT_WHEEL[key_normalized]

    # Try with variations
    for k, v in CAMELOT_WHEEL.items():
        if key_normalized.upper() == k.upper():
            return v

    return None


def get_compatible_keys(camelot: str) -> list[str]:
    """
    Get harmonically compatible keys for mixing.

    Args:
        camelot: Camelot notation (e.g., "8A")

    Returns:
        List of compatible Camelot keys
    """
    if not camelot or len(camelot) < 2:
        return []

    try:
        number = int(camelot[:-1])
        letter = camelot[-1].upper()
    except (ValueError, IndexError):
        return []

    compatible = []

    # Same key
    compatible.append(camelot)

    # +/- 1 on wheel (same letter)
    prev_num = number - 1 if number > 1 else 12
    next_num = number + 1 if number < 12 else 1
    compatible.append(f"{prev_num}{letter}")
    compatible.append(f"{next_num}{letter}")

    # Relative major/minor
    other_letter = "B" if letter == "A" else "A"
    compatible.append(f"{number}{other_letter}")

    return compatible


# ===== Enhanced BPM Detection for EDM =====

def detect_bpm_multipass(y: np.ndarray, sr: int) -> dict[str, Any]:
    """
    Multi-pass BPM detection optimized for EDM.

    Args:
        y: Audio time series
        sr: Sample rate

    Returns:
        Dictionary with BPM info and confidence
    """
    # Pass 1: HPSS separation
    try:
        y_harmonic, y_percussive = librosa.effects.hpss(y, margin=2.0)
    except Exception:
        y_percussive = y

    # Pass 2: Multiple tempo estimates
    tempo_estimates = []

    # Standard beat tracking on percussive
    tempo, beats = librosa.beat.beat_track(y=y_percussive, sr=sr, units='time')
    if tempo and tempo > 0:
        tempo_estimates.append(float(tempo))

    # Onset envelope method
    try:
        onset_env = librosa.onset.onset_strength(y=y_percussive, sr=sr)
        tempo_onset = librosa.feature.tempo(onset_envelope=onset_env, sr=sr)
        if len(tempo_onset) > 0 and tempo_onset[0] > 0:
            tempo_estimates.append(float(tempo_onset[0]))
    except Exception:
        pass

    # Tempogram method for more accuracy
    try:
        tempogram = librosa.feature.tempogram(y=y_percussive, sr=sr)
        tempo_tempogram = librosa.feature.tempo(onset_envelope=tempogram.mean(axis=0), sr=sr)
        if len(tempo_tempogram) > 0 and tempo_tempogram[0] > 0:
            tempo_estimates.append(float(tempo_tempogram[0]))
    except Exception:
        pass

    if not tempo_estimates:
        return {"bpm": None, "confidence": 0.0, "estimates": []}

    # Consensus voting
    tempo_median = float(np.median(tempo_estimates))
    tempo_std = float(np.std(tempo_estimates))

    # Confidence based on agreement
    confidence = 1.0 - min(tempo_std / tempo_median, 1.0) if tempo_median > 0 else 0.0

    # EDM-specific range optimization (most EDM is 110-180 BPM)
    candidates = [tempo_median / 2, tempo_median, tempo_median * 2]
    edm_candidates = [c for c in candidates if 110 <= c <= 180]

    if edm_candidates:
        final_bpm = min(edm_candidates, key=lambda c: abs(c - tempo_median))
    else:
        final_bpm = tempo_median

    return {
        "bpm": round(final_bpm, 1),
        "confidence": round(confidence, 3),
        "estimates": [round(t, 1) for t in tempo_estimates],
        "std_dev": round(tempo_std, 2)
    }


# ===== Sub-Bass & Frequency Analysis =====

def analyze_frequency_bands(y: np.ndarray, sr: int) -> dict[str, float]:
    """
    Analyze energy in different frequency bands (EDM-optimized).

    Args:
        y: Audio time series
        sr: Sample rate

    Returns:
        Dictionary with energy values for different bands
    """
    # Compute STFT
    D = librosa.stft(y)
    S = np.abs(D)

    # Convert to dB
    S_db = librosa.amplitude_to_db(S, ref=np.max)

    # Frequency bins
    freqs = librosa.fft_frequencies(sr=sr)

    # Define bands (EDM-relevant)
    bands = {
        "sub_bass": (20, 60),      # Sub-bass (kick fundamentals)
        "bass": (60, 250),         # Bass (bass lines)
        "low_mid": (250, 500),     # Low mids
        "mid": (500, 2000),        # Mids (synths, vocals)
        "high_mid": (2000, 6000),  # High mids (leads)
        "high": (6000, 16000)      # Highs (hats, cymbals)
    }

    energy = {}
    for band_name, (low_freq, high_freq) in bands.items():
        # Find frequency bins in range
        mask = (freqs >= low_freq) & (freqs <= high_freq)

        # Average energy in band
        if mask.any():
            band_energy = float(np.mean(S_db[mask, :]))
            energy[band_name] = round(band_energy, 2)
        else:
            energy[band_name] = 0.0

    return energy


def calculate_energy_score(y: np.ndarray, sr: int) -> dict[str, float]:
    """
    Calculate overall energy/intensity score.

    Args:
        y: Audio time series
        sr: Sample rate

    Returns:
        Dictionary with energy metrics
    """
    # RMS energy
    rms = librosa.feature.rms(y=y)[0]
    rms_mean = float(np.mean(rms))
    rms_std = float(np.std(rms))

    # Peak energy
    peak = float(np.max(np.abs(y)))

    # Dynamic range
    dynamic_range = float(20 * np.log10(peak / (rms_mean + 1e-10)))

    # Energy score (normalized 0-100)
    energy_score = min(100, rms_mean * 100 * 10)

    return {
        "energy_score": round(energy_score, 2),
        "rms_mean": round(rms_mean, 4),
        "rms_std": round(rms_std, 4),
        "peak": round(peak, 4),
        "dynamic_range": round(dynamic_range, 2)
    }


# ===== Transient Detection =====

def analyze_transients(y: np.ndarray, sr: int) -> dict[str, Any]:
    """
    Analyze percussive transients (kicks, snares, hats).

    Args:
        y: Audio time series
        sr: Sample rate

    Returns:
        Dictionary with transient metrics
    """
    # Detect onsets
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, units='time')

    # Transient density (onsets per second)
    duration = len(y) / sr
    transient_density = len(onsets) / duration if duration > 0 else 0.0

    # Onset strength statistics
    onset_mean = float(np.mean(onset_env))
    onset_std = float(np.std(onset_env))
    onset_max = float(np.max(onset_env))

    return {
        "transient_count": len(onsets),
        "transient_density": round(transient_density, 2),
        "onset_strength_mean": round(onset_mean, 4),
        "onset_strength_std": round(onset_std, 4),
        "onset_strength_max": round(onset_max, 4)
    }


# ===== Enhanced Key Detection =====

def detect_key_enhanced(y: np.ndarray, sr: int) -> dict[str, Any]:
    """
    Enhanced key detection with longer analysis window.

    Args:
        y: Audio time series
        sr: Sample rate

    Returns:
        Dictionary with key info and confidence
    """
    # Use longer hop length for stability
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=4096)

    # Average chroma over time
    chroma_mean = np.mean(chroma, axis=1)

    # Find dominant pitch class
    dominant_pitch = int(np.argmax(chroma_mean))

    # Determine major/minor (simplified heuristic)
    # Compare major vs minor profiles
    major_profile = np.array([1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1])
    minor_profile = np.array([1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0])

    # Rotate profiles to match dominant pitch
    major_rotated = np.roll(major_profile, dominant_pitch)
    minor_rotated = np.roll(minor_profile, dominant_pitch)

    # Correlation
    major_corr = float(np.corrcoef(chroma_mean, major_rotated)[0, 1])
    minor_corr = float(np.corrcoef(chroma_mean, minor_rotated)[0, 1])

    # Key names
    notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    if major_corr > minor_corr:
        key = notes[dominant_pitch]
        confidence = major_corr
    else:
        key = notes[dominant_pitch] + 'm'
        confidence = minor_corr

    # Get Camelot notation
    camelot = key_to_camelot(key)
    compatible = get_compatible_keys(camelot) if camelot else []

    return {
        "key": key,
        "confidence": round(max(confidence, 0.0), 3),
        "camelot": camelot,
        "compatible_keys": compatible,
        "major_correlation": round(major_corr, 3),
        "minor_correlation": round(minor_corr, 3)
    }


# ===== Main EDM Analysis Function =====

def analyze_edm_features(file_path: Path) -> dict[str, Any]:
    """
    Comprehensive EDM-optimized audio analysis.

    Args:
        file_path: Path to audio file

    Returns:
        Dictionary with all EDM-relevant features
    """
    # Load audio
    try:
        y, sr = librosa.load(file_path, sr=44100, mono=True)
    except Exception as e:
        return {"error": str(e)}

    features = {}

    # Enhanced BPM detection
    bpm_info = detect_bpm_multipass(y, sr)
    features["bpm"] = bpm_info["bpm"]
    features["bpm_confidence"] = bpm_info["confidence"]
    features["bpm_estimates"] = bpm_info["estimates"]
    features["bpm_std_dev"] = bpm_info.get("std_dev", 0.0)

    # Enhanced key detection
    key_info = detect_key_enhanced(y, sr)
    features["key"] = key_info["key"]
    features["key_confidence"] = key_info["confidence"]
    features["camelot"] = key_info["camelot"]
    features["compatible_keys"] = key_info["compatible_keys"]

    # Frequency band analysis
    freq_bands = analyze_frequency_bands(y, sr)
    features["frequency_bands"] = freq_bands

    # Energy analysis
    energy = calculate_energy_score(y, sr)
    features["energy"] = energy

    # Transient analysis
    transients = analyze_transients(y, sr)
    features["transients"] = transients

    # Duration
    features["duration"] = len(y) / sr

    return features
