from __future__ import annotations

import sqlite3
import sys
from types import SimpleNamespace

import pytest

from src.vec_availability import (
    format_availability_message,
    is_sqlite_vec_available,
    probe_sqlite_vec,
)


def test_probe_reports_python_and_sqlite_versions():
    report = probe_sqlite_vec()
    assert report.python_version.startswith(f"{sys.version_info.major}.")
    assert report.sqlite_version == sqlite3.sqlite_version


def test_not_installed_when_import_fails(monkeypatch: pytest.MonkeyPatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sqlite_vec":
            raise ImportError("no sqlite_vec")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    report = probe_sqlite_vec()
    assert report.available is False
    assert report.reason == "not_installed"
    assert report.package_installed is False
    assert "pip install -e .[vec]" in format_availability_message(report)


def test_load_extension_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, "sqlite_vec", SimpleNamespace(load=lambda conn: None))
    monkeypatch.setattr(
        "src.vec_availability._supports_load_extension",
        lambda: False,
    )
    report = probe_sqlite_vec()
    assert report.available is False
    assert report.reason == "load_extension_disabled"
    assert report.package_installed is True


def test_load_failed(monkeypatch: pytest.MonkeyPatch):
    def failing_load(conn):
        raise OSError("extension load failed")

    monkeypatch.setitem(sys.modules, "sqlite_vec", SimpleNamespace(load=failing_load))
    report = probe_sqlite_vec()
    assert report.available is False
    assert report.reason == "load_failed"
    assert report.package_installed is True


def test_vec_version_failed(monkeypatch: pytest.MonkeyPatch):
    class BrokenConn:
        def enable_load_extension(self, _enabled):
            return None

        def execute(self, _sql):
            raise sqlite3.OperationalError("no vec_version")

        def close(self):
            return None

    monkeypatch.setitem(sys.modules, "sqlite_vec", SimpleNamespace(load=lambda conn: None))
    monkeypatch.setattr(
        "src.vec_availability._open_probe_connection",
        lambda: BrokenConn(),
    )
    report = probe_sqlite_vec()
    assert report.available is False
    assert report.reason == "vec_version_failed"
    assert report.extension_loaded is True


@pytest.mark.skipif(
    not is_sqlite_vec_available(),
    reason="sqlite-vec optional extra not installed in this environment",
)
def test_probe_available_when_extension_loads():
    report = probe_sqlite_vec()
    assert report.available is True
    assert report.reason is None
    assert report.vec_version
    assert report.package_installed is True
    assert report.extension_loaded is True
    assert "[OK]" in format_availability_message(report)
