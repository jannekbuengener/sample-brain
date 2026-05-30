from __future__ import annotations

from dataclasses import dataclass

from .index import SearchHit


@dataclass(frozen=True)
class HybridMetadata:
    sample_id: int
    bpm: float | None = None
    key: str | None = None
    pred_type: str | None = None
    audio_class: str | None = None


@dataclass(frozen=True)
class HybridQuery:
    target_bpm: float | None = None
    target_key: str | None = None
    target_type: str | None = None
    semantic_weight: float = 1.0
    bpm_weight: float = 0.0
    key_weight: float = 0.0
    type_weight: float = 0.0
    bpm_tolerance: float = 8.0


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    return normalized or None


def score_bpm_match(
    sample_bpm: float | None,
    target_bpm: float | None,
    tolerance: float,
) -> float:
    if sample_bpm is None or target_bpm is None:
        return 0.0
    if tolerance <= 0:
        return 0.0

    diff = abs(sample_bpm - target_bpm)
    if diff >= tolerance:
        return 0.0
    if diff == 0:
        return 1.0
    return 1.0 - (diff / tolerance)


def score_key_match(sample_key: str | None, target_key: str | None) -> float:
    normalized_sample = _normalize_text(sample_key)
    normalized_target = _normalize_text(target_key)
    if normalized_sample is None or normalized_target is None:
        return 0.0
    return 1.0 if normalized_sample == normalized_target else 0.0


def score_type_match(sample_type: str | None, target_type: str | None) -> float:
    normalized_sample = _normalize_text(sample_type)
    normalized_target = _normalize_text(target_type)
    if normalized_sample is None or normalized_target is None:
        return 0.0
    return 1.0 if normalized_sample == normalized_target else 0.0


def combine_hybrid_score(
    semantic_score: float,
    metadata: HybridMetadata,
    query: HybridQuery,
) -> float:
    bpm_match = score_bpm_match(metadata.bpm, query.target_bpm, query.bpm_tolerance)
    key_match = score_key_match(metadata.key, query.target_key)
    type_match = score_type_match(metadata.pred_type, query.target_type)

    return (
        query.semantic_weight * semantic_score
        + query.bpm_weight * bpm_match
        + query.key_weight * key_match
        + query.type_weight * type_match
    )


def rerank_hits(
    hits: list[SearchHit],
    metadata_by_sample_id: dict[int, HybridMetadata],
    query: HybridQuery,
) -> list[SearchHit]:
    scored: list[tuple[float, int, int, SearchHit]] = []
    for original_index, hit in enumerate(hits):
        metadata = metadata_by_sample_id.get(
            hit.sample_id,
            HybridMetadata(sample_id=hit.sample_id),
        )
        combined = combine_hybrid_score(hit.score, metadata, query)
        scored.append((combined, original_index, hit.sample_id, hit))

    scored.sort(key=lambda item: (-item[0], item[1], item[2]))

    return [
        SearchHit(sample_id=hit.sample_id, path=hit.path, score=combined)
        for combined, _, _, hit in scored
    ]
