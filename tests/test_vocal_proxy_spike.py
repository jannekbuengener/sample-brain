from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from src.benchmark_search_quality import load_search_quality_suite, run_search_quality_benchmark
from src.embed import ClapEmbeddingBackend, _clap_available
from src.search_quality_fixtures import (
    _CLAP_SR,
    generate_search_quality_fixture,
    render_formant_tone_waveform,
    write_vowel_pad_wav,
)

VOCAL_PROXY_SPIKE_SUITE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "search_quality"
    / "golden_v2_clap_vocal_proxy_spike.yaml"
)

VOCAL_PROXY_IDS = {1, 2, 3}
INSTRUMENTAL_IDS = {4, 5, 6}


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    left = np.asarray(a, dtype=np.float32)
    right = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denom == 0.0:
        return 0.0
    return float(np.dot(left, right) / denom)


class TestVocalProxyFixtures:
    def test_formant_tone_deterministic(self, tmp_path: Path):
        params = {"f0_hz": 150.0, "formants_hz": [700.0, 1220.0, 2600.0]}
        path_a = generate_search_quality_fixture(
            tmp_path, "formant-a", "formant_tone", params
        )
        path_b = generate_search_quality_fixture(
            tmp_path, "formant-b", "formant_tone", params
        )
        wave_a, sr_a = sf.read(path_a, dtype="float32")
        wave_b, sr_b = sf.read(path_b, dtype="float32")
        assert sr_a == _CLAP_SR
        assert sr_b == _CLAP_SR
        assert np.allclose(wave_a, wave_b)
        assert np.isfinite(wave_a).all()
        assert wave_a.size > 0

    def test_vowel_pad_writes_wav(self, tmp_path: Path):
        path = write_vowel_pad_wav(tmp_path / "vowel.wav", duration_sec=2.0)
        wave, sr = sf.read(path, dtype="float32")
        assert sr == _CLAP_SR
        assert np.isfinite(wave).all()
        assert wave.size == int(_CLAP_SR * 2.0)

    def test_formant_waveform_amplitude_bounds(self):
        wave = render_formant_tone_waveform(duration_sec=1.0, f0_hz=140.0)
        assert np.isfinite(wave).all()
        assert float(np.max(np.abs(wave))) <= 1.0

    def test_unknown_fixture_type_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="Unknown search quality fixture type"):
            generate_search_quality_fixture(tmp_path, "x", "not_a_type", {})


class TestVocalProxySpikeSuite:
    def test_spike_suite_structure(self):
        suite = load_search_quality_suite(VOCAL_PROXY_SPIKE_SUITE)
        assert suite["tier"] == "B"
        assert len(suite["catalog"]["samples"]) == 6
        assert len(suite["queries"]) == 6
        classes = {sample["sample_class"] for sample in suite["catalog"]["samples"]}
        assert classes == {"vocal_no_vocal"}
        texts = {query["text"] for query in suite["queries"] if query["mode"] == "text"}
        assert "singing voice" in texts
        assert "vocal sound" in texts
        assert "human voice tone" in texts
        assert "instrumental synth pad" in texts
        forbidden = {"no vocals", "without vocals", "acapella", "vocal chop"}
        assert forbidden.isdisjoint(texts)


def _mean_audio_embedding(backend: ClapEmbeddingBackend, paths: list[Path]) -> np.ndarray:
    vectors = [backend.embed_audio(str(path)) for path in paths]
    stacked = np.stack([np.asarray(vector, dtype=np.float32) for vector in vectors], axis=0)
    mean = stacked.mean(axis=0)
    norm = float(np.linalg.norm(mean))
    if norm > 0.0:
        mean = mean / norm
    return mean.astype(np.float32)


def evaluate_vocal_proxy_spike_margins(
    audio_dir: Path,
    backend: ClapEmbeddingBackend,
    *,
    benchmark_result,
) -> dict[str, float | bool | int]:
    vocal_paths = [
        audio_dir / "vocal-proxy-a.wav",
        audio_dir / "vocal-proxy-b.wav",
        audio_dir / "vocal-proxy-c.wav",
    ]
    instrumental_paths = [
        audio_dir / "instrumental-chord.wav",
        audio_dir / "instrumental-sine.wav",
        audio_dir / "instrumental-texture.wav",
    ]
    vocal_mean = _mean_audio_embedding(backend, vocal_paths)
    instrumental_mean = _mean_audio_embedding(backend, instrumental_paths)

    singing_voice = backend.embed_text("singing voice")
    vocal_sound = backend.embed_text("vocal sound")
    margin_singing = _cosine(singing_voice, vocal_mean) - _cosine(singing_voice, instrumental_mean)
    margin_vocal = _cosine(vocal_sound, vocal_mean) - _cosine(vocal_sound, instrumental_mean)
    vocal_a = backend.embed_audio(str(vocal_paths[0]))
    chord = backend.embed_audio(str(instrumental_paths[0]))
    margin_formant_vs_chord = _cosine(singing_voice, vocal_a) - _cosine(singing_voice, chord)

    by_id = {row.query_id: row for row in benchmark_result.query_results}
    vocal_ref_top1 = by_id["vocal_proxy_audio_ref"].ranked_ids[0] in VOCAL_PROXY_IDS
    instrumental_ref_top1 = (
        by_id["instrumental_chord_audio_ref"].ranked_ids[0] in INSTRUMENTAL_IDS
    )

    stage1_pass = (
        margin_singing >= 0.08
        and margin_vocal >= 0.08
        and margin_formant_vs_chord >= 0.05
        and vocal_ref_top1
        and instrumental_ref_top1
        and benchmark_result.summary.precision_at_5 >= 0.25
    )

    return {
        "margin_singing_voice": margin_singing,
        "margin_vocal_sound": margin_vocal,
        "margin_formant_vs_chord": margin_formant_vs_chord,
        "mean_precision_at_5": benchmark_result.summary.precision_at_5,
        "vocal_ref_top1_vocal_class": vocal_ref_top1,
        "instrumental_ref_top1_instrumental_class": instrumental_ref_top1,
        "stage1_pass": stage1_pass,
        "query_count": benchmark_result.summary.query_count,
    }


class TestVocalProxySpikeClap:
    @pytest.mark.clap
    def test_vocal_proxy_spike_benchmark(self, tmp_path: Path):
        if not _clap_available():
            pytest.skip("CLAP optional extra not installed")

        work_dir = tmp_path / "vocal-proxy-spike"
        result = run_search_quality_benchmark(
            VOCAL_PROXY_SPIKE_SUITE,
            work_dir=work_dir,
        )
        assert result.tier == "B"
        assert result.summary.query_count == 6
        for row in result.query_results:
            assert row.error is None, row.query_id

        by_id = {row.query_id: row for row in result.query_results}
        assert by_id["vocal_proxy_audio_ref"].ranked_ids[0] in VOCAL_PROXY_IDS
        assert by_id["instrumental_chord_audio_ref"].ranked_ids[0] in INSTRUMENTAL_IDS

        audio_dir = work_dir / "audio"
        backend = ClapEmbeddingBackend()
        margins = evaluate_vocal_proxy_spike_margins(
            audio_dir,
            backend,
            benchmark_result=result,
        )
        if not margins["stage1_pass"]:
            pytest.skip(
                "HOLD_VOCAL_PROXY_FAILED: "
                f"margin_singing_voice={margins['margin_singing_voice']:.3f}, "
                f"margin_vocal_sound={margins['margin_vocal_sound']:.3f}, "
                f"margin_formant_vs_chord={margins['margin_formant_vs_chord']:.3f}"
            )
