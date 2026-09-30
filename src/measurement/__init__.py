"""Provider-neutral Measurement Contract v1 (ADR-0006)."""

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
from .reader import MeasurementReader, ReadStatus
from .report import (
    StageFinishedReport,
    build_stage_finished_report,
    format_report_text,
    report_to_dict,
)
from .sinks import NullSink, SidecarSqliteSink
from .stats import percentile

__all__ = [
    "FORBIDDEN_PROP_KEYS",
    "STAGE_FINISHED_ALLOWED_PROPS",
    "MeasurementBus",
    "MeasurementEvent",
    "MeasurementMode",
    "MeasurementReader",
    "NullSink",
    "PrivacyClass",
    "ReadStatus",
    "SidecarSqliteSink",
    "StageFinishedReport",
    "build_stage_finished_report",
    "emit_pipeline_stage_finished",
    "format_report_text",
    "percentile",
    "record_analyze_stage_safe",
    "report_to_dict",
    "resolve_measurement_db_path",
    "resolve_measurement_mode",
    "validate_event",
]
