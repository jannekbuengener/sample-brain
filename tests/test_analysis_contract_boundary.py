from __future__ import annotations

import ast
import importlib
import importlib.util
import os
import subprocess
import sys
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
    if "." in module_name:
        parts = module_name.split(".")[:-1]
        parents = (".".join(parts[:index]) for index in range(1, len(parts) + 1))
        pending.extend(parent for parent in parents if _module_source(parent) is not None)
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


ANALYSIS_PUBLIC_IMPORT_ROOT = "src.analysis"
ANALYSIS_PUBLIC_API = (
    "ANALYZE_HOP_LENGTH", "ANALYZE_SR", "AttackSuggestion", "BPMNormalizationMode",
    "Features", "GestureAnalysis", "GestureEvent", "HarmonyInput", "HarmonyRelation",
    "HarmonySuggestion", "KeyAnalysisV2Result", "ParsedKey", "analyze_gesture_audio",
    "determine_relation", "estimate_key_v2_shadow", "extract_features", "find_harmony_matches",
    "format_key_signature", "is_same_mode", "is_same_root", "key_distance_semitones",
    "normalize_bpm", "parse_key_signature", "rate_harmony", "rule_type", "score_bpm_match",
    "suggest_attack_ms", "validate_bpm_normalization",
)

ANALYSIS_PACKAGE_CANDIDATES = (
    ANALYSIS_PUBLIC_IMPORT_ROOT, "src.analysis_contracts", "src.feature_analysis",
    "src.classification", "src.key_analysis_v2_core", "src.joint_key_profile",
    "src.bpm_matching", "src.attack_analysis", "src.gesture_analysis", "src.harmony",
    "src.key_signature", "src.canon_audio",
)
ANALYSIS_ALLOWED_INTERNAL_MODULES = {
    *ANALYSIS_PACKAGE_CANDIDATES,
    "src.bpm_display",
    "src.content_hash",
    "src.utils",
}

ANALYSIS_FORBIDDEN_MODULES = {
    "src.analyze", "src.asset_analysis", "src.cli", "src.classify", "src.config",
    "src.config_loader", "src.context_analyze", "src.db", "src.key_analysis_v2",
    "src.matching", "src.path_metadata", "src.scan",
}
ANALYSIS_FORBIDDEN_PREFIXES = ("src.workbench", "workbench", "PySide6", "sqlalchemy", "tkinter", "PyInstaller")
ANALYSIS_ALLOWED_EXTERNAL_ROOTS = {"librosa", "numpy", "soundfile"}
ANALYSIS_FORBIDDEN_STANDARD_LIBRARY_ROOTS = {"sqlite3", "_sqlite3"}


def _is_analysis_forbidden(module_name: str) -> bool:
    return (
        any(
            module_name == forbidden or module_name.startswith(f"{forbidden}.")
            for forbidden in ANALYSIS_FORBIDDEN_MODULES
        )
        or any(
            module_name == prefix
            or module_name.startswith(f"{prefix}.")
            or module_name.startswith(f"{prefix}_")
            for prefix in ANALYSIS_FORBIDDEN_PREFIXES
        )
    )


def _is_analysis_internal_import_allowed(module_name: str) -> bool:
    return module_name == "src" or any(
        module_name == allowed or module_name.startswith(f"{allowed}.")
        for allowed in ANALYSIS_ALLOWED_INTERNAL_MODULES
    )


def _is_forbidden_standard_library_import(module_name: str) -> bool:
    return module_name.split(".", 1)[0] in ANALYSIS_FORBIDDEN_STANDARD_LIBRARY_ROOTS


def _import_time_nodes(tree: ast.AST):
    def visit(node: ast.AST):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield from node.decorator_list
            yield from node.args.defaults
            yield from (default for default in node.args.kw_defaults if default is not None)
            return
        if isinstance(node, ast.ClassDef):
            yield from node.decorator_list
            yield from node.bases
            yield from node.keywords
            for child in node.body:
                yield from visit(child)
            return
        yield node
        for child in ast.iter_child_nodes(node):
            yield from visit(child)

    for statement in tree.body:
        yield from visit(statement)


