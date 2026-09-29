"""Public, deterministic Screen-1 visual-acceptance contracts."""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import struct
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping

from .runtime_provenance import RuntimeReport, RuntimeStatus
from .workbench_controller import WorkbenchRow
from .workbench_harmony import HarmonyRelation, HarmonySuggestion

FIXTURE_VERSION = "screen1_visual_fixture_v1"
REQUIRED_STATE_IDS = ("screen1-default-3panel", "screen1-harmonic-4panel")
CLIENT_WIDTH, CLIENT_HEIGHT, MANIFEST_SCHEMA = 1600, 900, 1

class EvidenceError(ValueError): pass

@dataclass(frozen=True)
class Screen1VisualFixture:
    version: str
    library_labels: tuple[str, ...]
    browser_rows: tuple[WorkbenchRow, ...]
    selected_browser_index: int
    harmony_results: tuple[HarmonySuggestion, ...]
    assignments: Mapping[str, Mapping[str, WorkbenchRow]]
    state_ids: tuple[str, ...]

def _synthetic_envelope(seed: int) -> tuple[float, ...]:
    """Return deterministic envelope data for screenshot fixtures, not glyphs."""
    return tuple(
        round(
            min(
                1.0,
                0.12
                + 0.72
                * abs(math.sin((index + 1) * (0.19 + seed * 0.003))),
            ),
            3,
        )
        for index in range(72)
    )


def _row(name: str, kind: str, key: str | None, duration: str, seed: int) -> WorkbenchRow:
    return WorkbenchRow(name, f"fixture/{name}.wav", f"fixture/{name}.wav", 132.0, key, .91 if key else None, -14.0, 2000.0 + seed, "loop" if "LOOP" in name else "one_shot", kind, "ok", {"duration_sec": duration, "waveform_envelope": _synthetic_envelope(seed)})

def _match(row: WorkbenchRow, relation: HarmonyRelation, score: float, pitch: int | None = None) -> HarmonySuggestion:
    return HarmonySuggestion(row, relation, {HarmonyRelation.DIRECT: 1., HarmonyRelation.RELATED: .7, HarmonyRelation.TRANSPOSE: .5}[relation], 1., score, pitch, relation.value)

def build_screen1_visual_fixture_v1() -> Screen1VisualFixture:
    rows = tuple(_row(*value) for value in (
        ("TECH_KICK_01", "Kick", "C", "0.98", 1), ("TECH_KICK_02", "Kick", "C", "1.02", 2),
        ("TECH_BASS_01", "Bass", "F#", "2.00", 3), ("TECH_BASS_02", "Bass", "G", "2.00", 4),
        ("TECH_CLAP_01", "Clap", None, "0.50", 5), ("TECH_CLOSED_HAT_01", "Closed Hat", None, "0.25", 6),
        ("TECH_OPEN_HAT_01", "Open Hat", None, "0.42", 7), ("TECH_PERC_LOOP_01", "Percussion Loop", "F#", "4.00", 8),
        ("TECH_TOP_LOOP_01", "Top Loop", "A#", "4.00", 9), ("TECH_ATMOS_01", "Atmosphere", "D", "8.00", 10),
        ("TECH_FX_RISER_01", "FX", None, "4.00", 11), ("TECH_VOX_LOOP_01", "Vocal Loop", "A#", "8.00", 12)))
    matches = (_match(_row("TECH_SYNTH_01", "Synth Loop", "F#", "4.00", 21), HarmonyRelation.DIRECT, .95), _match(_row("TECH_VOX_LOOP_02", "Vocal Loop", "F#", "8.00", 22), HarmonyRelation.DIRECT, .90), _match(_row("TECH_PAD_01", "Pad", "A#", "8.00", 23), HarmonyRelation.RELATED, .89), _match(_row("TECH_ARP_LOOP_01", "Arp Loop", "A#", "4.00", 24), HarmonyRelation.RELATED, .72), _match(_row("TECH_LEAD_01", "Lead", "C#", "4.00", 25), HarmonyRelation.TRANSPOSE, .82, -3), _match(_row("TECH_PLUCK_01", "Pluck", "D#", "2.00", 26), HarmonyRelation.TRANSPOSE, .76, -3))
    return Screen1VisualFixture(FIXTURE_VERSION, ("All Samples", "Samples", "Techno", "Favorites"), rows, 2, matches, {"Drums": {"Main Drum": rows[0], "Closed Hat": rows[5], "Open Hat": rows[6]}}, REQUIRED_STATE_IDS)

