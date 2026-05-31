from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .db import load_hybrid_metadata, load_sample_paths
from .embed import EmbeddingBackendUnavailableError, get_backend
from .hybrid_rank import HybridQuery, rerank_hits
from .index import SearchHit, normalize_vectors
from .search_backend import (
    SearchBackendError,
    StaleVecCacheError,
    get_search_backend,
)
from .search_filters import SearchFilters, resolve_filtered_sample_ids

DEFAULT_METADATA_WEIGHT = 0.5


@dataclass(frozen=True)
class SearchRunResult:
    hits: tuple[SearchHit, ...] = ()
    error: str | None = None
    info: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


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


def collect_search_hits(
    query: str | None = None,
    query_audio: str | None = None,
    query_vector: np.ndarray | None = None,
    model_id: int | None = None,
    topk: int = 10,
    backend_name: str = "noop",
    search_backend: str = "numpy",
    index_path: str | None = None,
    hybrid_query: HybridQuery | None = None,
    search_filters: SearchFilters | None = None,
) -> SearchRunResult:
    if model_id is None:
        return SearchRunResult(error="search requires --model-id for now.")

    if query_vector is None:
        if query and query_audio:
            return SearchRunResult(
                error="search accepts either a text query or --query-audio, not both."
            )

        if not query and not query_audio:
            return SearchRunResult(
                error="search requires a text query or --query-audio."
            )

        query_text = query.strip() if query else None
        if query is not None and not query_text:
            return SearchRunResult(
                error="search requires a text query or --query-audio."
            )

        audio_path = Path(query_audio).expanduser() if query_audio else None
        if audio_path is not None and not audio_path.is_file():
            return SearchRunResult(error=f"query audio file not found: {audio_path}")

        if topk <= 0:
            return SearchRunResult(error="search requires --topk > 0.")

        try:
            backend = get_backend(backend_name)
            if audio_path is not None:
                embedding = backend.embed_audio(str(audio_path))
            else:
                embedding = backend.embed_text(query_text)
        except EmbeddingBackendUnavailableError:
            return SearchRunResult(
                error="The selected embedding backend is not available."
            )
        except NotImplementedError:
            return SearchRunResult(error="No embedding backend configured.")

        query_vec = np.asarray(
            embedding.vector if hasattr(embedding, "vector") else embedding,
            dtype=np.float32,
        )
        if query_vec.ndim != 1:
            return SearchRunResult(
                error=f"Search failed: expected 1D query vector, got shape {query_vec.shape}"
            )
    else:
        if topk <= 0:
            return SearchRunResult(error="search requires --topk > 0.")
        query_vec = np.asarray(query_vector, dtype=np.float32)
        if query_vec.ndim != 1:
            return SearchRunResult(
                error=f"Search failed: expected 1D query vector, got shape {query_vec.shape}"
            )

    query_vec = normalize_vectors(query_vec.reshape(1, -1))[0]

    if search_backend == "sqlite-vec" and index_path:
        return SearchRunResult(
            error="--index-path is only supported with --search-backend numpy."
        )

    candidate_sample_ids = resolve_filtered_sample_ids(search_filters)
    if candidate_sample_ids is not None and len(candidate_sample_ids) == 0:
        return SearchRunResult(info="No search results.")

    try:
        backend = get_search_backend(search_backend)
        hits = backend.search(
            query_vec,
            model_id,
            topk=topk,
            index_path=index_path,
            candidate_sample_ids=candidate_sample_ids,
        )
    except FileNotFoundError as e:
        return SearchRunResult(error=str(e))
    except ValueError as e:
        return SearchRunResult(error=f"Search failed: {e}")
    except StaleVecCacheError as e:
        return SearchRunResult(error=str(e))
    except SearchBackendError as e:
        return SearchRunResult(error=str(e))

    if not hits:
        return SearchRunResult(info="No search results.")

    sample_ids = [hit.sample_id for hit in hits]
    metadata = load_hybrid_metadata(sample_ids)

    if hybrid_query is not None and hybrid_rerank_active(hybrid_query):
        normalized = normalize_hybrid_query(hybrid_query)
        hits = rerank_hits(hits, metadata, normalized)

    return SearchRunResult(hits=tuple(hits))


def run_search(
    query: str | None = None,
    query_audio: str | None = None,
    model_id: int | None = None,
    topk: int = 10,
    backend_name: str = "noop",
    search_backend: str = "numpy",
    index_path: str | None = None,
    hybrid_query: HybridQuery | None = None,
    search_filters: SearchFilters | None = None,
) -> None:
    result = collect_search_hits(
        query=query,
        query_audio=query_audio,
        model_id=model_id,
        topk=topk,
        backend_name=backend_name,
        search_backend=search_backend,
        index_path=index_path,
        hybrid_query=hybrid_query,
        search_filters=search_filters,
    )

    if result.error:
        if result.error == "The selected embedding backend is not available.":
            print("[ERROR] The selected embedding backend is not available.")
            print(
                "[INFO] Install torch + transformers and use "
                "'sample-brain embed --backend clap' first."
            )
            return
        if result.error == "No embedding backend configured.":
            print("[ERROR] No embedding backend configured.")
            print("[INFO] Use --backend clap or set embedding.backend in your profile.")
            return
        if result.error.startswith("Search failed:"):
            print(f"[ERROR] {result.error}")
            return
        if result.error.startswith("query audio file not found:"):
            print(f"[ERROR] {result.error}")
            return
        if result.error == "--index-path is only supported with --search-backend numpy.":
            print(f"[ERROR] {result.error}")
            return
        if "search requires" in result.error:
            print(f"[ERROR] {result.error}")
            return
        if result.error.startswith("search accepts"):
            print(f"[ERROR] {result.error}")
            return
        print(f"[ERROR] {result.error}")
        return

    if result.info:
        print(f"[INFO] {result.info}")
        return

    sample_ids = [hit.sample_id for hit in result.hits]
    sample_paths = load_sample_paths(sample_ids)
    metadata = load_hybrid_metadata(sample_ids)

    for rank, hit in enumerate(result.hits, start=1):
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
