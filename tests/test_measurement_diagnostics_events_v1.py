"""Diagnostics-oriented Measurement event contracts for Slice 1 (#1242)."""

from __future__ import annotations

from dataclasses import replace
import math
from typing import Any, Callable

import pytest

import src.measurement as measurement
import src.measurement.emit as emit_module
from src.measurement.bus import MeasurementBus
from src.measurement.config import MeasurementMode
from src.measurement.contract import MeasurementEvent, PrivacyClass, validate_event


RUN_ID = "550e8400-e29b-41d4-a716-446655440010"
SESSION_ID = "550e8400-e29b-41d4-a716-446655440011"
APP = {
    "app_version": "0.1.0",
    "git_sha": None,
    "analyzer_version": None,
    "search_backend": None,
}


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[MeasurementEvent] = []
        self.flushes = 0

    def write(self, event: MeasurementEvent) -> None:
        self.events.append(event)

    def flush(self) -> None:
        self.flushes += 1


def _bus() -> tuple[MeasurementBus, RecordingSink]:
    sink = RecordingSink()
    return MeasurementBus(mode=MeasurementMode.LOCAL, sink=sink), sink


def _emitter(name: str) -> Callable[..., None]:
    candidate = getattr(emit_module, name, None)
    assert callable(candidate), f"missing Measurement emitter: {name}"
    return candidate


def _event(
    event_name: str,
    *,
    domain: str,
    props: dict[str, Any],
    session_id: str | None = None,
    status: str = "ok",
    reason_code: str | None = None,
    privacy_class: PrivacyClass | str = PrivacyClass.EXPORT_SAFE,
) -> MeasurementEvent:
    return MeasurementEvent(
        document_type="sample_brain.measurement_event",
        schema_version="1.0.0",
        event_name=event_name,
        event_version=1,
        occurred_at="2026-10-21T10:15:30.123Z",
        run_id=RUN_ID,
        session_id=session_id,
        domain=domain,
        privacy_class=privacy_class,
        status=status,
        reason_code=reason_code,
        app=APP,
        props=props,
    )


def _workbench_event(**props: Any) -> MeasurementEvent:
    return _event(
        "workbench.session_finished",
        domain="workbench",
        session_id=SESSION_ID,
        props={"renderer": "qml", "duration_ms_bucket": "1m_5m", **props},
    )


def _rt_event(**props: Any) -> MeasurementEvent:
    return _event(
        "rt.callback_stats",
        domain="rt",
        props={
            "buffer_size": 256,
            "callback_mean_us": 125.5,
            "callback_p95_us": 220,
            "xrun_count": 0,
            **props,
        },
    )


def _failure_event(**props: Any) -> MeasurementEvent:
    return _event(
        "process.failure",
        domain="eng",
        props={"component": "measurement", **props},
        status="error",
        reason_code="MEASUREMENT_SINK_UNAVAILABLE",
    )


@pytest.mark.parametrize("renderer", ["qml", "tk"])
@pytest.mark.parametrize(
    "duration_ms_bucket",
    ["lt_1m", "1m_5m", "5m_15m", "15m_60m", "ge_60m"],
)
def test_workbench_session_finished_accepts_only_frozen_values(
    renderer: str, duration_ms_bucket: str
) -> None:
    event = _workbench_event(
        renderer=renderer, duration_ms_bucket=duration_ms_bucket
    )
    assert validate_event(event) is event


@pytest.mark.parametrize("renderer", ["web", "QML", ""])
def test_workbench_session_finished_rejects_unknown_renderer(renderer: str) -> None:
    assert validate_event(_workbench_event(renderer=renderer)) is None


@pytest.mark.parametrize("duration_ms_bucket", ["60m_plus", "1234", ""])
def test_workbench_session_finished_rejects_unknown_duration_bucket(
    duration_ms_bucket: str,
) -> None:
    assert (
        validate_event(_workbench_event(duration_ms_bucket=duration_ms_bucket))
        is None
    )


def test_workbench_session_finished_requires_session_id() -> None:
    assert validate_event(replace(_workbench_event(), session_id=None)) is None


@pytest.mark.parametrize("buffer_size", [0, -1, 1.5, True])
def test_rt_callback_stats_requires_positive_integer_buffer_size(
    buffer_size: object,
) -> None:
    assert validate_event(_rt_event(buffer_size=buffer_size)) is None


@pytest.mark.parametrize("xrun_count", [-1, 1.5, False])
def test_rt_callback_stats_requires_non_negative_integer_xruns(
    xrun_count: object,
) -> None:
    assert validate_event(_rt_event(xrun_count=xrun_count)) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("callback_mean_us", -0.1),
        ("callback_mean_us", math.inf),
        ("callback_mean_us", math.nan),
        ("callback_mean_us", True),
        ("callback_p95_us", -1),
        ("callback_p95_us", math.inf),
        ("callback_p95_us", False),
    ],
)
def test_rt_callback_stats_requires_finite_non_negative_scalars(
    field: str, value: object
) -> None:
    assert validate_event(_rt_event(**{field: value})) is None