def validate_runtime_for_visual_acceptance(report: RuntimeReport) -> None:
    if report.status is not RuntimeStatus.VALID or report.manifest is None: raise EvidenceError("Runtime-Provenance ist nicht VALID; Capture wird blockiert.")

def apply_screen1_visual_fixture(app, fixture: Screen1VisualFixture, state_id: str) -> None:
    if state_id not in REQUIRED_STATE_IDS: raise EvidenceError("Unbekannter Acceptance-State.")
    from .workbench_controller import WorkbenchResult
    app._library_paths = [f"fixture:{label}" for label in fixture.library_labels]
    app._library_list.delete(0, "end")
    for label in fixture.library_labels: app._library_list.insert("end", label)
    app._populate_playlist(WorkbenchResult(summary={"fixture": 12}, rows=list(fixture.browser_rows)))
    app._tree.selection_set(str(fixture.selected_browser_index)); app._set_detail(fixture.browser_rows[2])
    for group, slots in fixture.assignments.items():
        for slot, row in slots.items(): app._assign_row_to_live_kit(row, group, slot)
    if state_id.endswith("4panel"):
        app._harmonic_match_controller._finder = lambda *_a, **_k: (list(fixture.harmony_results), None)
        app._harmonic_match_btn.invoke()
    else: app._close_harmonic_match_library()

def _sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def _private(value: object) -> bool:
    text = json.dumps(value).casefold(); return any(x in text for x in ("\\\\", ":\\", "/users/", "/home/", "@"))
def build_visual_evidence_manifest(*, runtime_report: RuntimeReport, fixture: Screen1VisualFixture, captures: Mapping[str, Path], os_name: str, dpi_scale: int, client_width: int, client_height: int, sanity_results: Mapping[str, object]) -> dict[str, object]:
    validate_runtime_for_visual_acceptance(runtime_report)
    if tuple(captures) != REQUIRED_STATE_IDS or fixture.state_ids != REQUIRED_STATE_IDS: raise EvidenceError("Beide Pflicht-States fehlen.")
    if (client_width, client_height, dpi_scale) != (CLIENT_WIDTH, CLIENT_HEIGHT, 100): raise EvidenceError("Capture-Baseline ist ungültig.")
    if not all(path.is_file() for path in captures.values()): raise EvidenceError("Capture-Datei fehlt.")
    result = {"schema": MANIFEST_SCHEMA, "commit": runtime_report.manifest.commit, "channel": runtime_report.manifest.channel, "runtime_status": "valid", "python": f"{platform.python_implementation()} {platform.python_version()}", "os": os_name, "dpi": dpi_scale, "client_width": client_width, "client_height": client_height, "fixture": fixture.version, "states": list(REQUIRED_STATE_IDS), "screenshot_hashes": {k: _sha(v) for k,v in captures.items()}, "sanity_results": dict(sanity_results), "created_at": datetime.now(UTC).isoformat()}
    if _private(result): raise EvidenceError("Evidence enthält private Pfaddaten.")
    return result
def write_visual_evidence_manifest(path: Path, manifest: Mapping[str, object]) -> None:
    if _private(manifest): raise EvidenceError("Evidence enthält private Pfaddaten.")
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n", encoding="utf-8")

