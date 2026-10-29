from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "docs"
    / "skills"
    / "sample-brain-skill-effectiveness"
    / "scripts"
    / "evaluate_result.py"
)


def _load_mod():
    spec = importlib.util.spec_from_file_location("evaluate_result", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["evaluate_result"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ev():
    return _load_mod()


def _effective_payload() -> dict:
    return {
        "target_skill": "demo-skill",
        "target_revision": "abc123",
        "skill_type": "discipline",
        "scenario_id": "demo",
        "inputs_comparable": True,
        "structural_only": False,
        "baseline": {
            "ran": True,
            "outcome": "fail",
            "failure_category": "order_violation",
            "notes": "skipped gates",
        },
        "skill_enabled": {
            "ran": True,
            "skill_loaded": True,
            "outcome": "pass",
            "notes": "followed gates",
        },
        "delta": {
            "improved": True,
            "material_change": True,
            "summary": "order restored",
        },
        "activation": {"positive": "used", "negative": "correctly_idle"},
        "transfer": {
            "variants_passed": 1,
            "counterexamples_passed": 1,
            "overconstraint": False,
        },
        "verdict": "EFFECTIVE",
    }


def test_parse_simple_yaml_nested(ev) -> None:
    text = """
target_skill: demo
baseline:
  ran: true
  outcome: fail
skill_enabled:
  ran: true
  skill_loaded: true
"""
    data = ev.parse_simple_yaml(text)
    assert data["target_skill"] == "demo"
    assert data["baseline"]["ran"] is True
    assert data["skill_enabled"]["skill_loaded"] is True


def test_missing_baseline_rejects_effective(ev) -> None:
    data = _effective_payload()
    data["baseline"] = {"ran": False, "outcome": "not_run"}
    finalized = ev.finalize_result(data)
    assert finalized["verdict"] == "INCOMPLETE"
    assert finalized["incomplete_reason"] == "missing_baseline"


def test_inequivalent_inputs_reject(ev) -> None:
    data = _effective_payload()
    data["inputs_comparable"] = False
    finalized = ev.finalize_result(data)
    assert finalized["verdict"] == "INCOMPLETE"
    assert finalized["incomplete_reason"] == "inequivalent_inputs"


def test_structural_only_reject(ev) -> None:
    data = _effective_payload()
    data["structural_only"] = True
    finalized = ev.finalize_result(data)
    assert finalized["verdict"] == "INCOMPLETE"
    assert finalized["incomplete_reason"] == "structural_only"


def test_skill_not_loaded_reject(ev) -> None:
    data = _effective_payload()
    data["skill_enabled"]["skill_loaded"] = False
    finalized = ev.finalize_result(data)
    assert finalized["verdict"] == "INCOMPLETE"
    assert finalized["incomplete_reason"] == "skill_not_loaded"


def test_compute_effective(ev) -> None:
    assert ev.compute_verdict(_effective_payload()) == "EFFECTIVE"


def test_compute_ineffective_when_still_failing(ev) -> None:
    data = _effective_payload()
    data["skill_enabled"]["outcome"] = "fail"
    data["delta"] = {
        "improved": False,
        "material_change": False,
        "summary": "no change",
    }
    data["verdict"] = "INEFFECTIVE"
    assert ev.compute_verdict(data) == "INEFFECTIVE"


def test_compute_unnecessary_when_baseline_already_pass(ev) -> None:
    data = _effective_payload()
    data["baseline"]["outcome"] = "pass"
    data["baseline"]["failure_category"] = None
    data["delta"] = {
        "improved": False,
        "material_change": False,
        "summary": "already compliant",
    }
    data["verdict"] = "UNNECESSARY"
    assert ev.compute_verdict(data) == "UNNECESSARY"


def test_incomplete_not_forced_to_ineffective(ev) -> None:
    data = _effective_payload()
    del data["baseline"]
    finalized = ev.finalize_result(data)
    assert finalized["verdict"] == "INCOMPLETE"
    assert finalized["verdict"] != "INEFFECTIVE"


def test_validate_rejects_confidence(ev) -> None:
    data = _effective_payload()
    data["confidence"] = 0.9
    problems = ev.validate_result(data)
    assert any("confidence" in p for p in problems)


def test_activation_markers_helper(ev) -> None:
    scored = ev.score_activation_markers(
        "Follow DOCS -> TESTS then TEST_FREEZE before code",
        positive_markers=["TEST_FREEZE", "DOCS -> TESTS"],
        negative_markers=["skip all gates"],
    )
    assert scored["activated"] is True
    assert "TEST_FREEZE" in scored["positive_hits"]
    assert scored["overconstraint_signal"] is False


def test_scenario_files_parse(ev) -> None:
    scenarios = (
        ROOT
        / "docs"
        / "skills"
        / "sample-brain-skill-effectiveness"
        / "scenarios"
    )
    for path in sorted(scenarios.glob("*.yml")):
        data = ev.load_result(path)
        assert "scenario_id" in data
        assert "skill_type" in data
        assert data["skill_type"] in ev.SKILL_TYPES


def test_evidence_results_validate_and_match_computed(ev) -> None:
    evidence_root = (
        ROOT
        / "docs"
        / "skills"
        / "sample-brain-skill-effectiveness"
        / "evidence"
    )
    for path in sorted(evidence_root.glob("*/RESULT.yml")):
        data = ev.load_result(path)
        problems = ev.validate_result(data)
        assert problems == [], (path, problems)
        assert data["verdict"] == ev.compute_verdict(data)
