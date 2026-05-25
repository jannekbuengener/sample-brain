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
    def __init__(self) -> None:
        self._model = None
        self._processor = None
        self._device = "cpu"

    def _load_model(self) -> None:
        if self._model is not None:
            return
        try:
            import torch  # noqa: F811
            import transformers  # noqa: F811
        except ImportError:
            raise EmbeddingBackendUnavailableError(
                "CLAP dependencies not available. "
                "pip install torch transformers>=4.35"
            )
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        model_name = "laion/clap-htsat-unfused"
        self._model = transformers.ClapModel.from_pretrained(model_name).to(self._device)
        self._processor = transformers.ClapProcessor.from_pretrained(model_name)

    def embed_text(self, text: str) -> np.ndarray:
        self._load_model()
        import torch  # noqa: F811
        inputs = self._processor(text=text, return_tensors="pt", padding=True)
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        with torch.no_grad():
            output = self._model.get_text_features(**inputs)
        return output.pooler_output.cpu().numpy().flatten()

    def embed_audio(self, audio_path: str) -> np.ndarray:
        raise EmbeddingBackendUnavailableError(
            "Audio embedding not yet implemented in this spike. "
            "Requires audio processor integration."
        )

    def model_info(self) -> EmbeddingModelInfo:
        return _CLAP_METADATA


class EmbeddingWorker:
    def __init__(self, backend: EmbeddingBackend) -> None:
        self._backend = backend

    def run(self, config: EmbeddingJobConfig) -> EmbeddingRunResult:
        if isinstance(self._backend, NoopEmbeddingBackend):
            return EmbeddingRunResult(
                message=(
                    "No embedding backend configured. "
                    "Install torch + transformers and set up a CLAP backend."
                )
            )
        return EmbeddingRunResult(
            message="Worker skeleton: no samples processed."
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


def run_embed(limit: Optional[int] = None, only_missing: bool = True) -> None:
    config = EmbeddingJobConfig(limit=limit, only_missing=only_missing)
    backend = get_backend("noop")
    worker = EmbeddingWorker(backend)
    result = worker.run(config)
    print(f"[INFO] {result.message}")
    print("[INFO] No files were processed.")
