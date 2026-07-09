"""Workbench attack/onset suggestion — analysis-only, never modifies originals."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from .workbench_waveform import clamp_cue_start_ms, read_audio_duration_ms

_FRAME_MS = 10
_ENERGY_RATIO_THRESHOLD = 0.2
_PEAK_FRACTION_THRESHOLD = 0.05
_SILENCE_PEAK = 1e-6
_CLEAR_RISE_RATIO = 5.0


@dataclass(frozen=True)
class AttackSuggestion:
    """Suggested attack position; user must explicitly accept before persisting."""

    attack_ms: int
    method: str
    confidence: str
    reason: str


def _mono_samples(data: np.ndarray) -> np.ndarray:
    samples = np.asarray(data, dtype=np.float32)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    return samples


def _frame_rms_values(samples: np.ndarray, *, sr: int, frame_ms: int) -> np.ndarray:
    frame_samples = max(1, int(sr * frame_ms / 1000.0))
    if samples.size == 0:
        return np.zeros(0, dtype=np.float32)
    pad = (-samples.size) % frame_samples
    if pad:
        padded = np.pad(samples, (0, pad))
    else:
        padded = samples
    frames = padded.reshape(-1, frame_samples)
    return np.sqrt(np.mean(frames * frames, axis=1)).astype(np.float32)


def _confidence_for_attack(
    *,
    attack_frame: int,
    attack_ms: int,
    rms_values: np.ndarray,
    threshold: float,
) -> tuple[str, str]:
    if rms_values.size == 0:
        return "low", "Keine Energieframes — Vorschlag unsicher."

    max_rms = float(np.max(rms_values))
    if attack_frame == 0 and max_rms >= threshold:
        return "high", "Transient beginnt nahe am Dateianfang."

    if attack_frame == 0:
        return "medium", "Energie ab dem ersten Frame — Vorschlag prüfen."

    pre_rms = float(np.mean(rms_values[:attack_frame]))
    post_rms = float(rms_values[attack_frame])
    ratio = post_rms / (pre_rms + 1e-12)
    if ratio >= _CLEAR_RISE_RATIO:
        return "medium", f"Energieanstieg nach ~{attack_ms} ms Vorlauf/Stille."

    return "low", "Schwacher oder unklarer Anstieg — nur als Hinweis."


def suggest_attack_ms(path: Path | str, *, frame_ms: int = _FRAME_MS) -> AttackSuggestion | None:
    """Suggest an attack/onset time in milliseconds without modifying *path*."""
    if frame_ms <= 0:
        raise ValueError("frame_ms must be positive")

    resolved = Path(path)
    if not resolved.is_file():
        return None

    duration_ms = read_audio_duration_ms(resolved)
    if duration_ms is None:
        return None

    try:
        data, sr = sf.read(resolved, dtype="float32", always_2d=False)
    except Exception:
        return None

    samples = _mono_samples(data)
    if samples.size == 0:
        return None

    peak = float(np.max(np.abs(samples)))
    if peak <= _SILENCE_PEAK:
        return AttackSuggestion(
            attack_ms=0,
            method="energy_threshold",
            confidence="low",
            reason="Signal ist praktisch stumm — Vorschlag unsicher.",
        )

    rms_values = _frame_rms_values(samples, sr=sr, frame_ms=frame_ms)
    if rms_values.size == 0:
        return None

    max_rms = float(np.max(rms_values))
    threshold = max(max_rms * _ENERGY_RATIO_THRESHOLD, peak * _PEAK_FRACTION_THRESHOLD)

    attack_frame = 0
    for index, value in enumerate(rms_values):
        if float(value) >= threshold:
            attack_frame = index
            break

    frame_samples = max(1, int(sr * frame_ms / 1000.0))
    attack_ms = int(round(attack_frame * frame_samples / sr * 1000.0))
    attack_ms = clamp_cue_start_ms(attack_ms, duration_ms)

    confidence, reason = _confidence_for_attack(
        attack_frame=attack_frame,
        attack_ms=attack_ms,
        rms_values=rms_values,
        threshold=threshold,
    )
    return AttackSuggestion(
        attack_ms=attack_ms,
        method="energy_threshold",
        confidence=confidence,
        reason=reason,
    )


__all__ = ["AttackSuggestion", "suggest_attack_ms"]
