"""Diagnose virtual MIDI observer ports without mutating devices."""

from __future__ import annotations

import sys
from dataclasses import dataclass


OBSERVER_IN_NAME = "Sample Brain Observer"
OBSERVER_OUT_NAME = "Sample Brain Observer Out"


@dataclass
class MidiHealth:
    available: bool
    input_count: int = 0
    output_count: int = 0
    observer_in_present: bool = False
    observer_out_present: bool = False
    detail: str = ""


def probe_midi_ports() -> MidiHealth:
    if sys.platform != "win32":
        return MidiHealth(available=False, detail="not_windows")
    try:
        import ctypes
        from ctypes import wintypes

        winmm = ctypes.windll.winmm

        class MIDIINCAPS(ctypes.Structure):
            _fields_ = [
                ("wMid", wintypes.WORD),
                ("wPid", wintypes.WORD),
                ("vDriverVersion", wintypes.DWORD),
                ("szPname", wintypes.WCHAR * 32),
                ("dwSupport", wintypes.DWORD),
            ]

        class MIDIOUTCAPS(ctypes.Structure):
            _fields_ = [
                ("wMid", wintypes.WORD),
                ("wPid", wintypes.WORD),
                ("vDriverVersion", wintypes.DWORD),
                ("szPname", wintypes.WCHAR * 32),
                ("wTechnology", wintypes.WORD),
                ("wVoices", wintypes.WORD),
                ("wNotes", wintypes.WORD),
                ("wChannelMask", wintypes.WORD),
                ("dwSupport", wintypes.DWORD),
            ]

        in_n = int(winmm.midiInGetNumDevs())
        out_n = int(winmm.midiOutGetNumDevs())
        in_names: list[str] = []
        out_names: list[str] = []
        caps_in = MIDIINCAPS()
        for i in range(in_n):
            if winmm.midiInGetDevCapsW(i, ctypes.byref(caps_in), ctypes.sizeof(caps_in)) == 0:
                in_names.append(caps_in.szPname)
        caps_out = MIDIOUTCAPS()
        for i in range(out_n):
            if winmm.midiOutGetDevCapsW(i, ctypes.byref(caps_out), ctypes.sizeof(caps_out)) == 0:
                out_names.append(caps_out.szPname)
        obs_in = any(OBSERVER_IN_NAME.lower() in n.lower() for n in in_names)
        obs_out = any(OBSERVER_OUT_NAME.lower() in n.lower() for n in out_names)
        detail = "ok" if obs_in and obs_out else "observer_port_missing"
        return MidiHealth(
            available=True,
            input_count=in_n,
            output_count=out_n,
            observer_in_present=obs_in,
            observer_out_present=obs_out,
            detail=detail,
        )
    except Exception as exc:
        return MidiHealth(available=False, detail=type(exc).__name__)
