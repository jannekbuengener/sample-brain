"""TEST_GATE / TEST_FREEZE — Workbench musical session persistence (#809 / #818 / #819).

Canonical authority:
- docs/SESSION_OWNERSHIP_CONTRACT.md
- docs/DATA_AND_ARTIFACT_POLICY.md
- docs/PATTERN_CORE_CONTRACT.md
- Issue #809 / #817 / #818 / #819

Frozen product rules:
- versioned local JSON under workbench_state_dir (workbench_session.json)
- Live Kit path refs + Channel Rack channels/triggers + MASTER BPM + SYNC
- schema writer = v2; reader accepts v1 (default MASTER + SYNC off) and v2
- all-or-nothing fail-closed restore
- no autosave callbacks during restore
- edited triggers are authority (no DEFAULT_ON re-seed on restore)
- playback/loop runtime never persisted; restore is quiet/stopped
- resume MASTER prefers pending tempo target when scheduled
- Python-owned persistence_status honesty codes (#819); no private paths in status
"""

from __future__ import annotations

import json
import math
import os
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from src.channel_rack import toggle_step
from src.pattern_core import CHANNEL_ID_BY_LIVE_KIT_SLOT, allocate_user_channel_id
from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitState
from src.workbench_session import compose_workbench_session
from src.workbench_transport_ui import DEFAULT_TEMPO_BPM


def _row(name: str, path: str) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=Path(path).name,
        path=path,
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class=None,
        pred_type=None,
        status="ok",
        details={},
    )


def _session_path(state_dir: Path) -> Path:
    from src.workbench_session_store import workbench_session_path

    return workbench_session_path(state_dir=state_dir)


def _triggers_for(state, channel_id: str) -> tuple:
    return tuple(t for t in state.pattern.triggers if t.channel_id == channel_id)


def _write_raw(state_dir: Path, payload: Any) -> Path:
    path = _session_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _empty_live_kit_payload() -> dict[str, dict[str, None]]:
    return {group: {slot: None for slot in slots} for group, slots in LIVE_KIT_SLOT_MAPPING}


# --- 1. Missing file → fresh -------------------------------------------------


def test_missing_session_file_yields_fresh_empty_session(tmp_path: Path) -> None:
    session = compose_workbench_session(state_dir=tmp_path)
    assert all(
        session.live_kit.assignment_for(group, slot) is None
        for group, slots in LIVE_KIT_SLOT_MAPPING
        for slot in slots
    )
    assert session.channel_rack.state is None
    assert session.channel_rack.is_playing is False
    assert session.transport.get_current_tempo() == pytest.approx(DEFAULT_TEMPO_BPM)
    assert session.transport.is_sync_enabled() is False
    assert session.transport.get_snapshot()["next_tempo_bpm"] is None
    assert session.transport.playing is False
    session.transport.close()
    assert session.channel_rack.projection()["groups"] == []


# --- 2. Live Kit round-trip --------------------------------------------------


def test_live_kit_assignments_round_trip_across_compose(tmp_path: Path) -> None:
    kick = str(tmp_path / "kick.wav")
    pad = str(tmp_path / "pad.wav")
    Path(kick).write_bytes(b"RIFF")
    Path(pad).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=tmp_path)
    a.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    a.live_kit.assign("Melodic", "Pad", _row("pad.wav", pad))
    assert _session_path(tmp_path).is_file()

    b = compose_workbench_session(state_dir=tmp_path)
    assert b.live_kit.assignment_for("Kick + Bass", "Kick") is not None
    assert b.live_kit.assignment_for("Kick + Bass", "Kick").path == kick
    assert b.live_kit.assignment_for("Melodic", "Pad") is not None
    assert b.live_kit.assignment_for("Melodic", "Pad").path == pad
    assert b.live_kit.assignment_for("Kick + Bass", "Bass") is None
    # Minimal row: path durable, analysis not invented
    restored = b.live_kit.assignment_for("Kick + Bass", "Kick")
    assert restored.bpm is None
    assert restored.key is None
    assert restored.display_name == "kick.wav"


# --- 3. Edited seed pattern round-trip (no DEFAULT_ON re-seed) ---------------


def test_edited_seed_pattern_round_trip_without_default_on_reseed(
    tmp_path: Path,
) -> None:
    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=tmp_path)
    a.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    state = a.enter_screen2()
    # DEFAULT_ON then turn some steps off
    for step in (1, 3, 5, 7, 9, 11, 13, 15):
        state = a.channel_rack.toggle_step("ch_kick", step)
    expected = _triggers_for(state, "ch_kick")
    assert len(expected) == 8

    b = compose_workbench_session(state_dir=tmp_path)
    assert b.channel_rack.state is not None
    restored = _triggers_for(b.channel_rack.state, "ch_kick")
    assert restored == expected
    # enter_screen2 must keep edited triggers (reconcile keep, not seed)
    after_enter = b.enter_screen2()
    assert _triggers_for(after_enter, "ch_kick") == expected


# --- 4 / 5. User channel round-trip + next ID --------------------------------


def test_user_channel_round_trip_and_next_id_collision_free(tmp_path: Path) -> None:
    sample = str(tmp_path / "user_one.wav")
    Path(sample).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=tmp_path)
    a.enter_screen2()
    a.channel_rack.add_user_channel()
    a.channel_rack.assign_user_channel_sample("ch_user_1", sample)
    # DEFAULT_ON is all on; toggle off non-desired steps → keep 0/4/8/12
    for step in range(16):
        if step not in (0, 4, 8, 12):
            a.channel_rack.toggle_step("ch_user_1", step)
    expected = _triggers_for(a.channel_rack.state, "ch_user_1")
    assert len(expected) == 4

    b = compose_workbench_session(state_dir=tmp_path)
    assert b.channel_rack.state is not None
    user = next(c for c in b.channel_rack.state.channels if c.channel_id == "ch_user_1")
    assert user.live_kit_group is None
    assert user.live_kit_slot is None
    assert user.sample_path == sample
    assert _triggers_for(b.channel_rack.state, "ch_user_1") == expected

    b.enter_screen2()
    b.channel_rack.add_user_channel()
    ids = {c.channel_id for c in b.channel_rack.state.channels}
    assert "ch_user_1" in ids
    assert "ch_user_2" in ids
    # Allocator must also agree when asked directly
    assert allocate_user_channel_id(ids - {"ch_user_2"}) == "ch_user_2"


# --- 6. Mixed full session ---------------------------------------------------


