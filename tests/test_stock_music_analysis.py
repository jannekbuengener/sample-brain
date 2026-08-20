from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.embed import (
    EmbeddingBackend,
    EmbeddingBackendUnavailableError,
    EmbeddingModelInfo,
    NoopEmbeddingBackend,
)
from src.stock_music_analysis import produce_stock_music_analysis


ROOT = Path(__file__).resolve().parents[1]


def _track_map(*, bpm_status: str = "ok", bpm: float | None = 128.0) -> dict:
    bpm_block: dict[str, object] = {
        "status": bpm_status,
        "source_ref": "analyze",
    }
    if bpm is not None:
        bpm_block.update({"value": bpm, "unit": "bpm", "normalization": "none"})
    return {
        "document_type": "sample_brain.track_map",
        "schema_version": "1.1.0",
        "source": {
            "original": {
                "file_name": "private-track.wav",
                "hash": {"algorithm": "sha256", "value": "a" * 64},
            }
        },
        "analysis": {
            "musical": {"bpm": bpm_block},
            "timeline": {},
        },
        "provenance": {"components": {"analyze": {"component": "analyze"}}},
        "rights": {"ownership_authorized": True},
        "contributor": {"composer": "must not leak"},
    }


def _arrangement(
    *, role: str = "drop", status: str = "available", root_status: str | None = None
) -> dict:
    return {
        "document_type": "sample_brain.arrangement_map",
        "schema_version": "0.1.0-draft",
        "status": status if root_status is None else root_status,
        "sections": [
            {
                "id": "section_01",
                "automatic_result": {"role": role, "status": status},
                "effective_value": {"role": "outro", "source": "manual"},
            }
        ],
        "provenance": {"component": "arrangement_classifier"},
    }


def _group(kind: str, status: str) -> dict:
    technical_stems = {
        "kick_bass": ["drums", "bass"],
        "drums": ["drums"],
        "vocal": ["vocals"],
        "melodic": ["other"],
        "atmos_fx": ["other"],
    }
    manifest: dict[str, object] = {
        "document_type": "sample_brain.producer_group",
        "schema_version": "1.0.0",
        "group_kind": kind,
        "group_id": f"producer_group_id_{kind}",
        "group_ref": f"producer_group_{kind}",
        "status": status,
        "masks": "confirmed_test_mask",
        "summation": "confirmed_test_sum",
        "timebase": {"sample_rate_hz": 44100, "n_samples": 44100},
        "technical_stems": technical_stems[kind],
        "components": [{"source_kind": "test"}],
        "processing": [],
    }
    if status == "no_result":
        manifest["reason_code"] = "NO_CONFIRMED_AUDIO"
    return manifest


class _SemanticBackend(EmbeddingBackend):
    def embed_audio(self, audio_path: str) -> np.ndarray:
        assert audio_path == "C:\\private\\input\\track.wav"
        return np.array([1.0, 0.0], dtype=np.float32)

    def embed_text(self, text: str) -> np.ndarray:
        if "electronic" in text:
            return np.array([1.0, 0.0], dtype=np.float32)
        return np.array([0.0, 1.0], dtype=np.float32)

    def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            provider="fake",
            model_name="fake-clap",
            model_version="test-v1",
            embedding_dim=2,
            modality="audio_text",
        )


class _InsufficientBackend(_SemanticBackend):
    def embed_text(self, text: str) -> np.ndarray:
        return np.array([-1.0, 0.0], dtype=np.float32)


class _BadBackend(_SemanticBackend):
    def embed_audio(self, audio_path: str) -> np.ndarray:
        return np.zeros(2, dtype=np.float32)


class _UnavailableBackend(_SemanticBackend):
    def embed_audio(self, audio_path: str) -> np.ndarray:
        raise EmbeddingBackendUnavailableError(f"unavailable for {audio_path}")


class _SecretProvenanceBackend(_SemanticBackend):
    def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            provider="token=top-secret",
            model_name="C:\\model-cache\\private-model",
            model_version="test-v1",
            embedding_dim=2,
            modality="audio_text",
        )


