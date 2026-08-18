from __future__ import annotations

from pathlib import Path

import pytest

import src.export_fl as export_fl
from src.export_fl import resolve_export_path, run_export, write_fl_tags_from_sample_rows


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


def _sample_rows(root: Path) -> list[tuple]:
    sample = root / "drums" / "kick.wav"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_bytes(b"data")
    return [
        (
            str(sample),
            "drums/kick.wav",
            2.5,
            2000.0,
            -20.0,
            "loop",
            "Am",
            0.8,
            128.0,
            "Kick",
        )
    ]


def test_write_fl_tags_from_sample_rows_writes_expected_file(tmp_path: Path):
    root = tmp_path / "library"
    rows = _sample_rows(root)
    fl_user = tmp_path / "fl_user"

    tags_path, count, warnings = write_fl_tags_from_sample_rows(rows, fl_user, [root])

    assert count == 1
    assert warnings == []
    assert tags_path.is_file()
    content = tags_path.read_text(encoding="utf-8")
    assert content.startswith("@TagCase=*")
    assert "kick.wav" in content
    assert "Kick" in content


def test_write_fl_tags_replaces_existing_target_atomically(tmp_path: Path):
    root = tmp_path / "library"
    rows = _sample_rows(root)
    fl_user = tmp_path / "fl_user"
    tags_path = fl_user / "FL Studio" / "Settings" / "Browser" / "Tags"
    tags_path.parent.mkdir(parents=True, exist_ok=True)
    tags_path.write_text("OLD\n", encoding="utf-8")

    written_path, count, warnings = write_fl_tags_from_sample_rows(rows, fl_user, [root])

    assert written_path == tags_path
    assert count == 1
    assert warnings == []
    assert tags_path.read_text(encoding="utf-8") != "OLD\n"
    assert not list(tags_path.parent.glob(f".{tags_path.name}.*.tmp"))


def test_write_fl_tags_keeps_existing_target_on_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "library"
    rows = _sample_rows(root)
    fl_user = tmp_path / "fl_user"
    tags_path = fl_user / "FL Studio" / "Settings" / "Browser" / "Tags"
    tags_path.parent.mkdir(parents=True, exist_ok=True)
    tags_path.write_text("KEEP-ME\n", encoding="utf-8")

    def fail_write(handle, payload):
        handle.write(payload[:5])
        raise OSError("simulated write failure")

    monkeypatch.setattr(export_fl, "_write_tags_payload", fail_write)

    with pytest.raises(OSError, match="simulated write failure"):
        write_fl_tags_from_sample_rows(rows, fl_user, [root])

    assert tags_path.read_text(encoding="utf-8") == "KEEP-ME\n"
    assert not list(tags_path.parent.glob(f".{tags_path.name}.*.tmp"))
