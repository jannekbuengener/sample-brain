"""B2R regression — VERIFIED_PACKAGE_MEDIA_REBASE for PR #1137 / #1078.

Canon: ``docs/USER_CHANNEL_CLASSIFICATION_AUTHORITY.md`` §4a and
``docs/TRACK_PACKAGE_OWNERSHIP_CONTRACT.md`` §5a (merged to ``main`` via #1138 /
``4d906d5120c7b167a5ab1c1e012a0921d1040fe8``).

Frozen decision: a Track-Package-Runtime media copy inside the *same
successful* package transaction that is byte-identity-verified is **not** a
new sample assignment. Authoritatively resolved derived in-memory
``UserSampleMetadata`` evidence transfers identically (``sample_class`` +
``source_bpm``) to the package-relative destination. No classification, no
library refresh, no second classifier/normalizer, and no serialization of any
kind. Source ``ambiguous`` stays ``ambiguous``; an unverified copy transfers
nothing; a genuine user replacement A→B stays a regular Library-resolved B2
event; cold restore stays existing B1 semantics.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from src import track_package as tp
from src import workbench_session as ws
from src.arrangement_32_field_time import build_32_field_channel_rack_state
from src.channel_rack import (
    DEFAULT_STEP_COUNT,
    ChannelRackState,
    classification_kind,
    is_explicit_loop,
    point_trigger_eligible_channel_ids,
    sample_class_for_channel,
)
from src.pattern_core import Channel, Pattern, Trigger
from src.track_package import TrackPackageDraft, TrackPackageMediaSource
from src.workbench_controller import WorkbenchRow
from src.workbench_feature_settings import (
    WorkbenchFeatureSettings,
    save_workbench_feature_settings,
)
from src.workbench_library import init_workbench_library, upsert_folder, upsert_sample
from src.workbench_session_store import workbench_session_path

FORBIDDEN_METADATA_MARKERS = (
    "sample_class",
    "source_bpm",
    "user_metadata",
    "classification",
)


# ---------------------------------------------------------------------------
# Library + session fixtures
# ---------------------------------------------------------------------------


def _mono_wav(path: Path, *, frequency_hz: float = 60) -> Path:
    from tests.audio_fixtures import write_sine_wav

    path.parent.mkdir(parents=True, exist_ok=True)
    write_sine_wav(path, duration_sec=0.05, frequency_hz=frequency_hz)
    return path


def _library_row(name: str, path: str, *, bpm: float | None, sample_class: str | None):
    return WorkbenchRow(
        display_name=name,
        relative_path=name,
        path=path,
        bpm=bpm,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class=sample_class,
        pred_type=None,
        status="ok",
        details={},
    )


def _seeded_library(
    tmp_path: Path,
    rows: tuple[tuple[str, float | None, str | None], ...],
) -> tuple[Path, dict[str, str]]:
    """Create a real Workbench library; return ``(db_path, name→durable_path)``."""
    db = tmp_path / "library.db"
    init_workbench_library(db)
    folder = tmp_path / "samples"
    folder.mkdir(parents=True, exist_ok=True)
    folder_id = upsert_folder(folder, db_path=db)
    resolved: dict[str, str] = {}
    for row_index, (name, bpm, sample_class) in enumerate(rows):
        audio = _mono_wav(folder / name, frequency_hz=60 + 30 * row_index)
        durable = str(audio.resolve())
        stat = audio.stat()
        upsert_sample(
            folder_id,
            _library_row(name, durable, bpm=bpm, sample_class=sample_class),
            size_bytes=int(stat.st_size),
            mtime_ns=int(stat.st_mtime_ns),
            db_path=db,
        )
        resolved[name] = durable
    return db, resolved


def _user_session(tmp_path: Path, db: Path, *, kit_path: str | None = None):
    session = ws.compose_workbench_session(
        state_dir=tmp_path / "state",
        library_db_path=db,
    )
    if kit_path is not None:
        from tests.test_active_track_persistence_1098 import _row

        session.live_kit.assign("Kick + Bass", "Kick", _row(Path(kit_path)))
    return session


def _enable_arrangement(session) -> None:
    settings = replace(WorkbenchFeatureSettings(), arrangement_mode_enabled=True)
    assert save_workbench_feature_settings(settings, state_dir=session._state_dir)


def _materialize_user_channel(session, sample_path: str) -> str:
    """32-field contract state + one user channel resolved at restore (B1).

    The 32-field v1 truth only represents integer quarter-note fields, so the
    user channel carries one field-aligned trigger instead of the legacy
    sub-field DEFAULT_ON seed (which would fail the entry gate).
    """
    controller = session.channel_rack
    base = build_32_field_channel_rack_state(session.live_kit)
    channel_id = "u_b2r"
    state = ChannelRackState(
        channels=(
            *base.channels,
            Channel(
                channel_id=channel_id,
                live_kit_group=None,
                live_kit_slot=None,
                sample_path=sample_path,
            ),
        ),
        pattern=Pattern(
            pattern_id=base.pattern.pattern_id,
            length_quarter_notes=base.pattern.length_quarter_notes,
            triggers=_triggers(channel_id),
        ),
        step_count=base.step_count,
    )
    controller.restore_state(state)
    return channel_id


def _triggers(channel_id: str) -> tuple[Trigger, ...]:
    return (Trigger(channel_id=channel_id, position=Fraction(0)),)


def _class_for(session, channel_id: str) -> tuple[str | None, float | None]:
    channel = _channel_by_id(session.channel_rack.state, channel_id)
    metadata = session.channel_rack.user_metadata.get(channel.sample_path)
    if metadata is None:
        return None, None
    return metadata.sample_class, metadata.source_bpm


def _channel_by_id(state: ChannelRackState, channel_id: str) -> Channel:
    return next(c for c in state.channels if str(c.channel_id) == channel_id)


def _state(pattern_id: str, channels: tuple[Channel, ...]) -> ChannelRackState:
    return ChannelRackState(
        channels=channels,
        pattern=Pattern(pattern_id=pattern_id, length_quarter_notes=Fraction(4, 1)),
        step_count=DEFAULT_STEP_COUNT,
    )


# ---------------------------------------------------------------------------
# Session-level P1 regression + vectors 1–3, 5–7, 10
# ---------------------------------------------------------------------------


def test_user_channel_one_shot_survives_package_media_rebase(tmp_path):
    """P1: library-classified user channel stays classified after Entry+Return."""
    db, paths = _seeded_library(
        tmp_path,
        rows=(("kick.wav", 128.0, "one_shot"),),
    )
    kit_path = paths["kick.wav"]
    s = _user_session(tmp_path, db, kit_path=kit_path)
    old_path = paths["kick.wav"]
    channel_id = _materialize_user_channel(s, old_path)
    assert _class_for(s, channel_id) == ("one_shot", 128.0)

    rebased_channel_before = _channel_by_id(s.channel_rack.state, channel_id)
    _enable_arrangement(s)
    root = tmp_path / "track"
    result = s.enter_arrangement_from_edit(package_root=root)
    assert result.outcome == "open" and result.ok
    assert s.projection_mode == "ARRANGEMENT"

    after = _channel_by_id(s.channel_rack.state, channel_id)
    assert after.channel_id == rebased_channel_before.channel_id
    assert after.live_kit_group == rebased_channel_before.live_kit_group
    assert after.live_kit_slot == rebased_channel_before.live_kit_slot
    new_path = after.sample_path
    assert new_path is not None and Path(new_path) != Path(old_path)
    assert Path(new_path).is_relative_to(root)
    copied = Path(new_path).read_bytes()
    assert copied == Path(old_path).read_bytes()

    # Vector 1: sample_class survives the verified rebase identically.
    after_class, bpm = _class_for(s, channel_id)
    assert (after_class, bpm) == ("one_shot", 128.0)
    assert sample_class_for_channel(
        after, s.live_kit, user_metadata=s.channel_rack.user_metadata
    ) == "one_shot"
    assert channel_id in point_trigger_eligible_channel_ids(
        s.channel_rack.state, s.live_kit, user_metadata=s.channel_rack.user_metadata
    )

    # Vector 7 (task list): Return to Edit keeps the classification.
    s.return_to_edit()
    assert s.projection_mode == "EDIT"
    assert _class_for(s, channel_id) == ("one_shot", 128.0)
    s.transport.close()


def test_loop_rebase_keeps_class_and_source_bpm(tmp_path):
    """Vector 2: loop + verified rebase keeps loop class and identical source_bpm."""
    db, paths = _seeded_library(
        tmp_path,
        rows=(("pad.wav", 100.5, "loop"),),
    )
    kit_path = paths["pad.wav"]
    s = _user_session(tmp_path, db, kit_path=kit_path)
    old_path = paths["pad.wav"]
    channel_id = _materialize_user_channel(s, old_path)
    loop_channel = _channel_by_id(s.channel_rack.state, channel_id)
    assert is_explicit_loop(
        sample_class_for_channel(
            loop_channel, s.live_kit, user_metadata=s.channel_rack.user_metadata
        )
    )
    _enable_arrangement(s)
    root = tmp_path / "track"
    result = s.enter_arrangement_from_edit(package_root=root)
    assert result.outcome == "open" and result.ok
    after_class, bpm = _class_for(s, channel_id)
    assert after_class == "loop"
    assert bpm == 100.5
    s.transport.close()


def test_ambiguous_source_stays_ambiguous_after_rebase(tmp_path):
    """Vector 3: ambiguous Source ⇒ ambiguous Destination, no invented class."""
    db, _paths = _seeded_library(
        tmp_path,
        rows=(("kick.wav", 128.0, "one_shot"), ("pad.wav", 100.0, "loop")),
    )
    kit_path = _paths["kick.wav"]
    stale = _mono_wav(tmp_path / "samples" / "ambiguous.wav")
    stale_path = str(stale.resolve())
    s = _user_session(tmp_path, db, kit_path=kit_path)
    channel_id = _materialize_user_channel(s, stale_path)
    assert _class_for(s, channel_id)[0] is None
    _enable_arrangement(s)
    root = tmp_path / "track"
    result = s.enter_arrangement_from_edit(package_root=root)
    assert result.outcome == "open" and result.ok
    resolved_class = sample_class_for_channel(
        _channel_by_id(s.channel_rack.state, channel_id),
        s.live_kit,
        user_metadata=s.channel_rack.user_metadata,
    )
    assert resolved_class is None
    assert classification_kind(resolved_class) == "ambiguous"
    s.transport.close()


def test_real_user_replacement_is_normal_b2_not_rebase(tmp_path):
    """Vector 5: explicit A→B replacement resolves through the Library."""
    db, paths = _seeded_library(
        tmp_path,
        rows=(("kick.wav", 128.0, "one_shot"), ("pad.wav", 100.0, "loop")),
    )
    kit_path = paths["kick.wav"]
    s = _user_session(tmp_path, db, kit_path=kit_path)
    old_path = paths["kick.wav"]
    channel_id = _materialize_user_channel(s, old_path)
    _enable_arrangement(s)
    root = tmp_path / "track"
    result = s.enter_arrangement_from_edit(package_root=root)
    assert result.outcome == "open" and result.ok
    old_dest = _channel_by_id(s.channel_rack.state, channel_id).sample_path

    replacement_state = s.channel_rack.assign_user_channel_sample(
        channel_id, paths["pad.wav"]
    )
    del replacement_state
    # The open-package autosave may already have copied the newly required
    # media and rebased the runtime path inside the same verified transaction;
    # classification must come from the pad Library row either way.
    pad_dwelling = _channel_by_id(s.channel_rack.state, channel_id)
    assert pad_dwelling.sample_path not in (None, old_dest)
    binding = s.channel_rack.user_metadata
    destination_entry = binding[str(pad_dwelling.sample_path)]
    assert destination_entry.sample_class == "loop"
    assert destination_entry.source_bpm == 100.0
    assert is_explicit_loop(
        sample_class_for_channel(pad_dwelling, s.live_kit, user_metadata=binding)
    )
    assert old_dest not in binding
    s.transport.close()


def test_entry_performs_no_library_write(tmp_path):
    """Vector 6: Entry + rebase never writes the Workbench library."""
    db, paths = _seeded_library(
        tmp_path,
        rows=(("kick.wav", 128.0, "one_shot"),),
    )
    kit_path = paths["kick.wav"]
    s = _user_session(tmp_path, db, kit_path=kit_path)
    _materialize_user_channel(s, paths["kick.wav"])
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    _enable_arrangement(s)
    root = tmp_path / "track"
    assert s.enter_arrangement_from_edit(package_root=root).outcome == "open"
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    s.transport.close()


def test_no_metadata_serialization_after_entry(tmp_path):
    """Vector 7: rebase lands nowhere persisted — session JSON and package."""
    db, paths = _seeded_library(
        tmp_path,
        rows=(("kick.wav", 128.0, "one_shot"),),
    )
    kit_path = paths["kick.wav"]
    s = _user_session(tmp_path, db, kit_path=kit_path)
    _materialize_user_channel(s, paths["kick.wav"])
    _enable_arrangement(s)
    root = tmp_path / "track"
    assert s.enter_arrangement_from_edit(package_root=root).outcome == "open"
    package_document = (root / "track_package.json").read_text(encoding="utf-8")
    payload = json.loads(package_document)
    assert payload["schema_version"] == 1
    assert payload["package_kind"] == "sample_brain_track_package"
    resume_document = workbench_session_path(state_dir=s._state_dir).read_text(
        encoding="utf-8"
    )
    for marker in FORBIDDEN_METADATA_MARKERS:
        assert f'"{marker}"' not in package_document
        assert f'"{marker}"' not in resume_document
    s.transport.close()


def test_entry_resolves_through_exactly_one_resolver_pass(tmp_path):
    """Vector 10: the transition runs no second classification pass.

    Exactly one resolver batch belongs to the bound B1 restore; B2R itself
    performs zero library reads at the destination.
    """
    db, paths = _seeded_library(
        tmp_path,
        rows=(("kick.wav", 128.0, "one_shot"),),
    )
    kit_path = paths["kick.wav"]
    s = _user_session(tmp_path, db, kit_path=kit_path)
    channel_id = _materialize_user_channel(s, paths["kick.wav"])
    _enable_arrangement(s)
    root = tmp_path / "track"

    opens = {"count": 0}
    original_resolver = s.channel_rack._user_metadata_resolver

    class _CountingResolver:
        def resolve(self, batch):
            opens["count"] += 1
            return original_resolver.resolve(batch)

        def resolve_one(self, path):
            opens["count"] += 1
            return original_resolver.resolve_one(path)

    s.channel_rack._user_metadata_resolver = _CountingResolver()
    try:
        result = s.enter_arrangement_from_edit(package_root=root)
        assert result.outcome == "open" and result.ok
        assert opens["count"] == 1
        assert _class_for(s, channel_id) == ("one_shot", 128.0)
    finally:
        s.channel_rack._user_metadata_resolver = original_resolver
    s.transport.close()


# ---------------------------------------------------------------------------
# track_package seam vectors: 4 (unverified copy ⇒ no transfer)
# ---------------------------------------------------------------------------


def test_unverified_copy_refuses_transfer(tmp_path):
    """Vector 4: an unverified destination yields no rebase pair.

    Verification lives at the runtime copy + ``media_rebase_transfer_map``
    seam: an intact byte-identical copy qualifies; a mutated destination
    refuses the pair. The transfer seam never fabricates identity.
    """
    source = _mono_wav(tmp_path / "samples" / "kick.wav")
    source_path = str(source.resolve())
    musical = {
        "live_kit": {"Kick + Bass": {"Kick": {"path": source_path}}},
        "channel_rack": None,
        "master_bpm": 1.0,
        "sync_enabled": False,
    }
    intact = tp.create_track_package(
        TrackPackageDraft(
            media_sources=(TrackPackageMediaSource(source),),
            musical=musical,
        ),
        tmp_path / "track",
    )
    assert intact.outcome == "open" and intact.ok
    verified = tp.media_rebase_transfer_map(intact, [source_path])
    assert len(verified) == 1
    (pair_old, pair_new), = verified.items()
    assert pair_old == source_path
    assert Path(pair_new).is_file()
    assert Path(pair_new).read_bytes() == source.read_bytes()

    Path(pair_new).write_bytes(b"tampered, no longer byte-identical")
    assert tp.media_rebase_transfer_map(intact, [source_path]) == {}


# ---------------------------------------------------------------------------
# Controller-level binding vectors 8/9 (reference-safe source binding)
# ---------------------------------------------------------------------------


def _destination_copy(tmp_path: Path, source: str) -> str:
    destination = tmp_path / "pkg" / "media" / "media.wav"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(Path(source).read_bytes())
    return str(destination)


def test_shared_source_binding_kept_while_referenced(tmp_path):
    """Vector 8: Source stays bound while any channel still references it."""
    db, paths = _seeded_library(
        tmp_path,
        rows=(("kick.wav", 128.0, "one_shot"),),
    )
    old_path = paths["kick.wav"]
    kit_path = paths["kick.wav"]
    s = _user_session(tmp_path, db, kit_path=kit_path)
    controller = s.channel_rack
    # Pre-restore: both channels reference the Source → B1 resolves it once.
    pre = _state(
        "b2r-shared-pre",
        (
            Channel(
                channel_id="u_survivor",
                live_kit_group=None,
                live_kit_slot=None,
                sample_path=old_path,
            ),
            Channel(
                channel_id="u_rebased",
                live_kit_group=None,
                live_kit_slot=None,
                sample_path=old_path,
            ),
        ),
    )
    controller.restore_state(pre)
    assert controller.user_metadata[old_path].sample_class == "one_shot"
    new_path = _destination_copy(tmp_path, old_path)
    controller.stage_media_rebase_transfer({old_path: new_path})
    # Survivor still references the Source after the transaction restore; the
    # rebased channel moved on to the verified destination.
    restored = _state(
        "b2r-shared",
        (
            Channel(
                channel_id="u_survivor",
                live_kit_group=None,
                live_kit_slot=None,
                sample_path=old_path,
            ),
            Channel(
                channel_id="u_rebased",
                live_kit_group=None,
                live_kit_slot=None,
                sample_path=new_path,
            ),
        ),
    )
    controller.restore_state(restored)
    binding = controller.user_metadata
    assert old_path in binding
    new_entry = binding[new_path]
    assert new_entry.sample_class == "one_shot" and new_entry.source_bpm == 128.0
    assert binding[old_path] == binding[new_path]
    s.transport.close()


def test_unreferenced_source_may_prune_after_transfer(tmp_path):
    """Vector 9: after a completed verified rebase only destination evidence."""
    db, paths = _seeded_library(
        tmp_path,
        rows=(("pad.wav", 100.0, "loop"),),
    )
    old_path = paths["pad.wav"]
    kit_path = paths["pad.wav"]
    s = _user_session(tmp_path, db, kit_path=kit_path)
    controller = s.channel_rack
    pre = _state(
        "b2r-prune-pre",
        (
            Channel(
                channel_id="u_rebased",
                live_kit_group=None,
                live_kit_slot=None,
                sample_path=old_path,
            ),
        ),
    )
    controller.restore_state(pre)
    assert controller.user_metadata[old_path].source_bpm == 100.0
    new_path = _destination_copy(tmp_path, old_path)
    controller.stage_media_rebase_transfer(
        {old_path: new_path, "unrelated/old": new_path}
    )
    restored = _state(
        "b2r-prune",
        (
            Channel(
                channel_id="u_rebased",
                live_kit_group=None,
                live_kit_slot=None,
                sample_path=new_path,
            ),
        ),
    )
    controller.restore_state(restored)
    binding = controller.user_metadata
    entry = binding[new_path]
    assert entry.sample_class == "loop" and entry.source_bpm == 100.0
    assert old_path not in binding
    assert "unrelated/old" not in binding
    s.transport.close()
