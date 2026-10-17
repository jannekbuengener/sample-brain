from __future__ import annotations

import ast
import importlib
import importlib.metadata
import math
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "0.1.1"
EXPECTED_WHEEL_URL = (
    "https://github.com/jannekbuengener/sample-brain-analysis/releases/download/"
    "v0.1.1/sample_brain_analysis-0.1.1-py3-none-any.whl"
    "#sha256=3c5d3d97dbc5d171b65c19a56bba2317f64ebcbaaf6dcd075c836b8b29385da7"
)

MODULE_ALIASES = {
    "src.analysis": "sample_brain_analysis",
    "src.analysis_contracts": "sample_brain_analysis.analysis_contracts",
    "src.attack_analysis": "sample_brain_analysis.attack_analysis",
    "src.bpm_display": "sample_brain_analysis.bpm_display",
    "src.bpm_matching": "sample_brain_analysis.bpm_matching",
    "src.canon_audio": "sample_brain_analysis.canon_audio",
    "src.classification": "sample_brain_analysis.classification",
    "src.content_hash": "sample_brain_analysis.content_hash",
    "src.feature_analysis": "sample_brain_analysis.feature_analysis",
    "src.gesture_analysis": "sample_brain_analysis.gesture_analysis",
    "src.harmony": "sample_brain_analysis.harmony",
    "src.joint_key_profile": "sample_brain_analysis.joint_key_profile",
    "src.key_analysis_v2_core": "sample_brain_analysis.key_analysis_v2_core",
    "src.key_signature": "sample_brain_analysis.key_signature",
    "src.utils": "sample_brain_analysis.utils",
}


def test_sample_brain_pins_released_analysis_wheel() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    expected = f"sample-brain-analysis @ {EXPECTED_WHEEL_URL}"
    assert expected in dependencies

    requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert expected in requirements
    assert importlib.metadata.version("sample-brain-analysis") == EXPECTED_VERSION


def test_non_finite_reference_bpm_is_rejected_through_legacy_harmony_consumer_path() -> None:
    harmony = importlib.import_module("src.harmony")
    candidate = harmony.HarmonyInput(
        display_name="candidate",
        relative_path="candidate.wav",
        path="/synthetic/candidate.wav",
        bpm=128.0,
        key="Cmaj",
        pred_type="kick",
    )

    for bpm in (math.nan, math.inf, -math.inf):
        reference = harmony.HarmonyInput(
            display_name="reference",
            relative_path="reference.wav",
            path="/synthetic/reference.wav",
            bpm=bpm,
            key="Cmaj",
            pred_type="kick",
        )
        matches, error = harmony.find_harmony_matches(reference, [candidate])

        assert matches == []
        assert error == "Ähnliche Samples benötigen ein analysiertes BPM."


def test_legacy_analysis_modules_are_external_module_aliases() -> None:
    for legacy_name, external_name in MODULE_ALIASES.items():
        sys.modules.pop(legacy_name, None)
        external = importlib.import_module(external_name)
        legacy = importlib.import_module(legacy_name)
        assert legacy is external, f"{legacy_name} still owns a separate module object"
        source_path = Path(external.__file__).resolve()
        assert not source_path.is_relative_to(REPO_ROOT), (
            f"{external_name} is shadowed by Sample Brain source: {source_path}"
        )


def test_legacy_analysis_shims_contain_no_duplicate_implementation_or_constants() -> None:
    for legacy_name, external_name in MODULE_ALIASES.items():
        relative = Path(*legacy_name.split(".")).with_suffix(".py")
        source_path = REPO_ROOT / relative
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        definitions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        assert definitions == [], f"{legacy_name} still contains implementation definitions"

        external_imports = 0
        module_registrations = 0
        assignments = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
        ]
        for assignment in assignments:
            if (
                isinstance(assignment, ast.Assign)
                and len(assignment.targets) == 1
                and isinstance(assignment.targets[0], ast.Name)
                and assignment.targets[0].id == "_external_module"
                and isinstance(assignment.value, ast.Call)
                and isinstance(assignment.value.func, ast.Name)
                and assignment.value.func.id == "_import_module"
                and len(assignment.value.args) == 1
                and isinstance(assignment.value.args[0], ast.Constant)
                and assignment.value.args[0].value == external_name
                and not assignment.value.keywords
            ):
                external_imports += 1
                continue

            if (
                isinstance(assignment, ast.Assign)
                and len(assignment.targets) == 1
                and isinstance(assignment.targets[0], ast.Subscript)
                and isinstance(assignment.targets[0].value, ast.Attribute)
                and isinstance(assignment.targets[0].value.value, ast.Name)
                and assignment.targets[0].value.value.id == "_sys"
                and assignment.targets[0].value.attr == "modules"
                and isinstance(assignment.targets[0].slice, ast.Name)
                and assignment.targets[0].slice.id == "__name__"
                and isinstance(assignment.value, ast.Name)
                and assignment.value.id == "_external_module"
            ):
                module_registrations += 1
                continue

            raise AssertionError(
                f"{legacy_name} has a non-alias assignment: {ast.dump(assignment)}"
            )

        assert external_imports == 1, f"{legacy_name} must import exactly {external_name}"
        assert module_registrations == 1, f"{legacy_name} must register exactly one alias"
