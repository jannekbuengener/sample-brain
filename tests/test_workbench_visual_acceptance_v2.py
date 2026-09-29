"""TEST_GATE — Screen-1 visual acceptance v2 (#700).

Additive calm-workspace fixture contract. Historical v1 remains frozen.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from src.runtime_provenance import RuntimeManifest, RuntimeReport, RuntimeStatus
from src.workbench_visual_acceptance import (
    CANONICAL_ACTIVE_SOURCE_RATIOS_V2,
    CANONICAL_HARMONIC_OPEN_RATIOS_V2,
    CLIENT_HEIGHT,
    CLIENT_WIDTH,
    DENSITY_MODE_V2_COMPACT_TARGET,
    ELASTIC_RESIZED_RATIOS_V2,
    EvidenceError,
    FIXTURE_VERSION,
    FIXTURE_VERSION_V2,
    MOTION_MODE_FULL,
    REQUIRED_STATE_IDS,
    REQUIRED_STATE_IDS_V2,
    build_screen1_visual_fixture_v1,
    build_screen1_visual_fixture_v2,
    build_visual_evidence_manifest,
    build_visual_evidence_manifest_v2,
    resolve_screen1_visual_state_v2,
    validate_screen1_visual_fixture_v2,
)


def _report(status: RuntimeStatus = RuntimeStatus.VALID) -> RuntimeReport:
    return RuntimeReport(
        status,
        "test",
        RuntimeManifest(1, "main", "a" * 40, "runtime", "python", "now"),
    )


def _png(path: Path, pixels: bytes = b"\x12\x34\x56\xff") -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\0" + pixels))
        + chunk(b"IEND", b"")
    )


def test_v1_fixture_contract_remains_frozen():
    fixture = build_screen1_visual_fixture_v1()
    assert fixture.version == FIXTURE_VERSION == "screen1_visual_fixture_v1"
    assert fixture.state_ids == REQUIRED_STATE_IDS == (
        "screen1-default-3panel",
        "screen1-harmonic-4panel",
    )
    assert len(fixture.browser_rows) == 12
    assert fixture.browser_rows[2].display_name == "TECH_BASS_01"


def test_v2_public_state_ids_and_version():
    assert FIXTURE_VERSION_V2 == "screen1_visual_fixture_v2"
    assert REQUIRED_STATE_IDS_V2 == (
        "screen1-clean-start",
        "screen1-active-source",
        "screen1-harmonic-open",
        "screen1-elastic-resized",
    )
    # v2 must not collide with historical v1 IDs.
    assert set(REQUIRED_STATE_IDS_V2).isdisjoint(REQUIRED_STATE_IDS)


def test_v2_fixture_clean_start_semantics():
    fixture = build_screen1_visual_fixture_v2()
    validate_screen1_visual_fixture_v2(fixture)
    state = resolve_screen1_visual_state_v2(fixture, "screen1-clean-start")
    assert state.source_selected is False
    assert state.selected_source_label is None
    assert state.selected_browser_index is None
    assert state.preview_active is False
    assert state.auto_audition is False
    assert state.density_mode == DENSITY_MODE_V2_COMPACT_TARGET
    assert state.motion_mode == MOTION_MODE_FULL
    assert state.layout.source_nav_visible is True
    assert state.layout.calm_canvas_visible is True
    assert state.layout.browser_materialized is False
    assert state.layout.harmonic_visible is False
    assert state.layout.live_kit_materialized is False
    assert state.layout.panel_ratios == {"source_nav": 1.0}
    assert state.browser_fixture_row_count == 0
    assert state.harmony_fixture_row_count == 0


def test_v2_fixture_active_source_semantics():
    fixture = build_screen1_visual_fixture_v2()
    state = resolve_screen1_visual_state_v2(fixture, "screen1-active-source")
    assert state.source_selected is True
    assert state.selected_source_label == "Techno"
    assert state.selected_browser_index == 2
    assert fixture.browser_rows[2].display_name == "TECH_BASS_01"
    assert state.preview_active is False
    assert state.auto_audition is False
    assert state.layout.browser_materialized is True
    assert state.layout.harmonic_visible is False
    assert state.layout.live_kit_materialized is True
    assert state.layout.calm_canvas_visible is False
    assert dict(state.layout.panel_ratios) == dict(CANONICAL_ACTIVE_SOURCE_RATIOS_V2)
    assert state.browser_fixture_row_count == 12
    assert state.harmony_fixture_row_count == 0


def test_v2_fixture_harmonic_open_semantics():
    fixture = build_screen1_visual_fixture_v2()
    state = resolve_screen1_visual_state_v2(fixture, "screen1-harmonic-open")
    assert state.source_selected is True
    assert state.layout.browser_materialized is True
    assert state.layout.harmonic_visible is True
    assert state.layout.live_kit_materialized is True
    assert dict(state.layout.panel_ratios) == dict(CANONICAL_HARMONIC_OPEN_RATIOS_V2)
    assert state.harmony_fixture_row_count == 6
    assert len(fixture.harmony_results) == 6


def test_v2_fixture_elastic_resized_uses_non_default_ratios():
    fixture = build_screen1_visual_fixture_v2()
    state = resolve_screen1_visual_state_v2(fixture, "screen1-elastic-resized")
    assert state.source_selected is True
    assert state.layout.browser_materialized is True
    assert state.layout.harmonic_visible is False
    assert dict(state.layout.panel_ratios) == dict(ELASTIC_RESIZED_RATIOS_V2)
    assert dict(state.layout.panel_ratios) != dict(CANONICAL_ACTIVE_SOURCE_RATIOS_V2)
    assert abs(sum(state.layout.panel_ratios.values()) - 1.0) <= 1e-9


def test_v2_unknown_state_fail_closed():
    fixture = build_screen1_visual_fixture_v2()
    with pytest.raises(EvidenceError, match="Unknown Screen-1 v2"):
        resolve_screen1_visual_state_v2(fixture, "screen1-default-3panel")


def test_v2_manifest_requires_four_captures(tmp_path: Path):
    fixture = build_screen1_visual_fixture_v2()
    paths = {}
    for state_id in REQUIRED_STATE_IDS_V2:
        paths[state_id] = tmp_path / f"{state_id}.png"
        _png(paths[state_id])
    result = build_visual_evidence_manifest_v2(
        runtime_report=_report(),
        fixture=fixture,
        captures=paths,
        os_name="Windows 11",
        dpi_scale=100,
        client_width=CLIENT_WIDTH,
        client_height=CLIENT_HEIGHT,
        sanity_results={},
    )
    assert result["fixture"] == FIXTURE_VERSION_V2
    assert result["states"] == list(REQUIRED_STATE_IDS_V2)
    assert set(result["screenshot_hashes"]) == set(REQUIRED_STATE_IDS_V2)
    assert result["state_contracts"]["screen1-clean-start"]["browser_materialized"] is False
    assert result["state_contracts"]["screen1-active-source"]["auto_audition"] is False
    assert "runtime_root" not in str(result)
    assert "C:\\" not in str(result)


def test_v1_manifest_path_still_requires_only_v1_states(tmp_path: Path):
    paths = {}
    for state_id in REQUIRED_STATE_IDS:
        paths[state_id] = tmp_path / f"{state_id}.png"
        _png(paths[state_id])
    result = build_visual_evidence_manifest(
        runtime_report=_report(),
        fixture=build_screen1_visual_fixture_v1(),
        captures=paths,
        os_name="Windows 11",
        dpi_scale=100,
        client_width=CLIENT_WIDTH,
        client_height=CLIENT_HEIGHT,
        sanity_results={},
    )
    assert result["fixture"] == FIXTURE_VERSION
    assert result["states"] == list(REQUIRED_STATE_IDS)