def _chunk(kind: bytes, data: bytes) -> bytes: return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
def _write_png(path: Path, width: int, height: int, rgba: bytes) -> None:
    raw=b"".join(b"\0"+rgba[i:i+width*4] for i in range(0,len(rgba),width*4)); path.write_bytes(b"\x89PNG\r\n\x1a\n"+_chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,6,0,0,0))+_chunk(b"IDAT",zlib.compress(raw))+_chunk(b"IEND",b""))
def validate_capture_sanity(path: Path, *, expected_width: int, expected_height: int) -> dict[str,bool]:
    if not path.is_file(): return {"exists":False,"dimensions":False,"non_black":False,"pass":False}
    data=path.read_bytes(); width,height=struct.unpack(">II",data[16:24]); raw=zlib.decompress(data[41:-12]); pixels=b"".join(raw[i+1:i+1+width*4] for i in range(0,len(raw),width*4+1)); non_black=any(v for i,v in enumerate(pixels) if i%4!=3); dimensions=(width,height)==(expected_width,expected_height); return {"exists":True,"dimensions":dimensions,"non_black":non_black,"pass":dimensions and non_black}
def capture_windows_client_window(hwnd: int, target: Path) -> tuple[int,int]:
    if os.name != "nt": raise EvidenceError("Window-Capture ist nur unter Windows verfügbar.")
    import ctypes
    from ctypes import wintypes
    u,g=ctypes.windll.user32,ctypes.windll.gdi32; rect=wintypes.RECT(); u.GetClientRect(hwnd,ctypes.byref(rect)); w,h=rect.right,rect.bottom
    if w<=0 or h<=0 or not u.IsWindowVisible(hwnd): raise EvidenceError("Acceptance-Fenster ist nicht sichtbar.")
    dc=u.GetDC(hwnd); mem=g.CreateCompatibleDC(dc); bmp=g.CreateCompatibleBitmap(dc,w,h); old=g.SelectObject(mem,bmp)
    try:
        if not g.BitBlt(mem,0,0,w,h,dc,0,0,0x00CC0020): raise EvidenceError("Client-Capture fehlgeschlagen.")
        info=ctypes.create_string_buffer(struct.pack("<IiiHHIIiiII",40,w,-h,1,32,0,w*h*4,0,0,0,0)); pixels=ctypes.create_string_buffer(w*h*4); g.GetDIBits(mem,bmp,0,h,pixels,info,0); b=pixels.raw; _write_png(target,w,h,b"".join(b[i+2:i+3]+b[i+1:i+2]+b[i:i+1]+b"\xff" for i in range(0,len(b),4)))
    finally: g.SelectObject(mem,old); g.DeleteObject(bmp); g.DeleteDC(mem); u.ReleaseDC(hwnd,dc)
    return w,h
def current_windows_dpi_scale(hwnd: int) -> int:
    import ctypes
    return round(int(ctypes.windll.user32.GetDpiForWindow(hwnd))*100/96)


# --- Additive Screen-1 visual acceptance v2 (#700 / #691) --------------------
# Historical ``screen1_visual_fixture_v1`` above stays frozen #503 evidence.
# Do not retarget REQUIRED_STATE_IDS / FIXTURE_VERSION / portfolio captures.

FIXTURE_VERSION_V2 = "screen1_visual_fixture_v2"
REQUIRED_STATE_IDS_V2 = (
    "screen1-clean-start",
    "screen1-active-source",
    "screen1-harmonic-open",
    "screen1-elastic-resized",
)

# Declared acceptance modes (documentation + fixture identity). Product density
# (#692) and elastic solver (#694) are NOT applied by this QA contract.
DENSITY_MODE_V2_COMPACT_TARGET = "compact_target_30dip"
DENSITY_MODE_V2_HISTORICAL_BASELINE = "historical_browser_row_66"
MOTION_MODE_FULL = "full"
MOTION_MODE_REDUCED = "reduced"
MOTION_MODE_OFF = "off"

