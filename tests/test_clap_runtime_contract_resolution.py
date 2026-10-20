from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_contract_api():
    try:
        from src.clap_runtime_contract import ClapRuntimeContractError, load_clap_runtime_pins
    except ModuleNotFoundError:
        pytest.fail("CLAP runtime contract resolver is not implemented")
    return ClapRuntimeContractError, load_clap_runtime_pins


def _write_pyproject(root: Path, *, torch: str, transformers: str) -> None:
    (root / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "sample-brain"',
                'version = "0.1.0"',
                "",
                "[project.optional-dependencies]",
                "clap = [",
                f'    "torch=={torch}",',
                f'    "transformers=={transformers}",',
                "]",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_clap_runtime_pins_follow_future_manifest_versions(tmp_path: Path) -> None:
    _, load_clap_runtime_pins = _load_contract_api()
    _write_pyproject(tmp_path, torch="2.14.0", transformers="9.8.7")

    pins = load_clap_runtime_pins(project_root=tmp_path)

    assert pins.torch == "2.14.0"
    assert pins.transformers == "9.8.7"


def test_clap_runtime_pins_reject_non_exact_dependency_specs(tmp_path: Path) -> None:
    ContractError, load_clap_runtime_pins = _load_contract_api()
    _write_pyproject(tmp_path, torch="2.14.0", transformers=">=9.8,<10")

    with pytest.raises(ContractError, match="exact == pin"):
        load_clap_runtime_pins(project_root=tmp_path)


@pytest.mark.parametrize(
    "relative_path",
    [
        "docs/MODEL_READINESS_V1.md",
        "docs/benchmarks/CLAP_TIER_B_RUNTIME.md",
    ],
)
def test_clap_runtime_docs_reference_manifests_without_copying_transformers_pin(
    relative_path: str,
) -> None:
    text = (ROOT / relative_path).read_text(encoding="utf-8")

    assert "requirements-clap.txt" in text
    assert "pyproject.toml" in text
    assert re.search(r"(?m)^\| Transformers \| `\d", text) is None
