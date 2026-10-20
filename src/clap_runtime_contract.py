"""Resolve the optional CLAP package-version contract without optional imports.

The source checkout owns exact CLAP package pins in ``pyproject.toml``.  A
normal installed distribution resolves the same values from its wheel metadata.
This module intentionally uses only the Python standard library so importing
model-readiness metadata never imports torch or transformers.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
import re
import tomllib
from typing import Iterable


_PROJECT_DISTRIBUTION = "sample-brain"
_PACKAGE_NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")
_EXACT_PIN_RE = re.compile(
    r"^\s*([A-Za-z0-9_.-]+)\s*==\s*([A-Za-z0-9][A-Za-z0-9_.+!-]*)\s*$"
)


class ClapRuntimeContractError(RuntimeError):
    """Raised when the CLAP package identity cannot be resolved exactly."""


@dataclass(frozen=True)
class ClapRuntimePins:
    torch: str
    transformers: str


def _normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _exact_pin(requirements: Iterable[str], package: str) -> str:
    target = _normalize_package_name(package)
    versions: list[str] = []

    for raw_requirement in requirements:
        requirement = raw_requirement.split(";", 1)[0].strip()
        name_match = _PACKAGE_NAME_RE.match(requirement)
        if name_match is None or _normalize_package_name(name_match.group(1)) != target:
            continue

        exact_match = _EXACT_PIN_RE.fullmatch(requirement)
        if exact_match is None or _normalize_package_name(exact_match.group(1)) != target:
            raise ClapRuntimeContractError(
                f"CLAP dependency {package!r} must use an exact == pin"
            )
        versions.append(exact_match.group(2))

    if len(versions) != 1:
        raise ClapRuntimeContractError(
            f"expected exactly one CLAP dependency for {package!r}, found {len(versions)}"
        )
    return versions[0]


def _pins_from_requirements(requirements: Iterable[str]) -> ClapRuntimePins:
    requirements = tuple(requirements)
    return ClapRuntimePins(
        torch=_exact_pin(requirements, "torch"),
        transformers=_exact_pin(requirements, "transformers"),
    )


def load_clap_runtime_pins(*, project_root: Path) -> ClapRuntimePins:
    """Load exact CLAP pins from a source checkout's ``pyproject.toml``."""

    pyproject_path = Path(project_root) / "pyproject.toml"
    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        requirements = pyproject["project"]["optional-dependencies"]["clap"]
    except (OSError, KeyError, tomllib.TOMLDecodeError, TypeError) as exc:
        raise ClapRuntimeContractError(
            f"unable to read CLAP dependency contract from {pyproject_path}"
        ) from exc

    if not isinstance(requirements, list) or not all(
        isinstance(item, str) for item in requirements
    ):
        raise ClapRuntimeContractError("CLAP optional dependencies must be a string list")
    return _pins_from_requirements(requirements)


def _load_installed_clap_runtime_pins() -> ClapRuntimePins:
    try:
        requirements = metadata.requires(_PROJECT_DISTRIBUTION)
    except metadata.PackageNotFoundError as exc:
        raise ClapRuntimeContractError(
            "sample-brain package metadata is unavailable for CLAP runtime resolution"
        ) from exc

    if requirements is None:
        raise ClapRuntimeContractError(
            "sample-brain package metadata contains no dependency requirements"
        )
    return _pins_from_requirements(requirements)


def resolve_clap_runtime_pins() -> ClapRuntimePins:
    """Resolve CLAP pins from source manifest, then installed metadata.

    Source checkouts deliberately win so a Dependabot edit to ``pyproject.toml``
    is immediately authoritative during tests and development.  Wheels normally
    do not contain the repository manifest, so installed package metadata is the
    deterministic fallback.
    """

    project_root = Path(__file__).resolve().parents[1]
    if (project_root / "pyproject.toml").is_file():
        return load_clap_runtime_pins(project_root=project_root)
    return _load_installed_clap_runtime_pins()


__all__ = [
    "ClapRuntimeContractError",
    "ClapRuntimePins",
    "load_clap_runtime_pins",
    "resolve_clap_runtime_pins",
]
