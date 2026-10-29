from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "sample-brain-skill-effectiveness"
CANON = REPO_ROOT / "docs" / "skills" / SKILL_NAME / "SKILL.md"
MIRROR = REPO_ROOT / ".cursor" / "skills" / SKILL_NAME / "SKILL.md"
SKILLS_README = REPO_ROOT / "docs" / "skills" / "README.md"
AVAILABLE = REPO_ROOT / "SB.VERFUEGBARE.SKILLS.md"
ROUTING = REPO_ROOT / ".cursor" / "rules" / "skill-routing.mdc"
PLAN = REPO_ROOT / "docs" / "SKILL_INTEGRATION_PLAN.md"
REGISTRY = REPO_ROOT / "docs" / "operations" / "CAPABILITY_REGISTRY.json"
FIXTURE = (
    REPO_ROOT
    / "docs"
    / "skills"
    / SKILL_NAME
    / "fixtures"
    / "eval-only-cite-git-sha"
    / "SKILL.md"
)
HEADING = "# Sample Brain Skill-Effectiveness Skill"


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
        f"Canonical Skill Source: docs/skills/{SKILL_NAME}/SKILL.md" in mirror_text
    )


def test_skill_bodies_are_synchronized() -> None:
    assert _body(CANON.read_text(encoding="utf-8")) == _body(
        MIRROR.read_text(encoding="utf-8")
    )


def test_frontmatter_description_is_activation_oriented() -> None:
    text = CANON.read_text(encoding="utf-8")
    assert "Use when" in text
    # Description must not dump the full algorithm into frontmatter alone.
    front = text.split("---", 2)[1]
    assert "BASELINE WITHOUT SKILL" not in front


def test_distinguishes_structural_vs_behavioral() -> None:
    text = CANON.read_text(encoding="utf-8").lower()
    assert "structural" in text
    assert "insufficient" in text
    assert "behavioral" in text or "behavior" in text


def test_result_contract_and_incomplete_fail_closed() -> None:
    text = CANON.read_text(encoding="utf-8")
    assert "EFFECTIVE" in text
    assert "INEFFECTIVE" in text
    assert "UNNECESSARY" in text
    assert "INCOMPLETE" in text
    assert "missing_baseline" in text or "Baseline not captured" in text


def test_skill_types_are_classified() -> None:
    text = CANON.read_text(encoding="utf-8")
    for kind in ("discipline", "technique", "pattern", "reference"):
        assert kind in text


def test_standalone_and_relationships_boundaries() -> None:
    text = CANON.read_text(encoding="utf-8")
    assert "standalone: true" in text
    assert "## Relationships" in text
    lowered = text.lower()
    assert "does **not** replace" in text.lower() or "does not replace" in lowered
    assert "arvp" in lowered
    assert "root-cause" in lowered


def test_provider_independence() -> None:
    text = CANON.read_text(encoding="utf-8").lower()
    assert "provider-neutral" in text or "no mandatory cloud" in text
    assert "chatgpt mcp" in text


def test_helper_script_exists() -> None:
    helper = (
        REPO_ROOT
        / "docs"
        / "skills"
        / SKILL_NAME
        / "scripts"
        / "evaluate_result.py"
    )
    assert helper.is_file()


def test_evaluation_fixture_exists_but_is_not_production_capability() -> None:
    assert FIXTURE.is_file()
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    ids = {cap["id"] for cap in registry["capabilities"]}
    assert "eval-only-cite-git-sha" not in ids
    assert SKILL_NAME in ids


def test_evidence_covers_existing_and_new_candidate() -> None:
    existing = (
        REPO_ROOT
        / "docs"
        / "skills"
        / SKILL_NAME
        / "evidence"
        / "existing-test-first"
        / "RESULT.yml"
    )
    fixture = (
        REPO_ROOT
        / "docs"
        / "skills"
        / SKILL_NAME
        / "evidence"
        / "fixture-cite-git-sha"
        / "RESULT.yml"
    )
    assert existing.is_file()
    assert fixture.is_file()
    assert "sample-brain-test-first" in existing.read_text(encoding="utf-8")
    assert "eval-only-cite-git-sha" in fixture.read_text(encoding="utf-8")


def test_registry_and_generated_views_know_skill() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    cap = next(c for c in registry["capabilities"] if c["id"] == SKILL_NAME)
    assert cap["type"] == "skill"
    assert cap["lifecycle"] == "active"
    assert cap["canonical_source"] == f"docs/skills/{SKILL_NAME}/SKILL.md"
    situations = [
        row["situation"] for row in registry["routing"]["priority_a_matrix"]
    ]
    assert any("Skill-Effektivität" in s or "skill effectiveness" in s.lower() for s in situations) or any(
        SKILL_NAME in row.get("capability_ids", [])
        for row in registry["routing"]["priority_a_matrix"]
    )
    assert SKILL_NAME in AVAILABLE.read_text(encoding="utf-8")
    assert SKILL_NAME in ROUTING.read_text(encoding="utf-8")
    assert SKILL_NAME in SKILLS_README.read_text(encoding="utf-8")
    assert SKILL_NAME in PLAN.read_text(encoding="utf-8")


def test_routing_keeps_prior_core_skills() -> None:
    routing = ROUTING.read_text(encoding="utf-8")
    for prior in (
        "sample-brain-issue-to-session-plan",
        "sample-brain-root-cause",
        "sample-brain-regression-gap",
        "sample-brain-test-first",
        "sample-brain-jules-dispatch",
    ):
        assert prior in routing
