# name=SB Workflow Observer
# url=
# version 1.0.0
"""
#1321 durable FL MIDI scripting observer — read-only signal capture.

Install (Windows): tools/fl_workflow_recorder/install.ps1

Writes ONLY under:
  %LOCALAPPDATA%\\sample-brain\\workflow-observer\\spool\\fl-events.jsonl
  %LOCALAPPDATA%\\sample-brain\\workflow-observer\\fl-recorder-meta.json

Never calls playlist.selectTool for observation. Never mutates transport/project for observation.
Proven MIDI pairing: IN "Sample Brain Observer" / OUT "Sample Brain Observer Out" / port 240.
"""

from __future__ import annotations

import json
import os
import time
import traceback

import general
import midi
import transport
import ui

_LOCALAPPDATA = os.environ.get("LOCALAPPDATA") or os.path.join(
    os.path.expanduser("~"), "AppData", "Local"
)
ROOT_DIR = os.path.join(_LOCALAPPDATA, "sample-brain", "workflow-observer")
SPOOL_DIR = os.path.join(ROOT_DIR, "spool")
FL_EVENTS_PATH = os.path.join(SPOOL_DIR, "fl-events.jsonl")
META_PATH = os.path.join(ROOT_DIR, "fl-recorder-meta.json")
LOG_PATH = os.path.join(ROOT_DIR, "logs", "fl-script.log")

_seq = 0
_subscribed_dirty = True
_dirty_channels = []
_dirty_mixer = []
_last = {
    "focus_surface": None,
    "focus_form_caption": None,
    "focus_form_id": None,
    "focus_plugin": None,
    "hint": None,
    "playing": None,
    "undo_last": None,
    "undo_count": None,
    "undo_pos": None,
    "undo_level_hint": None,
}
_idle_samples = 0
_idle_last_mono = None
_idle_intervals_ms = []
_oninit_count = 0
_ondeinit_count = 0


def _ensure_spool():
    try:
        os.makedirs(SPOOL_DIR, exist_ok=True)
        os.makedirs(os.path.join(ROOT_DIR, "logs"), exist_ok=True)
    except Exception:
        pass


def _bp(path):
    if isinstance(path, bytes):
        return path
    return str(path).encode("utf-8")