def test_mixed_live_kit_user_channels_and_pattern_round_trip(tmp_path: Path) -> None:
    kick = str(tmp_path / "kick.wav")
    hat = str(tmp_path / "hat.wav")
    user = str(tmp_path / "fx.wav")
    for p in (kick, hat, user):
        Path(p).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=tmp_path)
    a.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    a.live_kit.assign("Drums", "Closed Hat", _row("hat.wav", hat))
    a.enter_screen2()
    a.channel_rack.toggle_step("ch_kick", 0)  # turn first step off
    a.channel_rack.add_user_channel()
    a.channel_rack.assign_user_channel_sample("ch_user_1", user)
    a.channel_rack.toggle_step("ch_user_1", 1)
    snap_a = a.channel_rack.state
    assert snap_a is not None

    b = compose_workbench_session(state_dir=tmp_path)
    assert b.live_kit.assignment_for("Kick + Bass", "Kick").path == kick
    assert b.live_kit.assignment_for("Drums", "Closed Hat").path == hat
    assert b.channel_rack.state is not None
    assert b.channel_rack.state.pattern.pattern_id == snap_a.pattern.pattern_id
    assert b.channel_rack.state.pattern.length_quarter_notes == snap_a.pattern.length_quarter_notes
    assert b.channel_rack.state.step_count == snap_a.step_count
    assert b.channel_rack.state.pattern.triggers == snap_a.pattern.triggers
    assert [c.channel_id for c in b.channel_rack.state.channels] == [
        c.channel_id for c in snap_a.channels
    ]


# --- 7 / 8 / 9. Fail-closed --------------------------------------------------


def test_corrupt_json_yields_fresh_session(tmp_path: Path) -> None:
    path = _session_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")

    session = compose_workbench_session(state_dir=tmp_path)
    assert session.live_kit.assignment_for("Kick + Bass", "Kick") is None
    assert session.channel_rack.state is None


def test_wrong_schema_version_yields_fresh_session(tmp_path: Path) -> None:
    _write_raw(
        tmp_path,
        {"schema_version": 99, "live_kit": {}, "channel_rack": None},
    )
    session = compose_workbench_session(state_dir=tmp_path)
    assert session.channel_rack.state is None
    assert all(
        session.live_kit.assignment_for(g, s) is None
        for g, slots in LIVE_KIT_SLOT_MAPPING
        for s in slots
    )


def test_semantically_invalid_payload_yields_fresh_session(tmp_path: Path) -> None:
    # Unknown trigger channel → reject entire snapshot (all-or-nothing)
    _write_raw(
        tmp_path,
        {
            "schema_version": 1,
            "live_kit": {
                "Kick + Bass": {"Kick": {"path": str(tmp_path / "k.wav")}, "Bass": None},
            },
            "channel_rack": {
                "pattern_id": "screen2-main",
                "length_quarter_notes": {"numerator": 4, "denominator": 1},
                "step_count": 16,
                "channels": [
                    {
                        "channel_id": "ch_kick",
                        "live_kit_group": "Kick + Bass",
                        "live_kit_slot": "Kick",
                        "sample_path": str(tmp_path / "k.wav"),
                    }
                ],
                "triggers": [
                    {
                        "channel_id": "ch_unknown",
                        "position": {"numerator": 0, "denominator": 4},
                    }
                ],
            },
        },
    )
    session = compose_workbench_session(state_dir=tmp_path)
    # All-or-nothing: kit must also be empty (not half-applied)
    assert session.live_kit.assignment_for("Kick + Bass", "Kick") is None
    assert session.channel_rack.state is None


def test_invalid_fraction_float_rejected(tmp_path: Path) -> None:
    _write_raw(
        tmp_path,
        {
            "schema_version": 1,
            "live_kit": {},
            "channel_rack": {
                "pattern_id": "screen2-main",
                "length_quarter_notes": {"numerator": 4.0, "denominator": 1},
                "step_count": 16,
                "channels": [],
                "triggers": [],
            },
        },
    )
    session = compose_workbench_session(state_dir=tmp_path)
    assert session.channel_rack.state is None


def test_bool_as_int_fraction_rejected(tmp_path: Path) -> None:
    _write_raw(
        tmp_path,
        {
            "schema_version": 1,
            "live_kit": {},
            "channel_rack": {
                "pattern_id": "screen2-main",
                "length_quarter_notes": {"numerator": True, "denominator": 1},
                "step_count": 16,
                "channels": [],
                "triggers": [],
            },
        },
    )
    session = compose_workbench_session(state_dir=tmp_path)
    assert session.channel_rack.state is None


def test_all_or_nothing_rejects_valid_kit_when_rack_invalid(tmp_path: Path) -> None:
    kick = str(tmp_path / "kick.wav")
    live_kit_payload: dict[str, Any] = {
        group: {slot: None for slot in slots} for group, slots in LIVE_KIT_SLOT_MAPPING
    }
    live_kit_payload["Kick + Bass"]["Kick"] = {"path": kick}
    _write_raw(
        tmp_path,
        {
            "schema_version": 1,
            "live_kit": live_kit_payload,
            "channel_rack": {
                "pattern_id": "screen2-main",
                "length_quarter_notes": {"numerator": 4, "denominator": 1},
                "step_count": 16,
                "channels": [
                    {
                        "channel_id": "ch_kick",
                        "live_kit_group": "Kick + Bass",
                        "live_kit_slot": "Kick",
                        "sample_path": kick,
                    },
                    {
                        # duplicate id
                        "channel_id": "ch_kick",
                        "live_kit_group": None,
                        "live_kit_slot": None,
                        "sample_path": None,
                    },
                ],
                "triggers": [],
            },
        },
    )
    session = compose_workbench_session(state_dir=tmp_path)
    assert session.live_kit.assignment_for("Kick + Bass", "Kick") is None
    assert session.channel_rack.state is None


# --- 10. Stale sample path ---------------------------------------------------


def test_stale_missing_sample_path_kept_as_reference(tmp_path: Path) -> None:
    missing = str(tmp_path / "gone" / "missing.wav")
    assert not Path(missing).exists()

    a = compose_workbench_session(state_dir=tmp_path)
    a.live_kit.assign("Kick + Bass", "Kick", _row("missing.wav", missing))

    b = compose_workbench_session(state_dir=tmp_path)
    restored = b.live_kit.assignment_for("Kick + Bass", "Kick")
    assert restored is not None
    assert restored.path == missing
    assert restored.bpm is None


# --- 11. Mutation autosave ---------------------------------------------------


