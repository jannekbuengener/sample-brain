"""Regression tests for #1208: Workbench library state cleanup guard.

Covers the fail-closed connection boundary, the deterministic test-artifact
classifier rule, the SQLAlchemy-free read-only catalog inspection, and the
read-only dry-run removal preview.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import src.workbench_library as workbench_library
from src.workbench_library import (
    CleanupClassification,
    WorkbenchLibraryConnectionError,
    connect_workbench_library,
    init_workbench_library,
    preview_library_folder_removal,
    register_library_folder,
    workbench_library_db_path,
)


def _db_bytes(db_path: Path) -> bytes:
    return db_path.read_bytes()


def _get_producer_db() -> Path:
    return Path.home() / ".sample-brain" / "workbench_library.db"


# ---------------------------------------------------------------------------
# A. normal pytest default resolves isolated state
# ---------------------------------------------------------------------------
def test_a_normal_pytest_default_resolves_isolated_state(
    isolated_workbench_state_dir: Path,
) -> None:
    db_path = workbench_library_db_path()
    assert db_path == isolated_workbench_state_dir / "workbench_library.db"

    producer_db = _get_producer_db()
    producer_existed_before = producer_db.is_file()
    producer_bytes_before = _db_bytes(producer_db) if producer_existed_before else None

    # Default connection resolves to the isolated pytest state, not the producer.
    conn = connect_workbench_library()
    try:
        assert conn.execute("SELECT 1").fetchone()[0] == 1
    finally:
        conn.close()

    # The real producer DB was neither created nor modified by this test.
    assert producer_db.is_file() == producer_existed_before
    if producer_existed_before:
        assert _db_bytes(producer_db) == producer_bytes_before


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
    fake_temp = tmp_path / "temp"
    fake_temp.mkdir()
    monkeypatch.setattr(
        workbench_library.tempfile, "gettempdir", lambda: str(fake_temp)
    )
    return fake_temp


def test_g_canonical_temp_plus_pytest_structure_is_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_temp = _fake_temp_root(tmp_path, monkeypatch)
    target = fake_temp / "pytest-of-user" / "pytest-123" / "test_node"
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
# I. my_pytest_tmp_samples outside pytest tree => not deterministic
# J. pytest-project outside pytest tree => not deterministic
# ---------------------------------------------------------------------------
def test_i_my_pytest_tmp_samples_outside_pytest_tree_not_deterministic(
    tmp_path: Path,
) -> None:
    target = tmp_path / "my_pytest_tmp_samples"
    target.mkdir()
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


def test_j_pytest_project_outside_pytest_tree_not_deterministic(
    tmp_path: Path,
) -> None:
    target = tmp_path / "pytest-project"
    target.mkdir()
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        != CleanupClassification.DETERMINISTIC_TEST_ARTIFACT
    )


# ---------------------------------------------------------------------------
# K. narrowly proven exact historical test signature => deterministic
# ---------------------------------------------------------------------------
def test_k_exact_historical_test_signature_is_deterministic(tmp_path: Path) -> None:
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
# L. generic nonexistent path => AMBIGUOUS
# ---------------------------------------------------------------------------
def test_l_generic_nonexistent_path_is_ambiguous(tmp_path: Path) -> None:
    target = tmp_path / "does-not-exist"
    assert (
        workbench_library.classify_folder_for_cleanup(target)
        == CleanupClassification.AMBIGUOUS
    )


# ---------------------------------------------------------------------------
# M. read-only dry-run does not create missing DB
# N. read-only dry-run does not change existing DB contents/schema
# O. filesystem sentinel survives dry-run
# ---------------------------------------------------------------------------
def test_m_readonly_dry_run_does_not_create_missing_db(tmp_path: Path) -> None:
    missing_db = tmp_path / "missing" / "workbench_library.db"
    missing_folder = tmp_path / "some-folder"
    assert not missing_db.exists()

    preview = preview_library_folder_removal(missing_folder, db_path=missing_db)

    assert preview is None
    assert not missing_db.exists()
    assert not missing_db.parent.exists()


def test_n_readonly_dry_run_does_not_change_existing_db(tmp_path: Path) -> None:
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


def test_o_filesystem_sentinel_survives_dry_run(tmp_path: Path) -> None:
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
