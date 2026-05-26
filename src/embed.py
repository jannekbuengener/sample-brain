from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .db import (
    insert_sample_embedding,
    iter_pending_samples,
    upsert_embedding_model,
)


@dataclass
class EmbeddingVector:
    vector: np.ndarray
    model_id: int
    sample_id: int
    source_hash: str
    embedding_format: str = "numpy-blob"


@dataclass
class EmbeddingModelInfo:
    provider: str
    model_name: str
    model_version: Optional[str]
    embedding_dim: int
    modality: str


@dataclass
class EmbeddingJobConfig:
    limit: Optional[int] = None
    only_missing: bool = True
    backend_name: str = "noop"


@dataclass
class EmbeddingRunResult:
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    message: str = ""


class EmbeddingBackendUnavailableError(RuntimeError):
    ...


class EmbeddingBackend(ABC):
    @abstractmethod
    def embed_audio(self, audio_path: str) -> np.ndarray:
        ...

    @abstractmethod
    def embed_text(self, text: str) -> np.ndarray:
        ...

    @abstractmethod
    def model_info(self) -> EmbeddingModelInfo:
        ...


class NoopEmbeddingBackend(EmbeddingBackend):
    def embed_audio(self, audio_path: str) -> np.ndarray:
        raise NotImplementedError(
            "No embedding backend configured. "
            "Install torch + transformers and set up a CLAP backend."
        )

    def embed_text(self, text: str) -> np.ndarray:
        raise NotImplementedError(
            "No embedding backend configured. "
            "Install torch + transformers and set up a CLAP backend."
        )

    def model_info(self) -> EmbeddingModelInfo:
        raise NotImplementedError(
            "No embedding backend configured. "
            "Install torch + transformers and set up a CLAP backend."
        )


_CLAP_METADATA = EmbeddingModelInfo(
    provider="laion",
    model_name="laion/clap-htsat-unfused",
    model_version="planned",
    embedding_dim=512,
    modality="audio_text",
)


def _clap_available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except ImportError:
        return False


class ClapEmbeddingBackend(EmbeddingBackend):
    def embed_audio(self, audio_path: str) -> np.ndarray:
        raise EmbeddingBackendUnavailableError(
            "CLAP backend is not yet implemented. "
            "Install torch, transformers, and clap "
            "to enable real audio embedding."
        )

    def embed_text(self, text: str) -> np.ndarray:
        raise EmbeddingBackendUnavailableError(
            "CLAP backend is not yet implemented. "
            "Install torch, transformers, and clap "
            "to enable real text embedding."
        )

    def model_info(self) -> EmbeddingModelInfo:
        return _CLAP_METADATA


class EmbeddingWorker:
    def __init__(self, backend: EmbeddingBackend) -> None:
        self._backend = backend

    def run(self, config: EmbeddingJobConfig) -> EmbeddingRunResult:
        if isinstance(self._backend, NoopEmbeddingBackend):
            return EmbeddingRunResult(
                processed=0,
                skipped=0,
                failed=0,
                message=(
                    "No embedding backend configured. "
                    "Install torch + transformers and set up a CLAP backend."
                ),
            )

        info = self._backend.model_info()
        model_id = upsert_embedding_model(
            provider=info.provider,
            model_name=info.model_name,
            model_version=info.model_version,
            embedding_dim=info.embedding_dim,
            modality=info.modality,
        )

        pending = iter_pending_samples(model_id=model_id, limit=config.limit)

        processed = 0
        skipped = 0
        failed = 0

        for sample_id, path, source_hash in pending:
            try:
                vector = self._backend.embed_audio(path)
                arr = np.asarray(
                    vector.vector if hasattr(vector, "vector") else vector,
                    dtype=np.float32,
                )

                if arr.ndim != 1:
                    raise ValueError(
                        f"Embedding must be 1D, got shape {arr.shape}"
                    )

                if arr.shape[0] != info.embedding_dim:
                    raise ValueError(
                        f"Embedding dimension mismatch: "
                        f"expected {info.embedding_dim}, got {arr.shape[0]}"
                    )

                insert_sample_embedding(
                    sample_id=sample_id,
                    model_id=model_id,
                    embedding=arr.tobytes(),
                    embedding_format="numpy.float32",
                    source_hash=source_hash,
                )
                processed += 1
            except Exception as exc:
                failed += 1
                print(f"[WARN] Failed to embed sample_id={sample_id}: {exc}")

        return EmbeddingRunResult(
            processed=processed,
            skipped=skipped,
            failed=failed,
            message=(
                f"Embedding run complete: "
                f"processed={processed}, skipped={skipped}, failed={failed}."
            ),
        )


_backend: Optional[EmbeddingBackend] = None


def get_backend(name: str = "noop") -> EmbeddingBackend:
    global _backend
    if _backend is not None:
        return _backend
    if name == "noop":
        _backend = NoopEmbeddingBackend()
    elif name == "clap":
        _backend = ClapEmbeddingBackend()
    else:
        raise ValueError(f"Unknown embedding backend: {name}")
    return _backend


def run_embed(limit: Optional[int] = None, only_missing: bool = True, backend_name: str = "noop") -> None:
    config = EmbeddingJobConfig(limit=limit, only_missing=only_missing, backend_name=backend_name)
    backend = get_backend(backend_name)
    worker = EmbeddingWorker(backend)
    result = worker.run(config)
    print(f"[INFO] {result.message}")
