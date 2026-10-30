#!/usr/bin/env python3
"""Windows exact-head QML evidence driver for Browser Loop runtime (#1285).

Uses only synthetic row identities and writes JSON/PNG evidence outside the repo.
Qt scale is set before any PySide6/project import in this process.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--scale", type=float, choices=(1.0, 1.25, 1.5), required=True)
    return parser.parse_args()


def _wait_until(predicate, *, app, timeout_sec: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(predicate())


def _git_head(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def _src_clean(root: Path) -> bool:
    out = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain", "--", "src"],
        text=True,
    ).strip()
    return not bool(out)


def _run(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    evidence_dir = args.evidence_dir.resolve()
    if evidence_dir.is_relative_to(root.resolve()):
        raise SystemExit("evidence-dir must be outside the repository")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # Delayed imports: scaling environment is frozen before Qt is loaded.
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from src import workbench_qml as production_qml
    from src.browser_loop_playback import BrowserLoopExtent, BrowserLoopResult
    from src.workbench_controller import WorkbenchRow
    from src.workbench_qml import (
        Screen1QmlInteractionAdapter,
        Screen1QmlViewModel,
        _qml_row,
        _qml_transport_bridge,
    )
    from src.workbench_qml_spike import _grab_qml_window_png, _qml_engine, _settle_qml_frame
    from src.workbench_transport_adapter import WorkbenchTransportAdapter

    production_path = Path(production_qml.__file__).resolve()
    if not production_path.is_relative_to(root.resolve()):
        raise SystemExit(f"wrong worktree provenance: {production_path}")

    # Synthetic evidence rows have no on-disk audio file. Supply only the source
    # frame-count metadata needed to verify Loop-extent waveform alignment; the
    # production path still uses audio_source_frame_info against the real owner.
    production_qml.audio_source_frame_info = lambda _path: (1000, 48000)

    def row(index: int, *, owner: bool = False) -> WorkbenchRow:
        name = "owner-loop" if owner else f"row-{index:03d}"
        envelope = tuple(
            min(1.0, 0.18 + 0.75 * abs(math.sin((point + index) * 0.37)))
            for point in range(96)
        )
        return WorkbenchRow(
            display_name=name,
            relative_path=f"synthetic/{name}.wav",
            path=f"C:/sample-brain-synthetic/{name}.wav",
            bpm=120.0 + (index % 4),
            key="Am",
            key_conf=1.0,
            loudness=None,
            brightness=None,
            sample_class="loop",
            pred_type="loop",
            status="ok",
            details={"waveform_envelope": envelope, "duration_sec": 4.0},
        )

    rows = tuple(row(i, owner=i == 2) for i in range(60))
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=("Synthetic",),
        browser_rows=tuple(_qml_row(r) for r in rows),
        selected_browser_index=0,
        harmony_rows=(),
        live_kit_groups=(),
        browser_context="Synthetic acceptance",
    )
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=False,
    )
    view_model.set_library_revealed(True)

    @dataclass
    class LoopStub:
        owner_row: WorkbenchRow | None
        extent: BrowserLoopExtent | None
        phase: int | None
        reduced_capability_reason: str | None = None

        @property
        def is_active(self) -> bool:
            return self.owner_row is not None and self.extent is not None

        def current_source_phase_frame(self) -> int | None:
            return self.phase

        def loop_on(self, target: WorkbenchRow) -> BrowserLoopResult:
            self.owner_row = target
            self.extent = BrowserLoopExtent(100, 900, 2, (100, 500, 900))
            self.phase = 340
            self.reduced_capability_reason = None
            return BrowserLoopResult(ok=True, owner_path=str(target.path), bar_count=2)

        def loop_off(self) -> BrowserLoopResult:
            self.owner_row = None
            self.extent = None
            self.phase = None
            self.reduced_capability_reason = None
            return BrowserLoopResult(ok=True, message="LOOP OFF")

    loop = LoopStub(rows[2], BrowserLoopExtent(100, 900, 2, (100, 500, 900)), 340)
    previews: list[str] = []
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        on_preview_requested=lambda target, **_kwargs: previews.append(str(target.path)),
    )
    adapter.bind_browser_loop(loop)

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.resize(1440, 900)
    window.show()
    QTest.qWaitForWindowExposed(window, 5000)
    _settle_qml_frame(app)

    assert _wait_until(
        lambda: window.findChild(QQuickItem, "browserList") is not None
        and window.findChild(QQuickItem, "browserLoopSticky") is not None
        and window.findChild(QQuickItem, "browserSearch") is not None,
        app=app,
    )
    browser = window.findChild(QQuickItem, "browserList")
    sticky = window.findChild(QQuickItem, "browserLoopSticky")
    search = window.findChild(QQuickItem, "browserSearch")
    assert browser is not None and sticky is not None and search is not None
    bridge = engine._screen1_interaction_bridge

    evidence: dict[str, object] = {
        "issue": 1285,
        "exit_target": "BROWSER_LOOP_QML_RUNTIME_PASS",
        "git_head": _git_head(root),
        "src_clean": _src_clean(root),
        "module_provenance": str(production_path.relative_to(root)).replace("\\", "/"),
        "magicpath_revision": "466704025803440128",
        "scale": args.scale,
        "checks": {},
        "captures": {},
    }
    checks: dict[str, object] = evidence["checks"]  # type: ignore[assignment]
    captures: dict[str, str] = evidence["captures"]  # type: ignore[assignment]

    def snapshot(name: str) -> None:
        path = evidence_dir / f"{name}.png"
        _grab_qml_window_png(window, path, engine=engine)
        captures[name] = path.name

    def assert_xor() -> None:
        inline = bool(browser.property("loopOwnerInlineVisible"))
        sticky_visible = bool(sticky.property("visible"))
        assert inline != sticky_visible, (inline, sticky_visible, browser.property("loopStickyEdge"))

    try:
        assert _wait_until(lambda: bool(browser.property("loopOwnerInlineVisible")), app=app)
        def rendered_inline_playheads():
            found = []
            def walk(item):
                if item.objectName() == "browserLoopInlinePlayhead":
                    found.append(item)
                for child in item.childItems():
                    walk(child)
            walk(window.contentItem())
            return [
                item for item in found
                if bool(item.property("visible")) and float(item.width()) > 0 and float(item.height()) > 0
            ]
        assert _wait_until(lambda: len(rendered_inline_playheads()) == 1, app=app)
        inline_playhead = rendered_inline_playheads()[0]
        assert_xor()
        assert bridge.property("browserLoopOwnerName") == "owner-loop"
        assert list(bridge.property("browserLoopBarPositions")) == [0.0, 0.5, 1.0]
        assert 0.0 < float(bridge.property("browserLoopProgress")) < 1.0
        assert bool(inline_playhead.property("visible"))
        checks["inline_grid_playhead"] = "PASS"
        assert bool(bridge.property("browserLoopWaveformAligned"))
        checks["inline_waveform_extent_aligned"] = "PASS"
        snapshot("01-inline-owner")

        adapter.preview_row(5)
        bridge.refreshPlaybackProjection()
        app.processEvents()
        assert previews == [str(rows[5].path)]
        assert bridge.property("browserLoopOwnerPath") == str(rows[2].path)
        checks["different_row_audition_preserves_loop"] = "PASS"

        browser.setProperty("contentY", 600.0)
        assert _wait_until(lambda: browser.property("loopStickyEdge") == "top", app=app)
        assert_xor()
        checks["sticky_top"] = "PASS"
        snapshot("02-sticky-top")

        browser.setProperty("contentY", 0.0)
        assert _wait_until(lambda: bool(browser.property("loopOwnerInlineVisible")), app=app)
        assert_xor()
        checks["return_to_inline"] = "PASS"

        loop.loop_on(rows[50])
        bridge.refreshPlaybackProjection()
        assert _wait_until(lambda: int(browser.property("loopOwnerVisibleIndex")) == 50, app=app)
        assert _wait_until(lambda: browser.property("loopStickyEdge") == "bottom", app=app)
        assert_xor()
        assert bridge.property("browserLoopOwnerPath") == str(rows[50].path)
        checks["atomic_owner_replace_and_sticky_bottom"] = "PASS"
        snapshot("03-sticky-bottom-replace")

        browser.setProperty("contentY", 1450.0)
        assert _wait_until(lambda: bool(browser.property("loopOwnerInlineVisible")), app=app)
        assert_xor()
        checks["replacement_owner_inline"] = "PASS"

        search.setProperty("text", "row-001")
        assert _wait_until(lambda: int(browser.property("loopOwnerVisibleIndex")) == -1, app=app)
        assert bool(sticky.property("visible"))
        assert bridge.property("browserLoopOwnerPath") == str(rows[50].path)
        checks["filter_hidden_owner_persists"] = "PASS"
        snapshot("04-filter-hidden-owner")

        search.setProperty("text", "")
        browser.setProperty("contentY", 0.0)
        assert _wait_until(lambda: int(browser.property("loopOwnerVisibleIndex")) == 50, app=app)

        bridge.openSampleContext(1)
        assert bridge.property("contextTargetIsLoopOwner") is False
        assert bridge.property("browserLoopOwnerPath") == str(rows[50].path)
        bridge.closeSampleContext()
        checks["context_target_coexists_without_retarget"] = "PASS"

        # Global SYNC authority is the transport bridge; Loop projection exposes no local SYNC field.
        transport = WorkbenchTransportAdapter(initial_bpm=120.0, initial_sync_enabled=False)
        transport_bridge = _qml_transport_bridge(transport)
        assert transport_bridge.property("syncEnabled") is False
        assert transport_bridge.toggleSync() is True
        assert transport_bridge.property("syncEnabled") is True
        assert bridge.metaObject().indexOfProperty("syncEnabled") == -1
        assert transport_bridge.toggleSync() is False
        checks["sync_global_authority_on_off"] = "PASS"

        loop.reduced_capability_reason = "SYNC_NOT_SYNCABLE"
        bridge.refreshPlaybackProjection()
        app.processEvents()
        assert bridge.property("browserLoopActive") is True
        assert bridge.property("browserLoopPlaybackAvailable") is False
        assert bridge.property("browserLoopReducedCapabilityReason") == "SYNC_NOT_SYNCABLE"
        checks["reduced_capability_fail_closed"] = "PASS"
        snapshot("05-reduced-capability")

        loop.reduced_capability_reason = None
        bridge.setWaveformMotionMode("reduced")
        bridge.refreshPlaybackProjection()
        app.processEvents()
        assert bridge.property("waveformMotionMode") == "reduced"
        checks["reduced_motion_truthful"] = "PASS"

        browser.setProperty("hoveredWaveformIndex", 49)
        app.processEvents()
        assert bridge.property("browserLoopOwnerPath") == str(rows[50].path)
        checks["hover_coexists_without_owner_mutation"] = "PASS"

        window.resize(900, 700)
        _settle_qml_frame(app)
        assert float(browser.width()) > 0
        assert float(sticky.width()) <= float(browser.width()) + 1.0
        assert_xor()
        checks["narrow_width"] = "PASS"
        snapshot("06-narrow-width")

        adapter.open_sample_context(50)
        result = adapter.request_context_loop_toggle()
        bridge.refreshPlaybackProjection()
        app.processEvents()
        assert result.ok
        assert bridge.property("browserLoopActive") is False
        assert sticky.property("visible") is False
        checks["loop_off_clears_only_persistent_role"] = "PASS"

        evidence["result"] = "PASS"
    except Exception as exc:
        evidence["result"] = "FAIL"
        evidence["error"] = f"{type(exc).__name__}: {exc}"
        evidence["traceback"] = traceback.format_exc()
        evidence["failure_state"] = {
            "inline": bool(browser.property("loopOwnerInlineVisible")),
            "sticky_edge": str(browser.property("loopStickyEdge")),
            "sticky_visible": bool(sticky.property("visible")),
            "owner_index": int(browser.property("loopOwnerVisibleIndex") or -1),
            "owner_name": str(bridge.property("browserLoopOwnerName") or ""),
            "owner_path": str(bridge.property("browserLoopOwnerPath") or ""),
            "bar_positions": list(bridge.property("browserLoopBarPositions") or []),
            "progress": float(bridge.property("browserLoopProgress") or 0.0),
            "playback_available": bool(bridge.property("browserLoopPlaybackAvailable")),
            "motion_mode": str(bridge.property("waveformMotionMode") or ""),
        }
    finally:
        window.close()
        app.processEvents()
        for name in ("_screen1_waveform_timer", "_screen1_browser_loop_timer"):
            timer = getattr(engine, name, None)
            if timer is not None:
                timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()

    target = evidence_dir / "browser_loop_qml_runtime_evidence.json"
    target.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence.get("result") == "PASS" else 1


def main() -> int:
    args = _parse_args()
    os.environ["QT_QPA_PLATFORM"] = "windows"
    os.environ["QT_QUICK_BACKEND"] = "software"
    os.environ["QT_SCALE_FACTOR"] = str(args.scale)
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
