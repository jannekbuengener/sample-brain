"""TEST_GATE / TEST_FREEZE — Workbench musical session persistence (#809).

Canonical authority:
- docs/SESSION_OWNERSHIP_CONTRACT.md
- docs/DATA_AND_ARTIFACT_POLICY.md
- docs/PATTERN_CORE_CONTRACT.md
- Issue #809

Frozen product rules:
- versioned local JSON under workbench_state_dir (workbench_session.json)
- Live Kit path refs + Channel Rack channels/triggers only
- all-or-nothing fail-closed restore
- no autosave callbacks during restore
- edited triggers are authority (no DEFAULT_ON re-seed on restore)
- playback/loop runtime never persisted; restore is quiet/stopped
"""

from __future__ import annotations

import json
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
