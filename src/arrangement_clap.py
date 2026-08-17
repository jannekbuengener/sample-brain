"""Optional CLAP semantic evidence for arrangement-role evaluation (Issue #243).

This module deliberately does not replace the deterministic arrangement classifier.
It compares one rendered/local section against a small set of semantic role prompts
and reports the CLAP ranking alongside the heuristic role.  The heuristic role
remains the effective role until pilot evidence justifies a future policy change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from .arrangement_classifier import SectionRole
from .embed import EmbeddingBackend, EmbeddingBackendUnavailableError

CLAP_ARRANGEMENT_COMPONENT = "arrangement_clap_signal"

ROLE_PROMPTS: Mapping[SectionRole, str] = {
    "intro": "techno track intro, restrained opening, sparse low energy arrangement",
    "groove": "steady techno groove, repeating rhythmic body, stable dancefloor pattern",
    "build": "techno build-up, rising tension, increasing energy before a change",
    "drop": "techno drop, high-energy main section, strong kick and low-end impact",
    "breakdown": "techno breakdown, reduced drums and low-end, spacious lower-energy section",
    "outro": "techno outro, ending section, energy reducing toward the finish",
    "unknown": "unclear ambiguous techno arrangement section",
}


@dataclass(frozen=True)
class ClapRoleScore:
    role: SectionRole
    similarity: float


@dataclass(frozen=True)
class ClapArrangementSignal:
    """Side-by-side semantic evidence; never authoritative for v1 roles."""

    status: str
    heuristic_role: SectionRole
    effective_role: SectionRole
    ranked_roles: tuple[ClapRoleScore, ...] = ()
    top_role: SectionRole | None = None
    top_margin: float | None = None
    provenance: Mapping[str, object] | None = None
    limitation: str | None = None


def _unit_vector(vector: np.ndarray) -> np.ndarray:
    arr = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if not np.isfinite(norm) or norm <= 0.0:
        raise ValueError("CLAP embedding must have a finite non-zero norm")
    return arr / norm


def evaluate_clap_arrangement_signal(
    section_audio_path: str,
    heuristic_role: SectionRole,
    backend: EmbeddingBackend,
) -> ClapArrangementSignal:
    """Compare a local section with role prompts using the existing CLAP backend.

    ``section_audio_path`` is consumed only by the supplied embedding backend.  No
    path is copied into the result/provenance so private local paths do not leak
    into reports or GitHub evidence.
    """

    if not section_audio_path:
        raise ValueError("section_audio_path must be non-empty")

    try:
        audio_vector = _unit_vector(backend.embed_audio(section_audio_path))
        scores: list[ClapRoleScore] = []
        for role, prompt in ROLE_PROMPTS.items():
            if role == "unknown":
                continue
            text_vector = _unit_vector(backend.embed_text(prompt))
            if audio_vector.shape != text_vector.shape:
                raise ValueError(
                    "CLAP audio/text embedding dimensions must match: "
                    f"{audio_vector.shape} != {text_vector.shape}"
                )
            scores.append(
                ClapRoleScore(role=role, similarity=float(np.dot(audio_vector, text_vector)))
            )
    except (EmbeddingBackendUnavailableError, NotImplementedError) as exc:
        return ClapArrangementSignal(
            status="unavailable",
            heuristic_role=heuristic_role,
            effective_role=heuristic_role,
            provenance={
                "component": CLAP_ARRANGEMENT_COMPONENT,
                "method": "optional_clap_audio_text_similarity_v1",
            },
            limitation=str(exc),
        )

    ranked = tuple(sorted(scores, key=lambda item: (-item.similarity, item.role)))
    if not ranked:
        return ClapArrangementSignal(
            status="unavailable",
            heuristic_role=heuristic_role,
            effective_role=heuristic_role,
            provenance={
                "component": CLAP_ARRANGEMENT_COMPONENT,
                "method": "optional_clap_audio_text_similarity_v1",
            },
            limitation="no CLAP role scores produced",
        )

    margin = ranked[0].similarity - ranked[1].similarity if len(ranked) > 1 else None
    model_info = backend.model_info()
    return ClapArrangementSignal(
        status="available",
        heuristic_role=heuristic_role,
        effective_role=heuristic_role,
        ranked_roles=ranked,
        top_role=ranked[0].role,
        top_margin=margin,
        provenance={
            "component": CLAP_ARRANGEMENT_COMPONENT,
            "method": "optional_clap_audio_text_similarity_v1",
            "provider": model_info.provider,
            "model_name": model_info.model_name,
            "model_version": model_info.model_version,
            "decision_policy": "observe_only_heuristic_remains_authoritative",
        },
        limitation=(
            "CLAP ranking is evaluation evidence only; it does not override the "
            "heuristic arrangement role in Issue #243."
        ),
    )


__all__ = [
    "CLAP_ARRANGEMENT_COMPONENT",
    "ROLE_PROMPTS",
    "ClapArrangementSignal",
    "ClapRoleScore",
    "evaluate_clap_arrangement_signal",
]
