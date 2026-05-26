from __future__ import annotations

import numpy as np

from .embed import EmbeddingBackendUnavailableError, get_backend
from .index import build_numpy_index, load_numpy_index, search_index


def run_search(
    query: str | None = None,
    model_id: int | None = None,
    topk: int = 10,
    backend_name: str = "noop",
    index_path: str | None = None,
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

    for rank, hit in enumerate(hits, start=1):
        print(f"rank={rank} sample_id={hit.sample_id} score={hit.score:.4f}")