class _RelativeModelPathBackend(_SemanticBackend):
    def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            provider="fake",
            model_name="fake/model-cache",
            model_version="test-v1",
            embedding_dim=2,
            modality="audio_text",
        )


class _DimensionMismatchBackend(_SemanticBackend):
    def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            provider="fake",
            model_name="fake-clap",
            model_version="test-v1",
            embedding_dim=512,
            modality="audio_text",
        )


def _item_values(field: dict) -> set[str]:
    return {item["value"] for item in field["items"]}


def test_rule_derived_values_are_ok_and_use_automatic_evidence_only() -> None:
    result = produce_stock_music_analysis(
        _track_map(),
        arrangement_map=_arrangement(),
        producer_group_manifests=(_group("drums", "ok"), _group("vocal", "ok")),
    )

    assert result["track_ref"] == f"sha256:{'a' * 64}"
    assert result["semantic"]["pace_character"]["status"] == "ok"
    assert _item_values(result["semantic"]["pace_character"]) == {"upbeat"}
    assert result["semantic"]["energy_class"]["status"] == "ok"
    assert result["semantic"]["energy_class"]["value"] == "high"
    assert result["semantic"]["arrangement_character"]["status"] == "ok"
    assert _item_values(result["semantic"]["arrangement_character"]) == {"drop"}
    assert _item_values(result["semantic"]["instrumentation"]) == {"drums", "vocals"}
    assert all(
        item["status"] == "ok" for item in result["semantic"]["instrumentation"]["items"]
    )
    assert "outro" not in _item_values(result["semantic"]["arrangement_character"])


def test_proxy_and_clap_values_remain_partial_with_score_semantics() -> None:
    result = produce_stock_music_analysis(
        _track_map(),
        arrangement_map=_arrangement(role="build", status="uncertain"),
        producer_group_manifests=(_group("melodic", "partial"),),
        audio_path="C:\\private\\input\\track.wav",
        semantic_backend=_SemanticBackend(),
    )

    instrumentation = result["semantic"]["instrumentation"]
    assert instrumentation["status"] == "partial"
    assert instrumentation["items"][0]["value"] == "melodic_elements"
    assert instrumentation["items"][0]["status"] == "partial"
    assert result["semantic"]["arrangement_character"]["status"] == "partial"
    genre = result["semantic"]["genre"]
    assert genre["status"] == "partial"
    assert genre["value"] == "electronic"
    assert genre["score_kind"] == "clap_audio_text_cosine_similarity_v1"
    assert -1.0 <= genre["score"] <= 1.0
    assert "confidence" not in json.dumps(result).lower()


def test_missing_or_insufficient_evidence_is_not_invented() -> None:
    no_bpm = produce_stock_music_analysis(_track_map(bpm_status="no_result", bpm=None))
    assert no_bpm["semantic"]["pace_character"]["status"] == "no_result"
    assert no_bpm["semantic"]["instrumentation"]["status"] == "not_run"

    insufficient = produce_stock_music_analysis(
        _track_map(),
        audio_path="C:\\private\\input\\track.wav",
        semantic_backend=_InsufficientBackend(),
    )
    assert insufficient["semantic"]["genre"]["status"] == "no_result"
    assert "value" not in insufficient["semantic"]["genre"]


def test_optional_backend_is_not_run_when_omitted_or_unavailable() -> None:
    omitted = produce_stock_music_analysis(_track_map())
    assert omitted["semantic"]["genre"]["status"] == "not_run"

    unavailable = produce_stock_music_analysis(
        _track_map(),
        audio_path="C:\\private\\input\\track.wav",
        semantic_backend=_UnavailableBackend(),
    )
    assert unavailable["semantic"]["genre"]["status"] == "not_run"
    assert "C:\\private" not in json.dumps(unavailable)


def test_backend_contract_failure_is_failed_without_leaking_private_data() -> None:
    result = produce_stock_music_analysis(
        _track_map(),
        audio_path="C:\\private\\input\\track.wav",
        semantic_backend=_BadBackend(),
    )

    assert result["semantic"]["genre"]["status"] == "failed"
    assert "C:\\private" not in json.dumps(result)


