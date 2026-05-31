import pytest

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "clap: optional CLAP-backed search quality tests (requires [clap] extra)",
    )