# Canonical default panel ratios for active workspace (sum == 1.0).
# Keys omitted or 0.0 mean the panel is not an active materialised working pane.
CANONICAL_ACTIVE_SOURCE_RATIOS_V2: Mapping[str, float] = {
    "source_nav": 0.18,
    "browser": 0.57,
    "live_kit": 0.25,
}
CANONICAL_HARMONIC_OPEN_RATIOS_V2: Mapping[str, float] = {
    "source_nav": 0.16,
    "browser": 0.44,
    "harmonic": 0.20,
    "live_kit": 0.20,
}
# Deterministic non-default ratios for elastic-resized acceptance representation.
ELASTIC_RESIZED_RATIOS_V2: Mapping[str, float] = {
    "source_nav": 0.12,
    "browser": 0.63,
    "live_kit": 0.25,
}


@dataclass(frozen=True)
class Screen1PanelLayoutV2:
    """Declared panel visibility + ratios for one calm-workspace acceptance state."""

    source_nav_visible: bool
    calm_canvas_visible: bool
    browser_materialized: bool
    harmonic_visible: bool
    live_kit_materialized: bool
    panel_ratios: Mapping[str, float]


@dataclass(frozen=True)
class Screen1VisualStateV2:
    """One deterministic Screen-1 calm-workspace acceptance state (#700)."""

    state_id: str
    source_selected: bool
    selected_source_label: str | None
    selected_browser_index: int | None
    preview_active: bool
    auto_audition: bool
    density_mode: str
    motion_mode: str
    layout: Screen1PanelLayoutV2
    browser_fixture_row_count: int
    harmony_fixture_row_count: int


@dataclass(frozen=True)
class Screen1VisualFixtureV2:
    """Additive v2 fixture bundle shared by #692–#696 acceptance."""

    version: str
    library_labels: tuple[str, ...]
    browser_rows: tuple[WorkbenchRow, ...]
    harmony_results: tuple[HarmonySuggestion, ...]
    assignments: Mapping[str, Mapping[str, WorkbenchRow | None]]
    states: Mapping[str, Screen1VisualStateV2]
    state_ids: tuple[str, ...]


def _ratios_sum_ok(ratios: Mapping[str, float]) -> bool:
    if not ratios:
        return False
    values: list[float] = []
    for raw in ratios.values():
        value = float(raw)
        if value != value or value == float("inf") or value == float("-inf"):
            return False
        if value < 0.0:
            return False
        if value > 0.0:
            values.append(value)
    if not values:
        return False
    return abs(sum(values) - 1.0) <= 1e-9


def _layout(
    *,
    source_nav_visible: bool,
    calm_canvas_visible: bool,
    browser_materialized: bool,
    harmonic_visible: bool,
    live_kit_materialized: bool,
    panel_ratios: Mapping[str, float],
) -> Screen1PanelLayoutV2:
    frozen = {str(k): float(v) for k, v in panel_ratios.items()}
    if not _ratios_sum_ok(frozen):
        raise EvidenceError("panel_ratios must sum to 1.0 for positive entries")
    return Screen1PanelLayoutV2(
        source_nav_visible=source_nav_visible,
        calm_canvas_visible=calm_canvas_visible,
        browser_materialized=browser_materialized,
        harmonic_visible=harmonic_visible,
        live_kit_materialized=live_kit_materialized,
        panel_ratios=frozen,
    )


