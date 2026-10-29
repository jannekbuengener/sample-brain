from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "sample-brain-qml-profiler"
CANON = REPO_ROOT / "docs" / "skills" / SKILL_NAME / "SKILL.md"
MIRROR = REPO_ROOT / ".cursor" / "skills" / SKILL_NAME / "SKILL.md"
HELPER = (
    REPO_ROOT
    / "docs"
    / "skills"
    / SKILL_NAME
    / "scripts"
    / "qml_profiler_summarize.py"
)
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "qml_profiler"
RED_EVIDENCE = (
    REPO_ROOT / "docs" / "skills" / SKILL_NAME / "evidence" / "RED_BASELINE.md"
)
GREEN_EVIDENCE = (
    REPO_ROOT / "docs" / "skills" / SKILL_NAME / "evidence" / "GREEN_VALIDATION.md"
)
SKILLS_README = REPO_ROOT / "docs" / "skills" / "README.md"
AVAILABLE = REPO_ROOT / "SB.VERFUEGBARE.SKILLS.md"
ROUTING = REPO_ROOT / ".cursor" / "rules" / "skill-routing.mdc"
PLAN = REPO_ROOT / "docs" / "SKILL_INTEGRATION_PLAN.md"
REGISTRY = REPO_ROOT / "docs" / "operations" / "CAPABILITY_REGISTRY.json"

TOOLS = REPO_ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import capability_lib as caplib  # noqa: E402


def _load_helper():
    spec = importlib.util.spec_from_file_location("qml_profiler_summarize", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _body(text: str) -> str:
    idx = text.find("# Sample Brain QML Profiler Skill")
    assert idx != -1, "skill heading not found"
    return text[idx:].strip()


def _naive_perf_answer(path: Path) -> dict:
    """Stand-in for RED generic investigation: guesses without measurement."""
    raw = path.read_text(encoding="utf-8")
    return {
        "reproduction": None,
        "tool_discovery": "skipped",
        "measured_hotspots": [],
        "verdict": "guessed_fix_without_measurement",
        "mentions_qmlprofiler_assumption": "qmlprofiler" in raw.lower(),
    }


def test_canonical_skill_and_evidence_exist() -> None:
    assert CANON.is_file()
    assert HELPER.is_file()
    assert RED_EVIDENCE.is_file()
    assert GREEN_EVIDENCE.is_file()
    assert (FIXTURES / "red_naive_scroll_complaint.yaml").is_file()


def test_cursor_mirror_exists_and_points_to_canon() -> None:
    assert MIRROR.is_file()
    mirror_text = MIRROR.read_text(encoding="utf-8")
    assert (
        f"Canonical Skill Source: docs/skills/{SKILL_NAME}/SKILL.md" in mirror_text
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
    assert "Use when investigating Sample Brain PySide6" in text
    assert "MEASURE FIRST" in text
    lowered = text.lower()
    assert "standalone: true" in lowered
    assert "sample-brain-root-cause" in lowered
    assert "hotspot_proven" in lowered
    assert "no_actionable_hotspot" in lowered
    assert "profile_inconclusive" in lowered
    assert "do not invent" in lowered or "must not" in lowered


def test_red_naive_answer_misses_measurement() -> None:
    red = FIXTURES / "red_naive_scroll_complaint.yaml"
    naive = _naive_perf_answer(red)
    assert naive["reproduction"] is None
    assert naive["measured_hotspots"] == []
    assert naive["verdict"] == "guessed_fix_without_measurement"
    assert naive["mentions_qmlprofiler_assumption"] is True
    red_doc = RED_EVIDENCE.read_text(encoding="utf-8")
    assert "red_naive_scroll_complaint.yaml" in red_doc
    assert "GENERIC_PERF_INVESTIGATION_INCOMPLETE" in red_doc


def test_scenario_a_hotspot_proven_delegate() -> None:
    helper = _load_helper()
    capture = json.loads(
        (FIXTURES / "scenario_a_delegate_churn.json").read_text(encoding="utf-8")
    )
    summary = helper.summarize(capture, REPO_ROOT)
    assert summary["verdict"] == "HOTSPOT_PROVEN"
    dominant = summary["verdict_detail"]["dominant"]
    assert dominant["category"] == "delegate_lifecycle"
    assert dominant["component"] == "browserRow"
    assert str(dominant.get("mapped_path") or "").endswith("workbench_qml.py")
    assert summary["hypothesis"] is not None
    assert summary["hypothesis"]["evidence_class"] == "HYPOTHESIS"
    assert summary["next_experiment"]["evidence_class"] == "VERIFY"
    assert any(m["evidence_class"] == "MEASURED" for m in summary["measured"])
    green = GREEN_EVIDENCE.read_text(encoding="utf-8")
    assert "scenario_a_delegate_churn.json" in green


def test_scenario_b_variant_bridge_transfer() -> None:
    helper = _load_helper()
    capture = json.loads(
        (FIXTURES / "scenario_b_bridge_traffic.json").read_text(encoding="utf-8")
    )
    summary = helper.summarize(capture, REPO_ROOT)
    assert summary["verdict"] == "HOTSPOT_PROVEN"
    assert summary["verdict_detail"]["dominant"]["category"] == "python_bridge"


def test_scenario_c_no_hotspot_and_inconclusive() -> None:
    helper = _load_helper()
    flat = json.loads(
        (FIXTURES / "scenario_c_no_hotspot.json").read_text(encoding="utf-8")
    )
    inconclusive = json.loads(
        (FIXTURES / "scenario_c_inconclusive.json").read_text(encoding="utf-8")
    )
    assert helper.summarize(flat, REPO_ROOT)["verdict"] == "NO_ACTIONABLE_HOTSPOT"
    assert (
        helper.summarize(inconclusive, REPO_ROOT)["verdict"] == "PROFILE_INCONCLUSIVE"
    )


def test_discover_tooling_does_not_require_second_qt_sdk() -> None:
    helper = _load_helper()
    discovered = helper.discover_tooling(REPO_ROOT)
    assert discovered["schema"] == "sample_brain_qml_profiler_tooling_v1"
    assert "install_second_qt_sdk_for_skill" in discovered["do_not"]
    assert isinstance(discovered["decision_tree"], list)
    assert discovered["decision_tree"]


def test_helper_cli_summarize_json(tmp_path: Path) -> None:
    helper = _load_helper()
    src = FIXTURES / "scenario_a_delegate_churn.json"
    # Ensure main entry works via module API used by CLI path.
    summary = helper.summarize(json.loads(src.read_text(encoding="utf-8")), REPO_ROOT)
    report = helper.build_report_yaml_like(summary)
    assert "verdict:" in report
    assert "HOTSPOT_PROVEN" in report
