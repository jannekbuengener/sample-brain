"""Explicit V2 key-analysis persistence facade over the neutral compute owner."""

from __future__ import annotations

import numpy as np

from .feature_analysis import _chroma_mean, estimate_key_mode
from .joint_key_profile import rank_joint_key_profiles
from .db import (
    KeyAnalysisFeatureRecord,
    read_key_analysis_feature_row,
    read_key_analysis_feature_rows,
    read_key_analysis_v2_shadow_row,
    write_key_analysis_v2_features_row,
    write_key_analysis_v2_shadow_row,
)
from .key_analysis_v2_core import (
    KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION,
    KeyAnalysisV2Result,
    _estimate_key_v2_shadow_with,
    serialize_key_analysis_v2_evidence,
)
from .key_signature import format_key_signature

def estimate_key_v2_shadow(y: np.ndarray, sr: int) -> KeyAnalysisV2Result | None:
    """Compatibility facade preserving legacy monkeypatch seams for V2 compute."""

    return _estimate_key_v2_shadow_with(
        y,
        sr,
        chroma_mean_fn=_chroma_mean,
        rank_fn=rank_joint_key_profiles,
        mode_fn=estimate_key_mode,
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
