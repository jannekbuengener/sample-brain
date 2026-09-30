"""Fail-soft measurement bus (ADR-0006)."""

from __future__ import annotations

from typing import Optional

from .config import MeasurementMode
from .contract import MeasurementEvent, validate_event
from .sinks import MeasurementSink, NullSink


class MeasurementBus:
    def __init__(self, *, mode: MeasurementMode, sink: Optional[MeasurementSink] = None) -> None:
        self.mode = mode
        if mode is MeasurementMode.OFF:
            self.sink: MeasurementSink = NullSink()
        else:
            self.sink = sink if sink is not None else NullSink()

    def emit(self, event: MeasurementEvent) -> None:
        try:
            if self.mode is MeasurementMode.OFF:
                return
            valid = validate_event(event)
            if valid is None:
                return
            self.sink.write(valid)
        except Exception:
            return

    def flush(self) -> None:
        try:
            if self.mode is MeasurementMode.OFF:
                return
            self.sink.flush()
        except Exception:
            return
