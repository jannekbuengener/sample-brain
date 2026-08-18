from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CANON = REPO_ROOT / "docs" / "skills" / "sample-brain-jules-dispatch" / "SKILL.md"
MIRROR = REPO_ROOT / ".cursor" / "skills" / "sample-brain-jules-dispatch" / "SKILL.md"
SKILLS_README = REPO_ROOT / "docs" / "skills" / "README.md"
AVAILABLE = REPO_ROOT / "SB.VERFUEGBARE.SKILLS.md"
ROUTING = REPO_ROOT / ".cursor" / "rules" / "skill-routing.mdc"
PLAN = REPO_ROOT / "docs" / "SKILL_INTEGRATION_PLAN.md"

SKILL_NAME = "sample-brain-jules-dispatch"


def _body(text: str) -> str:
    # Sync comparison ignores frontmatter / comment header ordering:
    # compare from the first markdown heading onward.
    idx = text.find("# Sample Brain Jules Dispatch Skill")
    assert idx != -1, "skill heading not found"
    return text[idx:].strip()


def test_canonical_skill_exists() -> None:
    assert CANON.is_file()


def test_cursor_mirror_exists() -> None:
    assert MIRROR.is_file()


def test_mirror_points_to_canonical_source() -> None:
    mirror_text = MIRROR.read_text(encoding="utf-8")
    assert "Canonical Skill Source: docs/skills/sample-brain-jules-dispatch/SKILL.md" in mirror_text


def test_skill_bodies_are_synchronized() -> None:
    canon = _body(CANON.read_text(encoding="utf-8"))
    mirror = _body(MIRROR.read_text(encoding="utf-8"))
    assert canon == mirror


def test_available_skills_knows_skill() -> None:
    assert SKILL_NAME in AVAILABLE.read_text(encoding="utf-8")


def test_routing_mdc_knows_skill() -> None:
    assert SKILL_NAME in ROUTING.read_text(encoding="utf-8")


def test_skills_readme_knows_skill() -> None:
    assert SKILL_NAME in SKILLS_README.read_text(encoding="utf-8")


def test_integration_plan_knows_skill() -> None:
    assert SKILL_NAME in PLAN.read_text(encoding="utf-8")


def test_skill_explicitly_forbids_merge_and_close() -> None:
    text = CANON.read_text(encoding="utf-8").lower()
    assert "do not merge" in text or "no merge" in text or "never" in text and "merge" in text
    assert "do not close issue" in text or "no issue close" in text


def test_skill_requires_independent_validation() -> None:
    text = CANON.read_text(encoding="utf-8").lower()
    assert "independent" in text
    assert "verification" in text


def test_skill_forbids_private_samples_and_secrets() -> None:
    text = CANON.read_text(encoding="utf-8").lower()
    assert "private sample" in text or "private samples" in text or "sample audio" in text
    assert "secret" in text
    assert "jules_api_key" in text


def test_routing_is_additive_only() -> None:
    # Existing core skills must still be referenced. This guards against a
    # routing rewrite that replaced prior routes.
    routing = ROUTING.read_text(encoding="utf-8")
    for prior in (
        "sample-brain-issue-to-session-plan",
        "sample-brain-root-cause",
        "sample-brain-regression-gap",
        "sample-brain-test-first",
    ):
        assert prior in routing
