"""BUILDINFO rendering and hygiene checks for the #729 Windows distributable."""

from __future__ import annotations

import re
from collections.abc import Mapping

# Absolute Windows / UNC / POSIX rooted paths must not appear in shipped BUILDINFO.
_ABS_PATH_RE = re.compile(
    r"(?i)(?:^[A-Z]:\\|/home/|/Users/|\\\\[^\\\s]+\\|[A-Z]:/)"
)
_DRIVE_INLINE_RE = re.compile(r"(?i)(?:^|[\s=])[A-Z]:\\")


def validate_buildinfo_hygiene(text: str) -> None:
    """Raise ValueError if BUILDINFO text embeds machine-local absolute paths."""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _ABS_PATH_RE.search(stripped) or _DRIVE_INLINE_RE.search(stripped):
            raise ValueError(f"BUILDINFO must not embed absolute paths: {stripped!r}")


def format_buildinfo(fields: Mapping[str, str]) -> str:
    """Format BUILDINFO as key=value lines and enforce path hygiene."""
    lines = [f"{key}={value}" for key, value in fields.items()]
    text = "\n".join(lines) + "\n"
    validate_buildinfo_hygiene(text)
    return text


def default_pilot_buildinfo_fields(
    *,
    build_id: str,
    source_sha: str,
    python: str,
    pyside6: str,
    qt: str,
    pyinstaller: str,
    nuitka: str,
    artifact_zip: str,
) -> dict[str, str]:
    """Canonical BUILDINFO keys for the Screen-1 pilot portable ZIP."""
    return {
        "product": "SampleBrain Screen 1 Pilot",
        "delivery": "PORTABLE_STANDALONE_ZIP",
        "build_id": build_id,
        "source_sha": source_sha,
        "python": python,
        "pyside6": pyside6,
        "qt": qt,
        "pyinstaller": pyinstaller,
        "nuitka": nuitka,
        "packager": (
            "pyside6-deploy dry-run -> Nuitka BLOCKED (librosa/lazy_loader) "
            "-> PyInstaller onedir fallback"
        ),
        "nuitka_blocker_evidence": f"nuitka-blocker-{build_id}.txt",
        "native_audio_dll": "samplebrain_audio.dll",
        "native_audio_source": "native/audio/build/bin/Release/samplebrain_audio.dll",
        "native_audio_dumpbin_evidence": f"dumpbin-samplebrain_audio-{build_id}.txt",
        "signing": "unsigned (pilot); SmartScreen may warn - More info / Run anyway",
        "artifact_zip": artifact_zip,
    }