def _append_bytes(path, data_bytes):
    try:
        with open(_bp(path), "ab") as fh:
            fh.write(data_bytes)
        return True
    except Exception:
        try:
            fd = os.open(_bp(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND)
            try:
                os.write(fd, data_bytes)
            finally:
                os.close(fd)
            return True
        except Exception:
            return False


def _write_bytes(path, data_bytes):
    try:
        with open(_bp(path), "wb") as fh:
            fh.write(data_bytes)
        return True
    except Exception:
        try:
            fd = os.open(_bp(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
            try:
                os.write(fd, data_bytes)
            finally:
                os.close(fd)
            return True
        except Exception:
            return False


def _log(msg):
    line = ("%s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), msg)).encode(
        "utf-8"
    )
    _append_bytes(LOG_PATH, line)


def _utc_from_wall_ns(wall_ns):
    sec = wall_ns // 1_000_000_000
    ms = (wall_ns % 1_000_000_000) // 1_000_000
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(sec)) + (".%03dZ" % ms)


def _emit(event_type, props=None):
    global _seq
    _seq += 1
    wall_ns = time.time_ns()
    mono_ns = time.monotonic_ns()
    evt = {
        "schema": "sb.fl_workflow_recorder.event.v1",
        "seq": _seq,
        "t_mono_ns": mono_ns,
        "t_wall_ns": wall_ns,
        "t_utc": _utc_from_wall_ns(wall_ns),
        "source": "fl",
        "type": event_type,
        "props": props or {},
    }
    line = (json.dumps(evt, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
    if not _append_bytes(FL_EVENTS_PATH, line):
        _log("WARN emit failed type=%s" % event_type)


def _safe_call(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _detect_versions():
    fl_version = None
    midi_api = None
    for mode in (5, 4, 6):
        try:
            fl_version = ui.getVersion(mode)
            if fl_version is not None:
                break
        except Exception:
            continue
    if fl_version is None:
        fl_version = _safe_call(ui.getProgTitle, None)
    try:
        midi_api = general.getVersion()
    except Exception:
        midi_api = None
    return fl_version, midi_api


def _focus_surface():
    checks = (
        ("Mixer", 0),
        ("ChannelRack", 1),
        ("Playlist", 2),
        ("PianoRoll", 3),
        ("Browser", 4),
        ("Plugin", 5),
        ("PluginEffect", 6),
        ("PluginGenerator", 7),
    )
    focused = []
    for name, idx in checks:
        try:
            if ui.getFocused(idx):
                focused.append(name)
        except Exception:
            pass
    if not focused:
        return "None"
    for pref in (
        "PluginGenerator",
        "PluginEffect",
        "Plugin",
        "Playlist",
        "PianoRoll",
        "ChannelRack",
        "Mixer",
        "Browser",
    ):
        if pref in focused:
            return pref
    return focused[0]


def _write_meta(extra=None):
    fl_version, midi_api = _detect_versions()
    meta = {
        "schema": "sb.fl_workflow_recorder.fl_meta.v1",
        "FL_VERSION": fl_version,
        "MIDI_SCRIPT_API_VERSION": midi_api,
        "spool_role": "fl-events.jsonl",
        "oninit_count": _oninit_count,
        "ondeinit_count": _ondeinit_count,
        "idle_samples": _idle_samples,
        "updated_t_wall_ns": time.time_ns(),
        "updated_t_utc": _utc_from_wall_ns(time.time_ns()),
    }
    if extra:
        meta.update(extra)
    _write_bytes(META_PATH, (json.dumps(meta, indent=2) + "\n").encode("utf-8"))


def OnInit():
    global _oninit_count, _seq, _idle_samples, _idle_last_mono, _idle_intervals_ms
    _ensure_spool()
    _oninit_count += 1
    _seq = 0
    _idle_samples = 0
    _idle_last_mono = None
    _idle_intervals_ms = []
    fl_version, midi_api = _detect_versions()
    _write_meta({"status": "ON_INIT"})
    _emit(
        "RECORDER_INIT",
        {
            "FL_VERSION": fl_version,
            "MIDI_SCRIPT_API_VERSION": midi_api,
            "oninit_count": _oninit_count,
        },
    )
    _emit("CLOCK_MARKER", {"marker": "fl_init", "pair_hint": "align_with_win"})
    _log("OnInit FL_VERSION=%r MIDI_SCRIPT_API_VERSION=%r" % (fl_version, midi_api))


def OnDeInit():
    global _ondeinit_count
    _ondeinit_count += 1
    _emit("RECORDER_DEINIT", {"ondeinit_count": _ondeinit_count})
    _write_meta({"status": "ON_DEINIT"})
    _log("OnDeInit count=%s" % _ondeinit_count)


def OnDirtyChannel(index, flag=0):
    if not _subscribed_dirty:
        return
    try:
        flag_name = None
        for name in ("CE_New", "CE_Delete", "CE_Replace", "CE_Rename", "CE_Select"):
            if hasattr(midi, name) and getattr(midi, name) == flag:
                flag_name = name
                break
        _dirty_channels.append(
            {"index": index, "flag": flag, "flag_name": flag_name or ("CE_%s" % flag)}
        )
    except Exception:
        _dirty_channels.append({"index": index, "flag": flag})


def OnDirtyMixerTrack(index):
    if not _subscribed_dirty:
        return
    _dirty_mixer.append({"index": index})


def OnRefresh(flags):
    props = {"flags": flags}
    if _dirty_channels:
        props["dirty_channels"] = list(_dirty_channels)
        del _dirty_channels[:]
    if _dirty_mixer:
        props["dirty_mixer"] = list(_dirty_mixer)
        del _dirty_mixer[:]
    _emit("REFRESH", props)
    if props.get("dirty_channels"):
        _emit("DIRTY_CHANNEL", {"items": props["dirty_channels"], "via": "OnRefresh"})
    if props.get("dirty_mixer"):
        _emit("DIRTY_MIXER", {"items": props["dirty_mixer"], "via": "OnRefresh"})


def OnUpdateBeatIndicator(value):
    _emit("BEAT_INDICATOR", {"value": value})


def OnIdle():
    global _idle_samples, _idle_last_mono
    now_mono = time.monotonic_ns()
    if _idle_last_mono is not None:
        dt_ms = (now_mono - _idle_last_mono) / 1_000_000.0
        if len(_idle_intervals_ms) < 400:
            _idle_intervals_ms.append(dt_ms)
        if _idle_samples % 100 == 0 and _idle_samples > 0:
            sample = sorted(_idle_intervals_ms)
            if sample:
                p50 = sample[len(sample) // 2]
                _emit("IDLE_STATS", {"n": len(sample), "p50_ms": round(p50, 2)})
    _idle_last_mono = now_mono
    _idle_samples += 1

    try:
        surface = _focus_surface()
        caption = _safe_call(ui.getFocusedFormCaption, "")
        form_id = _safe_call(ui.getFocusedFormID, None)
        plugin = _safe_call(ui.getFocusedPluginName, "")
        hint = _safe_call(ui.getHintMsg, "")
        playing = bool(_safe_call(transport.isPlaying, False))
        undo_last = _safe_call(general.getUndoHistoryLast, None)
        undo_count = _safe_call(general.getUndoHistoryCount, None)
        undo_pos = _safe_call(general.getUndoHistoryPos, None)
        undo_level = _safe_call(general.getUndoLevelHint, None)

        if surface != _last["focus_surface"]:
            _emit(
                "FOCUS_SURFACE",
                {
                    "surface": surface,
                    "prev": _last["focus_surface"],
                    "caption": caption,
                    "form_id": form_id,
                    "plugin": plugin,
                },
            )
            _last["focus_surface"] = surface
        if caption != _last["focus_form_caption"] or form_id != _last["focus_form_id"]:
            _emit(
                "FOCUS_FORM",
                {"caption": caption, "form_id": form_id, "plugin": plugin, "surface": surface},
            )
            _last["focus_form_caption"] = caption
            _last["focus_form_id"] = form_id
        if plugin != _last["focus_plugin"]:
            _emit("FOCUS_PLUGIN", {"plugin": plugin, "surface": surface, "caption": caption})
            _last["focus_plugin"] = plugin
        if hint != _last["hint"]:
            _emit("HINT", {"text": hint, "surface": surface})
            _last["hint"] = hint
        if playing != _last["playing"]:
            _emit(
                "TRANSPORT",
                {
                    "playing": playing,
                    "prev": _last["playing"],
                    "event": "PLAY" if playing else "STOP",
                },
            )
            _last["playing"] = playing
        if (
            undo_last != _last["undo_last"]
            or undo_count != _last["undo_count"]
            or undo_pos != _last["undo_pos"]
            or undo_level != _last["undo_level_hint"]
        ):
            _emit(
                "UNDO",
                {
                    "undo_last": undo_last,
                    "undo_count": undo_count,
                    "undo_pos": undo_pos,
                    "undo_level_hint": undo_level,
                    "hint": hint,
                },
            )
            _last["undo_last"] = undo_last
            _last["undo_count"] = undo_count
            _last["undo_pos"] = undo_pos
            _last["undo_level_hint"] = undo_level
    except Exception:
        _log("OnIdle error: %s" % traceback.format_exc().splitlines()[-1:])

    if _idle_samples in (50, 200, 500) or (_idle_samples > 0 and _idle_samples % 1000 == 0):
        _emit("CLOCK_MARKER", {"marker": "fl_idle", "idle_samples": _idle_samples})
        _write_meta({"status": "RUNNING", "idle_samples": _idle_samples})
