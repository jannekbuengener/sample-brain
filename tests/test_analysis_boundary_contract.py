from __future__ import annotations

import ast
import importlib.util
import sys

import pytest

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_MODULES = (
    "src.attack_analysis",
    "src.aq3_onset_attack_baseline",
    "src.aq3_onset_attack_candidate_compare",
    "src.gesture_analysis",
)


def _module_source(module_name: str) -> Path | None:
    path = REPO_ROOT.joinpath(*module_name.split("."))
    for source in (path.with_suffix(".py"), path / "__init__.py"):
        if source.is_file():
            return source
    return None


def _static_imports(module_name: str) -> set[str]:
    source_path = _module_source(module_name)
    if source_path is None:
        raise FileNotFoundError(f"Missing analysis surface: {module_name}")
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    package = module_name if source_path.name == "__init__.py" else module_name.rpartition(".")[0]
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative = "." * node.level + (node.module or "")
                base = importlib.util.resolve_name(relative, package)
            else:
                base = node.module or ""
            if base:
                imports.add(base)
                imports.update(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")
    return imports


def _import_closure(module_name: str) -> set[str]:
    pending = [module_name]
    visited: set[str] = set()
    imports: set[str] = set()
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        direct = _static_imports(current)
        imports.update(direct)
        pending.extend(name for name in direct if name not in visited and _module_source(name) is not None)
    return imports


def _is_forbidden(module_name: str) -> bool:
    return (
        module_name.startswith("PySide6")
        or any(part == "qml" or part.startswith("qml_") for part in module_name.split("."))
        or module_name in {"src.workbench", "workbench"}
        or module_name.startswith("src.workbench_")
        or module_name.startswith("workbench_")
    )


def test_analysis_surfaces_do_not_import_workbench_or_pyside() -> None:
    violations = {
        module_name: sorted(
            imported for imported in _static_imports(module_name) if _is_forbidden(imported)
        )
        for module_name in ANALYSIS_MODULES
    }
    violations = {module: imported for module, imported in violations.items() if imported}

    assert violations == {}


def test_boundary_detects_workbench_imported_from_src_package(
    tmp_path: Path, monkeypatch
) -> None:
    source_path = tmp_path / "src" / "attack_analysis.py"
    source_path.parent.mkdir()
    source_path.write_text("from src import workbench_waveform\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)

    imports = _static_imports("src.attack_analysis")
    assert any(_is_forbidden(module) for module in imports)


def test_boundary_detects_workbench_root_imported_from_src_package(
    tmp_path: Path, monkeypatch
) -> None:
    source_path = tmp_path / "src" / "attack_analysis.py"
    source_path.parent.mkdir()
    source_path.write_text("from src import workbench\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)

    imports = _static_imports("src.attack_analysis")
    assert any(_is_forbidden(module) for module in imports)


AQ6_MODULES = (
    "src.harmony",
    *(f"src.{path.stem}" for path in sorted((REPO_ROOT / "src").glob("aq6_*.py"))),
    "src.aq_headless_adapters.aq6_harmonic_ranking_compare",
)


def test_aq6_and_harmony_import_closures_are_product_free() -> None:
    violations = {
        module: sorted(name for name in _import_closure(module) if _is_forbidden(name))
        for module in AQ6_MODULES
    }
    assert {module: names for module, names in violations.items() if names} == {}


@pytest.mark.parametrize("source", [
    "import src.workbench_qml",
    "from .workbench_controller import WorkbenchRow",
    "from src import workbench",
    "from src import workbench_harmony",
    "from PySide6.QtCore import QObject",
    "import src.qml.presenter",
])
def test_boundary_detects_absolute_relative_and_presentation_imports(tmp_path, monkeypatch, source):
    package = tmp_path / "src"
    package.mkdir()
    (package / "harmony.py").write_text(source + "\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
    assert any(_is_forbidden(name) for name in _import_closure("src.harmony"))


def test_boundary_follows_indirect_package_submodule_imports(tmp_path, monkeypatch):
    package = tmp_path / "src"
    package.mkdir()
    (package / "harmony.py").write_text("from . import bridge\n", encoding="utf-8")
    (package / "bridge.py").write_text("from src.presenters import nested\n", encoding="utf-8")
    presenters = package / "presenters"
    presenters.mkdir()
    (presenters / "__init__.py").write_text("", encoding="utf-8")
    (presenters / "nested.py").write_text("from .. import workbench_qml\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
    assert "src.workbench_qml" in _import_closure("src.harmony")
    assert any(_is_forbidden(name) for name in _import_closure("src.harmony"))
