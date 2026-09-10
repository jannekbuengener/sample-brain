from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIN_TOOLS = ROOT / "tools" / "windows"


def test_windows_helper_scripts_exist():
    assert (WIN_TOOLS / "start_workbench.cmd").is_file()
    assert (WIN_TOOLS / "create_workbench_desktop_shortcut.ps1").is_file()
    assert (WIN_TOOLS / "README.md").is_file()


def test_legacy_start_workbench_cmd_routes_to_verified_runtime_only():
    content = (WIN_TOOLS / "start_workbench.cmd").read_text(encoding="utf-8")
    assert "%LOCALAPPDATA%\\SampleBrain\\runtime" in content
    assert "start_runtime_workbench.cmd" in content
    assert "src.cli workbench" not in content
    assert "set \"PY=python\"" not in content
    assert not re.search(r"[A-Za-z]:\\", content)


def test_legacy_shortcut_helper_targets_existing_verified_runtime():
    content = (WIN_TOOLS / "create_workbench_desktop_shortcut.ps1").read_text(encoding="utf-8")
    assert "SampleBrain\\runtime" in content
    assert "create_runtime_workbench_shortcut.ps1" in content
    assert "start_workbench.cmd" not in content
    assert not re.search(r"[A-Za-z]:\\", content)


def test_runtime_launcher_requires_its_own_venv_and_checks_provenance():
    content = (WIN_TOOLS / "start_runtime_workbench.cmd").read_text(encoding="utf-8")
    assert ".venv\\Scripts\\python.exe" in content
    assert "set \"PY=python\"" not in content
    assert "src.runtime_provenance --check" in content
    assert "src.cli workbench" in content


def test_runtime_shortcut_is_separate_from_the_legacy_shortcut():
    content = (WIN_TOOLS / "create_runtime_workbench_shortcut.ps1").read_text(
        encoding="utf-8"
    )
    assert "Sample Brain Runtime Workbench.lnk" in content
    assert "start_runtime_workbench.cmd" in content
    assert "create_workbench_desktop_shortcut" not in content


def test_runtime_installer_uses_detached_staging_without_developer_cleanup():
    content = (WIN_TOOLS / "install_runtime_workbench.ps1").read_text(encoding="utf-8")
    assert "worktree add --detach" in content
    assert "worktree move" in content
    assert "git clean" not in content
    assert "git reset" not in content


def test_runtime_installer_groups_existing_runtime_gate_before_test_path():
    content = (WIN_TOOLS / "install_runtime_workbench.ps1").read_text(encoding="utf-8")

    assert "if ((Test-Path -LiteralPath $RuntimeRoot) -and -not $ReplaceExisting)" in content
    assert "Test-Path -LiteralPath $RuntimeRoot -and" not in content


