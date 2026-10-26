"""Diagnostic Bundle V1 schema and privacy contract tests (#1242)."""

from __future__ import annotations

from copy import deepcopy
import importlib
import math
from typing import Any

import pytest


RUN_ID = "550e8400-e29b-41d4-a716-446655440030"
SESSION_ID = "550e8400-e29b-41d4-a716-446655440031"


def _contract() -> Any:
    try:
        module = importlib.import_module("src.diagnostics_contract")
    except ModuleNotFoundError:
        pytest.fail("src.diagnostics_contract is not implemented")
    return module


def _measurement_event() -> dict[str, Any]:
    return {
        "document_type": "sample_brain.measurement_event",
        "schema_version": "1.0.0",
        "event_name": "process.failure",
        "event_version": 1,
        "occurred_at": "2026-10-21T10:15:30.123Z",
        "run_id": RUN_ID,
        "session_id": SESSION_ID,
        "domain": "eng",
        "privacy_class": "export_safe",
        "status": "error",
        "reason_code": "PYTHON_STARTUP_FAILED",
        "app": {
            "app_version": "0.1.0",
            "git_sha": "abc1234",
            "analyzer_version": None,
            "search_backend": None,
        },
        "props": {"component": "python"},
    }


def _valid_bundle() -> dict[str, Any]:
    return {
        "document_type": "sample_brain.diagnostic_bundle",
        "schema_version": "1.0.0",
        "run_id": RUN_ID,
        "session_id": SESSION_ID,
        "app": {
            "app_version": "0.1.0",
            "git_sha": "abc1234",
            "python_version": "3.12.10",
            "qt_version": "6.8.3",
            "renderer": "qml",
            "platform": "windows",
        },
        "outcome": {
            "exit_code": 1,
            "failure_class": "STARTUP_FAILURE",
            "reason_code": "PYTHON_STARTUP_FAILED",
        },
        "last_events": [
            {
                "seq": 1,
                "occurred_at": "2026-10-21T10:15:30.123Z",
                "monotonic_ns": 123456,
                "component": "python",
                "event": "process.failure",
                "status": "error",
                "reason_code": "PYTHON_STARTUP_FAILED",
            }
        ],
        "qt_summary": {
            "debug_count": 0,
            "info_count": 1,
            "warning_count": 2,
            "critical_count": 0,
            "fatal_count": 0,
            "codes": ["QML_BINDING_WARNING"],
        },
        "native_summary": {
            "buffer_size": 256,
            "callback_mean_us": 125.5,
            "callback_p95_us": 220.0,
            "xrun_count": 0,
            "underflow_count": 0,
            "overflow_count": 0,
            "active_voice_count": 1,
            "total_voice_count": 2,
            "running": False,
        },
        "measurement_events": [_measurement_event()],
    }


def _validate(bundle: Any) -> bool:
    return bool(_contract().validate_diagnostic_bundle(bundle))


def test_public_contract_identity_is_frozen() -> None:
    contract = _contract()
    assert (
        contract.DIAGNOSTIC_BUNDLE_DOCUMENT_TYPE
        == "sample_brain.diagnostic_bundle"
    )
    assert contract.DIAGNOSTIC_BUNDLE_SCHEMA_VERSION == "1.0.0"
    assert callable(contract.validate_diagnostic_bundle)


def test_valid_diagnostic_bundle_is_accepted() -> None:
    assert _validate(_valid_bundle())


def test_null_session_id_is_accepted() -> None:
    bundle = _valid_bundle()
    bundle["session_id"] = None
    assert _validate(bundle)


def test_unknown_top_level_field_is_rejected() -> None:
    bundle = _valid_bundle()
    bundle["extra"] = 1
    assert not _validate(bundle)


@pytest.mark.parametrize(
    "field,value",
    [
        ("document_type", "sample_brain.other"),
        ("schema_version", "2.0.0"),
        ("run_id", "not-a-uuid"),
        ("run_id", "550e8400-e29b-41d4-c716-446655440030"),
        ("session_id", "not-a-uuid"),
    ],
)
def test_identity_fields_fail_closed(field: str, value: object) -> None:
    bundle = _valid_bundle()
    bundle[field] = value
    assert not _validate(bundle)


