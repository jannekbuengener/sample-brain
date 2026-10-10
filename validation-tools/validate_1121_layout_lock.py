from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
from pathlib import Path


def _framebuffer_matches_scale(actual_w: int, actual_h: int, *, scale: float, dpr: float, logical_w: int, logical_h: int) -> bool:
    if scale <= 0 or dpr <= 0 or logical_w <= 0 or logical_h <= 0:
        return False
    if abs(dpr - scale) > 0.05:
        return False
    expected_w = int(round(logical_w * dpr))
    expected_h = int(round(logical_h * dpr))
    tolerance = max(2, int(round(dpr)))
    return abs(actual_w - expected_w) <= tolerance and abs(actual_h - expected_h) <= tolerance


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--scale-factor", type=float, required=True)
    args = parser.parse_args()

    runtime_root = args.runtime_root.resolve()
    evidence_dir = args.evidence_dir.resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    scale = float(args.scale_factor)

    os.environ["QT_SCALE_FACTOR"] = str(scale)
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    state_dir = evidence_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    os.environ["SAMPLE_BRAIN_WORKBENCH_STATE_DIR"] = str(state_dir)

    sys.path.insert(0, str(runtime_root))
    os.chdir(runtime_root)

    from PySide6.QtCore import QObject

    from src.workbench_edit_docking import (
        LOCK_LOCKED,
        LOCK_UNLOCKED,
        EditDockingState,
        load_edit_docking_state,
        save_edit_docking_state,
    )
    from src.workbench_feature_settings import (
        WorkbenchFeatureSettings,
        save_workbench_feature_settings,
    )
    from src.workbench_qml import LiveKitPresenter, Screen1QmlInteractionAdapter, Screen1QmlViewModel
    from src.workbench_qml_spike import (
        CLIENT_HEIGHT,
        CLIENT_WIDTH,
        _grab_qml_window_png,
        _qml_engine,
        _settle_qml_frame,
        _wait_for_screen1_background_ready,
        validate_capture_sanity,
    )

    expected_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=runtime_root, text=True).strip()

    save_workbench_feature_settings(
        WorkbenchFeatureSettings(workspace_panel_docking_enabled=False),
        state_dir=state_dir,
    )
    if not save_edit_docking_state(EditDockingState(lock_state=LOCK_LOCKED), state_dir=state_dir):
        raise SystemExit("failed to seed layout state")

    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    presenter = LiveKitPresenter()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        live_kit=presenter,
        on_preview_requested=lambda *_a, **_k: None,
        on_preview_stopped=lambda: None,
    )
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.setWidth(CLIENT_WIDTH)
    window.setHeight(CLIENT_HEIGHT)
    window.show()
    _settle_qml_frame(app)
    _wait_for_screen1_background_ready(window, app)

    def find(name: str):
        obj = window.findChild(QObject, name)
        if obj is None:
            for root in engine.rootObjects():
                obj = root.findChild(QObject, name)
                if obj is not None:
                    break
        if obj is None:
            raise AssertionError(f"QML object not found: {name}")
        return obj

    popover = find("displayPreferencesPopover")
    toggle = find("workspaceLayoutLockToggle")
    bridge = getattr(engine, "_screen1_interaction_bridge", None)
    if bridge is None:
        raise AssertionError("interaction bridge missing")

    def refresh() -> None:
        bridge.refreshState()
        popover.setProperty("visible", True)
        _settle_qml_frame(app)
        if not bool(popover.property("visible")):
            raise AssertionError("display preferences popover did not open")

    results: dict[str, dict[str, object]] = {}

    def grab(label: str, expected_text: str, expected_enabled: bool) -> None:
        refresh()
        text = str(toggle.property("text"))
        enabled = bool(toggle.property("enabled"))
        if text != expected_text:
            raise AssertionError(f"{label}: text={text!r}, expected={expected_text!r}")
        if enabled is not expected_enabled:
            raise AssertionError(f"{label}: enabled={enabled}, expected={expected_enabled}")

        target = evidence_dir / f"{label}.png"
        _grab_qml_window_png(window, target, engine=engine)
        raw = target.read_bytes()
        actual_w, actual_h = struct.unpack(">II", raw[16:24])
        dpr = float(window.devicePixelRatio())
        logical_w = int(window.width())
        logical_h = int(window.height())
        sanity = validate_capture_sanity(target, expected_width=actual_w, expected_height=actual_h)
        scale_ok = _framebuffer_matches_scale(
            actual_w,
            actual_h,
            scale=scale,
            dpr=dpr,
            logical_w=logical_w,
            logical_h=logical_h,
        )
        passed = bool(sanity.get("pass")) and scale_ok
        results[label] = {
            "text": text,
            "enabled": enabled,
            "sanity": sanity,
            "scale_ok": scale_ok,
            "device_pixel_ratio": dpr,
            "logical_size": [logical_w, logical_h],
            "framebuffer_size": [actual_w, actual_h],
            "pass": passed,
        }
        if not passed:
            raise AssertionError(f"{label}: capture/scale validation failed: {results[label]}")

    grab("1121-feature-off", "Layout · Locked", False)

    save_workbench_feature_settings(
        WorkbenchFeatureSettings(workspace_panel_docking_enabled=True),
        state_dir=state_dir,
    )
    adapter.load_feature_settings(state_dir=state_dir)
    adapter.load_workspace_layout_state(state_dir=state_dir)
    grab("1121-locked", "Layout · Locked", True)

    bridge.setWorkspaceLayoutLocked(False)
    if load_edit_docking_state(state_dir=state_dir).lock_state != LOCK_UNLOCKED:
        raise AssertionError("unlock intent did not persist UNLOCKED")
    grab("1121-unlocked", "Layout · Unlocked", True)

    bridge.setWorkspaceLayoutLocked(True)
    if load_edit_docking_state(state_dir=state_dir).lock_state != LOCK_LOCKED:
        raise AssertionError("re-lock intent did not persist LOCKED")
    grab("1121-relocked", "Layout · Locked", True)

    manifest = {
        "issue": 1121,
        "target_head": expected_head,
        "scale_factor": scale,
        "states": results,
        "visual_accept_state": "VISUAL_ACCEPT_PENDING",
    }
    (evidence_dir / "1121-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
