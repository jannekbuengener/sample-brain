from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.runtime_provenance import (
    RuntimeManifest,
    RuntimeStatus,
    evaluate_runtime,
    harmonic_match_feature_available,
)


COMMIT = "a" * 40
NEWER_COMMIT = "b" * 40


def _runtime_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "runtime"
    python = root / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "cli.py").write_text("", encoding="utf-8")
    (root / "src" / "workbench.py").write_text(
        'BUTTON = "Harmonic Match"\n', encoding="utf-8"
    )
    return root, python


def _manifest(root: Path, python: Path, **changes: object) -> RuntimeManifest:
    values: dict[str, object] = {
        "schema": 1,
        "channel": "main",
        "commit": COMMIT,
        "runtime_root": str(root),
        "python_executable": str(python),
        "installed_at": "2026-09-07T20:00:00Z",
    }
    values.update(changes)
    return RuntimeManifest.from_dict(values)


def _write_manifest(path: Path, manifest: RuntimeManifest) -> None:
    path.write_text(json.dumps(manifest.to_dict()), encoding="utf-8")


def _git(head: str = COMMIT, dirty: bool = False):
    def run(*args: str) -> str:
        if args[-2:] == ("rev-parse", "HEAD"):
            return head
        if args[-2:] == ("status", "--porcelain"):
            return " M src/workbench.py\n" if dirty else ""
        raise AssertionError(args)

    return run


def test_valid_runtime_identity_includes_required_provenance(tmp_path: Path):
    root, python = _runtime_root(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = _manifest(root, python)
    _write_manifest(manifest_path, manifest)

    report = evaluate_runtime(
        root,
        manifest_path=manifest_path,
        executable=python,
        module_paths={"src.cli": root / "src" / "cli.py", "src.workbench": root / "src" / "workbench.py"},
        git_run=_git(),
    )

    assert report.status is RuntimeStatus.VALID
    assert report.can_launch is True
    assert report.manifest == manifest


@pytest.mark.parametrize(
    "changes,head,expected",
    [
        ({}, NEWER_COMMIT, RuntimeStatus.HEAD_MISMATCH),
        ({}, COMMIT, RuntimeStatus.DIRTY),
    ],
)
def test_mismatch_or_dirty_runtime_blocks_launch(
    tmp_path: Path, changes: dict[str, object], head: str, expected: RuntimeStatus
):
    root, python = _runtime_root(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, _manifest(root, python, **changes))

    report = evaluate_runtime(
        root,
        manifest_path=manifest_path,
        executable=python,
        module_paths={"src.cli": root / "src" / "cli.py", "src.workbench": root / "src" / "workbench.py"},
        git_run=_git(head=head, dirty=expected is RuntimeStatus.DIRTY),
    )

    assert report.status is expected
    assert report.can_launch is False


def test_missing_or_invalid_manifest_never_claims_a_build(tmp_path: Path):
    root, python = _runtime_root(tmp_path)

    missing = evaluate_runtime(
        root,
        manifest_path=tmp_path / "missing.json",
        executable=python,
        module_paths={},
        git_run=_git(),
    )

    assert missing.status is RuntimeStatus.UNKNOWN
    assert missing.can_launch is False
    assert "main@" not in missing.diagnosis


def test_wrong_interpreter_or_import_root_blocks_launch(tmp_path: Path):
    root, python = _runtime_root(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, _manifest(root, python))

    report = evaluate_runtime(
        root,
        manifest_path=manifest_path,
        executable=tmp_path / "other-python.exe",
        module_paths={"src.cli": tmp_path / "other" / "cli.py", "src.workbench": root / "src" / "workbench.py"},
        git_run=_git(),
    )

    assert report.status is RuntimeStatus.INTERPRETER_MISMATCH
    assert report.can_launch is False


def test_wrong_import_root_blocks_launch(tmp_path: Path):
    root, python = _runtime_root(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, _manifest(root, python))

    report = evaluate_runtime(
        root,
        manifest_path=manifest_path,
        executable=python,
        module_paths={
            "src.cli": tmp_path / "other" / "cli.py",
            "src.workbench": root / "src" / "workbench.py",
        },
        git_run=_git(),
    )

    assert report.status is RuntimeStatus.IMPORT_MISMATCH
    assert report.can_launch is False


def test_known_older_runtime_is_allowed_without_an_update(tmp_path: Path):
    root, python = _runtime_root(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, _manifest(root, python))

    report = evaluate_runtime(
        root,
        manifest_path=manifest_path,
        executable=python,
        module_paths={"src.cli": root / "src" / "cli.py", "src.workbench": root / "src" / "workbench.py"},
        git_run=_git(),
        current_channel_commit=NEWER_COMMIT,
    )

    assert report.status is RuntimeStatus.STALE
    assert report.can_launch is True
    assert "Update" in report.diagnosis


def test_harmonic_match_feature_smoke_uses_the_runtime_source(tmp_path: Path):
    root, _python = _runtime_root(tmp_path)

    assert harmonic_match_feature_available(root) is True
