"""TEST_GATE / TEST FREEZE — #936 user-channel classification authority.

Canonical authority:
- docs/USER_CHANNEL_CLASSIFICATION_AUTHORITY.md (architecture outcome
  ``USER_CHANNEL_CLASSIFICATION_RESOLVER_INJECTED``)
- docs/LOOP_ROW_PLAYBACK_CONTRACT.md (#920 / #926 playback owners)
- docs/SESSION_OWNERSHIP_CONTRACT.md
- Issue #936

This file is the contract-slice validation for the architecture freeze. It pins
only ownership invariants that are checkable before any runtime implementation
exists. Guards 1-5 are green on current ``main`` and must never be weakened.

Frozen ownership rules asserted here:

1. Low-level Rack / audio modules own no SQLite, library, or config I/O.
2. Session JSON stays path-only; no ``sample_class`` is ever persisted.
3. Pattern Core ``Channel`` / ``Trigger`` shapes are unchanged.
4. No filename/folder heuristic can produce classification.
5. Without an injected binding, user channels stay ``ambiguous`` and fail
   closed on both #926 playback owners.

Implementation-slice tests (resolver present, invalidation, reconcile,
observer semantics, gesture reuse) belong to the follow-up slice and are
intentionally absent here.
"""

from __future__ import annotations

import ast
import json
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from src.channel_rack import (
    ChannelRackState,
    classification_kind,
    point_trigger_eligible_channel_ids,
    sample_class_for_channel,
)
from src.loop_rack_playback import build_loop_cycle_specs
from src.pattern_core import Channel, Pattern, Trigger
from src.workbench_live_kit import LiveKitState
from src.workbench_session import compose_workbench_session

REPO_ROOT = Path(__file__).resolve().parents[1]

# Modules that must never gain SQLite / library / config I/O capability.
FORBIDDEN_IO_MODULES = (
    "src/channel_rack.py",
    "src/loop_rack_playback.py",
    "src/workbench_channel_rack.py",
    "src/sequencer_playback.py",
    "src/pattern_core.py",
)

FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "sqlite3",
        "workbench_library",
        "db",
        "config",
        "config_loader",
    }
)


def _imported_module_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.add(node.module.split(".")[0])
            if node.level and node.module is None:
                for alias in node.names:
                    roots.add(alias.name.split(".")[0])
    return roots


@pytest.mark.parametrize("relative", FORBIDDEN_IO_MODULES)
def test_low_level_rack_modules_import_no_sqlite_library_or_config(relative: str) -> None:
    """Rule 1: the Rack/audio layer must stay I/O-free (#936 §2)."""
    roots = _imported_module_roots(REPO_ROOT / relative)
    leaked = sorted(roots & FORBIDDEN_IMPORT_ROOTS)
    assert leaked == [], (
        f"{relative} must not import SQLite/library/config authority: {leaked}"
    )


def _user_channel(channel_id: str, sample_path: str) -> Channel:
    return Channel(
        channel_id=channel_id,
        live_kit_group=None,
        live_kit_slot=None,
        sample_path=sample_path,
    )


def _user_state(channel: Channel) -> ChannelRackState:
    return ChannelRackState(
        channels=(channel,),
        pattern=Pattern(
            pattern_id="screen2-main",
            length_quarter_notes=Fraction(4, 1),
            triggers=(Trigger(channel_id=channel.channel_id, position=Fraction(0, 1)),),
        ),
        step_count=16,
    )


def test_session_json_never_persists_sample_class(tmp_path: Path) -> None:
    """Rule 2: durable identity stays path-only; no copied classification."""
    session = compose_workbench_session(state_dir=tmp_path / "state")
    try:
        session.channel_rack.ensure_state(notify=False)
        state = session.channel_rack.add_user_channel()
        user_id = next(
            channel.channel_id
            for channel in state.channels
            if channel.live_kit_group is None and channel.live_kit_slot is None
        )
        session.channel_rack.assign_user_channel_sample(
            user_id, str(tmp_path / "synthetic" / "kick.wav")
        )
    finally:
        session.transport.close()

    payload: Any = json.loads(
        (tmp_path / "state" / "workbench_session.json").read_text(encoding="utf-8")
    )

    found: list[str] = []

    def _walk(node: Any, trail: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if "sample_class" in str(key):
                    found.append(f"{trail}.{key}")
                _walk(value, f"{trail}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                _walk(value, f"{trail}[{index}]")

    _walk(payload, "$")
    assert found == [], f"persisted classification duplicate found: {found}"


def test_pattern_core_channel_and_trigger_shapes_are_frozen() -> None:
    """Rule 3: Pattern Core keeps no classification/BPM field (#936 §1)."""
    import dataclasses

    assert tuple(f.name for f in dataclasses.fields(Channel)) == (
        "channel_id",
        "live_kit_group",
        "live_kit_slot",
        "sample_path",
    )
    assert tuple(f.name for f in dataclasses.fields(Trigger)) == (
        "channel_id",
        "position",
    )


def test_user_channel_classification_ignores_filename_and_folder_text() -> None:
    """Rule 4: no filename / folder heuristic may produce a class."""
    kit = LiveKitState()
    for channel_id, path in (
        ("ch_user_1", "C:/Loops/Drum_Loop_120bpm_Oneshot/Kick_Loop.wav"),
        ("ch_user_2", "/samples/LOOP/oneshot_pad.wav"),
        ("ch_user_3", "loop.wav"),
    ):
        channel = _user_channel(channel_id, path)
        assert sample_class_for_channel(channel, kit) is None
        assert classification_kind(sample_class_for_channel(channel, kit)) == "ambiguous"


def test_user_channel_without_binding_is_excluded_from_both_playback_paths() -> None:
    """Rule 5: no injected binding means ambiguous and fail-closed (#926)."""
    channel = _user_channel("ch_user_1", "synthetic/user.wav")
    state = _user_state(channel)
    kit = LiveKitState()

    assert channel.channel_id not in point_trigger_eligible_channel_ids(state, kit)

    specs = build_loop_cycle_specs(
        state=state,
        live_kit=kit,
        pcm_for_path=lambda _path: None,
        play_anchor_engine_frame=0,
        sync_enabled=False,
        master_bpm=120.0,
    )
    assert specs == ()

    # Persisted triggers are preserved; only playback is gated.
    assert state.pattern.triggers == (
        Trigger(channel_id=channel.channel_id, position=Fraction(0, 1)),
    )
