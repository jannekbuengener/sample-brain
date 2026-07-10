from __future__ import annotations

import math

import pytest

from src.bpm_display import (
    format_bpm_display,
    format_bpm_tag,
    is_valid_bpm,
    round_bpm_display,
)


class TestIsValidBpm:
    @pytest.mark.parametrize(
        "value",
        [None, float("nan"), 0.0, -1.0, -0.1],
    )
    def test_invalid_values(self, value):
        assert is_valid_bpm(value) is False

    def test_valid_positive(self):
        assert is_valid_bpm(120.0) is True
        assert is_valid_bpm(127.6) is True


class TestRoundBpmDisplay:
    def test_rounds_up_from_fraction(self):
        assert round_bpm_display(127.6) == 128

    def test_rounds_down_from_fraction(self):
        assert round_bpm_display(128.4) == 128

    def test_half_up_at_point_five(self):
        assert round_bpm_display(128.5) == 129

    @pytest.mark.parametrize("value", [None, float("nan"), 0.0, -10.0])
    def test_invalid_returns_none(self, value):
        assert round_bpm_display(value) is None


class TestFormatBpmDisplay:
    def test_formats_rounded_integer(self):
        assert format_bpm_display(127.6) == "128"

    def test_invalid_uses_placeholder(self):
        assert format_bpm_display(None) == "—"
        assert format_bpm_display(float("nan")) == "—"
        assert format_bpm_display(0.0) == "—"
        assert format_bpm_display(-1.0) == "—"

    def test_custom_placeholder(self):
        assert format_bpm_display(None, placeholder="n/a") == "n/a"


class TestFormatBpmTag:
    def test_formats_tag(self):
        assert format_bpm_tag(127.6) == "128BPM"

    @pytest.mark.parametrize("value", [None, float("nan"), 0.0, -1.0])
    def test_invalid_returns_none(self, value):
        assert format_bpm_tag(value) is None


class TestDisplayDoesNotUsePythonRound:
    def test_python_round_differs_on_half(self):
        assert round(128.5) == 128
        assert round_bpm_display(128.5) == 129
        assert math.floor(128.5 + 0.5) == 129
