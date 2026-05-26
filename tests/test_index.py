from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock, patch
import json

import numpy as np
import pytest

from src.index import (
    VectorIndex,
    SearchHit,
    decode_embedding_blob,
    normalize_vectors,
    search_index,
    build_numpy_index,
    build_index,
    save_numpy_index,
    load_numpy_index,
    default_index_path,
)


class TestDecodeEmbeddingBlob:
    def test_decodes_float32_blob(self):
        arr = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        blob = arr.tobytes()
        result = decode_embedding_blob(blob, 3)
        assert np.allclose(result, arr)
        assert result.dtype == np.float32

    def test_rejects_dimension_mismatch(self):
        arr = np.array([1.0, 2.0], dtype=np.float32)
        blob = arr.tobytes()
        with pytest.raises(ValueError, match="Blob length 2"):
            decode_embedding_blob(blob, 3)


class TestNormalizeVectors:
    def test_normalizes_to_unit_length(self):
        vectors = np.array([[3.0, 4.0], [1.0, 0.0]], dtype=np.float32)
        result = normalize_vectors(vectors)
        norms = np.linalg.norm(result, axis=1)
        assert np.allclose(norms, 1.0)

    def test_handles_zero_vector(self):
        vectors = np.array([[0.0, 0.0]], dtype=np.float32)
        result = normalize_vectors(vectors)
        assert np.allclose(result, [0.0, 0.0])

    def test_preserves_dimensions(self):
        vectors = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)
        result = normalize_vectors(vectors)
        assert result.shape == (1, 3)


class TestSearchIndex:
    def test_returns_ranked_hits(self):
        vectors = np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]], dtype=np.float32)
        index = VectorIndex(
            vectors=vectors,
            sample_ids=[10, 20, 30],
            model_id=1,
            embedding_dim=2,
        )
        query = np.array([1.0, 0.0], dtype=np.float32)
        hits = search_index(query, index, topk=2)
        assert len(hits) == 2
        assert hits[0].sample_id == 10
        assert hits[0].score > hits[1].score

    def test_empty_index_returns_empty(self):
        vectors = np.empty((0, 3), dtype=np.float32)
        index = VectorIndex(
            vectors=vectors,
            sample_ids=[],
            model_id=1,
            embedding_dim=3,
        )
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        hits = search_index(query, index, topk=10)
        assert hits == []

    def test_rejects_dimension_mismatch(self):
        vectors = np.array([[1.0, 0.0]], dtype=np.float32)
        index = VectorIndex(
            vectors=vectors,
            sample_ids=[1],
            model_id=1,
            embedding_dim=2,
        )
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        with pytest.raises(ValueError, match="Query dimension 3"):
            search_index(query, index)

    def test_returns_search_hit_fields(self):
        vectors = np.array([[1.0, 0.0]], dtype=np.float32)
        index = VectorIndex(
            vectors=vectors,
            sample_ids=[42],
            model_id=1,
            embedding_dim=2,
        )
        query = np.array([1.0, 0.0], dtype=np.float32)
        hits = search_index(query, index, topk=1)
        assert len(hits) == 1
        hit = hits[0]
        assert hit.sample_id == 42
        assert isinstance(hit.score, float)


class TestBuildNumpyIndex:
    @patch("src.index.get_engine")
    def test_returns_none_on_empty(self, mock_get_engine):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_engine = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        result = build_numpy_index(model_id=1)
        assert result is None

    @patch("src.index.get_engine")
    def test_builds_index_from_db_rows(self, mock_get_engine):
        dim = 3
        vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        blob = vec.tobytes()
        rows = [(1, blob, dim), (2, blob, dim)]

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = rows
        mock_engine = MagicMock()
        mock_engine.begin.return_value.__enter__.return_value = mock_conn
        mock_get_engine.return_value = mock_engine

        result = build_numpy_index(model_id=1)
        assert result is not None
        assert result.model_id == 1
        assert result.embedding_dim == 3
        assert result.sample_ids == [1, 2]
        assert result.vectors.shape == (2, 3)


