from __future__ import annotations

from pathlib import Path

import pytest

from src.benchmark_search_quality import (
    DEFAULT_SUITE_PATH,
    DEFAULT_TIER_B_SUITE_PATH,
    load_search_quality_suite,
)
from src.search_quality_contract import (
    TIER_B_QUERY_CLASSES,
    SearchQualityContractError,
    is_private_absolute_path,
    validate_search_quality_suite,
)


def _tier_b_suite(*, queries: list[dict], samples: list[dict] | None = None) -> dict:
    catalog_samples = samples or [
        {
            "id": 1,
            "fixture_name": "kick-a",
            "fixture_type": "kick_transient",
            "fixture_params": {"bpm": 120},
            "duration": 4.0,
            "pred_type": "kick",
            "sample_class": "kick_snare_perc",
            "tags": ["kick"],
        },
        {
            "id": 2,
            "fixture_name": "pad-a",
            "fixture_type": "sine_tone",
            "fixture_params": {"frequency_hz": 220},
            "duration": 4.0,
            "pred_type": "pad",
            "sample_class": "pad_texture",
            "tags": ["pad"],
        },
    ]
    return {
        "version": 1,
        "tier": "B",
        "embedding_dim": 512,
        "defaults": {"topk": 10, "model_id": 1, "backend": "clap"},
        "catalog": {"samples": catalog_samples},
        "queries": queries,
    }


