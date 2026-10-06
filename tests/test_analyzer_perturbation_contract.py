"""Frozen contract tests for analyzer perturbation fixtures (#957).

DOCS → TESTS → TEST FREEZE: these assertions encode
docs/ANALYZER_PERTURBATION_FIXTURE_CONTRACT.md and must not be reshaped
to fit a wrong implementation.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from src.analyzer_perturbation import (
    CONTRACT_ID,
    CONTRACT_VERSION,
    UnsupportedTransformError,
    ValidationError,
    compute_derived_identity,
    describe_capabilities,
    materialize_derived_fixture,
    validate_transform_spec,
)
from src.content_hash import compute_file_hash
from tests.audio_fixtures import write_sine_wav


def _spec(*steps: dict) -> dict:
    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "transforms": list(steps),
    }


def test_capabilities_declare_supported_and_unsupported_transforms() -> None:
    caps = describe_capabilities()
    assert caps["contract_id"] == CONTRACT_ID
    assert caps["contract_version"] == CONTRACT_VERSION
    supported = set(caps["supported"])
    unsupported = set(caps["unsupported"])
    assert {
        "gain",
        "peak_normalize",
        "to_mono",
        "to_stereo",
        "resample",
        "pad_silence",
        "trim",
        "pitch_shift",
        "time_stretch",
    } <= supported
    assert "energy_trim_silence" in unsupported
    assert supported.isdisjoint(unsupported)


def test_same_source_and_spec_yield_same_derived_identity(tmp_path: Path) -> None:
    src = write_sine_wav(tmp_path / "src.wav", duration_sec=0.25, frequency_hz=440.0)
    spec = _spec({"id": "gain", "version": "1", "params": {"factor": 0.5}})
    id_a = compute_derived_identity(src, spec)
    id_b = compute_derived_identity(src, spec)
    assert id_a == id_b
    assert len(id_a) == 64


def test_transform_order_changes_derived_identity(tmp_path: Path) -> None:
    src = write_sine_wav(tmp_path / "src.wav", duration_sec=0.25, frequency_hz=220.0)
    first = _spec(
        {"id": "gain", "version": "1", "params": {"factor": 0.5}},
        {
            "id": "pad_silence",
            "version": "1",
            "params": {"leading_samples": 100, "trailing_samples": 0},
        },
    )
    second = _spec(
        {
            "id": "pad_silence",
            "version": "1",
            "params": {"leading_samples": 100, "trailing_samples": 0},
        },
        {"id": "gain", "version": "1", "params": {"factor": 0.5}},
    )
    assert compute_derived_identity(src, first) != compute_derived_identity(src, second)


def test_semantic_identity_ignores_output_path_and_host_paths(tmp_path: Path) -> None:
    src = write_sine_wav(tmp_path / "src.wav", duration_sec=0.2, frequency_hz=330.0)
    spec = _spec({"id": "gain", "version": "1", "params": {"factor": 0.25}})
    out_a = tmp_path / "nested" / "a" / "derived.wav"
    out_b = tmp_path / "other place" / "b" / "derived.wav"
    prov_a = materialize_derived_fixture(src, spec, out_a)
    prov_b = materialize_derived_fixture(src, spec, out_b)
    assert prov_a["derived_identity"] == prov_b["derived_identity"]
    assert prov_a["derived_identity"] == compute_derived_identity(src, spec)
    portable = {
        k: prov_a[k]
        for k in (
            "contract_id",
            "contract_version",
            "source",
            "transforms",
            "derived_identity",
        )
    }
    dumped = str(portable)
    assert str(tmp_path) not in dumped
    assert ":\\" not in dumped.lower() or "content_hash" in dumped
    assert "users" not in dumped.lower()
    assert portable["source"]["content_hash"] == compute_file_hash(src)


def test_materialize_never_mutates_source(tmp_path: Path) -> None:
    src = write_sine_wav(tmp_path / "src.wav", duration_sec=0.3, frequency_hz=100.0)
    before = src.read_bytes()
    before_hash = compute_file_hash(src)
    spec = _spec(
        {"id": "gain", "version": "1", "params": {"factor": 0.1}},
        {
            "id": "pad_silence",
            "version": "1",
            "params": {"leading_samples": 500, "trailing_samples": 500},
        },
    )
    out = tmp_path / "derived.wav"
    materialize_derived_fixture(src, spec, out)
    assert src.read_bytes() == before
    assert compute_file_hash(src) == before_hash
    assert out.is_file()
    assert out.resolve() != src.resolve()


def test_no_hidden_normalization_on_gain_only(tmp_path: Path) -> None:
    src = write_sine_wav(
        tmp_path / "src.wav",
        duration_sec=0.2,
        frequency_hz=440.0,
        amplitude=0.4,
    )
    y0, sr0 = sf.read(str(src), dtype="float32", always_2d=True)
    factor = 0.5
    out = tmp_path / "gained.wav"
    materialize_derived_fixture(
        src,
        _spec({"id": "gain", "version": "1", "params": {"factor": factor}}),
        out,
    )
    y1, sr1 = sf.read(str(out), dtype="float32", always_2d=True)
    assert sr1 == sr0
    assert y1.shape == y0.shape
    np.testing.assert_allclose(y1, y0 * factor, rtol=0.0, atol=1e-4)


def test_pcm16_gain_that_would_clip_fails_closed(tmp_path: Path) -> None:
    src = write_sine_wav(
        tmp_path / "src.wav",
        duration_sec=0.2,
        frequency_hz=440.0,
        amplitude=0.8,
    )
    out = tmp_path / "clip.wav"
    with pytest.raises(ValidationError, match="would clip"):
        materialize_derived_fixture(
            src,
            _spec({"id": "gain", "version": "1", "params": {"factor": 2.0}}),
            out,
        )
    assert not out.exists()
    # Source must remain untouched when materialization fails closed.
    y0, _ = sf.read(str(src), dtype="float32", always_2d=True)
    assert float(np.max(np.abs(y0))) == pytest.approx(0.8, abs=1e-3)


def test_hard_link_destination_rejected(tmp_path: Path) -> None:
    src = write_sine_wav(tmp_path / "src.wav", duration_sec=0.2, frequency_hz=100.0)
    linked = tmp_path / "hardlink.wav"
    try:
        linked.hardlink_to(src)
    except OSError:
        pytest.skip("hard links unavailable on this filesystem")
    before = src.read_bytes()
    with pytest.raises(ValidationError, match="hard link|same inode"):
        materialize_derived_fixture(
            src,
            _spec({"id": "gain", "version": "1", "params": {"factor": 0.5}}),
            linked,
        )
    assert src.read_bytes() == before


def test_invalid_and_non_finite_params_fail_closed() -> None:
    with pytest.raises(ValidationError):
        validate_transform_spec(
            _spec({"id": "gain", "version": "1", "params": {"factor": math.nan}})
        )
    with pytest.raises(ValidationError):
        validate_transform_spec(
            _spec({"id": "gain", "version": "1", "params": {"factor": math.inf}})
        )
    with pytest.raises(ValidationError):
        validate_transform_spec(
            _spec({"id": "gain", "version": "1", "params": {"factor": 0.0}})
        )
    with pytest.raises(ValidationError):
        validate_transform_spec(
            _spec(
                {
                    "id": "time_stretch",
                    "version": "1",
                    "params": {"rate": -1.0},
                }
            )
        )
    with pytest.raises(ValidationError):
        validate_transform_spec(
            _spec(
                {
                    "id": "pad_silence",
                    "version": "1",
                    "params": {"leading_samples": -1, "trailing_samples": 0},
                }
            )
        )
    with pytest.raises(UnsupportedTransformError):
        validate_transform_spec(
            _spec(
                {
                    "id": "energy_trim_silence",
                    "version": "1",
                    "params": {"threshold_db": -40.0},
                }
            )
        )


def test_resample_and_channel_transforms_are_explicit(tmp_path: Path) -> None:
    src = write_sine_wav(tmp_path / "src.wav", duration_sec=0.25, frequency_hz=440.0)
    mono_path = tmp_path / "still_mono.wav"
    materialize_derived_fixture(
        src,
        _spec({"id": "to_mono", "version": "1", "params": {"method": "mean"}}),
        mono_path,
    )
    info_mono = sf.info(str(mono_path))
    assert info_mono.channels == 1

    stereo_path = tmp_path / "stereo.wav"
    materialize_derived_fixture(
        src,
        _spec({"id": "to_stereo", "version": "1", "params": {"method": "duplicate"}}),
        stereo_path,
    )
    info_stereo = sf.info(str(stereo_path))
    assert info_stereo.channels == 2

    resampled = tmp_path / "22k.wav"
    materialize_derived_fixture(
        src,
        _spec({"id": "resample", "version": "1", "params": {"target_sr": 22050}}),
        resampled,
    )
    assert sf.info(str(resampled)).samplerate == 22050
