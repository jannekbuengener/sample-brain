"""Screen-1 UI acceptance runner — local Windows desktop acceptance contract."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from ctypes import ArgumentError
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
    evaluate_app_start_controls,
    evaluate_harmonic_open_visual,
    evaluate_harmonic_restore_visual,
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
    pid_in_process_tree,
    require_sample_brain_foreground,
    terminate_process_tree,
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


def wait_for_window_for_pid(
    starter_pid: int,
    title: str = APP_WINDOW_TITLE,
    *,
    timeout_sec: float = 45.0,
    proc: subprocess.Popen[str] | None = None,
):
    """Wait for Sample Brain window owned by starter_pid or a descendant process."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            # Venv launcher may exit after spawning the real interpreter; only
            # fail if no matching window exists in the starter process tree.
            info = find_window_by_title(title)
            if (
                info is not None
                and info.width > 100
                and info.height > 100
                and pid_in_process_tree(info.pid, int(starter_pid))
            ):
                return info
            raise FocusGuardError(
                f"process exited before window starter_pid={starter_pid} code={proc.returncode}"
            )
        info = find_window_by_title(title)
        if (
            info is not None
            and info.width > 100
            and info.height > 100
            and pid_in_process_tree(info.pid, int(starter_pid))
        ):
            return info
        time.sleep(0.4)
    raise FocusGuardError(
        f"timed out waiting for window {title!r} owned by starter_pid={starter_pid} tree"
    )


def _focus(*, expected_pid: int, starter_pid: int | None = None):
    return require_sample_brain_foreground(
        expected_pid=expected_pid,
        starter_pid=starter_pid,
    )


def _case_from_focus_error(report: CaseReport, exc: Exception) -> CaseReport:
    message = str(exc)
    report.notes.append(f"{exc.__class__.__name__}: {message}")
    lowered = message.lower()
    if (
        "failed to foreground" in lowered
        or "foreground lost" in lowered
        or "foreground win32 overflow" in lowered
        or "overflow" in lowered
    ):
        report.result = CaseResult.BLOCKED.value
        report.verification.append("focus_guard_blocked")
    else:
        report.result = CaseResult.FAIL.value
    return report


def run_case_app_start(
    evidence_dir: Path,
    *,
    proc: subprocess.Popen[str],
    starter_pid: int,
) -> tuple[CaseReport, int]:
    from . import screen1_ui_acceptance_uia as uia

    report = CaseReport(case=CASE_APP_START, discovery=DiscoveryMethod.UIA.value)
    try:
        info = wait_for_window_for_pid(starter_pid, proc=proc)
        # Bind subsequent cases to the actual UI process (may be a venv child).
        expected_pid = int(info.pid)
        info = _focus(expected_pid=expected_pid, starter_pid=starter_pid)
        if not pid_in_process_tree(info.pid, int(starter_pid)):
            report.result = CaseResult.FAIL.value
            report.verification.append(
                f"window_pid_not_in_starter_tree actual={info.pid} starter={starter_pid}"
            )
            return report, expected_pid
        snap = evidence_dir / "case_app_start_snapshot.json"
        shot = evidence_dir / "case_app_start_screenshot.bmp"
        uia.dump_names_json(info.hwnd, snap)
        uia.capture_window_bmp(info.hwnd, shot)
        names = uia.list_interactive_names(info.hwnd)
        report.evidence.extend([str(snap), str(shot)])
        ok, reason = evaluate_app_start_controls(names)
        if not ok:
            report.result = CaseResult.FAIL.value
            report.verification.append(reason)
            report.notes.append(f"interactive_names={names[:20]}")
            return report, expected_pid
        report.verification.extend(
            [
                f"starter_pid={starter_pid}",
                f"pid={info.pid}",
                f"hwnd={info.hwnd}",
                f"size={info.width}x{info.height}",
                "window_visible",
                reason,
                "screenshot_captured",
                "foreground_confirmed",
                "process_tree_verified",
            ]
        )
        report.result = CaseResult.PASS.value
        return report, expected_pid
    except (FocusGuardError, OverflowError, ArgumentError) as exc:
        return _case_from_focus_error(report, exc), int(starter_pid)
    except Exception as exc:  # noqa: BLE001 - boundary for case isolation
        report.result = CaseResult.FAIL.value
        report.notes.append(f"{exc.__class__.__name__}: {exc}")
        return report, int(starter_pid)


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
        # Popup.CloseOnPressOutside — requires proven foreground.
        uia.click_screen(info.left + int(info.width * 0.35), info.top + int(info.height * 0.55))
        time.sleep(0.35)


