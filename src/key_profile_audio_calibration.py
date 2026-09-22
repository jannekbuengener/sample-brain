"""Audio-domain chroma evidence helper for evaluation-only key-profile gates.

It intentionally does not synthesize fixtures or choose a production key. Test
code owns public WAV creation; this helper only follows the analyzer's existing
load and CQT chroma-statistics path.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .analyze import extract_chroma_statistics, safe_load


def extract_audio_chroma_statistics(path: Path) -> tuple[np.ndarray, np.ndarray] | None:
    """Load one WAV and return the same CQT chroma mean/std as ``extract_features``."""
    y, sr = safe_load(path)
    if y is None or sr is None:
        return None
    return extract_chroma_statistics(y, sr)


__all__ = ["extract_audio_chroma_statistics"]
