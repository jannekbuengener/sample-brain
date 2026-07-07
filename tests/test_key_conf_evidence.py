from __future__ import annotations

import pytest

from src.export_fl import CONF_KEY_MIN, key_to_tag
from src.key_conf_evidence import (
    KeyConfEvidenceResult,
    KeyConfSampleRecord,
    _bucket_for_conf,
    run_key_conf_evidence,
)


class TestBucketForConf:
    def test_low_bucket(self):
        assert _bucket_for_conf(0.10) == "lt_0.40"

    def test_mid_low_bucket(self):
        assert _bucket_for_conf(0.45) == "0.40_0.55"

    def test_mid_high_bucket(self):
        assert _bucket_for_conf(0.60) == "0.55_0.70"

    def test_high_bucket(self):
        assert _bucket_for_conf(0.85) == "gte_0.70"


class TestKeyToTag:
    def test_high_confidence_exports_key(self):
        assert key_to_tag("A", 0.88) == "Amaj"

    def test_below_threshold_withholds_key(self):
        assert key_to_tag("A", 0.40) is None

    def test_at_threshold_exports_key(self):
        assert key_to_tag("C", CONF_KEY_MIN) == "Cmaj"

    def test_missing_key_returns_none(self):
        assert key_to_tag(None, 0.90) is None

    def test_missing_confidence_withholds_key(self):
        assert key_to_tag("A", None) is None

    def test_sharp_key_preserved(self):
        assert key_to_tag("C#", 0.80) == "C#"


class TestKeyConfEvidenceResult:
    def test_bucket_counts_and_export_rate(self):
        result = KeyConfEvidenceResult(
            records=[
                KeyConfSampleRecord("a", "sine", "A", 0.88, "Amaj", "gte_0.70"),
                KeyConfSampleRecord("b", "chord", "C", 0.33, None, "lt_0.40"),
            ]
        )
        assert result.bucket_counts() == {
            "lt_0.40": 1,
            "0.40_0.55": 0,
            "0.55_0.70": 0,
            "gte_0.70": 1,
        }
        assert result.export_rate == 0.5


def test_run_key_conf_evidence_produces_records(tmp_path):
    result = run_key_conf_evidence(tmp_path)
    assert result.total == 17
    assert len(result.with_conf) == result.total
    assert result.min_conf is not None
    assert 0.0 < result.min_conf <= result.median_conf <= result.max_conf <= 1.0
    assert sum(result.bucket_counts().values()) == len(result.with_conf)
