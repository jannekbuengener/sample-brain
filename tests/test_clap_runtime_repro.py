from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest

from src.benchmark_search_quality import (
    DEFAULT_SUITE_PATH,
    DEFAULT_TIER_B_SUITE_PATH,
    run_search_quality_benchmark,
)
from src.embed import (
    ClapEmbeddingBackend,
    EmbeddingBackendUnavailableError,
    _clap_available,
)


# ---------------------------------------------------------------------------
# Non-CLAP unit tests (no torch/transformers required)
# ---------------------------------------------------------------------------


def test_clap_marker_registered():
    assert hasattr(pytest.mark, "clap")


def test_clap_constants_agree_with_model_info():
    from src.embed import (
        CLAP_EMBEDDING_DIM,
        CLAP_MODEL_NAME,
        CLAP_MODALITY,
    )

    backend = ClapEmbeddingBackend()
    info = backend.model_info()
    assert info.model_name == CLAP_MODEL_NAME
    assert info.embedding_dim == CLAP_EMBEDDING_DIM
    assert info.modality == CLAP_MODALITY
    assert info.model_name == "laion/clap-htsat-unfused"
    assert info.embedding_dim == 512
    assert info.modality == "audio_text"


def test_no_download_on_import():
    backend = ClapEmbeddingBackend()
    assert backend._model is None
    assert backend._processor is None
    # model_info() must not trigger a model download / lazy load
    info = backend.model_info()
    assert info.embedding_dim == 512
    assert backend._model is None
    assert backend._processor is None


def test_missing_deps_unavailable(monkeypatch):
    monkeypatch.setattr("src.embed._clap_available", lambda: False)
    backend = ClapEmbeddingBackend()
    with pytest.raises(EmbeddingBackendUnavailableError) as exc:
        backend.embed_text("kick drum")
    assert "[clap]" in str(exc.value)


def test_non_clap_search_quality_suite_runs(tmp_path: Path):
    result = run_search_quality_benchmark(
        DEFAULT_SUITE_PATH,
        work_dir=tmp_path / "search-quality",
    )
    assert result.tier == "A"
    for row in result.query_results:
        assert row.error is None, row.query_id
    checks = result.threshold_pass()
    assert checks["mean_precision_at_1"]
    assert checks["mean_precision_at_5"]
    assert checks["mean_recall_at_10"]


# --- Fake transformers/torch injection for load-failure + cache_dir tests ---


class _FakeClapModel:
    def to(self, device):
        return self

    def eval(self):
        return self


class _FakeClapProcessor:
    pass


def _make_fake_torch() -> types.ModuleType:
    mod = types.ModuleType("torch")
    mod.cuda = types.SimpleNamespace(is_available=lambda: False)
    return mod


def _make_fake_transformers(
    *, load_error=None, captured=None
) -> types.ModuleType:
    mod = types.ModuleType("transformers")

    def _from_pretrained(name, **kwargs):
        if captured is not None:
            captured.append((name, dict(kwargs)))
        if load_error is not None:
            raise load_error
        return _FakeClapModel()

    mod.ClapModel = types.SimpleNamespace(from_pretrained=_from_pretrained)
    mod.ClapProcessor = types.SimpleNamespace(
        from_pretrained=lambda name, **kw: _FakeClapProcessor()
    )
    return mod


def _inject_fake_clap(monkeypatch, *, load_error=None, captured=None):
    monkeypatch.setattr("src.embed._clap_available", lambda: True)
    monkeypatch.setitem(sys.modules, "torch", _make_fake_torch())
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        _make_fake_transformers(load_error=load_error, captured=captured),
    )


def test_model_cache_dir_passed_to_loader(monkeypatch):
    captured = []
    _inject_fake_clap(monkeypatch, captured=captured)
    monkeypatch.setenv("SAMPLE_BRAIN_MODEL_CACHE_DIR", "/tmp/clap-model-cache")
    backend = ClapEmbeddingBackend()
    backend._load_model()
    assert backend._model is not None
    assert captured, "from_pretrained was not called"
    for name, kwargs in captured:
        assert kwargs.get("cache_dir") == "/tmp/clap-model-cache"


def test_model_cache_dir_absent_omitted(monkeypatch):
    captured = []
    _inject_fake_clap(monkeypatch, captured=captured)
    monkeypatch.delenv("SAMPLE_BRAIN_MODEL_CACHE_DIR", raising=False)
    backend = ClapEmbeddingBackend()
    backend._load_model()
    for name, kwargs in captured:
        assert "cache_dir" not in kwargs


def test_from_pretrained_failure_raises_unavailable(monkeypatch):
    load_error = OSError("Connection error: model laion/clap-htsat-unfused offline")
    _inject_fake_clap(monkeypatch, load_error=load_error)
    backend = ClapEmbeddingBackend()
    with pytest.raises(EmbeddingBackendUnavailableError) as exc:
        backend._load_model()
    assert "laion/clap-htsat-unfused" in str(exc.value)


def test_offline_model_missing_classification_deterministic(monkeypatch):
    # A simulated offline/missing-model load error must map to a clean,
    # deterministic runtime-unavailable classification (not a raw traceback).
    load_error = ConnectionError("HF hub unreachable (offline)")
    _inject_fake_clap(monkeypatch, load_error=load_error)
    backend = ClapEmbeddingBackend()
    with pytest.raises(EmbeddingBackendUnavailableError):
        backend._load_model()


# ---------------------------------------------------------------------------
# CLAP runtime tests (require [clap] extra + model; skip when unavailable)
# ---------------------------------------------------------------------------


@pytest.fixture
def clap_backend():
    if not _clap_available():
        pytest.skip("CLAP optional extra not installed")
    backend = ClapEmbeddingBackend()
    try:
        backend._load_model()
    except EmbeddingBackendUnavailableError as exc:
        pytest.skip(f"CLAP runtime unavailable: {exc}")
    return backend


@pytest.mark.clap
def test_clap_backend_loads_model(clap_backend):
    assert clap_backend._model is not None
    info = clap_backend.model_info()
    assert info.model_name == "laion/clap-htsat-unfused"
    assert info.embedding_dim == 512
    assert info.modality == "audio_text"


@pytest.mark.clap
def test_clap_text_embedding_512_finite(clap_backend):
    vec = clap_backend.embed_text("kick drum")
    assert vec.shape == (512,)
    assert vec.dtype == np.float32
    assert np.isfinite(vec).all()


@pytest.mark.clap
def test_clap_audio_embedding_512_finite(clap_backend, tmp_path: Path):
    from src.search_quality_fixtures import write_kick_transient_wav

    wav_path = write_kick_transient_wav(tmp_path / "kick.wav", bpm=120.0)
    vec = clap_backend.embed_audio(str(wav_path))
    assert vec.shape == (512,)
    assert vec.dtype == np.float32
    assert np.isfinite(vec).all()


@pytest.mark.clap
def test_clap_tier_b_harness_runs(tmp_path: Path):
    if not _clap_available():
        pytest.skip("CLAP optional extra not installed")
    try:
        result = run_search_quality_benchmark(
            DEFAULT_TIER_B_SUITE_PATH,
            work_dir=tmp_path / "clap-quality",
        )
    except EmbeddingBackendUnavailableError as exc:
        pytest.skip(f"CLAP runtime unavailable: {exc}")

    assert result.tier == "B"
    mode_keys = {row.group_key for row in result.mode_summaries}
    assert "text" in mode_keys
    assert "audio" in mode_keys
    for row in result.query_results:
        assert row.error is None, row.query_id
