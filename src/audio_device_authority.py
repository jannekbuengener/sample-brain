"""Single Audio Device Authority for Sample Brain playback routing (#1345/#1346/#1356).

Browser / Loop / Kit / Sequencer must not choose physical devices. They consume
playback intent only. This module resolves:

    preferred preference → live enumeration → opened engine device

and reports whether those identities still match.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class AudioDeviceRoute:
    """Authoritative route snapshot for UI + diagnostics."""

    audio_system: str
    requested_device_id: str
    requested_device_name: str
    resolved_device_id: str
    resolved_device_name: str
    opened_device_id: str
    opened_device_name: str
    opened_backend: str
    uses_os_default: bool
    ui_matches_opened: bool
    divergence: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "audio_system": self.audio_system,
            "requested_device_id": self.requested_device_id,
            "requested_device_name": self.requested_device_name,
            "resolved_device_id": self.resolved_device_id,
            "resolved_device_name": self.resolved_device_name,
            "opened_device_id": self.opened_device_id,
            "opened_device_name": self.opened_device_name,
            "opened_backend": self.opened_backend,
            "uses_os_default": self.uses_os_default,
            "ui_matches_opened": self.ui_matches_opened,
            "divergence": self.divergence,
        }


def _device_name(devices: Sequence[Mapping[str, Any]], device_id: str) -> str:
    if not device_id:
        return ""
    for item in devices:
        if str(item.get("id_hex") or item.get("id") or "") == device_id:
            return str(item.get("name") or "").strip()
    return ""


def _default_device(devices: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    for item in devices:
        if bool(item.get("is_default")):
            return (
                str(item.get("id_hex") or item.get("id") or ""),
                str(item.get("name") or "").strip(),
            )
    if devices:
        first = devices[0]
        return (
            str(first.get("id_hex") or first.get("id") or ""),
            str(first.get("name") or "").strip(),
        )
    return "", ""


def resolve_audio_output_route(
    *,
    preferred_id: str,
    preferred_name: str = "",
    enumerated: Sequence[Mapping[str, Any]],
    opened_device_id: str | None,
    opened_device_name: str = "",
    audio_system: str = "sample_brain_audio",
    opened_backend: str = "wasapi",
) -> AudioDeviceRoute:
    """Resolve requested/resolved/opened identities and divergence classification."""
    requested_id = str(preferred_id or "").strip()
    requested_name = str(preferred_name or "").strip()
    default_id, default_name = _default_device(enumerated)
    uses_os_default = not requested_id

    if uses_os_default:
        resolved_id = default_id
        resolved_name = default_name or "System default"
        requested_name = requested_name or f"System default ({resolved_name})" if resolved_name else "System default"
    else:
        resolved_id = requested_id
        resolved_name = _device_name(enumerated, requested_id) or requested_name or "Selected device"

    opened_id = "" if opened_device_id is None else str(opened_device_id).strip()
    if not opened_id and uses_os_default:
        # Native open with NULL follows OS default; treat resolved default as opened.
        opened_id = resolved_id
    opened_name = str(opened_device_name or "").strip()
    if not opened_name:
        opened_name = _device_name(enumerated, opened_id) if opened_id else ""
    if not opened_name and opened_id and opened_id == resolved_id:
        opened_name = resolved_name

    divergence = ""
    listed = bool(requested_id and _device_name(enumerated, requested_id))
    if opened_id and resolved_id and opened_id != resolved_id:
        divergence = "opened_mismatch"
    elif requested_id and not listed:
        if opened_id == requested_id:
            # Preference is open; listing may be stale (e.g. Vendor ASIO CLSID
            # vs WASAPI-only enum) without implying physical loss (#1350/#1351).
            divergence = ""
        else:
            divergence = "preferred_unavailable"
    elif not enumerated and not opened_id:
        divergence = "enumeration_empty"

    ui_matches_opened = (not divergence) and (
        (uses_os_default and (not opened_id or opened_id == resolved_id))
        or (not uses_os_default and opened_id == requested_id)
    )

    return AudioDeviceRoute(
        audio_system=audio_system,
        requested_device_id=requested_id,
        requested_device_name=requested_name or resolved_name,
        resolved_device_id=resolved_id,
        resolved_device_name=resolved_name,
        opened_device_id=opened_id,
        opened_device_name=opened_name or resolved_name,
        opened_backend=opened_backend,
        uses_os_default=uses_os_default,
        ui_matches_opened=ui_matches_opened,
        divergence=divergence,
    )


def build_output_device_choices(
    enumerated: Sequence[Mapping[str, Any]],
    *,
    preferred_id: str = "",
    preferred_name: str = "",
) -> list[dict[str, Any]]:
    """UI device list: System default (resolved name) + enumerated + unavailable preferred."""
    default_id, default_name = _default_device(enumerated)
    default_label = (
        f"System default ({default_name})" if default_name else "System default"
    )
    devices: list[dict[str, Any]] = [
        {
            "id": "",
            "name": default_label,
            "is_default": True,
            "resolved_default_id": default_id,
            "resolved_default_name": default_name,
        }
    ]
    seen_ids = {""}
    for item in enumerated:
        device_id = str(item.get("id_hex") or item.get("id") or "")
        name = str(item.get("name") or "").strip() or "Unnamed device"
        if len(device_id) != 512:
            continue
        devices.append(
            {
                "id": device_id,
                "name": name,
                "is_default": bool(item.get("is_default")),
            }
        )
        seen_ids.add(device_id)

    preferred = str(preferred_id or "").strip()
    if preferred and preferred not in seen_ids:
        label = str(preferred_name or "").strip() or "Selected device"
        devices.append(
            {
                "id": preferred,
                "name": f"{label} (unavailable)",
                "is_default": False,
                "unavailable": True,
            }
        )
    return devices


def preferred_device_index(
    devices: Sequence[Mapping[str, Any]],
    preferred_id: str,
) -> int:
    """Index of preferred id in choices. Never lies as System default when preferred set."""
    preferred = str(preferred_id or "").strip()
    for index, item in enumerate(devices):
        if str(item.get("id") or "") == preferred:
            return int(index)
    if preferred:
        # Should be unreachable when build_output_device_choices appended unavailable.
        for index, item in enumerate(devices):
            if item.get("unavailable") is True:
                return int(index)
        return -1
    return 0


__all__ = [
    "AudioDeviceRoute",
    "build_output_device_choices",
    "preferred_device_index",
    "resolve_audio_output_route",
]
