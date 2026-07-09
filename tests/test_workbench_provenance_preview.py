"""Workbench preview UX for auto-metadata provenance (#178)."""
from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.workbench_controller import (
    WorkbenchRow,
    format_metadata_provenance_hint,
    format_metadata_provenance_label,
)
from src.workbench_library import WorkbenchCueMetadata
from tests.audio_fixtures import write_sine_wav


def test_format_metadata_provenance_label_maps_known_sources():
    assert format_metadata_provenance_label("detected") == "erkannt"
    assert format_metadata_provenance_label("manual") == "manuell"
    assert format_metadata_provenance_label("DETECTED") == "erkannt"


def test_format_metadata_provenance_label_hides_unknown_and_empty():
    assert format_metadata_provenance_label(None) is None
    assert format_metadata_provenance_label("") is None
    assert format_metadata_provenance_label("default") is None


def test_format_metadata_provenance_hint_loop_detected():
    metadata = WorkbenchCueMetadata(loop_source="detected")
    assert format_metadata_provenance_hint(metadata) == "Loop: erkannt"


def test_format_metadata_provenance_hint_attack_manual():
    metadata = WorkbenchCueMetadata(attack_source="manual")
    assert format_metadata_provenance_hint(metadata) == "Attack: manuell"


def test_format_metadata_provenance_hint_cue_detected():
    metadata = WorkbenchCueMetadata(cue_source="detected")
    assert format_metadata_provenance_hint(metadata) == "Cue: erkannt"


def test_format_metadata_provenance_hint_all_none_sources():
    metadata = WorkbenchCueMetadata(
        loop_source=None,
        attack_source=None,
        cue_source="manual",
    )
    assert format_metadata_provenance_hint(metadata) == ""


def test_format_metadata_provenance_hint_cue_manual_only_when_updated():
    metadata = WorkbenchCueMetadata(cue_source="manual", cue_updated_at=None)
    assert format_metadata_provenance_hint(metadata) == ""

    metadata = WorkbenchCueMetadata(
        cue_source="manual",
        cue_updated_at="2026-07-09T12:00:00",
    )
    assert format_metadata_provenance_hint(metadata) == "Cue: manuell"


def test_format_metadata_provenance_hint_joins_multiple_fields():
    metadata = WorkbenchCueMetadata(
        loop_source="detected",
        attack_source="manual",
        cue_source="detected",
    )
    assert format_metadata_provenance_hint(metadata) == (
        "Loop: erkannt · Attack: manuell · Cue: erkannt"
    )


def _workbench_module():
    return importlib.import_module("src.workbench")


def _sample_row(path: Path) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=path.name,
        relative_path=path.name,
        path=str(path.resolve()),
        bpm=120.0,
        key="C",
        key_conf=0.9,
        loudness=-10.0,
        brightness=50.0,
        sample_class="kick",
        pred_type="kick",
        status="ok",
    )


def _provenance_app():
    cls = _workbench_module().WorkbenchApp
    app = cls.__new__(cls)
    values: dict[str, str] = {"value": ""}
    app._provenance_var = SimpleNamespace(
        value="",
        set=lambda text: values.__setitem__("value", str(text)),
        get=lambda: values["value"],
    )
    app._provenance_values = values
    return app


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        (WorkbenchCueMetadata(loop_source="detected"), "Loop: erkannt"),
        (WorkbenchCueMetadata(attack_source="manual"), "Attack: manuell"),
        (WorkbenchCueMetadata(cue_source="detected"), "Cue: erkannt"),
        (
            WorkbenchCueMetadata(
                loop_source=None,
                attack_source=None,
                cue_source="manual",
            ),
            "",
        ),
    ],
)
def test_update_metadata_provenance_display(tmp_path: Path, metadata, expected: str):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.2, frequency_hz=440.0)
    app = _provenance_app()
    row = _sample_row(wav)

    with patch("src.workbench.load_workbench_sample_cue", return_value=metadata):
        app._update_metadata_provenance_display(row)

    assert app._provenance_values["value"] == expected


def test_update_metadata_provenance_display_clears_without_row():
    app = _provenance_app()
    app._provenance_values["value"] = "Loop: erkannt"
    app._update_metadata_provenance_display(None)
    assert app._provenance_values["value"] == ""


def test_update_metadata_provenance_display_survives_load_error(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.2, frequency_hz=440.0)
    app = _provenance_app()
    row = _sample_row(wav)

    with patch("src.workbench.load_workbench_sample_cue", side_effect=RuntimeError("boom")):
        app._update_metadata_provenance_display(row)

    assert app._provenance_values["value"] == ""


def test_manual_loop_edit_updates_provenance_display(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.5, frequency_hz=440.0)
    app = _provenance_app()
    row = _sample_row(wav)

    after_save = WorkbenchCueMetadata(
        loop_start_ms=100,
        loop_end_ms=300,
        loop_source="manual",
    )

    with patch("src.workbench.load_workbench_sample_cue", return_value=after_save):
        app._update_metadata_provenance_display(row)

    assert app._provenance_values["value"] == "Loop: manuell"
