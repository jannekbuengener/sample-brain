from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np


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


_backend: Optional[EmbeddingBackend] = None


def get_backend(name: str = "noop") -> EmbeddingBackend:
    global _backend
    if _backend is not None:
        return _backend
    if name == "noop":
        _backend = NoopEmbeddingBackend()
    else:
        raise ValueError(f"Unknown embedding backend: {name}")
    return _backend


def run_embed(limit: Optional[int] = None, only_missing: bool = True) -> None:
    print(
        "[INFO] Embedding pipeline is not yet implemented. "
        "Run `sample-brain init` first, then install an embedding backend "
        "(e.g. CLAP with torch + transformers)."
    )
    print("[INFO] No files were processed.")