def test_mutations_autosave_snapshot(tmp_path: Path) -> None:
    kick = str(tmp_path / "kick.wav")
    user = str(tmp_path / "user.wav")
    Path(kick).write_bytes(b"RIFF")
    Path(user).write_bytes(b"RIFF")

    session = compose_workbench_session(state_dir=tmp_path)
    path = _session_path(tmp_path)

    session.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["live_kit"]["Kick + Bass"]["Kick"]["path"] == kick

    session.enter_screen2()
    before = path.read_text(encoding="utf-8")
    session.channel_rack.toggle_step("ch_kick", 2)
    assert path.read_text(encoding="utf-8") != before

    session.channel_rack.add_user_channel()
    data = json.loads(path.read_text(encoding="utf-8"))
    user_ids = [c["channel_id"] for c in data["channel_rack"]["channels"] if c["channel_id"].startswith("ch_user_")]
    assert user_ids == ["ch_user_1"]

    session.channel_rack.assign_user_channel_sample("ch_user_1", user)
    data = json.loads(path.read_text(encoding="utf-8"))
    user_ch = next(c for c in data["channel_rack"]["channels"] if c["channel_id"] == "ch_user_1")
    assert user_ch["sample_path"] == user


# --- 12. Loop / playback not persisted ---------------------------------------


def test_loop_and_playback_runtime_not_persisted(tmp_path: Path) -> None:
    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=tmp_path)
    a.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    a.enter_screen2()
    # Simulate prior loop/play runtime without requiring a real engine
    a.channel_rack._playing = True
    a.channel_rack._loop_active = True
    a.channel_rack._loop_pass_index = 3
    a.channel_rack._play_handle = object()  # type: ignore[assignment]
    # Force save of musical state (mutation) while runtime flags are dirty
    a.channel_rack.toggle_step("ch_kick", 0)

    raw = json.loads(_session_path(tmp_path).read_text(encoding="utf-8"))
    blob = json.dumps(raw)
    assert "_playing" not in blob
    assert "_loop_active" not in blob
    assert "loop_pass" not in blob
    assert "play_handle" not in blob
    assert "voice" not in blob.lower() or "voice" not in str(raw.get("channel_rack"))

    b = compose_workbench_session(state_dir=tmp_path)
    assert b.channel_rack.is_playing is False
    assert b.channel_rack._loop_active is False
    assert b.channel_rack._loop_pass_index == 0
    assert b.channel_rack._play_handle is None


# --- 13. Compose restart → first projection restored -------------------------


def test_compose_restart_first_projection_already_restored(tmp_path: Path) -> None:
    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=tmp_path)
    a.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    a.enter_screen2()
    a.channel_rack.toggle_step("ch_kick", 0)
    del a

    b = compose_workbench_session(state_dir=tmp_path)
    # Before enter_screen2: restored state already projects
    proj = b.channel_rack.projection()
    assert proj["groups"]  # non-empty
    assert b.live_kit.assignment_for("Kick + Bass", "Kick") is not None
    kick_id = CHANNEL_ID_BY_LIVE_KIT_SLOT[("Kick + Bass", "Kick")]
    assert len(_triggers_for(b.channel_rack.state, kick_id)) == 15


# --- Restore callback suppression --------------------------------------------


def test_restore_does_not_fire_autosave_during_reconstruction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=tmp_path)
    a.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    a.enter_screen2()
    a.channel_rack.toggle_step("ch_kick", 1)
    path = _session_path(tmp_path)
    mtime_before = path.stat().st_mtime_ns
    content_before = path.read_text(encoding="utf-8")

    save_calls: list[int] = []
    import src.workbench_session_store as store_mod

    real_save = store_mod.save_workbench_session_snapshot

    def counting_save(*args, **kwargs):
        save_calls.append(1)
        return real_save(*args, **kwargs)

    monkeypatch.setattr(store_mod, "save_workbench_session_snapshot", counting_save)
    # Also patch the name used inside compose if imported differently
    monkeypatch.setattr(
        "src.workbench_session.save_workbench_session_snapshot",
        counting_save,
        raising=False,
    )

    b = compose_workbench_session(state_dir=tmp_path)
    assert b.channel_rack.state is not None
    # Restore must not rewrite the file / call save
    assert save_calls == []
    assert path.read_text(encoding="utf-8") == content_before
    assert path.stat().st_mtime_ns == mtime_before


# --- Atomic write failure keeps previous snapshot ----------------------------


def test_failed_atomic_replace_preserves_previous_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src import workbench_session_store as store_mod

    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")
    session = compose_workbench_session(state_dir=tmp_path)
    session.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    path = _session_path(tmp_path)
    previous = path.read_text(encoding="utf-8")

    real_replace = os.replace

    def boom(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(store_mod.os, "replace", boom)
    # Mutation triggers autosave; IO failure must not wipe prior file or memory
    session.live_kit.assign("Melodic", "Pad", _row("pad.wav", str(tmp_path / "pad.wav")))
    assert path.read_text(encoding="utf-8") == previous
    assert session.live_kit.assignment_for("Melodic", "Pad") is not None
    assert session.live_kit.assignment_for("Kick + Bass", "Kick").path == kick
    monkeypatch.setattr(store_mod.os, "replace", real_replace)


# --- Fractions never floats in on-disk JSON ----------------------------------


def test_persisted_fractions_are_exact_int_pairs(tmp_path: Path) -> None:
    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")
    session = compose_workbench_session(state_dir=tmp_path)
    session.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    session.enter_screen2()
    raw = json.loads(_session_path(tmp_path).read_text(encoding="utf-8"))
    length = raw["channel_rack"]["length_quarter_notes"]
    assert type(length["numerator"]) is int
    assert type(length["denominator"]) is int
    for trig in raw["channel_rack"]["triggers"]:
        assert type(trig["position"]["numerator"]) is int
        assert type(trig["position"]["denominator"]) is int
        assert not isinstance(trig["position"]["numerator"], bool)


# --- 14 / 15. Focused regressions via compose contracts ----------------------


def test_restore_leaves_screen1_quiet_no_audition_no_focus_claim(
    tmp_path: Path,
) -> None:
    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")
    a = compose_workbench_session(state_dir=tmp_path)
    a.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    a.enter_screen2()
    a.channel_rack.toggle_step("ch_kick", 0)

    claims: list[str] = []
    b = compose_workbench_session(state_dir=tmp_path)
    # restore_state must not claim audio focus
    b.channel_rack.set_audio_focus_hooks(
        on_claim_focus=lambda: claims.append("claim"),
        on_release_to_screen1=lambda: claims.append("release"),
    )
    # Re-compose already restored; ensure quiet
    assert b.channel_rack.is_playing is False
    assert claims == []
    # Explicit enter still claims (normal #807 path)
    b.enter_screen2()
    assert "claim" in claims


def test_user_channel_cannot_forge_live_kit_provenance_in_snapshot(
    tmp_path: Path,
) -> None:
    _write_raw(
        tmp_path,
        {
            "schema_version": 1,
            "live_kit": {
                group: {slot: None for slot in slots}
                for group, slots in LIVE_KIT_SLOT_MAPPING
            },
            "channel_rack": {
                "pattern_id": "screen2-main",
                "length_quarter_notes": {"numerator": 4, "denominator": 1},
                "step_count": 16,
                "channels": [
                    {
                        "channel_id": "ch_user_1",
                        "live_kit_group": "Kick + Bass",
                        "live_kit_slot": "Kick",
                        "sample_path": None,
                    }
                ],
                "triggers": [],
            },
        },
    )
    session = compose_workbench_session(state_dir=tmp_path)
    assert session.channel_rack.state is None


def test_unknown_keys_fail_closed(tmp_path: Path) -> None:
    _write_raw(
        tmp_path,
        {
            "schema_version": 1,
            "live_kit": {},
            "channel_rack": None,
            "playing": True,
        },
    )
    session = compose_workbench_session(state_dir=tmp_path)
    assert session.channel_rack.state is None
    assert session.live_kit.assignment_for("Kick + Bass", "Kick") is None


def test_toggle_step_core_still_symmetric_after_persistence_import() -> None:
    """#806 surface still importable; persistence must not break toggle contract."""
    from src.channel_rack import build_channel_rack_state

    kit = LiveKitState()
    kit.assign("Kick + Bass", "Kick", _row("k.wav", "synthetic/k.wav"))
    state = build_channel_rack_state(kit)
    assert len(_triggers_for(state, "ch_kick")) == 16
    state2 = toggle_step(state, "ch_kick", 0)
    assert len(_triggers_for(state2, "ch_kick")) == 15


# --- #817 late Live Kit assign → DEFAULT_ON across restart --------------------

_DEFAULT_ON_POSITIONS = tuple(Fraction(i, 4) for i in range(16))


def test_late_live_kit_assign_after_empty_rack_persists_default_on(
    tmp_path: Path,
) -> None:
    """Case 1: empty rack birth → Screen1 late assign → restart → DEFAULT_ON."""
    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=tmp_path)
    empty = a.enter_screen2()
    assert a.channel_rack.state is not None
    kick_ch = next(c for c in empty.channels if c.channel_id == "ch_kick")
    assert kick_ch.sample_path is None
    assert _triggers_for(empty, "ch_kick") == ()
    a.return_to_screen1()

    a.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))

    b = compose_workbench_session(state_dir=tmp_path)
    assert b.live_kit.assignment_for("Kick + Bass", "Kick") is not None
    assert b.live_kit.assignment_for("Kick + Bass", "Kick").path == kick
    restored = b.enter_screen2()
    kick_restored = next(c for c in restored.channels if c.channel_id == "ch_kick")
    assert kick_restored.sample_path == kick
    kick_triggers = _triggers_for(restored, "ch_kick")
    assert len(kick_triggers) == 16
    assert [t.position for t in kick_triggers] == list(_DEFAULT_ON_POSITIONS)


