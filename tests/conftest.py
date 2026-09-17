from pathlib import Path

import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(autouse=True)
def isolated_workbench_state_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Keep every pytest case away from the producer's default Workbench state."""
    state_dir = tmp_path / "global_workbench_state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    return state_dir


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "clap: optional CLAP-backed search quality tests (requires [clap] extra)",
    )
