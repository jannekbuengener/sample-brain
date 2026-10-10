"""Exact-HEAD QML runtime evidence for #1077 Live Kit Edit states.

Evidence is written outside the repository. Synthetic fixture paths only.
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
    """Fail closed when requested scale is not the effective Qt scale.

    Compares the capture to ``logical_* * devicePixelRatio`` (OS may clamp the
    logical window below CLIENT_*), and requires DPR ≈ ``scale_factor`` so a
    plain 100% run cannot be labeled 125/150.
    """
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
    parser = argparse.ArgumentParser(description="#1077 Live Kit Edit visual evidence")
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
    # Must precede QApplication creation so Qt honors the requested scale.
    os.environ["QT_SCALE_FACTOR"] = str(scale_factor)
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

    from src.workbench_controller import WorkbenchRow
    from src.workbench_qml import LiveKitPresenter, Screen1QmlInteractionAdapter
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
    fixture = build_screen1_visual_fixture_v2()
    state = resolve_screen1_visual_state_v2(fixture, "screen1-active-source")
    view_model = build_qml_view_model_from_fixture_v2(fixture, "screen1-active-source")
    presenter = LiveKitPresenter()
    view_model.live_kit_groups = presenter.groups
    adapter = Screen1QmlInteractionAdapter(view_model=view_model, live_kit=presenter)
    apply_screen1_visual_state_v2(view_model, adapter, fixture, state)
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=False,
    )
    adapter._live_kit_drawer_open = False
    adapter.live_kit_collapsed = True

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
    labels_notes = [
        ("1077-clean-edit-hidden", "Clean Edit; Live Kit hidden; no bottom cavity"),
        ("1077-live-kit-revealed", "Live Kit revealed; groups/slots; no step grid"),
        ("1077-live-kit-compact-resized", "Live Kit compact/resized drawer"),
        ("1077-live-kit-populated", "Populated slots + Remove/Export"),
        ("1077-live-kit-hidden-restored", "Hidden again; Edit area restored"),
        (
            "1077-live-kit-restart-restored-visible",
            "Restart with live_kit_visible=true rematerializes Live Kit",
        ),
    ]

    failed_checks: list[str] = []

    def grab(label: str, note: str) -> None:
        import struct

        path = evidence_dir / f"{label}.png"
        _grab_qml_window_png(window, path, engine=engine)
        # High-DPI / QT_SCALE_FACTOR captures use framebuffer pixels, not
        # logical CLIENT_* alone. Validate against the actual PNG size and
        # require a non-black, minimum-usable frame.
        raw = path.read_bytes()
        actual_w, actual_h = struct.unpack(">II", raw[16:24])
        dpr = float(window.devicePixelRatio())
        logical_w = int(window.width())
        logical_h = int(window.height())
        expected_w = int(round(logical_w * dpr))
        expected_h = int(round(logical_h * dpr))
        # Sanity checks existence/non-black against the captured frame; scale
        # authority is the DPR/framebuffer gate (rounding may be ±1–2 px).
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
        usable = actual_w >= CLIENT_WIDTH and actual_h >= max(600, CLIENT_HEIGHT // 2)
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

    grab(*labels_notes[0])

    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=True,
    )
    adapter._live_kit_drawer_open = True
    adapter.live_kit_collapsed = False
    refresh()
    grab(*labels_notes[1])

    # Compact/resized: exercise user height authority (not just row-derived height).
    adapter.set_live_kit_user_height_px(180, max_px=320)
    refresh()
    grab(*labels_notes[2])

    row = WorkbenchRow(
        display_name="kick_synth.wav",
        relative_path="synthetic/kick_synth.wav",
        path="synthetic/kick_synth.wav",
        bpm=128.0,
        key="Am",
        key_conf=0.9,
        loudness=-12.0,
        brightness=3000.0,
        sample_class="one_shot",
        pred_type="Kick",
        status="ok",
        details={"duration_sec": "0.2", "source": "synthetic"},
    )
    presenter.assign("Kick + Bass", "Kick", row)
    presenter.assign("Drums", "Closed Hat", row)
    adapter._sync_live_kit_projection()
    if presenter.presentation.is_collapsed("Kick + Bass"):
        presenter.toggle_group("Kick + Bass")
    adapter._sync_live_kit_projection()
    refresh()
    grab(*labels_notes[3])

    adapter._live_kit_drawer_open = False
    adapter.live_kit_collapsed = True
    refresh()
    grab(*labels_notes[4])

    # Restart-visible preference path: rematerialize via reveal seam (#1077 P1).
    # Keep preference I/O inside evidence_dir — never touch the user state home.
    from src.workbench_library_navigation import LibraryScope, LibraryScopeKind
    from src.workbench_live_kit_edit import save_live_kit_visibility_preference
    from src.workbench_qml_runtime import Screen1BrowserState, Screen1QmlRuntimeComposition

    pref_dir = evidence_dir / "pref-state"
    pref_dir.mkdir(parents=True, exist_ok=True)
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=False,
    )
    adapter._live_kit_drawer_open = False
    adapter.live_kit_collapsed = True
    composition = Screen1QmlRuntimeComposition()
    composition._selected_node_id = "root:evidence"
    composition.browser_state = Screen1BrowserState(
        scope=LibraryScope(LibraryScopeKind.ROOT, folder_id=1, folder_path="synthetic"),
        browser_context="Evidence active source",
    )
    adapter._runtime_composition = composition
    save_live_kit_visibility_preference(True, state_dir=pref_dir)
    # Point load path at evidence_dir for the restore call.
    os.environ["SAMPLE_BRAIN_WORKBENCH_STATE_DIR"] = str(pref_dir)
    assert adapter.apply_live_kit_visibility_preference() is True
    assert adapter.live_kit_is_visible() is True
    refresh()
    grab(*labels_notes[5])

    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=args.runtime_root, text=True
    ).strip()
    provenance = {
        "status": getattr(getattr(report, "status", None), "value", str(report.status)),
        "diagnosis": getattr(report, "diagnosis", None),
        "commit": getattr(getattr(report, "manifest", None), "commit", None),
    }
    manifest = {
        "issue": 1077,
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
        (evidence_dir / "1077-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(manifest, indent=2, sort_keys=True))
        print(
            f"capture sanity failed: {', '.join(failed_checks)}",
            file=sys.stderr,
        )
        return 1

    (evidence_dir / "1077-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
