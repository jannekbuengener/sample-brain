"""Regression tests for #1208: Workbench library state cleanup guard.

Covers the fail-closed connection boundary, the deterministic test-artifact
classifier rule, the SQLAlchemy-free read-only catalog inspection, and the
read-only dry-run removal preview.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

import src.workbench_library as workbench_library
from src.workbench_library import (
    CleanupClassification,
    WorkbenchLibraryConnectionError,
    classify_folder_for_cleanup,
    connect_workbench_library,
    init_workbench_library,
    preview_library_folder_removal,
    register_library_folder,
    workbench_library_db_path,
)


def _db_bytes(db_path: Path) -> bytes:
    return db_path.read_bytes()


# ---------------------------------------------------------------------------
# A. normal pytest default resolves isolated state
# ---------------------------------------------------------------------------
def test_a_normal_pytest_default_resolves_isolated_state(
    isolated_workbench_state_dir: Path, tmp_path: Path
) -> None:
    db_path = workbench_library_db_path()
    assert db_path == isolated_workbench_state_dir / "workbench_library.db"

    # Default connection resolves to the isolated pytest state, not the
    # producer.  Only the isolated synthetic DB is opened and used; the real
    # producer DB is never stat'd, read, hashed, or otherwise touched here.
    conn = connect_workbench_library()
    try:
        assert conn.execute("SELECT 1").fetchone()[0] == 1
    finally:
        conn.close()

    # The fail-closed guard refuses a protected synthetic producer target
    # before any sqlite connection, proving isolation without touching the
    # real producer DB.
    synthetic_producer_db = tmp_path / "producer-state" / "workbench_library.db"
    synthetic_producer_db.parent.mkdir(parents=True)
    workbench_library.protect_connection_target(synthetic_producer_db)
    with pytest.raises(WorkbenchLibraryConnectionError):
        workbench_library.connect_workbench_library(synthetic_producer_db)


# ---------------------------------------------------------------------------
# B. clearing SAMPLE_BRAIN_WORKBENCH_STATE_DIR after fixture setup and
#    attempting default DB connection fails before sqlite connection
# ---------------------------------------------------------------------------
def test_b_clearing_env_blocks_producer_default_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", raising=False)
    with pytest.raises(WorkbenchLibraryConnectionError):
        connect_workbench_library()


# ---------------------------------------------------------------------------
# C. explicit safe db_path works
# ---------------------------------------------------------------------------
def test_c_explicit_safe_db_path_works(tmp_path: Path) -> None:
    safe_db = tmp_path / "safe" / "workbench_library.db"
    conn = connect_workbench_library(safe_db)
    try:
        assert conn.execute("SELECT 1").fetchone()[0] == 1
    finally:
        conn.close()
    assert safe_db.is_file()


# ---------------------------------------------------------------------------
# D. explicit state_dir works
# ---------------------------------------------------------------------------
def test_d_explicit_state_dir_works(tmp_path: Path) -> None:
    state_dir = tmp_path / "explicit-state"
    assert workbench_library_db_path(state_dir=state_dir) == (
        state_dir / "workbench_library.db"
    )


# ---------------------------------------------------------------------------
# E. env={} + synthetic HOME works
# ---------------------------------------------------------------------------
def test_e_env_empty_synthetic_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    synthetic_home = tmp_path / "synthetic-home"
    monkeypatch.setattr(Path, "home", lambda: synthetic_home)
    assert workbench_library_db_path(env={}) == (
        synthetic_home / ".sample-brain" / "workbench_library.db"
    )


# ---------------------------------------------------------------------------
# F. guard error contains no private producer path
# ---------------------------------------------------------------------------
def test_f_guard_error_contains_no_producer_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", raising=False)
    producer_state_dir = Path.home() / ".sample-brain"
    producer_db = producer_state_dir / "workbench_library.db"
    with pytest.raises(WorkbenchLibraryConnectionError) as excinfo:
        connect_workbench_library()
    msg = str(excinfo.value)
    assert str(producer_state_dir) not in msg
    assert str(producer_db) not in msg


# ---------------------------------------------------------------------------
# G. canonical temp + pytest structure => DETERMINISTIC_TEST_ARTIFACT
# H. canonical temp without pytest structure => not deterministic
# ---------------------------------------------------------------------------
def _fake_temp_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pin the canonical temp roots to a synthetic directory.

    Both the runtime temp root and the platform default temp root are pinned
    so the classification result never depends on where pytest happens to put
    ``tmp_path`` on the current machine.  The runtime root is pinned through
    ``_runtime_temp_root`` because the classifier resolves it without calling
    ``tempfile.gettempdir()`` (which would probe the filesystem).
    """
    fake_temp = tmp_path / "temp"
    fake_temp.mkdir()
    monkeypatch.setattr(
        workbench_library, "_runtime_temp_root", lambda: fake_temp
    )
    monkeypatch.setattr(
        workbench_library, "_platform_default_temp_root", lambda: fake_temp
    )
    return fake_temp


