from __future__ import annotations

import numpy as np
import pytest

from src.analyze import _extract_bpm_scalar, normalize_bpm
from src.config_loader import ConfigError, resolve_profile


class TestNormalizeBpm:
    def test_none_returns_none(self):
        assert normalize_bpm(None, mode="none") is None
        assert normalize_bpm(None, mode="heuristic") is None

    def test_zero_returns_none(self):
        assert normalize_bpm(0.0, mode="none") is None
        assert normalize_bpm(0.0, mode="heuristic") is None

    def test_negative_returns_none(self):
        assert normalize_bpm(-10.0, mode="none") is None
        assert normalize_bpm(-10.0, mode="heuristic") is None

    def test_none_mode_passthrough(self):
        assert normalize_bpm(100.0, mode="none") == 100.0
        assert normalize_bpm(87.6, mode="none") == 87.6
        assert normalize_bpm(220.0, mode="none") == 220.0

    def test_heuristic_below_90_doubled(self):
        assert normalize_bpm(87.6, mode="heuristic") == 175.2
        assert normalize_bpm(60.0, mode="heuristic") == 120.0
        assert normalize_bpm(89.9, mode="heuristic") == 179.8

    def test_heuristic_above_200_halved(self):
        assert normalize_bpm(220.0, mode="heuristic") == 110.0
        assert normalize_bpm(280.0, mode="heuristic") == 140.0

    def test_heuristic_in_range_unchanged(self):
        assert normalize_bpm(120.0, mode="heuristic") == pytest.approx(120.0)
        assert normalize_bpm(90.0, mode="heuristic") == 90.0
        assert normalize_bpm(200.0, mode="heuristic") == 200.0

    def test_heuristic_boundary_at_90_stays(self):
        assert normalize_bpm(90.0, mode="heuristic") == 90.0

    def test_heuristic_boundary_at_200_stays(self):
        assert normalize_bpm(200.0, mode="heuristic") == 200.0

    def test_invalid_mode_returns_none(self):
        assert normalize_bpm(120.0, mode="invalid") is None


class TestExtractBpmScalar:
    def test_scalar_float(self):
        assert _extract_bpm_scalar(120.0) == 120.0

    def test_scalar_int(self):
        assert _extract_bpm_scalar(120) == 120.0

    def test_numpy_scalar(self):
        assert _extract_bpm_scalar(np.float64(87.6)) == 87.6

    def test_numpy_0d_array(self):
        val = np.array(87.6)
        assert val.ndim == 0
        assert _extract_bpm_scalar(val) == 87.6

    def test_numpy_1d_single_element(self):
        val = np.array([120.0])
        assert _extract_bpm_scalar(val) == 120.0

    def test_numpy_1d_first_element(self):
        val = np.array([140.0, 160.0])
        assert _extract_bpm_scalar(val) == 140.0

    def test_list_first_element(self):
        assert _extract_bpm_scalar([100.0]) == 100.0

    def test_none_returns_none(self):
        assert _extract_bpm_scalar(None) is None

    def test_empty_array_returns_none(self):
        assert _extract_bpm_scalar(np.array([])) is None

    def test_zero_returns_none(self):
        assert _extract_bpm_scalar(0.0) is None

    def test_negative_returns_none(self):
        assert _extract_bpm_scalar(-50.0) is None

    def test_numpy_1d_multiple_elements(self):
        val = np.array([120.0, 140.0])
        assert _extract_bpm_scalar(val) == 120.0


class TestConfigBpmNormalization:
    def test_default_is_none_when_absent(self, tmp_path):
        example_path = tmp_path / "profiles.example.yaml"
        example_path.write_text(
            "profiles:\n  default:\n    library_roots:\n      - /tmp/samples\n    database:\n      path: data/catalog.db\n"
        )
        config = resolve_profile(
            profile_name="default",
            example_path=example_path,
            local_path=None,
        )
        assert config.get("analyze", {}).get("bpm_normalization", "none") == "none"

    def test_heuristic_accepted(self, tmp_path):
        example_path = tmp_path / "profiles.example.yaml"
        example_path.write_text(
            "profiles:\n  default:\n    library_roots:\n      - /tmp/samples\n    database:\n      path: data/catalog.db\n    analyze:\n      bpm_normalization: heuristic\n"
        )
        config = resolve_profile(
            profile_name="default",
            example_path=example_path,
            local_path=None,
        )
        assert config.get("analyze", {}).get("bpm_normalization") == "heuristic"

    def test_invalid_bpm_normalization_raises(self, tmp_path):
        example_path = tmp_path / "profiles.example.yaml"
        example_path.write_text(
            "profiles:\n  default:\n    library_roots:\n      - /tmp/samples\n    database:\n      path: data/catalog.db\n    analyze:\n      bpm_normalization: clamp\n"
        )
        with pytest.raises(ConfigError, match="bpm_normalization"):
            resolve_profile(
                profile_name="default",
                example_path=example_path,
                local_path=None,
            )

    def test_env_override_bpm_normalization(self, tmp_path):
        example_path = tmp_path / "profiles.example.yaml"
        example_path.write_text(
            "profiles:\n  default:\n    library_roots:\n      - /tmp/samples\n    database:\n      path: data/catalog.db\n    analyze:\n      bpm_normalization: none\n"
        )
        config = resolve_profile(
            profile_name="default",
            example_path=example_path,
            local_path=None,
            env={"SAMPLE_BRAIN_BPM_NORMALIZATION": "heuristic"},
        )
        assert config.get("analyze", {}).get("bpm_normalization") == "heuristic"