def _product_environment_accesses(tree: ast.AST) -> set[str]:
    findings: set[str] = set()
    os_modules = {"os"}
    getenv_names: set[str] = set()
    environ_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_modules.add(alias.asname or "os")
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                if alias.name == "getenv":
                    getenv_names.add(alias.asname or alias.name)
                elif alias.name == "environ":
                    environ_names.add(alias.asname or alias.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in os_modules and node.attr == "environ":
                findings.add("os.environ")
            if node.value.id in os_modules and node.attr == "getenv":
                findings.add("os.getenv")
        if isinstance(node, ast.Name) and node.id in environ_names:
            findings.add("os.environ")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in getenv_names:
                findings.add("os.getenv")
    return findings


def test_analysis_forbidden_modules_cover_submodules() -> None:
    assert _is_analysis_forbidden("src.db.models")
    assert _is_analysis_forbidden("src.config.profile")
    assert not _is_analysis_forbidden("src.db_helpers")


def test_analysis_import_gate_requires_explicit_internal_and_stdlib_allowlists() -> None:
    assert _is_analysis_internal_import_allowed("src.bpm_display.format_bpm_display")
    assert not _is_analysis_internal_import_allowed("src.live_profile")
    assert not _is_analysis_internal_import_allowed("src.analysis_quality_loop_state")
    assert _is_forbidden_standard_library_import("sqlite3.dbapi2")
    assert _is_forbidden_standard_library_import("_sqlite3")
    assert not _is_forbidden_standard_library_import("statistics")


def test_analysis_environment_gate_resolves_os_import_aliases() -> None:
    tree = ast.parse(
        "import os as operating_system\n"
        "from os import getenv as read_env, environ as environment\n"
        "value = operating_system.getenv('X')\n"
        "other = read_env('Y')\n"
        "third = environment.get('Z')\n"
    )
    assert _product_environment_accesses(tree) == {"os.environ", "os.getenv"}


def test_analysis_public_api_manifest_is_frozen() -> None:
    api = importlib.import_module(ANALYSIS_PUBLIC_IMPORT_ROOT)
    assert tuple(api.__all__) == ANALYSIS_PUBLIC_API

    owners = {
        "ANALYZE_HOP_LENGTH": "src.analysis_contracts", "ANALYZE_SR": "src.analysis_contracts",
        "AttackSuggestion": "src.attack_analysis", "BPMNormalizationMode": "src.analysis_contracts",
        "Features": "src.analysis_contracts", "GestureAnalysis": "src.gesture_analysis",
        "GestureEvent": "src.gesture_analysis", "HarmonyInput": "src.harmony",
        "HarmonyRelation": "src.harmony", "HarmonySuggestion": "src.harmony",
        "KeyAnalysisV2Result": "src.key_analysis_v2_core", "ParsedKey": "src.key_signature",
        "analyze_gesture_audio": "src.gesture_analysis", "determine_relation": "src.harmony",
        "estimate_key_v2_shadow": "src.key_analysis_v2_core", "extract_features": "src.feature_analysis",
        "find_harmony_matches": "src.harmony", "format_key_signature": "src.key_signature",
        "is_same_mode": "src.key_signature", "is_same_root": "src.key_signature",
        "key_distance_semitones": "src.key_signature", "normalize_bpm": "src.feature_analysis",
        "parse_key_signature": "src.key_signature", "rate_harmony": "src.harmony",
        "rule_type": "src.classification", "score_bpm_match": "src.bpm_matching",
        "suggest_attack_ms": "src.attack_analysis",
        "validate_bpm_normalization": "src.analysis_contracts",
    }
    assert set(owners) == set(ANALYSIS_PUBLIC_API)
    for name, module_name in owners.items():
        assert getattr(api, name) is getattr(importlib.import_module(module_name), name)


def test_analysis_package_import_closure_has_only_neutral_dependencies() -> None:
    closures = {
        module: _import_closure(module)
        for module in ANALYSIS_PACKAGE_CANDIDATES
    }
    violations = {
        module: sorted(
            imported for imported in imports
            if _is_analysis_forbidden(imported)
            or any(part == "qml" or part.startswith("qml_") for part in imported.split("."))
        )
        for module, imports in closures.items()
    }
    assert {module: imports for module, imports in violations.items() if imports} == {}

    internal_imports = {
        imported
        for imports in closures.values()
        for imported in imports
        if imported == "src" or imported.startswith("src.")
    }
    unexpected_internal = sorted(
        imported
        for imported in internal_imports
        if not _is_analysis_internal_import_allowed(imported)
    )
    assert unexpected_internal == []

    forbidden_standard_library = sorted(
        imported
        for imports in closures.values()
        for imported in imports
        if _is_forbidden_standard_library_import(imported)
    )
    assert forbidden_standard_library == []

    external_imports = {
        imported.split(".", 1)[0]
        for imports in closures.values()
        for imported in imports
        if imported and imported.split(".", 1)[0] not in sys.stdlib_module_names
        and imported.split(".", 1)[0] != "src"
    }
    assert external_imports <= ANALYSIS_ALLOWED_EXTERNAL_ROOTS


def test_analysis_candidates_do_not_own_product_environment_or_import_state() -> None:
    findings: dict[str, list[str]] = {}
    modules_to_scan: set[str] = set()
    for module in ANALYSIS_PACKAGE_CANDIDATES:
        modules_to_scan.add(module)
        for imported in _import_closure(module):
            parts = imported.split(".")
            for end in range(len(parts), 0, -1):
                candidate = ".".join(parts[:end])
                if _module_source(candidate) is not None:
                    modules_to_scan.add(candidate)
                    break
    for module in sorted(modules_to_scan):
        source = _module_source(module)
        assert source is not None
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        module_findings = _product_environment_accesses(tree)
        for node in _import_time_nodes(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in {"mkdir", "makedirs"}:
                module_findings.add(f"import-time {func.attr}")
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == "Path" and func.attr in {"home", "cwd"}:
                    module_findings.add(f"import-time Path.{func.attr}")
        if module_findings:
            findings[module] = sorted(module_findings)
    assert findings == {}


def test_analysis_public_api_works_from_clean_non_repo_context(tmp_path: Path) -> None:
    consumer_cwd = tmp_path / "consumer"
    consumer_cwd.mkdir()
    baseline_entries = sorted(path.name for path in consumer_cwd.iterdir())
    code = f"""
import sample_brain_analysis as external_analysis
import src.analysis as analysis
from pathlib import Path

assert analysis is external_analysis
assert analysis.normalize_bpm(80.0, "heuristic") == 160.0
assert analysis.rule_type(0.2, -12.0, 6000.0, None, "oneshot")
assert analysis.score_bpm_match(120.0, 120.0, 8.0) == 1.0
assert analysis.parse_key_signature("C major").root == "C"
left = analysis.HarmonyInput("ref", "ref.wav", "ref.wav", 120.0, "Cmaj", None)
right = analysis.HarmonyInput("candidate", "candidate.wav", "candidate.wav", 120.0, "Cmaj", None)
assert analysis.rate_harmony(left, right).total_score == 1.0
assert sorted(path.name for path in Path.cwd().iterdir()) == {baseline_entries!r}
"""
    env = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith("SAMPLE_BRAIN_")
        and key.upper() not in {"PYTHONPATH", "PYTHONHOME"}
    }
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=consumer_cwd, env=env,
        check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert sorted(path.name for path in consumer_cwd.iterdir()) == baseline_entries
