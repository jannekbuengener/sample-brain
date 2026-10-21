from pathlib import Path

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

# ---------------------------------------------------------------------------
# Session-scoped capture of the "raw" producer state path.
# This is resolved *before* the autouse fixture monkeypatches the environment,
# so it represents the directory pytest would use if it ignored the fixture
# entirely.  The producer workbench library DB derived from it is registered as
# a protected connection target so src can fail-closed before ever opening it.
# ---------------------------------------------------------------------------
from src.workbench_library import (  # noqa: E402
    resolve_workbench_state_dir as _resolve_raw,
    protect_connection_target as _protect_connection_target,
    _LIBRARY_DB_NAME,
)

_PRODUCER_STATE_DIR: Path = _resolve_raw()  # e.g. Path.home() / ".sample-brain"
_protect_connection_target(_PRODUCER_STATE_DIR / _LIBRARY_DB_NAME)


def _get_producer_state_dir() -> Path:
    """Return the captured raw producer state directory (for diagnostics).

    This is a plain helper, not a pytest fixture.  It is never embedded in
    exception text, so no private producer path leaks into error messages.
    """
    return _PRODUCER_STATE_DIR


# ---------------------------------------------------------------------------
# Fail-closed guard: the autouse fixture isolates pytest from the producer
# Workbench state by pointing ``SAMPLE_BRAIN_WORKBENCH_STATE_DIR`` at an
# isolated tmp_path, and asserts that resolution through the normal
# environment path returns the isolated tmp_path rather than the real
# producer directory.  The connection boundary itself is guarded in
# ``src.workbench_library.connect_workbench_library`` (no pytest awareness
# there): any resolved target equal to the captured producer DB raises before
# ``sqlite3.connect`` is ever invoked.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_workbench_state_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Keep every pytest case away from the producer's default Workbench state."""

    # 1. Set up the isolated state directory
    state_dir = tmp_path / "global_workbench_state"
    state_dir.mkdir(parents=True, exist_ok=True)

    # 2. Install the environment variable so that downstream resolver calls
    #    read the isolated path through os.environ (the "normal environment path").
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))

    # 3. Fail-closed check: the resolver, called through its plain environment
    #    path, must return the isolated tmp_path and not the real producer
    #    directory.  If it ever returns the producer path, the assertion fails
    #    and the test never runs -- no DB mutation can occur.
    from src.workbench_library import resolve_workbench_state_dir

    resolved = resolve_workbench_state_dir()  # reads os.environ
    assert resolved == state_dir.resolve(), (
        f"Workbench state isolation broken!  "
        f"Resolver pointed to {resolved}, expected {state_dir.resolve()}."
    )

    return state_dir


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "clap: optional CLAP-backed search quality tests (requires [clap] extra)",
    )