def test_last_events_limit_is_exactly_128() -> None:
    bundle = _valid_bundle()
    prototype = bundle["last_events"][0]
    bundle["last_events"] = [
        {
            **prototype,
            "seq": index,
            "monotonic_ns": index,
        }
        for index in range(128)
    ]
    assert _validate(bundle)
    bundle["last_events"].append(
        {**prototype, "seq": 128, "monotonic_ns": 128}
    )
    assert not _validate(bundle)


def test_last_events_require_monotonic_seq_and_clock() -> None:
    bundle = _valid_bundle()
    event = bundle["last_events"][0]
    bundle["last_events"] = [
        {**event, "seq": 2, "monotonic_ns": 20},
        {**event, "seq": 1, "monotonic_ns": 10},
    ]
    assert not _validate(bundle)


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-21T10:15:30Z",
        "2026-10-21T10:15:30.123+00:00",
        "2026-13-21T10:15:30.123Z",
        "not-a-timestamp",
    ],
)
def test_last_event_timestamp_uses_measurement_semantics(value: str) -> None:
    bundle = _valid_bundle()
    bundle["last_events"][0]["occurred_at"] = value
    assert not _validate(bundle)


@pytest.mark.parametrize(
    "field,value",
    [
        ("component", "operator laptop"),
        ("component", "device"),
        ("event", "free text"),
        ("event", "Process.Failure"),
        ("status", "failed badly"),
        ("reason_code", "C:/Users/operator/private"),
    ],
)
def test_last_event_machine_fields_reject_free_text(
    field: str, value: object
) -> None:
    bundle = _valid_bundle()
    bundle["last_events"][0][field] = value
    assert not _validate(bundle)


@pytest.mark.parametrize(
    "field,value",
    [
        ("exit_code", True),
        ("failure_class", "Startup failed badly"),
        ("reason_code", "python startup failed"),
    ],
)
def test_outcome_requires_typed_exit_and_machine_codes(
    field: str, value: object
) -> None:
    bundle = _valid_bundle()
    bundle["outcome"][field] = value
    assert not _validate(bundle)


def test_nullable_outcome_codes_are_accepted() -> None:
    bundle = _valid_bundle()
    bundle["outcome"]["failure_class"] = None
    bundle["outcome"]["reason_code"] = None
    assert _validate(bundle)


@pytest.mark.parametrize(
    "field,value",
    [
        ("renderer", "web"),
        ("platform", "operator-pc"),
        ("git_sha", "g123456"),
        ("app_version", ""),
        ("app_version", None),
        ("python_version", "3.12 private"),
        ("python_version", None),
    ],
)
def test_app_provenance_is_allowlisted_and_tokenized(
    field: str, value: object
) -> None:
    bundle = _valid_bundle()
    bundle["app"][field] = value
    assert not _validate(bundle)


def test_app_rejects_unknown_identity_field() -> None:
    bundle = _valid_bundle()
    bundle["app"]["username"] = "operator"
    assert not _validate(bundle)


def test_empty_plane_summaries_are_accepted() -> None:
    bundle = _valid_bundle()
    bundle["qt_summary"] = {}
    bundle["native_summary"] = {}
    assert _validate(bundle)


def test_last_event_code_is_bounded() -> None:
    bundle = _valid_bundle()
    bundle["last_events"][0]["event"] = "process." + ("x" * 65)
    assert not _validate(bundle)


@pytest.mark.parametrize(
    "path",
    [
        "C:/Users/operator/private.log",
        r"\\server\share\private.log",
        "/home/operator/private.log",
        "/Users/operator/private.log",
        "/tmp/private.log",
    ],
)
def test_private_absolute_paths_are_rejected_recursively(path: str) -> None:
    bundle = _valid_bundle()
    bundle["app"]["app_version"] = path
    assert not _validate(bundle)