def test_late_live_kit_assign_reconciles_in_memory_before_restart(
    tmp_path: Path,
) -> None:
    """Case 2: late assign heals active rack immediately (no re-enter needed)."""
    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")

    session = compose_workbench_session(state_dir=tmp_path)
    session.enter_screen2()
    session.return_to_screen1()
    session.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))

    state = session.channel_rack.state
    assert state is not None
    kick_ch = next(c for c in state.channels if c.channel_id == "ch_kick")
    assert kick_ch.sample_path == kick
    kick_triggers = _triggers_for(state, "ch_kick")
    assert len(kick_triggers) == 16
    assert [t.position for t in kick_triggers] == list(_DEFAULT_ON_POSITIONS)

    # Disk already coherent (Case 9)
    data = json.loads(_session_path(tmp_path).read_text(encoding="utf-8"))
    disk_kick = next(c for c in data["channel_rack"]["channels"] if c["channel_id"] == "ch_kick")
    assert disk_kick["sample_path"] == kick
    disk_triggers = [
        t for t in data["channel_rack"]["triggers"] if t["channel_id"] == "ch_kick"
    ]
    assert len(disk_triggers) == 16


def test_replacement_preserves_custom_pattern_across_restart(tmp_path: Path) -> None:
    """Case 3: assigned → replacement keeps exact custom triggers."""
    kick_a = str(tmp_path / "kick_a.wav")
    kick_b = str(tmp_path / "kick_b.wav")
    Path(kick_a).write_bytes(b"RIFF")
    Path(kick_b).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=tmp_path)
    a.live_kit.assign("Kick + Bass", "Kick", _row("kick_a.wav", kick_a))
    state = a.enter_screen2()
    for step in (1, 3, 5, 7, 9, 11, 13, 15):
        state = a.channel_rack.toggle_step("ch_kick", step)
    expected = _triggers_for(state, "ch_kick")
    assert len(expected) == 8
    a.return_to_screen1()
    a.live_kit.assign("Kick + Bass", "Kick", _row("kick_b.wav", kick_b))

    b = compose_workbench_session(state_dir=tmp_path)
    assert b.live_kit.assignment_for("Kick + Bass", "Kick").path == kick_b
    restored = b.enter_screen2()
    assert next(c for c in restored.channels if c.channel_id == "ch_kick").sample_path == kick_b
    assert _triggers_for(restored, "ch_kick") == expected


def test_manual_all_off_survives_replacement_across_restart(tmp_path: Path) -> None:
    """Case 4: intentional all-off must never reseed DEFAULT_ON on replace."""
    kick_a = str(tmp_path / "kick_a.wav")
    kick_b = str(tmp_path / "kick_b.wav")
    Path(kick_a).write_bytes(b"RIFF")
    Path(kick_b).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=tmp_path)
    a.live_kit.assign("Kick + Bass", "Kick", _row("kick_a.wav", kick_a))
    a.enter_screen2()
    for step in range(16):
        a.channel_rack.toggle_step("ch_kick", step)
    assert _triggers_for(a.channel_rack.state, "ch_kick") == ()
    a.return_to_screen1()
    a.live_kit.assign("Kick + Bass", "Kick", _row("kick_b.wav", kick_b))

    b = compose_workbench_session(state_dir=tmp_path)
    restored = b.enter_screen2()
    assert next(c for c in restored.channels if c.channel_id == "ch_kick").sample_path == kick_b
    assert _triggers_for(restored, "ch_kick") == ()


