"""Hidden hierarchical performance elements for issue #375.

The normal live-performance layout stays intentionally simple. This module adds
an optional internal detail layer that can be revealed explicitly for a parent
performance group (for example ``drums`` -> kick/snare/hats/percussion).

No separation is invented here. Callers must provide source-backed element
candidates from a real separator or another truthful producer. Candidates
without positive evidence are represented as ``no_result`` and are never mixed
into rebuilt parent audio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

import numpy as np

from .live_profile import LiveLayout

ELEMENT_LAYER_DOCUMENT_TYPE = "sample_brain.performance_element_layer"
ELEMENT_LAYER_SCHEMA_VERSION = "1.0.0"

STATUS_OK = "ok"
STATUS_NO_RESULT = "no_result"
REASON_EVIDENCE_UNSUPPORTED = "SEPARATION_EVIDENCE_UNSUPPORTED"
REASON_MISSING_AUDIO = "MISSING_ELEMENT_AUDIO"

DEFAULT_DRUM_ELEMENTS = (
    "kick",
    "snare_clap",
    "hi_hats",
    "percussion",
    "cymbals_tops",
    "other_drums",
)


@dataclass(frozen=True)
class ElementCandidate:
    """One source-backed lower-level separation candidate.

    ``evidence_supported`` is deliberately explicit. A non-empty audio array is
    not enough to claim a clean element; callers must positively attest that the
    upstream separation result supports exposing it.
    """

    audio: Optional[np.ndarray]
    source_kind: str
    source_ref: str
    evidence_supported: bool
    technical_stems: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    reason_code: Optional[str] = None


@dataclass
class PerformanceSubElement:
    element: str
    parent_group: str
    status: str
    source_kind: Optional[str]
    source_ref: Optional[str]
    technical_stems: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    reason_code: Optional[str] = None
    audio: Optional[np.ndarray] = field(default=None, repr=False)

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "element": self.element,
            "parent_group": self.parent_group,
            "status": self.status,
        }
        if self.source_kind is not None:
            payload["source_kind"] = self.source_kind
            payload["source_ref"] = self.source_ref
            payload["technical_stems"] = list(self.technical_stems)
            payload["provenance"] = list(self.provenance)
        if self.status == STATUS_NO_RESULT:
            payload["reason_code"] = self.reason_code
        return payload


@dataclass
class PerformanceElementLayer:
    """Optional lower-level elements for exactly one top-level group."""

    parent_group: str
    elements: list[PerformanceSubElement]
    hidden_by_default: bool = True

    @property
    def available_elements(self) -> list[PerformanceSubElement]:
        return [e for e in self.elements if e.status == STATUS_OK]

    def summary_dict(self) -> dict[str, object]:
        """Metadata safe to show in the normal compact top-level view."""
        return {
            "parent_group": self.parent_group,
            "hidden_by_default": self.hidden_by_default,
            "available_count": len(self.available_elements),
            "has_detail": bool(self.available_elements),
        }

    def reveal_dict(self) -> dict[str, object]:
        """Return details only after an explicit reveal action."""
        return {
            "document_type": ELEMENT_LAYER_DOCUMENT_TYPE,
            "schema_version": ELEMENT_LAYER_SCHEMA_VERSION,
            **self.summary_dict(),
            "elements": [e.as_dict() for e in self.elements],
        }

    def rebuild_parent_audio(self, enabled: Optional[Sequence[str]] = None) -> Optional[np.ndarray]:
        """Rebuild the parent group from evidenced child elements.

        Only ``ok`` elements participate. All included arrays must share one
        sample length; mismatch fails closed rather than silently truncating or
        padding. ``None`` means there is no evidenced material to rebuild.
        """
        allowed = set(enabled) if enabled is not None else None
        selected = [
            e
            for e in self.available_elements
            if allowed is None or e.element in allowed
        ]
        if not selected:
            return None

        arrays = [np.asarray(e.audio, dtype=np.float32) for e in selected if e.audio is not None]
        if len(arrays) != len(selected):
            raise ValueError("ok element is missing audio")
        lengths = {a.shape[0] for a in arrays}
        if len(lengths) != 1:
            raise ValueError("hierarchical element audio lengths do not match")
        if any(a.ndim != 1 for a in arrays):
            raise ValueError("hierarchical element audio must be mono 1-D")

        mixed = np.sum(np.stack(arrays, axis=0), axis=0, dtype=np.float32)
        return np.asarray(mixed, dtype=np.float32)


@dataclass
class HierarchicalLiveLayout:
    """Wrap a compact ``LiveLayout`` with hidden optional detail layers."""

    top_level: LiveLayout
    detail_layers: dict[str, PerformanceElementLayer] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        """Preserve the simple default layout and expose only detail metadata."""
        payload = self.top_level.as_dict()
        payload["detail_layers"] = [
            layer.summary_dict()
            for _, layer in sorted(self.detail_layers.items())
        ]
        return payload

    def reveal_group(self, parent_group: str) -> Optional[dict[str, object]]:
        layer = self.detail_layers.get(parent_group)
        if layer is None or not layer.available_elements:
            return None
        return layer.reveal_dict()

    def rebuild_group_audio(
        self, parent_group: str, enabled: Optional[Sequence[str]] = None
    ) -> Optional[np.ndarray]:
        layer = self.detail_layers.get(parent_group)
        if layer is None:
            return None
        return layer.rebuild_parent_audio(enabled=enabled)


def build_performance_element_layer(
    parent_group: str,
    candidates: Mapping[str, ElementCandidate],
    *,
    expected_elements: Optional[Sequence[str]] = None,
) -> PerformanceElementLayer:
    """Build one fail-closed hidden detail layer from explicit evidence.

    Missing expected elements and unsupported candidates become ``no_result``.
    Unexpected candidates are ignored when ``expected_elements`` is supplied so
    the exposed vocabulary stays deterministic.
    """
    if not parent_group or not parent_group.strip():
        raise ValueError("parent_group must be non-empty")

    vocabulary = tuple(expected_elements) if expected_elements is not None else tuple(candidates)
    elements: list[PerformanceSubElement] = []
    for element in vocabulary:
        candidate = candidates.get(element)
        if candidate is None:
            elements.append(
                PerformanceSubElement(
                    element=element,
                    parent_group=parent_group,
                    status=STATUS_NO_RESULT,
                    source_kind=None,
                    source_ref=None,
                    reason_code=REASON_MISSING_AUDIO,
                )
            )
            continue

        audio = None if candidate.audio is None else np.asarray(candidate.audio, dtype=np.float32)
        has_audio = audio is not None and audio.ndim == 1 and audio.size > 0
        has_provenance = bool(candidate.source_kind.strip() and candidate.source_ref.strip())
        if not candidate.evidence_supported or not has_provenance:
            elements.append(
                PerformanceSubElement(
                    element=element,
                    parent_group=parent_group,
                    status=STATUS_NO_RESULT,
                    source_kind=None,
                    source_ref=None,
                    reason_code=candidate.reason_code or REASON_EVIDENCE_UNSUPPORTED,
                )
            )
            continue
        if not has_audio:
            elements.append(
                PerformanceSubElement(
                    element=element,
                    parent_group=parent_group,
                    status=STATUS_NO_RESULT,
                    source_kind=candidate.source_kind,
                    source_ref=candidate.source_ref,
                    technical_stems=candidate.technical_stems,
                    provenance=candidate.provenance,
                    reason_code=candidate.reason_code or REASON_MISSING_AUDIO,
                )
            )
            continue

        elements.append(
            PerformanceSubElement(
                element=element,
                parent_group=parent_group,
                status=STATUS_OK,
                source_kind=candidate.source_kind,
                source_ref=candidate.source_ref,
                technical_stems=candidate.technical_stems,
                provenance=candidate.provenance,
                audio=audio,
            )
        )

    return PerformanceElementLayer(parent_group=parent_group, elements=elements)


def build_drums_element_layer(
    candidates: Mapping[str, ElementCandidate],
) -> PerformanceElementLayer:
    """Build the deterministic first hierarchy under the ``drums`` group."""
    return build_performance_element_layer(
        "drums", candidates, expected_elements=DEFAULT_DRUM_ELEMENTS
    )


__all__ = [
    "ELEMENT_LAYER_DOCUMENT_TYPE",
    "ELEMENT_LAYER_SCHEMA_VERSION",
    "STATUS_OK",
    "STATUS_NO_RESULT",
    "REASON_EVIDENCE_UNSUPPORTED",
    "REASON_MISSING_AUDIO",
    "DEFAULT_DRUM_ELEMENTS",
    "ElementCandidate",
    "PerformanceSubElement",
    "PerformanceElementLayer",
    "HierarchicalLiveLayout",
    "build_performance_element_layer",
    "build_drums_element_layer",
]
