"""Frozen contracts for the optional Screen-1 Qt Quick proof spike."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from src.runtime_provenance import RuntimeManifest, RuntimeStatus
from src.workbench_controller import WorkbenchRow
from src.workbench_visual_acceptance import (
    CLIENT_HEIGHT,
    CLIENT_WIDTH,
    EvidenceError,
    REQUIRED_STATE_IDS,
    build_screen1_visual_fixture_v1,
    build_visual_evidence_manifest,
)


PROVENANCE_COMMIT = "b" * 40


def _renderer_runtime(tmp_path: Path) -> tuple[Path, Path, Path, RuntimeManifest]:
    root = tmp_path / "runtime"
    python = root / ".venv" / "Scripts" / "python.exe"
    src = root / "src"
    python.parent.mkdir(parents=True)
    src.mkdir()
    python.write_text("", encoding="utf-8")
    for name in (
        "cli.py",
        "workbench.py",
        "workbench_qml_spike.py",
        "workbench_visual_acceptance.py",
    ):
        (src / name).write_text("", encoding="utf-8")
    manifest = RuntimeManifest(
        schema=1,
        channel="spike",
        commit=PROVENANCE_COMMIT,
        runtime_root=str(root),
        python_executable=str(python),
        installed_at="2026-09-09T12:00:00Z",
    )
    return root, python, tmp_path / "runtime-manifest.json", manifest


def _provenance_git(head: str = PROVENANCE_COMMIT):
    def run(*args: str) -> str:
        if args[-2:] == ("rev-parse", "HEAD"):
            return head
        if args[-2:] == ("status", "--porcelain"):
            return ""
        raise AssertionError(args)

    return run


def _write_manifest(path: Path, manifest: RuntimeManifest) -> None:
    path.write_text(json.dumps(manifest.to_dict()), encoding="utf-8")


def _renderer_paths(root: Path) -> dict[str, Path]:
    return {
        "src.cli": root / "src" / "cli.py",
        "src.workbench": root / "src" / "workbench.py",
        "src.workbench_qml_spike": root / "src" / "workbench_qml_spike.py",
        "src.workbench_visual_acceptance": root
        / "src"
        / "workbench_visual_acceptance.py",
    }


def _surface():
    """Import the new optional renderer boundary without requiring PySide6."""
    try:
        return importlib.import_module("src.workbench_qml_spike")
    except ModuleNotFoundError as exc:
        if exc.name == "src.workbench_qml_spike":
            raise AssertionError("MISSING_PRODUCTION_SURFACE: Qt Quick proof spike") from exc
        raise


def test_view_model_reuses_the_public_visual_fixture_for_both_required_states():
    surface = _surface()
    fixture = build_screen1_visual_fixture_v1()

    default = surface.Screen1QmlViewModel.from_fixture(
        fixture, "screen1-default-3panel"
    )
    harmonic = surface.Screen1QmlViewModel.from_fixture(
        fixture, "screen1-harmonic-4panel"
    )

    assert default.panel_count == 3
    assert harmonic.panel_count == 4
    assert default.browser_rows[fixture.selected_browser_index].source_row is fixture.browser_rows[2]
    assert harmonic.harmony_rows[0].source_row is fixture.harmony_results[0].row
    assert default.live_kit_groups[1].name == "Drums"
    assert default.live_kit_groups[1].slots[0].assignment is fixture.browser_rows[0]


def test_view_model_routes_selection_once_to_the_existing_python_callback():
    surface = _surface()
    fixture = build_screen1_visual_fixture_v1()
    selected: list[WorkbenchRow] = []
    view_model = surface.Screen1QmlViewModel.from_fixture(
        fixture,
        "screen1-default-3panel",
        on_browser_selected=selected.append,
    )

    result = view_model.select_browser_index(4)

    assert result is fixture.browser_rows[4]
    assert selected == [fixture.browser_rows[4]]
    assert view_model.selected_browser_index == 4


def test_virtual_window_is_bounded_for_a_50k_library_and_keeps_selection_visible():
    surface = _surface()
    rows = tuple(
        WorkbenchRow(
            display_name=f"SYNTH_{index:05d}",
            relative_path=f"fixture/SYNTH_{index:05d}.wav",
            path=f"fixture/SYNTH_{index:05d}.wav",
            bpm=132.0,
            key=None,
            key_conf=None,
            loudness=None,
            brightness=None,
            sample_class="one_shot",
            pred_type="Kick",
            status="ok",
            details={},
        )
        for index in range(50_000)
    )

    window = surface.virtual_row_window(
        rows, selected_index=49_999, visible_rows=12, cache_buffer_rows=4
    )

    assert window.total_rows == 50_000
    assert len(window.rows) <= 20
    assert window.rows[-1].source_row is rows[-1]
    assert window.first_index <= 49_999 <= window.last_index


def test_qml_source_declares_a_recycling_listview_without_importing_pyside_on_core_import():
    surface = _surface()

    assert "ListView" in surface.QML_SOURCE
    assert "reuseItems: true" in surface.QML_SOURCE
    assert surface.qml_runtime_available() in {True, False}


def test_qml_capture_accepts_only_a_renderer_proven_from_the_validated_runtime(
    tmp_path: Path,
):
    surface = _surface()
    root, python, manifest_path, runtime_manifest = _renderer_runtime(tmp_path)
    _write_manifest(manifest_path, runtime_manifest)

    report = surface.validate_qml_renderer_provenance(
        root,
        manifest_path=manifest_path,
        executable=python,
        module_paths=_renderer_paths(root),
        git_run=_provenance_git(),
    )

    captures = {}
    for state_id in REQUIRED_STATE_IDS:
        capture = tmp_path / f"{state_id}.png"
        capture.write_bytes(b"synthetic-capture")
        captures[state_id] = capture
    evidence = build_visual_evidence_manifest(
        runtime_report=report,
        fixture=build_screen1_visual_fixture_v1(),
        captures=captures,
        os_name="Windows 11",
        dpi_scale=100,
        client_width=CLIENT_WIDTH,
        client_height=CLIENT_HEIGHT,
        sanity_results={},
    )

    assert report.status is RuntimeStatus.VALID
    assert evidence["commit"] == PROVENANCE_COMMIT


@pytest.mark.parametrize(
    ("module_name", "expected_message"),
    (
        ("src.cli", "nicht VALID"),
        ("src.workbench_qml_spike", "nicht aus dem Runtime-Root"),
        ("src.workbench_visual_acceptance", "nicht aus dem Runtime-Root"),
    ),
)
def test_qml_capture_rejects_renderer_imported_from_another_checkout(
    tmp_path: Path, module_name: str, expected_message: str
):
    surface = _surface()
    root, python, manifest_path, runtime_manifest = _renderer_runtime(tmp_path)
    _write_manifest(manifest_path, runtime_manifest)
    module_paths = _renderer_paths(root)
    module_paths[module_name] = tmp_path / "other-checkout" / "src" / "foreign.py"

    with pytest.raises(EvidenceError, match=expected_message):
        surface.validate_qml_renderer_provenance(
            root,
            manifest_path=manifest_path,
            executable=python,
            module_paths=module_paths,
            git_run=_provenance_git(),
        )


def test_qml_capture_rejects_an_interpreter_outside_the_runtime_venv(tmp_path: Path):
    surface = _surface()
    root, _python, manifest_path, runtime_manifest = _renderer_runtime(tmp_path)
    foreign_python = tmp_path / "other-checkout" / ".venv" / "Scripts" / "python.exe"
    foreign_python.parent.mkdir(parents=True)
    foreign_python.write_text("", encoding="utf-8")
    _write_manifest(
        manifest_path,
        RuntimeManifest(
            schema=runtime_manifest.schema,
            channel=runtime_manifest.channel,
            commit=runtime_manifest.commit,
            runtime_root=runtime_manifest.runtime_root,
            python_executable=str(foreign_python),
            installed_at=runtime_manifest.installed_at,
        ),
    )

    with pytest.raises(EvidenceError, match="Runtime-.venv"):
        surface.validate_qml_renderer_provenance(
            root,
            manifest_path=manifest_path,
            executable=foreign_python,
            module_paths=_renderer_paths(root),
            git_run=_provenance_git(),
        )


def test_qml_capture_keeps_manifest_head_mismatch_fail_closed(tmp_path: Path):
    surface = _surface()
    root, python, manifest_path, runtime_manifest = _renderer_runtime(tmp_path)
    _write_manifest(manifest_path, runtime_manifest)

    with pytest.raises(EvidenceError, match="nicht VALID"):
        surface.validate_qml_renderer_provenance(
            root,
            manifest_path=manifest_path,
            executable=python,
            module_paths=_renderer_paths(root),
            git_run=_provenance_git("c" * 40),
        )
