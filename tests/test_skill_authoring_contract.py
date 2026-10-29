from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "sample-brain-skill-authoring"
CANON = REPO_ROOT / "docs" / "skills" / SKILL_NAME / "SKILL.md"
MIRROR = REPO_ROOT / ".cursor" / "skills" / SKILL_NAME / "SKILL.md"
SKILLS_README = REPO_ROOT / "docs" / "skills" / "README.md"
AVAILABLE = REPO_ROOT / "SB.VERFUEGBARE.SKILLS.md"
ROUTING = REPO_ROOT / ".cursor" / "rules" / "skill-routing.mdc"
PLAN = REPO_ROOT / "docs" / "SKILL_INTEGRATION_PLAN.md"
REGISTRY = REPO_ROOT / "docs" / "operations" / "CAPABILITY_REGISTRY.json"
CHECKER = (
    REPO_ROOT
    / "docs"
    / "skills"
    / SKILL_NAME
    / "scripts"
    / "check_authoring_package.py"
)
HEADING = "# Sample Brain Skill-Authoring Skill"
EVIDENCE = REPO_ROOT / "docs" / "skills" / SKILL_NAME / "evidence"


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
    front = text.split("---", 2)[1]
    assert "Use when" in front
    assert "OBSERVED REUSABLE FAILURE" not in front
    assert "BASELINE WITHOUT SKILL" not in front


def test_standalone_and_no_mandatory_1304() -> None:
    text = CANON.read_text(encoding="utf-8")
    assert "standalone: true" in text
    assert "Does **not** require" in text
    assert "sample-brain-skill-effectiveness" in text
    assert "## Relationships" in text


def test_reuse_decisions_and_lifecycle_enums() -> None:
    text = CANON.read_text(encoding="utf-8")
    for token in (
        "REUSE EXISTING",
        "EXTEND EXISTING",
        "CREATE NEW",
        "DO NOT CREATE",
        "active",
        "on-demand",
        "historical",
        "parked",
        "discipline",
        "technique",
        "pattern",
        "reference",
    ):
        assert token in text


def test_output_contract_fields() -> None:
    text = CANON.read_text(encoding="utf-8")
    for field in (
        "need:",
        "reuse_decision:",
        "skill_id:",
        "skill_type:",
        "trigger:",
        "non_trigger:",
        "canonical_source:",
        "behavior_scenarios:",
        "registry_routing_impact:",
        "lifecycle:",
        "validation_evidence:",
        "exit_decision:",
    ):
        assert field in text


def test_forbids_second_registry_and_unsupported_mirrors() -> None:
    text = CANON.read_text(encoding="utf-8").lower()
    assert "second registry" in text
    assert ".claude" in text
    assert "without verified loader" in text or "loader need" in text


def test_progressive_disclosure_reference_exists() -> None:
    ref = (
        REPO_ROOT
        / "docs"
        / "skills"
        / SKILL_NAME
        / "references"
        / "progressive-disclosure.md"
    )
    checklist = (
        REPO_ROOT
        / "docs"
        / "skills"
        / SKILL_NAME
        / "references"
        / "package-checklist.md"
    )
    assert ref.is_file()
    assert checklist.is_file()
    assert "references/progressive-disclosure.md" in CANON.read_text(encoding="utf-8")


def test_evidence_scenarios_exist() -> None:
    for name in (
        "RED_BASELINE.md",
        "GREEN_VALIDATION.md",
        "VARIANT_EDIT.md",
        "COUNTEREXAMPLE_DO_NOT_CREATE.md",
        "LIFECYCLE_HISTORICAL.md",
        "DESCRIPTION_QUALITY.md",
        "PROGRESSIVE_DISCLOSURE.md",
        "SELF_HOSTING_AUDIT.md",
    ):
        assert (EVIDENCE / name).is_file(), name


def test_red_fixture_is_mirror_only() -> None:
    base = (
        REPO_ROOT
        / "docs"
        / "skills"
        / SKILL_NAME
        / "fixtures"
        / "red-mirror-only-path-hint"
    )
    assert (
        base / ".cursor" / "skills" / "sample-brain-path-hint" / "SKILL.md"
    ).is_file()
    assert not (
        base / "docs" / "skills" / "sample-brain-path-hint" / "SKILL.md"
    ).is_file()


def test_registry_and_generated_views_know_skill() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    matches = [c for c in registry["capabilities"] if c["id"] == SKILL_NAME]
    assert len(matches) == 1
    cap = matches[0]
    assert cap["type"] == "skill"
    assert cap["lifecycle"] == "active"
    assert cap["canonical_source"] == f"docs/skills/{SKILL_NAME}/SKILL.md"
    assert SKILL_NAME in AVAILABLE.read_text(encoding="utf-8")
    assert SKILL_NAME in ROUTING.read_text(encoding="utf-8")
    assert SKILL_NAME in SKILLS_README.read_text(encoding="utf-8")
    assert SKILL_NAME in PLAN.read_text(encoding="utf-8")


def test_historical_liste_not_active_route() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    hist = next(
        c
        for c in registry["capabilities"]
        if c["id"] == "sb-verfuegbare-skills-liste-2026-08-09"
    )
    assert hist["lifecycle"] == "historical"
    for row in registry["routing"]["priority_a_matrix"]:
        assert "sb-verfuegbare-skills-liste-2026-08-09" not in row.get(
            "capability_ids", []
        )


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


def test_check_authoring_package_script_passes() -> None:
    assert CHECKER.is_file()
    proc = subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--root",
            str(REPO_ROOT),
            "--skill-id",
            SKILL_NAME,
            "--check-red-fixture",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
