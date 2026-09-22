"""Audio-domain chroma evidence helper for evaluation-only key-profile gates.

It intentionally does not synthesize fixtures or choose a production key. Test
code owns public WAV creation; this helper only follows the analyzer's existing
load and CQT chroma-statistics path.
"""

from __future__ import annotations

from pathlib import Path

from dataclasses import dataclass

import librosa
import numpy as np

from .analyze import extract_chroma_statistics, safe_load


def extract_audio_chroma_statistics(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    """Load one WAV and return the same CQT chroma mean/std as ``extract_features``."""
    y, sr = safe_load(path)
    if y is None or sr is None:
        return None
    return extract_chroma_statistics(y, sr)


@dataclass(frozen=True)
class HarmonicChromaEvidence:
    chroma_mean: np.ndarray | None
    chroma_std: np.ndarray | None
    harmonic_rms: float
    percussive_rms: float
    harmonic_energy_fraction: float


def extract_harmonic_chroma_evidence(path: Path) -> HarmonicChromaEvidence:
    """Evaluation-only HPSS followed by the analyzer's exact CQT aggregation."""
    y, sr = safe_load(path)
    if y is None or sr is None:
        return HarmonicChromaEvidence(None, None, 0.0, 0.0, 0.0)
    try:
        harmonic, percussive = librosa.effects.hpss(y)
        harmonic_energy = float(np.mean(np.square(harmonic)))
        percussive_energy = float(np.mean(np.square(percussive)))
        fraction = harmonic_energy / (harmonic_energy + percussive_energy + 1e-12)
        statistics = extract_chroma_statistics(harmonic, sr)
        return HarmonicChromaEvidence(
            statistics[0] if statistics else None,
            statistics[1] if statistics else None,
            float(np.sqrt(max(0.0, harmonic_energy))),
            float(np.sqrt(max(0.0, percussive_energy))),
            max(0.0, min(1.0, fraction)),
        )
    except Exception:
        return HarmonicChromaEvidence(None, None, 0.0, 0.0, 0.0)


__all__ = ["HarmonicChromaEvidence", "extract_audio_chroma_statistics", "extract_harmonic_chroma_evidence"]
