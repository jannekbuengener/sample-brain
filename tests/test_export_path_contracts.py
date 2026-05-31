from __future__ import annotations

from pathlib import Path

import pytest

from src.export_fl import resolve_export_path, run_export


def test_resolve_export_path_with_single_root_match(tmp_path: Path):
    root = tmp_path / "library"
    sample_path = root / "drums" / "kick.wav"
    final_path, warning = resolve_export_path(
        path=str(sample_path),
        relpath="drums/kick.wav",
        roots=[root],
    )
    assert final_path == str(sample_path)
    assert warning is None


def test_resolve_export_path_prefers_matching_root_in_multi_root(tmp_path: Path):
    root_a = tmp_path / "library_a"
    root_b = tmp_path / "library_b"
    sample_path = root_b / "loops" / "perc.wav"
    final_path, warning = resolve_export_path(
        path=str(sample_path),
        relpath="loops/perc.wav",
        roots=[root_a, root_b],
    )
    assert final_path == str(sample_path)
    assert warning is None


def test_resolve_export_path_warns_when_no_root_matches(tmp_path: Path):
    root_a = tmp_path / "library_a"
    root_b = tmp_path / "library_b"
    outside_path = tmp_path / "outside" / "fx.wav"
    final_path, warning = resolve_export_path(
        path=str(outside_path),
        relpath="fx.wav",
        roots=[root_a, root_b],
    )
    assert final_path == str(outside_path)
    assert warning is not None
    assert "Could not resolve sample path" in warning


def test_resolve_export_path_without_roots_keeps_stored_path(tmp_path: Path):
    sample_path = tmp_path / "samples" / "snare.wav"
    final_path, warning = resolve_export_path(
        path=str(sample_path),
        relpath="samples/snare.wav",
        roots=[],
    )
    assert final_path == str(sample_path)
    assert warning is None


def test_run_export_rejects_empty_fl_user_data():
    with pytest.raises(ValueError, match="FL user data path is empty"):
        run_export(fl_user_data_folder="   ", roots=[])
