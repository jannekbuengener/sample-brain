"""Local aggregation + formatting for Measurement Local Report v1."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .contract import MeasurementEvent
from .reader import (
    MATCH_QUERY_FINISHED_EVENT_NAME,
    TARGET_EVENT_NAME,
    MeasurementReader,
    ReadCounters,
    ReadStatus,
)
from .stats import percentile


def _wall_summary(values: list[int]) -> dict[str, Optional[float | int]]:
    if not values:
        return {"min": None, "p50": None, "p95": None, "max": None}
    return {
        "min": min(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "max": max(values),
    }


@dataclass
class StageFinishedReport:
    status: ReadStatus
    events: int = 0
    runs: int = 0
    invalid: int = 0
    skipped_unknown: int = 0
    rows_seen: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)
    by_stage: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_app: list[dict[str, Any]] = field(default_factory=list)
    error_code: Optional[str] = None


@dataclass
class MatchQueryFinishedReport:
    status: ReadStatus
    events: int = 0
    runs: int = 0
    invalid: int = 0
    skipped_unknown: int = 0
    rows_seen: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)
    wall_ms: dict[str, Optional[float | int]] = field(
        default_factory=lambda: {"min": None, "p50": None, "p95": None, "max": None}
    )
    result_count: dict[str, Optional[float | int]] = field(
        default_factory=lambda: {"min": None, "p50": None, "p95": None, "max": None}
    )
    by_app: list[dict[str, Any]] = field(default_factory=list)
    error_code: Optional[str] = None


def _aggregate_stage_events(events: list[MeasurementEvent]) -> StageFinishedReport:
    status_counts: dict[str, int] = defaultdict(int)
    run_ids: set[str] = set()
    stage_walls: dict[str, list[int]] = defaultdict(list)
    stage_ok: dict[str, int] = defaultdict(int)
    stage_skip: dict[str, int] = defaultdict(int)
    stage_fail: dict[str, int] = defaultdict(int)
    stage_n: dict[str, int] = defaultdict(int)
    stage_status: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    app_groups: dict[tuple[Any, Any, Any], dict[str, Any]] = {}

    for event in events:
        status_counts[event.status] += 1
        run_ids.add(event.run_id)
        stage = str(event.props.get("stage"))
        stage_n[stage] += 1
        stage_ok[stage] += int(event.props["items_ok"])
        stage_skip[stage] += int(event.props["items_skip"])
        stage_fail[stage] += int(event.props["items_fail"])
        stage_walls[stage].append(int(event.props["wall_ms"]))
        stage_status[stage][event.status] += 1

        app = event.app if isinstance(event.app, dict) else {}
        key = (app.get("app_version"), app.get("analyzer_version"), app.get("git_sha"))
        bucket = app_groups.setdefault(
            key,
            {
                "app_version": key[0],
                "analyzer_version": key[1],
                "git_sha": key[2],
                "events": 0,
                "wall_ms_values": [],
            },
        )
        bucket["events"] += 1
        bucket["wall_ms_values"].append(int(event.props["wall_ms"]))

    by_stage: dict[str, dict[str, Any]] = {}
    for stage, n in stage_n.items():
        by_stage[stage] = {
            "events": n,
            "items_ok_sum": stage_ok[stage],
            "items_skip_sum": stage_skip[stage],
            "items_fail_sum": stage_fail[stage],
            "status_counts": dict(stage_status[stage]),
            "wall_ms": _wall_summary(stage_walls[stage]),
        }

    by_app: list[dict[str, Any]] = []
    for bucket in app_groups.values():
        walls = bucket.pop("wall_ms_values")
        by_app.append({**bucket, "wall_ms": _wall_summary(walls)})
    by_app.sort(
        key=lambda row: (
            str(row.get("app_version") or ""),
            str(row.get("analyzer_version") or ""),
            str(row.get("git_sha") or ""),
        )
    )

    return StageFinishedReport(
        status=ReadStatus.OK,
        events=len(events),
        runs=len(run_ids),
        status_counts=dict(status_counts),
        by_stage=by_stage,
        by_app=by_app,
    )


def _aggregate_match_events(events: list[MeasurementEvent]) -> MatchQueryFinishedReport:
    status_counts: dict[str, int] = defaultdict(int)
    run_ids: set[str] = set()
    walls: list[int] = []
    counts: list[int] = []
    app_groups: dict[tuple[Any, Any, Any], dict[str, Any]] = {}

    for event in events:
        status_counts[event.status] += 1
        run_ids.add(event.run_id)
        walls.append(int(event.props["wall_ms"]))
        counts.append(int(event.props["result_count"]))

        app = event.app if isinstance(event.app, dict) else {}
        key = (app.get("app_version"), app.get("analyzer_version"), app.get("git_sha"))
        bucket = app_groups.setdefault(
            key,
            {
                "app_version": key[0],
                "analyzer_version": key[1],
                "git_sha": key[2],
                "events": 0,
                "wall_ms_values": [],
                "result_count_values": [],
            },
        )
        bucket["events"] += 1
        bucket["wall_ms_values"].append(int(event.props["wall_ms"]))
        bucket["result_count_values"].append(int(event.props["result_count"]))

    by_app: list[dict[str, Any]] = []
    for bucket in app_groups.values():
        wall_vals = bucket.pop("wall_ms_values")
        count_vals = bucket.pop("result_count_values")
        by_app.append(
            {
                **bucket,
                "wall_ms": _wall_summary(wall_vals),
                "result_count": _wall_summary(count_vals),
            }
        )
    by_app.sort(
        key=lambda row: (
            str(row.get("app_version") or ""),
            str(row.get("analyzer_version") or ""),
            str(row.get("git_sha") or ""),
        )
    )

    return MatchQueryFinishedReport(
        status=ReadStatus.OK,
        events=len(events),
        runs=len(run_ids),
        status_counts=dict(status_counts),
        wall_ms=_wall_summary(walls),
        result_count=_wall_summary(counts),
        by_app=by_app,
    )


def _empty_stage_from_counters(
    status: ReadStatus, counters: ReadCounters, *, error_code: Optional[str] = None
) -> StageFinishedReport:
    return StageFinishedReport(
        status=status,
        rows_seen=counters.rows_seen,
        invalid=counters.invalid,
        skipped_unknown=counters.skipped_unknown,
        error_code=error_code,
    )


def _empty_match_from_counters(
    status: ReadStatus, counters: ReadCounters, *, error_code: Optional[str] = None
) -> MatchQueryFinishedReport:
    return MatchQueryFinishedReport(
        status=status,
        rows_seen=counters.rows_seen,
        invalid=counters.invalid,
        skipped_unknown=counters.skipped_unknown,
        error_code=error_code,
    )


def build_stage_finished_report(db_path: Path) -> StageFinishedReport:
    reader = MeasurementReader(db_path)
    events, counters, status = reader.iter_stage_finished()
    if status is ReadStatus.MISSING_DB:
        return StageFinishedReport(status=status)
    if status is ReadStatus.ERROR:
        return _empty_stage_from_counters(
            status, counters, error_code="sidecar_unreadable"
        )
    if status is ReadStatus.NO_DATA:
        return _empty_stage_from_counters(status, counters)
    report = _aggregate_stage_events(events)
    report.rows_seen = counters.rows_seen
    report.invalid = counters.invalid
    report.skipped_unknown = counters.skipped_unknown
    return report


def build_match_query_finished_report(db_path: Path) -> MatchQueryFinishedReport:
    reader = MeasurementReader(db_path)
    events, counters, status = reader.iter_match_query_finished()
    if status is ReadStatus.MISSING_DB:
        return MatchQueryFinishedReport(status=status)
    if status is ReadStatus.ERROR:
        return _empty_match_from_counters(
            status, counters, error_code="sidecar_unreadable"
        )
    if status is ReadStatus.NO_DATA:
        return _empty_match_from_counters(status, counters)
    report = _aggregate_match_events(events)
    report.rows_seen = counters.rows_seen
    report.invalid = counters.invalid
    report.skipped_unknown = counters.skipped_unknown
    return report


def report_to_dict(report: StageFinishedReport) -> dict[str, Any]:
    return {
        "status": report.status.value,
        "event_name": TARGET_EVENT_NAME,
        "events": report.events,
        "runs": report.runs,
        "rows_seen": report.rows_seen,
        "invalid": report.invalid,
        "skipped_unknown": report.skipped_unknown,
        "status_counts": dict(report.status_counts),
        "by_stage": dict(report.by_stage),
        "by_app": list(report.by_app),
        "error_code": report.error_code,
    }


def match_report_to_dict(report: MatchQueryFinishedReport) -> dict[str, Any]:
    return {
        "status": report.status.value,
        "event_name": MATCH_QUERY_FINISHED_EVENT_NAME,
        "events": report.events,
        "runs": report.runs,
        "rows_seen": report.rows_seen,
        "invalid": report.invalid,
        "skipped_unknown": report.skipped_unknown,
        "status_counts": dict(report.status_counts),
        "wall_ms": dict(report.wall_ms),
        "result_count": dict(report.result_count),
        "by_app": list(report.by_app),
        "error_code": report.error_code,
    }


def format_report_text(report: StageFinishedReport) -> str:
    lines: list[str] = []
    lines.append(f"measurement report: {report.status.value}")
    if report.status is ReadStatus.MISSING_DB:
        lines.append("no measurement sidecar found")
        return "\n".join(lines) + "\n"
    if report.status is ReadStatus.ERROR:
        lines.append(f"error: {report.error_code or 'unknown'}")
        return "\n".join(lines) + "\n"
    if report.status is ReadStatus.NO_DATA:
        lines.append("sidecar present but no valid pipeline.stage_finished events")
        lines.append(
            f"rows_seen={report.rows_seen} invalid={report.invalid} "
            f"skipped_unknown={report.skipped_unknown}"
        )
        return "\n".join(lines) + "\n"

    lines.append(
        f"events={report.events} runs={report.runs} "
        f"invalid={report.invalid} skipped_unknown={report.skipped_unknown}"
    )
    if report.status_counts:
        status_bits = " ".join(f"{k}={v}" for k, v in sorted(report.status_counts.items()))
        lines.append(f"status: {status_bits}")
    for stage, data in sorted(report.by_stage.items()):
        wall = data["wall_ms"]
        lines.append(
            f"stage={stage} events={data['events']} "
            f"items_ok={data['items_ok_sum']} items_skip={data['items_skip_sum']} "
            f"items_fail={data['items_fail_sum']}"
        )
        lines.append(
            f"  wall_ms min={wall['min']} p50={wall['p50']} "
            f"p95={wall['p95']} max={wall['max']}"
        )
    if report.by_app:
        lines.append("by_app:")
        for row in report.by_app:
            wall = row["wall_ms"]
            lines.append(
                f"  app={row['app_version']} analyzer={row['analyzer_version']} "
                f"git={row['git_sha']} events={row['events']} "
                f"wall_ms_p50={wall['p50']}"
            )
    return "\n".join(lines) + "\n"


def format_match_report_text(report: MatchQueryFinishedReport) -> str:
    lines: list[str] = []
    lines.append(f"measurement report: {report.status.value}")
    lines.append(f"event={MATCH_QUERY_FINISHED_EVENT_NAME}")
    if report.status is ReadStatus.MISSING_DB:
        lines.append("no measurement sidecar found")
        return "\n".join(lines) + "\n"
    if report.status is ReadStatus.ERROR:
        lines.append(f"error: {report.error_code or 'unknown'}")
        return "\n".join(lines) + "\n"
    if report.status is ReadStatus.NO_DATA:
        lines.append("sidecar present but no valid match.query_finished events")
        lines.append(
            f"rows_seen={report.rows_seen} invalid={report.invalid} "
            f"skipped_unknown={report.skipped_unknown}"
        )
        return "\n".join(lines) + "\n"

    lines.append(
        f"events={report.events} runs={report.runs} "
        f"invalid={report.invalid} skipped_unknown={report.skipped_unknown}"
    )
    if report.status_counts:
        status_bits = " ".join(f"{k}={v}" for k, v in sorted(report.status_counts.items()))
        lines.append(f"status: {status_bits}")
    wall = report.wall_ms
    lines.append(
        f"wall_ms min={wall['min']} p50={wall['p50']} "
        f"p95={wall['p95']} max={wall['max']}"
    )
    counts = report.result_count
    lines.append(
        f"result_count min={counts['min']} p50={counts['p50']} "
        f"p95={counts['p95']} max={counts['max']}"
    )
    if report.by_app:
        lines.append("by_app:")
        for row in report.by_app:
            wall_row = row["wall_ms"]
            lines.append(
                f"  app={row['app_version']} analyzer={row['analyzer_version']} "
                f"git={row['git_sha']} events={row['events']} "
                f"wall_ms_p50={wall_row['p50']}"
            )
    return "\n".join(lines) + "\n"
