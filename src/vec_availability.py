from __future__ import annotations

import sqlite3
import sys
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class VecAvailabilityReport:
    available: bool
    reason: str | None
    python_version: str
    sqlite_version: str
    vec_version: str | None
    package_installed: bool
    extension_loaded: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _probe_vec_version(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT vec_version()").fetchone()
    if row is None or row[0] is None:
        raise RuntimeError("vec_version() returned no value")
    return str(row[0])


def _supports_load_extension() -> bool:
    return hasattr(sqlite3.Connection, "enable_load_extension")


def _open_probe_connection() -> sqlite3.Connection:
    return sqlite3.connect(":memory:")


def probe_sqlite_vec() -> VecAvailabilityReport:
    python_version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    sqlite_version = sqlite3.sqlite_version

    try:
        import sqlite_vec  # noqa: F401
    except ImportError:
        return VecAvailabilityReport(
            available=False,
            reason="not_installed",
            python_version=python_version,
            sqlite_version=sqlite_version,
            vec_version=None,
            package_installed=False,
            extension_loaded=False,
        )

    if not _supports_load_extension():
        return VecAvailabilityReport(
            available=False,
            reason="load_extension_disabled",
            python_version=python_version,
            sqlite_version=sqlite_version,
            vec_version=None,
            package_installed=True,
            extension_loaded=False,
        )

    conn = _open_probe_connection()
    try:
        conn.enable_load_extension(True)
        try:
            sqlite_vec.load(conn)
        except Exception:
            return VecAvailabilityReport(
                available=False,
                reason="load_failed",
                python_version=python_version,
                sqlite_version=sqlite_version,
                vec_version=None,
                package_installed=True,
                extension_loaded=False,
            )
        finally:
            conn.enable_load_extension(False)

        try:
            vec_version = _probe_vec_version(conn)
        except Exception:
            return VecAvailabilityReport(
                available=False,
                reason="vec_version_failed",
                python_version=python_version,
                sqlite_version=sqlite_version,
                vec_version=None,
                package_installed=True,
                extension_loaded=True,
            )
    finally:
        conn.close()

    return VecAvailabilityReport(
        available=True,
        reason=None,
        python_version=python_version,
        sqlite_version=sqlite_version,
        vec_version=vec_version,
        package_installed=True,
        extension_loaded=True,
    )


def is_sqlite_vec_available() -> bool:
    return probe_sqlite_vec().available


def format_availability_message(report: VecAvailabilityReport) -> str:
    if report.available:
        return (
            "[OK] sqlite-vec is available "
            f"(vec_version={report.vec_version}, sqlite={report.sqlite_version})"
        )

    messages = {
        "not_installed": (
            "sqlite-vec package is not installed. "
            "Install with: pip install -e .[vec]"
        ),
        "load_extension_disabled": (
            "Python sqlite3 build does not support loadable extensions "
            "(enable_load_extension unavailable)."
        ),
        "load_failed": (
            "sqlite-vec package is installed but the extension failed to load."
        ),
        "vec_version_failed": (
            "sqlite-vec loaded but vec_version() probe failed."
        ),
    }
    detail = messages.get(report.reason or "", report.reason or "unknown error")
    return f"[ERROR] sqlite-vec unavailable: {detail}"
