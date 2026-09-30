"""Qt bridge projecting #694 elastic layout solver into QML."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping

from .workbench_layout_solver import (
    CANONICAL_DEFAULT_RATIOS,
    HANDLE_WIDTH_PX,
    apply_divider_drag,
    load_layout_preferences,
    normalize_ratios,
    save_layout_preferences,
    solve_widths,
)

# Fixed No-Source Library width when revealed (#725 Opened-no-source).
# Not a ratio authority — elastic solve applies only with has_active_source.
OPENED_NO_SOURCE_LIBRARY_WIDTH_PX = 300.0


def create_elastic_layout_bridge(
    *,
    state_dir: Path | None = None,
    harmony_open: Callable[[], bool],
    has_active_source: Callable[[], bool],
    library_revealed: Callable[[], bool] | None = None,
    live_kit_visible: Callable[[], bool] | None = None,
    on_changed: Callable[[], None] | None = None,
):
    """Thin QObject projection; solver remains the layout authority."""
    from PySide6.QtCore import Property, QObject, Signal, Slot

    loaded = load_layout_preferences(state_dir=state_dir)
    ratios = dict(loaded.ratios)
    content_width = 1600.0
    widths = {
        "library": 300.0,
        "browser": 800.0,
        "harmony": 0.0,
        "livekit": 300.0,
    }
    persistable = bool(loaded.persistable)
    layout_revision = 0
    # Default True preserves legacy active-workspace callers; production passes
    # #725 library_revealed so collapsed Library reserves no elastic width.
    revealed = library_revealed if library_revealed is not None else (lambda: True)
    # Default True preserves pre-#742 bridge callers; production passes disclosure.
    kit_visible = live_kit_visible if live_kit_visible is not None else (lambda: True)

    class ElasticLayoutBridge(QObject):
        changed = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._recompute()

        def _emit(self) -> None:
            nonlocal layout_revision
            layout_revision += 1
            self.changed.emit()
            if on_changed is not None:
                on_changed()

        def _recompute(self) -> None:
            nonlocal widths
            if not bool(has_active_source()):
                # #725 No-Source presentation only — never touches stored ratios.
                library_w = (
                    OPENED_NO_SOURCE_LIBRARY_WIDTH_PX if bool(revealed()) else 0.0
                )
                widths = {
                    "library": library_w,
                    "browser": 0.0,
                    "harmony": 0.0,
                    "livekit": 0.0,
                }
                return
            solution = solve_widths(
                ratios,
                available_width=max(content_width, 1.0),
                harmony_open=bool(harmony_open()),
                has_active_source=True,
                library_visible=bool(revealed()),
                live_kit_visible=bool(kit_visible()),
            )
            widths = {
                "library": float(solution.widths.get("library", 0.0)),
                "browser": float(solution.widths.get("browser", 0.0)),
                "harmony": float(solution.widths.get("harmony", 0.0)),
                "livekit": float(solution.widths.get("livekit", 0.0)),
            }

        @Property(int, notify=changed)
        def layoutRevision(self) -> int:
            return int(layout_revision)

        @Property(float, notify=changed)
        def handleWidth(self) -> float:
            return float(HANDLE_WIDTH_PX)

        @Property(float, notify=changed)
        def libraryWidth(self) -> float:
            return widths["library"]

        @Property(float, notify=changed)
        def browserWidth(self) -> float:
            return widths["browser"]

        @Property(float, notify=changed)
        def harmonyWidth(self) -> float:
            return widths["harmony"] if harmony_open() else 0.0

        @Property(float, notify=changed)
        def liveKitWidth(self) -> float:
            return widths["livekit"]

        @Slot(float)
        def setContentWidth(self, width: float) -> None:
            nonlocal content_width
            value = float(width)
            if value <= 0 or value == content_width:
                return
            content_width = value
            self._recompute()
            self._emit()

        @Slot()
        def syncFromInteraction(self) -> None:
            self._recompute()
            self._emit()

        @Slot(str, float)
        def applyDrag(self, divider_after: str, delta_px: float) -> None:
            nonlocal ratios
            if not has_active_source():
                return
            ratios = apply_divider_drag(
                ratios,
                divider_after=str(divider_after),
                delta_px=float(delta_px),
                available_width=max(content_width, 1.0),
                harmony_open=bool(harmony_open()),
                has_active_source=True,
                library_visible=bool(revealed()),
                live_kit_visible=bool(kit_visible()),
            )
            self._recompute()
            self._emit()

        @Slot()
        def endDrag(self) -> None:
            nonlocal persistable
            if not persistable:
                # Still attempt write after a good session; corrupt load only
                # blocks claiming prior state was valid.
                persistable = True
            try:
                save_layout_preferences(ratios, state_dir=state_dir)
                persistable = True
            except OSError:
                persistable = False

        def current_ratios(self) -> Mapping[str, float]:
            return normalize_ratios(ratios)

    return ElasticLayoutBridge()


__all__ = [
    "CANONICAL_DEFAULT_RATIOS",
    "OPENED_NO_SOURCE_LIBRARY_WIDTH_PX",
    "create_elastic_layout_bridge",
]
