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
    MATCH_QUERY_FINISHED_ALLOWED_PROPS,
    STAGE_FINISHED_ALLOWED_PROPS,
    MeasurementEvent,
    PrivacyClass,
    validate_event,
)
from .emit import (
    emit_match_query_finished,
    emit_pipeline_stage_finished,
    make_match_query_finished_observer,
    record_analyze_stage_safe,
)
from .reader import MeasurementReader, ReadStatus
from .report import (
    MatchQueryFinishedReport,
    StageFinishedReport,
    build_match_query_finished_report,
    build_stage_finished_report,
    format_match_report_text,
    format_report_text,
    match_report_to_dict,
    report_to_dict,
)
from .sinks import NullSink, SidecarSqliteSink
from .stats import percentile

__all__ = [
    "FORBIDDEN_PROP_KEYS",
    "MATCH_QUERY_FINISHED_ALLOWED_PROPS",
    "STAGE_FINISHED_ALLOWED_PROPS",
    "MatchQueryFinishedReport",
    "MeasurementBus",
    "MeasurementEvent",
    "MeasurementMode",
    "MeasurementReader",
    "NullSink",
    "PrivacyClass",
    "ReadStatus",
    "SidecarSqliteSink",
    "StageFinishedReport",
    "build_match_query_finished_report",
    "build_stage_finished_report",
    "emit_match_query_finished",
    "emit_pipeline_stage_finished",
    "format_match_report_text",
    "format_report_text",
    "make_match_query_finished_observer",
    "match_report_to_dict",
    "percentile",
    "record_analyze_stage_safe",
    "report_to_dict",
    "resolve_measurement_db_path",
    "resolve_measurement_mode",
    "validate_event",
]