def test_late_kick_assign_isolates_unrelated_and_user_channels(tmp_path: Path) -> None:
    """Cases 5+6: late Kick assign must not mutate Hat/Pad/user triggers."""
    kick = str(tmp_path / "kick.wav")
    hat = str(tmp_path / "hat.wav")
    user = str(tmp_path / "user.wav")
    Path(kick).write_bytes(b"RIFF")
    Path(hat).write_bytes(b"RIFF")
    Path(user).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=tmp_path)
    a.live_kit.assign("Drums", "Closed Hat", _row("hat.wav", hat))
    a.enter_screen2()
    # Custom hat pattern (keep even steps)
    for step in (1, 3, 5, 7, 9, 11, 13, 15):
        a.channel_rack.toggle_step("ch_closed_hat", step)
    hat_expected = _triggers_for(a.channel_rack.state, "ch_closed_hat")
    a.channel_rack.add_user_channel()
    a.channel_rack.assign_user_channel_sample("ch_user_1", user)
    for step in range(16):
        if step not in (0, 8):
            a.channel_rack.toggle_step("ch_user_1", step)
    user_expected = _triggers_for(a.channel_rack.state, "ch_user_1")
    a.return_to_screen1()

    a.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))

    mem = a.channel_rack.state
    assert mem is not None
    assert len(_triggers_for(mem, "ch_kick")) == 16
    assert _triggers_for(mem, "ch_closed_hat") == hat_expected
    assert _triggers_for(mem, "ch_user_1") == user_expected
    user_ch = next(c for c in mem.channels if c.channel_id == "ch_user_1")
    assert user_ch.sample_path == user
    assert user_ch.live_kit_group is None
    assert user_ch.live_kit_slot is None

    b = compose_workbench_session(state_dir=tmp_path)
    restored = b.enter_screen2()
    assert len(_triggers_for(restored, "ch_kick")) == 16
    assert _triggers_for(restored, "ch_closed_hat") == hat_expected
    assert _triggers_for(restored, "ch_user_1") == user_expected