def build_screen1_visual_fixture_v2() -> Screen1VisualFixtureV2:
    """Build the additive calm-workspace acceptance fixture (no product apply)."""

    # Reuse the same synthetic catalogue as v1 so later slices share row identity,
    # without coupling v2 state IDs to historical 3panel/4panel semantics.
    v1 = build_screen1_visual_fixture_v1()
    rows = v1.browser_rows
    matches = v1.harmony_results
    # Active workspace may show Live Kit as an existing working pane; clean-start
    # declares it not materialised even though assignment data can still exist.
    assignments: dict[str, dict[str, WorkbenchRow | None]] = {
        "Drums": {
            "Main Drum": rows[0],
            "Closed Hat": rows[5],
            "Open Hat": rows[6],
        }
    }

    clean = Screen1VisualStateV2(
        state_id="screen1-clean-start",
        source_selected=False,
        selected_source_label=None,
        selected_browser_index=None,
        preview_active=False,
        auto_audition=False,
        density_mode=DENSITY_MODE_V2_COMPACT_TARGET,
        motion_mode=MOTION_MODE_FULL,
        layout=_layout(
            source_nav_visible=True,
            calm_canvas_visible=True,
            browser_materialized=False,
            harmonic_visible=False,
            live_kit_materialized=False,
            panel_ratios={"source_nav": 1.0},
        ),
        browser_fixture_row_count=0,
        harmony_fixture_row_count=0,
    )
    active = Screen1VisualStateV2(
        state_id="screen1-active-source",
        source_selected=True,
        selected_source_label="Techno",
        selected_browser_index=2,
        preview_active=False,
        auto_audition=False,
        density_mode=DENSITY_MODE_V2_COMPACT_TARGET,
        motion_mode=MOTION_MODE_FULL,
        layout=_layout(
            source_nav_visible=True,
            calm_canvas_visible=False,
            browser_materialized=True,
            harmonic_visible=False,
            live_kit_materialized=True,
            panel_ratios=CANONICAL_ACTIVE_SOURCE_RATIOS_V2,
        ),
        browser_fixture_row_count=len(rows),
        harmony_fixture_row_count=0,
    )
    harmonic = Screen1VisualStateV2(
        state_id="screen1-harmonic-open",
        source_selected=True,
        selected_source_label="Techno",
        selected_browser_index=2,
        preview_active=False,
        auto_audition=False,
        density_mode=DENSITY_MODE_V2_COMPACT_TARGET,
        motion_mode=MOTION_MODE_FULL,
        layout=_layout(
            source_nav_visible=True,
            calm_canvas_visible=False,
            browser_materialized=True,
            harmonic_visible=True,
            live_kit_materialized=True,
            panel_ratios=CANONICAL_HARMONIC_OPEN_RATIOS_V2,
        ),
        browser_fixture_row_count=len(rows),
        harmony_fixture_row_count=len(matches),
    )
    elastic = Screen1VisualStateV2(
        state_id="screen1-elastic-resized",
        source_selected=True,
        selected_source_label="Techno",
        selected_browser_index=2,
        preview_active=False,
        auto_audition=False,
        density_mode=DENSITY_MODE_V2_COMPACT_TARGET,
        motion_mode=MOTION_MODE_FULL,
        layout=_layout(
            source_nav_visible=True,
            calm_canvas_visible=False,
            browser_materialized=True,
            harmonic_visible=False,
            live_kit_materialized=True,
            panel_ratios=ELASTIC_RESIZED_RATIOS_V2,
        ),
        browser_fixture_row_count=len(rows),
        harmony_fixture_row_count=0,
    )
    states = {
        clean.state_id: clean,
        active.state_id: active,
        harmonic.state_id: harmonic,
        elastic.state_id: elastic,
    }
    return Screen1VisualFixtureV2(
        version=FIXTURE_VERSION_V2,
        library_labels=v1.library_labels,
        browser_rows=rows,
        harmony_results=matches,
        assignments=assignments,
        states=states,
        state_ids=REQUIRED_STATE_IDS_V2,
    )


def resolve_screen1_visual_state_v2(
    fixture: Screen1VisualFixtureV2, state_id: str
) -> Screen1VisualStateV2:
    if state_id not in REQUIRED_STATE_IDS_V2:
        raise EvidenceError(f"Unknown Screen-1 v2 acceptance state: {state_id!r}")
    try:
        return fixture.states[state_id]
    except KeyError as exc:
        raise EvidenceError(f"Missing Screen-1 v2 acceptance state: {state_id!r}") from exc


