from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANON = REPO_ROOT / "docs" / "skills" / "sample-brain-qml-component-test" / "SKILL.md"
MIRROR = REPO_ROOT / ".cursor" / "skills" / "sample-brain-qml-component-test" / "SKILL.md"
SKILLS_README = REPO_ROOT / "docs" / "skills" / "README.md"
AVAILABLE = REPO_ROOT / "SB.VERFUEGBARE.SKILLS.md"
ROUTING = REPO_ROOT / ".cursor" / "rules" / "skill-routing.mdc"
PLAN = REPO_ROOT / "docs" / "SKILL_INTEGRATION_PLAN.md"
REGISTRY = REPO_ROOT / "docs" / "operations" / "CAPABILITY_REGISTRY.json"

SKILL_NAME = "sample-brain-qml-component-test"
HEADING = "# Sample Brain QML Component-Test Skill"


def _body(text: str) -> str:
    idx = text.find(HEADING)
    assert idx != -1, "skill heading not found"
    return text[idx:].strip()


def test_canonical_skill_exists() -> None:
    assert CANON.is_file()


def test_cursor_mirror_exists() -> None:
    assert MIRROR.is_file()


def test_mirror_points_to_canonical_source() -> None:
    mirror_text = MIRROR.read_text(encoding="utf-8")
    assert (
        "Canonical Skill Source: docs/skills/sample-brain-qml-component-test/SKILL.md"
        in mirror_text
    )


def test_skill_bodies_are_synchronized() -> None:
    assert _body(CANON.read_text(encoding="utf-8")) == _body(
        MIRROR.read_text(encoding="utf-8")
    )


def test_available_skills_knows_skill() -> None:
    assert SKILL_NAME in AVAILABLE.read_text(encoding="utf-8")


def test_routing_mdc_knows_skill() -> None:
    assert SKILL_NAME in ROUTING.read_text(encoding="utf-8")


def test_skills_readme_knows_skill() -> None:
    assert SKILL_NAME in SKILLS_README.read_text(encoding="utf-8")


def test_integration_plan_knows_skill() -> None:
    assert SKILL_NAME in PLAN.read_text(encoding="utf-8")


def test_registry_lists_skill() -> None:
    assert SKILL_NAME in REGISTRY.read_text(encoding="utf-8")


def test_skill_declares_standalone_and_output_contract() -> None:
    text = CANON.read_text(encoding="utf-8")
    assert "standalone: true" in text
    for field in (
        "Behavior/authority:",
        "Why QML component coverage required:",
        "Layer decision:",
        "Fixture/boundary:",
        "Inputs/events:",
        "Observable assertions:",
        "Async/wait strategy:",
        "Lifecycle/virtualization:",
        "Companion tests:",
        "Non-goals:",
    ):
        assert field in text


def test_skill_keeps_python_authority_boundary() -> None:
    text = CANON.read_text(encoding="utf-8").lower()
    assert "python/core" in text or "python/core/controller" in text
    assert "authoritative" in text
    assert "do not bless duplicated qml product authority" in text


def test_skill_does_not_require_1303_or_1304_at_runtime() -> None:
    text = CANON.read_text(encoding="utf-8").lower()
    assert "does **not** require" in CANON.read_text(encoding="utf-8").lower() or (
        "does not require" in text
    )
    assert "sample-brain-qml-review" in text
    assert "sample-brain-skill-effectiveness" in text


def test_routing_is_additive_only() -> None:
    routing = ROUTING.read_text(encoding="utf-8")
    for prior in (
        "sample-brain-issue-to-session-plan",
        "sample-brain-root-cause",
        "sample-brain-regression-gap",
        "sample-brain-test-first",
        "sample-brain-jules-dispatch",
    ):
        assert prior in routing


def test_red_green_transfer_counterexample_evidence_exists() -> None:
    evidence = REPO_ROOT / "docs" / "skills" / "sample-brain-qml-component-test" / "evidence"
    for name in (
        "RED_BASELINE.md",
        "GREEN_VALIDATION.md",
        "TRANSFER_VIRTUALIZATION.md",
        "COUNTEREXAMPLE_PYTHON_DOMAIN.md",
    ):
        assert (evidence / name).is_file()
