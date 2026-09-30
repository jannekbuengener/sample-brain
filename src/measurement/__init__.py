"""Provider-neutral Measurement Contract v1 (ADR-0006) — first runtime slice."""

from __future__ import annotations

from .bus import MeasurementBus
from .config import (
    MeasurementMode,
    resolve_measurement_db_path,
    resolve_measurement_mode,
)
from .contract import (
    FORBIDDEN_PROP_KEYS,
    STAGE_FINISHED_ALLOWED_PROPS,
    MeasurementEvent,
    PrivacyClass,
    validate_event,
)
from .emit import emit_pipeline_stage_finished, record_analyze_stage_safe
from .sinks import NullSink, SidecarSqliteSink

__all__ = [
    "FORBIDDEN_PROP_KEYS",
    "STAGE_FINISHED_ALLOWED_PROPS",
    "MeasurementBus",
    "MeasurementEvent",
    "MeasurementMode",
    "NullSink",
    "PrivacyClass",
    "SidecarSqliteSink",
    "emit_pipeline_stage_finished",
    "record_analyze_stage_safe",
    "resolve_measurement_db_path",
    "resolve_measurement_mode",
    "validate_event",
]