def validate_screen1_visual_fixture_v2(fixture: Screen1VisualFixtureV2) -> None:
    if fixture.version != FIXTURE_VERSION_V2:
        raise EvidenceError("Unexpected Screen-1 v2 fixture version")
    if fixture.state_ids != REQUIRED_STATE_IDS_V2:
        raise EvidenceError("Screen-1 v2 state_ids must match REQUIRED_STATE_IDS_V2")
    if tuple(fixture.states) != REQUIRED_STATE_IDS_V2:
        raise EvidenceError("Screen-1 v2 states mapping order/keys invalid")
    for state_id in REQUIRED_STATE_IDS_V2:
        state = resolve_screen1_visual_state_v2(fixture, state_id)
        if state.state_id != state_id:
            raise EvidenceError("state_id mismatch inside Screen-1 v2 fixture")
        if not _ratios_sum_ok(state.layout.panel_ratios):
            raise EvidenceError(f"Invalid panel_ratios for {state_id}")
        if state.auto_audition:
            raise EvidenceError("v2 acceptance states must not enable auto_audition")
        if state.preview_active:
            raise EvidenceError("v2 acceptance states must not enable preview_active")
        if "\\" in json.dumps(state.layout.panel_ratios) or _private(
            {
                "label": state.selected_source_label,
                "density": state.density_mode,
                "motion": state.motion_mode,
            }
        ):
            raise EvidenceError("v2 fixture contains private path data")


def build_visual_evidence_manifest_v2(
    *,
    runtime_report: RuntimeReport,
    fixture: Screen1VisualFixtureV2,
    captures: Mapping[str, Path],
    os_name: str,
    dpi_scale: int,
    client_width: int,
    client_height: int,
    sanity_results: Mapping[str, object],
) -> dict[str, object]:
    """Manifest builder for v2 captures — parallel to v1, does not replace it."""
    validate_runtime_for_visual_acceptance(runtime_report)
    validate_screen1_visual_fixture_v2(fixture)
    if tuple(captures) != REQUIRED_STATE_IDS_V2:
        raise EvidenceError("All four Screen-1 v2 acceptance captures are required.")
    if (client_width, client_height, dpi_scale) != (CLIENT_WIDTH, CLIENT_HEIGHT, 100):
        raise EvidenceError("Capture-Baseline ist ungültig.")
    if not all(path.is_file() for path in captures.values()):
        raise EvidenceError("Capture-Datei fehlt.")
    result = {
        "schema": MANIFEST_SCHEMA,
        "commit": runtime_report.manifest.commit,
        "channel": runtime_report.manifest.channel,
        "runtime_status": "valid",
        "python": (
            f"{platform.python_implementation()} {platform.python_version()}"
        ),
        "os": os_name,
        "dpi": dpi_scale,
        "client_width": client_width,
        "client_height": client_height,
        "fixture": fixture.version,
        "states": list(REQUIRED_STATE_IDS_V2),
        "state_contracts": {
            state_id: {
                "source_selected": state.source_selected,
                "selected_source_label": state.selected_source_label,
                "selected_browser_index": state.selected_browser_index,
                "preview_active": state.preview_active,
                "auto_audition": state.auto_audition,
                "density_mode": state.density_mode,
                "motion_mode": state.motion_mode,
                "source_nav_visible": state.layout.source_nav_visible,
                "calm_canvas_visible": state.layout.calm_canvas_visible,
                "browser_materialized": state.layout.browser_materialized,
                "harmonic_visible": state.layout.harmonic_visible,
                "live_kit_materialized": state.layout.live_kit_materialized,
                "panel_ratios": dict(state.layout.panel_ratios),
                "browser_fixture_row_count": state.browser_fixture_row_count,
                "harmony_fixture_row_count": state.harmony_fixture_row_count,
            }
            for state_id, state in (
                (sid, resolve_screen1_visual_state_v2(fixture, sid))
                for sid in REQUIRED_STATE_IDS_V2
            )
        },
        "screenshot_hashes": {k: _sha(v) for k, v in captures.items()},
        "sanity_results": dict(sanity_results),
        "created_at": datetime.now(UTC).isoformat(),
    }
    if _private(result):
        raise EvidenceError("Evidence enthält private Pfaddaten.")
    return result