@pytest.mark.parametrize(
    "component",
    [
        "startup",
        "workbench",
        "qml",
        "python",
        "native_audio",
        "measurement",
        "unknown",
    ],
)
def test_process_failure_accepts_frozen_component_allowlist(component: str) -> None:
    event = _failure_event(component=component)
    assert validate_event(event) is event


def test_process_failure_requires_error_status_and_reason_code() -> None:
    assert validate_event(replace(_failure_event(), status="ok")) is None
    assert validate_event(replace(_failure_event(), reason_code=None)) is None


@pytest.mark.parametrize("component", ["audio", "device", "C:/private", ""])
def test_process_failure_rejects_unknown_or_private_component(component: str) -> None:
    assert validate_event(_failure_event(component=component)) is None


@pytest.mark.parametrize(
    "event,wrong_domain",
    [
        (_workbench_event(), "eng"),
        (_rt_event(), "workbench"),
        (_failure_event(), "rt"),
    ],
)
def test_diagnostics_events_reject_wrong_domain(
    event: MeasurementEvent, wrong_domain: str
) -> None:
    assert validate_event(replace(event, domain=wrong_domain)) is None


@pytest.mark.parametrize("event", [_workbench_event(), _rt_event(), _failure_event()])
def test_diagnostics_events_require_export_safe_privacy(
    event: MeasurementEvent,
) -> None:
    assert (
        validate_event(replace(event, privacy_class=PrivacyClass.LOCAL_ONLY)) is None
    )


@pytest.mark.parametrize(
    "event",
    [
        _workbench_event(sample_id="sample-1"),
        _rt_event(device_name="private-device"),
        _failure_event(message="C:/Users/operator/private"),
    ],
)
def test_diagnostics_events_reject_extra_identity_and_free_text_props(
    event: MeasurementEvent,
) -> None:
    assert validate_event(event) is None


@pytest.mark.parametrize(
    "name",
    [
        "emit_workbench_session_finished",
        "emit_rt_callback_stats",
        "emit_process_failure",
    ],
)
def test_diagnostics_emitters_are_public_measurement_api(name: str) -> None:
    assert callable(getattr(measurement, name, None))


def test_workbench_session_finished_emitter_writes_exact_contract() -> None:
    bus, sink = _bus()
    _emitter("emit_workbench_session_finished")(
        bus=bus,
        renderer="qml",
        duration_ms_bucket="1m_5m",
        run_id=RUN_ID,
        session_id=SESSION_ID,
        app=APP,
    )
    assert len(sink.events) == 1
    event = sink.events[0]
    assert event.event_name == "workbench.session_finished"
    assert event.domain == "workbench"
    assert event.props == {"renderer": "qml", "duration_ms_bucket": "1m_5m"}
    assert event.run_id == RUN_ID
    assert event.session_id == SESSION_ID
    assert sink.flushes == 1


def test_rt_callback_stats_emitter_preserves_numeric_types() -> None:
    bus, sink = _bus()
    _emitter("emit_rt_callback_stats")(
        bus=bus,
        buffer_size=256,
        callback_mean_us=125.5,
        callback_p95_us=220.0,
        xrun_count=2,
        run_id=RUN_ID,
        session_id=SESSION_ID,
        app=APP,
    )
    assert len(sink.events) == 1
    assert sink.events[0].props == {
        "buffer_size": 256,
        "callback_mean_us": 125.5,
        "callback_p95_us": 220.0,
        "xrun_count": 2,
    }


def test_process_failure_emitter_always_uses_error_status() -> None:
    bus, sink = _bus()
    _emitter("emit_process_failure")(
        bus=bus,
        component="python",
        reason_code="PYTHON_STARTUP_FAILED",
        run_id=RUN_ID,
        session_id=SESSION_ID,
        app=APP,
    )
    assert len(sink.events) == 1
    event = sink.events[0]
    assert event.status == "error"
    assert event.reason_code == "PYTHON_STARTUP_FAILED"
    assert event.props == {"component": "python"}


def test_invalid_diagnostics_emissions_drop_without_raising() -> None:
    bus, sink = _bus()
    _emitter("emit_workbench_session_finished")(
        bus=bus, renderer="qml", duration_ms_bucket="lt_1m", session_id=None
    )
    _emitter("emit_rt_callback_stats")(
        bus=bus,
        buffer_size=True,
        callback_mean_us=1.0,
        callback_p95_us=2.0,
        xrun_count=0,
    )
    _emitter("emit_process_failure")(
        bus=bus,
        component="C:/private",
        reason_code="PROCESS_FAILED",
    )
    assert sink.events == []


def test_diagnostics_emitters_swallow_sink_failures() -> None:
    class BoomSink:
        def write(self, event: MeasurementEvent) -> None:
            raise RuntimeError("write failed")

        def flush(self) -> None:
            raise RuntimeError("flush failed")

    bus = MeasurementBus(mode=MeasurementMode.LOCAL, sink=BoomSink())
    _emitter("emit_process_failure")(
        bus=bus,
        component="unknown",
        reason_code="UNKNOWN_FAILURE",
        run_id=RUN_ID,
    )
