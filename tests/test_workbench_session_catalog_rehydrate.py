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
- missing/incompatible library must NOT create DB, parent dirs, or schema DDL
- read-only resume must not create WAL/SHM sidecars on a clean WAL library
- committed WAL frames must still be visible (no immutable=1 false Catalog Miss)
- rehydrate completes before first Live Kit / QML projection
- SYNC tempo path can use restored source BPM
- #817 DEFAULT_ON heal semantics remain unchanged (covered elsewhere)
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from src.session_grid import compute_sync_playback_rate
from src.workbench_controller import WorkbenchRow
from src.workbench_library import init_workbench_library, upsert_folder, upsert_sample
from src.workbench_session import compose_workbench_session
from src.workbench_session_store import workbench_session_path


def _library_dir_fingerprint(db_path: Path) -> dict[str, object]:
    parent = db_path.parent
    names = sorted(p.name for p in parent.iterdir())
    hashes: dict[str, str] = {}
    for name in names:
        path = parent / name
        if path.is_file():
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"names": names, "hashes": hashes}


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
    before = bad_db.read_bytes()
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
    assert bad_db.read_bytes() == before
    b.transport.close()


def test_rehydrate_missing_library_db_does_not_create_file_or_parent(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    missing_parent = tmp_path / "absent-library-dir"
    missing_db = missing_parent / "library.db"
    kick = str((tmp_path / "kick.wav").resolve())
    Path(kick).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=state_dir)
    a.live_kit.assign("Kick + Bass", "Kick", _minimal_row("kick.wav", kick))
    a.transport.close()

    assert not missing_parent.exists()
    assert not missing_db.exists()

    b = compose_workbench_session(state_dir=state_dir, library_db_path=missing_db)
    restored = _kick_slot(b)
    assert restored is not None
    assert restored.path == kick
    assert restored.bpm is None
    assert restored.key is None
    assert not missing_db.exists()
    assert not missing_parent.exists()
    b.transport.close()


def test_rehydrate_wal_library_does_not_create_sidecars(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    seed_db = tmp_path / "seed" / "library.db"
    seed_db.parent.mkdir()
    folder = tmp_path / "samples"
    audio = folder / "kick.wav"
    kick = _seed_library_row(
        library_db=seed_db,
        folder=folder,
        audio=audio,
        bpm=128.0,
        key="Am",
    )
    with sqlite3.connect(seed_db) as conn:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    # Fresh main-file copy: WAL journal_mode in header, no sidecars present.
    library_db = tmp_path / "clean" / "library.db"
    library_db.parent.mkdir()
    shutil.copy2(seed_db, library_db)
    wal_path = Path(f"{library_db}-wal")
    shm_path = Path(f"{library_db}-shm")
    assert not wal_path.exists()
    assert not shm_path.exists()
    before = _library_dir_fingerprint(library_db)

    a = compose_workbench_session(state_dir=state_dir)
    a.live_kit.assign("Kick + Bass", "Kick", _minimal_row("kick.wav", kick))
    a.transport.close()

    b = compose_workbench_session(state_dir=state_dir, library_db_path=library_db)
    restored = _kick_slot(b)
    assert restored is not None
    assert restored.bpm == 128.0
    assert restored.key == "Am"
    assert _library_dir_fingerprint(library_db) == before
    assert not wal_path.exists()
    assert not shm_path.exists()
    b.transport.close()


def test_rehydrate_includes_committed_wal_only_catalog_row(tmp_path: Path) -> None:
    """Resume must rehydrate BPM/Key from committed WAL frames, not miss them."""
    state_dir = tmp_path / "state"
    library_db = tmp_path / "library" / "library.db"
    library_db.parent.mkdir()
    folder = tmp_path / "samples"
    audio = folder / "kick.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"RIFF" + b"\x00" * 40)
    kick = str(audio.resolve())

    # Persist path-only session before the WAL-only library exists.
    a = compose_workbench_session(state_dir=state_dir)
    a.live_kit.assign("Kick + Bass", "Kick", _minimal_row("kick.wav", kick))
    a.transport.close()

    init_workbench_library(library_db)
    with sqlite3.connect(library_db) as conn:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()

    # Keep a live connection so the committed row is not final-checkpointed into
    # the main DB file (crash / concurrent-open resume scenario).
    holder = sqlite3.connect(library_db)
    holder.execute("PRAGMA wal_autocheckpoint=0")
    try:
        folder_id = upsert_folder(folder, db_path=library_db)
        upsert_sample(
            folder_id,
            _minimal_row(audio.name, kick, bpm=128.0, key="Am"),
            size_bytes=44,
            mtime_ns=1_700_000_000_000_000_000,
            db_path=library_db,
        )
        wal_path = Path(f"{library_db}-wal")
        shm_path = Path(f"{library_db}-shm")
        assert wal_path.is_file() and wal_path.stat().st_size > 0

        # Prove the row is not fully checkpointed into the main DB alone.
        with sqlite3.connect(
            f"file:{library_db.resolve().as_posix()}?mode=ro&immutable=1",
            uri=True,
        ) as conn:
            assert (
                conn.execute(
                    "SELECT 1 FROM samples WHERE original_path = ?",
                    (kick,),
                ).fetchone()
                is None
            )

        before = _library_dir_fingerprint(library_db)
        assert "library.db-wal" in before["names"]
        # Holder must stay alive across resume so WAL frames remain uncheckpointed.
        assert holder.execute("SELECT 1").fetchone() == (1,)
        b = compose_workbench_session(state_dir=state_dir, library_db_path=library_db)
        restored = _kick_slot(b)
        assert holder.execute("SELECT 1").fetchone() == (1,)
        after = _library_dir_fingerprint(library_db)

        assert restored is not None
        assert restored.path == kick
        assert restored.bpm == pytest.approx(128.0)
        assert restored.key == "Am"
        # Durable source state must stay byte-identical. Entry set must not gain
        # or lose files. SHM content may change under a live holder (volatile
        # index); resume must neither create nor delete the SHM file.
        assert after["names"] == before["names"]
        assert after["hashes"]["library.db"] == before["hashes"]["library.db"]
        assert after["hashes"]["library.db-wal"] == before["hashes"]["library.db-wal"]
        assert wal_path.is_file() and wal_path.stat().st_size > 0
        assert shm_path.is_file()
        b.transport.close()
    finally:
        holder.close()


def test_rehydrate_incompatible_library_schema_fail_soft_without_migration(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "state"
    incompatible_db = tmp_path / "incompatible.db"
    with sqlite3.connect(incompatible_db) as conn:
        conn.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
        conn.commit()
    before = incompatible_db.read_bytes()
    kick = str((tmp_path / "kick.wav").resolve())
    Path(kick).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=state_dir)
    a.live_kit.assign("Kick + Bass", "Kick", _minimal_row("kick.wav", kick))
    a.transport.close()

    b = compose_workbench_session(state_dir=state_dir, library_db_path=incompatible_db)
    restored = _kick_slot(b)
    assert restored is not None
    assert restored.bpm is None
    assert restored.key is None
    assert incompatible_db.read_bytes() == before
    with sqlite3.connect(f"file:{incompatible_db.resolve().as_posix()}?mode=ro", uri=True) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "samples" not in names
    assert "folders" not in names
    assert "unrelated" in names
    b.transport.close()
