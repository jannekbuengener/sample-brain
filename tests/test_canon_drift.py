from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_canon_drift.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_canon_drift", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canon_frontdoor_has_no_deterministic_drift() -> None:
    checker = _load_checker()
    assert checker.collect_canon_drift() == []


def test_canon_checker_cli_contract_is_import_safe() -> None:
    checker = _load_checker()
    assert checker.main() == 0
