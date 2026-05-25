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
        self._load_model()
        try:
            import librosa
        except ImportError:
            raise EmbeddingBackendUnavailableError(
                "librosa is required for audio loading."
            )
        import torch  # noqa: F811
        y, sr = librosa.load(audio_path, sr=48000, mono=True)
        y = np.asarray(y, dtype=np.float32)
        inputs = self._processor(audio=y, sampling_rate=sr, return_tensors="pt")
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        with torch.no_grad():
            output = self._model.get_audio_features(**inputs)
        return output.pooler_output.cpu().numpy().flatten()

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
        from .db import init_db, upsert_embedding_model, insert_sample_embedding, iter_pending_samples
        init_db()
        info = self._backend.model_info()
        model_id = upsert_embedding_model(
            provider=info.provider,
            model_name=info.model_name,
            model_version=info.model_version,
            embedding_dim=info.embedding_dim,
            modality=info.modality,
        )
        pending = iter_pending_samples(
            model_id=model_id,
            limit=config.limit,
            only_missing=config.only_missing,
        )
        processed = 0
        failed = 0
        for row in pending:
            try:
                vector = self._backend.embed_audio(row["path"])
                embedding_bytes = vector.astype(np.float32).tobytes()
                insert_sample_embedding(
                    sample_id=row["id"],
                    model_id=model_id,
                    embedding=embedding_bytes,
                    embedding_format="float32_blob",
                    source_hash=row["hash"] or "",
                )
                processed += 1
            except Exception:
                failed += 1
        return EmbeddingRunResult(
            processed=processed,
            failed=failed,
            message=f"Processed {processed}, failed {failed}.",
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


def run_embed(
    limit: Optional[int] = None,
    only_missing: bool = True,
    backend_name: str = "noop",
) -> None:
    config = EmbeddingJobConfig(
        limit=limit,
        only_missing=only_missing,
        backend_name=backend_name,
    )
    backend = get_backend(config.backend_name)
    worker = EmbeddingWorker(backend)
    result = worker.run(config)
    print(f"[INFO] {result.message}")
    if result.processed == 0:
        print("[INFO] No files were processed.")
