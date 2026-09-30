"""Screen-1 UI acceptance runner — local Windows desktop acceptance contract."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from .screen1_ui_acceptance_contract import (
    ACCESSIBILITY_FOLLOWUPS_V1,
    APP_WINDOW_TITLE,
    CASE_APP_START,
    CASE_DISPLAY_PREFERENCES,
    CASE_HARMONIC_MATCH,
    DISPLAY_PREFERENCES_NAME,
    DISPLAY_PREFERENCES_OPEN_MARKERS,
    HARMONIC_MATCH_NAME,
    CaseReport,
    CaseResult,
    DiscoveryMethod,
    RunPhase,
    RunReport,
    aggregate_run_result,
    exit_code_for,
)
from .screen1_ui_acceptance_evidence import (
    assert_outside_repo,
    create_run_dir,
    write_json,
)
from .screen1_ui_acceptance_focus import (
    FocusGuardError,
    find_window_by_title,
    require_sample_brain_foreground,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _python_exe() -> Path:
    override = os.environ.get("SAMPLE_BRAIN_PYTHON", "").strip()
    if override:
        return Path(override)
    local = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if local.is_file():
        return local
    return Path(sys.executable)


def start_qml_screen1(*, cwd: Path | None = None) -> subprocess.Popen[str]:
    py = _python_exe()
    workdir = cwd or REPO_ROOT
    return subprocess.Popen(
        [str(py), "-m", "src.cli", "workbench", "--qml-screen1"],
        cwd=str(workdir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def wait_for_window(title: str = APP_WINDOW_TITLE, *, timeout_sec: float = 45.0):
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        info = find_window_by_title(title)
        if info is not None and info.width > 100 and info.height > 100:
            return info
        time.sleep(0.4)
    raise FocusGuardError(f"timed out waiting for window {title!r}")


def _focus(title: str = APP_WINDOW_TITLE):
    return require_sample_brain_foreground(title)


def run_case_app_start(evidence_dir: Path, *, proc: subprocess.Popen[str]) -> CaseReport:
    from . import screen1_ui_acceptance_uia as uia

    report = CaseReport(case=CASE_APP_START, discovery=DiscoveryMethod.UIA.value)
    try:
        if proc.poll() is not None:
            report.result = CaseResult.FAIL.value
            report.verification.append("process_exited_before_window")
            return report
        info = wait_for_window()
        info = _focus()
        snap = evidence_dir / "case_app_start_snapshot.json"
        shot = evidence_dir / "case_app_start_screenshot.bmp"
        uia.dump_names_json(info.hwnd, snap)
        uia.capture_window_bmp(info.hwnd, shot)
        names = uia.list_interactive_names(info.hwnd)
        report.evidence.extend([str(snap), str(shot)])
        if DISPLAY_PREFERENCES_NAME not in names and HARMONIC_MATCH_NAME not in names:
            # Clean-start may hide harmonic until source active; Display preferences should exist on screen1.
            if DISPLAY_PREFERENCES_NAME not in names:
                report.result = CaseResult.FAIL.value
                report.verification.append("missing_display_preferences_control")
                report.notes.append(f"interactive_names={names[:20]}")
                return report
        report.verification.extend(
            [
                f"pid={info.pid}",
                f"hwnd={info.hwnd}",
                f"size={info.width}x{info.height}",
                "window_visible",
                "screenshot_captured",
            ]
        )
        report.result = CaseResult.PASS.value
        return report
    except Exception as exc:  # noqa: BLE001 - boundary for case isolation
        report.result = CaseResult.FAIL.value
        report.notes.append(str(exc))
        return report


def _prefs_open(hwnd: int) -> bool:
    from . import screen1_ui_acceptance_uia as uia

    # Require the distinctive overflow actions — not short labels like "On".
    return all(
        uia.element_exists(hwnd, marker)
        for marker in (
            "Reset Layout",
            "Save Workspace Preset",
            "Density",
            "Motion",
        )
    )


def _close_display_preferences(info) -> None:
    from . import screen1_ui_acceptance_uia as uia

    uia.send_escape()
    time.sleep(0.25)
    if _prefs_open(info.hwnd):
        # Popup.CloseOnPressOutside
        uia.click_screen(info.left + int(info.width * 0.35), info.top + int(info.height * 0.55))
        time.sleep(0.35)


def run_case_display_preferences(evidence_dir: Path) -> CaseReport:
    from . import screen1_ui_acceptance_uia as uia

    report = CaseReport(case=CASE_DISPLAY_PREFERENCES, discovery=DiscoveryMethod.UIA.value)
    try:
        info = _focus()
        # Normalize: previous runs may leave the overflow popup open.
        for _ in range(3):
            if not _prefs_open(info.hwnd):
                break
            _close_display_preferences(info)
            info = _focus()

        before_snap = evidence_dir / "case_display_preferences_before.json"
        before_shot = evidence_dir / "case_display_preferences_before.bmp"
        uia.dump_names_json(info.hwnd, before_snap)
        uia.capture_window_bmp(info.hwnd, before_shot)
        report.evidence.extend([str(before_snap), str(before_shot)])

        if not uia.element_exists(info.hwnd, DISPLAY_PREFERENCES_NAME):
            report.result = CaseResult.FAIL.value
            report.verification.append("display_preferences_not_found")
            return report
        if _prefs_open(info.hwnd):
            report.result = CaseResult.FAIL.value
            report.verification.append("preferences_still_open_before_case")
            return report

        uia.invoke_by_name(info.hwnd, DISPLAY_PREFERENCES_NAME)
        opened = uia.wait_until(lambda: _prefs_open(info.hwnd), timeout_sec=8.0)
        info = _focus()
        after_snap = evidence_dir / "case_display_preferences_after_open.json"
        after_shot = evidence_dir / "case_display_preferences_after_open.bmp"
        uia.dump_names_json(info.hwnd, after_snap)
        uia.capture_window_bmp(info.hwnd, after_shot)
        report.evidence.extend([str(after_snap), str(after_shot)])
        if not opened:
            present = [m for m in DISPLAY_PREFERENCES_OPEN_MARKERS if uia.element_exists(info.hwnd, m)]
            report.result = CaseResult.FAIL.value
            report.verification.append(f"open_markers_missing present={present}")
            return report
        report.verification.append("preferences_open_markers_present")

        _close_display_preferences(info)
        closed = uia.wait_until(lambda: not _prefs_open(info.hwnd), timeout_sec=8.0)
        if not closed:
            _close_display_preferences(info)
            closed = uia.wait_until(lambda: not _prefs_open(info.hwnd), timeout_sec=5.0)
        info = _focus()
        restore_snap = evidence_dir / "case_display_preferences_after_restore.json"
        restore_shot = evidence_dir / "case_display_preferences_after_restore.bmp"
        uia.dump_names_json(info.hwnd, restore_snap)
        uia.capture_window_bmp(info.hwnd, restore_shot)
        report.evidence.extend([str(restore_snap), str(restore_shot)])
        if not closed:
            report.result = CaseResult.FAIL.value
            report.verification.append("preferences_not_closed_after_esc")
            return report
        report.verification.append("preferences_closed_after_esc")
        report.result = CaseResult.PASS.value
        return report
    except Exception as exc:  # noqa: BLE001
        report.result = CaseResult.FAIL.value
        report.notes.append(str(exc))
        return report


def run_case_harmonic_match(evidence_dir: Path) -> CaseReport:
    from . import screen1_ui_acceptance_uia as uia

    report = CaseReport(case=CASE_HARMONIC_MATCH, discovery=DiscoveryMethod.UIA.value)
    try:
        info = _focus()
        if not uia.element_exists(info.hwnd, HARMONIC_MATCH_NAME):
            report.result = CaseResult.FAIL.value
            report.discovery = DiscoveryMethod.NOT_AVAILABLE.value
            report.verification.append("harmonic_match_button_missing")
            return report

        before_shot = evidence_dir / "case_harmonic_before.bmp"
        uia.capture_window_bmp(info.hwnd, before_shot)
        before_luma = uia.region_mean_luma(before_shot, x_ratio0=0.72, x_ratio1=0.98)
        report.evidence.append(str(before_shot))

        # ListView rows are not in UIA — required sample selection marked VISUAL_FALLBACK.
        report.discovery = DiscoveryMethod.VISUAL_FALLBACK.value
        report.notes.append(
            "sample_row_selection=VISUAL_FALLBACK (browser ListView rows absent from UIA)"
        )
        # Click approximate first browser row area inside the Sample Brain window.
        row_x = info.left + int(info.width * 0.55)
        row_y = info.top + int(info.height * 0.28)
        uia.click_screen(row_x, row_y)
        time.sleep(0.4)
        info = _focus()

        # Button itself is UIA-addressable.
        uia.invoke_by_name(info.hwnd, HARMONIC_MATCH_NAME)
        time.sleep(0.8)
        info = _focus()
        after_shot = evidence_dir / "case_harmonic_after_open.bmp"
        uia.capture_window_bmp(info.hwnd, after_shot)
        after_luma = uia.region_mean_luma(after_shot, x_ratio0=0.72, x_ratio1=0.98)
        report.evidence.append(str(after_shot))

        uia_open = uia.element_exists(info.hwnd, "Harmonic Matches")
        visual_open = abs(after_luma - before_luma) >= 1.5
        if uia_open:
            report.verification.append("harmonic_panel_title_uia")
            # Promote discovery note: button UIA + panel title UIA, but selection was fallback.
            report.notes.append("panel_title_discovered=uia")
        elif visual_open:
            report.verification.append(
                f"harmonic_panel_visual_delta luma_before={before_luma:.2f} luma_after={after_luma:.2f}"
            )
        else:
            report.result = CaseResult.FAIL.value
            report.verification.append("harmonic_open_not_verified")
            return report

        # Close: toggle until visual restore or retries exhausted.
        for _ in range(3):
            uia.invoke_by_name(info.hwnd, HARMONIC_MATCH_NAME)
            time.sleep(0.7)
            info = _focus()
            restore_shot = evidence_dir / "case_harmonic_after_restore.bmp"
            uia.capture_window_bmp(info.hwnd, restore_shot)
            restore_luma = uia.region_mean_luma(restore_shot, x_ratio0=0.72, x_ratio1=0.98)
            visual_closed = abs(restore_luma - before_luma) <= max(
                0.75, abs(after_luma - before_luma) * 0.45
            )
            if visual_closed:
                break
        else:
            visual_closed = False
        if str(restore_shot) not in report.evidence:
            report.evidence.append(str(restore_shot))
        uia_title_still_present = uia.element_exists(info.hwnd, "Harmonic Matches")
        if uia_title_still_present:
            report.notes.append(
                "harmonic_matches_title_still_in_uia_after_close (known QML opacity/a11y gap)"
            )
        if not visual_closed:
            report.result = CaseResult.PARTIAL.value
            report.verification.append(
                f"harmonic_restore_visual_uncertain before={before_luma:.2f} after={after_luma:.2f} restore={restore_luma:.2f}"
            )
            return report
        report.verification.append("harmonic_restore_visual_ok")
        report.result = CaseResult.PASS.value
        return report
    except Exception as exc:  # noqa: BLE001
        report.result = CaseResult.FAIL.value
        report.notes.append(str(exc))
        return report


def run_acceptance(*, keep_app: bool = False) -> tuple[RunReport, int]:
    if sys.platform != "win32":
        report = RunReport(result=CaseResult.BLOCKED.value, notes=["requires Windows host"])
        return report, exit_code_for(CaseResult.BLOCKED)

    evidence_dir = create_run_dir()
    assert_outside_repo(evidence_dir, REPO_ROOT)
    run = RunReport(
        run_id=evidence_dir.name,
        evidence_dir=str(evidence_dir),
        accessibility_followups=list(ACCESSIBILITY_FOLLOWUPS_V1),
    )
    run.phases.append(RunPhase.PRECHECK.value)

    # Prefer attaching to an already-running Sample Brain if present.
    proc: subprocess.Popen[str] | None = None
    started_here = False
    existing = find_window_by_title(APP_WINDOW_TITLE)
    run.phases.append(RunPhase.START_APP.value)
    if existing is None:
        proc = start_qml_screen1()
        started_here = True
        run.notes.append(f"started_pid={proc.pid}")
    else:
        run.notes.append(f"reused_existing_hwnd={existing.hwnd}")

    case_reports: list[CaseReport] = []
    try:
        run.phases.append(RunPhase.FOCUS_APP.value)
        run.phases.append(RunPhase.SNAPSHOT_INITIAL.value)
        run.phases.append(RunPhase.RUN_CASES.value)
        if proc is None:

            class _Alive:
                def poll(self):
                    return None

            case_reports.append(run_case_app_start(evidence_dir, proc=_Alive()))  # type: ignore[arg-type]
        else:
            case_reports.append(run_case_app_start(evidence_dir, proc=proc))
        case_reports.append(run_case_display_preferences(evidence_dir))
        case_reports.append(run_case_harmonic_match(evidence_dir))
        run.phases.append(RunPhase.RESTORE.value)
        run.phases.append(RunPhase.CAPTURE_EVIDENCE.value)
    finally:
        for case in case_reports:
            write_json(evidence_dir / f"{case.case}.json", case.to_dict())
        if started_here and proc is not None and not keep_app:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    results = [CaseResult(c.result) for c in case_reports]
    overall = aggregate_run_result(results)
    run.result = overall.value
    run.cases = [c.to_dict() for c in case_reports]
    run.phases.append(RunPhase.FINAL_RESULT.value)
    write_json(evidence_dir / "run.json", run.to_dict())
    return run, exit_code_for(overall)
