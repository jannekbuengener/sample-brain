from __future__ import annotations
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.embed import (
    EmbeddingBackend,
    EmbeddingJobConfig,
    EmbeddingModelInfo,
    EmbeddingWorker,
    NoopEmbeddingBackend,
)


class FakeBackend(EmbeddingBackend):
    def __init__(self, dim: int = 3, fail_paths: set[str] | None = None) -> None:
        self._dim = dim
        self._fail_paths = fail_paths or set()

    def embed_audio(self, path: str) -> np.ndarray:
        if path in self._fail_paths:
            raise RuntimeError(f"Failed to embed {path}")
        vals = [float(i + 1) for i in range(self._dim)]
        return np.array(vals, dtype=np.float32)

    def embed_text(self, text: str) -> np.ndarray:
        raise NotImplementedError

    def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            provider="test",
            model_name="fake",
            model_version="1",
            embedding_dim=self._dim,
            modality="audio",
        )


class TestEmbeddingWorkerNoop:
    def test_noop_returns_without_db_calls(self):
        worker = EmbeddingWorker(NoopEmbeddingBackend())
        config = EmbeddingJobConfig()
        result = worker.run(config)
        assert result.processed == 0
        assert result.skipped == 0
        assert result.failed == 0
        assert "No embedding backend configured" in result.message


class TestEmbeddingWorkerWithFakeBackend:
    @patch("src.embed.upsert_embedding_model", return_value=7)
    @patch("src.embed.iter_pending_samples", return_value=[])
    @patch("src.embed.insert_sample_embedding")
    def test_no_pending_samples_returns_zeros(
        self, mock_insert, mock_pending, mock_upsert
    ):
        worker = EmbeddingWorker(FakeBackend(dim=3))
        config = EmbeddingJobConfig(limit=10)
        result = worker.run(config)
        assert result.processed == 0
        assert result.failed == 0
        mock_upsert.assert_called_once()
        mock_pending.assert_called_once_with(model_id=7, limit=10)
        mock_insert.assert_not_called()

    @patch("src.embed.upsert_embedding_model", return_value=7)
    @patch(
        "src.embed.iter_pending_samples",
        return_value=[(1, "/samples/kick.wav", "hash1")],
    )
    @patch("src.embed.insert_sample_embedding", return_value=100)
    def test_persists_pending_embedding(self, mock_insert, mock_pending, mock_upsert):
        worker = EmbeddingWorker(FakeBackend(dim=3))
        config = EmbeddingJobConfig()
        result = worker.run(config)
        assert result.processed == 1
        assert result.failed == 0
        mock_insert.assert_called_once()
        args, kwargs = mock_insert.call_args
        assert kwargs["sample_id"] == 1
        assert kwargs["model_id"] == 7
        assert kwargs["source_hash"] == "hash1"
        assert kwargs["embedding_format"] == "numpy.float32"
        embedding_bytes = kwargs["embedding"]
        arr = np.frombuffer(embedding_bytes, dtype=np.float32)
        assert arr.shape == (3,)
        assert list(arr) == [1.0, 2.0, 3.0]

    @patch("src.embed.upsert_embedding_model", return_value=7)
    @patch(
        "src.embed.iter_pending_samples",
        return_value=[
            (1, "/samples/kick.wav", "hash1"),
            (2, "/samples/bad.wav", "hash2"),
        ],
    )
    @patch("src.embed.insert_sample_embedding", return_value=100)
    def test_counts_failed_samples_and_continues(
        self, mock_insert, mock_pending, mock_upsert
    ):
        fail_paths = {"/samples/bad.wav"}
        worker = EmbeddingWorker(FakeBackend(dim=3, fail_paths=fail_paths))
        config = EmbeddingJobConfig()
        result = worker.run(config)
        assert result.processed == 1
        assert result.failed == 1

    @patch("src.embed.upsert_embedding_model", return_value=7)
    @patch(
        "src.embed.iter_pending_samples",
        return_value=[(1, "/samples/kick.wav", "hash1")],
    )
    @patch("src.embed.insert_sample_embedding")
    def test_rejects_dimension_mismatch(self, mock_insert, mock_pending, mock_upsert):
        class WrongDimBackend(EmbeddingBackend):
            def embed_audio(self, path):
                return np.array([1.0, 2.0], dtype=np.float32)

            def embed_text(self, text):
                raise NotImplementedError

            def model_info(self):
                return EmbeddingModelInfo(
                    provider="test",
                    model_name="wrong",
                    model_version="1",
                    embedding_dim=3,
                    modality="audio",
                )

        worker = EmbeddingWorker(WrongDimBackend())
        config = EmbeddingJobConfig()
        result = worker.run(config)
        assert result.processed == 0
        assert result.failed == 1
        mock_insert.assert_not_called()