def test_g_actual_pytest_managed_layout_under_canonical_temp_is_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_temp = _fake_temp_root(tmp_path, monkeypatch)
    target = fake_temp / "pytest-of-user" / "pytest-123" / "test_node"
    target.mkdir(parents=True)
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        == CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_g_current_pytest_run_is_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_temp = _fake_temp_root(tmp_path, monkeypatch)
    target = fake_temp / "pytest-of-user" / "pytest-current" / "test_node"
    target.mkdir(parents=True)
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        == CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_h_canonical_temp_without_pytest_structure_is_not_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_temp = _fake_temp_root(tmp_path, monkeypatch)
    target = fake_temp / "my_samples"
    target.mkdir()
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


# ---------------------------------------------------------------------------
# I. pytest-project under canonical temp => not deterministic
# J. pytest-backups under canonical temp => not deterministic
# K. my_pytest_tmp_samples under canonical temp => not deterministic
# ---------------------------------------------------------------------------
def test_i_pytest_project_under_canonical_temp_is_not_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_temp = _fake_temp_root(tmp_path, monkeypatch)
    target = fake_temp / "pytest-project" / "Samples"
    target.mkdir(parents=True)
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_j_pytest_backups_under_canonical_temp_is_not_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_temp = _fake_temp_root(tmp_path, monkeypatch)
    target = fake_temp / "pytest-backups" / "Samples"
    target.mkdir(parents=True)
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_k_my_pytest_tmp_samples_under_canonical_temp_is_not_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_temp = _fake_temp_root(tmp_path, monkeypatch)
    target = fake_temp / "my_pytest_tmp_samples"
    target.mkdir()
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


# ---------------------------------------------------------------------------
# L. exact known signature still deterministic when supplied
# ---------------------------------------------------------------------------
def test_l_exact_historical_test_signature_is_deterministic(tmp_path: Path) -> None:
    # ``engine_already_running`` is the documented, narrowly-scoped historical
    # test-generated directory family referenced by the classifier contract.
    target = tmp_path / "engine_already_running"
    target.mkdir()
    assert (
        workbench_library.classify_folder_for_cleanup(
            target, known_test_roots=frozenset({"engine_already_running"})
        )
        == CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


# ---------------------------------------------------------------------------
# M. generic nonexistent path => AMBIGUOUS
# ---------------------------------------------------------------------------
def test_m_generic_nonexistent_path_is_ambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_temp_root(tmp_path, monkeypatch)
    target = tmp_path / "does-not-exist"
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        == CleanupClassification.AMBIGUOUS
    )


# ---------------------------------------------------------------------------
# N. read-only dry-run does not create missing DB
# O. read-only dry-run does not change existing DB contents/schema
# P. filesystem sentinel survives dry-run
# ---------------------------------------------------------------------------
def test_n_readonly_dry_run_does_not_create_missing_db(tmp_path: Path) -> None:
    missing_db = tmp_path / "missing" / "workbench_library.db"
    missing_folder = tmp_path / "some-folder"
    assert not missing_db.exists()

    preview = preview_library_folder_removal(missing_folder, db_path=missing_db)

    assert preview is None
    assert not missing_db.exists()
    assert not missing_db.parent.exists()