@pytest.mark.parametrize(
    "leak_case",
    [
        "last_event_message",
        "last_event_exception",
        "last_event_traceback",
        "qt_raw_text",
        "native_device",
        "app_hostname",
        "measurement_sample_id",
        "measurement_query",
        "measurement_secret",
    ],
)
def test_forbidden_identity_and_raw_text_keys_are_rejected_recursively(
    leak_case: str,
) -> None:
    bundle = _valid_bundle()
    if leak_case == "last_event_message":
        bundle["last_events"][0]["message"] = "raw text"
    elif leak_case == "last_event_exception":
        bundle["last_events"][0]["exception"] = "ValueError"
    elif leak_case == "last_event_traceback":
        bundle["last_events"][0]["traceback"] = "trace"
    elif leak_case == "qt_raw_text":
        bundle["qt_summary"]["raw_qt_text"] = "binding failed"
    elif leak_case == "native_device":
        bundle["native_summary"]["device_name"] = "private device"
    elif leak_case == "app_hostname":
        bundle["app"]["hostname"] = "operator-pc"
    elif leak_case == "measurement_sample_id":
        bundle["measurement_events"][0]["props"]["sample_id"] = "sample-1"
    elif leak_case == "measurement_query":
        bundle["measurement_events"][0]["props"]["query"] = "private prompt"
    else:
        bundle["measurement_events"][0]["app"]["token"] = "secret-value"
    assert not _validate(bundle)


def test_qt_summary_allows_counts_and_codes_only() -> None:
    bundle = _valid_bundle()
    bundle["qt_summary"]["warning_count"] = -1
    assert not _validate(bundle)
    bundle = _valid_bundle()
    bundle["qt_summary"]["codes"] = ["free text warning"]
    assert not _validate(bundle)
    bundle = _valid_bundle()
    bundle["qt_summary"]["other_count"] = 1
    assert not _validate(bundle)


@pytest.mark.parametrize(
    "field,value",
    [
        ("buffer_size", 0),
        ("callback_mean_us", math.inf),
        ("callback_p95_us", -1.0),
        ("xrun_count", True),
        ("active_voice_count", -1),
        ("running", 1),
    ],
)
def test_native_summary_allows_safe_scalar_counters_only(
    field: str, value: object
) -> None:
    bundle = _valid_bundle()
    bundle["native_summary"][field] = value
    assert not _validate(bundle)


def test_native_summary_rejects_unknown_field() -> None:
    bundle = _valid_bundle()
    bundle["native_summary"]["device_id"] = "private-device"
    assert not _validate(bundle)


def test_embedded_measurement_event_is_revalidated() -> None:
    bundle = _valid_bundle()
    bundle["measurement_events"][0]["run_id"] = "bad-run"
    assert not _validate(bundle)


@pytest.mark.parametrize("event_version", [True, 2, 99])
def test_embedded_measurement_event_version_is_exactly_v1(
    event_version: object,
) -> None:
    bundle = _valid_bundle()
    bundle["measurement_events"][0]["event_version"] = event_version
    assert not _validate(bundle)


def test_embedded_measurement_event_must_be_export_safe() -> None:
    bundle = _valid_bundle()
    bundle["measurement_events"][0]["privacy_class"] = "local_only"
    assert not _validate(bundle)


def test_embedded_measurement_event_rejects_unknown_envelope_field() -> None:
    bundle = _valid_bundle()
    bundle["measurement_events"][0]["message"] = "raw failure"
    assert not _validate(bundle)


@pytest.mark.parametrize(
    "malformed",
    [None, [], "bundle", 1, object()],
)
def test_malformed_input_returns_false_without_raising(malformed: object) -> None:
    assert not _validate(malformed)


def test_recursive_container_is_rejected_without_raising() -> None:
    bundle = _valid_bundle()
    recursive: list[Any] = []
    recursive.append(recursive)
    bundle["qt_summary"]["codes"] = recursive
    assert not _validate(bundle)
