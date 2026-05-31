from __future__ import annotations

import numpy as np

from .db import load_hybrid_metadata, load_sample_paths
from .embed import EmbeddingBackendUnavailableError, get_backend
from .hybrid_rank import HybridQuery, rerank_hits
from .index import build_numpy_index, load_numpy_index, search_index

DEFAULT_METADATA_WEIGHT = 0.5


def _fmt_optional(value: object | None) -> str:
    return "" if value is None else str(value)


def normalize_hybrid_query(query: HybridQuery) -> HybridQuery:
    bpm_weight = query.bpm_weight
    key_weight = query.key_weight
    type_weight = query.type_weight

    if query.target_bpm is not None and bpm_weight == 0.0:
        bpm_weight = DEFAULT_METADATA_WEIGHT
    if query.target_key is not None and key_weight == 0.0:
        key_weight = DEFAULT_METADATA_WEIGHT
    if query.target_type is not None and type_weight == 0.0:
        type_weight = DEFAULT_METADATA_WEIGHT

    if (
        bpm_weight == query.bpm_weight
        and key_weight == query.key_weight
        and type_weight == query.type_weight
    ):
        return query

    return HybridQuery(
        target_bpm=query.target_bpm,
        target_key=query.target_key,
        target_type=query.target_type,
        semantic_weight=query.semantic_weight,
        bpm_weight=bpm_weight,
        key_weight=key_weight,
        type_weight=type_weight,
        bpm_tolerance=query.bpm_tolerance,
    )


def hybrid_rerank_active(query: HybridQuery) -> bool:
    normalized = normalize_hybrid_query(query)
    return (
        normalized.target_bpm is not None
        or normalized.target_key is not None
        or normalized.target_type is not None
        or normalized.bpm_weight != 0.0
        or normalized.key_weight != 0.0
        or normalized.type_weight != 0.0
    )


def hybrid_query_from_cli_args(args) -> HybridQuery | None:
    has_target = (
        args.target_bpm is not None
        or args.target_key is not None
        or args.target_type is not None
    )
    has_metadata_weight = (
        args.bpm_weight != 0.0
        or args.key_weight != 0.0
        or args.type_weight != 0.0
    )
    if not has_target and not has_metadata_weight:
        return None

    query = HybridQuery(
        target_bpm=args.target_bpm,
        target_key=args.target_key,
        target_type=args.target_type,
        semantic_weight=args.semantic_weight,
        bpm_weight=args.bpm_weight,
        key_weight=args.key_weight,
        type_weight=args.type_weight,
        bpm_tolerance=args.bpm_tolerance,
    )
    normalized = normalize_hybrid_query(query)
    if not hybrid_rerank_active(normalized):
        return None
    return normalized


def run_search(
    query: str | None = None,
    model_id: int | None = None,
    topk: int = 10,
    backend_name: str = "noop",
    index_path: str | None = None,
    hybrid_query: HybridQuery | None = None,
) -> None:
    if model_id is None:
        print("[ERROR] search requires --model-id for now.")
        return

    if not query:
        print("[ERROR] search requires a query string.")
        return

    if topk <= 0:
        print("[ERROR] search requires --topk > 0.")
        return

    try:
        backend = get_backend(backend_name)
        embedding = backend.embed_text(query)
    except EmbeddingBackendUnavailableError:
        print("[ERROR] The selected embedding backend is not available.")
        print("[INFO] Install torch + transformers and use 'sample-brain embed --backend clap' first.")
        return
    except NotImplementedError:
        print("[ERROR] No embedding backend configured.")
        print("[INFO] Use --backend clap or set embedding.backend in your profile.")
        return

    query_vec = np.asarray(
        embedding.vector if hasattr(embedding, "vector") else embedding,
        dtype=np.float32,
    )
    if query_vec.ndim != 1:
        print(f"[ERROR] Search failed: expected 1D query vector, got shape {query_vec.shape}")
        return

    try:
        if index_path:
            index = load_numpy_index(index_path, model_id=model_id)
        else:
            index = build_numpy_index(model_id=model_id)
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] {e}")
        return

    if index is None:
        print("[INFO] No search results.")
        return

    try:
        hits = search_index(query_vec, index, topk=topk)
    except ValueError as e:
        print(f"[ERROR] Search failed: {e}")
        return

    if not hits:
        print("[INFO] No search results.")
        return

    sample_ids = [hit.sample_id for hit in hits]
    sample_paths = load_sample_paths(sample_ids)
    metadata = load_hybrid_metadata(sample_ids)

    if hybrid_query is not None and hybrid_rerank_active(hybrid_query):
        normalized = normalize_hybrid_query(hybrid_query)
        hits = rerank_hits(hits, metadata, normalized)

    for rank, hit in enumerate(hits, start=1):
        hit_path = hit.path or sample_paths.get(hit.sample_id, "")
        hit_metadata = metadata.get(hit.sample_id)
        print(
            " ".join(
                [
                    f"rank={rank}",
                    f"sample_id={hit.sample_id}",
                    f"score={hit.score:.4f}",
                    f"path={hit_path}",
                    f"bpm={_fmt_optional(hit_metadata.bpm if hit_metadata else None)}",
                    f"key={_fmt_optional(hit_metadata.key if hit_metadata else None)}",
                    f"pred_type={_fmt_optional(hit_metadata.pred_type if hit_metadata else None)}",
                    f"class={_fmt_optional(hit_metadata.audio_class if hit_metadata else None)}",
                ]
            )
        )
