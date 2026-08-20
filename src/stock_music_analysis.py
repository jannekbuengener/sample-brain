"""Portable, evidence-backed stock-music descriptors for issue #449.

The producer in this module is deliberately an artefact/view over existing
analysis results.  It does not alter Track Map semantics, persist data, or
load an optional semantic model.  A caller must supply both an audio path and
an ``EmbeddingBackend`` explicitly before any model-backed descriptors run.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import math
import re

import numpy as np

from .content_hash import normalize_hash_record
from .embed import EmbeddingBackendUnavailableError


STOCK_MUSIC_ANALYSIS_DOCUMENT_TYPE = "sample_brain.stock_music_analysis"
STOCK_MUSIC_ANALYSIS_SCHEMA_VERSION = "1.0.0"
STOCK_MUSIC_VOCABULARY = "sample_brain.stock_music_descriptor_v1"
STOCK_MUSIC_VOCABULARY_VERSION = "1.0.0"
ARRANGEMENT_ROLE_VOCABULARY = "sample_brain.arrangement_role_vocabulary"
ARRANGEMENT_ROLE_VOCABULARY_VERSION = "1.0.0"
CLAP_SCORE_KIND = "clap_audio_text_cosine_similarity_v1"

_STATUSES = frozenset({"ok", "partial", "not_run", "failed", "no_result"})
_ARRANGEMENT_STATUSES = frozenset(
    {"available", "uncertain", "unknown", "unavailable", "failed"}
)
_PRODUCER_GROUP_STATUSES = frozenset({"ok", "partial", "no_result", "failed"})
_ARRANGEMENT_ROLES = (
    "intro",
    "groove",
    "build",
    "drop",
    "breakdown",
    "outro",
)
_INSTRUMENTATION = (
    "drums",
    "bass",
    "vocals",
    "melodic_elements",
    "atmospheric_fx",
)
_MODEL_SCORE_MINIMUM = 0.5

_MODEL_PROMPTS: dict[str, dict[str, str]] = {
    "genre": {
        "acoustic": "acoustic music",
        "ambient": "ambient music",
        "cinematic": "cinematic music",
        "classical": "classical music",
        "electronic": "electronic music",
        "hip_hop": "hip hop music",
        "pop": "pop music",
        "rock": "rock music",
    },
    "subgenre": {
        "ambient_electronic": "ambient electronic music",
        "downtempo": "downtempo music",
        "house": "house music",
        "techno": "techno music",
        "trap": "trap music",
    },
    "mood": {
        "calm": "calm mood",
        "dark": "dark mood",
        "driving": "driving mood",
        "energetic": "energetic mood",
        "hopeful": "hopeful mood",
        "mysterious": "mysterious mood",
        "tense": "tense mood",
        "uplifting": "uplifting mood",
    },
    "sound_palette": {
        "atmospheric": "atmospheric sound palette",
        "bright": "bright sound palette",
        "dark": "dark sound palette",
        "warm": "warm sound palette",
        "electronic": "electronic sound palette",
        "acoustic": "acoustic sound palette",
    },
    "production_character": {
        "dense": "dense production",
        "minimal": "minimal production",
        "polished": "polished production",
        "raw": "raw production",
        "spacious": "spacious production",
    },
    "usage_context": {
        "background": "background music",
        "corporate": "corporate music",
        "documentary": "documentary music",
        "fitness": "fitness music",
        "podcast": "podcast music",
        "promotion": "promotion music",
    },
}
_MODEL_COLLECTION_FIELDS = frozenset(
    {"mood", "sound_palette", "production_character", "usage_context"}
)
_GROUP_TERMS = {
    "kick_bass": ("drums", "bass"),
    "drums": ("drums",),
    "vocal": ("vocals",),
    "melodic": ("melodic_elements",),
    "atmos_fx": ("atmospheric_fx",),
}
_PROXY_GROUPS = frozenset({"melodic", "atmos_fx"})
_SAFE_SECTION_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SAFE_PROVIDER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_SAFE_MODEL_NAME = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?$"
)
_SAFE_MODEL_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def produce_stock_music_analysis(
    track_map: Mapping[str, object],
    *,
    arrangement_map: Mapping[str, object] | None = None,
    producer_group_manifests: Iterable[Mapping[str, object]] = (),
    audio_path: str | None = None,
    semantic_backend: object | None = None,
) -> dict[str, object]:
    """Produce the portable #449 semantic analysis artefact.

    ``audio_path`` is supplied only to an explicitly injected backend and never
    enters the returned artefact.  The function has no implicit backend choice,
    model loading, persistence, or network behaviour.
    """

    track_ref, track_source = _track_identity(track_map)
    sources: dict[str, dict[str, object]] = {
        "track_map_v1": track_source,
        "rule_engine": {
            "kind": "semantic_producer",
            "component": "stock_music_analysis",
            "version": STOCK_MUSIC_ANALYSIS_SCHEMA_VERSION,
            "method": "deterministic_rules_v1",
        },
        "arrangement_map": {
            "kind": "analysis_artifact",
            "document_type": "sample_brain.arrangement_map",
            "status": "not_run" if arrangement_map is None else "available",
        },
        "producer_groups": {
            "kind": "analysis_artifact_collection",
            "document_type": "sample_brain.producer_group",
            "status": "not_run",
        },
        "clap_semantic_backend": {
            "kind": "optional_semantic_backend",
            "status": "not_run",
        },
    }

    pace = _pace_character(track_map)
    energy, arrangement = _arrangement_descriptors(arrangement_map, sources)
    instrumentation = _instrumentation(producer_group_manifests, sources)
    model_fields = _model_descriptors(audio_path, semantic_backend, sources)

    semantic: dict[str, object] = {
        "genre": model_fields["genre"],
        "subgenre": model_fields["subgenre"],
        "mood": model_fields["mood"],
        "energy_class": energy,
        "pace_character": pace,
        "instrumentation": instrumentation,
        "sound_palette": model_fields["sound_palette"],
        "production_character": model_fields["production_character"],
        "usage_context": model_fields["usage_context"],
        "arrangement_character": arrangement,
    }
    semantic["status"] = _aggregate_status(
        _field_status(field) for field in semantic.values()
    )

    return {
        "document_type": STOCK_MUSIC_ANALYSIS_DOCUMENT_TYPE,
        "schema_version": STOCK_MUSIC_ANALYSIS_SCHEMA_VERSION,
        "track_ref": track_ref,
        "semantic": semantic,
        "provenance": {"sources": {key: sources[key] for key in sorted(sources)}},
    }


def _track_identity(track_map: Mapping[str, object]) -> tuple[str, dict[str, object]]:
    if not isinstance(track_map, Mapping):
        raise ValueError("track_map must be a mapping")
    if track_map.get("document_type") != "sample_brain.track_map":
        raise ValueError("track_map must use sample_brain.track_map")
    schema_version = track_map.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.startswith("1."):
        raise ValueError("track_map must use Track Map v1")
    hash_record = _mapping_at(track_map, "source", "original", "hash")
    normalized_hash = normalize_hash_record(dict(hash_record))
    track_ref = f"{normalized_hash['algorithm']}:{normalized_hash['value']}"
    return track_ref, {
        "kind": "analysis_artifact",
        "document_type": "sample_brain.track_map",
        "schema_version": schema_version,
        "track_ref": track_ref,
    }


def _pace_character(track_map: Mapping[str, object]) -> dict[str, object]:
    bpm = _mapping_at(track_map, "analysis", "musical", "bpm")
    status = bpm.get("status")
    if status == "failed":
        return _collection("failed", [], "track_map_v1", "BPM_ANALYSIS_FAILED")
    value = bpm.get("value")
    if status != "ok" or not _finite_number(value):
        return _collection("no_result", [], "track_map_v1", "BPM_UNAVAILABLE")

    bpm_value = float(value)
    if bpm_value < 80.0:
        pace = "slow"
    elif bpm_value < 110.0:
        pace = "moderate"
    elif bpm_value < 140.0:
        pace = "upbeat"
    else:
        pace = "fast"
    return _collection(
        "ok",
        [
            _value(
                pace,
                "ok",
                ["track_map.analysis.musical.bpm"],
                "track_map_v1",
            )
        ],
        "track_map_v1",
    )


def _arrangement_descriptors(
    arrangement_map: Mapping[str, object] | None,
    sources: dict[str, dict[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    if arrangement_map is None:
        return (
            _empty_value("not_run", "arrangement_map", "ARRANGEMENT_MAP_NOT_SUPPLIED"),
            _collection(
                "not_run", [], "arrangement_map", "ARRANGEMENT_MAP_NOT_SUPPLIED"
            ),
        )
    if not isinstance(arrangement_map, Mapping) or (
        arrangement_map.get("document_type") != "sample_brain.arrangement_map"
    ):
        sources["arrangement_map"]["status"] = "failed"
        return (
            _empty_value("failed", "arrangement_map", "ARRANGEMENT_MAP_INVALID"),
            _collection("failed", [], "arrangement_map", "ARRANGEMENT_MAP_INVALID"),
        )

    schema_version = arrangement_map.get("schema_version")
    if isinstance(schema_version, str):
        sources["arrangement_map"]["schema_version"] = schema_version
    records, producer_status = _automatic_arrangement_records(arrangement_map)
    sources["arrangement_map"]["status"] = producer_status
    if producer_status == "failed":
        return (
            _empty_value("failed", "arrangement_map", "ARRANGEMENT_ANALYSIS_FAILED"),
            _collection("failed", [], "arrangement_map", "ARRANGEMENT_ANALYSIS_FAILED"),
        )
    if not records:
        return (
            _empty_value("no_result", "arrangement_map", "ARRANGEMENT_UNAVAILABLE"),
            _collection("no_result", [], "arrangement_map", "ARRANGEMENT_UNAVAILABLE"),
        )

    arrangement_items = [
        _value(
            role,
            "partial" if status == "uncertain" else "ok",
            refs,
            "arrangement_map",
            vocabulary=ARRANGEMENT_ROLE_VOCABULARY,
            vocabulary_version=ARRANGEMENT_ROLE_VOCABULARY_VERSION,
        )
        for role, status, refs in _collapse_arrangement_records(records)
    ]
    arrangement_status = _aggregate_status(item["status"] for item in arrangement_items)
    energy_value, energy_status, energy_refs = _energy_from_arrangement(records)
    energy = _value(
        energy_value,
        energy_status,
        energy_refs,
        "arrangement_map",
    )
    return energy, _collection(arrangement_status, arrangement_items, "arrangement_map")


def _automatic_arrangement_records(
    arrangement_map: Mapping[str, object],
) -> tuple[list[tuple[str, str, list[str]]], str]:
    root_status = arrangement_map.get("status")
    if root_status == "failed":
        return [], "failed"
    sections = arrangement_map.get("sections")
    if not isinstance(sections, list):
        return [], "failed"

    records: list[tuple[str, str, list[str]]] = []
    saw_unavailable = False
    for index, section in enumerate(sections, start=1):
        if not isinstance(section, Mapping):
            return [], "failed"
        automatic = section.get("automatic_result")
        if not isinstance(automatic, Mapping):
            continue
        role = automatic.get("role")
        status = automatic.get("status")
        if not isinstance(role, str) or not isinstance(status, str):
            return [], "failed"
        if status not in _ARRANGEMENT_STATUSES:
            return [], "failed"
        if status == "failed":
            return [], "failed"
        if status in {"unknown", "unavailable"} or role not in _ARRANGEMENT_ROLES:
            saw_unavailable = True
            continue
        section_id = section.get("id")
        stable_id = (
            section_id
            if isinstance(section_id, str) and _SAFE_SECTION_ID.fullmatch(section_id)
            else f"section_{index:02d}"
        )
        records.append(
            (
                role,
                status,
                [f"arrangement_map.sections.{stable_id}.automatic_result"],
            )
        )

    if records:
        return records, "uncertain" if any(item[1] == "uncertain" for item in records) else "available"
    if root_status in {"unknown", "unavailable"} or saw_unavailable:
        return [], "unavailable"
    return [], "unavailable"


def _collapse_arrangement_records(
    records: list[tuple[str, str, list[str]]],
) -> list[tuple[str, str, list[str]]]:
    by_role: dict[str, tuple[str, list[str]]] = {}
    for role, status, refs in records:
        existing = by_role.get(role)
        if existing is None:
            by_role[role] = (status, list(refs))
            continue
        existing_status, existing_refs = existing
        combined_status = "available" if "available" in {existing_status, status} else "uncertain"
        by_role[role] = (combined_status, sorted(set(existing_refs + refs)))
    return [
        (role, by_role[role][0], by_role[role][1])
        for role in _ARRANGEMENT_ROLES
        if role in by_role
    ]


def _energy_from_arrangement(
    records: list[tuple[str, str, list[str]]],
) -> tuple[str, str, list[str]]:
    collapsed = {role: (status, refs) for role, status, refs in _collapse_arrangement_records(records)}
    if "drop" in collapsed and "breakdown" in collapsed:
        evidence = [collapsed["drop"], collapsed["breakdown"]]
        value = "dynamic"
    elif "drop" in collapsed:
        evidence = [collapsed["drop"]]
        value = "high"
    elif "groove" in collapsed:
        evidence = [collapsed["groove"]]
        value = "medium"
    elif "build" in collapsed:
        evidence = [collapsed["build"]]
        value = "medium"
    else:
        evidence = [collapsed["breakdown"]]
        value = "low"
    status = "partial" if any(item[0] == "uncertain" for item in evidence) else "ok"
    refs = sorted({ref for _, item_refs in evidence for ref in item_refs})
    return value, status, refs


def _instrumentation(
    manifests: Iterable[Mapping[str, object]], sources: dict[str, dict[str, object]]
) -> dict[str, object]:
    try:
        materialized = tuple(manifests)
    except TypeError:
        sources["producer_groups"]["status"] = "failed"
        return _collection("failed", [], "producer_groups", "PRODUCER_GROUPS_INVALID")
    if not materialized:
        return _collection("not_run", [], "producer_groups", "PRODUCER_GROUPS_NOT_SUPPLIED")

    terms: dict[str, dict[str, object]] = {}
    saw_no_result = False
    for manifest in materialized:
        if not isinstance(manifest, Mapping):
            sources["producer_groups"]["status"] = "failed"
            return _collection("failed", [], "producer_groups", "PRODUCER_GROUP_INVALID")
        if manifest.get("document_type") != "sample_brain.producer_group":
            sources["producer_groups"]["status"] = "failed"
            return _collection("failed", [], "producer_groups", "PRODUCER_GROUP_INVALID")
        group_kind = manifest.get("group_kind")
        group_status = manifest.get("status")
        if not isinstance(group_kind, str) or group_kind not in _GROUP_TERMS:
            continue
        if not isinstance(group_status, str) or group_status not in _PRODUCER_GROUP_STATUSES:
            sources["producer_groups"]["status"] = "failed"
            return _collection("failed", [], "producer_groups", "PRODUCER_GROUP_INVALID")
        source_ref = f"producer_group_{group_kind}"
        source = {
            "kind": "analysis_artifact",
            "document_type": "sample_brain.producer_group",
            "group_kind": group_kind,
        }
        schema_version = manifest.get("schema_version")
        if isinstance(schema_version, str):
            source["schema_version"] = schema_version
        sources[source_ref] = source
        if group_status == "failed":
            sources["producer_groups"]["status"] = "failed"
            return _collection("failed", [], "producer_groups", "PRODUCER_GROUP_FAILED")
        if group_status == "no_result":
            saw_no_result = True
            continue

        descriptor_status = (
            "partial"
            if group_status == "partial" or group_kind in _PROXY_GROUPS
            else "ok"
        )
        evidence_ref = f"producer_groups.{group_kind}"
        for term in _GROUP_TERMS[group_kind]:
            current = terms.get(term)
            if current is None:
                terms[term] = {
                    "status": descriptor_status,
                    "evidence_refs": [evidence_ref],
                    "source_ref": source_ref,
                }
                continue
            current["evidence_refs"] = sorted(
                set(current["evidence_refs"] + [evidence_ref])  # type: ignore[operator]
            )
            if descriptor_status == "ok":
                current["status"] = "ok"

    if not terms:
        sources["producer_groups"]["status"] = "no_result" if saw_no_result else "unavailable"
        return _collection("no_result", [], "producer_groups", "NO_CONFIRMED_PRODUCER_GROUP")

    sources["producer_groups"]["status"] = _aggregate_status(
        str(item["status"]) for item in terms.values()
    )
    items = [
        _value(
            term,
            str(terms[term]["status"]),
            list(terms[term]["evidence_refs"]),  # type: ignore[arg-type]
            str(terms[term]["source_ref"]),
        )
        for term in _INSTRUMENTATION
        if term in terms
    ]
    return _collection(_aggregate_status(item["status"] for item in items), items, "producer_groups")


def _model_descriptors(
    audio_path: str | None,
    semantic_backend: object | None,
    sources: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    if audio_path is None or semantic_backend is None:
        return _empty_model_fields("not_run", "SEMANTIC_BACKEND_NOT_SUPPLIED")
    if not _looks_like_backend(semantic_backend):
        sources["clap_semantic_backend"]["status"] = "failed"
        return _empty_model_fields("failed", "SEMANTIC_BACKEND_INVALID")

    try:
        audio_vector = _normalized_vector(semantic_backend.embed_audio(audio_path))
        scored = _score_model_prompts(semantic_backend, audio_vector)
        source = _model_source(semantic_backend.model_info())
    except EmbeddingBackendUnavailableError:
        return _empty_model_fields("not_run", "SEMANTIC_BACKEND_UNAVAILABLE")
    except Exception:
        sources["clap_semantic_backend"]["status"] = "failed"
        return _empty_model_fields("failed", "SEMANTIC_BACKEND_FAILURE")

    sources["clap_semantic_backend"] = source
    return {
        field: _model_field(field, candidates)
        for field, candidates in scored.items()
    }


def _looks_like_backend(value: object) -> bool:
    return all(callable(getattr(value, name, None)) for name in ("embed_audio", "embed_text", "model_info"))


def _normalized_vector(value: object) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float64).reshape(-1)
    if vector.size == 0 or not np.all(np.isfinite(vector)):
        raise ValueError("semantic vector is invalid")
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm <= 0.0:
        raise ValueError("semantic vector has no magnitude")
    return vector / norm


def _score_model_prompts(
    backend: object, audio_vector: np.ndarray
) -> dict[str, list[tuple[str, float]]]:
    scored: dict[str, list[tuple[str, float]]] = {}
    for field, prompts in _MODEL_PROMPTS.items():
        candidates: list[tuple[str, float]] = []
        for value, prompt in prompts.items():
            text_vector = _normalized_vector(backend.embed_text(prompt))
            if text_vector.shape != audio_vector.shape:
                raise ValueError("semantic vector dimensions differ")
            score = float(np.clip(np.dot(audio_vector, text_vector), -1.0, 1.0))
            if score >= _MODEL_SCORE_MINIMUM:
                candidates.append((value, round(score, 12)))
        scored[field] = sorted(candidates, key=lambda item: (-item[1], item[0]))
    return scored


def _model_source(model_info: object) -> dict[str, object]:
    provider = getattr(model_info, "provider", None)
    model_name = getattr(model_info, "model_name", None)
    model_version = getattr(model_info, "model_version", None)
    embedding_dim = getattr(model_info, "embedding_dim", None)
    modality = getattr(model_info, "modality", None)
    if (
        not isinstance(provider, str)
        or not _SAFE_PROVIDER.fullmatch(provider)
        or not isinstance(model_name, str)
        or not _SAFE_MODEL_NAME.fullmatch(model_name)
        or not isinstance(model_version, str)
        or not _SAFE_MODEL_VERSION.fullmatch(model_version)
        or not isinstance(embedding_dim, int)
        or isinstance(embedding_dim, bool)
        or embedding_dim < 1
        or modality != "audio_text"
    ):
        raise ValueError("semantic model provenance is not portable")
    return {
        "kind": "optional_semantic_backend",
        "status": "available",
        "provider": provider,
        "model_name": model_name,
        "model_version": model_version,
        "embedding_dim": embedding_dim,
        "modality": modality,
    }


def _model_field(field: str, candidates: list[tuple[str, float]]) -> dict[str, object]:
    if not candidates:
        if field in _MODEL_COLLECTION_FIELDS:
            return _collection("no_result", [], "clap_semantic_backend", "MODEL_EVIDENCE_INSUFFICIENT")
        return _empty_value("no_result", "clap_semantic_backend", "MODEL_EVIDENCE_INSUFFICIENT")
    value, score = candidates[0]
    item = _value(
        value,
        "partial",
        [f"clap.prompts.{field}.{value}"],
        "clap_semantic_backend",
        score=score,
    )
    if field in _MODEL_COLLECTION_FIELDS:
        return _collection("partial", [item], "clap_semantic_backend")
    return item


def _empty_model_fields(status: str, reason_code: str) -> dict[str, dict[str, object]]:
    return {
        field: (
            _collection(status, [], "clap_semantic_backend", reason_code)
            if field in _MODEL_COLLECTION_FIELDS
            else _empty_value(status, "clap_semantic_backend", reason_code)
        )
        for field in _MODEL_PROMPTS
    }


def _value(
    value: str,
    status: str,
    evidence_refs: list[str],
    source_ref: str,
    *,
    vocabulary: str = STOCK_MUSIC_VOCABULARY,
    vocabulary_version: str = STOCK_MUSIC_VOCABULARY_VERSION,
    score: float | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "value": value,
        "status": status,
        "evidence_refs": sorted(set(evidence_refs)),
        "source_ref": source_ref,
        "vocabulary": vocabulary,
        "vocabulary_version": vocabulary_version,
    }
    if score is not None:
        result["score"] = score
        result["score_kind"] = CLAP_SCORE_KIND
    return result


def _empty_value(status: str, source_ref: str, reason_code: str) -> dict[str, object]:
    return {
        "status": status,
        "evidence_refs": [],
        "source_ref": source_ref,
        "reason_code": reason_code,
    }


def _collection(
    status: str,
    items: list[dict[str, object]],
    source_ref: str,
    reason_code: str | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "status": status,
        "items": items,
        "source_ref": source_ref,
    }
    if reason_code is not None:
        result["reason_code"] = reason_code
    return result


def _mapping_at(value: object, *keys: str) -> Mapping[str, object]:
    current = value
    for key in keys:
        if not isinstance(current, Mapping):
            return {}
        current = current.get(key)
    return current if isinstance(current, Mapping) else {}


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _field_status(field: object) -> str:
    if isinstance(field, Mapping) and isinstance(field.get("status"), str):
        return str(field["status"])
    return "failed"


def _aggregate_status(statuses: Iterable[object]) -> str:
    normalized = [str(status) for status in statuses if str(status) in _STATUSES]
    if not normalized:
        return "failed"
    if "failed" in normalized and not any(
        status in {"ok", "partial"} for status in normalized
    ):
        return "failed"
    if "partial" in normalized or "failed" in normalized:
        return "partial"
    if "ok" in normalized:
        return "ok"
    if "no_result" in normalized:
        return "no_result"
    return "not_run"


__all__ = ["produce_stock_music_analysis"]
