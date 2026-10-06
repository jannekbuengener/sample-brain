"""Frozen contract tests for analyzer semantic determinism (#959).

DOCS → TESTS → TEST FREEZE: these assertions encode
docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md and must not be reshaped
to fit a wrong implementation.
"""

from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest

from src.analyzer_semantic_determinism import (
    CONTRACT_ID,
    CONTRACT_VERSION,
    InvalidSemanticValueError,
    SHAPE_RANKED_RETRIEVAL,
    SHAPE_TRACK_ANALYSIS,
    VOLATILE_FIELD_KEYS,
    compare_semantic,
    describe_capabilities,
    project_semantic,
)


def _track_analysis_payload(*, bpm: float = 120.0, fingerprint: str = "fp-a") -> dict:
    return {
        "analyzer_context": {"analysis_fingerprint": fingerprint},
        "overall_status": "ok",
        "musical": {
            "bpm": {
                "status": "ok",
                "value": bpm,
                "unit": "bpm",
                "normalization": "none",
                "source_ref": "analyze",
            },
            "key": {
                "status": "ok",
                "root": "C",
                "mode": "major",
                "key_conf": 0.8,
                "source_ref": "analyze",
            },
        },
        "audio_summary": {
            "loudness": {
                "status": "ok",
                "value": -12.5,
                "unit": "dBFS",
                "method": "global_rms",
                "source_ref": "analyze",
            },
            "brightness": {
                "status": "ok",
                "value": 1800.0,
                "unit": "Hz",
                "method": "mean_spectral_centroid",
                "source_ref": "analyze",
            },
        },
        "quality_notes": [],
    }


def _ranked_payload(
    *,
    fingerprint: str = "rank-fp",
    first_id: str = "s1",
    second_id: str = "s2",
) -> dict:
    return {
        "analyzer_context": {"analysis_fingerprint": fingerprint},
        "status": "ok",
        "rankings": [
            {
                "cluster_id": 0,
                "ranked": [
                    {"sample_id": first_id, "distance": 0.1, "rank": 1},
                    {"sample_id": second_id, "distance": 0.1, "rank": 2},
                ],
            }
        ],
    }


def test_capabilities_declare_shapes_and_volatile_keys() -> None:
    caps = describe_capabilities()
    assert caps["contract_id"] == CONTRACT_ID
    assert caps["contract_version"] == CONTRACT_VERSION
    assert SHAPE_TRACK_ANALYSIS in caps["shapes"]
    assert SHAPE_RANKED_RETRIEVAL in caps["shapes"]
    declared = set(caps["volatile_fields"])
    assert declared == set(VOLATILE_FIELD_KEYS)
    for key in (
        "timestamp",
        "run_id",
        "duration_ms",
        "source_path",
        "username",
        "cache_status",
        "cache_key",
    ):
        assert key in declared


def test_identical_track_analysis_results_are_equal() -> None:
    left = _track_analysis_payload()
    right = copy.deepcopy(left)
    result = compare_semantic(left, right, shape=SHAPE_TRACK_ANALYSIS)
    assert result.outcome == "equal"
    assert result.mismatches == ()


def test_volatile_metadata_only_still_equal() -> None:
    left = {
        **_track_analysis_payload(),
        "timestamp": "2026-01-01T00:00:00Z",
        "run_id": "run-1",
        "attempt": 1,
        "duration_ms": 42.0,
        "source_path": r"D:\Users\alice\private\track.wav",
        "username": "alice",
        "cache_status": "miss",
        "cache_key": "abc123",
    }
    right = {
        **_track_analysis_payload(),
        "timestamp": "2026-10-06T12:00:00Z",
        "run_id": "run-9",
        "attempt": 99,
        "duration_ms": 9001.0,
        "source_path": r"C:\Users\bob\other\track.wav",
        "username": "bob",
        "hostname": "studio-b",
        "cache_status": "hit",
        "cache_key": "zzz999",
    }
    result = compare_semantic(left, right, shape=SHAPE_TRACK_ANALYSIS)
    assert result.outcome == "equal"
    projection = project_semantic(left, shape=SHAPE_TRACK_ANALYSIS)
    for volatile in ("timestamp", "run_id", "source_path", "username", "cache_status"):
        assert volatile not in projection
        assert volatile not in projection.get("analyzer_context", {})


