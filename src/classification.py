"""Neutral sample-classification computation with no catalog/index ownership."""

from __future__ import annotations

import math

import numpy as np

def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))

# ---------- Regelbasierte Autotypisierung ----------
# Default thresholds are production identity. Optional kwargs exist only so
# AQ4 candidate-compare adapters (#1034) can declare thin config variants
# without changing production defaults when callers omit them.
_RULE_SHORT_MAX_SEC = 0.35
_RULE_MID_MAX_SEC = 1.2
_RULE_LONG_MIN_SEC = 2.5
_RULE_BRIGHT_MIN = 4500.0
_RULE_DARK_MAX = 1500.0
_RULE_PUNCHY_MIN_LOUDNESS = -18.0


def rule_type(
    duration,
    loudness,
    brightness,
    mfcc_mean_blob,
    clazz,
    *,
    short_max_sec: float = _RULE_SHORT_MAX_SEC,
    mid_max_sec: float = _RULE_MID_MAX_SEC,
    long_min_sec: float = _RULE_LONG_MIN_SEC,
    bright_min: float = _RULE_BRIGHT_MIN,
    dark_max: float = _RULE_DARK_MAX,
    punchy_min_loudness: float = _RULE_PUNCHY_MIN_LOUDNESS,
) -> list[str]:
    tags: list[str] = []
    mfcc = None
    if mfcc_mean_blob:
        try: mfcc = np.frombuffer(mfcc_mean_blob, dtype=np.float32)
        except Exception: mfcc = None

    is_short  = (duration is not None and duration < short_max_sec)
    is_mid    = (
        duration is not None and short_max_sec <= duration <= mid_max_sec
    )
    is_long   = (duration is not None and duration > long_min_sec)
    is_bright = (brightness is not None and brightness > bright_min)
    is_dark   = (brightness is not None and brightness < dark_max)
    is_punchy = (loudness  is not None and loudness  > punchy_min_loudness)
    low_energy = (mfcc is not None and mfcc.shape[0] >= 2 and mfcc[1] > 0.0)

    if clazz == "oneshot":
        if is_short and is_dark and is_punchy and low_energy: tags.append("Kick")
        elif is_short and is_bright and is_punchy:            tags.append("HiHat-Closed")
        elif is_mid and (is_bright or is_punchy):             tags.append("Snare")
        elif is_long and is_dark and not is_bright:           tags.append("Drone")
        elif is_long and is_bright:                           tags.append("Impact")
        else:                                                 tags.append("OneShot")
    else:
        if is_bright and not is_long: tags.append("Drum Loop")
        elif is_long and is_dark:     tags.append("Drone")
        else:                          tags.append("Loop")

    if is_bright: tags.append("Bright")
    if is_dark:   tags.append("Dark")
    if is_punchy: tags.append("Punchy")
    if is_long and "Drone" not in tags: tags.append("Atmospheric")

    core: list[str] = []
    for t in ("Kick","Snare","HiHat-Closed","Impact","Drone","Pad","Loop","OneShot","Drum Loop"):
        if t in tags: core.append(t)
    if not core:
        core = ["FX"] if (clazz == "oneshot") else ["Loop"]
    for t in ("Bright","Dark","Punchy","Atmospheric"):
        if t in tags and len(core) < 5: core.append(t)
    return core

def _knn_predict(qvec: np.ndarray, X: np.ndarray, y: np.ndarray, topk=7):
    q = qvec.astype(np.float32); q /= (np.linalg.norm(q)+1e-9)
    sims = X @ q
    idx = np.argsort(-sims)[:topk]
    labs = y[idx]; scs = sims[idx]
    from collections import defaultdict
    agg = defaultdict(float)
    for L,S in zip(labs, scs): agg[L] += float(max(0.0, S))
    best = sorted(agg.items(), key=lambda x: -x[1])
    scores = np.array([s for _,s in best], dtype=np.float32)
    conf = float(_sigmoid(scores[0])) if scores.size else 0.0
    return dict(label=best[0][0], confidence=conf)

__all__ = [
    "rule_type",
]
