"""TEST_GATE / TEST_FREEZE — Catalog rehydrate on Workbench resume (#820).

Canonical authority:
- docs/SESSION_OWNERSHIP_CONTRACT.md
- docs/DATA_AND_ARTIFACT_POLICY.md
- Issue #820

Frozen product rules:
- path refs remain persisted session authority (no mandatory analysis blobs)
- with library_db_path: best-effort read-only rehydrate of Live Kit rows
- catalog hit → BPM/Key (and related analysis fields) on restored WorkbenchRow
- catalog miss / missing library → keep minimal path row; no crash
- rehydrate completes before first Live Kit / QML projection
- SYNC tempo path can use restored source BPM
- #817 DEFAULT_ON heal semantics remain unchanged (covered elsewhere)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.session_grid import compute_sync_playback_rate
from src.workbench_controller import WorkbenchRow
from src.workbench_library import upsert_folder, upsert_sample
from src.workbench_session import compose_workbench_session
from src.workbench_session_store import workbench_session_path


def _minimal_row(name: str, path: str, *, bpm: float | None = None, key: str | None = None) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=Path(path).name,
        path=path,
        bpm=bpm,
        key=key,
        key_conf=0.9 if key else None,
        loudness=-10.0 if bpm is not None else None,
        brightness=1800.0 if bpm is not None else None,
        sample_class="loop" if bpm is not None else None,
        pred_type="Kick" if bpm is not None else None,
        status="ok",
        details={},
    )


def _seed_library_row(
    *,
    library_db: Path,
    folder: Path,
    audio: Path,
    bpm: float,
    key: str,
) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"RIFF" + b"\x00" * 40)
    resolved = str(audio.resolve())
    folder_id = upsert_folder(folder, db_path=library_db)
    upsert_sample(
        folder_id,
        _minimal_row(audio.name, resolved, bpm=bpm, key=key),
        size_bytes=44,
        mtime_ns=1_700_000_000_000_000_000,
        db_path=library_db,
    )
    return resolved


def _kick_slot(session):
    return session.live_kit.assignment_for("Kick + Bass", "Kick")


def _projected_kick_row(session) -> WorkbenchRow | None:
    for group in session.live_kit_presenter.groups:
        if group.name != "Kick + Bass":
            continue
        for slot in group.slots:
            if slot.name == "Kick":
                return slot.assignment
    return None


def _vm_kick_row(session) -> WorkbenchRow | None:
    for group in session.qml_interaction_adapter.view_model.live_kit_groups:
        if group.name != "Kick + Bass":
            continue
        for slot in group.slots:
            if slot.name == "Kick":
                return slot.assignment
    return None


def test_restore_catalog_hit_rehydrates_bpm_and_key(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    library_db = tmp_path / "library.db"
    folder = tmp_path / "samples"
    kick = folder / "kick.wav"
    path = _seed_library_row(
        library_db=library_db,
        folder=folder,
        audio=kick,
        bpm=128.0,
        key="Am",
    )

    a = compose_workbench_session(state_dir=state_dir)
    a.live_kit.assign("Kick + Bass", "Kick", _minimal_row("kick.wav", path, bpm=128.0, key="Am"))
    a.transport.close()

    # Persisted authority stays path-only even when in-memory row had analysis.
    payload = json.loads(workbench_session_path(state_dir=state_dir).read_text(encoding="utf-8"))
    assert payload["live_kit"]["Kick + Bass"]["Kick"] == {"path": path}
    assert "bpm" not in json.dumps(payload["live_kit"])

    b = compose_workbench_session(state_dir=state_dir, library_db_path=library_db)
    restored = _kick_slot(b)
    assert restored is not None
    assert restored.path == path
    assert restored.bpm == pytest.approx(128.0)
    assert restored.key == "Am"
    b.transport.close()


def test_restore_catalog_miss_keeps_minimal_row(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    library_db = tmp_path / "library.db"
    folder = tmp_path / "samples"
    folder.mkdir()
    # Seed a different path so the kit path is a clean miss.
    other = folder / "other.wav"
    _seed_library_row(
        library_db=library_db,
        folder=folder,
        audio=other,
        bpm=140.0,
        key="C",
    )
    missing = str((folder / "missing_kick.wav").resolve())
    Path(missing).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=state_dir)
    a.live_kit.assign("Kick + Bass", "Kick", _minimal_row("missing_kick.wav", missing))
    a.transport.close()

    b = compose_workbench_session(state_dir=state_dir, library_db_path=library_db)
    restored = _kick_slot(b)
    assert restored is not None
    assert restored.path == missing
    assert restored.bpm is None
    assert restored.key is None
    assert restored.display_name == "missing_kick.wav"
    b.transport.close()


def test_restore_without_library_db_keeps_minimal_row(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    kick = str((tmp_path / "kick.wav").resolve())
    Path(kick).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=state_dir)
    a.live_kit.assign(
        "Kick + Bass",
        "Kick",
        _minimal_row("kick.wav", kick, bpm=120.0, key="F"),
    )
    a.transport.close()

    b = compose_workbench_session(state_dir=state_dir)
    restored = _kick_slot(b)
    assert restored is not None
    assert restored.path == kick
    assert restored.bpm is None
    assert restored.key is None
    b.transport.close()


def test_rehydrate_completes_before_first_projection(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    library_db = tmp_path / "library.db"
    folder = tmp_path / "samples"
    path = _seed_library_row(
        library_db=library_db,
        folder=folder,
        audio=folder / "kick.wav",
        bpm=132.0,
        key="Dm",
    )

    a = compose_workbench_session(state_dir=state_dir)
    a.live_kit.assign("Kick + Bass", "Kick", _minimal_row("kick.wav", path))
    a.transport.close()

    b = compose_workbench_session(state_dir=state_dir, library_db_path=library_db)
    projected = _projected_kick_row(b)
    vm_row = _vm_kick_row(b)
    assert projected is not None
    assert projected.bpm == pytest.approx(132.0)
    assert projected.key == "Dm"
    assert vm_row is not None
    assert vm_row.bpm == pytest.approx(132.0)
    assert vm_row.key == "Dm"
    b.transport.close()


def test_restored_bpm_is_sync_usable(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    library_db = tmp_path / "library.db"
    folder = tmp_path / "samples"
    path = _seed_library_row(
        library_db=library_db,
        folder=folder,
        audio=folder / "loop.wav",
        bpm=128.0,
        key="G",
    )

    a = compose_workbench_session(state_dir=state_dir)
    a.live_kit.assign("Melodic", "Pad", _minimal_row("loop.wav", path))
    a.transport.set_tempo(132.0)
    a.transport.set_sync_enabled(True)
    a.transport.close()

    b = compose_workbench_session(state_dir=state_dir, library_db_path=library_db)
    restored = b.live_kit.assignment_for("Melodic", "Pad")
    assert restored is not None
    assert restored.bpm == pytest.approx(128.0)
    assert b.transport.is_sync_enabled() is True
    rate, status = compute_sync_playback_rate(
        b.transport.get_current_tempo(),
        restored.bpm,
        sync_enabled=True,
    )
    assert status == "sync"
    assert rate == pytest.approx(132.0 / 128.0)
    b.transport.close()


def test_rehydrate_is_read_only_and_fail_soft_on_bad_library(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    bad_db = tmp_path / "not-a-db.txt"
    bad_db.write_text("not sqlite", encoding="utf-8")
    kick = str((tmp_path / "kick.wav").resolve())
    Path(kick).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=state_dir)
    a.live_kit.assign("Kick + Bass", "Kick", _minimal_row("kick.wav", kick))
    a.transport.close()

    b = compose_workbench_session(state_dir=state_dir, library_db_path=bad_db)
    restored = _kick_slot(b)
    assert restored is not None
    assert restored.bpm is None
    assert restored.key is None
    b.transport.close()
