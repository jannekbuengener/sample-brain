#!/usr/bin/env python3
"""Deterministic helper for sample-brain-qml-profiler.

Discovers live Qt/PySide6 profiling facilities, summarizes bounded profile
captures (Sample Brain JSON schema; optional Qt Creator .qtd), and maps
hotspots to repository sources without inventing line certainty.

Does NOT run a new profiler or require a second Qt SDK.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

SCHEMA = "sample_brain_qml_profile_v1"
VERDICTS = frozenset(
    {"HOTSPOT_PROVEN", "NO_ACTIONABLE_HOTSPOT", "PROFILE_INCONCLUSIVE"}
)
CATEGORIES = frozenset(
    {
        "frame_render",
        "binding",
        "delegate_lifecycle",
        "layout",
        "js_qml",
        "resource_waveform",
        "python_bridge",
        "memory",
        "other",
    }
)

QT_INTERNAL_PREFIXES = ("qrc:/qt-project.org/", "qrc:/QtQuick/")


def _repo_root_from_script() -> Path:
    # docs/skills/<skill>/scripts/this.py -> repo root
    return Path(__file__).resolve().parents[4]


def discover_tooling(repo_root: Path | None = None) -> dict[str, Any]:
    """Probe the live environment for profiling-related facilities."""
    root = repo_root or _repo_root_from_script()
    qmlprofiler = shutil.which("qmlprofiler") or shutil.which("qmlprofiler.exe")
    qtcreator = shutil.which("qtcreator") or shutil.which("qtcreator.exe")

    pyside6: dict[str, Any] = {"available": False}
    plugins: list[str] = []
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        from PySide6.QtQml import QQmlDebuggingEnabler

        site = Path(PySide6.__file__).resolve().parent
        tooling = site / "plugins" / "qmltooling"
        if tooling.is_dir():
            plugins = sorted(p.name for p in tooling.glob("qmldbg_*profil*.dll"))
            plugins += sorted(
                p.name
                for p in tooling.glob("qmldbg_*profil*")
                if p.suffix in {".so", ".dylib"} and p.name not in plugins
            )
        pyside6 = {
            "available": True,
            "version": getattr(PySide6, "__version__", "unknown"),
            "qt_version": qVersion(),
            "site_packages": str(site),
            "qmltooling_profiler_plugins": plugins,
            "qqml_debugging_enabler": True,
            "profiler_services": list(QQmlDebuggingEnabler.profilerServices()),
        }
    except Exception as exc:  # noqa: BLE001 — discovery must never crash callers
        pyside6 = {"available": False, "error": type(exc).__name__}

    research = root / "src" / "workbench_waveform_research.py"
    decision = _tooling_decision(qmlprofiler, plugins, research.is_file(), pyside6)

    return {
        "schema": "sample_brain_qml_profiler_tooling_v1",
        "qmlprofiler_cli": qmlprofiler,
        "qtcreator": qtcreator,
        "pyside6": pyside6,
        "repo_instrumentation": {
            "waveform_research_benchmark": research.is_file(),
            "path": str(research) if research.is_file() else None,
            "notes": (
                "Bounded scroll/delegate timings for research ListView only; "
                "not Screen-1 Browser itself."
                if research.is_file()
                else "absent"
            ),
        },
        "decision_tree": decision,
        "do_not": [
            "install_second_qt_sdk_for_skill",
            "hardcode_qt_6_12_plus",
            "require_cmake_qt_qml_debug_rebuild_for_pyside6_app",
            "treat_missing_qmlprofiler_as_blocker_when_fallbacks_exist",
        ],
    }


def _tooling_decision(
    qmlprofiler: str | None,
    plugins: list[str],
    has_research: bool,
    pyside6: dict[str, Any],
) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = []
    if qmlprofiler:
        steps.append(
            {
                "prefer": "qmlprofiler_cli",
                "why": "CLI present; can capture .qtd for parse/summarize",
                "path": qmlprofiler,
            }
        )
    else:
        steps.append(
            {
                "prefer": "skip_qmlprofiler_cli",
                "why": "qmlprofiler not on PATH / not in PySide6 wheel",
                "path": "",
            }
        )
    if plugins and pyside6.get("available"):
        steps.append(
            {
                "prefer": "pyside6_qmltooling_plugins",
                "why": "qmldbg profiler plugins present; use only with known connector",
                "path": ",".join(plugins),
            }
        )
    if has_research:
        steps.append(
            {
                "prefer": "repo_instrumentation_or_bridge_counters",
                "why": (
                    "Use bounded Python timing + delegate/bridge counters for "
                    "representative synthetic workloads when CLI profiler absent"
                ),
                "path": "src/workbench_waveform_research.py",
            }
        )
    steps.append(
        {
            "prefer": "helper_summarize_only",
            "why": "Never invent a new profiler; summarize/map existing evidence",
            "path": "docs/skills/sample-brain-qml-profiler/scripts/qml_profiler_summarize.py",
        }
    )
    return steps


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_qtd_trace(path: Path) -> dict[str, Any]:
    """Minimal .qtd → event list (2D Qt Quick ranges only).

    Adapted in spirit from TheQtCompanyRnD qt-qml-profiler parser; Sample Brain
    does not require qmlprofiler to be installed for this path — only that a
    .qtd already exists.
    """
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as exc:
        return {"error": f"Failed to parse qtd: {exc}"}

    root = tree.getroot()
    event_data = root.find("eventData")
    if event_data is None:
        return {"error": "No eventData found in trace"}

    event_defs: dict[int, dict[str, str]] = {}
    for ev in event_data:
        try:
            idx = int(ev.get("index", -1))
        except ValueError:
            continue
        event_defs[idx] = {
            "name": ev.findtext("displayname", "") or "",
            "type": ev.findtext("type", "") or "",
            "filename": ev.findtext("filename", "") or "",
            "line": ev.findtext("line", "") or "",
            "details": ev.findtext("details", "") or "",
        }

    events: list[dict[str, Any]] = []
    for section in root:
        if section.tag != "profilerDataModel":
            continue
        for rng in section:
            if rng.tag != "range":
                continue
            try:
                ev_idx = int(rng.get("eventIndex", -1))
            except ValueError:
                continue
            ed = event_defs.get(ev_idx)
            if not ed:
                continue
            if ed["type"].startswith("Quick3D"):
                continue
            try:
                duration = int(rng.get("duration", 0))
            except ValueError:
                duration = 0
            if duration <= 0:
                continue
            events.append(
                {
                    "category": _map_qtd_type(ed["type"]),
                    "component": ed["name"] or ed["details"] or ed["type"],
                    "source": ed["filename"],
                    "line": int(ed["line"]) if ed["line"].isdigit() else None,
                    "count": 1,
                    "duration_ms": round(duration / 1e6, 3),
                    "details": ed["details"],
                    "qtd_type": ed["type"],
                }
            )

    if not events:
        return {"error": "No usable 2D range events in qtd"}

    return {
        "schema": SCHEMA,
        "reproduction": {
            "build_sha": None,
            "surface": "imported_qtd",
            "precondition": "existing .qtd",
            "dataset_scale": "unknown",
            "user_action": "unknown — verify against capture notes",
            "capture_window": path.name,
            "observed_symptom": "imported_trace",
        },
        "tool": {
            "name": "qmlprofiler_qtd",
            "version": "imported",
            "discovery_notes": f"parsed {path.name}",
        },
        "events": events,
        "confounders": ["qtd_imported_without_live_reproduction_contract"],
    }


def _map_qtd_type(qtd_type: str) -> str:
    t = (qtd_type or "").lower()
    if "bind" in t:
        return "binding"
    if "creat" in t:
        return "delegate_lifecycle"
    if "paint" in t or "scene" in t or "render" in t or "anim" in t:
        return "frame_render"
    if "layout" in t or "geom" in t:
        return "layout"
    if "javascript" in t or "signal" in t or "compil" in t:
        return "js_qml"
    if "pixmap" in t or "image" in t:
        return "resource_waveform"
    if "memory" in t:
        return "memory"
    return "other"


def normalize_capture(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("error"):
        return data
    if data.get("schema") != SCHEMA:
        return {"error": f"Unsupported schema: {data.get('schema')!r}; need {SCHEMA}"}
    events = data.get("events")
    if not isinstance(events, list):
        return {"error": "events must be a list"}
    return data


def aggregate_hotspots(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for ev in events:
        category = str(ev.get("category") or "other")
        if category not in CATEGORIES:
            category = "other"
        component = str(ev.get("component") or "unknown")
        source = str(ev.get("source") or "")
        key = (category, component, source)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "category": category,
                "component": component,
                "source": source,
                "line": ev.get("line"),
                "count": 0,
                "duration_ms": 0.0,
                "details": [],
            }
            buckets[key] = bucket
        bucket["count"] += int(ev.get("count") or 1)
        bucket["duration_ms"] += float(ev.get("duration_ms") or 0.0)
        detail = ev.get("details")
        if detail and detail not in bucket["details"]:
            bucket["details"].append(str(detail))
        line = ev.get("line")
        if bucket.get("line") in (None, 0) and line not in (None, 0):
            bucket["line"] = line

    ranked = sorted(
        buckets.values(),
        key=lambda b: (b["duration_ms"], b["count"]),
        reverse=True,
    )
    for item in ranked:
        item["duration_ms"] = round(float(item["duration_ms"]), 3)
    return ranked


def map_sources(
    hotspots: list[dict[str, Any]],
    repo_root: Path,
    *,
    search_roots: list[Path] | None = None,
) -> list[dict[str, Any]]:
    roots = search_roots or [repo_root / "src", repo_root / "tests"]
    mapped: list[dict[str, Any]] = []
    for hs in hotspots:
        source = hs.get("source") or ""
        entry = {
            **hs,
            "mapped_path": None,
            "mapping_status": "unresolved",
            "mapping_notes": "",
        }
        if not source or source.startswith(QT_INTERNAL_PREFIXES):
            entry["mapping_status"] = "qt_internal_or_empty"
            entry["mapping_notes"] = "ignored Qt-internal or empty source"
            mapped.append(entry)
            continue

        # Direct repo-relative path
        candidate = Path(source)
        if not candidate.is_absolute():
            direct = repo_root / candidate
            if direct.is_file():
                entry["mapped_path"] = str(direct.relative_to(repo_root)).replace(
                    "\\", "/"
                )
                entry["mapping_status"] = "resolved"
                mapped.append(entry)
                continue

        # Embedded marker like "src/workbench_qml.py:browserList delegate"
        marker = source.split(":", 1)[0].strip()
        if marker and (repo_root / marker).is_file():
            entry["mapped_path"] = marker.replace("\\", "/")
            entry["mapping_status"] = "resolved_component_marker"
            if hs.get("line") in (None, 0):
                entry["mapping_notes"] = (
                    "component marker mapped; line certainty not invented"
                )
            mapped.append(entry)
            continue

        basename = Path(source.split("?")[0]).name
        if not basename:
            entry["mapping_notes"] = "no basename"
            mapped.append(entry)
            continue

        hits: list[Path] = []
        for root in roots:
            if not root.is_dir():
                continue
            hits.extend(root.rglob(basename))
        # Also allow fixture dirs named in source
        unique = []
        seen: set[str] = set()
        for hit in hits:
            rel = str(hit.relative_to(repo_root)).replace("\\", "/")
            if rel not in seen:
                seen.add(rel)
                unique.append(rel)
        if len(unique) == 1:
            entry["mapped_path"] = unique[0]
            entry["mapping_status"] = "resolved"
        elif len(unique) > 1:
            entry["mapping_status"] = "ambiguous"
            entry["mapping_notes"] = f"matches={unique[:5]}"
        else:
            entry["mapping_status"] = "unresolved"
            entry["mapping_notes"] = f"basename={basename} not found under search roots"
        mapped.append(entry)
    return mapped


def choose_verdict(
    capture: dict[str, Any],
    hotspots: list[dict[str, Any]],
) -> dict[str, Any]:
    repro = capture.get("reproduction") or {}
    required = [
        "surface",
        "user_action",
        "capture_window",
        "observed_symptom",
    ]
    missing = [k for k in required if not repro.get(k)]
    confounders = list(capture.get("confounders") or [])
    tool = capture.get("tool") or {}

    if missing:
        return {
            "verdict": "PROFILE_INCONCLUSIVE",
            "reason": "incomplete_reproduction_contract",
            "missing_reproduction_fields": missing,
        }
    if not tool.get("name"):
        return {
            "verdict": "PROFILE_INCONCLUSIVE",
            "reason": "tool_not_recorded",
        }
    if capture.get("error"):
        return {
            "verdict": "PROFILE_INCONCLUSIVE",
            "reason": str(capture["error"]),
        }
    if not hotspots:
        return {
            "verdict": "PROFILE_INCONCLUSIVE",
            "reason": "no_events",
        }

    total = sum(float(h["duration_ms"]) for h in hotspots) or 1.0
    top = hotspots[0]
    share = float(top["duration_ms"]) / total
    mapped_ok = top.get("mapping_status", "").startswith("resolved")
    top_ms = float(top["duration_ms"])
    top_count = int(top["count"])

    blocking_confounders = {
        "instrumentation_overhead_unseparated",
        "unstable_capture",
        "contradictory_evidence",
        "env_noise_dominates",
    }
    if blocking_confounders.intersection(confounders):
        return {
            "verdict": "PROFILE_INCONCLUSIVE",
            "reason": "confounders_block_proof",
            "confounders": confounders,
            "dominant_candidate": _compact_hotspot(top),
        }

    # Flat / tiny absolute cost: relative share alone is not actionable.
    # No universal product budget — only relative+magnitude gate for fixtures.
    if top_ms < 5.0 and top_count < 20 and total < 15.0:
        return {
            "verdict": "NO_ACTIONABLE_HOTSPOT",
            "reason": "no_dominant_cost_in_bounded_window",
            "top_share": round(share, 3),
            "dominant_candidate": _compact_hotspot(top),
        }

    if share >= 0.35 and mapped_ok:
        return {
            "verdict": "HOTSPOT_PROVEN",
            "reason": "dominant_cost_mapped_to_source",
            "top_share": round(share, 3),
            "dominant": _compact_hotspot(top),
        }

    if share >= 0.35 and not mapped_ok:
        return {
            "verdict": "PROFILE_INCONCLUSIVE",
            "reason": "dominant_cost_unmapped",
            "top_share": round(share, 3),
            "dominant_candidate": _compact_hotspot(top),
        }

    return {
        "verdict": "NO_ACTIONABLE_HOTSPOT",
        "reason": "relative_costs_do_not_justify_action",
        "top_share": round(share, 3),
        "dominant_candidate": _compact_hotspot(top),
    }


def _compact_hotspot(hs: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": hs.get("category"),
        "component": hs.get("component"),
        "source": hs.get("source"),
        "mapped_path": hs.get("mapped_path"),
        "mapping_status": hs.get("mapping_status"),
        "line": hs.get("line"),
        "count": hs.get("count"),
        "duration_ms": hs.get("duration_ms"),
        "details": hs.get("details") or [],
    }


def summarize(
    capture: dict[str, Any],
    repo_root: Path,
    *,
    top_n: int = 8,
) -> dict[str, Any]:
    capture = normalize_capture(capture)
    if capture.get("error"):
        return {
            "schema": "sample_brain_qml_profiler_summary_v1",
            "verdict": "PROFILE_INCONCLUSIVE",
            "reason": capture["error"],
            "hotspots": [],
            "measured": [],
            "hypothesis": None,
            "next_experiment": "fix capture schema / re-run discovery",
        }

    hotspots = aggregate_hotspots(list(capture.get("events") or []))
    mapped = map_sources(hotspots, repo_root)
    decision = choose_verdict(capture, mapped)
    top = mapped[:top_n]

    measured = [
        {
            "kind": "hotspot",
            "category": h["category"],
            "component": h["component"],
            "mapped_path": h.get("mapped_path"),
            "mapping_status": h.get("mapping_status"),
            "count": h["count"],
            "duration_ms": h["duration_ms"],
            "evidence_class": "MEASURED",
        }
        for h in top
    ]

    hypothesis = None
    next_experiment = None
    verdict = decision["verdict"]
    if verdict == "HOTSPOT_PROVEN":
        dom = decision["dominant"]
        hypothesis = {
            "evidence_class": "HYPOTHESIS",
            "statement": (
                f"Dominant {dom['category']} cost in {dom['component']} "
                f"({dom.get('mapped_path') or dom.get('source')}) explains the "
                f"reproduced interaction cost within the bounded window."
            ),
        }
        next_experiment = {
            "evidence_class": "VERIFY",
            "action": (
                "Run smallest control: reduce that path only (e.g. fewer bridge "
                "calls, less offscreen work, diagnostic reuse compare) and "
                "re-capture the same reproduction."
            ),
        }
    elif verdict == "NO_ACTIONABLE_HOTSPOT":
        next_experiment = {
            "evidence_class": "VERIFY",
            "action": (
                "Do not optimize. Optionally re-check with a larger synthetic "
                "but repo-safe scale, or a different user action, if the "
                "symptom persists outside this window."
            ),
        }
    else:
        next_experiment = {
            "evidence_class": "VERIFY",
            "action": (
                "Repair reproduction/tooling/mapping/confounders before any "
                "product change. Inconclusive ≠ wrong theory."
            ),
        }

    by_category: dict[str, float] = defaultdict(float)
    for h in mapped:
        by_category[str(h["category"])] += float(h["duration_ms"])

    return {
        "schema": "sample_brain_qml_profiler_summary_v1",
        "reproduction": capture.get("reproduction"),
        "tool": capture.get("tool"),
        "confounders": capture.get("confounders") or [],
        "by_category_ms": {k: round(v, 3) for k, v in sorted(by_category.items())},
        "hotspots": top,
        "measured": measured,
        "hypothesis": hypothesis,
        "next_experiment": next_experiment,
        "verdict": verdict,
        "verdict_detail": decision,
    }


def load_capture(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".qtd":
        return parse_qtd_trace(path)
    data = _load_json(path)
    if path.suffix.lower() in {".yaml", ".yml"}:
        return {"error": "YAML captures unsupported; emit JSON schema capture"}
    return data


def build_report_yaml_like(summary: dict[str, Any]) -> str:
    """Compact YAML-like report (stdlib only — no PyYAML dependency)."""

    def dump(obj: Any, indent: int = 0) -> list[str]:
        pad = "  " * indent
        lines: list[str] = []
        if isinstance(obj, dict):
            for key, val in obj.items():
                if isinstance(val, (dict, list)):
                    lines.append(f"{pad}{key}:")
                    lines.extend(dump(val, indent + 1))
                else:
                    lines.append(f"{pad}{key}: {_scalar(val)}")
        elif isinstance(obj, list):
            if not obj:
                lines.append(f"{pad}[]")
            for item in obj:
                if isinstance(item, (dict, list)):
                    lines.append(f"{pad}-")
                    lines.extend(dump(item, indent + 1))
                else:
                    lines.append(f"{pad}- {_scalar(item)}")
        else:
            lines.append(f"{pad}{_scalar(obj)}")
        return lines

    def _scalar(val: Any) -> str:
        if val is None:
            return "null"
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, (int, float)):
            return str(val)
        text = str(val).replace("\n", " ").replace('"', '\\"')
        return f'"{text}"'

    ordered = {
        "reproduction": summary.get("reproduction"),
        "tool": summary.get("tool"),
        "trace_scope": (summary.get("reproduction") or {}).get("capture_window"),
        "by_category_ms": summary.get("by_category_ms"),
        "measured_hotspots": summary.get("measured"),
        "hypothesis": summary.get("hypothesis"),
        "confounders": summary.get("confounders"),
        "next_experiment": summary.get("next_experiment"),
        "verdict": summary.get("verdict"),
        "verdict_detail": summary.get("verdict_detail"),
    }
    return "\n".join(dump(ordered)) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: inferred from script location)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_disc = sub.add_parser("discover", help="Discover live profiling tooling")
    p_disc.add_argument("--json", action="store_true", help="JSON only")

    p_sum = sub.add_parser("summarize", help="Summarize a bounded capture")
    p_sum.add_argument("capture", type=Path, help="JSON capture or .qtd path")
    p_sum.add_argument("--json", action="store_true", help="Emit JSON summary")
    p_sum.add_argument("--top", type=int, default=8)

    args = parser.parse_args(argv)
    repo_root = (args.repo_root or _repo_root_from_script()).resolve()

    if args.cmd == "discover":
        payload = discover_tooling(repo_root)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.cmd == "summarize":
        capture = load_capture(args.capture)
        summary = summarize(capture, repo_root, top_n=args.top)
        if args.json:
            print(json.dumps(summary, indent=2, sort_keys=True))
        else:
            print(build_report_yaml_like(summary))
        return 0 if summary.get("verdict") in VERDICTS else 2

    parser.error(f"unknown command {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
