from __future__ import annotations

import sqlite3
from typing import Protocol

import numpy as np
import sqlite_vec

from .db import get_vector_index_state
from .index import SearchHit, build_numpy_index, load_numpy_index, normalize_vectors, search_index
from .vec_index import (
    SQLITE_VEC_BACKEND,
    VEC_SAMPLE_CURRENT_TABLE,
    compute_source_fingerprint,
    load_current_embedding_rows,
    open_vec_connection,
    require_sqlite_vec,
)

VALID_SEARCH_BACKENDS = frozenset({"numpy", "sqlite-vec"})


class SearchBackendError(RuntimeError):
    """Raised when vector search cannot run."""


class StaleVecCacheError(SearchBackendError):
    """Raised when sqlite-vec cache metadata does not match embeddings."""


class NumpySearchBackend:
    def search(
        self,
        query_vector: np.ndarray,
        model_id: int,
        topk: int,
        *,
        index_path: str | None = None,
        candidate_sample_ids: set[int] | None = None,
    ) -> list[SearchHit]:
        if index_path:
            index = load_numpy_index(index_path, model_id=model_id)
        else:
            built = build_numpy_index(model_id=model_id)
            if built is None:
                return []
            index = built

        hits = search_index(query_vector, index, topk=topk)
        if candidate_sample_ids is None:
            return hits
        filtered = [hit for hit in hits if hit.sample_id in candidate_sample_ids]
        if len(filtered) >= topk:
            return filtered[:topk]
        return self._fill_filtered_hits(
            query_vector,
            index,
            topk,
            candidate_sample_ids,
            filtered,
        )

    def _fill_filtered_hits(
        self,
        query_vector: np.ndarray,
        index,
        topk: int,
        candidate_sample_ids: set[int],
        initial_hits: list[SearchHit],
    ) -> list[SearchHit]:
        fetch_k = min(len(index.sample_ids), max(topk * 50, 200))
        expanded = search_index(query_vector, index, topk=fetch_k)
        seen = {hit.sample_id for hit in initial_hits}
        merged = list(initial_hits)
        for hit in expanded:
            if hit.sample_id in candidate_sample_ids and hit.sample_id not in seen:
                merged.append(hit)
                seen.add(hit.sample_id)
            if len(merged) >= topk:
                break
        return merged[:topk]


class SqliteVecSearchBackend:
    def search(
        self,
        query_vector: np.ndarray,
        model_id: int,
        topk: int,
        *,
        index_path: str | None = None,
        candidate_sample_ids: set[int] | None = None,
    ) -> list[SearchHit]:
        if index_path:
            raise SearchBackendError(
                "sqlite-vec search does not use --index-path; rebuild the SQLite vec0 cache instead."
            )

        require_sqlite_vec()
        state = get_vector_index_state(model_id, SQLITE_VEC_BACKEND)
        if state is None:
            raise StaleVecCacheError(
                "No sqlite-vec cache found. Run "
                "'sample-brain index_build --search-backend sqlite-vec --model-id ...' first."
            )

        rows = load_current_embedding_rows(model_id)
        fingerprint = compute_source_fingerprint(
            [(sample_id, source_hash) for sample_id, _, source_hash, _ in rows]
        )
        if state.get("source_fingerprint") != fingerprint:
            raise StaleVecCacheError(
                "sqlite-vec cache is stale. Rebuild with "
                "'sample-brain index_build --search-backend sqlite-vec --model-id ...'."
            )

        embedding_dim = int(state["embedding_dim"])
        if query_vector.shape[0] != embedding_dim:
            raise ValueError(
                f"Query dimension {query_vector.shape[0]} "
                f"does not match cache dimension {embedding_dim}"
            )

        query_norm = normalize_vectors(query_vector.reshape(1, -1))[0]
        serialized = sqlite_vec.serialize_float32(query_norm.astype(np.float32))
        fetch_k = topk
        if candidate_sample_ids is not None:
            fetch_k = min(
                int(state["sample_count"]),
                max(topk * 50, 200),
            )

        conn = open_vec_connection()
        try:
            conn.row_factory = sqlite3.Row
            matches = conn.execute(
                f"""
                SELECT rowid, distance
                FROM {VEC_SAMPLE_CURRENT_TABLE}
                WHERE embedding MATCH ?
                ORDER BY distance
                LIMIT ?
                """,
                (serialized, fetch_k),
            ).fetchall()
        finally:
            conn.close()

        hits: list[SearchHit] = []
        for row in matches:
            sample_id = int(row["rowid"])
            if candidate_sample_ids is not None and sample_id not in candidate_sample_ids:
                continue
            distance = float(row["distance"])
            hits.append(
                SearchHit(
                    sample_id=sample_id,
                    path="",
                    score=-distance,
                )
            )
            if len(hits) >= topk:
                break
        return hits


class SearchBackend(Protocol):
    def search(
        self,
        query_vector: np.ndarray,
        model_id: int,
        topk: int,
        *,
        index_path: str | None = None,
        candidate_sample_ids: set[int] | None = None,
    ) -> list[SearchHit]:
        ...


def get_search_backend(name: str) -> SearchBackend:
    if name == "numpy":
        return NumpySearchBackend()
    if name == "sqlite-vec":
        return SqliteVecSearchBackend()
    raise ValueError(
        f"Unknown search backend: {name!r}. "
        f"Must be one of: {', '.join(sorted(VALID_SEARCH_BACKENDS))}"
    )