def _powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _run_powershell(command: str, *, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    executable = _powershell()
    assert executable is not None
    return subprocess.run(
        [
            executable,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_runtime_installer_existing_runtime_gate_powershell_smoke():
    if _powershell() is None:
        return

    installer = WIN_TOOLS / "install_runtime_workbench.ps1"
    with tempfile.TemporaryDirectory() as temporary_directory:
        runtime_root = Path(temporary_directory) / "existing-runtime"
        runtime_root.mkdir()
        environment = dict(os.environ)
        environment["INSTALLER_PATH"] = str(installer)
        environment["SYNTHETIC_RUNTIME_ROOT"] = str(runtime_root)

        unchanged = _run_powershell(
            """
function git {
    param([Parameter(ValueFromRemainingArguments = $true)] $Arguments)
    if ($Arguments -contains 'rev-parse') {
        '0123456789012345678901234567890123456789'
        $global:LASTEXITCODE = 0
        return
    }
    throw "Unexpected git invocation: $Arguments"
}
& $env:INSTALLER_PATH -RuntimeRoot $env:SYNTHETIC_RUNTIME_ROOT
""",
            environment=environment,
        )
        assert unchanged.returncode == 0, unchanged.stderr
        assert "was left unchanged" in unchanged.stdout

        staging_probe = _run_powershell(
            """
function git {
    param([Parameter(ValueFromRemainingArguments = $true)] $Arguments)
    if ($Arguments -contains 'rev-parse') {
        '0123456789012345678901234567890123456789'
        $global:LASTEXITCODE = 0
        return
    }
    if ($Arguments -contains 'worktree') {
        Write-Output 'REACHED_STAGING'
        throw 'STOP_AFTER_GATE'
    }
    throw "Unexpected git invocation: $Arguments"
}
try {
    & $env:INSTALLER_PATH -RuntimeRoot $env:SYNTHETIC_RUNTIME_ROOT -ReplaceExisting
    throw 'Installer did not reach the staging probe.'
} catch {
    if ($_.Exception.Message -match 'STOP_AFTER_GATE') { exit 23 }
    throw
}
""",
            environment=environment,
        )
        assert staging_probe.returncode == 23, staging_probe.stderr
        assert "REACHED_STAGING" in staging_probe.stdout

        missing_root = Path(temporary_directory) / "missing-runtime"
        environment["SYNTHETIC_RUNTIME_ROOT"] = str(missing_root)
        missing_probe = _run_powershell(
            """
function git {
    param([Parameter(ValueFromRemainingArguments = $true)] $Arguments)
    if ($Arguments -contains 'rev-parse') {
        '0123456789012345678901234567890123456789'
        $global:LASTEXITCODE = 0
        return
    }
    if ($Arguments -contains 'worktree') {
        Write-Output 'REACHED_STAGING'
        throw 'STOP_AFTER_GATE'
    }
    throw "Unexpected git invocation: $Arguments"
}
try {
    & $env:INSTALLER_PATH -RuntimeRoot $env:SYNTHETIC_RUNTIME_ROOT
    throw 'Installer did not reach the staging probe.'
} catch {
    if ($_.Exception.Message -match 'STOP_AFTER_GATE') { exit 23 }
    throw
}
""",
            environment=environment,
        )
        assert missing_probe.returncode == 23, missing_probe.stderr
        assert "REACHED_STAGING" in missing_probe.stdout


def test_runtime_installer_parent_gate_powershell_smoke():
    if _powershell() is None:
        return

    installer = WIN_TOOLS / "install_runtime_workbench.ps1"
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        environment = dict(os.environ)
        environment["INSTALLER_PATH"] = str(installer)

        existing_parent = temporary_root / "existing-parent"
        existing_parent.mkdir()
        environment["SYNTHETIC_RUNTIME_ROOT"] = str(existing_parent / "runtime")
        existing_parent_probe = _run_powershell(
            """
function New-Item {
    throw 'EXISTING_PARENT_NEW_ITEM_CALLED'
}
function git {
    param([Parameter(ValueFromRemainingArguments = $true)] $Arguments)
    if ($Arguments -contains 'rev-parse') {
        '0123456789012345678901234567890123456789'
        $global:LASTEXITCODE = 0
        return
    }
    if ($Arguments -contains 'worktree') {
        Write-Output 'REACHED_STAGING'
        throw 'STOP_AFTER_GATE'
    }
    throw "Unexpected git invocation: $Arguments"
}
try {
    & $env:INSTALLER_PATH -RuntimeRoot $env:SYNTHETIC_RUNTIME_ROOT
    throw 'Installer did not reach the staging probe.'
} catch {
    if ($_.Exception.Message -match 'STOP_AFTER_GATE') { exit 23 }
    throw
}
""",
            environment=environment,
        )
        assert existing_parent_probe.returncode == 23, existing_parent_probe.stderr
        assert "REACHED_STAGING" in existing_parent_probe.stdout

        missing_parent = temporary_root / "missing-parent"
        environment["SYNTHETIC_RUNTIME_ROOT"] = str(missing_parent / "runtime")
        missing_parent_probe = _run_powershell(
            """
function git {
    param([Parameter(ValueFromRemainingArguments = $true)] $Arguments)
    if ($Arguments -contains 'rev-parse') {
        '0123456789012345678901234567890123456789'
        $global:LASTEXITCODE = 0
        return
    }
    if ($Arguments -contains 'worktree') {
        Write-Output 'REACHED_STAGING'
        throw 'STOP_AFTER_GATE'
    }
    throw "Unexpected git invocation: $Arguments"
}
try {
    & $env:INSTALLER_PATH -RuntimeRoot $env:SYNTHETIC_RUNTIME_ROOT
    throw 'Installer did not reach the staging probe.'
} catch {
    if ($_.Exception.Message -match 'STOP_AFTER_GATE') { exit 23 }
    throw
}
""",
            environment=environment,
        )
        assert missing_parent_probe.returncode == 23, missing_parent_probe.stderr
        assert missing_parent.is_dir()
        assert "REACHED_STAGING" in missing_parent_probe.stdout

        if os.name == "nt":
            root_parent = Path(temporary_root.anchor)
            environment["SYNTHETIC_RUNTIME_ROOT"] = str(
                root_parent / f"samplebrain-root-parent-{uuid.uuid4().hex}"
            )
            root_parent_probe = _run_powershell(
                """
function New-Item {
    throw 'ROOT_PARENT_NEW_ITEM_CALLED'
}
function git {
    param([Parameter(ValueFromRemainingArguments = $true)] $Arguments)
    if ($Arguments -contains 'rev-parse') {
        '0123456789012345678901234567890123456789'
        $global:LASTEXITCODE = 0
        return
    }
    if ($Arguments -contains 'worktree') {
        Write-Output 'REACHED_STAGING'
        throw 'STOP_AFTER_GATE'
    }
    throw "Unexpected git invocation: $Arguments"
}
try {
    & $env:INSTALLER_PATH -RuntimeRoot $env:SYNTHETIC_RUNTIME_ROOT
    throw 'Installer did not reach the staging probe.'
} catch {
    if ($_.Exception.Message -match 'STOP_AFTER_GATE') { exit 23 }
    throw
}
""",
                environment=environment,
            )
            assert root_parent_probe.returncode == 23, root_parent_probe.stderr
            assert "REACHED_STAGING" in root_parent_probe.stdout


def test_runtime_installer_scopes_staging_provenance_to_staging_cwd():
    content = (WIN_TOOLS / "install_runtime_workbench.ps1").read_text(encoding="utf-8")

    push_location = "Push-Location -LiteralPath $StagingRoot"
    manifest_call = "& $Python -m src.runtime_provenance --write-manifest"
    check_call = "& $Python -m src.runtime_provenance --check --runtime-root $StagingRoot"

    assert push_location in content
    assert manifest_call in content
    assert check_call in content
    assert content.index(push_location) < content.index(manifest_call) < content.index(
        check_call
    )
    assert "finally {\n        Pop-Location\n    }" in content

    if _powershell() is None:
        return

    with tempfile.TemporaryDirectory() as temporary_directory:
        caller_cwd = Path(temporary_directory) / "caller"
        staging_cwd = Path(temporary_directory) / "staging"
        caller_cwd.mkdir()
        staging_cwd.mkdir()
        environment = dict(os.environ)
        environment["SYNTHETIC_CALLER_CWD"] = str(caller_cwd)
        environment["SYNTHETIC_STAGING_CWD"] = str(staging_cwd)

        success = _run_powershell(
            """
Set-Location -LiteralPath $env:SYNTHETIC_CALLER_CWD
Push-Location -LiteralPath $env:SYNTHETIC_STAGING_CWD
try {
    "PROVENANCE_CWD=$((Get-Location).Path)"
}
finally {
    Pop-Location
}
"CALLER_CWD=$((Get-Location).Path)"
""",
            environment=environment,
        )
        assert success.returncode == 0, success.stderr
        assert f"PROVENANCE_CWD={staging_cwd}" in success.stdout
        assert f"CALLER_CWD={caller_cwd}" in success.stdout

        failure = _run_powershell(
            """
Set-Location -LiteralPath $env:SYNTHETIC_CALLER_CWD
try {
    Push-Location -LiteralPath $env:SYNTHETIC_STAGING_CWD
    try {
        "PROVENANCE_CWD=$((Get-Location).Path)"
        throw 'SYNTHETIC_PROVENANCE_FAILURE'
    }
    finally {
        Pop-Location
    }
} catch {
    if ($_.Exception.Message -ne 'SYNTHETIC_PROVENANCE_FAILURE') { throw }
}
"CALLER_CWD=$((Get-Location).Path)"
""",
            environment=environment,
        )
        assert failure.returncode == 0, failure.stderr
        assert f"PROVENANCE_CWD={staging_cwd}" in failure.stdout
        assert f"CALLER_CWD={caller_cwd}" in failure.stdout


def test_runtime_installer_provenance_processes_use_staging_cwd():
    if _powershell() is None:
        return

    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        staging_root = temporary_root / "staging"
        caller_cwd = temporary_root / "caller"
        staging_src = staging_root / "src"
        caller_src = caller_cwd / "src"
        staging_src.mkdir(parents=True)
        caller_src.mkdir(parents=True)
        (staging_root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
        shutil.copyfile(ROOT / "src" / "runtime_provenance.py", staging_src / "runtime_provenance.py")
        for source_root, marker in ((staging_src, "staging"), (caller_src, "caller")):
            (source_root / "__init__.py").write_text("", encoding="utf-8")
            (source_root / "cli.py").write_text(f"MARKER = {marker!r}\n", encoding="utf-8")
            (source_root / "workbench.py").write_text(f"MARKER = {marker!r}\n", encoding="utf-8")

        for arguments in (
            ("init",),
            ("config", "user.email", "synthetic@example.invalid"),
            ("config", "user.name", "Synthetic Runtime"),
            ("add", "."),
            ("commit", "-m", "synthetic runtime"),
        ):
            subprocess.run(["git", *arguments], cwd=staging_root, check=True, capture_output=True)
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=staging_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        environment = dict(os.environ)
        environment.update(
            {
                "SYNTHETIC_CALLER_CWD": str(caller_cwd),
                "SYNTHETIC_STAGING_CWD": str(staging_root),
                "SYNTHETIC_PYTHON": sys.executable,
                "SYNTHETIC_COMMIT": commit,
            }
        )

        success = _run_powershell(
            """
Set-Location -LiteralPath $env:SYNTHETIC_CALLER_CWD
Push-Location -LiteralPath $env:SYNTHETIC_STAGING_CWD
try {
    & $env:SYNTHETIC_PYTHON -m src.runtime_provenance --write-manifest --runtime-root $env:SYNTHETIC_STAGING_CWD --channel main --commit $env:SYNTHETIC_COMMIT
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $env:SYNTHETIC_PYTHON -m src.runtime_provenance --check --runtime-root $env:SYNTHETIC_STAGING_CWD
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $env:SYNTHETIC_PYTHON -c "import src.cli, src.workbench; print('CLI=' + src.cli.__file__); print('WORKBENCH=' + src.workbench.__file__)"
} finally {
    Pop-Location
}
"CALLER_CWD=$((Get-Location).Path)"
""",
            environment=environment,
        )
        assert success.returncode == 0, success.stderr
        assert "Verifizierte Runtime: main@" in success.stdout
        assert f"CLI={staging_src / 'cli.py'}" in success.stdout
        assert f"WORKBENCH={staging_src / 'workbench.py'}" in success.stdout
        assert f"CALLER_CWD={caller_cwd}" in success.stdout

        failure = _run_powershell(
            """
Set-Location -LiteralPath $env:SYNTHETIC_CALLER_CWD
Push-Location -LiteralPath $env:SYNTHETIC_STAGING_CWD
try {
    & $env:SYNTHETIC_PYTHON -m src.runtime_provenance --write-manifest --runtime-root $env:SYNTHETIC_STAGING_CWD --channel main --commit ('0' * 40)
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $env:SYNTHETIC_PYTHON -m src.runtime_provenance --check --runtime-root $env:SYNTHETIC_STAGING_CWD
    if ($LASTEXITCODE -eq 0) { exit 99 }
    "CHECK_FAILURE=$LASTEXITCODE"
} finally {
    Pop-Location
}
"CALLER_CWD=$((Get-Location).Path)"
""",
            environment=environment,
        )
        assert failure.returncode == 0, failure.stderr
        assert "CHECK_FAILURE=1" in failure.stdout
        assert f"CALLER_CWD={caller_cwd}" in failure.stdout


def test_runtime_installer_rewrites_provenance_after_activation_before_shortcut():
    content = (WIN_TOOLS / "install_runtime_workbench.ps1").read_text(encoding="utf-8")

    activation = "worktree move $StagingRoot $RuntimeRoot"
    runtime_python = "$RuntimePython = Join-Path $RuntimeRoot '.venv\\Scripts\\python.exe'"
    final_manifest = "--write-manifest --runtime-root $RuntimeRoot"
    final_check = "--check --runtime-root $RuntimeRoot"
    shortcut = "if ($CreateShortcut)"

    assert content.index(activation) < content.index(runtime_python)
    assert content.index(runtime_python) < content.index(final_manifest) < content.index(final_check)
    assert content.index(final_check) < content.index(shortcut)


def test_runtime_provenance_manifest_is_refreshed_after_worktree_move():
    if os.name != "nt" or _powershell() is None:
        return
    with tempfile.TemporaryDirectory(dir=ROOT.parent) as temporary_directory:
        root = Path(temporary_directory)
        repo, staging, final = root / "repo", root / "staging", root / "final"
        source = repo / "src"
        source.mkdir(parents=True)
        (repo / ".gitignore").write_text(".venv/\n__pycache__/\n", encoding="utf-8")
        shutil.copyfile(ROOT / "src" / "runtime_provenance.py", source / "runtime_provenance.py")
        for name in ("__init__.py", "cli.py", "workbench.py"):
            (source / name).write_text("", encoding="utf-8")
        def git(*args: str, cwd: Path = repo) -> subprocess.CompletedProcess[str]:
            return subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True)
        git("init")
        git("config", "user.email", "synthetic@example.invalid")
        git("config", "user.name", "Synthetic Runtime")
        git("add", ".")
        git("commit", "-m", "synthetic runtime")
        head = git("rev-parse", "HEAD").stdout.strip()
        git("worktree", "add", "--detach", str(staging), head)
        subprocess.run([sys.executable, "-m", "venv", ".venv"], cwd=staging, check=True)
        staging_python = staging / ".venv" / "Scripts" / "python.exe"
        def provenance(python: Path, root_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([str(python), "-m", "src.runtime_provenance", *arguments], cwd=root_path, text=True, capture_output=True)
        write = provenance(staging_python, staging, "--write-manifest", "--runtime-root", str(staging), "--channel", "main", "--commit", head)
        check = provenance(staging_python, staging, "--check", "--runtime-root", str(staging))
        assert write.returncode == check.returncode == 0
        manifest = Path(git("rev-parse", "--git-path", "sample-brain-runtime.json", cwd=staging).stdout.strip())
        staging_manifest = json.loads(manifest.read_text(encoding="utf-8"))
        assert staging_manifest["runtime_root"] == str(staging)
        assert staging_manifest["python_executable"] == str(staging_python)
        git("worktree", "move", str(staging), str(final))
        final_python = final / ".venv" / "Scripts" / "python.exe"
        assert json.loads(manifest.read_text(encoding="utf-8")) == staging_manifest
        stale = provenance(final_python, final, "--check", "--runtime-root", str(final))
        assert stale.returncode != 0
        final_write = provenance(final_python, final, "--write-manifest", "--runtime-root", str(final), "--channel", "main", "--commit", head)
        final_check = provenance(final_python, final, "--check", "--runtime-root", str(final))
        assert final_write.returncode == final_check.returncode == 0
        final_manifest = Path(git("rev-parse", "--git-path", "sample-brain-runtime.json", cwd=final).stdout.strip())
        value = json.loads(final_manifest.read_text(encoding="utf-8"))
        assert value["runtime_root"] == str(final)
        assert value["python_executable"] == str(final_python)
        assert value["commit"] == head and value["channel"] == "main"


def _git_worktree_lifecycle(
    root: Path, *, with_existing_runtime: bool = True
) -> tuple[Path, Path | None, Path, str, str]:
    repo = root / "repo"
    source = repo / "src"
    source.mkdir(parents=True)
    (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    shutil.copyfile(ROOT / "src" / "runtime_provenance.py", source / "runtime_provenance.py")
    for name in ("__init__.py", "cli.py", "workbench.py"):
        (source / name).write_text("", encoding="utf-8")
    (repo / "runtime-marker.txt").write_text("known-good\n", encoding="utf-8")

    def git(*args: str, cwd: Path = repo) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=cwd, check=True, text=True, capture_output=True
        )

    git("init")
    git("config", "user.email", "synthetic@example.invalid")
    git("config", "user.name", "Synthetic Runtime")
    git("add", ".")
    git("commit", "-m", "known-good runtime")
    known_good_head = git("rev-parse", "HEAD").stdout.strip()
    (repo / "runtime-marker.txt").write_text("candidate\n", encoding="utf-8")
    git("add", "runtime-marker.txt")
    git("commit", "-m", "candidate runtime")
    candidate_head = git("rev-parse", "HEAD").stdout.strip()

    runtime = root / "runtime"
    staging = root / "staging"
    if with_existing_runtime:
        git("worktree", "add", "--detach", str(runtime), known_good_head)
    else:
        runtime = None
    git("worktree", "add", "--detach", str(staging), candidate_head)
    return repo, runtime, staging, known_good_head, candidate_head


def test_runtime_installer_rolls_back_final_provenance_failure():
    content = (WIN_TOOLS / "install_runtime_workbench.ps1").read_text(encoding="utf-8")

    activation = "worktree move $StagingRoot $RuntimeRoot"
    rollback_candidate = "worktree move $RuntimeRoot $StagingRoot"
    rollback_backup = "worktree move $BackupRoot $RuntimeRoot"
    final_manifest = "Could not write final runtime manifest."
    shortcut = "if ($CreateShortcut)"

    assert "$ActivationComplete = $true" in content
    assert rollback_candidate in content
    assert rollback_backup in content
    assert content.index(activation) < content.index(final_manifest) < content.index(
        rollback_candidate
    ) < content.index(shortcut)

    with tempfile.TemporaryDirectory(dir=ROOT.parent) as temporary_directory:
        root = Path(temporary_directory)
        repo, runtime, staging, known_good_head, candidate_head = _git_worktree_lifecycle(root)
        backup = root / "backup"

        def git(*args: str, cwd: Path = repo) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["git", *args], cwd=cwd, check=True, text=True, capture_output=True
            )

        git("worktree", "move", str(runtime), str(backup))
        git("worktree", "move", str(staging), str(runtime))
        failed_check = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.runtime_provenance",
                "--write-manifest",
                "--runtime-root",
                str(runtime),
                "--channel",
                "main",
                "--commit",
                "0" * 40,
            ],
            cwd=runtime,
            check=True,
            text=True,
            capture_output=True,
        )
        assert failed_check.returncode == 0
        final_check = subprocess.run(
            [sys.executable, "-m", "src.runtime_provenance", "--check", "--runtime-root", str(runtime)],
            cwd=runtime,
            text=True,
            capture_output=True,
        )
        assert final_check.returncode != 0

        git("worktree", "move", str(runtime), str(staging))
        git("worktree", "move", str(backup), str(runtime))

        assert (runtime / "runtime-marker.txt").read_text(encoding="utf-8") == "known-good\n"
        assert git("rev-parse", "HEAD", cwd=runtime).stdout.strip() == known_good_head
        assert git("status", "--porcelain", cwd=runtime).stdout == ""
        assert git("rev-parse", "HEAD", cwd=staging).stdout.strip() == candidate_head
        assert not backup.exists()


def test_runtime_installer_rolls_back_fresh_final_provenance_failure():
    with tempfile.TemporaryDirectory(dir=ROOT.parent) as temporary_directory:
        root = Path(temporary_directory)
        repo, existing_runtime, staging, _known_good_head, candidate_head = _git_worktree_lifecycle(
            root, with_existing_runtime=False
        )
        runtime = root / "fresh-runtime"
        assert existing_runtime is None

        def git(*args: str, cwd: Path = repo) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["git", *args], cwd=cwd, check=True, text=True, capture_output=True
            )

        git("worktree", "move", str(staging), str(runtime))
        subprocess.run(
            [
                sys.executable,
                "-m",
                "src.runtime_provenance",
                "--write-manifest",
                "--runtime-root",
                str(runtime),
                "--channel",
                "main",
                "--commit",
                "0" * 40,
            ],
            cwd=runtime,
            check=True,
            capture_output=True,
            text=True,
        )
        final_check = subprocess.run(
            [sys.executable, "-m", "src.runtime_provenance", "--check", "--runtime-root", str(runtime)],
            cwd=runtime,
            text=True,
            capture_output=True,
        )
        assert final_check.returncode != 0

        git("worktree", "move", str(runtime), str(staging))

        assert not runtime.exists()
        assert staging.is_dir()
        assert git("rev-parse", "HEAD", cwd=staging).stdout.strip() == candidate_head
