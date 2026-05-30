from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_config_snippet(env: dict[str, str], code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_default_db_path_when_env_unset():
    env = os.environ.copy()
    env.pop("SAMPLE_BRAIN_DB_PATH", None)
    result = _run_config_snippet(
        env,
        """
from src.config import DB_PATH, DATA_DIR
assert DB_PATH == DATA_DIR / "catalog.db"
print("OK")
""",
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_sample_brain_db_path_override_creates_db(tmp_path: Path):
    db_path = tmp_path / "nested" / "catalog.db"
    env = os.environ.copy()
    env["SAMPLE_BRAIN_DB_PATH"] = str(db_path)
    result = _run_config_snippet(
        env,
        """
import os
from pathlib import Path
expected = Path(os.environ["SAMPLE_BRAIN_DB_PATH"]).expanduser().resolve()
from src.config import DB_PATH
from src.db import init_db
assert DB_PATH == expected
init_db()
assert expected.exists()
print("OK")
""",
    )
    assert result.returncode == 0, result.stderr or result.stdout
