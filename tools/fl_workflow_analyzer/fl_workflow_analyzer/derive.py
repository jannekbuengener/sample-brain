"""Transitions, hot paths, loops, backtracking, churn, undo, bottlenecks."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from typing import Any

from .correlate import CorrelatedAction
from .rules import (
    BACKTRACK_MAX_RETURN_NS,
    BOTTLENECK_MAD_K,
    BOTTLENECK_MIN_SAMPLES,
    CHURN_WINDOW_NS,
    HOT_PATH_MIN_COUNT,
    HOT_PATH_NS,
    LOOP_MIN_REPEATS,
)
from .segment import ActivitySegment

# Activities excluded from workflow path mining (still counted in coverage).
_PATH_EXCLUDE = frozenset({"idle", "background"})


def _median(xs: list[float | int]) -> float | None:
    if not xs:
        return None
    return float(statistics.median(xs))


def _mad(xs: list[float], med: float) -> float:
    if not xs:
        return 0.0
    return float(statistics.median([abs(x - med) for x in xs]))


def transition_matrix(segments: list[ActivitySegment]) -> list[dict[str, Any]]:
    """A→B counts + durations (time spent in A before transition)."""
    buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
    workflow = [s for s in segments if s.activity not in _PATH_EXCLUDE]
    for a, b in zip(workflow, workflow[1:]):
        buckets[(a.activity, b.activity)].append(a.duration_ns)
    out = []
    for (frm, to), durs in sorted(buckets.items()):
        out.append(
            {
                "from_activity": frm,
                "to_activity": to,
                "count": len(durs),
                "total_duration_ns": int(sum(durs)),
                "median_duration_ns": int(_median(durs) or 0),
                "durations_ns": durs,
            }
        )
    return out


def hot_paths(segments: list[ActivitySegment], *, session_id: str) -> list[dict[str, Any]]:
    """Deterministic n-gram counts for n=2..5. One-off paths are not hot."""
    seq = [s.activity for s in segments if s.activity not in _PATH_EXCLUDE]
    if len(seq) < 2:
        return []
    results: list[dict[str, Any]] = []
    total_sessions_coverage = 1  # per-session call; aggregator rolls up
    for n in HOT_PATH_NS:
        if len(seq) < n:
            continue
        counts: Counter[tuple[str, ...]] = Counter()
        dur_map: dict[tuple[str, ...], list[int]] = defaultdict(list)
        for i in range(len(seq) - n + 1):
            gram = tuple(seq[i : i + n])
            counts[gram] += 1
            # Duration = sum of segment durations in the gram window.
            window = [s for s in segments if s.activity not in _PATH_EXCLUDE][i : i + n]
            dur_map[gram].append(sum(s.duration_ns for s in window))
        total = sum(counts.values()) or 1
        for gram, cnt in counts.most_common():
            if cnt < HOT_PATH_MIN_COUNT:
                continue
            results.append(
                {
                    "session_id": session_id,
                    "n": n,
                    "path": list(gram),
                    "count": cnt,
                    "relative_frequency": round(cnt / total, 6),
                    "session_coverage": total_sessions_coverage,
                    "median_duration_ns": int(_median(dur_map[gram]) or 0),
                }
            )
    return results


def detect_loops(segments: list[ActivitySegment], *, session_id: str) -> list[dict[str, Any]]:
    """Detect repeated alternating patterns (e.g. edit→play→edit→play)."""
    seq = [(s.activity, s.start_wall_ns, s.end_wall_ns) for s in segments if s.activity not in _PATH_EXCLUDE]
    loops: list[dict[str, Any]] = []
    # Look for period-2 and period-3 cycles with ≥ LOOP_MIN_REPEATS full cycles.
    for period in (2, 3):
        if len(seq) < period * LOOP_MIN_REPEATS:
            continue
        i = 0
        while i <= len(seq) - period * LOOP_MIN_REPEATS:
            pattern = [seq[i + k][0] for k in range(period)]
            if len(set(pattern)) < 2:
                i += 1
                continue
            repeats = 1
            j = i + period
            while j + period <= len(seq):
                nxt = [seq[j + k][0] for k in range(period)]
                if nxt == pattern:
                    repeats += 1
                    j += period
                else:
                    break
            if repeats >= LOOP_MIN_REPEATS:
                start = seq[i][1]
                end = seq[j - 1][2]
                loops.append(
                    {
                        "session_id": session_id,
                        "pattern": pattern,
                        "repeats": repeats,
                        "duration_ns": end - start,
                        "start_wall_ns": start,
                        "end_wall_ns": end,
                        "confidence": "high" if repeats >= 3 else "medium",
                        "truth_level": "correlated",
                    }
                )
                i = j
            else:
                i += 1
    return loops


def detect_backtracks(segments: list[ActivitySegment], *, session_id: str) -> list[dict[str, Any]]:
    """A→B→A or A→B→C→A within BACKTRACK_MAX_RETURN_NS."""
    workflow = [s for s in segments if s.activity not in _PATH_EXCLUDE]
    out: list[dict[str, Any]] = []
    for i, s in enumerate(workflow):
        for span in (2, 3):  # A B A  or  A B C A
            j = i + span
            if j >= len(workflow):
                break
            if workflow[j].activity != s.activity:
                continue
            mid = [workflow[k].activity for k in range(i + 1, j)]
            if s.activity in mid:
                continue
            ret_ns = workflow[j].start_wall_ns - s.end_wall_ns
            if ret_ns < 0 or ret_ns > BACKTRACK_MAX_RETURN_NS:
                continue
            out.append(
                {
                    "session_id": session_id,
                    "pattern": [s.activity] + mid + [s.activity],
                    "return_latency_ns": ret_ns,
                    "start_wall_ns": s.start_wall_ns,
                    "end_wall_ns": workflow[j].end_wall_ns,
                    "confidence": "high" if span == 2 else "medium",
                    "truth_level": "correlated",
                }
            )
    return out


def churn_metrics(segments: list[ActivitySegment], *, session_id: str) -> dict[str, Any]:
    """Context-switch density in CHURN_WINDOW_NS sliding windows (measurement only)."""
    workflow = [s for s in segments if s.activity not in _PATH_EXCLUDE]
    if len(workflow) < 2:
        return {
            "session_id": session_id,
            "switch_count": 0,
            "switches_per_active_minute": 0.0,
            "peak_window_switches": 0,
            "pairs": [],
        }
    switches = 0
    pair_counts: Counter[tuple[str, str]] = Counter()
    for a, b in zip(workflow, workflow[1:]):
        if a.activity != b.activity:
            switches += 1
            pair_counts[(a.activity, b.activity)] += 1
    active_ns = sum(s.duration_ns for s in workflow) or 1
    per_min = switches / (active_ns / 60_000_000_000)

    # Peak switches in any CHURN_WINDOW_NS wall window.
    peak = 0
    starts = [s.start_wall_ns for s in workflow]
    for t0 in starts:
        t1 = t0 + CHURN_WINDOW_NS
        c = sum(
            1
            for a, b in zip(workflow, workflow[1:])
            if a.activity != b.activity and t0 <= a.end_wall_ns < t1
        )
        peak = max(peak, c)

    return {
        "session_id": session_id,
        "switch_count": switches,
        "switches_per_active_minute": round(per_min, 4),
        "peak_window_switches": peak,
        "pairs": [
            {"from": a, "to": b, "count": n}
            for (a, b), n in pair_counts.most_common(20)
        ],
    }


def undo_metrics(actions: list[CorrelatedAction], segments: list[ActivitySegment], *, session_id: str) -> dict[str, Any]:
    undos = [a for a in actions if a.action_type == "undo"]
    active_ns = sum(
        s.duration_ns for s in segments if s.activity not in _PATH_EXCLUDE | {"transport_listening"}
    )
    active_min = (active_ns / 60_000_000_000) if active_ns else 0.0

    undo_after_edit = 0
    chains = 0
    in_chain = False
    for i, a in enumerate(actions):
        if a.action_type != "undo":
            in_chain = False
            continue
        # Prior input/edit action within recent timeline.
        prior = actions[i - 1] if i else None
        if prior and (
            prior.action_type.startswith(("click", "drag", "wheel", "key"))
            or prior.action_type in ("undo",)
            or "edit" in (prior.props.get("sb_context") or "")
        ):
            undo_after_edit += 1
        if in_chain:
            chains += 1
        in_chain = True

    return {
        "session_id": session_id,
        "undo_count": len(undos),
        "undo_per_active_minute": round(len(undos) / active_min, 4) if active_min > 0 else None,
        "undo_after_edit": undo_after_edit,
        "undo_chain_extensions": chains,
        "truth_level": "measured",
        "note": "Undo density is evidence only — not an automatic error judgment.",
    }


def bottleneck_candidates(segments: list[ActivitySegment], *, session_id: str) -> list[dict[str, Any]]:
    """Flag long segments vs per-session per-activity robust median+MAD.

    Relative to *own* observed behavior only — no industry benchmarks.
    """
    by_act: dict[str, list[ActivitySegment]] = defaultdict(list)
    for s in segments:
        if s.activity in _PATH_EXCLUDE:
            continue
        by_act[s.activity].append(s)

    out: list[dict[str, Any]] = []
    for activity, group in by_act.items():
        durs = [float(s.duration_ns) for s in group]
        if len(durs) < BOTTLENECK_MIN_SAMPLES:
            continue
        med = statistics.median(durs)
        mad = _mad(durs, med)
        # If MAD is 0, use a small epsilon from median to avoid divide issues;
        # still require duration clearly above median.
        scale = mad if mad > 0 else max(med * 0.1, 1.0)
        for s in group:
            z = (s.duration_ns - med) / scale
            if z >= BOTTLENECK_MAD_K:
                out.append(
                    {
                        "session_id": session_id,
                        "segment_id": s.segment_id,
                        "activity": activity,
                        "duration_ns": s.duration_ns,
                        "session_median_ns": int(med),
                        "session_mad_ns": int(mad),
                        "robust_score": round(z, 3),
                        "confidence": "medium",
                        "truth_level": "interpreted",
                        "reasons": ["duration_outlier_vs_session_median_mad"],
                        "note": "Candidate only — not a product judgment.",
                    }
                )
    return out


def edit_arrangement_evidence(segments: list[ActivitySegment], *, session_id: str) -> dict[str, Any]:
    """Dedicated Edit↔Arrangement transition evidence (Sample Brain product relevance)."""
    # Normalize playlist_edit/arrangement → arrangement; edit-family → edit for this view.
    def norm(a: str) -> str | None:
        if a in ("arrangement", "playlist_edit"):
            return "arrangement"
        if a in ("edit", "piano_roll_edit", "channel_rack", "plugin_interaction"):
            return "edit"
        return None

    seq = [(norm(s.activity), s) for s in segments]
    seq = [(n, s) for n, s in seq if n is not None]
    ea = 0
    ae = 0
    ea_durs: list[int] = []
    ae_durs: list[int] = []
    short_returns = 0
    for i in range(len(seq) - 1):
        a, sa = seq[i]
        b, sb = seq[i + 1]
        if a == "edit" and b == "arrangement":
            ea += 1
            ea_durs.append(sa.duration_ns)
        elif a == "arrangement" and b == "edit":
            ae += 1
            ae_durs.append(sa.duration_ns)
    # Short return: edit→arrangement→edit within backtrack window
    for i in range(len(seq) - 2):
        a, sa = seq[i]
        b, sb = seq[i + 1]
        c, sc = seq[i + 2]
        if a == "edit" and b == "arrangement" and c == "edit":
            if sc.start_wall_ns - sa.end_wall_ns <= BACKTRACK_MAX_RETURN_NS:
                short_returns += 1
        if a == "arrangement" and b == "edit" and c == "arrangement":
            if sc.start_wall_ns - sa.end_wall_ns <= BACKTRACK_MAX_RETURN_NS:
                short_returns += 1

    covered = sum(s.duration_ns for _, s in seq)
    total = sum(s.duration_ns for s in segments if s.activity not in _PATH_EXCLUDE) or 1
    return {
        "session_id": session_id,
        "edit_to_arrangement_count": ea,
        "arrangement_to_edit_count": ae,
        "edit_to_arrangement_median_dwell_ns": int(_median(ea_durs) or 0),
        "arrangement_to_edit_median_dwell_ns": int(_median(ae_durs) or 0),
        "short_return_count": short_returns,
        "session_coverage_fraction": round(covered / total, 6),
        "truth_level": "interpreted",
        "note": "Frequency is evidence only — not a good/bad workflow claim.",
    }


def coverage_metrics(
    segments: list[ActivitySegment],
    actions: list[CorrelatedAction],
    *,
    session_id: str,
) -> dict[str, Any]:
    by_conf = {"high": 0, "medium": 0, "low": 0}
    unknown_ns = 0
    idle_ns = 0
    listening_ns = 0
    active_ns = 0
    for s in segments:
        if s.activity == "idle":
            idle_ns += s.duration_ns
            continue
        if s.activity == "background":
            continue
        if s.activity == "transport_listening":
            listening_ns += s.duration_ns
            active_ns += s.duration_ns
            by_conf[s.confidence] = by_conf.get(s.confidence, 0) + s.duration_ns
            continue
        active_ns += s.duration_ns
        if s.activity == "unknown":
            unknown_ns += s.duration_ns
        by_conf[s.confidence] = by_conf.get(s.confidence, 0) + s.duration_ns

    return {
        "session_id": session_id,
        "active_ns": active_ns,
        "listening_ns": listening_ns,
        "idle_ns": idle_ns,
        "high_confidence_active_ns": by_conf.get("high", 0),
        "medium_confidence_active_ns": by_conf.get("medium", 0),
        "low_confidence_active_ns": by_conf.get("low", 0),
        "unknown_active_ns": unknown_ns,
        "action_count": len(actions),
        "segment_count": len(segments),
    }