class TestBuildIndexCLI:
    def test_no_model_id_prints_info(self, capsys):
        build_index(model_id=None)
        captured = capsys.readouterr()
        assert "No model_id specified" in captured.out

    @patch("src.index.build_numpy_index", return_value=None)
    def test_no_embeddings_prints_info(self, mock_build, capsys):
        build_index(model_id=1)
        captured = capsys.readouterr()
        assert "No embeddings found" in captured.out

    @patch("src.index.build_numpy_index")
    def test_index_built_prints_summary(self, mock_build, capsys):
        mock_index = MagicMock()
        mock_index.model_id = 1
        mock_index.embedding_dim = 3
        mock_index.sample_ids = [10, 20]
        mock_build.return_value = mock_index

        build_index(model_id=1)
        captured = capsys.readouterr()
        assert "Index built" in captured.out
        assert "vectors=2" in captured.out

    @patch("src.index.build_numpy_index")
    def test_build_index_save_prints_path(self, mock_build, capsys, tmp_path):
        mock_index = MagicMock()
        mock_index.model_id = 1
        mock_index.embedding_dim = 3
        mock_index.sample_ids = [10, 20]
        mock_index.vectors = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
        mock_build.return_value = mock_index

        index_path = tmp_path / "test.npz"
        build_index(model_id=1, save=True, index_path=str(index_path))
        captured = capsys.readouterr()
        assert "Index saved to" in captured.out
        assert index_path.exists()

    def test_build_index_save_without_path_prints_info(self, capsys):
        build_index(model_id=1, save=True)
        captured = capsys.readouterr()
        assert "No embeddings found" in captured.out


class TestSaveLoadIndex:
    def _make_index(self, model_id=1, dim=3, n=2):
        vectors = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)[:n]
        return VectorIndex(
            vectors=vectors,
            sample_ids=list(range(10, 10 + n)),
            model_id=model_id,
            embedding_dim=dim,
        )

    def test_save_load_roundtrip(self, tmp_path):
        index = self._make_index(model_id=1, dim=3, n=2)
        path = tmp_path / "test.npz"

        save_numpy_index(index, path)
        assert path.exists()

        loaded = load_numpy_index(path)
        assert loaded.model_id == 1
        assert loaded.embedding_dim == 3
        assert loaded.sample_ids == [10, 11]
        assert loaded.vectors.shape == (2, 3)
        assert np.allclose(loaded.vectors, index.vectors)

    def test_load_nonexistent_path(self, tmp_path):
        path = tmp_path / "nonexistent.npz"
        with pytest.raises(FileNotFoundError, match="Index file not found"):
            load_numpy_index(path)

    def test_load_rejects_wrong_model_id(self, tmp_path):
        index = self._make_index(model_id=1)
        path = tmp_path / "test.npz"
        save_numpy_index(index, path)

        with pytest.raises(ValueError, match="Index model_id 1 does not match requested model_id 2"):
            load_numpy_index(path, model_id=2)

    def test_load_rejects_bad_format_version(self, tmp_path):
        index = self._make_index()
        path = tmp_path / "bad_version.npz"
        save_numpy_index(index, path)

        data = np.load(path)
        bad_meta = json.loads(data["metadata_json"].item())
        bad_meta["format_version"] = 99
        np.savez_compressed(
            path,
            vectors=data["vectors"],
            sample_ids=data["sample_ids"],
            metadata_json=json.dumps(bad_meta),
        )
        data.close()

        with pytest.raises(ValueError, match="Unsupported format version"):
            load_numpy_index(path)

    def test_load_rejects_bad_metric(self, tmp_path):
        index = self._make_index()
        path = tmp_path / "bad_metric.npz"
        save_numpy_index(index, path)

        data = np.load(path)
        bad_meta = json.loads(data["metadata_json"].item())
        bad_meta["metric"] = "euclidean"
        np.savez_compressed(
            path,
            vectors=data["vectors"],
            sample_ids=data["sample_ids"],
            metadata_json=json.dumps(bad_meta),
        )
        data.close()

        with pytest.raises(ValueError, match="Unsupported metric"):
            load_numpy_index(path)

    def test_load_rejects_dimension_mismatch(self, tmp_path):
        index = self._make_index(dim=3)
        path = tmp_path / "dim_mismatch.npz"
        save_numpy_index(index, path)

        data = np.load(path)
        bad_meta = json.loads(data["metadata_json"].item())
        bad_meta["embedding_dim"] = 128
        np.savez_compressed(
            path,
            vectors=data["vectors"],
            sample_ids=data["sample_ids"],
            metadata_json=json.dumps(bad_meta),
        )
        data.close()

        with pytest.raises(ValueError, match="does not match"):
            load_numpy_index(path)

    def test_default_index_path_format(self):
        path = default_index_path(model_id=1)
        assert isinstance(path, Path)
        assert path.name == "model-1-numpy-cosine.npz"
        assert "indexes" in str(path)
        assert path.suffix == ".npz"

    def test_default_index_path_custom_metric(self):
        path = default_index_path(model_id=5, metric="cosine")
        assert path.name == "model-5-numpy-cosine.npz"
