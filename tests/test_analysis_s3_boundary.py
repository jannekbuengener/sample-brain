from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
NEUTRAL_ANALYSIS_MODULES = (
    "src.feature_analysis",
    "src.classification",
    "src.key_analysis_v2_core",
    "src.bpm_matching",
)
FORBIDDEN_PREFIXES = (
    "PySide6",
    "sqlalchemy",
    "src.config",
    "src.config_loader",
    "src.db",
    "src.index",
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
        raise FileNotFoundError(f"Missing S3 neutral analysis surface: {module_name}")
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


def _is_forbidden(module_name: str) -> bool:
    return (
        module_name.startswith(FORBIDDEN_PREFIXES)
        or any(part == "qml" or part.startswith("qml_") for part in module_name.split("."))
    )


@pytest.mark.parametrize("module_name", NEUTRAL_ANALYSIS_MODULES)
def test_s3_neutral_analysis_import_closures_are_application_free(module_name: str) -> None:
    violations = sorted(name for name in _import_closure(module_name) if _is_forbidden(name))
    assert violations == []


def test_feature_analysis_legacy_surface_identity() -> None:
    from src import analyze, feature_analysis

    assert analyze.extract_features is feature_analysis.extract_features
    assert analyze.safe_load is feature_analysis.safe_load
    assert analyze.estimate_key is feature_analysis.estimate_key
    assert analyze.estimate_key_mode is feature_analysis.estimate_key_mode


def test_classification_legacy_surface_identity() -> None:
    from src import classification, classify

    assert classify.rule_type is classification.rule_type
    assert classify._knn_predict is classification._knn_predict


def test_key_v2_legacy_compute_surface_identity() -> None:
    from src import key_analysis_v2, key_analysis_v2_core

    assert key_analysis_v2.KeyAnalysisV2Result is key_analysis_v2_core.KeyAnalysisV2Result
    assert key_analysis_v2.estimate_key_v2_shadow is key_analysis_v2_core.estimate_key_v2_shadow
    assert (
        key_analysis_v2.serialize_key_analysis_v2_evidence
        is key_analysis_v2_core.serialize_key_analysis_v2_evidence
    )


def test_key_v2_contract_version_has_neutral_semantic_owner() -> None:
    from src import analysis_contracts, db, key_analysis_v2, key_analysis_v2_core

    assert analysis_contracts.KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION == 2
    assert db.KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION == 2
    assert key_analysis_v2.KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION == 2
    assert key_analysis_v2_core.KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION == 2


def test_bpm_matching_legacy_surface_identity() -> None:
    from src import bpm_matching, matching

    assert matching.score_bpm_match is bpm_matching.score_bpm_match
    assert matching._score_bpm_details is bpm_matching._score_bpm_details
    assert matching.DEFAULT_BPM_TOLERANCE == bpm_matching.DEFAULT_BPM_TOLERANCE == 8.0


def test_harmony_depends_on_neutral_bpm_matching_not_catalog_matching() -> None:
    imports = _static_imports("src.harmony")
    assert "src.bpm_matching" in imports
    assert "src.matching" not in imports