def test_decision_relevant_value_change_is_mismatch() -> None:
    left = _track_analysis_payload(bpm=120.0)
    right = _track_analysis_payload(bpm=121.0)
    result = compare_semantic(left, right, shape=SHAPE_TRACK_ANALYSIS)
    assert result.outcome == "mismatch"
    paths = {item.path for item in result.mismatches}
    assert "musical.bpm.value" in paths


def test_status_change_is_mismatch() -> None:
    left = _track_analysis_payload()
    right = copy.deepcopy(left)
    right["musical"]["bpm"] = {
        "status": "no_result",
        "reason_code": "BPM_UNDETECTABLE",
        "source_ref": "analyze",
    }
    right["overall_status"] = "partial"
    result = compare_semantic(left, right, shape=SHAPE_TRACK_ANALYSIS)
    assert result.outcome == "mismatch"
    paths = {item.path for item in result.mismatches}
    assert "musical.bpm.status" in paths or "overall_status" in paths


def test_ranked_tie_order_is_significant() -> None:
    left = _ranked_payload(first_id="s1", second_id="s2")
    right = _ranked_payload(first_id="s2", second_id="s1")
    result = compare_semantic(left, right, shape=SHAPE_RANKED_RETRIEVAL)
    assert result.outcome == "mismatch"
    paths = {item.path for item in result.mismatches}
    assert any(path.startswith("rankings[0].ranked[") for path in paths)


def test_ranked_identical_including_tie_order_is_equal() -> None:
    left = _ranked_payload()
    right = copy.deepcopy(left)
    result = compare_semantic(left, right, shape=SHAPE_RANKED_RETRIEVAL)
    assert result.outcome == "equal"


def test_cache_hit_vs_fresh_equivalent_via_same_projection() -> None:
    analysis = _track_analysis_payload(fingerprint="shared-fp")
    fresh = {
        "cache_status": "miss",
        "cache_key": "fresh-key",
        "timestamp": "2026-01-01T00:00:00Z",
        "track_map": {"analysis": analysis},
        "analyzer_context": {"analysis_fingerprint": "shared-fp"},
    }
    cached = {
        "cache_status": "hit",
        "cache_key": "cached-key",
        "duration_ms": 0.5,
        "source_path": r"D:\Users\alice\library\song.wav",
        "track_map": {"analysis": copy.deepcopy(analysis)},
        "analyzer_context": {"analysis_fingerprint": "shared-fp"},
    }
    result = compare_semantic(fresh, cached, shape=SHAPE_TRACK_ANALYSIS)
    assert result.outcome == "equal"


def test_incompatible_analyzer_context_is_explicit() -> None:
    left = _track_analysis_payload(fingerprint="fp-a")
    right = _track_analysis_payload(fingerprint="fp-b")
    result = compare_semantic(left, right, shape=SHAPE_TRACK_ANALYSIS)
    assert result.outcome == "incompatible"
    assert result.mismatches == ()
    assert "fingerprint" in (result.reason or "").lower() or "context" in (
        result.reason or ""
    ).lower()


def test_non_finite_values_fail_closed() -> None:
    left = _track_analysis_payload()
    right = copy.deepcopy(left)
    right["musical"]["bpm"]["value"] = math.nan
    result = compare_semantic(left, right, shape=SHAPE_TRACK_ANALYSIS)
    assert result.outcome == "invalid"
    assert result.mismatches == ()


def test_positive_infinity_fails_closed_on_ranked_distance() -> None:
    payload = _ranked_payload()
    payload["rankings"][0]["ranked"][0]["distance"] = math.inf
    with pytest.raises(InvalidSemanticValueError):
        project_semantic(payload, shape=SHAPE_RANKED_RETRIEVAL)
    compare = compare_semantic(payload, _ranked_payload(), shape=SHAPE_RANKED_RETRIEVAL)
    assert compare.outcome == "invalid"


def test_missing_required_semantic_field_is_not_ignored() -> None:
    left = _track_analysis_payload()
    right = copy.deepcopy(left)
    del right["musical"]["key"]
    result = compare_semantic(left, right, shape=SHAPE_TRACK_ANALYSIS)
    assert result.outcome in {"mismatch", "invalid"}
    if result.outcome == "mismatch":
        paths = {item.path for item in result.mismatches}
        assert any("musical.key" in path for path in paths)


