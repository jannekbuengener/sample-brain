"""#695 Waveform rendering research spike — isolated harness (not production QML).

Compares Canvas / Shape / cached-static / QSGGeometry backends with synthetic
envelopes. Does not modify production ``QML_SOURCE`` or audio contracts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import time
from typing import Any, Callable, Mapping, Sequence

os.environ.setdefault("QT_QUICK_BACKEND", "software")

RENDERER_CANVAS = "canvas"
RENDERER_SHAPE = "shape"
RENDERER_CACHED = "cached_static"
RENDERER_QSG = "qsg_geometry"
RENDERERS = (
    RENDERER_CANVAS,
    RENDERER_SHAPE,
    RENDERER_CACHED,
    RENDERER_QSG,
)

MOTION_OFF = "off"
MOTION_REDUCED = "reduced"
MOTION_ON = "on"
MOTION_MODES = (MOTION_OFF, MOTION_REDUCED, MOTION_ON)

POINTS = 96
VISIBLE_ROWS_DEFAULT = 24
SEED = 695_2026

WINDOW_SIZES = (
    (1600, 900),
    (1280, 720),
    (1120, 640),
)


@dataclass(frozen=True)
class RendererResult:
    renderer: str
    window_width: int
    window_height: int
    row_count: int
    visible_rows: int
    motion_mode: str
    initial_ms: float
    scroll_ms: float
    scroll_burst_ms: float
    selection_ms: float
    keyboard_nav_ms: float
    preview_start_ms: float
    active_motion_frame_ms: float
    delegate_creations: int
    virtualized: bool
    pooled_timers_active: int
    notes: str = ""


def synthetic_envelope(index: int, *, points: int = POINTS, seed: int = SEED) -> list[float]:
    """Deterministic peak envelope in ``[0, 1]`` — no audio IO."""
    rng = random.Random(seed + index * 9973)
    values: list[float] = []
    phase = rng.random() * math.tau
    for i in range(points):
        t = i / max(1, points - 1)
        base = 0.18 + 0.55 * abs(math.sin(phase + t * 9.0))
        noise = 0.12 * rng.random()
        values.append(max(0.0, min(1.0, base + noise)))
    return values


def build_envelopes(row_count: int, *, points: int = POINTS, seed: int = SEED) -> tuple[list[float], ...]:
    return tuple(synthetic_envelope(i, points=points, seed=seed) for i in range(row_count))


def _require_pyside6() -> None:
    try:
        import PySide6  # noqa: F401
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("PySide6 required for #695 waveform research spike") from exc


def _waveform_item_qml(renderer: str) -> str:
    """Only the active renderer is compiled into the research delegate."""
    if renderer == RENDERER_CANVAS:
        return """
                    Canvas {
                        id: canvasWave
                        anchors.fill: parent
                        property var envelope: row.envelope
                        property real playhead: (row.rowActive ? root.playheadNorm : -1)
                        onEnvelopeChanged: requestPaint()
                        onPlayheadChanged: requestPaint()
                        onWidthChanged: requestPaint()
                        onHeightChanged: requestPaint()
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            ctx.strokeStyle = (index === root.selectedIndex) ? "#b1122b" : "#6d737c"
                            ctx.lineWidth = 1.2
                            ctx.beginPath()
                            var points = envelope || []
                            var center = height / 2
                            if (points.length === 0) {
                                ctx.moveTo(0, center); ctx.lineTo(width, center)
                            } else {
                                var step = width / points.length
                                for (var p = 0; p < points.length; p++) {
                                    var v = Math.max(0, Math.min(1, Number(points[p]) || 0))
                                    var x = Math.min(width, p * step + step / 2)
                                    var amp = Math.max(1, height * 0.42 * v)
                                    if (row.rowActive && root.motionMode === "on")
                                        amp *= (0.85 + 0.15 * Math.sin(root.playheadNorm * 6.28 + p * 0.2))
                                    ctx.moveTo(x, center - amp)
                                    ctx.lineTo(x, center + amp)
                                }
                            }
                            ctx.stroke()
                            if (playhead >= 0) {
                                var px = playhead * width
                                ctx.strokeStyle = "#eceef1"
                                ctx.lineWidth = 1
                                ctx.beginPath()
                                ctx.moveTo(px, 0); ctx.lineTo(px, height)
                                ctx.stroke()
                            }
                        }
                    }