class TestTierBGoldenContract:
    def test_valid_tier_b_text_query_loads(self):
        suite = _tier_b_suite(
            queries=[
                {
                    "id": "kick_text",
                    "mode": "text",
                    "query_class": "kick_snare_perc",
                    "text": "kick drum",
                    "relevant_sample_ids": [1],
                    "negative_sample_ids": [2],
                }
            ]
        )
        validated = validate_search_quality_suite(suite)
        query = validated.queries[0]
        assert query.mode == "text"
        assert query.query_class == "kick_snare_perc"
        assert query.relevant_sample_ids == (1,)
        assert query.negative_sample_ids == (2,)

    def test_valid_tier_b_audio_query_loads(self):
        suite = _tier_b_suite(
            queries=[
                {
                    "id": "kick_audio",
                    "mode": "audio",
                    "query_class": "kick_snare_perc",
                    "query_audio_fixture": "kick-a",
                    "relevant_sample_ids": [1],
                }
            ]
        )
        validated = validate_search_quality_suite(suite)
        assert validated.queries[0].mode == "audio"

    def test_duplicate_query_id_rejected(self):
        suite = _tier_b_suite(
            queries=[
                {
                    "id": "dup",
                    "mode": "text",
                    "query_class": "kick_snare_perc",
                    "text": "kick",
                    "relevant_sample_ids": [1],
                },
                {
                    "id": "dup",
                    "mode": "text",
                    "query_class": "pad_texture",
                    "text": "pad",
                    "relevant_sample_ids": [2],
                },
            ]
        )
        with pytest.raises(
            SearchQualityContractError, match="duplicate query id"
        ) as exc:
            validate_search_quality_suite(suite)
        assert exc.value.query_id == "dup"

    def test_invalid_query_mode_rejected(self):
        suite = _tier_b_suite(
            queries=[
                {
                    "id": "bad_mode",
                    "mode": "vector",
                    "query_class": "kick_snare_perc",
                    "text": "kick",
                    "relevant_sample_ids": [1],
                }
            ]
        )
        with pytest.raises(
            SearchQualityContractError, match="invalid query mode"
        ) as exc:
            validate_search_quality_suite(suite)
        assert exc.value.query_id == "bad_mode"

    def test_unknown_query_class_rejected(self):
        suite = _tier_b_suite(
            queries=[
                {
                    "id": "bad_class",
                    "mode": "text",
                    "query_class": "unknown_class",
                    "text": "kick",
                    "relevant_sample_ids": [1],
                }
            ]
        )
        with pytest.raises(
            SearchQualityContractError, match="unknown query_class"
        ) as exc:
            validate_search_quality_suite(suite)
        assert exc.value.query_id == "bad_class"

    def test_text_query_with_conflicting_audio_reference_rejected(self):
        suite = _tier_b_suite(
            queries=[
                {
                    "id": "text_audio_conflict",
                    "mode": "text",
                    "query_class": "kick_snare_perc",
                    "text": "kick",
                    "query_audio_fixture": "kick-a",
                    "relevant_sample_ids": [1],
                }
            ]
        )
        with pytest.raises(
            SearchQualityContractError, match="query_audio_fixture"
        ) as exc:
            validate_search_quality_suite(suite)
        assert exc.value.query_id == "text_audio_conflict"

    def test_audio_query_without_portable_reference_rejected(self):
        suite = _tier_b_suite(
            queries=[
                {
                    "id": "audio_missing_fixture",
                    "mode": "audio",
                    "query_class": "kick_snare_perc",
                    "relevant_sample_ids": [1],
                }
            ]
        )
        with pytest.raises(
            SearchQualityContractError, match="query_audio_fixture"
        ) as exc:
            validate_search_quality_suite(suite)
        assert exc.value.query_id == "audio_missing_fixture"

    @pytest.mark.parametrize(
        "path",
        [
            r"C:\Users\janne\samples\kick.wav",
            r"D:/Dev/Workspaces/samples/kick.wav",
            "/Users/janne/samples/kick.wav",
            "/home/janne/samples/kick.wav",
        ],
    )
    def test_private_absolute_paths_rejected(self, path: str):
        assert is_private_absolute_path(path)
        suite = _tier_b_suite(
            samples=[
                {
                    "id": 1,
                    "path": path,
                    "fixture_name": "kick-a",
                    "fixture_type": "kick_transient",
                    "duration": 4.0,
                    "pred_type": "kick",
                    "sample_class": "kick_snare_perc",
                }
            ],
            queries=[
                {
                    "id": "catalog_private_path",
                    "mode": "text",
                    "query_class": "kick_snare_perc",
                    "text": "kick",
                    "relevant_sample_ids": [1],
                }
            ],
        )
        with pytest.raises(SearchQualityContractError, match="private absolute path"):
            validate_search_quality_suite(suite)

    def test_expected_positive_hits_loaded(self):
        suite = _tier_b_suite(
            queries=[
                {
                    "id": "multi_relevant",
                    "mode": "text",
                    "query_class": "kick_snare_perc",
                    "text": "kick",
                    "relevant_sample_ids": [1, 2],
                }
            ]
        )
        validated = validate_search_quality_suite(suite)
        assert validated.queries[0].relevant_sample_ids == (1, 2)

    def test_hard_negatives_separate_from_relevant(self):
        suite = _tier_b_suite(
            queries=[
                {
                    "id": "negatives_ok",
                    "mode": "text",
                    "query_class": "kick_snare_perc",
                    "text": "kick",
                    "relevant_sample_ids": [1],
                    "negative_sample_ids": [2],
                }
            ]
        )
        validated = validate_search_quality_suite(suite)
        assert set(validated.queries[0].relevant_sample_ids).isdisjoint(
            set(validated.queries[0].negative_sample_ids)
        )

        overlap_suite = _tier_b_suite(
            queries=[
                {
                    "id": "neg_overlap",
                    "mode": "text",
                    "query_class": "kick_snare_perc",
                    "text": "kick",
                    "relevant_sample_ids": [1],
                    "negative_sample_ids": [1, 2],
                }
            ]
        )
        with pytest.raises(SearchQualityContractError, match="overlap") as exc:
            validate_search_quality_suite(overlap_suite)
        assert exc.value.query_id == "neg_overlap"

    def test_empty_relevance_definition_rejected(self):
        suite = _tier_b_suite(
            queries=[
                {
                    "id": "empty_relevant",
                    "mode": "text",
                    "query_class": "kick_snare_perc",
                    "text": "kick",
                    "relevant_sample_ids": [],
                }
            ]
        )
        with pytest.raises(
            SearchQualityContractError, match="must not be empty"
        ) as exc:
            validate_search_quality_suite(suite)
        assert exc.value.query_id == "empty_relevant"

    def test_existing_four_query_classes_remain_loadable(self):
        suite = load_search_quality_suite(DEFAULT_TIER_B_SUITE_PATH)
        validated = validate_search_quality_suite(suite)
        classes = {query.query_class for query in validated.queries}
        assert classes >= {
            "kick_snare_perc",
            "pad_texture",
            "riser_impact",
            "dry_wet",
        }
        assert classes <= TIER_B_QUERY_CLASSES

    def test_tier_a_dataset_remains_compatible(self):
        suite = load_search_quality_suite(DEFAULT_SUITE_PATH)
        validated = validate_search_quality_suite(suite)
        assert validated.tier == "A"
        assert len(validated.queries) >= 8

    def test_errors_contain_query_id_context(self):
        suite = _tier_b_suite(
            queries=[
                {
                    "id": "ctx_query",
                    "mode": "audio",
                    "query_class": "kick_snare_perc",
                    "relevant_sample_ids": [1],
                }
            ]
        )
        with pytest.raises(SearchQualityContractError) as exc:
            validate_search_quality_suite(suite)
        assert exc.value.query_id == "ctx_query"
        assert "ctx_query" in str(exc.value)

    def test_validation_runs_without_clap_or_audio_playback(self, tmp_path: Path):
        suite = _tier_b_suite(
            queries=[
                {
                    "id": "offline_ok",
                    "mode": "text",
                    "query_class": "pad_texture",
                    "text": "warm pad",
                    "relevant_sample_ids": [2],
                }
            ]
        )
        yaml_path = tmp_path / "contract_suite.yaml"
        import yaml

        yaml_path.write_text(yaml.safe_dump(suite), encoding="utf-8")
        loaded = load_search_quality_suite(yaml_path)
        validated = validate_search_quality_suite(loaded)
        assert validated.queries[0].id == "offline_ok"

    def test_eval_excluded_placeholder_query_class_supported(self):
        suite = _tier_b_suite(
            queries=[
                {
                    "id": "genre_placeholder",
                    "mode": "text",
                    "query_class": "genre_mood",
                    "text": "upbeat electronic",
                    "relevant_sample_ids": [],
                    "eval_excluded": True,
                    "notes": "Pending #215 fixtures; not evaluated",
                }
            ]
        )
        validated = validate_search_quality_suite(suite)
        assert validated.queries[0].eval_excluded is True
        assert validated.queries[0].query_class == "genre_mood"
