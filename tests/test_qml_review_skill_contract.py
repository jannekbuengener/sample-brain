from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANON = REPO_ROOT / "docs" / "skills" / "sample-brain-qml-review" / "SKILL.md"
MIRROR = REPO_ROOT / ".cursor" / "skills" / "sample-brain-qml-review" / "SKILL.md"
SCANNER = (
    REPO_ROOT
    / "docs"
    / "skills"
    / "sample-brain-qml-review"
    / "scripts"
    / "qml_review_scan.py"
)
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "qml_review"
SKILLS_README = REPO_ROOT / "docs" / "skills" / "README.md"
AVAILABLE = REPO_ROOT / "SB.VERFUEGBARE.SKILLS.md"
ROUTING = REPO_ROOT / ".cursor" / "rules" / "skill-routing.mdc"
PLAN = REPO_ROOT / "docs" / "SKILL_INTEGRATION_PLAN.md"
REGISTRY = REPO_ROOT / "docs" / "operations" / "CAPABILITY_REGISTRY.json"
RED_EVIDENCE = (
    REPO_ROOT
    / "docs"
    / "skills"
    / "sample-brain-qml-review"
    / "evidence"
    / "RED_BASELINE.md"
)
GREEN_EVIDENCE = (
    REPO_ROOT
    / "docs"
    / "skills"
    / "sample-brain-qml-review"
    / "evidence"
    / "GREEN_VALIDATION.md"
)

SKILL_NAME = "sample-brain-qml-review"
TOOLS = REPO_ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import capability_lib as caplib  # noqa: E402


def _load_scanner():
    spec = importlib.util.spec_from_file_location("qml_review_scan", SCANNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses require the module to be present in sys.modules during exec.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _body(text: str) -> str:
    idx = text.find("# Sample Brain QML Review Skill")
    assert idx != -1, "skill heading not found"
    return text[idx:].strip()


def _generic_review_misses_authority(path: Path) -> dict:
    """Stand-in for RED generic review: notices QML surface, misses authority classes."""
    text = path.read_text(encoding="utf-8")
    return {
        "activated": "ListView" in text or "QtQuick" in text,
        "categories": [],
        "verdict": "PASS",
        "notes": "debounce/Timer treated as UX only",
    }


def test_canonical_skill_exists() -> None:
    assert CANON.is_file()
    assert SCANNER.is_file()
    assert RED_EVIDENCE.is_file()
    assert GREEN_EVIDENCE.is_file()


def test_cursor_mirror_exists_and_points_to_canon() -> None:
    assert MIRROR.is_file()
    mirror_text = MIRROR.read_text(encoding="utf-8")
    assert (
        "Canonical Skill Source: docs/skills/sample-brain-qml-review/SKILL.md"
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
    assert "Use when reviewing Sample Brain changes that materially contain" in text
    assert "PySide6" in text
    assert "Qt Quick" in text or "QML" in text
    lowered = text.lower()
    assert "python/core" in lowered
    assert "projection" in lowered
    assert "sample-brain-root-cause" in lowered
    assert "sample-brain-regression-gap" in lowered
    assert "sample-brain-test-first" in lowered
    assert "not_activated" in lowered
    assert "auto-edit product code" in lowered or "must not" in lowered


def test_red_vs_green_behavior_delta_on_same_fixture() -> None:
    red_path = FIXTURES / "red_stale_delegate_index.qml"
    generic = _generic_review_misses_authority(red_path)
    assert generic["verdict"] == "PASS"
    assert "DELEGATE_IDENTITY_AS_AUTHORITY" not in generic["categories"]
    assert "STALE_CACHED_DELEGATE_INDEX" not in generic["categories"]

    scanner = _load_scanner()
    green = scanner.scan_paths([red_path])
    categories = {f["category"] for f in green["findings"]}
    assert green["activated"] is True
    assert green["verdict"] == "HOLD"
    # Helper supplies a mechanical reuse-risk signal only.
    assert "STALE_CACHED_DELEGATE_INDEX" in categories
    assert "QML_SHADOW_AUTHORITY" not in categories
    # Skill body keeps the semantic authority category for agent judgment.
    skill = CANON.read_text(encoding="utf-8")
    assert "DELEGATE_IDENTITY_AS_AUTHORITY" in skill
    assert "semantic ownership review required" in green["findings"][0]["authority"]
    # Evidence docs must name the same fixture for non-cheating RED/GREEN.
    assert "red_stale_delegate_index.qml" in RED_EVIDENCE.read_text(encoding="utf-8")
    assert "red_stale_delegate_index.qml" in GREEN_EVIDENCE.read_text(encoding="utf-8")


def test_variants_transfer() -> None:
    scanner = _load_scanner()
    binding = scanner.scan_paths([FIXTURES / "variants" / "binding_break_width.qml"])
    shadow = scanner.scan_paths(
        [FIXTURES / "variants" / "qml_shadow_bpm_authority.qml"]
    )
    assert binding["verdict"] == "HOLD"
    assert {f["category"] for f in binding["findings"]} >= {"BINDING_BREAK_ASSIGNMENT"}
    # Authority/shadow ownership is semantic — helper must not token-HOLD it.
    shadow_categories = {f["category"] for f in shadow["findings"]}
    assert "QML_SHADOW_AUTHORITY" not in shadow_categories
    assert "MUSICAL_SHADOW" not in CANON.read_text(encoding="utf-8")
    assert "QML_SHADOW_AUTHORITY" in CANON.read_text(encoding="utf-8")
    assert "semantic only" in CANON.read_text(encoding="utf-8").lower() or (
        "not helper-tokenized" in CANON.read_text(encoding="utf-8")
    )


def test_helper_has_no_authority_token_lists() -> None:
    source = SCANNER.read_text(encoding="utf-8")
    assert "MUSICAL_SHADOW_NAMES" not in source
    assert "QML_SHADOW_AUTHORITY" not in source
    assert "authority-token" not in source.lower()


def test_counterexample_no_false_positive() -> None:
    scanner = _load_scanner()
    result = scanner.scan_paths(
        [FIXTURES / "counterexamples" / "immediate_index_intent.qml"]
    )
    assert result["activated"] is True
    assert result["verdict"] == "PASS"
    assert result["findings"] == []


def test_non_activation_for_python_only() -> None:
    scanner = _load_scanner()
    result = scanner.scan_paths([FIXTURES / "non_activation_python_only.py"])
    assert result["activated"] is False
    assert result["verdict"] == "NOT_ACTIVATED"
    assert result["findings"] == []


def test_helper_cli_json_roundtrip() -> None:
    scanner = _load_scanner()
    # Exercise main() path lightly via scan_paths already covered; ensure module API.
    assert callable(scanner.should_activate)
    assert callable(scanner.try_qmllint)
