from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANON = REPO_ROOT / "docs" / "skills" / "sample-brain-qml-test-run" / "SKILL.md"
MIRROR = REPO_ROOT / ".cursor" / "skills" / "sample-brain-qml-test-run" / "SKILL.md"
HELPER = (
    REPO_ROOT
    / "docs"
    / "skills"
    / "sample-brain-qml-test-run"
    / "scripts"
    / "qml_test_run.py"
)
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "qml_test_run" / "transcripts"
SKILLS_README = REPO_ROOT / "docs" / "skills" / "README.md"
AVAILABLE = REPO_ROOT / "SB.VERFUEGBARE.SKILLS.md"
ROUTING = REPO_ROOT / ".cursor" / "rules" / "skill-routing.mdc"
PLAN = REPO_ROOT / "docs" / "SKILL_INTEGRATION_PLAN.md"
REGISTRY = REPO_ROOT / "docs" / "operations" / "CAPABILITY_REGISTRY.json"
RED_EVIDENCE = (
    REPO_ROOT
    / "docs"
    / "skills"
    / "sample-brain-qml-test-run"
    / "evidence"
    / "RED_BASELINE.md"
)
GREEN_EVIDENCE = (
    REPO_ROOT
    / "docs"
    / "skills"
    / "sample-brain-qml-test-run"
    / "evidence"
    / "GREEN_VALIDATION.md"
)

SKILL_NAME = "sample-brain-qml-test-run"
TOOLS = REPO_ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import capability_lib as caplib  # noqa: E402


def _load_helper():
    spec = importlib.util.spec_from_file_location("qml_test_run", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _body(text: str) -> str:
    idx = text.find("# Sample Brain QML Test-Run Skill")
    assert idx != -1, "skill heading not found"
    return text[idx:].strip()


def _naive_exit_code_only(exit_code: int) -> dict:
    """RED stand-in: treats exit code as the whole story."""
    return {
        "failure_class": "PRODUCT_OR_UNKNOWN" if exit_code != 0 else "PASS",
        "assertions_exercised": None,
        "target_collected": None,
    }


def test_canonical_skill_and_helper_exist() -> None:
    assert CANON.is_file()
    assert HELPER.is_file()
    assert RED_EVIDENCE.is_file()
    assert GREEN_EVIDENCE.is_file()
    assert (FIXTURES / "pass_focused.txt").is_file()


def test_cursor_mirror_exists_and_points_to_canon() -> None:
    assert MIRROR.is_file()
    mirror_text = MIRROR.read_text(encoding="utf-8")
    assert (
        "Canonical Skill Source: docs/skills/sample-brain-qml-test-run/SKILL.md"
        in mirror_text
    )


def test_skill_bodies_are_synchronized() -> None:
    assert _body(CANON.read_text(encoding="utf-8")) == _body(
        MIRROR.read_text(encoding="utf-8")
    )
    mirror_problems = [
        p for p in caplib.validate_skill_mirrors(REPO_ROOT) if SKILL_NAME in p
    ]
    assert mirror_problems == []


def test_registry_and_routing_know_skill() -> None:
    registry = REGISTRY.read_text(encoding="utf-8")
    assert f'"id": "{SKILL_NAME}"' in registry
    assert SKILL_NAME in AVAILABLE.read_text(encoding="utf-8")
    assert SKILL_NAME in ROUTING.read_text(encoding="utf-8")
    assert SKILL_NAME in SKILLS_README.read_text(encoding="utf-8")
    assert SKILL_NAME in PLAN.read_text(encoding="utf-8")


def test_skill_frontmatter_is_trigger_oriented() -> None:
    text = CANON.read_text(encoding="utf-8")
    assert "Use when running, observing, classifying" in text
    assert "standalone: true" in text
    lowered = text.lower()
    assert "sample-brain-root-cause" in lowered
    assert "windows_test_harness" in lowered or "qt_qpa_platform" in lowered
    assert "second test harness" in lowered or "second qml test harness" in lowered
    assert "offscreen" in lowered


def test_red_naive_exit_code_misses_cleanup_noise() -> None:
    naive = _naive_exit_code_only(1)
    assert naive["failure_class"] == "PRODUCT_OR_UNKNOWN"

    helper = _load_helper()
    transcript = (FIXTURES / "cleanup_noise_after_pass.txt").read_text(encoding="utf-8")
    report = helper.run_target(
        "cleanup_noise_after_pass",
        dry_classify_output=transcript,
        dry_exit_code=1,
    )
    assert report.failure_class == "UNRELATED_BASELINE"
    assert report.assertions_exercised is True
    assert "cleanup_noise_after_pass" in RED_EVIDENCE.read_text(
        encoding="utf-8"
    ) or "PermissionError" in RED_EVIDENCE.read_text(encoding="utf-8")


def test_scenario_classifications() -> None:
    helper = _load_helper()
    cases = [
        ("pass_focused.txt", 0, "PASS", True),
        ("assertion_behavior_fail.txt", 1, "ASSERTION_BEHAVIOR", True),
        ("harness_bootstrap_import.txt", 4, "TEST_HARNESS_BOOTSTRAP", False),
        ("qml_parse_load_fail.txt", 1, "QML_PARSE_LOAD_IMPORT", True),
        ("cleanup_noise_after_pass.txt", 1, "UNRELATED_BASELINE", True),
    ]
    for name, exit_code, expected_class, exercised in cases:
        text = (FIXTURES / name).read_text(encoding="utf-8")
        report = helper.run_target(
            name,
            dry_classify_output=text,
            dry_exit_code=exit_code,
        )
        assert report.failure_class == expected_class, name
        assert report.assertions_exercised is exercised, name


def test_recommended_windows_qpa_is_not_blind_offscreen() -> None:
    helper = _load_helper()
    assert helper.recommended_qt_qpa("Windows") == "windows"
    assert helper.recommended_qt_qpa("Linux") is None


def test_helper_does_not_claim_pass_on_skip_only() -> None:
    helper = _load_helper()
    text = "\n1 skipped in 0.10s\n"
    report = helper.run_target(
        "skip_only",
        dry_classify_output=text,
        dry_exit_code=5,
    )
    assert report.failure_class == "TEST_HARNESS_BOOTSTRAP"
    assert report.result_state == "HOLD"
    assert report.assertions_exercised is False
