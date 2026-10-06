"""#960 portable analyzer evidence projection contracts."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from src.analyze import _serialize_key_mode_evidence
from src.beat_grid import BeatGridSeries
from src.portable_analyzer_projection import (
    ANALYZER_PORTABLE_SURFACE_IDS,
    PortableProjectionError,
    assert_no_privacy_leaks,
    dumps_portable_evidence,
    ensure_finite_float_vector,
    project_portable_value,
)


def test_surface_inventory_covers_aq_families() -> None:
    assert "bpm_beatgrid" in ANALYZER_PORTABLE_SURFACE_IDS
    assert "key_mode_tonality" in ANALYZER_PORTABLE_SURFACE_IDS
    assert "onset_gesture" in ANALYZER_PORTABLE_SURFACE_IDS
    assert "classification_type_tags" in ANALYZER_PORTABLE_SURFACE_IDS
    assert "search_ranking" in ANALYZER_PORTABLE_SURFACE_IDS
    assert "harmonic_match" in ANALYZER_PORTABLE_SURFACE_IDS
    assert "structure_arrangement" in ANALYZER_PORTABLE_SURFACE_IDS
    assert "loudness_brightness_mfcc_chroma" in ANALYZER_PORTABLE_SURFACE_IDS
    assert len(ANALYZER_PORTABLE_SURFACE_IDS) == 8


def test_dumps_portable_evidence_is_deterministic_and_rejects_nan() -> None:
    payload = {
        "suite": "analyzer_portable_output_baseline",
        "bpm": None,
        "key_conf": 0.5,
        "status": "ok",
    }
    first = dumps_portable_evidence(payload)
    second = dumps_portable_evidence({"status": "ok", "key_conf": 0.5, "bpm": None, "suite": payload["suite"]})
    assert first == second
    assert "bpm" in first
    roundtrip = json.loads(first)
    assert roundtrip["bpm"] is None
    assert roundtrip["key_conf"] == 0.5

    with pytest.raises(PortableProjectionError, match="non-finite"):
        dumps_portable_evidence({"score": float("nan")})
    with pytest.raises(PortableProjectionError, match="non-finite"):
        dumps_portable_evidence({"score": float("inf")})


def test_project_rejects_runtime_objects_and_bytes() -> None:
    with pytest.raises(PortableProjectionError, match="Path"):
        project_portable_value(Path("C:/Users/example/private.wav"))
    with pytest.raises(PortableProjectionError, match="bytes"):
        project_portable_value(b"\x00\x01")
    with pytest.raises(PortableProjectionError, match="set"):
        project_portable_value({"a", "b"})


def test_privacy_leak_guard_rejects_absolute_paths() -> None:
    with pytest.raises(PortableProjectionError, match="absolute/private path"):
        assert_no_privacy_leaks({"sample_ref": r"D:\Samples\kick.wav"})
    with pytest.raises(PortableProjectionError, match="absolute/private path"):
        assert_no_privacy_leaks({"sample_ref": "/home/user/kit/snare.wav"})
    # Any POSIX absolute path — not only a curated root allowlist.
    with pytest.raises(PortableProjectionError, match="absolute/private path"):
        assert_no_privacy_leaks({"sample_ref": "/workspace/alice/private.wav"})
    with pytest.raises(PortableProjectionError, match="absolute/private path"):
        assert_no_privacy_leaks({"sample_ref": "/var/lib/private.wav"})
    with pytest.raises(PortableProjectionError, match="absolute/private path"):
        assert_no_privacy_leaks({"sample_ref": r"\\server\share\kick.wav"})
    with pytest.raises(PortableProjectionError, match="absolute/private path"):
        assert_no_privacy_leaks({"sample_ref": "file:///home/user/sample.wav"})
    assert_no_privacy_leaks({"public_sample_id": "42", "status": "ok"})
    assert_no_privacy_leaks({"rel": "fixtures/public/kick.wav", "status": "ok"})


def test_finite_vector_contract_for_mfcc_chroma_shapes() -> None:
    mfcc = ensure_finite_float_vector(list(range(13)), field="mfcc_mean", expected_len=13)
    chroma = ensure_finite_float_vector([0.1] * 12, field="chroma_mean", expected_len=12)
    assert len(mfcc) == 13
    assert len(chroma) == 12
    with pytest.raises(PortableProjectionError, match="length"):
        ensure_finite_float_vector([1.0, 2.0], field="mfcc_mean", expected_len=13)
    with pytest.raises(PortableProjectionError, match="non-finite"):
        ensure_finite_float_vector([1.0, float("nan")], field="chroma_mean")


def test_v1_key_mode_evidence_serialization_rejects_nan() -> None:
    evidence = {
        "kind": "third_contrast",
        "major_third_energy": 0.1,
        "minor_third_energy": 0.2,
        "contrast": float("nan"),
        "threshold": 0.15,
        "mode": None,
    }
    with pytest.raises(ValueError):
        _serialize_key_mode_evidence(evidence)


def test_beat_grid_series_still_rejects_non_finite_times() -> None:
    with pytest.raises(ValueError, match="finite"):
        BeatGridSeries(
            status="ok",
            sample_indices=(0, 1),
            times_sec=(0.0, float("nan")),
        )


def test_none_miss_is_not_coerced_to_zero() -> None:
    projected = project_portable_value({"bpm": None, "loudness": None})
    assert projected == {"bpm": None, "loudness": None}
    assert projected["bpm"] is None


def test_gesture_zero_vector_requires_explicit_status_for_portable_use() -> None:
    """Gesture fail-soft zeros remain domain semantics; portable use needs status."""
    zero_features = [0.0] * 15
    ensure_finite_float_vector(zero_features, field="feature_vector", expected_len=15)
    # Zero alone is serializable but must not be labeled measured-ok without status.
    portable = dumps_portable_evidence(
        {
            "surface": "onset_gesture",
            "status": "empty",
            "feature_vector": zero_features,
        }
    )
    body = json.loads(portable)
    assert body["status"] == "empty"
    assert body["feature_vector"] == zero_features
    assert math.isfinite(sum(body["feature_vector"]))


def test_numpy_scalar_is_rejected_until_explicitly_projected() -> None:
    with pytest.raises(PortableProjectionError, match="unsupported runtime type"):
        project_portable_value(np.float32(1.25))
