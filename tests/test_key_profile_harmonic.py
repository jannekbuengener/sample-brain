from __future__ import annotations

import math
from pathlib import Path

from src.key_profile_analysis import rank_key_profiles
from src.key_profile_audio_calibration import extract_harmonic_chroma_evidence
from src.key_profile_harmonic import (
    HarmonicProfileFixture,
    benchmark_harmonic_profile_paths,
    evaluate_harmonic_profile_fixtures,
    summarize_harmonic_profile_evaluation,
)
from tests.audio_fixtures import (
    write_hihat_noise_wav,
    write_kick_transient_wav,
    write_key_audio_wav,
    write_mixed_key_audio_wav,
    write_pulse_train_wav,
    write_seeded_noise_wav,
)


NOTE_HZ = {
    "C": 261.63,
    "D": 293.66,
    "E": 329.63,
    "F": 349.23,
    "G": 392.00,
    "A": 440.00,
}


def build_public_harmonic_corpus(work_dir: Path) -> tuple[HarmonicProfileFixture, ...]:
    """Build the documented public Phase-5 corpus without committing audio."""
    fixtures: list[HarmonicProfileFixture] = []
    for root, frequency_hz in NOTE_HZ.items():
        for mode in ("maj", "min"):
            key = f"{root}_{mode}"
            fixtures.append(HarmonicProfileFixture(
                name=f"clear_{key}", group="clear",
                path=write_key_audio_wav(
                    work_dir / f"clear_{key}.wav", frequency_hz=frequency_hz, mode=mode, duration_sec=0.5,
                ),
                root=root, mode=mode,
            ))
            for mix, label in (("kick", "kick"), ("hat", "noise_hat")):
                for strength in ("light", "strong"):
                    fixtures.append(HarmonicProfileFixture(
                        name=f"{strength}_{label}_{key}", group=f"{strength}_{label}",
                        path=write_mixed_key_audio_wav(
                            work_dir / f"{strength}_{label}_{key}.wav",
                            frequency_hz=frequency_hz, mode=mode, mix=mix, strength=strength, duration_sec=0.5,
                        ),
                        root=root, mode=mode,
                    ))

    fixtures.extend((
        HarmonicProfileFixture("pulse", "non_tonal", write_pulse_train_wav(work_dir / "pulse.wav", bpm=120.0)),
        HarmonicProfileFixture("kick", "non_tonal", write_kick_transient_wav(work_dir / "kick.wav", bpm=120.0)),
        HarmonicProfileFixture("noise", "non_tonal", write_seeded_noise_wav(work_dir / "noise.wav")),
        HarmonicProfileFixture("hat", "non_tonal", write_hihat_noise_wav(work_dir / "hat.wav")),
    ))
    return tuple(fixtures)


def test_hpss_evidence_is_deterministic_finite_and_bounded(tmp_path: Path) -> None:
    path = write_key_audio_wav(tmp_path / "clear.wav", frequency_hz=261.63, mode="maj")
    first = extract_harmonic_chroma_evidence(path)
    second = extract_harmonic_chroma_evidence(path)
    assert first.harmonic_energy_fraction == second.harmonic_energy_fraction
    assert first.harmonic_rms == second.harmonic_rms
    assert first.percussive_rms == second.percussive_rms
    assert 0.0 <= first.harmonic_energy_fraction <= 1.0
    assert first.harmonic_rms >= 0.0 and first.percussive_rms >= 0.0
    assert rank_key_profiles(first.chroma_mean if first.chroma_mean is not None else ()).root == "C"


def test_noise_is_not_a_production_key_claim(tmp_path: Path) -> None:
    evidence = extract_harmonic_chroma_evidence(write_seeded_noise_wav(tmp_path / "noise.wav"))
    assert 0.0 <= evidence.harmonic_energy_fraction <= 1.0


