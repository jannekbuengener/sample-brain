from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import yaml

from src.benchmark_search_quality import load_search_quality_suite
from src.search_quality_contract import (
    is_private_absolute_path,
    validate_search_quality_suite,
)
from src.search_quality_fixtures import (
    CLAP_SAMPLE_RATE,
    DEFAULT_FIXTURE_RECIPES_PATH,
    build_fixture_generation_report_row,
    generate_all_recipe_fixtures,
    generate_catalog_fixtures,
    generate_fixture_from_recipe,
    generate_search_quality_fixture,
    list_tier_b_recipe_fixture_ids,
    load_fixture_recipes,
    render_electronic_scene_waveform,
    render_formant_tone_waveform,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_SUITE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "search_quality" / "golden_v2_clap.yaml"
)


def _read_pcm(path: Path) -> tuple[np.ndarray, int]:
    data, sr = sf.read(path, dtype="float32", always_2d=False)
    return np.asarray(data, dtype=np.float32), int(sr)


def _assert_audio_basics(wave: np.ndarray, sr: int, *, duration_sec: float) -> None:
    assert sr == CLAP_SAMPLE_RATE
    assert wave.ndim == 1
    expected_samples = int(round(duration_sec * sr))
    assert abs(wave.shape[0] - expected_samples) <= 1
    assert np.isfinite(wave).all()
    assert float(np.max(np.abs(wave))) > 1e-6
    assert float(np.max(np.abs(wave))) <= 1.0


class TestFixtureDeterminism:
    def test_same_recipe_produces_identical_pcm(self, tmp_path: Path):
        params = {"f0_hz": 150.0, "formants_hz": [700.0, 1220.0, 2600.0]}
        path_a = generate_search_quality_fixture(
            tmp_path, "formant-a", "formant_tone", params
        )
        path_b = generate_search_quality_fixture(
            tmp_path, "formant-b", "formant_tone", params
        )
        wave_a, sr_a = _read_pcm(path_a)
        wave_b, sr_b = _read_pcm(path_b)
        assert sr_a == sr_b == CLAP_SAMPLE_RATE
        assert np.array_equal(wave_a, wave_b)

    def test_different_fixture_ids_produce_distinct_audio(self, tmp_path: Path):
        vocal = render_formant_tone_waveform(duration_sec=1.0, f0_hz=150.0)
        electronic = render_electronic_scene_waveform(
            duration_sec=1.0, variant="dark", seed=301
        )
        assert vocal.shape == electronic.shape
        assert not np.allclose(vocal, electronic)

    def test_fixed_seed_is_deterministic(self, tmp_path: Path):
        wave_a = render_electronic_scene_waveform(duration_sec=2.0, seed=99)
        wave_b = render_electronic_scene_waveform(duration_sec=2.0, seed=99)
        assert np.array_equal(wave_a, wave_b)


class TestFixtureAudioProperties:
    @pytest.mark.parametrize("fixture_id", list_tier_b_recipe_fixture_ids())
    def test_recipe_fixtures_meet_audio_basics(self, tmp_path: Path, fixture_id: str):
        recipes = load_fixture_recipes()
        recipe = recipes["recipes"][fixture_id]
        path = generate_fixture_from_recipe(tmp_path, fixture_id)
        wave, sr = _read_pcm(path)
        _assert_audio_basics(wave, sr, duration_sec=float(recipe["duration_sec"]))

    def test_generation_report_fields(self, tmp_path: Path):
        path = generate_fixture_from_recipe(tmp_path, "vocal-formant-a")
        row = build_fixture_generation_report_row("vocal-formant-a", path, tmp_path)
        assert row.fixture_id == "vocal-formant-a"
        assert row.relative_filename.endswith(".wav")
        assert row.byte_size > 0
        assert row.sample_rate == CLAP_SAMPLE_RATE
        assert row.channels == 1
        assert 0.0 < row.peak_abs <= 1.0
        assert len(row.sha256) == 64


class TestFixtureRecipeManifest:
    def test_all_vocal_fixture_ids_unique(self):
        ids = list_tier_b_recipe_fixture_ids(query_class="vocal_no_vocal")
        assert len(ids) == len(set(ids))
        assert len(ids) >= 6

    def test_all_genre_fixture_ids_unique(self):
        ids = list_tier_b_recipe_fixture_ids(query_class="genre_mood")
        assert len(ids) == len(set(ids))
        assert len(ids) >= 6

    def test_positive_and_negative_roles_do_not_overlap(self):
        data = load_fixture_recipes()
        vocal = data["recipes"]
        positives = {
            fid
            for fid, recipe in vocal.items()
            if recipe.get("query_class") == "vocal_no_vocal"
            and recipe.get("role") == "positive_candidate"
        }
        hard_negs = {
            fid
            for fid, recipe in vocal.items()
            if recipe.get("query_class") == "vocal_no_vocal"
            and recipe.get("role") == "hard_negative_candidate"
        }
        assert positives.isdisjoint(hard_negs)
        assert len(positives) >= 3
        assert len(hard_negs) >= 2


