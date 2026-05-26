from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import json

import numpy as np

from .config import DATA_DIR
from .db import get_engine, text


@dataclass
class SearchHit:
    sample_id: int
    path: str
    score: float


@dataclass
class VectorIndex:
    vectors: np.ndarray
    sample_ids: list[int]
    model_id: int
    embedding_dim: int


def decode_embedding_blob(blob: bytes, embedding_dim: int) -> np.ndarray:
    arr = np.frombuffer(blob, dtype=np.float32)
    if arr.shape[0] != embedding_dim:
        raise ValueError(
            f"Blob length {arr.shape[0]} does not match expected dimension {embedding_dim}"
        )
    return arr


def normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def load_embeddings_for_model(
    model_id: int, limit: int | None = None
) -> tuple[np.ndarray, list[int]]:
    engine = get_engine()
    query = """
        SELECT e.sample_id, e.embedding, m.embedding_dim
        FROM sample_embeddings e
        JOIN embedding_models m ON m.id = e.model_id
        WHERE e.model_id = :model_id
        ORDER BY e.sample_id
    """
    if limit is not None:
        query += " LIMIT :limit"
    with engine.begin() as conn:
        params: dict = {"model_id": model_id}
        if limit is not None:
            params["limit"] = limit
        rows = conn.execute(text(query), params).fetchall()

    if not rows:
        return np.empty((0, 0), dtype=np.float32), []

    embedding_dim = rows[0][2]
    sample_ids: list[int] = []
    vectors_list: list[np.ndarray] = []
    for row in rows:
        sample_ids.append(row[0])
        vectors_list.append(decode_embedding_blob(row[1], embedding_dim))

    vectors = np.stack(vectors_list, axis=0)
    return vectors, sample_ids


def build_numpy_index(
    model_id: int, limit: int | None = None
) -> VectorIndex | None:
    vectors, sample_ids = load_embeddings_for_model(model_id, limit=limit)
    if len(sample_ids) == 0:
        return None

    embedding_dim = vectors.shape[1]
    normalized = normalize_vectors(vectors)
    return VectorIndex(
        vectors=normalized,
        sample_ids=sample_ids,
        model_id=model_id,
        embedding_dim=embedding_dim,
    )


def search_index(
    query_vector: np.ndarray,
    index: VectorIndex,
    topk: int = 10,
) -> list[SearchHit]:
    if query_vector.ndim != 1:
        raise ValueError(
            f"Query must be 1D, got shape {query_vector.shape}"
        )
    if query_vector.shape[0] != index.embedding_dim:
        raise ValueError(
            f"Query dimension {query_vector.shape[0]} "
            f"does not match index dimension {index.embedding_dim}"
        )

    query_norm = query_vector / (np.linalg.norm(query_vector) or 1.0)
    scores = index.vectors @ query_norm

    n = min(topk, len(scores))
    if n <= 0:
        return []

    top_indices = np.argsort(scores)[::-1][:n]
    return [
        SearchHit(
            sample_id=index.sample_ids[idx],
            path="",
            score=float(scores[idx]),
        )
        for idx in top_indices
    ]


def default_index_path(model_id: int, metric: str = "cosine") -> Path:
    indexes_dir = DATA_DIR / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)
    return indexes_dir / f"model-{model_id}-numpy-{metric}.npz"


def save_numpy_index(index: VectorIndex, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "format_version": 1,
        "backend": "numpy",
        "model_id": index.model_id,
        "embedding_dim": index.embedding_dim,
        "metric": "cosine",
        "normalized": True,
        "sample_count": len(index.sample_ids),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    np.savez_compressed(
        path,
        vectors=index.vectors,
        sample_ids=np.array(index.sample_ids, dtype=np.int64),
        metadata_json=json.dumps(metadata),
    )


def load_numpy_index(
    path: str | Path, model_id: int | None = None
) -> VectorIndex:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Index file not found: {path}")

    data = np.load(path)
    metadata = json.loads(data["metadata_json"].item())

    if metadata.get("format_version") != 1:
        raise ValueError(
            f"Unsupported format version: {metadata.get('format_version')}"
        )
    if metadata.get("metric") != "cosine":
        raise ValueError(f"Unsupported metric: {metadata.get('metric')}")
    if metadata.get("backend") != "numpy":
        raise ValueError(f"Unsupported backend: {metadata.get('backend')}")

    vectors = data["vectors"]
    sample_ids = data["sample_ids"].tolist()

    if vectors.shape[0] != len(sample_ids):
        raise ValueError(
            f"Vector count {vectors.shape[0]} does not match "
            f"sample count {len(sample_ids)}"
        )
    if vectors.shape[1] != metadata.get("embedding_dim"):
        raise ValueError(
            f"Vector dimension {vectors.shape[1]} does not match "
            f"metadata dimension {metadata.get('embedding_dim')}"
        )
    if model_id is not None and metadata.get("model_id") != model_id:
        raise ValueError(
            f"Index model_id {metadata.get('model_id')} does not match "
            f"requested model_id {model_id}"
        )

    return VectorIndex(
        vectors=vectors,
        sample_ids=sample_ids,
        model_id=metadata["model_id"],
        embedding_dim=metadata["embedding_dim"],
    )


def build_index(
    model_id: int | None = None,
    limit: int | None = None,
    save: bool = False,
    index_path: str | None = None,
) -> None:
    if model_id is None:
        print(
            "[INFO] No model_id specified. "
            "Use --model-id to select an embedding model."
        )
        return

    index = build_numpy_index(model_id, limit=limit)
    if index is None:
        print(
            f"[INFO] No embeddings found for model_id={model_id}. "
            "Run 'sample-brain embed' first."
        )
        return

    print(
        f"[INFO] Index built: model_id={index.model_id}, "
        f"dim={index.embedding_dim}, vectors={len(index.sample_ids)}"
    )

    if save:
        path = Path(index_path) if index_path else default_index_path(model_id)
        save_numpy_index(index, path)
        print(f"[INFO] Index saved to: {path}")
    else:
        print("[INFO] Index is in-memory. Use --save to persist.")