def test_evidence_sources_and_vocabulary_are_registered() -> None:
    result = produce_stock_music_analysis(
        _track_map(),
        arrangement_map=_arrangement(),
        producer_group_manifests=(_group("drums", "ok"),),
    )

    sources = result["provenance"]["sources"]
    assert {"track_map_v1", "arrangement_map", "producer_group_drums", "rule_engine"} <= set(sources)
    pace_item = result["semantic"]["pace_character"]["items"][0]
    assert pace_item["evidence_refs"] == ["track_map.analysis.musical.bpm"]
    assert pace_item["source_ref"] == "track_map_v1"
    assert pace_item["vocabulary"] == "sample_brain.stock_music_descriptor_v1"
    assert pace_item["vocabulary_version"] == "1.0.0"
    arrangement_item = result["semantic"]["arrangement_character"]["items"][0]
    assert arrangement_item["vocabulary"] == "sample_brain.arrangement_role_vocabulary"
    assert arrangement_item["vocabulary_version"] == "1.0.0"


def test_result_is_deterministic_portable_and_excludes_profiles_and_references() -> None:
    kwargs = {
        "arrangement_map": _arrangement(),
        "producer_group_manifests": (_group("drums", "ok"),),
        "audio_path": "C:\\private\\input\\track.wav",
        "semantic_backend": _SecretProvenanceBackend(),
    }
    first = produce_stock_music_analysis(_track_map(), **kwargs)
    second = produce_stock_music_analysis(_track_map(), **kwargs)

    assert first == second
    raw = json.dumps(first).lower()
    for forbidden in (
        "c:\\private",
        "model-cache",
        "top-secret",
        ".db",
        ".npz",
        ".pth",
        "file://",
        "rights",
        "contributor",
        "artist",
        "brand",
        "film",
        "tv",
        "game",
        "sounds like",
    ):
        assert forbidden not in raw


def test_missing_producer_group_does_not_create_instrumentation() -> None:
    result = produce_stock_music_analysis(
        _track_map(),
        producer_group_manifests=(_group("drums", "no_result"),),
    )

    instrumentation = result["semantic"]["instrumentation"]
    assert instrumentation["status"] == "no_result"
    assert instrumentation["items"] == []


def test_arrangement_without_energy_bearing_role_has_no_energy_result() -> None:
    result = produce_stock_music_analysis(
        _track_map(),
        arrangement_map=_arrangement(role="intro"),
    )

    assert result["semantic"]["arrangement_character"]["status"] == "ok"
    assert _item_values(result["semantic"]["arrangement_character"]) == {"intro"}
    assert result["semantic"]["energy_class"]["status"] == "no_result"


def test_root_arrangement_uncertainty_keeps_derived_descriptors_partial() -> None:
    result = produce_stock_music_analysis(
        _track_map(),
        arrangement_map=_arrangement(root_status="uncertain"),
    )

    assert result["semantic"]["arrangement_character"]["status"] == "partial"
    assert result["semantic"]["arrangement_character"]["items"][0]["status"] == "partial"
    assert result["semantic"]["energy_class"]["status"] == "partial"


def test_explicit_noop_backend_is_not_run() -> None:
    result = produce_stock_music_analysis(
        _track_map(),
        audio_path="C:\\private\\input\\track.wav",
        semantic_backend=NoopEmbeddingBackend(),
    )

    assert result["semantic"]["genre"]["status"] == "not_run"


def test_unconfirmed_producer_group_manifest_cannot_create_instrumentation() -> None:
    manifest = _group("drums", "ok")
    manifest.pop("components")

    result = produce_stock_music_analysis(
        _track_map(),
        producer_group_manifests=(manifest,),
    )

    assert result["semantic"]["instrumentation"]["status"] == "failed"
    assert result["semantic"]["instrumentation"]["items"] == []


def test_nonportable_schema_versions_are_failed_closed_or_rejected() -> None:
    unsafe_track_map = _track_map()
    unsafe_track_map["schema_version"] = "1.file://private"
    with pytest.raises(ValueError):
        produce_stock_music_analysis(unsafe_track_map)

    unsafe_arrangement = _arrangement()
    unsafe_arrangement["schema_version"] = "0.1.0-file://private"
    result = produce_stock_music_analysis(_track_map(), arrangement_map=unsafe_arrangement)
    assert result["semantic"]["energy_class"]["status"] == "failed"
    assert "file://private" not in json.dumps(result)


