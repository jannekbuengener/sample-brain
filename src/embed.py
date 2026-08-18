from __future__ import annotations
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .db import (
    insert_sample_embedding,
    iter_pending_samples,
    upsert_embedding_model,
)
from .model_readiness import CLAP_MODEL_NAME, CLAP_MODEL_REVISION


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


CLAP_EMBEDDING_DIM = 512
CLAP_MODALITY = "audio_text"
CLAP_PROVIDER = "laion"

_CLAP_METADATA = EmbeddingModelInfo(
    provider=CLAP_PROVIDER,
    model_name=CLAP_MODEL_NAME,
    model_version=CLAP_MODEL_REVISION,
    embedding_dim=CLAP_EMBEDDING_DIM,
    modality=CLAP_MODALITY,
)


def _clap_available() -> bool:
    """Probe optional CLAP imports without risking the current process.

    PyTorch's own installation verification begins with a real ``import torch``.
    On Windows, a broken native runtime can terminate the interpreter before a
    Python exception is raised, so the optional-dependency probe runs in a short
    child Python process. A non-zero exit or timeout means CLAP is unavailable.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import torch; import transformers"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _resolve_clap_cache_dir() -> Optional[str]:
    """Return ``SAMPLE_BRAIN_MODEL_CACHE_DIR`` if set, else ``None``.

    The value is forwarded as ``cache_dir`` to the CLAP model and processor
    loaders so model weights stay outside the repo. ``HF_HOME`` is a documented
    alternative but is never mutated here.
    """
    value = os.environ.get("SAMPLE_BRAIN_MODEL_CACHE_DIR")
    if not value:
        return None
    return str(value)


def _clap_feature_vector(output) -> np.ndarray:
    """Normalize supported Transformers CLAP feature-output shapes.

    Transformers has returned direct tensors in 4.x and documents model-output
    objects in current 5.x releases. Keep this boundary tolerant while retaining
    the existing downstream 512-d validation.
    """
    value = output
    if hasattr(value, "pooler_output"):
        value = value.pooler_output
    elif isinstance(value, (tuple, list)):
        if not value:
            raise ValueError("CLAP feature output is empty")
        value = value[0]

    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()

    try:
        arr = np.asarray(value, dtype=np.float32)
    except Exception as exc:
        raise ValueError("Unsupported CLAP feature output") from exc
    if arr.size == 0:
        raise ValueError("CLAP feature output is empty")
    return arr.flatten()


class ClapEmbeddingBackend(EmbeddingBackend):
    def __init__(self) -> None:
        self._model = None
        self._processor = None
        self._device = "cpu"

    def _load_model(self) -> None:
        if self._model is not None:
            return
        if not _clap_available():
            raise EmbeddingBackendUnavailableError(
                "CLAP dependencies not available. "
                "Install with: pip install -e .[clap]"
            )
        try:
            import torch  # noqa: F811
            import transformers  # noqa: F811
        except ImportError:
            raise EmbeddingBackendUnavailableError(
                "CLAP dependencies not available. "
                "Install with: pip install -e .[clap]"
            )
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        common_load_kwargs: dict = {"revision": CLAP_MODEL_REVISION}
        cache_dir = _resolve_clap_cache_dir()
        if cache_dir is not None:
            common_load_kwargs["cache_dir"] = cache_dir
        model_load_kwargs = dict(common_load_kwargs)
        model_load_kwargs["use_safetensors"] = True
        try:
            self._model = transformers.ClapModel.from_pretrained(
                CLAP_MODEL_NAME, **model_load_kwargs
            ).to(self._device)
            self._processor = transformers.ClapProcessor.from_pretrained(
                CLAP_MODEL_NAME, **common_load_kwargs
            )
        except Exception as exc:
            raise EmbeddingBackendUnavailableError(
                f"CLAP model {CLAP_MODEL_NAME}@{CLAP_MODEL_REVISION} could not be loaded: {exc}. "
                "Ensure the [clap] extra is installed and the pinned safetensors "
                "snapshot is available (online first run downloads it, or use a "
                "populated SAMPLE_BRAIN_MODEL_CACHE_DIR offline)."
            ) from exc
        self._model.eval()

    def embed_text(self, text: str) -> np.ndarray:
        if not text:
            raise ValueError("embed_text requires a non-empty string")
        self._load_model()
        import torch  # noqa: F811
        inputs = self._processor(text=text, return_tensors="pt", padding=True)
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        with torch.no_grad():
            output = self._model.get_text_features(**inputs)
        return _clap_feature_vector(output)

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
        return _clap_feature_vector(output)

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
