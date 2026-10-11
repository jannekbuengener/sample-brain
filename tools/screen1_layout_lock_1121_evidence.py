"""Exact-HEAD QML runtime evidence for #1121 Layout Lock UX.

Evidence is written outside the repository. Synthetic fixture paths only.
Captures Feature OFF, Feature ON + LOCKED, Feature ON + UNLOCKED, RE-LOCKED.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def _git_head(runtime_root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(runtime_root), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def _ensure_runtime_manifest(runtime_root: Path, python_exe: Path) -> None:
    from src.runtime_provenance import (
        MANIFEST_SCHEMA,
        RuntimeManifest,
        evaluate_runtime,
        write_runtime_manifest,
    )

    report = evaluate_runtime(runtime_root, executable=python_exe)
    if report.status.value == "valid":
        return
    dirty = subprocess.check_output(
        ["git", "-C", str(runtime_root), "status", "--porcelain"],
        text=True,
    ).strip()
    if dirty:
        raise SystemExit(
            "worktree is dirty; commit before writing runtime manifest / capturing evidence"
        )
    branch = subprocess.check_output(
        ["git", "-C", str(runtime_root), "branch", "--show-current"],
        text=True,
    ).strip() or "detached"
    write_runtime_manifest(
        runtime_root,
        RuntimeManifest(
            schema=MANIFEST_SCHEMA,
            channel=branch,
            commit=_git_head(runtime_root),
            runtime_root=str(runtime_root.resolve()),
            python_executable=str(python_exe.resolve()),
            installed_at=datetime.now(UTC).isoformat(),
        ),
    )


def _framebuffer_matches_scale(
    actual_w: int,
    actual_h: int,
    *,
    scale_factor: float,
    device_pixel_ratio: float,
    logical_width: int,
    logical_height: int,
) -> bool:
    if scale_factor <= 0 or device_pixel_ratio <= 0:
        return False
    if abs(device_pixel_ratio - scale_factor) > 0.05:
        return False
    if logical_width <= 0 or logical_height <= 0:
        return False
    expected_w = int(round(logical_width * device_pixel_ratio))
    expected_h = int(round(logical_height * device_pixel_ratio))
    tol = max(2, int(round(device_pixel_ratio)))
    return abs(actual_w - expected_w) <= tol and abs(actual_h - expected_h) <= tol


def main() -> int:
    parser = argparse.ArgumentParser(description="#1121 Layout Lock UX visual evidence")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, default=Path.cwd())
    parser.add_argument("--scale-factor", type=float, default=1.0)
    args = parser.parse_args()

    evidence_dir = args.evidence_dir.resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    runtime_root = args.runtime_root.resolve()
    if evidence_dir.is_relative_to(runtime_root):
        print("evidence-dir must be outside the repository", file=sys.stderr)
        return 2
    scale_factor = float(args.scale_factor)
    if scale_factor <= 0:
        print("scale-factor must be > 0", file=sys.stderr)
        return 2
    os.environ["QT_SCALE_FACTOR"] = str(scale_factor)
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

    from src.workbench_controller import WorkbenchRow
    from src.workbench_feature_settings import WorkbenchFeatureSettings, save_workbench_feature_settings
    from src.workbench_live_kit import LiveKitPresentationState, LiveKitState
    from src.workbench_qml import (
        LiveKitPresenter,
        Screen1QmlInteractionAdapter,
        Screen1QmlViewModel,
    )
    from src.workbench_qml_spike import (
        CLIENT_HEIGHT,
        CLIENT_WIDTH,
        _grab_qml_window_png,
        _qml_engine,
        _require_fresh_qml_capture_process,
        _settle_qml_frame,
        _wait_for_screen1_background_ready,
        apply_screen1_visual_state_v2,
        build_qml_view_model_from_fixture_v2,
        validate_capture_sanity,
        validate_qml_renderer_provenance,
    )
    from src.workbench_visual_acceptance import (
        build_screen1_visual_fixture_v2,
        resolve_screen1_visual_state_v2,
    )

    _require_fresh_qml_capture_process()
    _ensure_runtime_manifest(runtime_root, Path(sys.executable))
    report = validate_qml_renderer_provenance(runtime_root)

    # Build the standard visual fixture
    fixture = build_screen1_visual_fixture_v2()
    state = resolve_screen1_visual_state_v2(fixture, "screen1-active-source")
    view_model = build_qml_view_model_from_fixture_v2(fixture, "screen1-active-source")

    # Create adapter and LiveKit presenter
    presenter = LiveKitPresenter()
    view_model.live_kit_groups = presenter.groups
    adapter = Screen1QmlInteractionAdapter(view_model=view_model, live_kit=presenter)

    # Apply the visual state (materialization, etc.)
    apply_screen1_visual_state_v2(view_model, adapter, fixture, state)

    # Ensure we have an active source with live_kit_materialized=True for the preferences popover
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=True,
    )
    view_model.set_library_revealed(True)

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.setWidth(CLIENT_WIDTH)
    window.setHeight(CLIENT_HEIGHT)
    window.show()
    _settle_qml_frame(app)
    _wait_for_screen1_background_ready(window, app)

    def refresh() -> None:
        bridge = getattr(engine, "_screen1_interaction_bridge", None)
        if bridge is not None:
            bridge.refreshState()
        _settle_qml_frame(app)

    captures: dict[str, str] = {}
    failed_checks: list[str] = []

    def grab(label: str, note: str) -> None:
        import struct

        path = evidence_dir / f"{label}.png"
        _grab_qml_window_png(window, path, engine=engine)
        raw = path.read_bytes()
        actual_w, actual_h = struct.unpack(">II", raw[16:24])
        dpr = float(window.devicePixelRatio())
        logical_w = int(window.width())
        logical_h = int(window.height())
        expected_w = int(round(logical_w * dpr))
        expected_h = int(round(logical_h * dpr))
        check = validate_capture_sanity(
            path, expected_width=actual_w, expected_height=actual_h
        )
        scale_ok = _framebuffer_matches_scale(
            actual_w,
            actual_h,
            scale_factor=scale_factor,
            device_pixel_ratio=dpr,
            logical_width=logical_w,
            logical_height=logical_h,
        )
        usable = actual_w >= 640 and actual_h >= 480
        check["note"] = note
        check["scale_factor"] = scale_factor
        check["qt_scale_factor"] = os.environ.get("QT_SCALE_FACTOR")
        check["device_pixel_ratio"] = dpr
        check["logical_width"] = logical_w
        check["logical_height"] = logical_h
        check["actual_width"] = actual_w
        check["actual_height"] = actual_h
        check["expected_width"] = expected_w
        check["expected_height"] = expected_h
        check["scale_framebuffer_match"] = scale_ok
        check["usable_framebuffer"] = usable
        check["pass"] = bool(check.get("pass")) and usable and scale_ok
        captures[label] = str(path)
        (evidence_dir / f"{label}.json").write_text(
            json.dumps(check, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if not check.get("pass"):
            failed_checks.append(label)

    # ================================================================
    # STATE 1: Feature OFF (workspace_panel_docking_enabled = false)
    # ================================================================
    # Create a temp dir for feature settings
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        # Save feature settings with docking DISABLED
        save_workbench_feature_settings(
            WorkbenchFeatureSettings(workspace_panel_docking_enabled=False),
            state_dir=tmp_path,
        )
        # Save lock state as UNLOCKED (should be ignored when feature OFF)
        from src.workbench_edit_docking import EditDockingState, LOCK_UNLOCKED, save_edit_docking_state
        save_edit_docking_state(
            EditDockingState(lock_state=LOCK_UNLOCKED),
            state_dir=tmp_path,
        )
        # Reload adapter state
        adapter.load_feature_settings(state_dir=tmp_path)
        adapter.load_workspace_layout_state(state_dir=tmp_path)
        refresh()

        grab(
            "1121-feature-off",
            "Feature OFF: workspace_panel_docking_enabled=false. Layout lock control should be disabled/opacity-reduced, not interactive. No docking affordance visible.",
        )

    # ================================================================
    # STATE 2: Feature ON + LOCKED (default)
    # ================================================================
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        save_workbench_feature_settings(
            WorkbenchFeatureSettings(workspace_panel_docking_enabled=True),
            state_dir=tmp_path,
        )
        from src.workbench_edit_docking import EditDockingState, LOCK_LOCKED, save_edit_docking_state
        save_edit_docking_state(
            EditDockingState(lock_state=LOCK_LOCKED),
            state_dir=tmp_path,
        )
        adapter.load_feature_settings(state_dir=tmp_path)
        adapter.load_workspace_layout_state(state_dir=tmp_path)
        refresh()

        grab(
            "1121-locked",
            "Feature ON + LOCKED: Control shows 'Layout · Locked', checkable but not checked. Near-black/Blood-A design. No panel movement affordance.",
        )

    # ================================================================
    # STATE 3: Feature ON + UNLOCKED
    # ================================================================
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        save_workbench_feature_settings(
            WorkbenchFeatureSettings(workspace_panel_docking_enabled=True),
            state_dir=tmp_path,
        )
        from src.workbench_edit_docking import EditDockingState, LOCK_UNLOCKED, save_edit_docking_state
        save_edit_docking_state(
            EditDockingState(lock_state=LOCK_UNLOCKED),
            state_dir=tmp_path,
        )
        adapter.load_feature_settings(state_dir=tmp_path)
        adapter.load_workspace_layout_state(state_dir=tmp_path)
        refresh()

        grab(
            "1121-unlocked",
            "Feature ON + UNLOCKED: Control shows 'Layout · Unlocked', checkable and checked. Visually distinct from LOCKED. No drag/drop/seam UI visible.",
        )

    # ================================================================
    # STATE 4: RE-LOCKED (after unlock, lock again)
    # ================================================================
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        save_workbench_feature_settings(
            WorkbenchFeatureSettings(workspace_panel_docking_enabled=True),
            state_dir=tmp_path,
        )
        from src.workbench_edit_docking import EditDockingState, LOCK_LOCKED, save_edit_docking_state
        save_edit_docking_state(
            EditDockingState(lock_state=LOCK_LOCKED),
            state_dir=tmp_path,
        )
        adapter.load_feature_settings(state_dir=tmp_path)
        adapter.load_workspace_layout_state(state_dir=tmp_path)
        refresh()

        grab(
            "1121-relocked",
            "RE-LOCKED: Control shows 'Layout · Locked' again. Surface consistent with initial LOCKED state. No topology change.",
        )

    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=args.runtime_root, text=True
    ).strip()
    provenance = {
        "status": getattr(getattr(report, "status", None), "value", str(report.status)),
        "diagnosis": getattr(report, "diagnosis", None),
        "commit": getattr(getattr(report, "manifest", None), "commit", None),
    }
    manifest = {
        "issue": 1121,
        "head": head,
        "platform": platform.platform(),
        "scale_factor": scale_factor,
        "visual_accept_state": "VISUAL_ACCEPT_PENDING",
        "captures": captures,
        "provenance": provenance,
    }
    if failed_checks:
        manifest["visual_accept_state"] = "VISUAL_ACCEPT_FAIL"
        manifest["failed_captures"] = failed_checks
        (evidence_dir / "1121-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(manifest, indent=2, sort_keys=True))
        print(
            f"capture sanity failed: {', '.join(failed_checks)}",
            file=sys.stderr,
        )
        return 1

    (evidence_dir / "1121-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())