def test_two_shapes_reuse_same_compare_seam() -> None:
    track = compare_semantic(
        _track_analysis_payload(),
        _track_analysis_payload(),
        shape=SHAPE_TRACK_ANALYSIS,
    )
    ranked = compare_semantic(
        _ranked_payload(),
        _ranked_payload(),
        shape=SHAPE_RANKED_RETRIEVAL,
    )
    assert track.outcome == "equal"
    assert ranked.outcome == "equal"
    assert track.__class__ is ranked.__class__


def test_projection_is_portable_without_host_paths() -> None:
    wrapped = {
        **_track_analysis_payload(),
        "source_path": str(Path.home() / "private" / "track.wav"),
        "username": "local-user",
    }
    projection = project_semantic(wrapped, shape=SHAPE_TRACK_ANALYSIS)
    blob = str(projection)
    assert "private" not in blob
    assert "local-user" not in blob
    assert "source_path" not in projection


def _real_track_map_payload(
    *,
    bpm: float = 120.0,
    fingerprint: str = "fp-real",
    note_code: str | None = None,
) -> dict:
    notes = []
    if note_code is not None:
        notes.append(
            {
                "code": note_code,
                "severity": "warning",
                "path": "/analysis",
                "message": "short audio",
            }
        )
    return {
        "document_type": "sample_brain.track_map",
        "analysis": {
            "status": "ok",
            "musical": {
                "bpm": {
                    "status": "ok",
                    "value": bpm,
                    "unit": "bpm",
                    "normalization": "none",
                    "source_ref": "analyze",
                },
                "key": {
                    "status": "ok",
                    "root": "C",
                    "mode": "major",
                    "key_conf": 0.8,
                    "source_ref": "analyze",
                },
            },
            "audio_summary": {
                "loudness": {
                    "status": "ok",
                    "value": -12.5,
                    "unit": "dBFS",
                    "method": "global_rms",
                    "source_ref": "analyze",
                },
                "brightness": {
                    "status": "ok",
                    "value": 1800.0,
                    "unit": "Hz",
                    "method": "mean_spectral_centroid",
                    "source_ref": "analyze",
                },
            },
        },
        "provenance": {
            "components": {
                "analyze": {
                    "configuration": {"parameter_fingerprint": fingerprint},
                }
            }
        },
        "quality": {"notes": notes},
    }


def test_real_track_map_status_and_quality_notes_project() -> None:
    left = _real_track_map_payload(note_code="SHORT_AUDIO")
    right = copy.deepcopy(left)
    equal = compare_semantic(left, right, shape=SHAPE_TRACK_ANALYSIS)
    assert equal.outcome == "equal"
    projection = project_semantic(left, shape=SHAPE_TRACK_ANALYSIS)
    assert projection["overall_status"] == "ok"
    assert projection["quality_notes"][0]["code"] == "SHORT_AUDIO"

    drifted = _real_track_map_payload(note_code="OTHER_NOTE")
    mismatch = compare_semantic(left, drifted, shape=SHAPE_TRACK_ANALYSIS)
    assert mismatch.outcome == "mismatch"
    assert any("quality_notes" in item.path for item in mismatch.mismatches)


def test_exact_numeric_type_and_signed_zero_mismatch() -> None:
    left = _ranked_payload()
    right = copy.deepcopy(left)
    right["rankings"][0]["ranked"][0]["distance"] = -0.0
    left["rankings"][0]["ranked"][0]["distance"] = 0.0
    result = compare_semantic(left, right, shape=SHAPE_RANKED_RETRIEVAL)
    assert result.outcome == "mismatch"


def test_overflow_numeric_is_invalid_not_crash() -> None:
    payload = _ranked_payload()
    payload["rankings"][0]["ranked"][0]["distance"] = 10**1000
    with pytest.raises(InvalidSemanticValueError):
        project_semantic(payload, shape=SHAPE_RANKED_RETRIEVAL)
    compare = compare_semantic(payload, _ranked_payload(), shape=SHAPE_RANKED_RETRIEVAL)
    assert compare.outcome == "invalid"
