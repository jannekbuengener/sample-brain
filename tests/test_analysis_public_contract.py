from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest


def test_analysis_contract_freezes_shared_defaults_and_modes() -> None:
    from src.analysis_contracts import (
        ANALYZE_HOP_LENGTH,
        ANALYZE_SR,
        VALID_BPM_NORMALIZATION_MODES,
    )

    assert ANALYZE_SR == 44100
    assert ANALYZE_HOP_LENGTH == 512
    assert VALID_BPM_NORMALIZATION_MODES == frozenset(
        {"none", "heuristic", "domain_110_170"}
    )


@pytest.mark.parametrize("mode", ["none", "heuristic", "domain_110_170"])
def test_validate_bpm_normalization_accepts_current_modes(mode: str) -> None:
    from src.analysis_contracts import validate_bpm_normalization

    assert validate_bpm_normalization(mode) == mode


def test_validate_bpm_normalization_rejects_unknown_mode() -> None:
    from src.analysis_contracts import validate_bpm_normalization

    with pytest.raises(ValueError, match="Unsupported BPM normalization mode"):
        validate_bpm_normalization("future-mode")


def test_features_is_frozen_neutral_result_contract() -> None:
    from src.analysis_contracts import Features

    assert [field.name for field in fields(Features)] == [
        "bpm",
        "key",
        "key_conf",
        "loudness",
        "brightness",
        "mfcc_mean",
        "mfcc_std",
        "chroma_mean",
        "chroma_std",
        "clazz",
        "quality_note",
        "key_mode",
        "key_mode_evidence",
    ]

    result = Features(
        bpm=132.0,
        key="Amin",
        key_conf=0.5,
        loudness=-12.0,
        brightness=2200.0,
        mfcc_mean=None,
        mfcc_std=None,
        chroma_mean=None,
        chroma_std=None,
        clazz="loop",
    )
    with pytest.raises(FrozenInstanceError):
        result.bpm = 133.0  # type: ignore[misc]


def test_analyze_reexports_the_neutral_features_type() -> None:
    from src.analysis_contracts import Features as NeutralFeatures
    from src.analyze import Features as LegacyFeatures

    assert LegacyFeatures is NeutralFeatures


def test_application_config_reexports_neutral_analysis_constants() -> None:
    from src import config
    from src.analysis_contracts import ANALYZE_HOP_LENGTH, ANALYZE_SR

    assert config.ANALYZE_SR == ANALYZE_SR == 44100
    assert config.ANALYZE_HOP_LENGTH == ANALYZE_HOP_LENGTH == 512


def test_config_loader_reuses_single_bpm_normalization_authority() -> None:
    from src import config_loader
    from src.analysis_contracts import VALID_BPM_NORMALIZATION_MODES

    assert config_loader._VALID_BPM_NORMALIZATION_MODES is VALID_BPM_NORMALIZATION_MODES
