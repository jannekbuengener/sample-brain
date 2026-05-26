from __future__ import annotations

import numpy as np
import pytest

from src.embed import ClapEmbeddingBackend, EmbeddingBackendUnavailableError


class TestClapModelInfo:
    def test_model_info_does_not_load_model(self):
        backend = ClapEmbeddingBackend()
        info = backend.model_info()
        assert info.embedding_dim == 512
        assert info.modality == "audio_text"
        assert info.provider == "laion"
        assert info.model_name == "laion/clap-htsat-unfused"
        assert backend._model is None
        assert backend._processor is None


class TestClapMissingDeps:
    def test_embed_text_raises_unavailable_when_deps_missing(self, monkeypatch):
        def failing_load():
            raise EmbeddingBackendUnavailableError(
                "CLAP dependencies not available. "
                "Install with: pip install -e .[clap]"
            )

        backend = ClapEmbeddingBackend()
        monkeypatch.setattr(backend, "_load_model", failing_load)

        with pytest.raises(EmbeddingBackendUnavailableError) as exc:
            backend.embed_text("test")
        assert "[clap]" in str(exc.value)

    def test_embed_audio_raises_unavailable_when_deps_missing(self, monkeypatch):
        def failing_load():
            raise EmbeddingBackendUnavailableError(
                "CLAP dependencies not available. "
                "Install with: pip install -e .[clap]"
            )

        backend = ClapEmbeddingBackend()
        monkeypatch.setattr(backend, "_load_model", failing_load)

        with pytest.raises(EmbeddingBackendUnavailableError) as exc:
            backend.embed_audio("fake.wav")
        assert "[clap]" in str(exc.value)


class TestClapEmbedText:
    def test_raises_on_empty_text(self):
        backend = ClapEmbeddingBackend()
        with pytest.raises(ValueError, match="non-empty string"):
            backend.embed_text("")
