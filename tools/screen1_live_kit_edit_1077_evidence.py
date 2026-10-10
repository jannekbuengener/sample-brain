"""Exact-HEAD QML runtime evidence for #1077 Live Kit Edit states.

Evidence is written outside the repository. Synthetic fixture paths only.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="#1077 Live Kit Edit visual evidence")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, default=Path.cwd())
    parser.add_argument("--scale-factor", type=float, default=1.0)
    args = parser.parse_args()

    evidence_dir = args.evidence_dir.resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if evidence_dir.is_relative_to(args.runtime_root.resolve()):
        print("evidence-dir must be outside the repository", file=sys.stderr)
        return 2

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
    report = validate_qml_renderer_provenance(args.runtime_root)
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
    ]

    def grab(label: str, note: str) -> None:
        path = evidence_dir / f"{label}.png"
        _grab_qml_window_png(window, path, engine=engine)
        check = validate_capture_sanity(
            path, expected_width=CLIENT_WIDTH, expected_height=CLIENT_HEIGHT
        )
        check["note"] = note
        check["scale_factor"] = args.scale_factor
        captures[label] = str(path)
        (evidence_dir / f"{label}.json").write_text(
            json.dumps(check, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

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

    # Compact: leave drawer open with collapsed groups (default disclosure).
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

    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=args.runtime_root, text=True
    ).strip()
    manifest = {
        "issue": 1077,
        "head": head,
        "platform": platform.platform(),
        "scale_factor": args.scale_factor,
        "visual_accept_state": "VISUAL_ACCEPT_PENDING",
        "captures": captures,
        "provenance": report,
    }
    (evidence_dir / "1077-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
