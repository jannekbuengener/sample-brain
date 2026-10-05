from __future__ import annotations

import numpy as np
import pytest

from src.analyze import _extract_bpm_scalar, normalize_bpm
from src.config_loader import ConfigError, resolve_profile


class TestNormalizeBpm:
    def test_none_returns_none(self):
        assert normalize_bpm(None, mode="none") is None
        assert normalize_bpm(None, mode="heuristic") is None
        assert normalize_bpm(None, mode="domain_110_170") is None

    def test_zero_returns_none(self):
        assert normalize_bpm(0.0, mode="none") is None
        assert normalize_bpm(0.0, mode="heuristic") is None
        assert normalize_bpm(0.0, mode="domain_110_170") is None

    def test_negative_returns_none(self):
        assert normalize_bpm(-10.0, mode="none") is None
        assert normalize_bpm(-10.0, mode="heuristic") is None
        assert normalize_bpm(-10.0, mode="domain_110_170") is None

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


class TestDomain110170Normalization:
    """Frozen #872 contract: explicit techno/dancefloor domain canonicalization."""

    # Frozen PIR-derived edge tolerance (not testset-tuned).
    EFF_LO = 109.316768
    EFF_HI = 170.683232

    def test_in_domain_preservation(self):
        for bpm in (110.0, 120.0, 128.0, 140.0, 150.0, 160.0, 170.0):
            assert normalize_bpm(bpm, mode="domain_110_170") == pytest.approx(bpm)

    def test_boundary_tolerance_keeps_near_edge_values(self):
        assert normalize_bpm(self.EFF_LO, mode="domain_110_170") == pytest.approx(self.EFF_LO)
        assert normalize_bpm(self.EFF_HI, mode="domain_110_170") == pytest.approx(self.EFF_HI)

    def test_half_time_candidates_doubled_into_domain(self):
        assert normalize_bpm(55.0, mode="domain_110_170") == pytest.approx(110.0)
        assert normalize_bpm(72.0, mode="domain_110_170") == pytest.approx(144.0)
        assert normalize_bpm(85.0, mode="domain_110_170") == pytest.approx(170.0)

    def test_regression_849_anonymized_half_tempo(self):
        # Anonymized #849-type raw half (~72.788 -> ~145.577); no private audio.
        raw = 72.78829225352112
        assert normalize_bpm(raw, mode="domain_110_170") == pytest.approx(raw * 2.0)

    def test_boundary_quantization_54978_to_109957(self):
        # Librosa tempo bin nearest 55 doubled lands just below nominal 110.
        raw = 54.978391
        selected = normalize_bpm(raw, mode="domain_110_170")
        assert selected == pytest.approx(raw * 2.0)
        assert self.EFF_LO <= selected <= self.EFF_HI

    def test_outside_frozen_tolerance_not_silently_expanded(self):
        # Just below effective lower edge after doubling must stay fail-closed.
        raw = 54.5  # 2*B = 109.0 < EFF_LO
        assert normalize_bpm(raw, mode="domain_110_170") == pytest.approx(54.5)

    def test_double_time_candidates_halved_into_domain(self):
        assert normalize_bpm(220.0, mode="domain_110_170") == pytest.approx(110.0)
        assert normalize_bpm(280.0, mode="domain_110_170") == pytest.approx(140.0)
        assert normalize_bpm(340.0, mode="domain_110_170") == pytest.approx(170.0)

    def test_out_of_domain_fail_closed_keeps_raw(self):
        for bpm in (50.0, 90.0, 100.0, 180.0, 200.0, 400.0):
            assert normalize_bpm(bpm, mode="domain_110_170") == pytest.approx(bpm)

    def test_domain_mode_does_not_change_none_or_heuristic_semantics(self):
        # Cross-check: heuristic still folds <90 even when 2x is outside domain.
        assert normalize_bpm(89.9, mode="heuristic") == pytest.approx(179.8)
        assert normalize_bpm(89.9, mode="none") == pytest.approx(89.9)
        # 89.9*2 = 179.8 is outside domain -> domain mode keeps raw.
        assert normalize_bpm(89.9, mode="domain_110_170") == pytest.approx(89.9)


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

    def test_domain_110_170_accepted(self, tmp_path):
        example_path = tmp_path / "profiles.example.yaml"
        example_path.write_text(
            "profiles:\n  default:\n    library_roots:\n      - /tmp/samples\n    database:\n      path: data/catalog.db\n    analyze:\n      bpm_normalization: domain_110_170\n"
        )
        config = resolve_profile(
            profile_name="default",
            example_path=example_path,
            local_path=None,
        )
        assert config.get("analyze", {}).get("bpm_normalization") == "domain_110_170"

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

    def test_env_override_domain_110_170(self, tmp_path):
        example_path = tmp_path / "profiles.example.yaml"
        example_path.write_text(
            "profiles:\n  default:\n    library_roots:\n      - /tmp/samples\n    database:\n      path: data/catalog.db\n    analyze:\n      bpm_normalization: none\n"
        )
        config = resolve_profile(
            profile_name="default",
            example_path=example_path,
            local_path=None,
            env={"SAMPLE_BRAIN_BPM_NORMALIZATION": "domain_110_170"},
        )
        assert config.get("analyze", {}).get("bpm_normalization") == "domain_110_170"

    def test_example_profile_default_remains_none(self):
        from pathlib import Path

        example = Path(__file__).resolve().parents[1] / "config" / "profiles.example.yaml"
        config = resolve_profile(
            profile_name="default",
            example_path=example,
            local_path=None,
        )
        assert config.get("analyze", {}).get("bpm_normalization") == "none"


