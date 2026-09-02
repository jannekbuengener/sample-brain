"""Optional model/runtime readiness metadata for Sample Brain.

This module is intentionally stdlib-only. Importing it must never import torch,
transformers, audio-separator, model weights, or any model cache.
"""

from __future__ import annotations

from dataclasses import dataclass

CLAP_TORCH_VERSION = "2.13.0"
CLAP_TRANSFORMERS_VERSION = "5.16.1"
CLAP_MODEL_NAME = "laion/clap-htsat-unfused"
# Official model-repository commit adding a safetensors variant on top of the
# prior main snapshot. Runtime loading also enforces use_safetensors=True.
CLAP_MODEL_REVISION = "79b58ed25fc00386262a2bea4b19fd21dc4310a0"
CLAP_MODEL_LICENSE = "Apache-2.0"

WEIGHT_LICENSE_UNKNOWN_UNVERIFIED = "UNKNOWN_UNVERIFIED"


@dataclass(frozen=True)
class ModelReadiness:
    model_id: str
    technical_status: str
    code_license: str
    weight_license: str
    commercial_ready: bool
    selection_status: str
    evidence_source: str


_MODEL_READINESS = {
    CLAP_MODEL_NAME: ModelReadiness(
        model_id=CLAP_MODEL_NAME,
        technical_status="OPTIONAL_SUPPORTED",
        code_license="Transformers/PyTorch package licenses are tracked separately",
        weight_license=CLAP_MODEL_LICENSE,
        commercial_ready=True,
        selection_status="OPTIONAL_EXPERIMENTAL",
        evidence_source=(
            "Hugging Face model repository safetensors revision " + CLAP_MODEL_REVISION
        ),
    ),
    "htdemucs": ModelReadiness(
        model_id="htdemucs",
        technical_status="OPTIONAL_EXPERIMENTAL",
        code_license="MIT",
        weight_license=WEIGHT_LICENSE_UNKNOWN_UNVERIFIED,
        commercial_ready=False,
        selection_status="NOT_APPROVED_AS_COMMERCIAL_DEFAULT",
        evidence_source="exact pretrained-weight commercial grant not verified",
    ),
    "htdemucs_ft": ModelReadiness(
        model_id="htdemucs_ft",
        technical_status="OPTIONAL_EXPERIMENTAL",
        code_license="MIT",
        weight_license=WEIGHT_LICENSE_UNKNOWN_UNVERIFIED,
        commercial_ready=False,
        selection_status="NOT_APPROVED_AS_COMMERCIAL_DEFAULT",
        evidence_source="exact pretrained-weight commercial grant not verified",
    ),
}


def get_model_readiness(model_id: str) -> ModelReadiness:
    """Return the explicit readiness record for a known optional model."""
    try:
        return _MODEL_READINESS[model_id]
    except KeyError as exc:
        raise KeyError(f"unknown model readiness id: {model_id}") from exc


__all__ = [
    "CLAP_TORCH_VERSION",
    "CLAP_TRANSFORMERS_VERSION",
    "CLAP_MODEL_NAME",
    "CLAP_MODEL_REVISION",
    "CLAP_MODEL_LICENSE",
    "WEIGHT_LICENSE_UNKNOWN_UNVERIFIED",
    "ModelReadiness",
    "get_model_readiness",
]
