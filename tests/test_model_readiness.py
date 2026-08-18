from __future__ import annotations

import sys
import tomllib
import types
from pathlib import Path

import numpy as np

from src.model_readiness import (
    CLAP_MODEL_REVISION,
    CLAP_TORCH_VERSION,
    CLAP_TRANSFORMERS_VERSION,
    WEIGHT_LICENSE_UNKNOWN_UNVERIFIED,
    get_model_readiness,
)
from src.stem_cache import (
    LEGACY_DEMUCS_V1_FINGERPRINT_LICENSE_TOKEN,
    StemModelIdentity,
    build_separation_fingerprint,
    known_htdemucs_ft_identity,
    known_htdemucs_identity,
)

ROOT = Path(__file__).resolve().parents[1]
SAFE_CLAP_REVISION = "79b58ed25fc00386262a2bea4b19fd21dc4310a0"


def test_clap_install_surfaces_pin_the_same_exact_matrix() -> None:
    requirements = [
        line.strip()
        for line in (ROOT / "requirements-clap.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extra = pyproject["project"]["optional-dependencies"]["clap"]

    expected = [
        f"torch=={CLAP_TORCH_VERSION}",
        f"transformers=={CLAP_TRANSFORMERS_VERSION}",
    ]
    assert requirements == expected
    assert extra == expected


def test_model_readiness_separates_technical_and_commercial_state() -> None:
    clap = get_model_readiness("laion/clap-htsat-unfused")
    assert clap.technical_status == "OPTIONAL_SUPPORTED"
    assert clap.weight_license == "Apache-2.0"
    assert clap.commercial_ready is True
    assert clap.selection_status == "OPTIONAL_EXPERIMENTAL"

    for model_name in ("htdemucs", "htdemucs_ft"):
        model = get_model_readiness(model_name)
        assert model.technical_status == "OPTIONAL_EXPERIMENTAL"
        assert model.weight_license == WEIGHT_LICENSE_UNKNOWN_UNVERIFIED
        assert model.commercial_ready is False
        assert model.selection_status == "NOT_APPROVED_AS_COMMERCIAL_DEFAULT"


def test_known_demucs_provenance_is_neutral_but_v1_fingerprint_is_compatible() -> None:
    weight_hash = {"algorithm": "sha256", "value": "abc123"}
    current = known_htdemucs_identity(weight_hash=weight_hash)
    assert current.weight_license == WEIGHT_LICENSE_UNKNOWN_UNVERIFIED
    assert current.to_provenance()["weight_license"] == WEIGHT_LICENSE_UNKNOWN_UNVERIFIED

    legacy = StemModelIdentity(
        family=current.family,
        name=current.name,
        checkpoint=current.checkpoint,
        weight_hash=weight_hash,
        code_license=current.code_license,
        weight_license=LEGACY_DEMUCS_V1_FINGERPRINT_LICENSE_TOKEN,
    )
    kwargs = {
        "backend_name": "python-audio-separator",
        "backend_version": "0.44.5",
        "configuration": {"overlap": 0.25},
    }
    assert build_separation_fingerprint(model_identity=current, **kwargs) == build_separation_fingerprint(
        model_identity=legacy, **kwargs
    )

    ft = known_htdemucs_ft_identity(weight_hash={"algorithm": "sha256-set-v1", "value": "def456"})
    assert ft.weight_license == WEIGHT_LICENSE_UNKNOWN_UNVERIFIED


def test_clap_metadata_uses_immutable_safetensors_model_revision() -> None:
    from src.embed import ClapEmbeddingBackend

    info = ClapEmbeddingBackend().model_info()
    assert CLAP_MODEL_REVISION == SAFE_CLAP_REVISION
    assert info.model_version == CLAP_MODEL_REVISION


def test_clap_loader_pins_revision_and_requires_safetensors(monkeypatch) -> None:
    import src.embed as embed

    captured: list[tuple[str, str, dict]] = []

    class FakeModel:
        def to(self, device):
            return self

        def eval(self):
            return self

    class FakeProcessor:
        pass

    def model_from_pretrained(name, **kwargs):
        captured.append(("model", name, dict(kwargs)))
        return FakeModel()

    def processor_from_pretrained(name, **kwargs):
        captured.append(("processor", name, dict(kwargs)))
        return FakeProcessor()

    fake_torch = types.ModuleType("torch")
    fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.ClapModel = types.SimpleNamespace(from_pretrained=model_from_pretrained)
    fake_transformers.ClapProcessor = types.SimpleNamespace(from_pretrained=processor_from_pretrained)

    monkeypatch.setattr(embed, "_clap_available", lambda: True)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    backend = embed.ClapEmbeddingBackend()
    backend._load_model()

    assert len(captured) == 2
    assert all(name == "laion/clap-htsat-unfused" for _, name, _ in captured)
    assert all(kwargs["revision"] == CLAP_MODEL_REVISION for _, _, kwargs in captured)

    model_kwargs = next(kwargs for kind, _, kwargs in captured if kind == "model")
    processor_kwargs = next(kwargs for kind, _, kwargs in captured if kind == "processor")
    assert model_kwargs["use_safetensors"] is True
    assert "use_safetensors" not in processor_kwargs


class _FakeTensor:
    def __init__(self, values):
        self._values = np.asarray(values, dtype=np.float32)

    def cpu(self):
        return self

    def numpy(self):
        return self._values


def test_clap_feature_output_normalization_accepts_supported_api_shapes() -> None:
    from src.embed import _clap_feature_vector

    direct = _clap_feature_vector(_FakeTensor([[1.0, 2.0, 3.0]]))
    pooled = _clap_feature_vector(
        types.SimpleNamespace(pooler_output=_FakeTensor([[4.0, 5.0, 6.0]]))
    )
    tuple_output = _clap_feature_vector((_FakeTensor([[7.0, 8.0, 9.0]]),))

    assert direct.dtype == np.float32
    assert direct.tolist() == [1.0, 2.0, 3.0]
    assert pooled.tolist() == [4.0, 5.0, 6.0]
    assert tuple_output.tolist() == [7.0, 8.0, 9.0]
