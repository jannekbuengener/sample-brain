"""Verification for a separately installed Sample Brain runtime.

The manifest lives in the runtime worktree's Git administrative directory, not
in its source tree.  Verification is deliberately read-only: installation is
the only code path that writes a manifest.
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Mapping


MANIFEST_SCHEMA = 1
MANIFEST_NAME = "sample-brain-runtime.json"
SHA_LENGTH = 40
GitRun = Callable[..., str]


class RuntimeStatus(str, Enum):
    VALID = "valid"
    STALE = "stale"
    UNKNOWN = "unknown"
    HEAD_MISMATCH = "head_mismatch"
    DIRTY = "dirty"
    INTERPRETER_MISMATCH = "interpreter_mismatch"
    IMPORT_MISMATCH = "import_mismatch"


@dataclass(frozen=True)
class RuntimeManifest:
    schema: int
    channel: str
    commit: str
    runtime_root: str
    python_executable: str
    installed_at: str

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "RuntimeManifest":
        required = (
            "schema",
            "channel",
            "commit",
            "runtime_root",
            "python_executable",
            "installed_at",
        )
        if any(key not in value for key in required):
            raise ValueError("Runtime-Manifest ist unvollständig.")
        manifest = cls(**{key: value[key] for key in required})  # type: ignore[arg-type]
        if manifest.schema != MANIFEST_SCHEMA:
            raise ValueError("Runtime-Manifest hat ein unbekanntes Schema.")
        if not manifest.channel:
            raise ValueError("Runtime-Manifest enthält keinen Channel.")
        if len(manifest.commit) != SHA_LENGTH or any(
            character not in "0123456789abcdef" for character in manifest.commit.lower()
        ):
            raise ValueError("Runtime-Manifest enthält keinen vollständigen Commit-SHA.")
        if not manifest.runtime_root or not manifest.python_executable:
            raise ValueError("Runtime-Manifest enthält keinen Runtime-Pfad.")
        if not manifest.installed_at:
            raise ValueError("Runtime-Manifest enthält keine Installationsinformation.")
        return manifest

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "channel": self.channel,
            "commit": self.commit,
            "runtime_root": self.runtime_root,
            "python_executable": self.python_executable,
            "installed_at": self.installed_at,
        }


@dataclass(frozen=True)
class RuntimeReport:
    status: RuntimeStatus
    diagnosis: str
    manifest: RuntimeManifest | None = None

    @property
    def can_launch(self) -> bool:
        return self.status in {RuntimeStatus.VALID, RuntimeStatus.STALE}


def _path(value: Path | str) -> Path:
    return Path(value).resolve()


def _default_git_run(runtime_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(runtime_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def manifest_path_for_runtime(runtime_root: Path, *, git_run: GitRun | None = None) -> Path:
    """Return the Git-administrative manifest path for this worktree."""
    root = _path(runtime_root)
    runner = git_run or (lambda *args: _default_git_run(root, *args))
    git_path = Path(runner("rev-parse", "--git-path", MANIFEST_NAME))
    return git_path if git_path.is_absolute() else root / git_path


def load_runtime_manifest(manifest_path: Path) -> RuntimeManifest:
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Runtime-Manifest fehlt oder ist nicht lesbar.") from exc
    if not isinstance(value, dict):
        raise ValueError("Runtime-Manifest hat kein Objektformat.")
    return RuntimeManifest.from_dict(value)


def write_runtime_manifest(runtime_root: Path, manifest: RuntimeManifest) -> Path:
    """Write local installation metadata outside the runtime source tree."""
    root = _path(runtime_root)
    if _path(manifest.runtime_root) != root:
        raise ValueError("Manifest-Runtime-Root stimmt nicht mit dem Ziel überein.")
    path = manifest_path_for_runtime(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.to_dict(), indent=2) + "\n", encoding="utf-8")
    return path


def _runtime_module_paths() -> dict[str, Path]:
    result: dict[str, Path] = {}
    for name in ("src.cli", "src.workbench"):
        module = importlib.import_module(name)
        location = getattr(module, "__file__", None)
        if location is None:
            raise ValueError(f"Import-Provenance für {name} fehlt.")
        result[name] = Path(location)
    return result


def _report(status: RuntimeStatus, diagnosis: str, manifest: RuntimeManifest | None = None) -> RuntimeReport:
    return RuntimeReport(status=status, diagnosis=diagnosis, manifest=manifest)


def evaluate_runtime(
    runtime_root: Path,
    *,
    manifest_path: Path | None = None,
    executable: Path | None = None,
    module_paths: Mapping[str, Path] | None = None,
    git_run: GitRun | None = None,
    current_channel_commit: str | None = None,
) -> RuntimeReport:
    """Classify runtime provenance without changing Git, imports, or files."""
    root = _path(runtime_root)
    try:
        manifest = load_runtime_manifest(manifest_path or manifest_path_for_runtime(root, git_run=git_run))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return _report(RuntimeStatus.UNKNOWN, f"Runtime-Herkunft unbekannt: {exc}")

    if _path(manifest.runtime_root) != root:
        return _report(RuntimeStatus.UNKNOWN, "Runtime-Root stimmt nicht mit dem Manifest überein.", manifest)

    actual_executable = _path(executable or Path(sys.executable))
    if actual_executable != _path(manifest.python_executable):
        return _report(RuntimeStatus.INTERPRETER_MISMATCH, "Runtime-Interpreter stimmt nicht mit dem Manifest überein.", manifest)

    try:
        paths = dict(module_paths) if module_paths is not None else _runtime_module_paths()
    except (ImportError, ValueError) as exc:
        return _report(RuntimeStatus.IMPORT_MISMATCH, f"Runtime-Import-Provenance ist ungültig: {exc}", manifest)
    for module_name in ("src.cli", "src.workbench"):
        module_path = paths.get(module_name)
        if module_path is None or root not in _path(module_path).parents:
            return _report(RuntimeStatus.IMPORT_MISMATCH, f"{module_name} stammt nicht aus dem Runtime-Root.", manifest)

    runner = git_run or (lambda *args: _default_git_run(root, *args))
    try:
        head = runner("rev-parse", "HEAD").strip()
        dirty = bool(runner("status", "--porcelain"))
    except (OSError, subprocess.SubprocessError) as exc:
        return _report(RuntimeStatus.UNKNOWN, f"Runtime-Git-Provenance nicht prüfbar: {exc}", manifest)
    if head != manifest.commit:
        return _report(RuntimeStatus.HEAD_MISMATCH, "Runtime-HEAD stimmt nicht mit dem Manifest-Commit überein.", manifest)
    if dirty:
        return _report(RuntimeStatus.DIRTY, "Runtime-Worktree ist dirty; Producer-Start wird nicht ausgeführt.", manifest)
    if current_channel_commit and current_channel_commit != manifest.commit:
        return _report(RuntimeStatus.STALE, "Bekannter älterer Runtime-Build; Update ist explizit auszuführen.", manifest)
    return _report(RuntimeStatus.VALID, f"Verifizierte Runtime: {manifest.channel}@{manifest.commit}", manifest)


def harmonic_match_feature_available(runtime_root: Path) -> bool:
    """A provenance smoke, not a visual acceptance assertion."""
    try:
        source = (_path(runtime_root) / "src" / "workbench.py").read_text(encoding="utf-8")
    except OSError:
        return False
    return "Harmonic Match" in source


def describe_runtime(runtime_root: Path) -> str:
    report = evaluate_runtime(runtime_root)
    if report.manifest is None:
        return report.diagnosis
    return "\n".join(
        (
            f"Status: {report.status.value}",
            f"Channel: {report.manifest.channel}",
            f"Commit: {report.manifest.commit}",
            f"Runtime: {report.manifest.runtime_root}",
            report.diagnosis,
        )
    )


def _main() -> int:
    parser = argparse.ArgumentParser(description="Sample Brain Runtime-Provenance")
    parser.add_argument("--runtime-root", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--channel", default="main")
    parser.add_argument("--commit")
    args = parser.parse_args()
    root = _path(args.runtime_root)
    if args.write_manifest:
        if args.commit is None:
            parser.error("--write-manifest benötigt --commit")
        manifest = RuntimeManifest(
            schema=MANIFEST_SCHEMA,
            channel=args.channel,
            commit=args.commit,
            runtime_root=str(root),
            python_executable=str(_path(Path(sys.executable))),
            installed_at=datetime.now(UTC).isoformat(),
        )
        write_runtime_manifest(root, RuntimeManifest.from_dict(manifest.to_dict()))
        return 0
    if args.check:
        report = evaluate_runtime(root)
        print(report.diagnosis)
        return 0 if report.can_launch else 1
    parser.error("--check oder --write-manifest erforderlich")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
