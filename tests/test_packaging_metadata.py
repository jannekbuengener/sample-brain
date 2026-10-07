from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIRECT_CORE_DEPENDENCIES = {
    "librosa",
    "numpy",
    "pyyaml",
    "scipy",
    "soundfile",
    "sqlalchemy",
    "tqdm",
}
OPTIONAL_ONLY_DEPENDENCIES = {
    "audio-separator",
    "beat-this",
    "sqlite-vec",
    "torch",
    "transformers",
}


def _requirement_name(requirement: str) -> str:
    match = re.match(r"^([A-Za-z0-9_.-]+)", requirement.strip())
    assert match is not None, requirement
    return match.group(1).lower().replace("_", "-")


def test_project_metadata_declares_all_direct_core_runtime_dependencies() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]
    names = {_requirement_name(item) for item in dependencies}

    assert DIRECT_CORE_DEPENDENCIES <= names
    assert names.isdisjoint(OPTIONAL_ONLY_DEPENDENCIES)


def test_setuptools_includes_src_subpackages() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    find = data["tool"]["setuptools"]["packages"]["find"]
    assert find["where"] == ["."]
    assert "src" in find["include"]
    assert "src.*" in find["include"]
    # Documented AQ1 proof provider must ship with the installed distribution.
    assert (ROOT / "src" / "aq_candidate_search_spaces" / "aq1_tempo.py").is_file()
    assert (ROOT / "src" / "aq_headless_adapters" / "__init__.py").is_file()
    assert (ROOT / "src" / "measurement" / "__init__.py").is_file()


def test_requirements_file_remains_repeatable_environment_input() -> None:
    lines = [
        line.strip()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    names = {_requirement_name(item) for item in lines}

    assert DIRECT_CORE_DEPENDENCIES <= names
    assert all("==" in item for item in lines)
