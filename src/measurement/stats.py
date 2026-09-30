"""Deterministic percentile helpers for Measurement reports (stdlib only)."""

from __future__ import annotations

import math
from typing import Optional, Sequence


def percentile(values: Sequence[float | int], p: float) -> Optional[float]:
    """Linear-interpolation percentile on a sorted copy.

    ``p`` is in ``[0, 100]``. Empty input → ``None``. Single value → that value
    for any ``p``.
    """
    if not values:
        return None
    if p < 0.0 or p > 100.0 or math.isnan(p):
        raise ValueError("percentile p must be in [0, 100]")
    xs = sorted(float(v) for v in values)
    if len(xs) == 1:
        return xs[0]
    rank = (p / 100.0) * (len(xs) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return xs[lo]
    weight = rank - lo
    return xs[lo] * (1.0 - weight) + xs[hi] * weight