class TestTechnoPerformanceProfile:
    """Frozen #876 contract: explicit opt-in techno/performance named profile."""

    @staticmethod
    def _example_path():
        from pathlib import Path

        return Path(__file__).resolve().parents[1] / "config" / "profiles.example.yaml"

    def test_techno_performance_sets_domain_110_170(self):
        config = resolve_profile(
            profile_name="techno-performance",
            example_path=self._example_path(),
            local_path=None,
        )
        assert config.get("analyze", {}).get("bpm_normalization") == "domain_110_170"

    def test_default_remains_none(self):
        config = resolve_profile(
            profile_name="default",
            example_path=self._example_path(),
            local_path=None,
        )
        assert config.get("analyze", {}).get("bpm_normalization") == "none"

    def test_minimal_demo_remains_none(self):
        config = resolve_profile(
            profile_name="minimal-demo",
            example_path=self._example_path(),
            local_path=None,
        )
        assert config.get("analyze", {}).get("bpm_normalization") == "none"

    def test_selectable_via_env_profile(self):
        config = resolve_profile(
            example_path=self._example_path(),
            local_path=None,
            env={"SAMPLE_BRAIN_PROFILE": "techno-performance"},
        )
        assert config.get("analyze", {}).get("bpm_normalization") == "domain_110_170"

    def test_env_bpm_normalization_overrides_profile(self):
        config = resolve_profile(
            profile_name="techno-performance",
            example_path=self._example_path(),
            local_path=None,
            env={"SAMPLE_BRAIN_BPM_NORMALIZATION": "none"},
        )
        assert config.get("analyze", {}).get("bpm_normalization") == "none"

    def test_unknown_profile_fail_closed(self):
        with pytest.raises(ConfigError, match="Unknown profile"):
            resolve_profile(
                profile_name="techno-performance-typo",
                example_path=self._example_path(),
                local_path=None,
            )

    def test_unknown_mode_fail_closed(self, tmp_path):
        example_path = tmp_path / "profiles.example.yaml"
        example_path.write_text(
            "profiles:\n  techno-performance:\n    library_roots:\n      - /tmp/samples\n"
            "    database:\n      path: data/catalog.db\n"
            "    analyze:\n      bpm_normalization: not_a_mode\n"
        )
        with pytest.raises(ConfigError, match="bpm_normalization"):
            resolve_profile(
                profile_name="techno-performance",
                example_path=example_path,
                local_path=None,
            )