"""
    if renderer == RENDERER_SHAPE:
        # PathSvg avoids per-bar createQmlObject; still exercises Shape triangulation.
        return """
                    Shape {
                        id: shapeWave
                        anchors.fill: parent
                        asynchronous: false
                        ShapePath {
                            id: shapePath
                            strokeWidth: 1.2
                            strokeColor: index === root.selectedIndex ? "#b1122b" : "#6d737c"
                            fillColor: "transparent"
                            PathSvg { id: shapeSvg; path: "" }
                        }
                        property var envelope: row.envelope
                        property real playhead: (row.rowActive ? root.playheadNorm : -1)
                        function rebuild() {
                            var points = envelope || []
                            var center = height / 2
                            if (width <= 0 || height <= 0) { shapeSvg.path = ""; return }
                            if (points.length === 0) {
                                shapeSvg.path = "M 0 " + center + " L " + width + " " + center
                                return
                            }
                            var step = width / points.length
                            var d = ""
                            for (var p = 0; p < points.length; p++) {
                                var v = Math.max(0, Math.min(1, Number(points[p]) || 0))
                                var x = Math.min(width, p * step + step / 2)
                                var amp = Math.max(1, height * 0.42 * v)
                                if (row.rowActive && root.motionMode === "on")
                                    amp *= (0.85 + 0.15 * Math.sin(root.playheadNorm * 6.28 + p * 0.2))
                                d += "M " + x + " " + (center - amp) + " L " + x + " " + (center + amp) + " "
                            }
                            shapeSvg.path = d
                        }
                        onEnvelopeChanged: rebuild()
                        onWidthChanged: rebuild()
                        onHeightChanged: rebuild()
                        onPlayheadChanged: if (row.rowActive) rebuild()
                        Component.onCompleted: rebuild()
                        Rectangle {
                            visible: shapeWave.playhead >= 0
                            x: Math.max(0, Math.min(parent.width - 1, shapeWave.playhead * parent.width))
                            width: 1; height: parent.height; color: "#eceef1"
                        }
                    }
"""
    if renderer == RENDERER_CACHED:
        return """
                    Image {
                        anchors.fill: parent
                        source: "image://waveform-research/" + index
                        fillMode: Image.Stretch
                        smooth: false
                        cache: true
                    }
                    Rectangle {
                        visible: row.rowActive && root.motionMode !== "off"
                        x: Math.max(0, Math.min(parent.width - 1, root.playheadNorm * parent.width))
                        width: 1; height: parent.height; color: "#eceef1"
                        z: 2
                    }
"""
    if renderer == RENDERER_QSG:
        return """
                    WaveformGeometryItem {
                        anchors.fill: parent
                        envelope: row.envelope
                        selected: index === root.selectedIndex
                        playhead: (row.rowActive && root.motionMode !== "off") ? root.playheadNorm : -1
                        intensity: (row.rowActive && root.motionMode === "on") ? 1.0 : 0.0
                    }
"""
    raise ValueError(f"Unknown renderer: {renderer}")


def _qml_list_document(*, renderer: str, motion_mode: str) -> str:
    """Isolated research QML — not the production Screen-1 shell."""
    shape_import = "import QtQuick.Shapes\n" if renderer == RENDERER_SHAPE else ""
    qsg_import = "import WaveformResearch 1.0\n" if renderer == RENDERER_QSG else ""
    wave_item = _waveform_item_qml(renderer)
    return f"""
