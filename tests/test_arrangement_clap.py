from __future__ import annotations

import numpy as np

from src.arrangement_clap import ROLE_PROMPTS, evaluate_clap_arrangement_signal
from src.embed import (
    EmbeddingBackend,
    EmbeddingBackendUnavailableError,
    EmbeddingModelInfo,
)


class FakeClapBackend(EmbeddingBackend):
    def __init__(self) -> None:
        self.text_vectors = {
            prompt: np.array([1.0, 0.0], dtype=np.float32)
            for prompt in ROLE_PROMPTS.values()
        }
        self.text_vectors[ROLE_PROMPTS["drop"]] = np.array(
            [0.95, 0.05], dtype=np.float32
        )
        self.text_vectors[ROLE_PROMPTS["groove"]] = np.array(
            [0.70, 0.30], dtype=np.float32
        )
        self.text_vectors[ROLE_PROMPTS["intro"]] = np.array(
            [0.0, 1.0], dtype=np.float32
        )
        self.text_vectors[ROLE_PROMPTS["build"]] = np.array(
            [0.2, 0.8], dtype=np.float32
        )
        self.text_vectors[ROLE_PROMPTS["breakdown"]] = np.array(
            [0.1, 0.9], dtype=np.float32
        )
        self.text_vectors[ROLE_PROMPTS["outro"]] = np.array(
            [0.05, 0.95], dtype=np.float32
        )

    def embed_audio(self, audio_path: str) -> np.ndarray:
        assert audio_path == "private-section.wav"
        return np.array([1.0, 0.0], dtype=np.float32)

    def embed_text(self, text: str) -> np.ndarray:
        return self.text_vectors[text]

    def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            provider="fake",
            model_name="fake-clap",
            model_version="test",
            embedding_dim=2,
            modality="audio_text",
        )


class MissingClapBackend(EmbeddingBackend):
    def embed_audio(self, audio_path: str) -> np.ndarray:
        raise EmbeddingBackendUnavailableError("CLAP is not installed")

    def embed_text(self, text: str) -> np.ndarray:
        raise AssertionError("text embedding must not run after backend failure")

    def model_info(self) -> EmbeddingModelInfo:
        raise AssertionError("model_info must not run after backend failure")


def test_clap_signal_reports_semantic_ranking_without_overriding_heuristic() -> None:
    signal = evaluate_clap_arrangement_signal(
        "private-section.wav", "groove", FakeClapBackend()
    )

    assert signal.status == "available"
    assert signal.heuristic_role == "groove"
    assert signal.effective_role == "groove"
    assert signal.top_role == "drop"
    assert signal.top_margin is not None and signal.top_margin > 0
    assert signal.ranked_roles[0].similarity >= signal.ranked_roles[1].similarity
    assert signal.provenance["decision_policy"] == (
        "observe_only_heuristic_remains_authoritative"
    )
    assert "private-section.wav" not in repr(signal)


def test_unknown_heuristic_is_not_replaced_by_clap_top_role() -> None:
    signal = evaluate_clap_arrangement_signal(
        "private-section.wav", "unknown", FakeClapBackend()
    )

    assert signal.status == "available"
    assert signal.top_role == "drop"
    assert signal.heuristic_role == "unknown"
    assert signal.effective_role == "unknown"


def test_missing_clap_falls_back_to_heuristic_without_fake_label() -> None:
    signal = evaluate_clap_arrangement_signal(
        "private-section.wav", "breakdown", MissingClapBackend()
    )

    assert signal.status == "unavailable"
    assert signal.ranked_roles == ()
    assert signal.top_role is None
    assert signal.effective_role == "breakdown"
    assert signal.limitation == "CLAP is not installed"


def test_zero_or_invalid_embedding_is_rejected() -> None:
    backend = FakeClapBackend()
    backend.text_vectors[ROLE_PROMPTS["drop"]] = np.zeros(2, dtype=np.float32)

    try:
        evaluate_clap_arrangement_signal("private-section.wav", "groove", backend)
    except ValueError as exc:
        assert "finite non-zero norm" in str(exc)
    else:
        raise AssertionError("expected invalid CLAP embedding to fail")
