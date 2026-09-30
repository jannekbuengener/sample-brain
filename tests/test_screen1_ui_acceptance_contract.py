"""Unit/contract tests for Screen-1 UI acceptance result model."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src.screen1_ui_acceptance_contract import (
    CASE_DISPLAY_PREFERENCES,
    CASE_HARMONIC_MATCH,
    CaseResult,
    DiscoveryMethod,
    aggregate_run_result,
    evaluate_app_start_controls,
    evaluate_harmonic_open_visual,
    evaluate_harmonic_restore_visual,
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
from src.screen1_ui_acceptance_focus import foreground_owned


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


def test_evidence_dir_outside_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_app_start_requires_display_preferences_even_if_harmonic_present() -> None:
    ok, reason = evaluate_app_start_controls(["Harmonic Match", "Search"])
    assert ok is False
    assert reason == "missing_display_preferences_control"
    ok2, reason2 = evaluate_app_start_controls(["Display preferences", "Harmonic Match"])
    assert ok2 is True
    assert reason2 == "display_preferences_present"


def test_harmonic_stale_uia_without_visual_delta_is_not_pass() -> None:
    open_ok, verification, notes = evaluate_harmonic_open_visual(
        title_before=True,
        title_after=True,
        before_luma=24.5,
        after_luma=24.5,
    )
    assert open_ok is False
    assert any("stale_uia_without_visual_delta" in item for item in verification)
    assert "harmonic_matches_title_present_before_toggle" in notes
    assert "harmonic_matches_title_present_after_toggle" in notes


def test_harmonic_visual_delta_passes_even_with_sticky_title() -> None:
    open_ok, verification, _notes = evaluate_harmonic_open_visual(
        title_before=True,
        title_after=True,
        before_luma=10.0,
        after_luma=20.0,
    )
    assert open_ok is True
    assert any("harmonic_panel_visual_delta" in item for item in verification)
    assert any("evidence_only" in item for item in verification)


def test_harmonic_restore_threshold() -> None:
    assert evaluate_harmonic_restore_visual(before_luma=10.0, after_luma=20.0, restore_luma=10.2)
    assert not evaluate_harmonic_restore_visual(
        before_luma=10.0, after_luma=20.0, restore_luma=18.0
    )


def test_foreground_owned_fail_closed() -> None:
    assert foreground_owned(100, 100) is True
    assert foreground_owned(100, 200) is False
    assert foreground_owned(0, 0) is False


def test_run_acceptance_blocks_existing_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if sys.platform != "win32":
        pytest.skip("Windows-only runner")
    from src.screen1_ui_acceptance_focus import WindowInfo
    from src import screen1_ui_acceptance as runner

    monkeypatch.setenv("SAMPLE_BRAIN_UI_ACCEPTANCE_EVIDENCE_ROOT", str(tmp_path))
    fake = WindowInfo(
        hwnd=111,
        title="Sample Brain",
        pid=4242,
        left=0,
        top=0,
        right=800,
        bottom=600,
    )
    started = {"called": False}

    def _boom(**_kwargs):
        started["called"] = True
        raise AssertionError("start_qml_screen1 must not run when existing window blocks")

    monkeypatch.setattr(runner, "find_window_by_title", lambda title="Sample Brain": fake)
    monkeypatch.setattr(runner, "start_qml_screen1", _boom)
    report, code = runner.run_acceptance()
    assert code == 3
    assert report.result == CaseResult.BLOCKED.value
    assert any("existing_sample_brain_window" in note for note in report.notes)
    assert started["called"] is False


def test_pid_in_process_tree_accepts_venv_child(monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform != "win32":
        pytest.skip("Windows-only focus helpers")
    from src import screen1_ui_acceptance_focus as focus

    parents = {26768: 22968, 22968: 1000, 1000: 0}
    monkeypatch.setattr(focus, "process_parent_pid", lambda pid: parents.get(int(pid), 0))
    assert focus.pid_in_process_tree(26768, 22968) is True
    assert focus.pid_in_process_tree(22968, 22968) is True
    assert focus.pid_in_process_tree(4242, 22968) is False