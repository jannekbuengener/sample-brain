"""Unit/contract tests for Screen-1 UI acceptance result model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.screen1_ui_acceptance_contract import (
    CASE_DISPLAY_PREFERENCES,
    CASE_HARMONIC_MATCH,
    CaseResult,
    DiscoveryMethod,
    aggregate_run_result,
    exit_code_for,
    parse_case_result,
    parse_discovery,
    validate_case_report_dict,
)
from src.screen1_ui_acceptance_evidence import (
    assert_outside_repo,
    create_run_dir,
    default_evidence_root,
    new_run_id,
)


def test_aggregate_fail_closed_precedence() -> None:
    assert (
        aggregate_run_result([CaseResult.PASS, CaseResult.PARTIAL, CaseResult.FAIL])
        is CaseResult.FAIL
    )
    assert aggregate_run_result([CaseResult.PASS, CaseResult.BLOCKED]) is CaseResult.BLOCKED
    assert aggregate_run_result([CaseResult.PASS, CaseResult.PARTIAL]) is CaseResult.PARTIAL
    assert aggregate_run_result([CaseResult.PASS, CaseResult.PASS]) is CaseResult.PASS
    assert aggregate_run_result([]) is CaseResult.BLOCKED


def test_exit_codes() -> None:
    assert exit_code_for(CaseResult.PASS) == 0
    assert exit_code_for(CaseResult.FAIL) == 1
    assert exit_code_for(CaseResult.PARTIAL) == 2
    assert exit_code_for(CaseResult.BLOCKED) == 3


def test_parse_helpers() -> None:
    assert parse_case_result("PASS") is CaseResult.PASS
    assert parse_discovery("visual_fallback") is DiscoveryMethod.VISUAL_FALLBACK
    with pytest.raises(ValueError):
        parse_case_result("maybe")
    with pytest.raises(ValueError):
        parse_discovery("magic")


def test_validate_display_preferences_requires_uia_for_pass() -> None:
    payload = {
        "schema_version": 1,
        "case": CASE_DISPLAY_PREFERENCES,
        "result": "pass",
        "discovery": "visual_fallback",
        "verification": ["x"],
        "evidence": ["y"],
    }
    errors = validate_case_report_dict(payload)
    assert any("discovery=uia" in e for e in errors)


def test_validate_harmonic_allows_visual_fallback_pass() -> None:
    payload = {
        "schema_version": 1,
        "case": CASE_HARMONIC_MATCH,
        "result": "pass",
        "discovery": "visual_fallback",
        "verification": ["open"],
        "evidence": ["shot.bmp"],
    }
    assert validate_case_report_dict(payload) == []


def test_evidence_dir_outside_repo(tmp_path: Path, monkeypatch: pytest.Monkeypatch) -> None:
    root = tmp_path / "ui-acceptance"
    monkeypatch.setenv("SAMPLE_BRAIN_UI_ACCEPTANCE_EVIDENCE_ROOT", str(root))
    assert default_evidence_root() == root.resolve()
    run_dir = create_run_dir("screen1-test", root=root)
    assert run_dir.is_dir()
    repo = tmp_path / "repo"
    repo.mkdir()
    assert_outside_repo(run_dir, repo)
    inside = repo / "leak"
    inside.mkdir()
    with pytest.raises(ValueError):
        assert_outside_repo(inside, repo)


def test_run_id_format() -> None:
    rid = new_run_id()
    assert rid.startswith("screen1-")
    assert "T" in rid


def test_case_report_roundtrip_json(tmp_path: Path) -> None:
    from src.screen1_ui_acceptance_contract import CaseReport
    from src.screen1_ui_acceptance_evidence import write_json

    report = CaseReport(
        case=CASE_DISPLAY_PREFERENCES,
        result=CaseResult.PASS.value,
        discovery=DiscoveryMethod.UIA.value,
        verification=["preferences_open_markers_present"],
        evidence=["a.bmp"],
    )
    path = write_json(tmp_path / "display_preferences.json", report.to_dict())
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert validate_case_report_dict(loaded) == []
