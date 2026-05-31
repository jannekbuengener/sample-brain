from __future__ import annotations

import numpy as np
import pytest

from src.embed import ClapEmbeddingBackend, EmbeddingBackendUnavailableError
from src.hybrid_rank import HybridMetadata, HybridQuery
from src.index import VectorIndex
from src.search import run_search
from tests.audio_fixtures import write_sine_wav


def _simulate_clap_deps_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force CLAP load failure so tests stay valid when torch/transformers are installed."""

    def failing_load(self: ClapEmbeddingBackend) -> None:
        raise EmbeddingBackendUnavailableError(
            "CLAP dependencies not available. "
            "Install with: pip install -e .[clap]"
        )

    monkeypatch.setattr(ClapEmbeddingBackend, "_load_model", failing_load)


@pytest.fixture(autouse=True)
def _clear_embed_backend_cache():
    import src.embed
    src.embed._backend = None
    yield


@pytest.fixture(autouse=True)
def _stub_search_output_lookups(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("src.search.load_sample_paths", lambda sample_ids: {})
    monkeypatch.setattr("src.search.load_hybrid_metadata", lambda sample_ids: {})


class TestRunSearchValidation:
    def test_requires_model_id(self, capsys):
        run_search(query="test", model_id=None)
        captured = capsys.readouterr()
        assert "search requires --model-id" in captured.out

    def test_requires_query_string(self, capsys):
        run_search(query=None, model_id=1)
        captured = capsys.readouterr()
        assert "search requires a text query or --query-audio" in captured.out

    def test_rejects_empty_query(self, capsys):
        run_search(query="", model_id=1)
        captured = capsys.readouterr()
        assert "search requires a text query or --query-audio" in captured.out

    def test_rejects_invalid_topk(self, capsys):
        run_search(query="test", model_id=1, topk=0)
        captured = capsys.readouterr()
        assert "search requires --topk > 0" in captured.out

        run_search(query="test", model_id=1, topk=-1)
        captured = capsys.readouterr()
        assert "search requires --topk > 0" in captured.out


class TestRunSearchUnavailableBackend:
    def test_noop_backend_prints_configure_message(self, capsys):
        run_search(query="kick", model_id=1, topk=5, backend_name="noop")
        captured = capsys.readouterr()
        assert "No embedding backend configured" in captured.out

    def test_clap_backend_prints_unavailable_message(self, capsys, monkeypatch):
        _simulate_clap_deps_unavailable(monkeypatch)
        run_search(query="kick", model_id=1, topk=5, backend_name="clap")
        captured = capsys.readouterr()
        assert "[ERROR] The selected embedding backend is not available." in captured.out
        assert "Install torch + transformers" in captured.out


class TestRunSearchAudioQuery:
    def test_rejects_both_text_and_audio(self, capsys):
        run_search(query="kick", query_audio="tone.wav", model_id=1)
        captured = capsys.readouterr()
        assert "either a text query or --query-audio, not both" in captured.out

    def test_missing_audio_file(self, capsys, tmp_path):
        missing = tmp_path / "missing.wav"
        run_search(query_audio=str(missing), model_id=1)
        captured = capsys.readouterr()
        assert "query audio file not found" in captured.out
        assert str(missing) in captured.out

    def test_audio_query_uses_embed_audio(self, capsys, monkeypatch, tmp_path):
        wav_path = write_sine_wav(
            tmp_path / "samples" / "tone.wav",
            duration_sec=0.2,
            frequency_hz=330.0,
        )
        fake_vector = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        called_with: str | None = None

        class FakeBackend:
            def embed_audio(self, path: str):
                nonlocal called_with
                called_with = path
                return fake_vector

        monkeypatch.setattr("src.search.get_backend", lambda name: FakeBackend())
        monkeypatch.setattr(
            "src.search.build_numpy_index",
            lambda model_id=None, limit=None: VectorIndex(
                vectors=np.array([[1.0, 0.0, 0.0]], dtype=np.float32),
                sample_ids=[99],
                model_id=1,
                embedding_dim=3,
            ),
        )

        run_search(query_audio=str(wav_path), model_id=1, topk=1)
        captured = capsys.readouterr()
        assert called_with == str(wav_path)
        assert "rank=1 sample_id=99" in captured.out

    def test_noop_backend_audio_query_prints_configure_message(self, capsys, tmp_path):
        wav_path = write_sine_wav(
            tmp_path / "samples" / "tone.wav",
            duration_sec=0.2,
            frequency_hz=440.0,
        )
        run_search(query_audio=str(wav_path), model_id=1, backend_name="noop")
        captured = capsys.readouterr()
        assert "No embedding backend configured" in captured.out

    def test_audio_query_loads_index_path_when_given(self, monkeypatch, tmp_path):
        wav_path = write_sine_wav(
            tmp_path / "samples" / "tone.wav",
            duration_sec=0.1,
            frequency_hz=220.0,
        )
        fake_vector = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        class FakeBackend:
            def embed_audio(self, path: str):
                return fake_vector

        monkeypatch.setattr("src.search.get_backend", lambda name: FakeBackend())

        load_called = False

        def fake_load(path, model_id=None):
            nonlocal load_called
            load_called = True
            assert "test.npz" in str(path)
            return VectorIndex(
                vectors=np.array([[1.0, 0.0, 0.0]], dtype=np.float32),
                sample_ids=[1],
                model_id=1,
                embedding_dim=3,
            )

        build_called = False

        def fake_build(model_id=None, limit=None):
            nonlocal build_called
            build_called = True
            return None

        monkeypatch.setattr("src.search.load_numpy_index", fake_load)
        monkeypatch.setattr("src.search.build_numpy_index", fake_build)

        run_search(query_audio=str(wav_path), model_id=1, index_path="test.npz")
        assert load_called
        assert not build_called


class TestRunSearchWithFakes:
    def test_full_search_flow_with_fake_backend_and_index(self, capsys, monkeypatch):
        fake_vector = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        class FakeBackend:
            def embed_text(self, text):
                return fake_vector

        monkeypatch.setattr("src.search.get_backend", lambda name: FakeBackend())

        fake_index = VectorIndex(
            vectors=np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32),
            sample_ids=[10, 20],
            model_id=1,
            embedding_dim=3,
        )
        monkeypatch.setattr(
            "src.search.build_numpy_index",
            lambda model_id=None, limit=None: fake_index,
        )

        run_search(query="test", model_id=1, topk=5)
        captured = capsys.readouterr()
        assert "rank=1" in captured.out
        assert "sample_id=10" in captured.out
        assert "score=" in captured.out

    def test_output_includes_enriched_metadata_fields(self, capsys, monkeypatch):
        fake_vector = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        class FakeBackend:
            def embed_text(self, text):
                return fake_vector

        monkeypatch.setattr("src.search.get_backend", lambda name: FakeBackend())
        monkeypatch.setattr("src.search.load_sample_paths", lambda sample_ids: {10: "/samples/kick.wav"})
        monkeypatch.setattr(
            "src.search.load_hybrid_metadata",
            lambda sample_ids: {
                10: HybridMetadata(
                    sample_id=10,
                    bpm=128.0,
                    key="Am",
                    pred_type="kick",
                    audio_class="percussive",
                )
            },
        )

        fake_index = VectorIndex(
            vectors=np.array([[1.0, 0.0, 0.0]], dtype=np.float32),
            sample_ids=[10],
            model_id=1,
            embedding_dim=3,
        )
        monkeypatch.setattr(
            "src.search.build_numpy_index",
            lambda model_id=None, limit=None: fake_index,
        )

        run_search(query="kick", model_id=1, topk=1)
        captured = capsys.readouterr()
        assert "path=/samples/kick.wav" in captured.out
        assert "bpm=128.0" in captured.out
        assert "key=Am" in captured.out
        assert "pred_type=kick" in captured.out
        assert "class=percussive" in captured.out

    def test_output_falls_back_when_metadata_missing(self, capsys, monkeypatch):
        fake_vector = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        class FakeBackend:
            def embed_text(self, text):
                return fake_vector

        monkeypatch.setattr("src.search.get_backend", lambda name: FakeBackend())
        monkeypatch.setattr("src.search.load_sample_paths", lambda sample_ids: {})
        monkeypatch.setattr("src.search.load_hybrid_metadata", lambda sample_ids: {})

        fake_index = VectorIndex(
            vectors=np.array([[1.0, 0.0, 0.0]], dtype=np.float32),
            sample_ids=[10],
            model_id=1,
            embedding_dim=3,
        )
        monkeypatch.setattr(
            "src.search.build_numpy_index",
            lambda model_id=None, limit=None: fake_index,
        )

        run_search(query="kick", model_id=1, topk=1)
        captured = capsys.readouterr()
        assert "rank=1 sample_id=10" in captured.out
        assert "path=" in captured.out
        assert "bpm=" in captured.out
        assert "key=" in captured.out
        assert "pred_type=" in captured.out
        assert "class=" in captured.out

    def test_loads_index_path_when_given(self, capsys, monkeypatch):
        fake_vector = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        class FakeBackend:
            def embed_text(self, text):
                return fake_vector

        monkeypatch.setattr("src.search.get_backend", lambda name: FakeBackend())

        load_called = False

        def fake_load(path, model_id=None):
            nonlocal load_called
            load_called = True
            assert "test.npz" in str(path)
            return VectorIndex(
                vectors=np.array([[1.0, 0.0, 0.0]], dtype=np.float32),
                sample_ids=[1],
                model_id=1,
                embedding_dim=3,
            )

        monkeypatch.setattr("src.search.load_numpy_index", fake_load)

        build_called = False

        def fake_build(model_id=None, limit=None):
            nonlocal build_called
            build_called = True
            return None

        monkeypatch.setattr("src.search.build_numpy_index", fake_build)

        run_search(query="test", model_id=1, index_path="test.npz")
        assert load_called, "load_numpy_index should be called when index_path is given"
        assert not build_called, "build_numpy_index should NOT be called when index_path is given"

    def test_dimension_mismatch_is_controlled(self, capsys, monkeypatch):
        fake_vector = np.array([1.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)

        class FakeBackend:
            def embed_text(self, text):
                return fake_vector

        monkeypatch.setattr("src.search.get_backend", lambda name: FakeBackend())

        fake_index = VectorIndex(
            vectors=np.array([[1.0, 0.0, 0.0]], dtype=np.float32),
            sample_ids=[1],
            model_id=1,
            embedding_dim=3,
        )
        monkeypatch.setattr(
            "src.search.build_numpy_index",
            lambda model_id=None, limit=None: fake_index,
        )

        run_search(query="test", model_id=1)
        captured = capsys.readouterr()
        assert "[ERROR] Search failed:" in captured.out


class TestRunSearchHybridRerank:
    def _fake_backend_and_index(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_vector = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        class FakeBackend:
            def embed_text(self, text):
                return fake_vector

        monkeypatch.setattr("src.search.get_backend", lambda name: FakeBackend())
        fake_index = VectorIndex(
            vectors=np.array([[1.0, 0.0, 0.0], [0.8, 0.6, 0.0]], dtype=np.float32),
            sample_ids=[10, 20],
            model_id=1,
            embedding_dim=3,
        )
        monkeypatch.setattr(
            "src.search.build_numpy_index",
            lambda model_id=None, limit=None: fake_index,
        )

    def test_semantic_only_preserves_order_with_metadata_output(self, capsys, monkeypatch):
        self._fake_backend_and_index(monkeypatch)
        load_called = False

        def fake_load(sample_ids):
            nonlocal load_called
            load_called = True
            return {}

        monkeypatch.setattr("src.search.load_hybrid_metadata", fake_load)

        run_search(query="test", model_id=1, topk=5, hybrid_query=None)
        captured = capsys.readouterr()

        assert load_called
        assert "rank=1" in captured.out
        assert "sample_id=10" in captured.out
        lines = [line for line in captured.out.splitlines() if line.startswith("rank=")]
        assert lines[0].startswith("rank=1 sample_id=10")
        assert lines[1].startswith("rank=2 sample_id=20")

    def test_hybrid_rerank_promotes_bpm_match(self, capsys, monkeypatch):
        self._fake_backend_and_index(monkeypatch)
        metadata = {
            10: HybridMetadata(sample_id=10, bpm=100.0),
            20: HybridMetadata(sample_id=20, bpm=128.0),
        }
        monkeypatch.setattr(
            "src.search.load_hybrid_metadata",
            lambda sample_ids: {sid: metadata[sid] for sid in sample_ids if sid in metadata},
        )

        hybrid_query = HybridQuery(target_bpm=128.0, bpm_weight=0.5)
        run_search(query="test", model_id=1, topk=5, hybrid_query=hybrid_query)
        captured = capsys.readouterr()

        assert "rank=1 sample_id=20" in captured.out
        assert "rank=2 sample_id=10" in captured.out

    def test_default_bpm_weight_applies_when_target_bpm_set(self, capsys, monkeypatch):
        self._fake_backend_and_index(monkeypatch)
        metadata = {
            10: HybridMetadata(sample_id=10, bpm=100.0),
            20: HybridMetadata(sample_id=20, bpm=128.0),
        }
        monkeypatch.setattr(
            "src.search.load_hybrid_metadata",
            lambda sample_ids: {sid: metadata[sid] for sid in sample_ids if sid in metadata},
        )

        hybrid_query = HybridQuery(target_bpm=128.0)
        run_search(query="test", model_id=1, topk=5, hybrid_query=hybrid_query)
        captured = capsys.readouterr()

        assert "rank=1 sample_id=20" in captured.out
