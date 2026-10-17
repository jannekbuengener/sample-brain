from __future__ import annotations

import ast
import importlib.util
import sys

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_MODULES = (
    "src.attack_analysis",
    "src.aq3_onset_attack_baseline",
    "src.aq3_onset_attack_candidate_compare",
    "src.gesture_analysis",
)


def _static_imports(module_name: str) -> set[str]:
    source_path = REPO_ROOT.joinpath(*module_name.split(".")).with_suffix(".py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    package = module_name.rpartition(".")[0]
    imports: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative = "." * node.level + (node.module or "")
                base = importlib.util.resolve_name(relative, package)
                imports.add(base)
                if node.module is None:
                    imports.update(f"{base}.{alias.name}" for alias in node.names)
            elif node.module:
                imports.add(node.module)
                if node.module == "src":
                    imports.update(f"src.{alias.name}" for alias in node.names)

    return imports


def _is_forbidden(module_name: str) -> bool:
    return (
        module_name.startswith("PySide6")
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
