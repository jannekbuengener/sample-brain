"""Enumerate installed manufacturer ASIO drivers (#1350).

Discovery only — does not open ASIO or create a second playback engine.
Filters out known wrapper/virtual drivers (ASIO4ALL, generic FL wrappers when
they are not manufacturer hardware drivers).
"""

from __future__ import annotations

import sys
from typing import Any


_EXCLUDED_NAME_FRAGMENTS = (
    "asio4all",
    "asio 4 all",
    "generic low latency",
    "fl studio asio",  # virtual wrapper, not a manufacturer hardware driver
)


def _is_excluded_driver_name(name: str) -> bool:
    lowered = name.casefold()
    return any(fragment in lowered for fragment in _EXCLUDED_NAME_FRAGMENTS)


def enumerate_vendor_asio_drivers() -> list[dict[str, Any]]:
    """Return unique installed ASIO drivers from HKLM SOFTWARE\\ASIO hives."""
    if sys.platform != "win32":
        return []
    import winreg

    hives = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\ASIO"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\ASIO"),
    )
    seen_clsids: set[str] = set()
    drivers: list[dict[str, Any]] = []
    for root, path in hives:
        try:
            key = winreg.OpenKey(root, path)
        except OSError:
            continue
        index = 0
        while True:
            try:
                name = winreg.EnumKey(key, index)
            except OSError:
                break
            index += 1
            if _is_excluded_driver_name(name):
                continue
            clsid = ""
            try:
                sub = winreg.OpenKey(key, name)
                try:
                    clsid = str(winreg.QueryValueEx(sub, "CLSID")[0] or "")
                finally:
                    winreg.CloseKey(sub)
            except OSError:
                clsid = ""
            clsid_key = clsid.casefold() or name.casefold()
            if clsid_key in seen_clsids:
                continue
            seen_clsids.add(clsid_key)
            drivers.append(
                {
                    "id": clsid or name,
                    "name": name,
                    "clsid": clsid,
                    "unavailable": False,
                }
            )
        winreg.CloseKey(key)
    drivers.sort(key=lambda item: str(item.get("name") or "").casefold())
    return drivers


__all__ = ["enumerate_vendor_asio_drivers"]
