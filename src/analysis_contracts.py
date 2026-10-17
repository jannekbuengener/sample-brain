"""Neutral shared contracts for Sample Brain analysis computation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast


ANALYZE_SR = 44100
ANALYZE_HOP_LENGTH = 512
KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION = 2

BPMNormalizationMode = Literal["none", "heuristic", "domain_110_170"]
VALID_BPM_NORMALIZATION_MODES = frozenset(
    {"none", "heuristic", "domain_110_170"}
)


def validate_bpm_normalization(mode: str) -> BPMNormalizationMode:
    """Validate and return one of the frozen analyzer BPM-normalization modes."""
    if mode not in VALID_BPM_NORMALIZATION_MODES:
        raise ValueError(f"Unsupported BPM normalization mode: {mode!r}")
    return cast(BPMNormalizationMode, mode)


@dataclass(frozen=True)
class Features:
    """Neutral feature-analysis result shared by analysis consumers."""

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


__all__ = [
    "ANALYZE_HOP_LENGTH",
    "ANALYZE_SR",
    "KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION",
    "BPMNormalizationMode",
    "VALID_BPM_NORMALIZATION_MODES",
    "Features",
    "validate_bpm_normalization",
]