def test_single_live_kit_assign_autosaves_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Case 7: one Live Kit assign → one coherent autosave (no double write)."""
    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")

    save_calls: list[Any] = []
    import src.workbench_session as session_mod

    real_save = session_mod.save_workbench_session_snapshot

    def _counting_save(snapshot, **kwargs):
        save_calls.append(snapshot)
        return real_save(snapshot, **kwargs)

    monkeypatch.setattr(session_mod, "save_workbench_session_snapshot", _counting_save)

    session = compose_workbench_session(state_dir=tmp_path)
    session.enter_screen2()
    session.return_to_screen1()
    save_calls.clear()

    session.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    assert len(save_calls) == 1
    snap = save_calls[0]
    assert snap.channel_rack is not None
    kick_ch = next(c for c in snap.channel_rack.channels if c.channel_id == "ch_kick")
    assert kick_ch.sample_path == kick
    assert len(_triggers_for(snap.channel_rack, "ch_kick")) == 16


def test_live_kit_assign_without_rack_keeps_channel_rack_null(tmp_path: Path) -> None:
    """Case 8: never entered Screen2 → assign persists kit only; rack stays null."""
    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")

    a = compose_workbench_session(state_dir=tmp_path)
    assert a.channel_rack.state is None
    a.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    assert a.channel_rack.state is None

    data = json.loads(_session_path(tmp_path).read_text(encoding="utf-8"))
    assert data["channel_rack"] is None
    assert data["live_kit"]["Kick + Bass"]["Kick"]["path"] == kick

    b = compose_workbench_session(state_dir=tmp_path)
    assert b.channel_rack.state is None
    built = b.enter_screen2()
    assert len(_triggers_for(built, "ch_kick")) == 16

# --- #818 MASTER + SYNC persistence ------------------------------------------


def test_v2_tempo_and_sync_round_trip_across_compose(tmp_path: Path) -> None:
    """Case 1: set MASTER 140 + SYNC on → restart restores both."""
    a = compose_workbench_session(state_dir=tmp_path)
    a.transport.set_tempo(140.0)
    a.transport.set_sync_enabled(True)
    assert a.transport.get_current_tempo() == pytest.approx(140.0)
    assert a.transport.is_sync_enabled() is True
    a.transport.close()

    data = json.loads(_session_path(tmp_path).read_text(encoding="utf-8"))
    assert data["schema_version"] == 2
    assert data["master_bpm"] == pytest.approx(140.0)
    assert data["sync_enabled"] is True

    b = compose_workbench_session(state_dir=tmp_path)
    assert b.transport.get_current_tempo() == pytest.approx(140.0)
    assert b.transport.is_sync_enabled() is True
    assert b.transport.get_snapshot()["next_tempo_bpm"] is None
    assert b.transport.playing is False
    b.transport.close()


def test_fresh_session_defaults_master_and_sync_off(tmp_path: Path) -> None:
    """Case 2: fresh compose uses canonical default MASTER and SYNC off."""
    session = compose_workbench_session(state_dir=tmp_path)
    assert session.transport.get_current_tempo() == pytest.approx(DEFAULT_TEMPO_BPM)
    assert session.transport.is_sync_enabled() is False
    assert not _session_path(tmp_path).is_file()
    session.transport.close()


def test_legacy_v1_restore_defaults_clock_and_next_mutation_writes_v2(
    tmp_path: Path,
) -> None:
    """Case 3: valid v1 file restores kit; default MASTER + SYNC off; mutation → v2."""
    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")
    _write_raw(
        tmp_path,
        {
            "schema_version": 1,
            "live_kit": {
                group: {
                    slot: ({"path": kick} if (group, slot) == ("Kick + Bass", "Kick") else None)
                    for slot in slots
                }
                for group, slots in LIVE_KIT_SLOT_MAPPING
            },
            "channel_rack": None,
        },
    )
    path = _session_path(tmp_path)
    content_before = path.read_text(encoding="utf-8")

    session = compose_workbench_session(state_dir=tmp_path)
    assert session.live_kit.assignment_for("Kick + Bass", "Kick").path == kick
    assert session.transport.get_current_tempo() == pytest.approx(DEFAULT_TEMPO_BPM)
    assert session.transport.is_sync_enabled() is False
    # Restore must not rewrite the v1 file.
    assert path.read_text(encoding="utf-8") == content_before
    assert json.loads(content_before)["schema_version"] == 1

    session.transport.set_tempo(128.0)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2
    assert data["master_bpm"] == pytest.approx(128.0)
    assert data["sync_enabled"] is False
    assert data["live_kit"]["Kick + Bass"]["Kick"]["path"] == kick
    session.transport.close()


def test_tempo_only_mutation_autosaves_without_kit_change(tmp_path: Path) -> None:
    """Case 4: set_tempo alone updates workbench_session.json."""
    session = compose_workbench_session(state_dir=tmp_path)
    path = _session_path(tmp_path)
    assert not path.is_file()
    session.transport.set_tempo(150.0)
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2
    assert data["master_bpm"] == pytest.approx(150.0)
    assert data["sync_enabled"] is False
    session.transport.close()


def test_sync_only_mutation_autosaves_without_kit_change(tmp_path: Path) -> None:
    """Case 5: toggle_sync alone updates workbench_session.json."""
    session = compose_workbench_session(state_dir=tmp_path)
    path = _session_path(tmp_path)
    session.transport.toggle_sync()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2
    assert data["sync_enabled"] is True
    assert data["master_bpm"] == pytest.approx(DEFAULT_TEMPO_BPM)
    session.transport.close()


def test_pending_tempo_persists_target_not_current_effective(
    tmp_path: Path,
) -> None:
    """Case 6: while playing, scheduled set_tempo target is the resume MASTER."""
    from types import SimpleNamespace

    from src.session_grid import MusicalPosition

    class _SnapEngine:
        def __init__(self) -> None:
            self.engine_frame = 0
            self.running = False

        def start(self) -> None:
            self.running = True

        def stop(self) -> None:
            self.running = False

        def close(self) -> None:
            return None

        def snapshot(self):
            return SimpleNamespace(engine_frame=self.engine_frame, running=self.running)

    a = compose_workbench_session(state_dir=tmp_path)
    transport = a.transport
    engine = _SnapEngine()
    with transport._lock:
        transport._native_engine = engine
        transport._native_available = True
        transport._native_owned = False
        transport._native_opened = True
    assert transport.get_current_tempo() == pytest.approx(132.0)
    bar_one = transport.tempo_map.bar_beat_to_frame(MusicalPosition(1, 0))
    transport.seek(bar_one)
    transport.play()
    assert transport.playing is True
    effective = transport.set_tempo(140.0)
    snap = transport.get_snapshot()
    assert snap["current_tempo"] == pytest.approx(132.0)
    assert snap["next_tempo_bpm"] == pytest.approx(140.0)
    assert effective > transport.get_session_frame()

    data = json.loads(_session_path(tmp_path).read_text(encoding="utf-8"))
    assert data["master_bpm"] == pytest.approx(140.0)
    assert "next_tempo_frame" not in data
    a.transport.close()

    b = compose_workbench_session(state_dir=tmp_path)
    assert b.transport.get_current_tempo() == pytest.approx(140.0)
    assert b.transport.get_snapshot()["next_tempo_bpm"] is None
    assert b.transport.playing is False
    b.transport.close()


@pytest.mark.parametrize(
    "bad_bpm",
    [0, -1, float("nan"), float("inf"), float("-inf"), True, "132", None],
)
def test_invalid_v2_master_bpm_fail_closed(tmp_path: Path, bad_bpm: object) -> None:
    """Case 7: invalid master_bpm → whole snapshot discarded."""
    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")
    payload: dict[str, Any] = {
        "schema_version": 2,
        "master_bpm": bad_bpm,
        "sync_enabled": False,
        "live_kit": {
            group: {
                slot: ({"path": kick} if (group, slot) == ("Kick + Bass", "Kick") else None)
                for slot in slots
            }
            for group, slots in LIVE_KIT_SLOT_MAPPING
        },
        "channel_rack": None,
    }
    # JSON cannot encode NaN/Inf with default allow_nan=False; write via dumps allow_nan.
    path = _session_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(bad_bpm, float) and not math.isfinite(bad_bpm):
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=True) + "\n",
            encoding="utf-8",
        )
    else:
        _write_raw(tmp_path, payload)

    session = compose_workbench_session(state_dir=tmp_path)
    assert session.live_kit.assignment_for("Kick + Bass", "Kick") is None
    assert session.transport.get_current_tempo() == pytest.approx(DEFAULT_TEMPO_BPM)
    assert session.transport.is_sync_enabled() is False
    session.transport.close()


@pytest.mark.parametrize("bad_sync", [0, 1, "true", "false", None, 1.0])
def test_invalid_v2_sync_enabled_fail_closed(tmp_path: Path, bad_sync: object) -> None:
    """Case 8: non-bool sync_enabled → whole snapshot discarded."""
    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")
    _write_raw(
        tmp_path,
        {
            "schema_version": 2,
            "master_bpm": 140.0,
            "sync_enabled": bad_sync,
            "live_kit": {
                group: {
                    slot: ({"path": kick} if (group, slot) == ("Kick + Bass", "Kick") else None)
                    for slot in slots
                }
                for group, slots in LIVE_KIT_SLOT_MAPPING
            },
            "channel_rack": None,
        },
    )
    session = compose_workbench_session(state_dir=tmp_path)
    assert session.live_kit.assignment_for("Kick + Bass", "Kick") is None
    assert session.transport.get_current_tempo() == pytest.approx(DEFAULT_TEMPO_BPM)
    session.transport.close()


def test_unknown_root_key_v2_fail_closed(tmp_path: Path) -> None:
    """Case 9: unknown root keys remain fail-closed on v2."""
    _write_raw(
        tmp_path,
        {
            "schema_version": 2,
            "master_bpm": 140.0,
            "sync_enabled": True,
            "live_kit": _empty_live_kit_payload(),
            "channel_rack": None,
            "playing": True,
        },
    )
    session = compose_workbench_session(state_dir=tmp_path)
    assert session.channel_rack.state is None
    assert session.transport.get_current_tempo() == pytest.approx(DEFAULT_TEMPO_BPM)
    assert session.transport.is_sync_enabled() is False
    session.transport.close()


def test_clock_restore_leaves_playback_runtime_absent(tmp_path: Path) -> None:
    """Case 10: restart is stopped with no pending tempo / loop / handles."""
    a = compose_workbench_session(state_dir=tmp_path)
    a.transport.set_tempo(144.0)
    a.transport.set_sync_enabled(True)
    # Dirty in-memory playback flags must not leak into the resume file.
    a.channel_rack._playing = True
    a.channel_rack._loop_active = True
    a.channel_rack._loop_pass_index = 2
    a.channel_rack._play_handle = object()  # type: ignore[assignment]
    a.transport.close()

    b = compose_workbench_session(state_dir=tmp_path)
    assert b.transport.get_current_tempo() == pytest.approx(144.0)
    assert b.transport.is_sync_enabled() is True
    assert b.transport.playing is False
    assert b.transport.get_snapshot()["next_tempo_bpm"] is None
    assert b.channel_rack.is_playing is False
    assert b.channel_rack._loop_active is False
    assert b.channel_rack._loop_pass_index == 0
    assert b.channel_rack._play_handle is None
    b.transport.close()


def test_restored_transport_is_shared_tempo_map_authority(tmp_path: Path) -> None:
    """Case 12: session.transport.tempo_map is channel_rack.transport.tempo_map."""
    a = compose_workbench_session(state_dir=tmp_path)
    a.transport.set_tempo(138.0)
    a.transport.close()

    b = compose_workbench_session(state_dir=tmp_path)
    assert b.channel_rack.transport is b.transport
    assert b.channel_rack.transport.tempo_map is b.transport.tempo_map
    assert b.transport.get_current_tempo() == pytest.approx(138.0)
    assert b.transport.tempo_map.segments[0].bpm == pytest.approx(138.0)
    b.transport.close()


def test_restore_v2_clock_does_not_autosave(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Case 14: composing a valid v2 snapshot must not write during restore."""
    _write_raw(
        tmp_path,
        {
            "schema_version": 2,
            "master_bpm": 140.0,
            "sync_enabled": True,
            "live_kit": _empty_live_kit_payload(),
            "channel_rack": None,
        },
    )
    path = _session_path(tmp_path)
    content_before = path.read_text(encoding="utf-8")
    mtime_before = path.stat().st_mtime_ns

    import src.workbench_session as session_mod

    save_calls: list[int] = []
    real_save = session_mod.save_workbench_session_snapshot

    def counting_save(*args, **kwargs):
        save_calls.append(1)
        return real_save(*args, **kwargs)

    monkeypatch.setattr(session_mod, "save_workbench_session_snapshot", counting_save)
    session = compose_workbench_session(state_dir=tmp_path)
    assert save_calls == []
    assert path.read_text(encoding="utf-8") == content_before
    assert path.stat().st_mtime_ns == mtime_before
    assert session.transport.get_current_tempo() == pytest.approx(140.0)
    assert session.transport.is_sync_enabled() is True
    session.transport.close()


