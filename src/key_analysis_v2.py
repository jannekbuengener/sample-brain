"""Explicit, non-default V2 key-analysis shadow contract (#642).

The normal analyzer remains V1.  This module is deliberately not imported by
``src.analyze`` and has no automatic consumer path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from .analyze import _chroma_mean, estimate_key_mode
from .db import (
    KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION,
    KeyAnalysisFeatureRecord,
    read_key_analysis_feature_row,
    read_key_analysis_feature_rows,
    read_key_analysis_v2_shadow_row,
    write_key_analysis_v2_features_row,
    write_key_analysis_v2_shadow_row,
)
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


def estimate_key_v2_shadow(y: np.ndarray, sr: int) -> KeyAnalysisV2Result | None:
    """Compute the locked V2 hybrid once, without changing the V1 default.

    The single CQT chroma mean is shared by the joint root ranker and the
    existing third-contrast mode detector.  ``joint.mode`` remains retained
    root evidence only; third contrast exclusively selects the output mode.
    """

    chroma_mean = _chroma_mean(y, sr)
    if chroma_mean is None:
        return None
    try:
        joint = rank_joint_key_profiles(chroma_mean)
    except JointKeyProfileError:
        return None

    mode, mode_evidence = estimate_key_mode(y, sr, root=joint.root, chroma_mean=chroma_mean)
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


def write_key_analysis_v2_features(*, sample_id: int, result: KeyAnalysisV2Result) -> None:
    """Persist an explicitly requested V2 key contract into ``features``.

    This is not the analyzer default. ``key_conf`` is always NULL; unrelated
    non-key feature columns are preserved when a row already exists.
    """

    if result.contract_version != KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION:
        raise ValueError("unsupported V2 key analysis contract version")
    if result.root_evidence.get("selected_root") != result.root:
        raise ValueError("V2 features root does not match root evidence")
    if result.mode_evidence.get("mode") != result.mode:
        raise ValueError("V2 features mode does not match mode evidence")
    if result.key != format_key_signature(result.root, result.mode):
        raise ValueError("V2 features key does not match root and mode")
    write_key_analysis_v2_features_row(
        sample_id=sample_id,
        key=result.key,
        key_mode=result.mode,
        key_root_evidence=result.root_evidence,
        key_mode_evidence=result.mode_evidence,
        contract_version=result.contract_version,
    )


def write_key_analysis_v2_shadow(
    *,
    sample_id: int,
    source_identity: object,
    result: KeyAnalysisV2Result,
    analyzed_at: str | None = None,
) -> None:
    """Persist a caller-requested V2 shadow result; never writes ``features``."""

    if result.contract_version != KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION:
        raise ValueError("unsupported V2 shadow contract version")
    if result.root_evidence.get("selected_root") != result.root:
        raise ValueError("V2 shadow root does not match root evidence")
    write_key_analysis_v2_shadow_row(
        sample_id=sample_id,
        source_identity=source_identity,
        key=result.key,
        key_mode=result.mode,
        key_root_evidence=result.root_evidence,
        key_mode_evidence=result.mode_evidence,
        contract_version=result.contract_version,
        analyzed_at=analyzed_at,
    )


def read_key_analysis_v2_shadow(
    *, sample_id: int, source_identity: object
) -> KeyAnalysisV2Result | None:
    """Read an exact-identity V2 shadow hit, never falling back to V1 data."""

    row = read_key_analysis_v2_shadow_row(sample_id=sample_id, source_identity=source_identity)
    if row is None:
        return None
    if row.key != format_key_signature(row.key_root_evidence["selected_root"], row.key_mode):
        return None
    return KeyAnalysisV2Result(
        key=row.key,
        root=row.key_root_evidence["selected_root"],
        mode=row.key_mode,
        root_evidence=row.key_root_evidence,
        mode_evidence=row.key_mode_evidence or {},
        contract_version=row.contract_version,
    )


__all__ = [
    "KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION",
    "KeyAnalysisFeatureRecord",
    "KeyAnalysisV2Result",
    "estimate_key_v2_shadow",
    "read_key_analysis_feature_row",
    "read_key_analysis_feature_rows",
    "read_key_analysis_v2_shadow",
    "serialize_key_analysis_v2_evidence",
    "write_key_analysis_v2_features",
    "write_key_analysis_v2_shadow",
]