def test_relative_model_cache_name_is_not_serialized() -> None:
    result = produce_stock_music_analysis(
        _track_map(),
        audio_path="C:\\private\\input\\track.wav",
        semantic_backend=_RelativeModelPathBackend(),
    )

    assert result["semantic"]["genre"]["status"] == "failed"
    assert "model-cache" not in json.dumps(result)


def test_model_embedding_dimension_mismatch_is_failed() -> None:
    result = produce_stock_music_analysis(
        _track_map(),
        audio_path="C:\\private\\input\\track.wav",
        semantic_backend=_DimensionMismatchBackend(),
    )

    assert result["semantic"]["genre"]["status"] == "failed"


def test_breakdown_alone_does_not_invent_low_energy() -> None:
    result = produce_stock_music_analysis(
        _track_map(),
        arrangement_map=_arrangement(role="breakdown"),
    )

    assert result["semantic"]["energy_class"]["status"] == "no_result"


def test_missing_automatic_arrangement_result_is_failed_closed() -> None:
    arrangement = _arrangement()
    arrangement["sections"].append({"id": "section_02"})

    result = produce_stock_music_analysis(_track_map(), arrangement_map=arrangement)

    assert result["semantic"]["energy_class"]["status"] == "failed"
    assert result["semantic"]["arrangement_character"]["status"] == "failed"


def test_malformed_producer_group_values_are_failed_closed() -> None:
    manifest = _group("drums", "ok")
    manifest["group_kind"] = []

    result = produce_stock_music_analysis(
        _track_map(),
        producer_group_manifests=(manifest,),
    )

    assert result["semantic"]["instrumentation"]["status"] == "failed"


def test_unsupported_arrangement_schema_major_is_failed_closed() -> None:
    arrangement = _arrangement()
    arrangement["schema_version"] = "1.0.0"

    result = produce_stock_music_analysis(_track_map(), arrangement_map=arrangement)

    assert result["semantic"]["energy_class"]["status"] == "failed"


def test_missing_arrangement_root_status_is_failed_closed() -> None:
    arrangement = _arrangement()
    arrangement.pop("status")

    result = produce_stock_music_analysis(_track_map(), arrangement_map=arrangement)

    assert result["semantic"]["energy_class"]["status"] == "failed"
    assert result["semantic"]["arrangement_character"]["status"] == "failed"


def test_mixed_unavailable_arrangement_sections_keep_descriptors_partial() -> None:
    arrangement = _arrangement()
    arrangement["sections"].append(
        {
            "id": "section_02",
            "automatic_result": {"role": "unknown", "status": "unavailable"},
        }
    )

    result = produce_stock_music_analysis(_track_map(), arrangement_map=arrangement)

    assert result["semantic"]["energy_class"]["status"] == "partial"
    assert result["semantic"]["arrangement_character"]["status"] == "partial"


def test_foreign_producer_group_track_ref_is_failed_closed() -> None:
    manifest = _group("drums", "ok")
    manifest["track_ref"] = f"sha256:{'b' * 64}"

    result = produce_stock_music_analysis(
        _track_map(), producer_group_manifests=(manifest,)
    )

    assert result["semantic"]["instrumentation"]["status"] == "failed"
    assert result["semantic"]["instrumentation"]["items"] == []


def test_vocabulary_contract_is_versioned_and_has_no_prohibited_terms() -> None:
    vocabulary = json.loads(
        (ROOT / "docs" / "stock_music_descriptor_vocabulary_v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert vocabulary["document_type"] == "sample_brain.stock_music_descriptor_vocabulary"
    assert vocabulary["schema_version"] == "1.0.0"
    assert vocabulary["score"] == {
        "kind": "clap_audio_text_cosine_similarity_v1",
        "range": [-1.0, 1.0],
    }
    vocabulary_text = json.dumps(vocabulary["fields"]).lower()
    for forbidden in ("artist", "brand", "film", "tv", "game", "rights", "contributor"):
        assert forbidden not in vocabulary_text