def test_set_sync_enabled_noop_does_not_autosave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = compose_workbench_session(state_dir=tmp_path)
    import src.workbench_session as session_mod

    save_calls: list[int] = []
    real_save = session_mod.save_workbench_session_snapshot

    def counting_save(*args, **kwargs):
        save_calls.append(1)
        return real_save(*args, **kwargs)

    monkeypatch.setattr(session_mod, "save_workbench_session_snapshot", counting_save)
    assert session.transport.is_sync_enabled() is False
    session.transport.set_sync_enabled(False)
    assert save_calls == []
    session.transport.set_tempo(DEFAULT_TEMPO_BPM)
    # Identical resume MASTER should not notify/autosave.
    assert save_calls == []
    session.transport.close()


def test_include_tk_workbench_restores_same_adapter_clock(tmp_path: Path) -> None:
    """Tk compose path must apply persisted clock onto the shared adapter."""
    a = compose_workbench_session(state_dir=tmp_path)
    a.transport.set_tempo(141.0)
    a.transport.set_sync_enabled(True)
    a.transport.close()

    b = compose_workbench_session(state_dir=tmp_path, include_tk_workbench=True)
    try:
        assert b.tk_workbench is not None
        assert b.transport is b.tk_workbench._transport_adapter
        assert b.transport.get_current_tempo() == pytest.approx(141.0)
        assert b.transport.is_sync_enabled() is True
        assert b.channel_rack.transport is b.transport
    finally:
        b.transport.close()
        if b.tk_workbench is not None:
            b.tk_workbench.root.destroy()


def test_pending_adjust_delta_persists_final_resume_target(tmp_path: Path) -> None:
    """Pending MASTER + user ± deltas persist the final resume target."""
    from types import SimpleNamespace

    from src.session_grid import MusicalPosition

    class _SnapEngine:
        def __init__(self) -> None:
            self.engine_frame = 0
            self.running = False

        def start(self) -> None:
            self.running = True

        def stop(self) -> None:
            self.running = False

        def close(self) -> None:
            return None

        def snapshot(self):
            return SimpleNamespace(engine_frame=self.engine_frame, running=self.running)

    a = compose_workbench_session(state_dir=tmp_path)
    transport = a.transport
    with transport._lock:
        transport._native_engine = _SnapEngine()
        transport._native_available = True
        transport._native_owned = False
        transport._native_opened = True
    bar_one = transport.tempo_map.bar_beat_to_frame(MusicalPosition(1, 0))
    transport.seek(bar_one)
    transport.play()
    transport.set_tempo(140.0)
    assert transport.get_resume_master_bpm() == pytest.approx(140.0)

    # Mimic QML/Tk adjust seams: resume base + delta.
    transport.set_tempo(transport.get_resume_master_bpm() + 1.0)
    assert transport.get_resume_master_bpm() == pytest.approx(141.0)
    transport.set_tempo(transport.get_resume_master_bpm() - 2.0)
    assert transport.get_resume_master_bpm() == pytest.approx(139.0)
    data = json.loads(_session_path(tmp_path).read_text(encoding="utf-8"))
    assert data["master_bpm"] == pytest.approx(139.0)
    a.transport.close()

    b = compose_workbench_session(state_dir=tmp_path)
    assert b.transport.get_current_tempo() == pytest.approx(139.0)
    assert b.transport.get_snapshot()["next_tempo_bpm"] is None
    assert b.transport.playing is False
    b.transport.close()


def test_set_tempo_autosaves_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.workbench_session as session_mod

    save_calls: list[Any] = []
    real_save = session_mod.save_workbench_session_snapshot

    def _counting_save(snapshot, **kwargs):
        save_calls.append(snapshot)
        return real_save(snapshot, **kwargs)

    monkeypatch.setattr(session_mod, "save_workbench_session_snapshot", _counting_save)
    session = compose_workbench_session(state_dir=tmp_path)
    save_calls.clear()
    session.transport.set_tempo(145.0)
    assert len(save_calls) == 1
    assert save_calls[0].master_bpm == pytest.approx(145.0)
    session.transport.close()


def test_toggle_sync_autosaves_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.workbench_session as session_mod

    save_calls: list[Any] = []
    real_save = session_mod.save_workbench_session_snapshot

    def _counting_save(snapshot, **kwargs):
        save_calls.append(snapshot)
        return real_save(snapshot, **kwargs)

    monkeypatch.setattr(session_mod, "save_workbench_session_snapshot", _counting_save)
    session = compose_workbench_session(state_dir=tmp_path)
    save_calls.clear()
    session.transport.toggle_sync()
    assert len(save_calls) == 1
    assert save_calls[0].sync_enabled is True
    session.transport.close()


def test_atomic_write_rejects_non_finite_master_bpm(tmp_path: Path) -> None:
    """Defense-in-depth: allow_nan=False blocks non-finite JSON emission."""
    from src.workbench_session_store import (
        WorkbenchSessionSnapshot,
        save_workbench_session_snapshot,
    )

    snapshot = WorkbenchSessionSnapshot(
        live_kit=_empty_live_kit_payload(),
        channel_rack=None,
        master_bpm=float("nan"),
        sync_enabled=False,
    )
    with pytest.raises(ValueError):
        save_workbench_session_snapshot(snapshot, state_dir=tmp_path)
    assert not _session_path(tmp_path).exists()


# --- #819 Persistence / resume honesty status (TEST_FREEZE) ------------------