def run_case_display_preferences(
    evidence_dir: Path, *, expected_pid: int, starter_pid: int
) -> CaseReport:
    from . import screen1_ui_acceptance_uia as uia

    report = CaseReport(case=CASE_DISPLAY_PREFERENCES, discovery=DiscoveryMethod.UIA.value)
    try:
        info = _focus(expected_pid=expected_pid, starter_pid=starter_pid)
        for _ in range(3):
            if not _prefs_open(info.hwnd):
                break
            _close_display_preferences(info)
            info = _focus(expected_pid=expected_pid, starter_pid=starter_pid)

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
        info = _focus(expected_pid=expected_pid, starter_pid=starter_pid)
        after_snap = evidence_dir / "case_display_preferences_after_open.json"
        after_shot = evidence_dir / "case_display_preferences_after_open.bmp"
        uia.dump_names_json(info.hwnd, after_snap)
        uia.capture_window_bmp(info.hwnd, after_shot)
        report.evidence.extend([str(after_snap), str(after_shot)])
        if not opened:
            present = [
                m for m in DISPLAY_PREFERENCES_OPEN_MARKERS if uia.element_exists(info.hwnd, m)
            ]
            report.result = CaseResult.FAIL.value
            report.verification.append(f"open_markers_missing present={present}")
            return report
        report.verification.append("preferences_open_markers_present")

        _close_display_preferences(info)
        closed = uia.wait_until(lambda: not _prefs_open(info.hwnd), timeout_sec=8.0)
        if not closed:
            _close_display_preferences(info)
            closed = uia.wait_until(lambda: not _prefs_open(info.hwnd), timeout_sec=5.0)
        info = _focus(expected_pid=expected_pid, starter_pid=starter_pid)
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
    except (FocusGuardError, OverflowError, ArgumentError) as exc:
        return _case_from_focus_error(report, exc)
    except Exception as exc:  # noqa: BLE001
        report.result = CaseResult.FAIL.value
        report.notes.append(f"{exc.__class__.__name__}: {exc}")
        return report


def run_case_harmonic_match(
    evidence_dir: Path, *, expected_pid: int, starter_pid: int
) -> CaseReport:
    from . import screen1_ui_acceptance_uia as uia

    report = CaseReport(case=CASE_HARMONIC_MATCH, discovery=DiscoveryMethod.UIA.value)
    try:
        info = _focus(expected_pid=expected_pid, starter_pid=starter_pid)
        if not uia.element_exists(info.hwnd, HARMONIC_MATCH_NAME):
            report.result = CaseResult.FAIL.value
            report.discovery = DiscoveryMethod.NOT_AVAILABLE.value
            report.verification.append("harmonic_match_button_missing")
            return report

        before_shot = evidence_dir / "case_harmonic_before.bmp"
        uia.capture_window_bmp(info.hwnd, before_shot)
        report.evidence.append(str(before_shot))

        report.discovery = DiscoveryMethod.VISUAL_FALLBACK.value
        report.notes.append(
            "sample_row_selection=VISUAL_FALLBACK (browser ListView rows absent from UIA)"
        )
        open_ok = False
        open_verification: list[str] = []
        open_notes: list[str] = []
        before_luma = 0.0
        after_luma = 0.0
        # Single visual-fallback row anchor; ListView rows are not in UIA.
        row_anchors = ((0.55, 0.30),)
        try:
            for idx, (xr, yr) in enumerate(row_anchors):
                info = _focus(expected_pid=expected_pid, starter_pid=starter_pid)
                uia.click_screen(
                    info.left + int(info.width * xr),
                    info.top + int(info.height * yr),
                )
                time.sleep(0.45)
                info = _focus(expected_pid=expected_pid, starter_pid=starter_pid)
                title_before = uia.element_exists(info.hwnd, "Harmonic Matches")
                before_shot_toggle = evidence_dir / f"case_harmonic_before_toggle_{idx}.bmp"
                uia.capture_window_bmp(info.hwnd, before_shot_toggle)
                before_luma = uia.region_mean_luma(
                    before_shot_toggle, x_ratio0=0.70, x_ratio1=0.99
                )
                report.evidence.append(str(before_shot_toggle))

                uia.invoke_by_name(info.hwnd, HARMONIC_MATCH_NAME)
                time.sleep(1.0)
                info = _focus(expected_pid=expected_pid, starter_pid=starter_pid)
                after_shot = evidence_dir / f"case_harmonic_after_open_{idx}.bmp"
                uia.capture_window_bmp(info.hwnd, after_shot)
                after_luma = uia.region_mean_luma(after_shot, x_ratio0=0.70, x_ratio1=0.99)
                report.evidence.append(str(after_shot))
                title_after = uia.element_exists(info.hwnd, "Harmonic Matches")
                open_ok, open_verification, open_notes = evaluate_harmonic_open_visual(
                    title_before=title_before,
                    title_after=title_after,
                    before_luma=before_luma,
                    after_luma=after_luma,
                )
                if open_ok:
                    report.notes.append(f"sample_row_anchor_index={idx}")
                    break
                uia.invoke_by_name(info.hwnd, HARMONIC_MATCH_NAME)
                time.sleep(0.4)
        except (FocusGuardError, OverflowError, ArgumentError) as exc:
            # Visual-fallback probing can hit host z-order/input races; do not
            # convert a missing visual proof into a false FAIL/PASS.
            report.notes.append(f"visual_probe_interrupted: {exc.__class__.__name__}: {exc}")
            if not open_verification:
                open_verification = ["harmonic_open_visual_probe_interrupted"]
            open_ok = False

        report.verification.extend(open_verification)
        report.notes.extend(open_notes)
        if not open_ok:
            report.result = CaseResult.PARTIAL.value
            return report

        restore_shot = evidence_dir / "case_harmonic_after_restore.bmp"
        restore_luma = after_luma
        visual_closed = False
        for _ in range(3):
            uia.invoke_by_name(info.hwnd, HARMONIC_MATCH_NAME)
            time.sleep(0.7)
            info = _focus(expected_pid=expected_pid, starter_pid=starter_pid)
            uia.capture_window_bmp(info.hwnd, restore_shot)
            restore_luma = uia.region_mean_luma(restore_shot, x_ratio0=0.70, x_ratio1=0.99)
            visual_closed = evaluate_harmonic_restore_visual(
                before_luma=before_luma,
                after_luma=after_luma,
                restore_luma=restore_luma,
            )
            if visual_closed:
                break
        if str(restore_shot) not in report.evidence:
            report.evidence.append(str(restore_shot))
        if uia.element_exists(info.hwnd, "Harmonic Matches"):
            report.notes.append(
                "harmonic_matches_title_still_in_uia_after_close (known QML opacity/a11y gap)"
            )
        if not visual_closed:
            report.result = CaseResult.PARTIAL.value
            report.verification.append(
                "harmonic_restore_visual_uncertain "
                f"before={before_luma:.2f} after={after_luma:.2f} restore={restore_luma:.2f}"
            )
            return report
        report.verification.append("harmonic_restore_visual_ok")
        report.result = CaseResult.PASS.value
        return report
    except (FocusGuardError, OverflowError, ArgumentError) as exc:
        return _case_from_focus_error(report, exc)
    except Exception as exc:  # noqa: BLE001
        report.result = CaseResult.FAIL.value
        report.notes.append(f"{exc.__class__.__name__}: {exc}")
        return report


