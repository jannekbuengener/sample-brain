"""Pure validation for the privacy-safe Diagnostic Bundle V1 contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import re
from typing import Any

from .measurement.contract import (
    FORBIDDEN_PROP_KEYS,
    MeasurementEvent,
    PrivacyClass,
    PROCESS_FAILURE_COMPONENTS,
    SUPPORTED_STATUSES,
    _canonical_uuid4_ok,
    _GIT_SHA_PATTERN,
    _PRIVATE_PATH,
    _REASON_CODE_PATTERN,
    _safe_token_ok,
    _utc_ms_z_ok,
    validate_event,
)


DIAGNOSTIC_BUNDLE_DOCUMENT_TYPE = "sample_brain.diagnostic_bundle"
DIAGNOSTIC_BUNDLE_SCHEMA_VERSION = "1.0.0"

_TOP_LEVEL_FIELDS = frozenset(
    {
        "document_type",
        "schema_version",
        "run_id",
        "session_id",
        "app",
        "outcome",
        "last_events",
        "qt_summary",
        "native_summary",
        "measurement_events",
    }
)
_APP_FIELDS = frozenset(
    {
        "app_version",
        "git_sha",
        "python_version",
        "qt_version",
        "renderer",
        "platform",
    }
)
_OUTCOME_FIELDS = frozenset({"exit_code", "failure_class", "reason_code"})
_LAST_EVENT_FIELDS = frozenset(
    {
        "seq",
        "occurred_at",
        "monotonic_ns",
        "component",
        "event",
        "status",
        "reason_code",
    }
)
_QT_SUMMARY_FIELDS = frozenset(
    {
        "debug_count",
        "info_count",
        "warning_count",
        "critical_count",
        "fatal_count",
        "codes",
    }
)
_NATIVE_SUMMARY_FIELDS = frozenset(
    {
        "buffer_size",
        "callback_mean_us",
        "callback_p95_us",
        "xrun_count",
        "underflow_count",
        "overflow_count",
        "active_voice_count",
        "total_voice_count",
        "running",
    }
)
_MEASUREMENT_EVENT_FIELDS = frozenset(
    {
        "document_type",
        "schema_version",
        "event_name",
        "event_version",
        "occurred_at",
        "run_id",
        "session_id",
        "domain",
        "privacy_class",
        "status",
        "reason_code",
        "app",
        "props",
    }
)
_FORBIDDEN_KEYS = FORBIDDEN_PROP_KEYS | frozenset(
    {
        "access_token",
        "credential",
        "credentials",
        "password",
        "qt_message",
        "raw_qt_text",
    }
)
_EVENT_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_MAX_LAST_EVENTS = 128
_MAX_SUMMARY_CODES = 128


def _exact_mapping(value: Any, fields: frozenset[str]) -> bool:
    return isinstance(value, Mapping) and set(value) == fields


def _machine_code(value: Any, *, nullable: bool = False) -> bool:
    if value is None:
        return nullable
    return isinstance(value, str) and _REASON_CODE_PATTERN.fullmatch(value) is not None


def _non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _non_negative_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _privacy_scan(value: Any, active: set[int]) -> bool:
    """Reject forbidden keys, private paths, unsupported values and cycles."""
    if value is None or isinstance(value, (bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, str):
        return _PRIVATE_PATH.search(value) is None
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            return False
        active.add(identity)
        try:
            for key, item in value.items():
                if not isinstance(key, str) or key in _FORBIDDEN_KEYS:
                    return False
                if not _privacy_scan(item, active):
                    return False
            return True
        finally:
            active.remove(identity)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        identity = id(value)
        if identity in active:
            return False
        active.add(identity)
        try:
            return all(_privacy_scan(item, active) for item in value)
        finally:
            active.remove(identity)
    return False


def _app_ok(app: Any) -> bool:
    if not _exact_mapping(app, _APP_FIELDS):
        return False
    if not isinstance(app["app_version"], str) or not _safe_token_ok(
        app["app_version"]
    ):
        return False
    if not isinstance(app["python_version"], str) or not _safe_token_ok(
        app["python_version"]
    ):
        return False
    qt_version = app["qt_version"]
    if qt_version is not None and not _safe_token_ok(qt_version):
        return False
    git_sha = app["git_sha"]
    if git_sha is not None and (
        not isinstance(git_sha, str) or _GIT_SHA_PATTERN.fullmatch(git_sha) is None
    ):
        return False
    return app["renderer"] in {"qml", "tk"} and app["platform"] in {
        "windows",
        "macos",
        "linux",
    }


def _outcome_ok(outcome: Any) -> bool:
    return (
        _exact_mapping(outcome, _OUTCOME_FIELDS)
        and isinstance(outcome["exit_code"], int)
        and not isinstance(outcome["exit_code"], bool)
        and _machine_code(outcome["failure_class"], nullable=True)
        and _machine_code(outcome["reason_code"], nullable=True)
    )


def _last_events_ok(events: Any) -> bool:
    if not isinstance(events, list) or len(events) > _MAX_LAST_EVENTS:
        return False
    previous_seq: int | None = None
    previous_clock: int | None = None
    for event in events:
        if not _exact_mapping(event, _LAST_EVENT_FIELDS):
            return False
        sequence = event["seq"]
        clock = event["monotonic_ns"]
        if not _non_negative_int(sequence) or not _non_negative_int(clock):
            return False
        if previous_seq is not None and sequence <= previous_seq:
            return False
        if previous_clock is not None and clock < previous_clock:
            return False
        if not _utc_ms_z_ok(event["occurred_at"]):
            return False
        if event["component"] not in PROCESS_FAILURE_COMPONENTS:
            return False
        event_name = event["event"]
        if (
            not isinstance(event_name, str)
            or len(event_name) > 64
            or _EVENT_CODE_PATTERN.fullmatch(event_name) is None
        ):
            return False
        if event["status"] not in SUPPORTED_STATUSES:
            return False
        if not _machine_code(event["reason_code"], nullable=True):
            return False
        previous_seq = sequence
        previous_clock = clock
    return True


def _qt_summary_ok(summary: Any) -> bool:
    if not isinstance(summary, Mapping) or set(summary) - _QT_SUMMARY_FIELDS:
        return False
    for key, value in summary.items():
        if key == "codes":
            if not isinstance(value, list) or len(value) > _MAX_SUMMARY_CODES:
                return False
            if not all(_machine_code(code) for code in value):
                return False
        elif not _non_negative_int(value):
            return False
    return True


def _native_summary_ok(summary: Any) -> bool:
    if not isinstance(summary, Mapping) or set(summary) - _NATIVE_SUMMARY_FIELDS:
        return False
    for key, value in summary.items():
        if key == "running":
            if not isinstance(value, bool):
                return False
        elif key == "buffer_size":
            if not _non_negative_int(value) or value == 0:
                return False
        elif key in {"callback_mean_us", "callback_p95_us"}:
            if not _non_negative_number(value):
                return False
        elif not _non_negative_int(value):
            return False
    return True


def _measurement_events_ok(events: Any) -> bool:
    if not isinstance(events, list):
        return False
    for raw_event in events:
        if not _exact_mapping(raw_event, _MEASUREMENT_EVENT_FIELDS):
            return False
        event = MeasurementEvent(**dict(raw_event))
        if validate_event(event) is None:
            return False
        if event.privacy_class not in {
            PrivacyClass.EXPORT_SAFE,
            PrivacyClass.EXPORT_SAFE.value,
        }:
            return False
    return True


def validate_diagnostic_bundle(bundle: Mapping[str, Any]) -> bool:
    """Return whether *bundle* satisfies Diagnostic Bundle V1; never raise."""
    try:
        if not _exact_mapping(bundle, _TOP_LEVEL_FIELDS):
            return False
        if not _privacy_scan(bundle, set()):
            return False
        if bundle["document_type"] != DIAGNOSTIC_BUNDLE_DOCUMENT_TYPE:
            return False
        if bundle["schema_version"] != DIAGNOSTIC_BUNDLE_SCHEMA_VERSION:
            return False
        if not _canonical_uuid4_ok(bundle["run_id"]):
            return False
        session_id = bundle["session_id"]
        if session_id is not None and not _canonical_uuid4_ok(session_id):
            return False
        return (
            _app_ok(bundle["app"])
            and _outcome_ok(bundle["outcome"])
            and _last_events_ok(bundle["last_events"])
            and _qt_summary_ok(bundle["qt_summary"])
            and _native_summary_ok(bundle["native_summary"])
            and _measurement_events_ok(bundle["measurement_events"])
        )
    except Exception:
        return False
