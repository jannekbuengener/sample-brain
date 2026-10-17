from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = "src.analysis_contracts"
FORBIDDEN_PREFIXES = (
    "PySide6",
    "src.config",
    "src.config_loader",
    "src.db",
    "src.workbench",
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
                imports.update(
                    f"{base}.{alias.name}"
                    for alias in node.names
                    if alias.name != "*"
                )
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
        pending.extend(
            imported
            for imported in direct
            if imported not in visited and _module_source(imported) is not None
        )
    return imports


def test_analysis_contract_import_closure_is_application_free() -> None:
    imports = _import_closure(ENTRYPOINT)
    violations = sorted(
        imported
        for imported in imports
        if imported.startswith(FORBIDDEN_PREFIXES)
        or any(part == "qml" or part.startswith("qml_") for part in imported.split("."))
    )
    assert violations == []


def test_analysis_candidate_modules_do_not_import_application_config() -> None:
    candidate_modules = (
        "src.analyze",
        "src.canon_audio",
        "src.gesture_analysis",
        "src.track_analysis_cache",
    )
    violations = {
        module_name: sorted(
            imported
            for imported in _static_imports(module_name)
            if imported == "src.config" or imported.startswith("src.config.")
        )
        for module_name in candidate_modules
    }
    assert {module: imports for module, imports in violations.items() if imports} == {}