class TestFixtureErrorsAndPaths:
    def test_unknown_fixture_id_rejected(self, tmp_path: Path):
        with pytest.raises(ValueError, match="Unknown fixture_id"):
            generate_fixture_from_recipe(tmp_path, "not-a-real-fixture")

    def test_unknown_fixture_type_rejected(self, tmp_path: Path):
        with pytest.raises(ValueError, match="Unknown search quality fixture type"):
            generate_search_quality_fixture(tmp_path, "x", "not_a_type", {})

    def test_invalid_output_directory_rejected(self, tmp_path: Path):
        blocked = tmp_path / "blocked.txt"
        blocked.write_text("not a dir", encoding="utf-8")
        with pytest.raises(ValueError, match="not a directory"):
            generate_fixture_from_recipe(blocked, "vocal-formant-a")

    @pytest.mark.parametrize(
        "bad_dir",
        [
            r"C:\Users\janne\fixtures",
            "/Users/janne/fixtures",
            "/home/janne/fixtures",
        ],
    )
    def test_private_absolute_paths_flagged(self, bad_dir: str):
        assert is_private_absolute_path(bad_dir)

    def test_portable_relative_fixture_references_in_golden(self):
        suite = load_search_quality_suite(GOLDEN_SUITE_PATH)
        fixture_names = {
            sample["fixture_name"] for sample in suite["catalog"]["samples"]
        }
        for query in suite["queries"]:
            ref = query.get("query_audio_fixture")
            if ref:
                assert ref in fixture_names


class TestGoldenIntegration:
    def test_all_golden_catalog_fixtures_generate(self, tmp_path: Path):
        suite = load_search_quality_suite(GOLDEN_SUITE_PATH)
        paths = generate_catalog_fixtures(tmp_path / "audio", suite)
        assert len(paths) == len(
            {s["fixture_name"] for s in suite["catalog"]["samples"]}
        )

    def test_golden_contract_remains_valid(self):
        suite = load_search_quality_suite(GOLDEN_SUITE_PATH)
        validated = validate_search_quality_suite(suite)
        assert validated.tier == "B"

    def test_existing_four_query_classes_unchanged(self):
        suite = load_search_quality_suite(GOLDEN_SUITE_PATH)
        classes = {query.get("query_class") for query in suite["queries"]}
        assert classes >= {
            "kick_snare_perc",
            "pad_texture",
            "riser_impact",
            "dry_wet",
        }

    def test_vocal_and_genre_classes_present(self):
        suite = load_search_quality_suite(GOLDEN_SUITE_PATH)
        classes = {query.get("query_class") for query in suite["queries"]}
        assert "vocal_no_vocal" in classes
        assert "genre_mood" in classes
        present = set(suite.get("query_classes_present") or [])
        assert "vocal_no_vocal" in present
        assert "genre_mood" in present
        pending = set(suite.get("query_classes_pending") or [])
        assert "vocal_no_vocal" not in pending
        assert "genre_mood" not in pending

    def test_all_golden_fixture_names_have_known_types(self):
        suite = load_search_quality_suite(GOLDEN_SUITE_PATH)
        allowed = {
            "kick_transient",
            "pulse_train",
            "perc_hit",
            "sine_tone",
            "chord_pad",
            "texture_noise",
            "freq_sweep_riser",
            "impact_hit",
            "wet_reverb",
            "formant_tone",
            "vowel_pad",
            "electronic_scene",
            "ambient_scene",
            "cinematic_tension_scene",
            "warm_harmonic_scene",
            "aggressive_perc_scene",
        }
        for sample in suite["catalog"]["samples"]:
            assert sample["fixture_type"] in allowed


class TestFixtureSafety:
    def test_no_wav_left_in_repo_after_generation(self, tmp_path: Path):
        generate_all_recipe_fixtures(tmp_path / "runtime-audio")
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        assert ".wav" not in status.stdout.lower()

    def test_reproducible_fixture_smoke_hashes_match(self, tmp_path: Path):
        out_a = tmp_path / "run-a"
        out_b = tmp_path / "run-b"
        rows_a = generate_all_recipe_fixtures(out_a)
        rows_b = generate_all_recipe_fixtures(out_b)
        by_id_a = {row.fixture_id: row for row in rows_a}
        by_id_b = {row.fixture_id: row for row in rows_b}
        assert by_id_a.keys() == by_id_b.keys()
        for fixture_id in by_id_a:
            assert by_id_a[fixture_id].sha256 == by_id_b[fixture_id].sha256

    def test_fixture_generation_does_not_import_clap(self, tmp_path: Path):
        code = """
import sys
from pathlib import Path
sys.path.insert(0, r'{root}')
from src.search_quality_fixtures import generate_all_recipe_fixtures
generate_all_recipe_fixtures(Path(r'{out}'))
assert 'torch' not in sys.modules
""".format(root=REPO_ROOT, out=tmp_path / "isolated")
        subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            cwd=REPO_ROOT,
        )


class TestRecipeFile:
    def test_recipe_file_loads(self):
        data = load_fixture_recipes(DEFAULT_FIXTURE_RECIPES_PATH)
        assert data["version"] == 1
        assert "recipes" in data

    def test_every_recipe_has_required_contract_fields(self):
        data = load_fixture_recipes()
        required = {
            "fixture_id",
            "query_class",
            "fixture_type",
            "role",
            "duration_sec",
            "expected_filename",
        }
        for fixture_id, recipe in data["recipes"].items():
            missing = required - set(recipe)
            assert not missing, f"{fixture_id} missing {missing}"

    def test_golden_new_samples_reference_recipe_ids(self):
        suite = yaml.safe_load(GOLDEN_SUITE_PATH.read_text(encoding="utf-8"))
        recipe_ids = set(load_fixture_recipes()["recipes"])
        new_samples = [
            sample
            for sample in suite["catalog"]["samples"]
            if sample.get("sample_class") in {"vocal_no_vocal", "genre_mood"}
        ]
        assert new_samples
        for sample in new_samples:
            assert sample["fixture_name"] in recipe_ids
