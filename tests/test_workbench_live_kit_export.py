"""Contracts for #728 Live Kit local-folder export.

Pure Python export service: deterministic portable structure, byte-identical
audio copies, fail-closed empty kit, transactional staging, no source mutation,
and no absolute/private paths in the manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitPresentationState, LiveKitState
from src.workbench_live_kit_export import (
    LIVE_KIT_EXPORT_DIR_NAME,
    LIVE_KIT_EXPORT_SCHEMA_VERSION,
    export_live_kit,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_bytes(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _row(path: Path, *, display_name: str | None = None) -> WorkbenchRow:
    name = display_name or path.name
    return WorkbenchRow(
        display_name=name,
        relative_path=f"synthetic/{name}",
        path=str(path),
        bpm=132.0,
        key="Am",
        key_conf=0.91,
        loudness=-13.5,
        brightness=3200.0,
        sample_class="one_shot",
        pred_type="Kick",
        status="ok",
        details={"duration_sec": "0.25", "source": "synthetic"},
    )


def _assign(state: LiveKitState, group: str, slot: str, path: Path, **kwargs) -> None:
    state.assign(group, slot, _row(path, **kwargs))


def _collect_relative_tree(root: Path) -> list[str]:
    entries: list[str] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        entries.append(rel + ("/" if path.is_dir() else ""))
    return entries


def test_empty_kit_rejected_without_creating_output(tmp_path: Path) -> None:
    destination = tmp_path / "dest"
    destination.mkdir()
    result = export_live_kit(LiveKitState(), destination)

    assert result.ok is False
    assert result.export_path is None
    assert result.error_code == "EMPTY_KIT"
    assert result.error_message
    assert "leer" in result.error_message.casefold() or "empty" in result.error_message.casefold()
    assert not (destination / LIVE_KIT_EXPORT_DIR_NAME).exists()
    assert list(destination.iterdir()) == []


def test_partial_kit_exports_only_assigned_audio_and_full_manifest(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    kick = _write_bytes(sources / "kick_a.wav", b"RIFF-KICK-A")
    hat = _write_bytes(sources / "hat_a.wav", b"RIFF-HAT-A")
    destination = tmp_path / "dest"
    destination.mkdir()

    state = LiveKitState()
    _assign(state, "Kick + Bass", "Kick", kick)
    _assign(state, "Drums", "Closed Hat", hat)

    result = export_live_kit(state, destination)

    assert result.ok is True
    assert result.export_path == destination / LIVE_KIT_EXPORT_DIR_NAME
    assert result.assigned_count == 2
    assert result.empty_count == sum(len(slots) for _, slots in LIVE_KIT_SLOT_MAPPING) - 2

    export_root = result.export_path
    assert export_root is not None
    audio_files = sorted(p for p in (export_root / "audio").rglob("*") if p.is_file())
    assert len(audio_files) == 2

    manifest = json.loads((export_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == LIVE_KIT_EXPORT_SCHEMA_VERSION
    flat_slots = [slot for group in manifest["groups"] for slot in group["slots"]]
    assert len(flat_slots) == sum(len(slots) for _, slots in LIVE_KIT_SLOT_MAPPING)
    assigned = [slot for slot in flat_slots if slot["assigned"]]
    empty = [slot for slot in flat_slots if not slot["assigned"]]
    assert len(assigned) == 2
    assert len(empty) == result.empty_count
    assert all(slot["audio_path"] for slot in assigned)
    assert all(slot["audio_path"] is None for slot in empty)
    assert "complete" not in json.dumps(manifest).casefold()


def test_complete_kit_exports_every_slot(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    destination = tmp_path / "dest"
    destination.mkdir()
    state = LiveKitState()
    payloads: dict[tuple[str, str], bytes] = {}
    for group_index, (group, slots) in enumerate(LIVE_KIT_SLOT_MAPPING, start=1):
        for slot_index, slot in enumerate(slots, start=1):
            payload = f"RIFF-{group_index}-{slot_index}".encode("ascii")
            path = _write_bytes(
                sources / f"g{group_index}_s{slot_index}.wav",
                payload,
            )
            payloads[(group, slot)] = payload
            _assign(state, group, slot, path)

    result = export_live_kit(state, destination)
    assert result.ok is True
    assert result.assigned_count == sum(len(slots) for _, slots in LIVE_KIT_SLOT_MAPPING)
    assert result.empty_count == 0

    export_root = result.export_path
    assert export_root is not None
    audio_files = sorted(p for p in (export_root / "audio").rglob("*") if p.is_file())
    assert len(audio_files) == result.assigned_count

    manifest = json.loads((export_root / "manifest.json").read_text(encoding="utf-8"))
    for group, slots in LIVE_KIT_SLOT_MAPPING:
        for slot in slots:
            entry = next(
                item
                for group_entry in manifest["groups"]
                if group_entry["name"] == group
                for item in group_entry["slots"]
                if item["slot"] == slot
            )
            assert entry["assigned"] is True
            rel = entry["audio_path"]
            assert isinstance(rel, str)
            exported = export_root / Path(rel)
            assert exported.is_file()
            assert exported.read_bytes() == payloads[(group, slot)]


def test_canonical_group_and_slot_ordering(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    destination = tmp_path / "dest"
    destination.mkdir()
    state = LiveKitState()
    _assign(state, "Atmos / FX", "FX", _write_bytes(sources / "fx.wav", b"RIFF-FX"))
    _assign(state, "Kick + Bass", "Bass", _write_bytes(sources / "bass.wav", b"RIFF-BASS"))
    _assign(state, "Drums", "Open Hat", _write_bytes(sources / "oh.wav", b"RIFF-OH"))

    result = export_live_kit(state, destination)
    assert result.ok is True
    export_root = result.export_path
    assert export_root is not None
    manifest = json.loads((export_root / "manifest.json").read_text(encoding="utf-8"))

    assert [group["name"] for group in manifest["groups"]] == [
        group for group, _ in LIVE_KIT_SLOT_MAPPING
    ]
    for group_entry, (group, slots) in zip(manifest["groups"], LIVE_KIT_SLOT_MAPPING, strict=True):
        assert group_entry["name"] == group
        assert [slot["slot"] for slot in group_entry["slots"]] == list(slots)

    group_dirs = sorted(
        path.name for path in (export_root / "audio").iterdir() if path.is_dir()
    )
    assert group_dirs == [
        "01_kick-bass",
        "02_drums",
        "03_melodic",
        "04_atmos-fx",
    ]


def test_duplicate_source_basenames_remain_conflict_free(tmp_path: Path) -> None:
    bank_a = tmp_path / "bank_a"
    bank_b = tmp_path / "bank_b"
    a = _write_bytes(bank_a / "kick.wav", b"RIFF-A")
    b = _write_bytes(bank_b / "kick.wav", b"RIFF-B")
    destination = tmp_path / "dest"
    destination.mkdir()

    state = LiveKitState()
    _assign(state, "Kick + Bass", "Kick", a)
    _assign(state, "Drums", "Main Drum", b)

    result = export_live_kit(state, destination)
    assert result.ok is True
    export_root = result.export_path
    assert export_root is not None
    files = sorted(p.name for p in (export_root / "audio").rglob("*.wav"))
    assert len(files) == 2
    assert len(set(files)) == 2
    assert {p.parent.name for p in (export_root / "audio").rglob("*.wav")} == {
        "01_kick-bass",
        "02_drums",
    }
    payloads = {p.read_bytes() for p in (export_root / "audio").rglob("*.wav")}
    assert payloads == {b"RIFF-A", b"RIFF-B"}


def test_same_source_reused_in_multiple_slots(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    shared = _write_bytes(sources / "shared.wav", b"RIFF-SHARED")
    destination = tmp_path / "dest"
    destination.mkdir()

    state = LiveKitState()
    _assign(state, "Kick + Bass", "Kick", shared)
    _assign(state, "Drums", "Main Drum", shared)

    before = _sha256(shared)
    result = export_live_kit(state, destination)
    assert result.ok is True
    assert _sha256(shared) == before

    export_root = result.export_path
    assert export_root is not None
    files = sorted((export_root / "audio").rglob("*.wav"))
    assert len(files) == 2
    assert all(path.read_bytes() == b"RIFF-SHARED" for path in files)
    assert files[0].name != files[1].name


def test_deterministic_filenames_and_manifest(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    kick = _write_bytes(sources / "Kick Sample!.wav", b"RIFF-KICK")
    hat = _write_bytes(sources / "hat.wav", b"RIFF-HAT")
    destination = tmp_path / "dest"
    destination.mkdir()

    state = LiveKitState()
    _assign(state, "Kick + Bass", "Kick", kick, display_name="Kick Sample!.wav")
    _assign(state, "Drums", "Closed Hat", hat)

    first = export_live_kit(state, destination)
    assert first.ok is True
    first_root = first.export_path
    assert first_root is not None
    first_tree = _collect_relative_tree(first_root)
    first_manifest = (first_root / "manifest.json").read_text(encoding="utf-8")
    first_hashes = {
        path.relative_to(first_root).as_posix(): _sha256(path)
        for path in first_root.rglob("*")
        if path.is_file()
    }

    # Remove and re-export into the same empty parent for filename stability.
    for child in destination.iterdir():
        if child.is_dir():
            for nested in sorted(child.rglob("*"), reverse=True):
                if nested.is_file():
                    nested.unlink()
                else:
                    nested.rmdir()
            child.rmdir()
        else:
            child.unlink()

    second = export_live_kit(state, destination)
    assert second.ok is True
    second_root = second.export_path
    assert second_root is not None
    assert _collect_relative_tree(second_root) == first_tree
    assert (second_root / "manifest.json").read_text(encoding="utf-8") == first_manifest
    assert {
        path.relative_to(second_root).as_posix(): _sha256(path)
        for path in second_root.rglob("*")
        if path.is_file()
    } == first_hashes

    assert (first_root / "audio" / "01_kick-bass" / "01_kick__kick-sample.wav").is_file()
    assert (first_root / "audio" / "02_drums" / "02_closed-hat__hat.wav").is_file()


def test_two_equivalent_exports_into_separate_destinations_match(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    kick = _write_bytes(sources / "kick.wav", b"RIFF-KICK")
    lead = _write_bytes(sources / "lead.wav", b"RIFF-LEAD")
    dest_a = tmp_path / "dest_a"
    dest_b = tmp_path / "dest_b"
    dest_a.mkdir()
    dest_b.mkdir()

    state = LiveKitState()
    _assign(state, "Kick + Bass", "Kick", kick)
    _assign(state, "Melodic", "Lead", lead)

    result_a = export_live_kit(state, dest_a)
    result_b = export_live_kit(state, dest_b)
    assert result_a.ok and result_b.ok
    assert result_a.export_path is not None and result_b.export_path is not None

    tree_a = _collect_relative_tree(result_a.export_path)
    tree_b = _collect_relative_tree(result_b.export_path)
    assert tree_a == tree_b
    assert (result_a.export_path / "manifest.json").read_text(
        encoding="utf-8"
    ) == (result_b.export_path / "manifest.json").read_text(encoding="utf-8")
    hashes_a = {
        path.relative_to(result_a.export_path).as_posix(): _sha256(path)
        for path in result_a.export_path.rglob("*")
        if path.is_file()
    }
    hashes_b = {
        path.relative_to(result_b.export_path).as_posix(): _sha256(path)
        for path in result_b.export_path.rglob("*")
        if path.is_file()
    }
    assert hashes_a == hashes_b


def test_missing_source_fails_before_finalization(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    missing = sources / "gone.wav"
    present = _write_bytes(sources / "hat.wav", b"RIFF-HAT")
    destination = tmp_path / "dest"
    destination.mkdir()

    state = LiveKitState()
    _assign(state, "Kick + Bass", "Kick", missing)
    _assign(state, "Drums", "Closed Hat", present)

    result = export_live_kit(state, destination)
    assert result.ok is False
    assert result.error_code == "SOURCE_MISSING"
    assert result.export_path is None
    assert not (destination / LIVE_KIT_EXPORT_DIR_NAME).exists()
    assert not any(destination.rglob("*"))


def test_unreadable_non_file_source_fails_cleanly(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    directory_source = sources / "not-a-file"
    directory_source.mkdir(parents=True)
    destination = tmp_path / "dest"
    destination.mkdir()

    state = LiveKitState()
    _assign(state, "Kick + Bass", "Kick", directory_source)

    result = export_live_kit(state, destination)
    assert result.ok is False
    assert result.error_code in {"SOURCE_NOT_FILE", "SOURCE_UNREADABLE"}
    assert result.export_path is None
    assert not (destination / LIVE_KIT_EXPORT_DIR_NAME).exists()


def test_unwritable_or_invalid_destination(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    kick = _write_bytes(sources / "kick.wav", b"RIFF-KICK")
    state = LiveKitState()
    _assign(state, "Kick + Bass", "Kick", kick)

    missing_parent = tmp_path / "missing" / "nested"
    missing_result = export_live_kit(state, missing_parent)
    assert missing_result.ok is False
    assert missing_result.error_code == "DESTINATION_INVALID"
    assert missing_result.export_path is None

    file_destination = tmp_path / "not-a-dir.txt"
    file_destination.write_text("x", encoding="utf-8")
    file_result = export_live_kit(state, file_destination)
    assert file_result.ok is False
    assert file_result.error_code == "DESTINATION_INVALID"

    if os.name == "nt":
        # Best-effort read-only destination on Windows; skip if chmod is ineffective.
        locked = tmp_path / "locked"
        locked.mkdir()
        try:
            os.chmod(locked, stat.S_IREAD | stat.S_IEXEC)
            probe = locked / "probe.txt"
            try:
                probe.write_text("probe", encoding="utf-8")
            except OSError:
                pass
            else:
                probe.unlink(missing_ok=True)
                pytest.skip("destination remained writable after chmod")
            locked_result = export_live_kit(state, locked)
            assert locked_result.ok is False
            assert locked_result.error_code in {
                "DESTINATION_INVALID",
                "DESTINATION_NOT_WRITABLE",
                "EXPORT_FAILED",
            }
            assert locked_result.export_path is None
        finally:
            os.chmod(locked, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)


def test_existing_final_output_directory_fail_closed(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    kick = _write_bytes(sources / "kick.wav", b"RIFF-KICK")
    destination = tmp_path / "dest"
    destination.mkdir()
    existing = destination / LIVE_KIT_EXPORT_DIR_NAME
    existing.mkdir()
    kept = existing / "keep-me.txt"
    kept.write_text("do-not-delete", encoding="utf-8")

    state = LiveKitState()
    _assign(state, "Kick + Bass", "Kick", kick)
    result = export_live_kit(state, destination)

    assert result.ok is False
    assert result.error_code == "OUTPUT_EXISTS"
    assert result.export_path is None
    assert kept.read_text(encoding="utf-8") == "do-not-delete"
    assert list(existing.iterdir()) == [kept]


def test_windows_path_edge_cases(tmp_path: Path) -> None:
    sources = tmp_path / "sources" / "weird name folder"
    awkward = _write_bytes(sources / "Kick Sample #1 (raw).wav", b"RIFF-AWKWARD")
    destination = tmp_path / "dest with spaces"
    destination.mkdir()

    state = LiveKitState()
    _assign(
        state,
        "Atmos / FX",
        "Atmos",
        awkward,
        display_name="Kick Sample #1 (raw).wav",
    )
    result = export_live_kit(state, destination)

    assert result.ok is True
    export_root = result.export_path
    assert export_root is not None
    audio_files = list((export_root / "audio").rglob("*.wav"))
    assert len(audio_files) == 1
    name = audio_files[0].name
    forbidden = '<>:"/\\|?*'
    assert not any(ch in name for ch in forbidden)
    assert name == "01_atmos__kick-sample-1-raw.wav"
    assert audio_files[0].read_bytes() == b"RIFF-AWKWARD"
    assert " " in str(result.export_path)


def test_source_bytes_unchanged_and_exported_bytes_identical(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    kick = _write_bytes(sources / "kick.wav", b"RIFF-IDENTICAL-BYTES")
    before_hash = _sha256(kick)
    before_mtime = kick.stat().st_mtime_ns
    destination = tmp_path / "dest"
    destination.mkdir()

    state = LiveKitState()
    _assign(state, "Kick + Bass", "Kick", kick)
    result = export_live_kit(state, destination)
    assert result.ok is True
    export_root = result.export_path
    assert export_root is not None

    exported = next((export_root / "audio").rglob("*.wav"))
    assert exported.read_bytes() == b"RIFF-IDENTICAL-BYTES"
    assert _sha256(exported) == before_hash
    assert _sha256(kick) == before_hash
    assert kick.stat().st_mtime_ns == before_mtime


def test_manifest_has_no_absolute_db_cache_or_runtime_paths(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    kick = _write_bytes(sources / "kick.wav", b"RIFF-KICK")
    destination = tmp_path / "dest"
    destination.mkdir()

    state = LiveKitState()
    absolute_row = _row(kick)
    absolute_row.path = str(kick.resolve())
    absolute_row.relative_path = str(kick.resolve())
    absolute_row.details = {
        "duration_sec": "0.25",
        "db_path": str(tmp_path / "catalog.db"),
        "cache_path": str(tmp_path / "cache"),
        "index_path": str(tmp_path / "indexes" / "x.npz"),
        "runtime_evidence": str(tmp_path / "evidence.json"),
    }
    state.assign("Kick + Bass", "Kick", absolute_row)

    result = export_live_kit(state, destination)
    assert result.ok is True
    export_root = result.export_path
    assert export_root is not None
    manifest_text = (export_root / "manifest.json").read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)

    assert str(kick.resolve()) not in manifest_text
    assert "catalog.db" not in manifest_text
    assert "indexes" not in manifest_text
    assert "evidence.json" not in manifest_text
    assert ":\\" not in manifest_text
    assert "C:/" not in manifest_text

    slot = manifest["groups"][0]["slots"][0]
    assert slot["audio_path"].startswith("audio/")
    assert not Path(slot["audio_path"]).is_absolute()


def test_no_partial_final_output_after_copy_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sources = tmp_path / "sources"
    kick = _write_bytes(sources / "kick.wav", b"RIFF-KICK")
    hat = _write_bytes(sources / "hat.wav", b"RIFF-HAT")
    destination = tmp_path / "dest"
    destination.mkdir()

    state = LiveKitState()
    _assign(state, "Kick + Bass", "Kick", kick)
    _assign(state, "Drums", "Closed Hat", hat)

    import src.workbench_live_kit_export as export_mod

    real_copy = export_mod.shutil.copy2
    calls = {"n": 0}

    def flaky_copy(src, dst, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise OSError("simulated copy failure")
        return real_copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(export_mod.shutil, "copy2", flaky_copy)
    result = export_live_kit(state, destination)

    assert result.ok is False
    assert result.export_path is None
    assert not (destination / LIVE_KIT_EXPORT_DIR_NAME).exists()
    leftover = [path for path in destination.rglob("*") if path != destination]
    assert leftover == []


def test_export_does_not_mutate_live_kit_or_presentation_state(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    kick = _write_bytes(sources / "kick.wav", b"RIFF-KICK")
    destination = tmp_path / "dest"
    destination.mkdir()

    state = LiveKitState()
    presentation = LiveKitPresentationState(state)
    assert presentation.is_collapsed("Kick + Bass") is True
    assert presentation.active_group() is None
    _assign(state, "Kick + Bass", "Kick", kick)
    assigned_before = state.assignment_for("Kick + Bass", "Kick")
    collapsed_before = {
        group: presentation.is_collapsed(group) for group in state.groups()
    }
    active_before = presentation.active_group()

    result = export_live_kit(state, destination)
    assert result.ok is True
    assert state.assignment_for("Kick + Bass", "Kick") is assigned_before
    assert {
        group: presentation.is_collapsed(group) for group in state.groups()
    } == collapsed_before
    assert presentation.active_group() == active_before
    assert state.assignment_for("Drums", "Main Drum") is None