def _assert_status_safe(status: str) -> None:
    """Status strings must stay reason-code sized — no paths/secrets/dumps."""
    assert status
    assert "\\" not in status
    assert "/" not in status or status.count("/") == 0
    assert "Traceback" not in status
    assert "OSError" not in status
    assert "C:" not in status
    assert "D:" not in status


def test_fresh_missing_status_when_no_session_file(tmp_path: Path) -> None:
    from src.workbench_session_store import PERSISTENCE_STATUS_FRESH_MISSING

    session = compose_workbench_session(state_dir=tmp_path)
    assert session.persistence_status == PERSISTENCE_STATUS_FRESH_MISSING
    _assert_status_safe(session.persistence_status)
    session.transport.close()


def test_restored_ok_status_after_successful_resume(tmp_path: Path) -> None:
    from src.workbench_session_store import PERSISTENCE_STATUS_RESTORED_OK

    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")
    a = compose_workbench_session(state_dir=tmp_path)
    a.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    a.transport.set_tempo(128.0)
    a.transport.close()

    b = compose_workbench_session(state_dir=tmp_path)
    assert b.persistence_status == PERSISTENCE_STATUS_RESTORED_OK
    assert b.live_kit.assignment_for("Kick + Bass", "Kick") is not None
    assert b.transport.get_current_tempo() == pytest.approx(128.0)
    _assert_status_safe(b.persistence_status)
    b.transport.close()


def test_corrupt_json_status_is_rejected_corrupt_and_empty(tmp_path: Path) -> None:
    from src.workbench_session_store import PERSISTENCE_STATUS_REJECTED_CORRUPT

    path = _session_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")

    session = compose_workbench_session(state_dir=tmp_path)
    assert session.persistence_status == PERSISTENCE_STATUS_REJECTED_CORRUPT
    assert session.live_kit.assignment_for("Kick + Bass", "Kick") is None
    assert session.channel_rack.state is None
    # Corrupt file remains (no required quarantine); status is the honesty surface.
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == "{not-json"
    _assert_status_safe(session.persistence_status)
    session.transport.close()


def test_wrong_schema_status_is_rejected_schema_and_empty(tmp_path: Path) -> None:
    from src.workbench_session_store import PERSISTENCE_STATUS_REJECTED_SCHEMA

    _write_raw(
        tmp_path,
        {"schema_version": 99, "live_kit": {}, "channel_rack": None},
    )
    session = compose_workbench_session(state_dir=tmp_path)
    assert session.persistence_status == PERSISTENCE_STATUS_REJECTED_SCHEMA
    assert session.channel_rack.state is None
    assert all(
        session.live_kit.assignment_for(g, s) is None
        for g, slots in LIVE_KIT_SLOT_MAPPING
        for s in slots
    )
    _assert_status_safe(session.persistence_status)
    session.transport.close()


def test_semantically_invalid_status_is_rejected_semantic_and_empty(
    tmp_path: Path,
) -> None:
    from src.workbench_session_store import PERSISTENCE_STATUS_REJECTED_SEMANTIC

    _write_raw(
        tmp_path,
        {
            "schema_version": 1,
            "live_kit": {
                "Kick + Bass": {
                    "Kick": {"path": str(tmp_path / "k.wav")},
                    "Bass": None,
                },
            },
            "channel_rack": {
                "pattern_id": "screen2-main",
                "length_quarter_notes": {"numerator": 4, "denominator": 1},
                "step_count": 16,
                "channels": [
                    {
                        "channel_id": "ch_kick",
                        "live_kit_group": "Kick + Bass",
                        "live_kit_slot": "Kick",
                        "sample_path": str(tmp_path / "k.wav"),
                    }
                ],
                "triggers": [
                    {
                        "channel_id": "ch_unknown",
                        "position": {"numerator": 0, "denominator": 4},
                    }
                ],
            },
        },
    )
    session = compose_workbench_session(state_dir=tmp_path)
    assert session.persistence_status == PERSISTENCE_STATUS_REJECTED_SEMANTIC
    assert session.live_kit.assignment_for("Kick + Bass", "Kick") is None
    assert session.channel_rack.state is None
    _assert_status_safe(session.persistence_status)
    session.transport.close()


def test_autosave_oserror_sets_autosave_failed_keeps_memory_and_last_good(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src import workbench_session_store as store_mod
    from src.workbench_session_store import (
        PERSISTENCE_STATUS_AUTOSAVE_FAILED,
        PERSISTENCE_STATUS_RESTORED_OK,
    )

    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")
    session = compose_workbench_session(state_dir=tmp_path)
    session.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    path = _session_path(tmp_path)
    previous = path.read_text(encoding="utf-8")
    # Successful mutation save leaves resume honesty as restored_ok after recompose,
    # but within the same process the compose status was fresh_missing then mutated.
    # Recompose to establish restored_ok as the baseline honesty code.
    session.transport.close()
    session = compose_workbench_session(state_dir=tmp_path)
    assert session.persistence_status == PERSISTENCE_STATUS_RESTORED_OK

    def boom(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(store_mod.os, "replace", boom)
    session.live_kit.assign(
        "Melodic", "Pad", _row("pad.wav", str(tmp_path / "pad.wav"))
    )
    assert session.persistence_status == PERSISTENCE_STATUS_AUTOSAVE_FAILED
    assert path.read_text(encoding="utf-8") == previous
    assert session.live_kit.assignment_for("Melodic", "Pad") is not None
    assert session.live_kit.assignment_for("Kick + Bass", "Kick").path == kick
    _assert_status_safe(session.persistence_status)
    session.transport.close()


def test_load_outcome_status_codes_are_stable_contract() -> None:
    from src.workbench_session_store import (
        PERSISTENCE_STATUS_AUTOSAVE_FAILED,
        PERSISTENCE_STATUS_FRESH_MISSING,
        PERSISTENCE_STATUS_REJECTED_CORRUPT,
        PERSISTENCE_STATUS_REJECTED_SCHEMA,
        PERSISTENCE_STATUS_REJECTED_SEMANTIC,
        PERSISTENCE_STATUS_RESTORED_OK,
        PERSISTENCE_STATUS_CODES,
    )

    assert PERSISTENCE_STATUS_CODES == frozenset(
        {
            PERSISTENCE_STATUS_FRESH_MISSING,
            PERSISTENCE_STATUS_RESTORED_OK,
            PERSISTENCE_STATUS_REJECTED_CORRUPT,
            PERSISTENCE_STATUS_REJECTED_SCHEMA,
            PERSISTENCE_STATUS_REJECTED_SEMANTIC,
            PERSISTENCE_STATUS_AUTOSAVE_FAILED,
        }
    )
    for code in PERSISTENCE_STATUS_CODES:
        _assert_status_safe(code)