def run_acceptance(
    *, keep_app: bool = False, allow_reuse: bool = False
) -> tuple[RunReport, int]:
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

    existing = find_window_by_title(APP_WINDOW_TITLE)
    run.phases.append(RunPhase.START_APP.value)
    if existing is not None and not allow_reuse:
        run.result = CaseResult.BLOCKED.value
        run.notes.append(
            "existing_sample_brain_window "
            f"hwnd={existing.hwnd} pid={existing.pid}; "
            "close it or pass --allow-reuse (debug only)"
        )
        run.phases.append(RunPhase.FINAL_RESULT.value)
        write_json(evidence_dir / "run.json", run.to_dict())
        return run, exit_code_for(CaseResult.BLOCKED)

    proc: subprocess.Popen[str] | None = None
    started_here = False
    starter_pid: int
    expected_pid: int
    if allow_reuse and existing is not None:
        starter_pid = int(existing.pid)
        expected_pid = int(existing.pid)
        run.notes.append(
            f"allow_reuse_existing_hwnd={existing.hwnd} pid={expected_pid} (debug opt-in)"
        )

        class _Alive:
            def poll(self):
                return None

            @property
            def pid(self):
                return starter_pid

        proc = _Alive()  # type: ignore[assignment]
    else:
        proc = start_qml_screen1()
        started_here = True
        starter_pid = int(proc.pid)
        expected_pid = starter_pid
        run.notes.append(f"started_pid={starter_pid}")

    case_reports: list[CaseReport] = []
    try:
        run.phases.append(RunPhase.FOCUS_APP.value)
        run.phases.append(RunPhase.SNAPSHOT_INITIAL.value)
        run.phases.append(RunPhase.RUN_CASES.value)
        app_report, expected_pid = run_case_app_start(
            evidence_dir, proc=proc, starter_pid=starter_pid
        )
        case_reports.append(app_report)
        if CaseResult(app_report.result) is CaseResult.PASS:
            case_reports.append(
                run_case_display_preferences(
                    evidence_dir, expected_pid=expected_pid, starter_pid=starter_pid
                )
            )
            case_reports.append(
                run_case_harmonic_match(
                    evidence_dir, expected_pid=expected_pid, starter_pid=starter_pid
                )
            )
        else:
            run.notes.append("skipped_remaining_cases_after_app_start_non_pass")
        run.phases.append(RunPhase.RESTORE.value)
        run.phases.append(RunPhase.CAPTURE_EVIDENCE.value)
    finally:
        for case in case_reports:
            write_json(evidence_dir / f"{case.case}.json", case.to_dict())
        if started_here and not keep_app:
            terminate_process_tree(starter_pid)
            if proc is not None and hasattr(proc, "poll") and proc.poll() is None:
                try:
                    proc.wait(timeout=3)
                except Exception:  # noqa: BLE001
                    pass

    results = [CaseResult(c.result) for c in case_reports]
    overall = aggregate_run_result(results)
    run.result = overall.value
    run.cases = [c.to_dict() for c in case_reports]
    run.phases.append(RunPhase.FINAL_RESULT.value)
    write_json(evidence_dir / "run.json", run.to_dict())
    return run, exit_code_for(overall)
