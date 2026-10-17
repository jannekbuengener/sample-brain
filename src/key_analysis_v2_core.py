"""Portable V2 key-analysis computation with no catalog persistence dependency."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from .analysis_contracts import KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION
from .feature_analysis import _chroma_mean, estimate_key_mode
from .joint_key_profile import JointKeyProfileError, rank_joint_key_profiles
from .key_signature import format_key_signature

_ROOT_EVIDENCE_KIND = "joint_24_profile_pearson"


@dataclass(frozen=True)
class KeyAnalysisV2Result:
    """One V2 shadow result; raw joint mode is evidence, never product mode."""

    key: str
    root: str
    mode: str | None
    root_evidence: dict[str, Any]
    mode_evidence: dict[str, Any]
    contract_version: int = KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION


def serialize_key_analysis_v2_evidence(evidence: Mapping[str, Any]) -> str:
    """Canonical JSON for V2 evidence without NaN/Inf representations."""

    return json.dumps(
        dict(evidence), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def _estimate_key_v2_shadow_with(
    y: np.ndarray,
    sr: int,
    *,
    chroma_mean_fn,
    rank_fn,
    mode_fn,
) -> KeyAnalysisV2Result | None:
    """Execute the locked V2 algorithm with explicit computation dependencies."""

    chroma_mean = chroma_mean_fn(y, sr)
    if chroma_mean is None:
        return None
    try:
        joint = rank_fn(chroma_mean)
    except JointKeyProfileError:
        return None

    mode, mode_evidence = mode_fn(y, sr, root=joint.root, chroma_mean=chroma_mean)
    if mode_evidence is None:
        return None
    augmented_mode_evidence = dict(mode_evidence)
    augmented_mode_evidence["root"] = joint.root
    augmented_mode_evidence["root_source"] = _ROOT_EVIDENCE_KIND
    root_evidence = {
        "kind": _ROOT_EVIDENCE_KIND,
        "selected_root": joint.root,
        "raw_top_score": joint.raw_score,
        "raw_top_mode": joint.mode,
        "raw_top_mode_authoritative": False,
    }
    key = format_key_signature(joint.root, mode)
    if key is None:
        return None
    return KeyAnalysisV2Result(
        key=key,
        root=joint.root,
        mode=mode,
        root_evidence=root_evidence,
        mode_evidence=augmented_mode_evidence,
    )


def estimate_key_v2_shadow(y: np.ndarray, sr: int) -> KeyAnalysisV2Result | None:
    """Compute the locked V2 hybrid once, without changing the V1 default."""

    return _estimate_key_v2_shadow_with(
        y,
        sr,
        chroma_mean_fn=_chroma_mean,
        rank_fn=rank_joint_key_profiles,
        mode_fn=estimate_key_mode,
    )


__all__ = [
    "KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION",
    "KeyAnalysisV2Result",
    "estimate_key_v2_shadow",
    "serialize_key_analysis_v2_evidence",
]
