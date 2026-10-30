#!/usr/bin/env python3
"""Windows exact-head QML evidence for Browser column reorder (#1292).

Uses generated/synthetic Browser rows only and writes JSON/PNG evidence outside
this repository. Qt scaling is configured before PySide6/project imports.
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
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--scale", type=float, choices=(1.0, 1.25, 1.5), required=True)
    return parser.parse_args()


def _git_head(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def _wait_until(predicate, *, app, timeout_sec: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(predicate())


def _variant_list(value) -> list[str]:
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return [str(item) for item in value]


def _run(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    evidence_dir = args.evidence_dir.resolve()
    if evidence_dir.is_relative_to(root.resolve()):
        raise SystemExit("evidence-dir must be outside the repository")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from src import workbench_qml as production_qml
    from src.workbench_controller import WorkbenchRow
    from src.workbench_qml import Screen1QmlInteractionAdapter, Screen1QmlViewModel, _qml_row
    from src.workbench_qml_spike import _grab_qml_window_png, _qml_engine, _settle_qml_frame

    production_path = Path(production_qml.__file__).resolve()
    if not production_path.is_relative_to(root.resolve()):
        raise SystemExit("wrong worktree provenance")

    def row(index: int) -> WorkbenchRow:
        envelope = tuple(
            min(1.0, 0.18 + 0.75 * abs(math.sin((point + index) * 0.37)))
            for point in range(96)
        )
        return WorkbenchRow(
            display_name=f"synthetic-row-{index:03d}",
            relative_path=f"synthetic/row-{index:03d}.wav",
            path=f"C:/sample-brain-synthetic/row-{index:03d}.wav",
            bpm=120.0 + (index % 6),
            key="Am",
            key_conf=1.0,
            loudness=None,
            brightness=None,
            sample_class="loop",
            pred_type="loop",
            status="ok",
            details={"waveform_envelope": envelope, "duration_sec": 4.0},
        )

    rows = tuple(row(i) for i in range(60))
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=("Synthetic",),
        browser_rows=tuple(_qml_row(item) for item in rows),
        selected_browser_index=3,
        harmony_rows=(),
        live_kit_groups=(),
        browser_context="Synthetic column reorder acceptance",
    )
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=False,
    )
    view_model.set_library_revealed(True)
    previews: list[str] = []
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        on_preview_requested=lambda target, **_kwargs: previews.append(str(target.path)),
    )

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.resize(1440, 900)
    window.show()
    QTest.qWaitForWindowExposed(window, 5000)
    _settle_qml_frame(app)

    def find_visual(root_item, object_name: str):
        if root_item.objectName() == object_name:
            return root_item
        for child in root_item.childItems():
            found = find_visual(child, object_name)
            if found is not None:
                return found
        return None

    def scene_point(item, x: float, y: float) -> QPoint:
        point = item.mapToScene(QPointF(float(x), float(y)))
        return QPoint(round(point.x()), round(point.y()))

    def scene_x(item) -> float:
        return float(item.mapToScene(QPointF(0.0, 0.0)).x())

    assert _wait_until(lambda: window.findChild(QQuickItem, "browserPane") is not None, app=app)
    pane = window.findChild(QQuickItem, "browserPane")
    assert pane is not None

    evidence: dict[str, object] = {
        "issue": 1292,
        "exit_target": "BROWSER_COLUMN_REORDER_RUNTIME_PASS",
        "git_head": _git_head(root),
        "module_provenance": str(production_path.relative_to(root)).replace("\\", "/"),
        "magicpath_revision": "466430376995328000",
        "scale": args.scale,
        "checks": {},
        "captures": {},
    }
    checks: dict[str, object] = evidence["checks"]  # type: ignore[assignment]
    captures: dict[str, str] = evidence["captures"]  # type: ignore[assignment]

    def snapshot(name: str) -> None:
        target = evidence_dir / f"{name}.png"
        _grab_qml_window_png(window, target, engine=engine)
        captures[name] = target.name

    try:
        default_order = ["waveform", "filename", "bpm", "favorite", "key", "length", "type"]
        assert _variant_list(pane.property("browserColumnOrder")) == default_order
        filename_header = find_visual(pane, "browserColumnHeader_filename")
        bpm_header = find_visual(pane, "browserColumnHeader_bpm")
        bpm_resize = find_visual(pane, "browserColumnResize_bpm")
        bpm_reorder = find_visual(pane, "browserColumnReorder_bpm")
        waveform_reorder = find_visual(pane, "browserColumnReorder_waveform")
        filename_row = find_visual(pane, "browserFilenameCell")
        bpm_row = find_visual(pane, "browserBpmCell")
        assert all(
            item is not None
            for item in (
                filename_header,
                bpm_header,
                bpm_resize,
                bpm_reorder,
                waveform_reorder,
                filename_row,
                bpm_row,
            )
        )
        assert str(filename_header.property("text")) == "DATEINAME"
        assert 'text: "WAVEFORM"' in production_qml.QML_SOURCE
        checks["default_order_and_dateiname"] = "PASS"
        checks["waveform_header_label"] = "PASS"
        snapshot("01-default")

        selected_before = view_model.selected_browser_index
        order_before_resize = _variant_list(pane.property("browserColumnOrder"))
        width_before = float(bpm_header.width())
        start = scene_point(bpm_resize, bpm_resize.width() / 2.0, bpm_resize.height() / 2.0)
        end = start + QPoint(14, 0)
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(window, end, delay=20)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, end)
        _settle_qml_frame(app)
        assert float(bpm_header.width()) > width_before
        resized_width = float(bpm_header.width())
        assert _variant_list(pane.property("browserColumnOrder")) == order_before_resize
        checks["separator_resize_wins"] = "PASS"

        start = scene_point(bpm_reorder, bpm_reorder.width() / 2.0, bpm_reorder.height() / 2.0)
        target = scene_point(filename_header, 2.0, filename_header.height() / 2.0)
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(window, target, delay=20)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, target)
        _settle_qml_frame(app)
        order = _variant_list(pane.property("browserColumnOrder"))
        assert order.index("bpm") < order.index("filename")
        assert scene_x(bpm_header) < scene_x(filename_header)
        assert scene_x(bpm_row) < scene_x(filename_row)
        assert pytest_approx(scene_x(bpm_row), scene_x(bpm_header), 1.5)
        assert pytest_approx(float(bpm_header.width()), resized_width, 1.0)
        assert pytest_approx(float(bpm_row.width()), resized_width, 1.0)
        assert view_model.selected_browser_index == selected_before
        assert previews == []
        checks["body_drag_reorders_header_and_rows"] = "PASS"
        checks["role_width_survives_reorder"] = "PASS"
        checks["reorder_has_zero_selection_audition_mutation"] = "PASS"
        snapshot("02-bpm-reordered")

        # WAVEFORM participates in the same body-drag reorder path.
        waveform_header = find_visual(pane, "browserColumnHeader_waveform")
        assert waveform_header is not None
        start = scene_point(waveform_reorder, waveform_reorder.width() / 2.0, waveform_reorder.height() / 2.0)
        target = scene_point(filename_header, max(2.0, filename_header.width() - 2.0), filename_header.height() / 2.0)
        QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
        QTest.mouseMove(window, target, delay=20)
        QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, target)
        _settle_qml_frame(app)
        order = _variant_list(pane.property("browserColumnOrder"))
        assert order.index("waveform") > order.index("filename")
        checks["waveform_reorder"] = "PASS"

        # Supported narrow-window runtime remains coherent even though outer
        # 3-panel geometry clamps browserPane above its <700-DIP compact seam.
        window.resize(900, 700)
        _settle_qml_frame(app)
        visible_roles = [role for role in _variant_list(pane.property("browserColumnOrder")) if role != "type" or not bool(pane.property("browserNarrowColumns"))]
        header_items = [find_visual(pane, f"browserColumnHeader_{role}") for role in visible_roles]
        assert all(item is not None and item.width() > 0 for item in header_items)
        visual = sorted((scene_x(item), float(item.width())) for item in header_items)
        assert all(right_x >= left_x + left_w - 1.0 for (left_x, left_w), (right_x, _right_w) in zip(visual, visual[1:]) if left_w > 0)
        checks["narrow_supported_window"] = "PASS"
        snapshot("03-narrow-window")

        assert view_model.selected_browser_index == selected_before
        assert previews == []
        evidence["result"] = "PASS"
    except Exception as exc:
        evidence["result"] = "FAIL"
        evidence["error"] = f"{type(exc).__name__}: {exc}"
        evidence["traceback"] = traceback.format_exc()
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loop_timer = getattr(engine, "_screen1_browser_loop_timer", None)
        if loop_timer is not None:
            loop_timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()

    target = evidence_dir / "browser_column_reorder_runtime_evidence.json"
    target.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence.get("result") == "PASS" else 1


def pytest_approx(actual: float, expected: float, tolerance: float) -> bool:
    return abs(float(actual) - float(expected)) <= float(tolerance)


def main() -> int:
    args = _parse_args()
    os.environ["QT_QPA_PLATFORM"] = "windows"
    os.environ["QT_QUICK_BACKEND"] = "software"
    os.environ["QT_SCALE_FACTOR"] = str(args.scale)
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