import QtQuick
import QtQuick.Controls
{shape_import}{qsg_import}ApplicationWindow {{
    id: root
    objectName: "waveformResearchWindow"
    width: 1600
    height: 900
    visible: true
    color: "#000000"
    title: "Waveform Research #695"
    property string rendererKind: "{renderer}"
    property string motionMode: "{motion_mode}"
    property int selectedIndex: 0
    property int playingIndex: -1
    property int hoveredIndex: -1
    property int delegateCreations: 0
    property real playheadNorm: 0.0
    property int activeTimers: 0
    property int rowH: 30
    property int waveW: 180
    property int waveH: 22

    function selectRow(i) {{ selectedIndex = i }}
    function previewRow(i) {{ playingIndex = i; playheadNorm = 0.0 }}
    function hoverRow(i) {{ hoveredIndex = i }}

    Timer {{
        id: motionTimer
        interval: root.motionMode === "on" ? 16 : (root.motionMode === "reduced" ? 50 : 0)
        running: root.playingIndex >= 0 && root.motionMode !== "off"
        repeat: true
        onRunningChanged: root.activeTimers = running ? 1 : 0
        onTriggered: root.playheadNorm = (root.playheadNorm + 0.02) % 1.0
    }}

    ListView {{
        id: list
        objectName: "researchList"
        anchors.fill: parent
        anchors.margins: 8
        clip: true
        reuseItems: true
        model: researchModel
        spacing: 2
        delegate: Rectangle {{
            id: row
            width: list.width
            height: root.rowH
            color: index === root.selectedIndex ? "#1a1012" : "#0c0d0e"
            border.color: index === root.selectedIndex ? "#b1122b" : "#222426"
            property bool rowActive: index === root.playingIndex
            property var envelope: model.envelope
            Component.onCompleted: root.delegateCreations += 1
            Row {{
                anchors.fill: parent
                anchors.margins: 4
                spacing: 8
                Item {{
                    width: root.waveW
                    height: root.waveH
                    anchors.verticalCenter: parent.verticalCenter
{wave_item}
                    MouseArea {{
                        anchors.fill: parent
                        hoverEnabled: true
                        onEntered: root.hoverRow(index)
                        onExited: if (root.hoveredIndex === index) root.hoverRow(-1)
                        onClicked: root.previewRow(index)
                    }}
                }}
                Text {{
                    text: model.label
                    color: "#eceef1"
                    font.pixelSize: 12
                    anchors.verticalCenter: parent.verticalCenter
                }}
            }}
            MouseArea {{
                anchors.fill: parent
                z: -1
                onClicked: root.selectRow(index)
            }}
        }}
    }}
}}
"""


def _make_envelope_model(row_count: int, *, points: int = POINTS, seed: int = SEED):
    """On-demand list model so 50k probes do not materialize JS envelope arrays."""
    from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

    class EnvelopeListModel(QAbstractListModel):
        EnvelopeRole = Qt.ItemDataRole.UserRole + 1
        LabelRole = Qt.ItemDataRole.UserRole + 2

        def __init__(self_inner, count: int):
            super().__init__()
            self_inner._count = int(count)
            self_inner._cache: dict[int, list[float]] = {}

        def rowCount(self_inner, parent=QModelIndex()):  # noqa: N802
            if parent.isValid():
                return 0
            return self_inner._count

        def data(self_inner, index, role=Qt.ItemDataRole.DisplayRole):  # noqa: A003
            if not index.isValid():
                return None
            row = index.row()
            if role == EnvelopeListModel.EnvelopeRole:
                env = self_inner._cache.get(row)
                if env is None:
                    env = synthetic_envelope(row, points=points, seed=seed)
                    self_inner._cache[row] = env
                    if len(self_inner._cache) > 512:
                        # Drop an arbitrary older key to bound memory.
                        self_inner._cache.pop(next(iter(self_inner._cache)))
                return env
            if role == EnvelopeListModel.LabelRole:
                return f"ROW_{row}"
            if role == Qt.ItemDataRole.DisplayRole:
                return f"ROW_{row}"
            return None

        def roleNames(self_inner):  # noqa: N802
            return {
                EnvelopeListModel.EnvelopeRole: b"envelope",
                EnvelopeListModel.LabelRole: b"label",
            }

    return EnvelopeListModel(row_count)


class _WaveformImageProvider:
    """Lazy-rasterized static waveform bitmaps (cached_static path)."""

    def __init__(
        self,
        *,
        width: int = 180,
        height: int = 22,
        cache_limit: int = 512,
        points: int = POINTS,
        seed: int = SEED,
    ):
        from collections import OrderedDict

        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QImage, QPainter, QPen
        from PySide6.QtQuick import QQuickImageProvider

        class Provider(QQuickImageProvider):
            def __init__(self_inner):
                super().__init__(QQuickImageProvider.ImageType.Image)
                self_inner._cache: OrderedDict[str, QImage] = OrderedDict()
                self_inner._accent = QColor("#6d737c")

            def _render(self_inner, key: str) -> QImage:
                try:
                    idx = int(key)
                except ValueError:
                    idx = 0
                env = synthetic_envelope(idx, points=points, seed=seed)
                img = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
                img.fill(Qt.GlobalColor.transparent)
                painter = QPainter(img)
                pen = QPen(self_inner._accent)
                pen.setWidthF(1.2)
                painter.setPen(pen)
                center = height / 2.0
                step = width / len(env)
                for p, raw in enumerate(env):
                    v = max(0.0, min(1.0, float(raw)))
                    x = min(width - 1, int(p * step + step / 2))
                    amp = max(1.0, height * 0.42 * v)
                    painter.drawLine(x, int(center - amp), x, int(center + amp))
                painter.end()
                return img

            def requestImage(self_inner, id, size, requestedSize):  # noqa: N802
                del requestedSize
                key = str(id).split("/")[0]
                img = self_inner._cache.get(key)
                if img is None:
                    img = self_inner._render(key)
                    self_inner._cache[key] = img
                    while len(self_inner._cache) > cache_limit:
                        self_inner._cache.popitem(last=False)
                else:
                    self_inner._cache.move_to_end(key)
                if size is not None:
                    size.setWidth(img.width())
                    size.setHeight(img.height())
                return img

        self.provider = Provider()


_QSG_ITEM_TYPE: type | None = None
_QSG_REGISTERED = False


def _register_qsg_item() -> type:
    """Python QQuickItem drawing vertical bars via QSGGeometry (research only)."""
    global _QSG_ITEM_TYPE
    if _QSG_ITEM_TYPE is not None:
        return _QSG_ITEM_TYPE

    from PySide6.QtCore import Property, Signal
    from PySide6.QtGui import QColor
    from PySide6.QtQuick import (
        QQuickItem,
        QSGFlatColorMaterial,
        QSGGeometry,
        QSGGeometryNode,
    )

    class WaveformGeometryItem(QQuickItem):
        envelopeChanged = Signal()
        selectedChanged = Signal()
        playheadChanged = Signal()
        intensityChanged = Signal()

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setFlag(QQuickItem.Flag.ItemHasContents, True)
            self._envelope: list[float] = []
            self._selected = False
            self._playhead = -1.0
            self._intensity = 0.0

        def _get_envelope(self):
            return self._envelope

        def _set_envelope(self, value):
            seq = list(value or [])
            if seq != self._envelope:
                self._envelope = seq
                self.envelopeChanged.emit()
                self.update()

        def _get_selected(self):
            return self._selected

        def _set_selected(self, value):
            value = bool(value)
            if value != self._selected:
                self._selected = value
                self.selectedChanged.emit()
                self.update()

        def _get_playhead(self):
            return self._playhead

        def _set_playhead(self, value):
            value = float(value)
            if value != self._playhead:
                self._playhead = value
                self.playheadChanged.emit()
                self.update()

        def _get_intensity(self):
            return self._intensity

        def _set_intensity(self, value):
            value = float(value)
            if value != self._intensity:
                self._intensity = value
                self.intensityChanged.emit()
                self.update()

        envelope = Property("QVariant", _get_envelope, _set_envelope, notify=envelopeChanged)
        selected = Property(bool, _get_selected, _set_selected, notify=selectedChanged)
        playhead = Property(float, _get_playhead, _set_playhead, notify=playheadChanged)
        intensity = Property(float, _get_intensity, _set_intensity, notify=intensityChanged)

        def updatePaintNode(self, old_node, data):  # noqa: N802
            del data
            width = float(self.width())
            height = float(self.height())
            if width <= 0 or height <= 0:
                return old_node

            points = self._envelope
            bar_count = max(1, len(points)) if points else 1
            vertex_count = bar_count * 2 + (2 if self._playhead >= 0 else 0)

            if old_node is None:
                node = QSGGeometryNode()
                geometry = QSGGeometry(QSGGeometry.defaultAttributes_Point2D(), vertex_count)
                geometry.setDrawingMode(QSGGeometry.DrawingMode.DrawLines)
                geometry.setLineWidth(1.2)
                node.setGeometry(geometry)
                node.setFlag(QSGGeometryNode.Flag.OwnsGeometry)
                material = QSGFlatColorMaterial()
                node.setMaterial(material)
                node.setFlag(QSGGeometryNode.Flag.OwnsMaterial)
            else:
                node = old_node
                geometry = node.geometry()
                geometry.allocate(vertex_count)

            vertices = geometry.vertexDataAsPoint2D()
            center = height / 2.0
            color = QColor("#b1122b" if self._selected else "#6d737c")
            material = node.material()
            material.setColor(color)

            idx = 0
            if not points:
                vertices[0].set(0.0, center)
                vertices[1].set(width, center)
                idx = 2
            else:
                step = width / len(points)
                for p, raw in enumerate(points):
                    v = max(0.0, min(1.0, float(raw)))
                    amp = max(1.0, height * 0.42 * v)
                    if self._intensity > 0:
                        amp *= 0.85 + 0.15 * math.sin(self._playhead * math.tau + p * 0.2)
                    x = min(width, p * step + step / 2.0)
                    vertices[idx].set(x, center - amp)
                    vertices[idx + 1].set(x, center + amp)
                    idx += 2
            if self._playhead >= 0:
                px = max(0.0, min(width, self._playhead * width))
                vertices[idx].set(px, 0.0)
                vertices[idx + 1].set(px, height)

            node.markDirty(QSGGeometryNode.DirtyStateBit.DirtyGeometry)
            node.markDirty(QSGGeometryNode.DirtyStateBit.DirtyMaterial)
            return node

    _QSG_ITEM_TYPE = WaveformGeometryItem
    return WaveformGeometryItem


def _ensure_qsg_registered() -> None:
    global _QSG_REGISTERED
    from PySide6.QtQml import qmlRegisterType

    item = _register_qsg_item()
    if not _QSG_REGISTERED:
        qmlRegisterType(item, "WaveformResearch", 1, 0, "WaveformGeometryItem")
        _QSG_REGISTERED = True


def _settle(app: Any, *, ms: int = 40) -> None:
    """Pump events without a nested QEventLoop (avoids Windows software-backend hangs)."""
    deadline = time.perf_counter() + (ms / 1000.0)
    while time.perf_counter() < deadline:
        try:
            app.processEvents()
        except Exception:
            # Windows COM RPC_E_WRONG_THREAD can surface during teardown; ignore.
            break
        time.sleep(0.001)


def _time_ms(fn: Callable[[], None]) -> float:
    t0 = time.perf_counter()
    fn()
    return (time.perf_counter() - t0) * 1000.0


def run_renderer_benchmark(
    *,
    renderer: str,
    row_count: int,
    window_size: tuple[int, int] = (1600, 900),
    motion_mode: str = MOTION_OFF,
    visible_hint: int = VISIBLE_ROWS_DEFAULT,
) -> RendererResult:
    """Run one isolated QML research window and collect timings."""
    if renderer not in RENDERERS:
        raise ValueError(f"Unknown renderer: {renderer}")
    if motion_mode not in MOTION_MODES:
        raise ValueError(f"Unknown motion mode: {motion_mode}")
    _require_pyside6()

    from PySide6.QtCore import QByteArray, QObject, QUrl, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    if renderer == RENDERER_QSG:
        _ensure_qsg_registered()

    engine = QQmlEngine()
    model = _make_envelope_model(row_count)
    engine.rootContext().setContextProperty("researchModel", model)

    if renderer == RENDERER_CACHED:
        provider = _WaveformImageProvider(width=180, height=22)
        engine.addImageProvider("waveform-research", provider.provider)

    component = QQmlComponent(engine)
    component.setData(
        QByteArray(_qml_list_document(renderer=renderer, motion_mode=motion_mode).encode("utf-8")),
        QUrl("qrc:/waveform-research.qml"),
    )
    if component.isError():
        raise RuntimeError(
            "QML research component error: " + "; ".join(e.toString() for e in component.errors())
        )

    window = component.create()
    if window is None:
        raise RuntimeError("Failed to create research window")
    window.setWidth(window_size[0])
    window.setHeight(window_size[1])
    # Avoid stealing focus / modal hangs in automated runs.
    try:
        window.setFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
    except Exception:
        pass
    window.show()

    notes = ""
    if renderer == RENDERER_SHAPE:
        notes = "Shape PathSvg rebuild on active playhead; triangulation cost under motion."
    if renderer == RENDERER_CACHED:
        notes = "Static ImageProvider bitmap + separate playhead Rectangle overlay."
    if renderer == RENDERER_QSG:
        notes = "Python QQuickItem + QSGGeometry line bars; higher integration complexity."

    initial_ms = _time_ms(lambda: _settle(app, ms=60))

    list_view = window.findChild(QObject, "researchList")
    if list_view is None:
        window.close()
        raise RuntimeError("researchList missing")

    def _scroll():
        h = float(list_view.property("contentHeight") or 0)
        vh = float(list_view.property("height") or 1)
        list_view.setProperty("contentY", max(0.0, h - vh))
        _settle(app, ms=30)

    scroll_ms = _time_ms(_scroll)

    def _burst():
        h = float(list_view.property("contentHeight") or 0)
        vh = float(list_view.property("height") or 1)
        max_y = max(0.0, h - vh)
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0, 0.1, 0.9, 0.0):
            list_view.setProperty("contentY", max_y * frac)
            app.processEvents()

    scroll_burst_ms = _time_ms(_burst)
    selection_ms = _time_ms(
        lambda: (window.setProperty("selectedIndex", min(5, max(0, row_count - 1))), _settle(app, ms=15))
    )

    def _keyboard_nav():
        for i in range(min(20, row_count)):
            window.setProperty("selectedIndex", i)
            app.processEvents()

    keyboard_nav_ms = _time_ms(_keyboard_nav)
    preview_start_ms = _time_ms(
        lambda: (
            window.setProperty("playingIndex", min(3, max(0, row_count - 1))),
            _settle(app, ms=20),
        )
    )

    def _motion_frames():
        for step in range(12):
            window.setProperty("playheadNorm", (step % 10) / 10.0)
            app.processEvents()

    if motion_mode == MOTION_OFF:
        active_motion_frame_ms = 0.0
    else:
        active_motion_frame_ms = _time_ms(_motion_frames) / 12.0

    creations = int(window.property("delegateCreations") or 0)
    # Stop motion timer before pool check: offscreen/pooled rows must not keep timers.
    window.setProperty("playingIndex", -1)
    list_view.setProperty("contentY", 0)
    _settle(app, ms=25)
    pooled_timers = int(window.property("activeTimers") or 0)

    result = RendererResult(
        renderer=renderer,
        window_width=window_size[0],
        window_height=window_size[1],
        row_count=row_count,
        visible_rows=visible_hint,
        motion_mode=motion_mode,
        initial_ms=round(initial_ms, 3),
        scroll_ms=round(scroll_ms, 3),
        scroll_burst_ms=round(scroll_burst_ms, 3),
        selection_ms=round(selection_ms, 3),
        keyboard_nav_ms=round(keyboard_nav_ms, 3),
        preview_start_ms=round(preview_start_ms, 3),
        active_motion_frame_ms=round(active_motion_frame_ms, 3),
        delegate_creations=creations,
        virtualized=creations < row_count,
        pooled_timers_active=pooled_timers,
        notes=notes,
    )
    window.close()
    engine.deleteLater()
    app.processEvents()
    return result


def capture_visual_states(
    *,
    renderer: str,
    evidence_dir: Path,
    motion_mode: str = MOTION_ON,
) -> dict[str, Path]:
    """Capture normal/hover/selected/playing stills for one renderer."""
    _require_pyside6()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    from PySide6.QtCore import QByteArray, QUrl, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    if renderer == RENDERER_QSG:
        _ensure_qsg_registered()

    engine = QQmlEngine()
    model = _make_envelope_model(40)
    engine.rootContext().setContextProperty("researchModel", model)
    if renderer == RENDERER_CACHED:
        provider = _WaveformImageProvider()
        engine.addImageProvider("waveform-research", provider.provider)

    component = QQmlComponent(engine)
    component.setData(
        QByteArray(_qml_list_document(renderer=renderer, motion_mode=motion_mode).encode("utf-8")),
        QUrl("qrc:/waveform-research-capture.qml"),
    )
    if component.isError():
        raise RuntimeError("; ".join(e.toString() for e in component.errors()))
    window = component.create()
    window.setWidth(1600)
    window.setHeight(900)
    try:
        window.setFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
    except Exception:
        pass
    window.show()
    _settle(app, ms=80)

    paths: dict[str, Path] = {}

    def _grab(label: str) -> None:
        target = evidence_dir / f"{renderer}-{label}.png"
        img = window.grabWindow()
        img.save(str(target), "PNG")
        paths[label] = target

    window.setProperty("selectedIndex", -1)
    window.setProperty("playingIndex", -1)
    window.setProperty("hoveredIndex", -1)
    _settle(app, ms=30)
    _grab("normal")
    window.setProperty("hoveredIndex", 2)
    _settle(app, ms=30)
    _grab("hovered")
    window.setProperty("selectedIndex", 2)
    _settle(app, ms=30)
    _grab("selected")
    window.setProperty("playingIndex", 2)
    window.setProperty("playheadNorm", 0.35)
    _settle(app, ms=30)
    _grab("active-preview")
    window.setProperty("playingIndex", -1)
    window.close()
    engine.deleteLater()
    app.processEvents()
    return paths


def _median_field(
    rows: Sequence[Mapping[str, Any]],
    renderer: str,
    field: str,
    *,
    motion: str | None = None,
) -> float | None:
    vals = [
        float(r[field])
        for r in rows
        if r.get("renderer") == renderer and (motion is None or r.get("motion_mode") == motion)
    ]
    if not vals:
        return None
    return float(statistics.median(vals))


def classify_from_results(
    results: Sequence[Mapping[str, Any]],
    fifty_k: Sequence[Mapping[str, Any]],
) -> str:
    """Decide EXIT classification from measured deltas (no vibes-only ranking)."""
    canvas_scroll = _median_field(results, RENDERER_CANVAS, "scroll_ms", motion=MOTION_OFF)
    cached_scroll = _median_field(results, RENDERER_CACHED, "scroll_ms", motion=MOTION_OFF)
    shape_scroll = _median_field(results, RENDERER_SHAPE, "scroll_ms", motion=MOTION_OFF)
    qsg_scroll = _median_field(results, RENDERER_QSG, "scroll_ms", motion=MOTION_OFF)
    canvas_motion = _median_field(results, RENDERER_CANVAS, "active_motion_frame_ms", motion=MOTION_ON)
    cached_motion = _median_field(results, RENDERER_CACHED, "active_motion_frame_ms", motion=MOTION_ON)
    shape_motion = _median_field(results, RENDERER_SHAPE, "active_motion_frame_ms", motion=MOTION_ON)

    if None in (canvas_scroll, cached_scroll, shape_scroll, qsg_scroll):
        return "INCONCLUSIVE — missing baseline scroll timings"

    fifty_ok = True
    if fifty_k:
        for row in fifty_k:
            if not row.get("virtualized"):
                fifty_ok = False
    if not fifty_ok:
        return "INCONCLUSIVE — 50k virtualization failed for a candidate"

    # Clear QSG win only if substantially faster than both canvas and cached.
    if qsg_scroll < cached_scroll * 0.75 and qsg_scroll < canvas_scroll * 0.75:
        return "MOVE_TO_SCENE_GRAPH_GEOMETRY"

    shape_rejected = shape_scroll > canvas_scroll * 1.35 or (
        shape_motion is not None
        and canvas_motion is not None
        and shape_motion > canvas_motion * 2.0
    )
    cached_better_or_equal = cached_scroll <= canvas_scroll * 1.05
    motion_ok = cached_motion is not None and (
        canvas_motion is None or cached_motion <= canvas_motion * 1.25
    )

    if cached_better_or_equal and motion_ok:
        # Static body + active overlay is the hybrid production path.
        return "HYBRID_RENDERER"
    if shape_rejected and not cached_better_or_equal:
        return "KEEP_CANVAS_PLUS_ACTIVE_OVERLAY"
    if cached_better_or_equal:
        return "MOVE_TO_CACHED_STATIC_RENDERING"
    return "KEEP_CANVAS_PLUS_ACTIVE_OVERLAY"


def scorecard_from_results(results: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    """Human-readable scorecard derived from measured medians."""
    out: dict[str, dict[str, str]] = {}
    canvas_scroll = _median_field(results, RENDERER_CANVAS, "scroll_ms", motion=MOTION_OFF) or 1.0
    canvas_motion = _median_field(results, RENDERER_CANVAS, "active_motion_frame_ms", motion=MOTION_ON) or 1.0
    for renderer in RENDERERS:
        scroll = _median_field(results, renderer, "scroll_ms", motion=MOTION_OFF) or 0.0
        motion = _median_field(results, renderer, "active_motion_frame_ms", motion=MOTION_ON) or 0.0
        virt_rows = [r for r in results if r.get("renderer") == renderer]
        virt_ok = all(bool(r.get("virtualized")) for r in virt_rows) if virt_rows else False
        scroll_ratio = scroll / canvas_scroll if canvas_scroll else 1.0
        motion_ratio = motion / canvas_motion if canvas_motion else 1.0

        def band(ratio: float) -> str:
            if ratio <= 1.05:
                return "gut"
            if ratio <= 1.35:
                return "mittel"
            return "schlecht"

        complexity = {
            RENDERER_CANVAS: "niedrig",
            RENDERER_SHAPE: "mittel",
            RENDERER_CACHED: "niedrig",
            RENDERER_QSG: "hoch",
        }[renderer]
        maintain = {
            RENDERER_CANVAS: "gut",
            RENDERER_SHAPE: "mittel",
            RENDERER_CACHED: "gut",
            RENDERER_QSG: "schlecht",
        }[renderer]
        visual = {
            RENDERER_CANVAS: "mittel",
            RENDERER_SHAPE: "hoch",
            RENDERER_CACHED: "hoch",
            RENDERER_QSG: "hoch",
        }[renderer]
        risk = {
            RENDERER_CANVAS: "niedrig",
            RENDERER_SHAPE: "mittel",
            RENDERER_CACHED: "niedrig",
            RENDERER_QSG: "hoch",
        }[renderer]
        out[renderer] = {
            "PERFORMANCE": band(scroll_ratio),
            "SCROLL": band(scroll_ratio),
            "ACTIVE_MOTION_COST": band(motion_ratio) if motion > 0 else "gut",
            "POOLING_SAFETY": "gut" if virt_ok else "schlecht",
            "IMPLEMENTATION_COMPLEXITY": complexity,
            "MAINTAINABILITY": maintain,
            "VISUAL_POTENTIAL": visual,
            "PRODUCTION_RISK": risk,
        }
    return out


def run_spike_suite(
    *,
    evidence_dir: Path | None = None,
    include_50k: bool = True,
    capture_visuals: bool = True,
) -> dict[str, Any]:
    """Run the full #695 measurement matrix and optionally write evidence."""
    evidence_dir = evidence_dir or Path(os.environ.get("TEMP", "/tmp")) / "sample-brain-695-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for renderer in RENDERERS:
        for motion in (MOTION_OFF, MOTION_ON):
            row_count = 400
            print(f"[695] benchmark {renderer} motion={motion} rows={row_count}", flush=True)
            res = run_renderer_benchmark(
                renderer=renderer,
                row_count=row_count,
                window_size=(1600, 900),
                motion_mode=motion,
            )
            results.append(asdict(res))

    for width, height in WINDOW_SIZES[1:]:
        for renderer in (RENDERER_CANVAS, RENDERER_CACHED):
            print(f"[695] geometry {renderer} {width}x{height}", flush=True)
            res = run_renderer_benchmark(
                renderer=renderer,
                row_count=300,
                window_size=(width, height),
                motion_mode=MOTION_OFF,
            )
            results.append(asdict(res))

    fifty_k: list[dict[str, Any]] = []
    if include_50k:
        for renderer in (RENDERER_CANVAS, RENDERER_CACHED, RENDERER_QSG):
            print(f"[695] 50k {renderer}", flush=True)
            res = run_renderer_benchmark(
                renderer=renderer,
                row_count=50_000,
                window_size=(1600, 900),
                motion_mode=MOTION_OFF,
            )
            fifty_k.append(asdict(res))

    visuals: dict[str, dict[str, str]] = {}
    if capture_visuals:
        for renderer in RENDERERS:
            print(f"[695] visuals {renderer}", flush=True)
            try:
                paths = capture_visual_states(
                    renderer=renderer,
                    evidence_dir=evidence_dir / "visuals" / renderer,
                    motion_mode=MOTION_ON,
                )
                visuals[renderer] = {k: str(v) for k, v in paths.items()}
            except Exception as exc:  # pragma: no cover
                visuals[renderer] = {"error": str(exc)}

    classification = classify_from_results(results, fifty_k)
    report = {
        "schema": "sample_brain_waveform_research_695",
        "issue": 695,
        "seed": SEED,
        "points": POINTS,
        "results": results,
        "fifty_k": fifty_k,
        "visuals": visuals,
        "scorecard": scorecard_from_results(results),
        "exit_classification": classification,
    }
    out = evidence_dir / "manifest-695.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["manifest_path"] = str(out)
    return report


__all__ = [
    "MOTION_MODES",
    "RENDERERS",
    "RendererResult",
    "build_envelopes",
    "capture_visual_states",
    "classify_from_results",
    "run_renderer_benchmark",
    "run_spike_suite",
    "scorecard_from_results",
    "synthetic_envelope",
]


def _main() -> int:
    evidence = Path(os.environ.get("SAMPLE_BRAIN_695_EVIDENCE", ""))
    if not str(evidence):
        evidence = Path(os.environ.get("TEMP", "/tmp")) / "sample-brain-695-evidence"
    report = run_spike_suite(evidence_dir=evidence, include_50k=True, capture_visuals=True)
    print(
        json.dumps(
            {
                "manifest": report.get("manifest_path"),
                "exit": report.get("exit_classification"),
                "scorecard": report.get("scorecard"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