def test_public_mixed_corpus_covers_six_major_and_minor_roots(tmp_path: Path) -> None:
    fixtures = build_public_harmonic_corpus(tmp_path)
    clear = [fixture for fixture in fixtures if fixture.group == "clear"]

    assert len({fixture.root for fixture in clear if fixture.mode == "maj"}) >= 6
    assert len({fixture.root for fixture in clear if fixture.mode == "min"}) >= 6
    assert {fixture.group for fixture in fixtures} == {
        "clear", "light_kick", "strong_kick", "light_noise_hat", "strong_noise_hat", "non_tonal",
    }


def test_full_and_harmonic_synthetic_aggregates_are_deterministic_and_complete(tmp_path: Path) -> None:
    fixtures = build_public_harmonic_corpus(tmp_path)
    evaluations = evaluate_harmonic_profile_fixtures(
        fixture for fixture in fixtures if fixture.root == "C"
    )
    first = summarize_harmonic_profile_evaluation(evaluations)
    second = summarize_harmonic_profile_evaluation(evaluations)

    assert first == second
    assert set(first["groups"]) == {
        "clear", "light_kick", "strong_kick", "light_noise_hat", "strong_noise_hat",
    }
    for group in first["groups"].values():
        assert group["fixture_count"] == 2
        for path in ("full", "harmonic"):
            for metric in ("root_accuracy", "mode_accuracy", "full_key_accuracy"):
                value = group[path][metric]
                assert value["comparable_count"] == 2
                assert 0 <= value["correct_count"] <= 2

    transition = first["transitions"]
    assert set(transition) == {
        "full_correct_to_harmonic_correct",
        "full_correct_to_harmonic_wrong",
        "full_wrong_to_harmonic_correct",
        "full_wrong_to_harmonic_wrong",
    }
    assert sum(transition.values()) == 10


def test_non_tonal_diagnostics_are_finite_and_do_not_claim_accuracy(tmp_path: Path) -> None:
    fixtures = build_public_harmonic_corpus(tmp_path)
    summary = summarize_harmonic_profile_evaluation(
        evaluate_harmonic_profile_fixtures(fixture for fixture in fixtures if fixture.group == "non_tonal")
    )

    diagnostics = summary["non_tonal_diagnostics"]
    assert diagnostics["fixture_count"] == 4
    assert "root_accuracy" not in diagnostics
    # TEST_CONTRACT_FIX: abstained profile rankings have no score margin; do not invent one.
    for distribution, missing_key in (
        (diagnostics["full_profile_margin"], "full_profile_no_margin_count"),
        (diagnostics["harmonic_profile_margin"], "harmonic_profile_no_margin_count"),
    ):
        assert distribution["count"] + diagnostics[missing_key] == 4
        assert distribution["count"] > 0
        assert all(math.isfinite(distribution[key]) for key in ("min", "median", "p95", "max"))
    assert diagnostics["harmonic_energy_fraction"]["count"] == 4
    assert all(math.isfinite(diagnostics["harmonic_energy_fraction"][key]) for key in ("min", "median", "p95", "max"))
    assert 0.0 <= diagnostics["harmonic_energy_fraction"]["min"] <= 1.0
    assert 0.0 <= diagnostics["harmonic_energy_fraction"]["max"] <= 1.0


def test_harmonic_benchmark_is_positive_and_has_a_stable_report_shape(tmp_path: Path) -> None:
    fixtures = build_public_harmonic_corpus(tmp_path)[:4]
    report = benchmark_harmonic_profile_paths(fixtures, warmup_count=1)

    assert report["warmup_file_count"] == 1
    assert report["file_count"] == 4
    assert set(report) == {
        "warmup_file_count", "file_count", "full_median_ms", "full_p95_ms",
        "harmonic_median_ms", "harmonic_p95_ms", "harmonic_to_full_ratio", "additive_delta_ms",
    }
    assert all(math.isfinite(report[key]) and report[key] > 0.0 for key in (
        "full_median_ms", "full_p95_ms", "harmonic_median_ms", "harmonic_p95_ms", "harmonic_to_full_ratio",
    ))