def test_o_readonly_dry_run_does_not_change_existing_db(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "workbench_library.db"
    folder = tmp_path / "samples"
    folder.mkdir()
    init_workbench_library(db_path)
    folder_id = register_library_folder(folder, db_path=db_path)

    before = _db_bytes(db_path)

    preview = preview_library_folder_removal(folder_id, db_path=db_path)

    assert preview is not None
    assert preview.folder_id == folder_id
    assert preview.metadata_only is True
    assert _db_bytes(db_path) == before


def test_p_filesystem_sentinel_survives_dry_run(tmp_path: Path) -> None:
    db_path = tmp_path / "state" / "workbench_library.db"
    folder = tmp_path / "samples"
    folder.mkdir()
    sentinel = folder / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")

    init_workbench_library(db_path)
    register_library_folder(folder, db_path=db_path)

    preview = preview_library_folder_removal(folder, db_path=db_path)

    assert preview is not None
    assert preview.folder_id is not None
    assert sentinel.is_file()
    assert sentinel.read_text(encoding="utf-8") == "keep"


# ---------------------------------------------------------------------------
# Q. writable connect rejected for protected target (P1)
# R. readonly connection rejected for protected target (P1)
# S. classifier/catalog lookup rejected for protected target (P1)
# T. snapshot/capture path rejects protected target before source reads (P1)
# ---------------------------------------------------------------------------
def test_q_writable_connect_rejected_for_protected_target(tmp_path: Path) -> None:
    protected_db = tmp_path / "protected-state" / "workbench_library.db"
    protected_db.parent.mkdir(parents=True)
    workbench_library.protect_connection_target(protected_db)
    with pytest.raises(WorkbenchLibraryConnectionError):
        workbench_library.connect_workbench_library(protected_db)


def test_r_readonly_connection_rejected_for_protected_target(tmp_path: Path) -> None:
    protected_db = tmp_path / "protected-state" / "workbench_library.db"
    protected_db.parent.mkdir(parents=True)
    protected_db.write_bytes(b"SQLite format 3\x00")
    workbench_library.protect_connection_target(protected_db)
    with pytest.raises(WorkbenchLibraryConnectionError):
        with workbench_library.workbench_library_readonly_connection(
            db_path=protected_db
        ) as conn:
            pass  # never reached: rejected before opening


def test_s_classifier_catalog_lookup_rejected_for_protected_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_temp_root(tmp_path, monkeypatch)
    protected_db = tmp_path / "protected-state" / "workbench_library.db"
    protected_db.parent.mkdir(parents=True)
    folder = tmp_path / "samples"
    folder.mkdir()
    workbench_library.protect_connection_target(protected_db)
    with pytest.raises(WorkbenchLibraryConnectionError):
        classify_folder_for_cleanup(folder, db_path=protected_db)


def test_t_snapshot_capture_rejects_protected_target_before_source_reads(
    tmp_path: Path,
) -> None:
    source_db = tmp_path / "source.db"
    source_db.write_bytes(b"SQLite format 3\x00")
    snap_db = tmp_path / "snap" / "readonly_snapshot.db"

    workbench_library.protect_connection_target(source_db)

    # Capture is refused before any source DB/WAL/journal read or copy.
    with pytest.raises(WorkbenchLibraryConnectionError):
        workbench_library._capture_sqlite_main_and_wal(source_db.resolve(), snap_db)

    # Source DB and sidecars untouched: no -wal / -journal appeared next to source.
    source_dir = source_db.parent
    assert not (source_dir / f"{source_db.name}-wal").exists()
    assert not (source_dir / f"{source_db.name}-journal").exists()
    assert source_db.read_bytes() == b"SQLite format 3\x00"


# ---------------------------------------------------------------------------
# U. readonly URI preserves path with space (P2)
# V. readonly URI preserves path with # (P2)
# W. readonly URI preserves path with % (P2)
# X. readonly URI preserves path with ? where platform-valid (P2)
# ---------------------------------------------------------------------------
def _seed_catalog_db(db_path: Path, folder: Path) -> None:
    db_path.parent.mkdir(parents=True)
    init_workbench_library(db_path)
    register_library_folder(folder, db_path=db_path)


def test_u_readonly_uri_preserves_path_with_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_temp_root(tmp_path, monkeypatch)
    db_path = tmp_path / "my db with spaces" / "workbench_library.db"
    folder = tmp_path / "samples"
    folder.mkdir()
    _seed_catalog_db(db_path, folder)
    # Catalog lookup must open the intended DB, not reinterpret the path.
    assert (
        classify_folder_for_cleanup(folder, db_path=db_path)
        == CleanupClassification.LEGITIMATE_OR_UNPROVEN
    )


def test_v_readonly_uri_preserves_path_with_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_temp_root(tmp_path, monkeypatch)
    db_path = tmp_path / "my#db" / "workbench_library.db"
    folder = tmp_path / "samples"
    folder.mkdir()
    _seed_catalog_db(db_path, folder)
    assert (
        classify_folder_for_cleanup(folder, db_path=db_path)
        == CleanupClassification.LEGITIMATE_OR_UNPROVEN
    )


def test_w_readonly_uri_preserves_path_with_percent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_temp_root(tmp_path, monkeypatch)
    db_path = tmp_path / "my%db" / "workbench_library.db"
    folder = tmp_path / "samples"
    folder.mkdir()
    _seed_catalog_db(db_path, folder)
    assert (
        classify_folder_for_cleanup(folder, db_path=db_path)
        == CleanupClassification.LEGITIMATE_OR_UNPROVEN
    )


def test_x_readonly_uri_preserves_path_with_question_mark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ``?`` is not a valid Windows filename character; skip there.
    if os.name == "nt":
        pytest.skip("? is not a valid filename character on Windows")
    _fake_temp_root(tmp_path, monkeypatch)
    db_path = tmp_path / "my?db" / "workbench_library.db"
    folder = tmp_path / "samples"
    folder.mkdir()
    _seed_catalog_db(db_path, folder)
    assert (
        classify_folder_for_cleanup(folder, db_path=db_path)
        == CleanupClassification.LEGITIMATE_OR_UNPROVEN
    )


# ---------------------------------------------------------------------------
# Y. pytest tmp_path node directory needs pytest-of-<user> ancestry directly
#    under canonical temp root; a bare custom basetemp is NOT deterministic.
# Z. the same directory shape outside a canonical temp root is NOT
#    deterministic (a user library may carry any name).
# ---------------------------------------------------------------------------
def test_y_custom_basetemp_without_pytest_of_is_not_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_temp = _fake_temp_root(tmp_path, monkeypatch)
    target = fake_temp / "custom-basetemp" / "test_record_with_stopped_trans0"
    target.mkdir(parents=True)
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_y2_platform_default_without_pytest_of_is_not_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Even under the platform default temp root, a directory not under
    # pytest-of-<user>/pytest-<run> is not a pytest node directory.
    fake_temp = _fake_temp_root(tmp_path, monkeypatch)
    platform_temp = tmp_path / "platform-temp"
    platform_temp.mkdir()
    monkeypatch.setattr(
        workbench_library, "_platform_default_temp_root", lambda: platform_temp
    )
    target = platform_temp / "sb-run-01" / "test_hw_record_stop_cycle0"
    target.mkdir(parents=True)
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_z_pytest_node_directory_outside_temp_root_is_not_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_temp = _fake_temp_root(tmp_path, monkeypatch)
    outside = tmp_path / "user-library" / "test_record_with_stopped_trans0"
    outside.mkdir(parents=True)
    assert (
        workbench_library.classify_folder_for_cleanup(outside)
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_z2_plain_library_name_under_temp_root_is_not_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Canonical temp ancestry alone is not evidence of a test artifact.
    fake_temp = _fake_temp_root(tmp_path, monkeypatch)
    target = fake_temp / "my_samples"
    target.mkdir()
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_z3_user_named_test_folder_without_uniquifier_is_not_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # pytest appends a numeric uniquifier to node directories; a user
    # library named ``test_samples`` must not be classified as a test artifact.
    fake_temp = _fake_temp_root(tmp_path, monkeypatch)
    target = fake_temp / "test_samples"
    target.mkdir()
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_z3b_node_directory_directly_under_temp_root_is_not_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # pytest never creates a node directory directly under the OS temp root,
    # so a matching leaf name there is not verifiable pytest evidence.
    fake_temp = _fake_temp_root(tmp_path, monkeypatch)
    target = fake_temp / "test_samples0"
    target.mkdir()
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_z4_nested_pytest_of_component_is_not_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The pytest-of-<user> base must sit directly under the temp root.
    fake_temp = _fake_temp_root(tmp_path, monkeypatch)
    target = fake_temp / "customer" / "pytest-of-alice" / "pytest-1" / "samples"
    target.mkdir(parents=True)
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


# ---------------------------------------------------------------------------
# AA. catalog inspection must not create WAL/SHM sidecars next to the source
#     library (read-only contract).
# AB. committed WAL frames must still be visible to the classifier.
# ---------------------------------------------------------------------------
def test_aa_catalog_lookup_does_not_create_sidecars_next_to_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_temp_root(tmp_path, monkeypatch)
    source_dir = tmp_path / "wal-source"
    source_dir.mkdir()
    db_path = source_dir / "workbench_library.db"
    folder = tmp_path / "samples"
    folder.mkdir()
    init_workbench_library(db_path)
    register_library_folder(folder, db_path=db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        wal_only = tmp_path / "wal-only"
        wal_only.mkdir()
        conn.execute(
            "INSERT INTO folders (path, last_scan_at, last_opened_at) VALUES (?, ?, ?)",
            (str(wal_only), "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()

        # Copy the live main DB plus its WAL so the copy carries a committed
        # frame that is not present in the main database file.
        copy_dir = tmp_path / "wal-copy"
        copy_dir.mkdir()
        copy_db = copy_dir / "workbench_library.db"
        shutil.copyfile(db_path, copy_db)
        shutil.copyfile(f"{db_path}-wal", f"{copy_db}-wal")
    finally:
        conn.close()

    assert not (copy_dir / "workbench_library.db-shm").exists()

    # The WAL-only registration is visible through the read-only snapshot.
    assert (
        classify_folder_for_cleanup(wal_only, db_path=copy_db)
        == CleanupClassification.LEGITIMATE_OR_UNPROVEN
    )

    # Read-only inspection must not create a sidecar next to the source.
    assert not (copy_dir / "workbench_library.db-shm").exists()
    assert not (copy_dir / "workbench_library.db-journal").exists()


# ---------------------------------------------------------------------------
# AC. the isolation failure message must not expose a private producer path.
# ---------------------------------------------------------------------------
def _load_conftest_module():
    path = Path(__file__).resolve().parent / "conftest.py"
    spec = importlib.util.spec_from_file_location("sb_1208_conftest", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ac_isolation_failure_message_is_path_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conftest_module = _load_conftest_module()
    producer_state_dir = Path.home() / ".sample-brain"

    monkeypatch.setattr(
        workbench_library,
        "resolve_workbench_state_dir",
        lambda *args, **kwargs: producer_state_dir,
    )

    with pytest.raises(AssertionError) as excinfo:
        conftest_module.isolated_workbench_state_dir.__wrapped__(tmp_path, monkeypatch)

    message = str(excinfo.value)
    assert str(producer_state_dir) not in message
    assert str(tmp_path) not in message


# ---------------------------------------------------------------------------
# AD. resolving the temp root must not probe (and mutate) the inspected dir.
# AE. the removal preview must classify a registered Source from the catalog
#     evidence it already collected.
# ---------------------------------------------------------------------------
def test_ad_classifier_never_calls_gettempdir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inspected = tmp_path / "library"
    inspected.mkdir()
    monkeypatch.setenv("TMPDIR", str(inspected))
    monkeypatch.setattr(workbench_library.tempfile, "tempdir", None, raising=False)

    def _boom() -> str:
        raise AssertionError("tempfile.gettempdir() must not be called")

    monkeypatch.setattr(workbench_library.tempfile, "gettempdir", _boom)

    target = inspected / "samples"
    target.mkdir()

    # Classification and the removal preview both stay read-only.
    workbench_library.classify_folder_for_cleanup(target, db_path=tmp_path / "missing.db")
    assert list(inspected.iterdir()) == [target]


def test_ad2_rejected_temp_candidate_is_not_canonical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # tempfile skips a candidate that is not writable and continues with the
    # next one; the classifier must not treat the rejected candidate as the
    # canonical temp root.
    rejected = tmp_path / "rejected"
    rejected.mkdir()
    accepted = tmp_path / "accepted"
    accepted.mkdir()
    monkeypatch.setenv("TMPDIR", str(rejected))
    monkeypatch.setenv("TEMP", str(accepted))
    monkeypatch.delenv("TMP", raising=False)
    monkeypatch.setattr(workbench_library.tempfile, "tempdir", None, raising=False)

    real_access = os.access

    def _access(path, mode, **kwargs):  # type: ignore[no-untyped-def]
        if str(path) == str(rejected):
            return False
        return real_access(path, mode, **kwargs)

    monkeypatch.setattr(workbench_library.os, "access", _access)

    assert workbench_library._runtime_temp_root() == accepted.resolve()


def test_ad3_legit_path_under_rejected_candidate_is_not_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rejected = tmp_path / "rejected"
    rejected.mkdir()
    accepted = tmp_path / "accepted"
    accepted.mkdir()
    platform_temp = tmp_path / "platform-temp"
    platform_temp.mkdir()
    monkeypatch.setenv("TMPDIR", str(rejected))
    monkeypatch.setenv("TEMP", str(accepted))
    monkeypatch.delenv("TMP", raising=False)
    monkeypatch.setattr(workbench_library.tempfile, "tempdir", None, raising=False)
    # The platform default root must not contain the inspected path either.
    monkeypatch.setattr(
        workbench_library, "_platform_default_temp_root", lambda: platform_temp
    )

    real_access = os.access

    def _access(path, mode, **kwargs):  # type: ignore[no-untyped-def]
        if str(path) == str(rejected):
            return False
        return real_access(path, mode, **kwargs)

    monkeypatch.setattr(workbench_library.os, "access", _access)

    # The rejected candidate is not a canonical root, so the path below it is
    # not inside the runtime temp directory and must not be classified as a
    # deterministic test artifact.
    assert workbench_library._runtime_temp_root() == accepted.resolve()

    target = rejected / "pytest-of-user" / "pytest-1" / "samples"
    target.mkdir(parents=True)
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_ad4_bytes_cached_temp_root_is_decoded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # tempfile supports a bytes tempdir global; Path() would raise TypeError.
    monkeypatch.setattr(
        workbench_library.tempfile, "tempdir", str(tmp_path).encode(), raising=False
    )
    assert workbench_library._runtime_temp_root() == tmp_path.resolve()


def test_ad5_fallback_candidates_are_modelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # tempfile continues through /var/tmp, /usr/tmp and the current directory
    # when no configured candidate is usable; the non-mutating resolver must
    # model the same order so a real pytest tree below the fallback is still
    # recognized.
    monkeypatch.setattr(workbench_library.os, "name", "posix")
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)

    candidates = [str(candidate) for candidate in workbench_library._temp_candidate_roots()]

    assert str(Path("/tmp")) in candidates
    assert str(Path("/var/tmp")) in candidates
    assert str(Path("/usr/tmp")) in candidates
    assert candidates[-1] == str(Path(os.getcwd()))


def test_ad6_windows_fallback_candidates_are_modelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Windows falls back to the user temp dir, the SystemRoot temp dir and the
    # standard drive-local temp directories before the current directory.
    monkeypatch.setattr(workbench_library.os, "name", "nt")
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.delenv("TEMP", raising=False)
    monkeypatch.delenv("TMP", raising=False)

    candidates = [str(candidate).lower() for candidate in workbench_library._temp_candidate_roots()]

    assert str(Path(os.path.expanduser(r"~\AppData\Local\Temp"))).lower() in candidates
    assert str(Path(os.path.expandvars(r"%SYSTEMROOT%\Temp"))).lower() in candidates
    for fallback in (r"c:\temp", r"c:\tmp", r"\temp", r"\tmp"):
        assert fallback in candidates
    assert candidates[-1] == str(Path(os.getcwd())).lower()


def test_ae_preview_classifies_registered_source_from_catalog_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_temp_root(tmp_path, monkeypatch)
    db_path = tmp_path / "state" / "workbench_library.db"
    folder = tmp_path / "samples"
    folder.mkdir()
    init_workbench_library(db_path)
    folder_id = register_library_folder(folder, db_path=db_path)

    preview = preview_library_folder_removal(folder_id, db_path=db_path)

    assert preview is not None
    assert preview.availability == "available"
    assert preview.classification == CleanupClassification.LEGITIMATE_OR_UNPROVEN


def test_ae2_preview_classifies_missing_registered_source_as_ambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_temp_root(tmp_path, monkeypatch)
    db_path = tmp_path / "state" / "workbench_library.db"
    folder = tmp_path / "samples"
    folder.mkdir()
    init_workbench_library(db_path)
    folder_id = register_library_folder(folder, db_path=db_path)
    folder.rmdir()

    preview = preview_library_folder_removal(folder_id, db_path=db_path)

    assert preview is not None
    assert preview.availability == "unavailable_or_missing"
    assert preview.classification == CleanupClassification.AMBIGUOUS


def test_ae3_preview_classifies_deterministic_test_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_temp = _fake_temp_root(tmp_path, monkeypatch)
    db_path = tmp_path / "state" / "workbench_library.db"
    artifact = fake_temp / "pytest-of-user" / "pytest-123" / "test_node"
    artifact.mkdir(parents=True)
    init_workbench_library(db_path)
    folder_id = register_library_folder(artifact, db_path=db_path)

    preview = preview_library_folder_removal(folder_id, db_path=db_path)

    assert preview is not None
    assert preview.classification == CleanupClassification.DETERMINISTIC_TEST_ARTIFACT


# ---------------------------------------------------------------------------
# AF. trusted pytest basetemp roots - explicit trusted roots
# ---------------------------------------------------------------------------
def test_af1_trusted_basetemp_with_pytest_node_is_deterministic(
    tmp_path: Path,
) -> None:
    """Trusted basetemp + pytest node directory directly below → deterministic."""
    trusted_root = tmp_path / "my-trusted-basetemp"
    trusted_root.mkdir()
    # pytest node directory directly under trusted root
    target = trusted_root / "test_example0"
    target.mkdir()
    assert (
        workbench_library.classify_folder_for_cleanup(
            target, trusted_pytest_basetemp_roots=(trusted_root,)
        )
        == CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_af2_trusted_basetemp_with_pytest_node_descendant_is_deterministic(
    tmp_path: Path,
) -> None:
    """Trusted basetemp + descendant within pytest node → deterministic."""
    trusted_root = tmp_path / "my-trusted-basetemp"
    trusted_root.mkdir()
    # pytest node with descendant
    target = trusted_root / "test_example0" / "samples"
    target.mkdir(parents=True)
    assert (
        workbench_library.classify_folder_for_cleanup(
            target, trusted_pytest_basetemp_roots=(trusted_root,)
        )
        == CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_af3_same_structure_without_trusted_root_is_not_deterministic(
    tmp_path: Path,
) -> None:
    """Same path shape but without trusted root → not deterministic."""
    fake_root = tmp_path / "my-basetemp"
    fake_root.mkdir()
    target = fake_root / "test_example0"
    target.mkdir()
    # No trusted roots provided
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )
    # Empty trusted roots tuple
    assert (
        workbench_library.classify_folder_for_cleanup(
            target, trusted_pytest_basetemp_roots=()
        )
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_af4_samples_folder_under_trusted_root_is_not_deterministic(
    tmp_path: Path,
) -> None:
    """Arbitrary Samples folder under trusted root → not deterministic."""
    trusted_root = tmp_path / "my-trusted-basetemp"
    trusted_root.mkdir()
    target = trusted_root / "Samples"
    target.mkdir()
    assert (
        workbench_library.classify_folder_for_cleanup(
            target, trusted_pytest_basetemp_roots=(trusted_root,)
        )
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_af5_test_samples_without_uniquifier_is_not_deterministic(
    tmp_path: Path,
) -> None:
    """test_samples without numeric uniquifier → not deterministic."""
    trusted_root = tmp_path / "my-trusted-basetemp"
    trusted_root.mkdir()
    # No numeric suffix at end
    target = trusted_root / "test_samples"
    target.mkdir()
    assert (
        workbench_library.classify_folder_for_cleanup(
            target, trusted_pytest_basetemp_roots=(trusted_root,)
        )
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_af6_root_vs_backup_prefix_collision_is_not_deterministic(
    tmp_path: Path,
) -> None:
    """root-backup must not be treated as child of root."""
    trusted_root = tmp_path / "my-trusted-basetemp"
    trusted_root.mkdir()
    # A directory that looks like a sibling with -backup suffix
    target = tmp_path / "my-trusted-basetemp-backup" / "test_example0"
    target.mkdir(parents=True)
    assert (
        workbench_library.classify_folder_for_cleanup(
            target, trusted_pytest_basetemp_roots=(trusted_root,)
        )
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_af7_missing_target_is_not_deterministic(
    tmp_path: Path,
) -> None:
    """Missing target path → fail-closed, not deterministic."""
    trusted_root = tmp_path / "my-trusted-basetemp"
    trusted_root.mkdir()
    target = trusted_root / "does_not_exist"
    assert (
        workbench_library.classify_folder_for_cleanup(
            target, trusted_pytest_basetemp_roots=(trusted_root,)
        )
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_af7b_missing_descendant_under_existing_node_is_not_deterministic(
    tmp_path: Path,
) -> None:
    """A missing descendant below an existing node directory stays fail-closed."""
    trusted_root = tmp_path / "my-trusted-basetemp"
    trusted_root.mkdir()
    node_dir = trusted_root / "test_example0"
    node_dir.mkdir()
    target = node_dir / "does_not_exist"
    assert (
        workbench_library.classify_folder_for_cleanup(
            target, trusted_pytest_basetemp_roots=(trusted_root,)
        )
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_af8_structural_variant_with_trusted_basetemp(
    tmp_path: Path,
) -> None:
    """classify_folder_for_cleanup_structural also respects trusted roots."""
    trusted_root = tmp_path / "my-trusted-basetemp"
    trusted_root.mkdir()
    target = trusted_root / "test_example0"
    target.mkdir()
    assert (
        workbench_library.classify_folder_for_cleanup_structural(
            target, trusted_pytest_basetemp_roots=(trusted_root,)
        )
        == CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )
    target2 = trusted_root / "test_example0" / "subdir"
    target2.mkdir(parents=True)
    assert (
        workbench_library.classify_folder_for_cleanup_structural(
            target2, trusted_pytest_basetemp_roots=(trusted_root,)
        )
        == CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_af9_trusted_root_itself_is_not_deterministic(
    tmp_path: Path,
) -> None:
    """The trusted root itself is not a pytest node."""
    trusted_root = tmp_path / "my-trusted-basetemp"
    trusted_root.mkdir()
    assert (
        workbench_library.classify_folder_for_cleanup(
            trusted_root, trusted_pytest_basetemp_roots=(trusted_root,)
        )
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_af10_symlink_escape_not_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Symlink/junction escape from trusted root must not become deterministic."""
    if os.name == "nt":
        pytest.skip("Symlink test requires appropriate permissions on Windows")
    trusted_root = tmp_path / "my-trusted-basetemp"
    trusted_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    # Create symlink from trusted_root/evil -> outside
    evil_link = trusted_root / "evil"
    evil_link.symlink_to(outside)
    target = evil_link / "test_example0"
    target.mkdir(parents=True)
    # The symlink target is outside the trusted root
    assert (
        workbench_library.classify_folder_for_cleanup(
            target, trusted_pytest_basetemp_roots=(trusted_root,)
        )
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )
