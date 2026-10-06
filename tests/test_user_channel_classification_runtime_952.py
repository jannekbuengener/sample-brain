"""TEST_GATE / TEST FREEZE — #952 user-channel classification runtime slice.

Canonical authority:
- docs/USER_CHANNEL_CLASSIFICATION_AUTHORITY.md §4 (boundaries B1-B5), §5
  (invalidation / trigger precedence), §6 (PLAYBACK_CLASSIFICATION_FREEZE,
  PLAYBACK_MUTATION_APPLY_POLICY), §7 (observer semantics), §9 (projection), §10
  (frozen contract tests 6-20)
- docs/LOOP_ROW_PLAYBACK_CONTRACT.md (#920 / #926 playback owners)
- docs/SESSION_OWNERSHIP_CONTRACT.md
- Issue #952

Companion file (guards 1-5, green on current ``main``, never weakened):
``tests/test_user_channel_classification_authority_contract.py``.

This file freezes contract tests 6-20 plus the §4 B5 no-resolution boundary
guard. It pins the *production surface the implementation must expose*:

``src/workbench_user_sample_metadata.py`` (new, session-owned, only I/O owner)
- ``UserSampleMetadata(sample_class, source_bpm)`` — frozen record
- ``UserSampleMetadataBinding`` — immutable ``Mapping[str, UserSampleMetadata]``
  keyed by the **exact durable** ``Channel.sample_path`` string
- ``UserSampleMetadataResolver`` — ``resolve(paths)`` / ``resolve_one(path)``
- ``WorkbenchLibraryUserSampleMetadataResolver(*, library_db_path)``

``src/channel_rack.py`` / ``src/loop_rack_playback.py`` (keyword-only, default ``None``)
- ``sample_class_for_channel(channel, live_kit, *, user_metadata=None)``
- ``point_trigger_eligible_channel_ids(state, live_kit, *, user_metadata=None)``
- ``filter_pattern_for_point_trigger_playback(state, live_kit, *, user_metadata=None)``
- ``reconcile_live_kit_sample_assignments(state, live_kit, *, user_metadata=None)``
- ``build_loop_cycle_specs(..., user_metadata=None)`` — user ``source_bpm`` seam

``src/workbench_channel_rack.py``
- ``ChannelRackController(..., user_metadata_resolver=None)``
- ``.user_metadata`` — read-only derived binding
- ``.playback_classification_snapshot`` — read-only per-Play snapshot or ``None``
- ``.clear_user_channel_sample(channel_id)`` — named public clear operation
- ``.refresh_user_channel_metadata()`` — B4 explicit seam
- ``project_bottom_rack_for_qml(state, live_kit, *, user_metadata=None)``

``src/workbench_session.py``
- ``compose_workbench_session(..., library_db_path=...)`` injects the resolver.

Frozen invariants asserted here: exact-durable-path keying, one read-only
connection per boundary, reference-counted invalidation on shared paths,
binding trigger precedence (loop strips / ambiguous + one-shot preserve, never
re-seed), resolve-only silence, single-observer adoption, per-Play path+class
snapshot stability, atomic after-stop mutation apply, and bottom-Rack
classification through the single ``sample_class_for_channel`` consumption
point.

No private MCP, no runtime/Live-Go, no settings toggle (NOT_APPLICABLE).
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
import os
from contextlib import contextmanager
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from src.channel_rack import (
    ChannelRackState,
    classification_kind,
    filter_pattern_for_point_trigger_playback,
    is_point_trigger_safe,
    point_trigger_eligible_channel_ids,
    reconcile_live_kit_sample_assignments,
    sample_class_for_channel,
)
from src.gesture_pattern_core_composition import GesturePatternCoreComposition
from src.gesture_rack_integration import plan_gesture_rack_integration
from src.loop_rack_playback import build_loop_cycle_specs
from src.native_audio import (
    SB_MAX_VOICES,
    SB_VOICE_IDLE,
    SB_VOICE_PLAYING,
    SB_VOICE_SCHEDULED,
    VoiceConfig,
)
from src.pattern_core import Channel, Pattern, Trigger
from src.sequencer_pcm import SequencerPcmProvider
from src.session_grid import SessionTransport
from src.workbench_channel_rack import (
    ChannelRackController,
    project_bottom_rack_for_qml,
)
from src.workbench_controller import WorkbenchRow
from src.workbench_library import init_workbench_library, upsert_folder, upsert_sample
from src.workbench_live_kit import LiveKitState

REPO_ROOT = Path(__file__).resolve().parents[1]

PCM_FRAMES = 8
SAMPLE_RATE = 48_000
BPM = 120.0

ONESHOT_PATH = "user_oneshot.wav"
LOOP_PATH = "user_loop.wav"
AMBIGUOUS_PATH = "user_ambiguous.wav"
SECOND_ONESHOT_PATH = "user_oneshot_2.wav"

# Guard 20: #926 regression suites must stay green. Presence + non-vacuity here,
# actual green-ness is proven by running them in the CHECKS phase.
PROTECTED_SUITES = (
    "tests/test_channel_rack_loop_classification.py",
    "tests/test_workbench_channel_rack_loop.py",
    "tests/test_loop_rack_playback.py",
    "tests/test_workbench_session_catalog_rehydrate.py",
    "tests/test_workbench_session_persistence.py",
    "tests/test_workbench_qml_screen2_channel_rack.py",
)


# ---------------------------------------------------------------------------
# Production-surface accessors (repo precedent: _require / _controller_module)
#
# The new metadata module is imported lazily so a missing implementation fails
# each test individually instead of breaking collection for the whole file.
# ---------------------------------------------------------------------------


def _metadata_module():
    try:
        return importlib.import_module("src.workbench_user_sample_metadata")
    except ModuleNotFoundError:
        pytest.fail(
            "MISSING_PRODUCTION_SURFACE: src.workbench_user_sample_metadata"
        )


def _require(module, name: str):
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(f"MISSING_PRODUCTION_SURFACE: {module.__name__}.{name}")
    return value


def _metadata_class(name: str):
    return _require(_metadata_module(), name)


def _workbench_library_resolver(library_db_path: Path):
    cls = _metadata_class("WorkbenchLibraryUserSampleMetadataResolver")
    return cls(library_db_path=library_db_path)


def _binding(entries: dict[str, Any] | None = None):
    cls = _metadata_class("UserSampleMetadataBinding")
    if entries is None:
        return cls()
    return cls(entries)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _user_channel(channel_id: str, sample_path: str | None) -> Channel:
    return Channel(
        channel_id=channel_id,
        live_kit_group=None,
        live_kit_slot=None,
        sample_path=sample_path,
    )


def _kit_channel(channel_id: str, group: str, slot: str, path: str) -> Channel:
    return Channel(
        channel_id=channel_id,
        live_kit_group=group,
        live_kit_slot=slot,
        sample_path=path,
    )


def _pattern(triggers: tuple[Trigger, ...] = ()) -> Pattern:
    return Pattern(
        pattern_id="screen2-main",
        length_quarter_notes=Fraction(4, 1),
        triggers=triggers,
    )


def _state(channels: tuple[Channel, ...], triggers: tuple[Trigger, ...]) -> ChannelRackState:
    return ChannelRackState(
        channels=channels,
        pattern=_pattern(triggers),
        step_count=16,
    )


def _trigger(channel_id: str, step_index: int) -> Trigger:
    return Trigger(channel_id=channel_id, position=Fraction(step_index, 4))


def _channel(state: ChannelRackState, channel_id: str) -> Channel:
    for channel in state.channels:
        if channel.channel_id == channel_id:
            return channel
    raise AssertionError(f"unknown channel_id in state: {channel_id}")


def _triggers_for(state: ChannelRackState, channel_id: str) -> tuple[Trigger, ...]:
    return tuple(t for t in state.pattern.triggers if t.channel_id == channel_id)


def _last_user_channel_id(state: ChannelRackState) -> str:
    for channel in reversed(state.channels):
        if channel.live_kit_group is None and channel.live_kit_slot is None:
            return channel.channel_id
    raise AssertionError("state has no user channel")


def _pcm_for_path(_path: str):
    return SimpleNamespace(
        channels=1,
        samples=np.zeros(PCM_FRAMES, dtype=np.float32),
        sample_rate=SAMPLE_RATE,
    )


def _pcm_provider() -> SequencerPcmProvider:
    def decode_fn(path, *, sample_rate, start_ms=0):
        del path, start_ms
        return np.linspace(-0.2, 0.2, PCM_FRAMES, dtype=np.float32), int(sample_rate)

    return SequencerPcmProvider(sample_rate=SAMPLE_RATE, decode_fn=decode_fn)


def _specs(
    state: ChannelRackState,
    live_kit: LiveKitState,
    user_metadata: Any,
    *,
    sync_enabled: bool = False,
    master_bpm: float = BPM,
) -> tuple[Any, ...]:
    return build_loop_cycle_specs(
        state=state,
        live_kit=live_kit,
        pcm_for_path=_pcm_for_path,
        play_anchor_engine_frame=0,
        sync_enabled=sync_enabled,
        master_bpm=master_bpm,
        user_metadata=user_metadata,
    )


# ---------------------------------------------------------------------------
# Scripted resolver double
# ---------------------------------------------------------------------------


class _ScriptedResolver:
    """Deterministic in-memory stand-in for the library resolver.

    ``classes`` maps a durable path string to the raw library ``sample_class``.
    A path absent from ``classes`` models a catalog miss (no binding entry).
    A path present with ``None`` or a non-explicit class models a resolved but
    unclassifiable row (``ambiguous``).
    """

    def __init__(self, classes: dict[str, str | None] | None = None) -> None:
        self._classes: dict[str, str | None] = dict(classes or {})
        self._bpms: dict[str, float | None] = {}
        self.resolve_calls: list[tuple[str, ...]] = []
        self.resolve_one_calls: list[str] = []

    # -- test authoring helpers ------------------------------------------------
    def set_class(self, path: str, value: str | None) -> None:
        self._classes[path] = value

    def set_bpm(self, path: str, value: float | None) -> None:
        self._bpms[path] = value

    def call_count(self) -> int:
        return len(self.resolve_calls) + len(self.resolve_one_calls)

    def call_log(self) -> list[tuple[str, ...]]:
        """Every path batch handed to the resolver, in call order."""
        return [*self.resolve_calls, *self.resolve_one_calls]

    def paths_since(self, mark: int) -> tuple[str, ...]:
        """Ordered unique paths requested by calls recorded after ``mark``."""
        calls = self.call_log()[mark:]
        return tuple(dict.fromkeys(path for call in calls for path in call))

    def mark(self) -> int:
        return len(self.call_log())

    # -- resolver protocol -----------------------------------------------------
    def resolve(self, paths):
        ordered = tuple(dict.fromkeys(str(p) for p in paths if p))
        self.resolve_calls.append(ordered)
        metadata_cls = _metadata_class("UserSampleMetadata")
        binding_cls = _metadata_class("UserSampleMetadataBinding")
        entries = {}
        for path in ordered:
            if path not in self._classes:
                continue
            entries[path] = metadata_cls(
                sample_class=self._classes[path],
                source_bpm=self._bpms.get(path),
            )
        return binding_cls(entries)

    def resolve_one(self, path: str):
        self.resolve_one_calls.append(str(path))
        return self.resolve((str(path),)).get(str(path))


# ---------------------------------------------------------------------------
# Native engine / transport doubles
# ---------------------------------------------------------------------------


@dataclass
class _Snapshot:
    total_voice_count: int
    active_voice_count: int
    voice_ids: tuple[int, ...]
    voice_states: tuple[int, ...]


class _FakeEngine:
    """Minimal native engine double: scheduling bookkeeping only."""

    def __init__(self) -> None:
        self.create_calls: list[VoiceConfig] = []
        self.schedule_calls: list[tuple[int, int]] = []
        self.stop_voice_calls: list[int] = []
        self.remove_voice_calls: list[int] = []
        self._voices: dict[int, int] = {}
        self._next_id = 1

    def create_voice(self, config: VoiceConfig) -> int:
        self.create_calls.append(config)
        voice_id = self._next_id
        self._next_id += 1
        self._voices[voice_id] = SB_VOICE_IDLE
        return voice_id

    def schedule_voice_start(self, voice_id: int, engine_frame: int) -> None:
        self.schedule_calls.append((int(voice_id), int(engine_frame)))
        if voice_id in self._voices:
            self._voices[voice_id] = SB_VOICE_SCHEDULED

    def stop_voice(self, voice_id: int) -> None:
        self.stop_voice_calls.append(int(voice_id))
        if voice_id in self._voices:
            self._voices[voice_id] = SB_VOICE_IDLE

    def remove_voice(self, voice_id: int) -> None:
        self.remove_voice_calls.append(int(voice_id))
        self._voices.pop(int(voice_id), None)

    def advance_to(self, engine_frame: int) -> None:
        for voice_id, state in list(self._voices.items()):
            if state == SB_VOICE_SCHEDULED:
                self._voices[voice_id] = SB_VOICE_PLAYING
            del engine_frame, voice_id

    def get_snapshot(self) -> _Snapshot:
        ids = tuple(sorted(self._voices))
        states = [self._voices[vid] for vid in ids]
        pad = SB_MAX_VOICES - len(ids)
        if pad > 0:
            states.extend([SB_VOICE_IDLE] * pad)
        return _Snapshot(
            total_voice_count=len(self._voices),
            active_voice_count=sum(1 for s in states if s == SB_VOICE_PLAYING),
            voice_ids=ids,
            voice_states=tuple(states),
        )

    def snapshot(self) -> _Snapshot:
        return self.get_snapshot()


class _EngineTransport:
    """Transport facade for the Rack controller (engine + session clock)."""

    def __init__(
        self,
        engine: _FakeEngine,
        *,
        bpm: float = BPM,
        sync_enabled: bool = False,
    ) -> None:
        self._engine = engine
        self._core = SessionTransport(sample_rate=SAMPLE_RATE, bpm=bpm)
        self._sync_enabled = bool(sync_enabled)

    @property
    def tempo_map(self):
        return self._core.tempo_map

    @property
    def sample_rate(self) -> int:
        return self._core.sample_rate

    @property
    def session_frame(self) -> int:
        return self._core.session_frame

    @session_frame.setter
    def session_frame(self, value: int) -> None:
        self._core.session_frame = int(value)

    @property
    def engine_frame(self) -> int:
        return self._core.engine_frame

    @engine_frame.setter
    def engine_frame(self, value: int) -> None:
        self._core.engine_frame = int(value)

    def play(self) -> None:
        self._core.play()

    def stop(self) -> None:
        self._core.stop()

    def poll(self) -> None:
        return None

    def get_native_engine(self) -> _FakeEngine:
        return self._engine

    def is_native_available(self) -> bool:
        return True

    def is_sync_enabled(self) -> bool:
        return self._sync_enabled

    def set_sync_enabled(self, enabled: bool) -> None:
        self._sync_enabled = bool(enabled)

    def get_current_tempo(self) -> float:
        segment = self._core.tempo_map._segment_for_frame(self._core.session_frame)
        return float(segment.bpm)

    def set_tempo(self, bpm: float) -> int:
        return self._core.set_tempo(bpm)

    def advance(self, frames: int) -> None:
        if not self._core.playing:
            self._core.play()
        self._core.advance(int(frames))
        self._engine.advance_to(self._core.engine_frame)


def _controller(
    *,
    resolver: Any = None,
    state: ChannelRackState | None = None,
    live_kit: LiveKitState | None = None,
    observer: list[int] | None = None,
    sync_enabled: bool = False,
    bpm: float = BPM,
) -> tuple[ChannelRackController, _FakeEngine, _EngineTransport]:
    engine = _FakeEngine()
    transport = _EngineTransport(engine, bpm=bpm, sync_enabled=sync_enabled)
    notifications: list[int] = observer if observer is not None else []
    controller = ChannelRackController(
        live_kit=live_kit if live_kit is not None else LiveKitState(),
        transport=transport,
        pcm_provider=_pcm_provider(),
        lookahead_frames=4800,
        user_metadata_resolver=resolver,
        on_musical_state_changed=lambda: notifications.append(1),
    )
    if state is not None:
        controller.restore_state(state)
    return controller, engine, transport


def _controller_with_assignment(
    resolver: Any,
    path: str,
) -> tuple[ChannelRackController, str]:
    """Controller with one materialized user channel holding ``path``."""
    controller, _engine, _transport = _controller(resolver=resolver)
    controller.ensure_state()
    controller.add_user_channel()
    channel_id = _last_user_channel_id(controller.state)
    controller.assign_user_channel_sample(channel_id, path)
    return controller, channel_id


# ---------------------------------------------------------------------------
# Real library fixture helpers (B1 / keying tests)
# ---------------------------------------------------------------------------


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


def _seed_library_sample(
    *,
    library_db: Path,
    folder: Path,
    name: str,
    bpm: float | None,
    sample_class: str | None,
) -> str:
    folder.mkdir(parents=True, exist_ok=True)
    audio = folder / name
    audio.write_bytes(b"RIFF" + b"\x00" * 40)
    resolved = str(audio.resolve())
    stat = audio.stat()
    folder_id = upsert_folder(folder, db_path=library_db)
    upsert_sample(
        folder_id,
        _library_row(name, resolved, bpm=bpm, sample_class=sample_class),
        size_bytes=int(stat.st_size),
        mtime_ns=int(stat.st_mtime_ns),
        db_path=library_db,
    )
    return resolved


@dataclass
class _SeededLibrary:
    db: Path
    folder: Path
    oneshot: str
    oneshot_bpm: float
    loop: str
    loop_bpm: float
    stale: str


def _seeded_library(tmp_path: Path) -> _SeededLibrary:
    db = tmp_path / "library.db"
    init_workbench_library(db)
    folder = tmp_path / "samples"
    oneshot_bpm = 128.0
    loop_bpm = 100.0
    oneshot = _seed_library_sample(
        library_db=db,
        folder=folder,
        name="kick.wav",
        bpm=oneshot_bpm,
        sample_class="one_shot",
    )
    loop = _seed_library_sample(
        library_db=db,
        folder=folder,
        name="pad.wav",
        bpm=loop_bpm,
        sample_class="loop",
    )
    stale = _seed_library_sample(
        library_db=db,
        folder=folder,
        name="stale.wav",
        bpm=90.0,
        sample_class="loop",
    )
    # Fingerprint gate: mutate the file so the cached row is a catalog miss.
    (folder / "stale.wav").write_bytes(b"RIFF" + b"\x01" * 64)
    return _SeededLibrary(
        db=db,
        folder=folder,
        oneshot=oneshot,
        oneshot_bpm=oneshot_bpm,
        loop=loop,
        loop_bpm=loop_bpm,
        stale=stale,
    )


def _library_dir_fingerprint(db_path: Path) -> dict[str, object]:
    parent = db_path.parent
    names = sorted(p.name for p in parent.iterdir())
    hashes = {}
    for name in names:
        path = parent / name
        if path.is_file():
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"names": names, "hashes": hashes}


@contextmanager
def _counted_readonly_opens(monkeypatch: pytest.MonkeyPatch):
    """Count read-only library connection opens, regardless of import form.

    The resolver module may either reference the seam through the
    ``workbench_library`` module object or import the symbol directly, so the
    patch target is resolved by identity.
    """
    from src import workbench_library as library_module

    resolver_module = _metadata_module()
    target = (
        resolver_module
        if hasattr(resolver_module, "workbench_library_readonly_connection")
        else library_module
    )
    real = getattr(target, "workbench_library_readonly_connection")
    counter = {"n": 0}

    @contextmanager
    def _counting(*args, **kwargs):
        counter["n"] += 1
        with real(*args, **kwargs) as conn:
            yield conn

    monkeypatch.setattr(target, "workbench_library_readonly_connection", _counting)
    yield counter


# ===========================================================================
# Contract test 6 — resolver-absent vs resolver-present equivalence
# ===========================================================================


def test_6_resolver_absent_matches_resolver_present_without_evidence() -> None:
    """No resolver, or a resolver with no library evidence, changes nothing."""
    kit = LiveKitState()
    suggestive = "C:/Loops/Drum_Loop_120bpm_Oneshot/Kick_Loop.wav"
    channel = _user_channel("ch_user_1", suggestive)
    state = _state((channel,), (_trigger(channel.channel_id, 0),))

    without, _e1, _t1 = _controller(resolver=None, state=state)
    empty_resolver = _ScriptedResolver({})
    with_empty, _e2, _t2 = _controller(resolver=empty_resolver, state=state)

    assert len(without.user_metadata) == 0
    assert dict(with_empty.user_metadata) == dict(without.user_metadata)
    assert without.state == with_empty.state == state
    assert without.projection() == with_empty.projection()

    for controller in (without, with_empty):
        binding = controller.user_metadata
        channel_obj = _channel(controller.state, channel.channel_id)
        assert sample_class_for_channel(channel_obj, kit, user_metadata=binding) is None
        assert (
            classification_kind(
                sample_class_for_channel(channel_obj, kit, user_metadata=binding)
            )
            == "ambiguous"
        )
        assert point_trigger_eligible_channel_ids(
            controller.state, kit, user_metadata=binding
        ) == frozenset()
        assert _specs(controller.state, kit, binding) == ()
        # Persisted triggers survive fail-closed classification.
        assert _triggers_for(controller.state, channel.channel_id) == (
            _trigger(channel.channel_id, 0),
        )


def test_6b_binding_parameters_are_keyword_only_and_default_none() -> None:
    """Threading must stay backwards compatible with frozen guards 1-5."""
    for func in (
        sample_class_for_channel,
        point_trigger_eligible_channel_ids,
        filter_pattern_for_point_trigger_playback,
        reconcile_live_kit_sample_assignments,
    ):
        parameter = inspect.signature(func).parameters["user_metadata"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, func.__name__
        assert parameter.default is None, func.__name__

    for func in (build_loop_cycle_specs, project_bottom_rack_for_qml):
        parameter = inspect.signature(func).parameters["user_metadata"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, func.__name__
        assert parameter.default is None, func.__name__

    init_parameter = inspect.signature(ChannelRackController.__init__).parameters[
        "user_metadata_resolver"
    ]
    assert init_parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert init_parameter.default is None


# ===========================================================================
# Contract test 7 — exact durable path keying, stale key is ambiguous
# ===========================================================================


def test_7_binding_is_keyed_by_the_exact_durable_path_string(tmp_path: Path) -> None:
    library = _seeded_library(tmp_path)
    resolver = _workbench_library_resolver(library.db)

    canonical = library.oneshot
    raw = os.path.join(str(library.folder), ".", "kick.wav")
    assert raw != canonical, "test requires a non-canonical raw spelling"

    binding = resolver.resolve((raw,))

    assert list(binding) == [raw]
    assert raw in binding
    metadata = binding[raw]
    assert metadata.sample_class == "one_shot"
    assert metadata.source_bpm == pytest.approx(library.oneshot_bpm)
    # Canonicalization stays private to workbench_library: the binding key is
    # the raw durable string, never a normalized one.
    assert canonical not in binding
    assert binding.get(canonical) is None
    assert resolver.resolve_one(raw) == metadata


def test_7b_stale_binding_key_is_ambiguous_and_fails_closed(tmp_path: Path) -> None:
    library = _seeded_library(tmp_path)
    resolver = _workbench_library_resolver(library.db)
    kit = LiveKitState()

    binding = resolver.resolve((library.oneshot,))
    # Channel holds a different spelling than the durable binding key: stale key.
    stale_channel = _user_channel("ch_user_1", library.loop)
    state = _state((stale_channel,), (_trigger(stale_channel.channel_id, 3),))

    resolved = sample_class_for_channel(stale_channel, kit, user_metadata=binding)
    assert resolved is None
    assert classification_kind(resolved) == "ambiguous"
    assert (
        stale_channel.channel_id
        not in point_trigger_eligible_channel_ids(state, kit, user_metadata=binding)
    )
    assert _specs(state, kit, binding) == ()


def test_7c_binding_is_an_immutable_mapping(tmp_path: Path) -> None:
    library = _seeded_library(tmp_path)
    resolver = _workbench_library_resolver(library.db)
    binding = resolver.resolve((library.oneshot, library.loop))

    assert isinstance(binding, object)
    assert len(binding) == 2
    assert dict(binding) == {
        library.oneshot: binding[library.oneshot],
        library.loop: binding[library.loop],
    }
    assert not hasattr(binding, "__setitem__"), "binding must be immutable"
    assert not hasattr(binding, "__delitem__"), "binding must be immutable"
    with pytest.raises(TypeError):
        binding["new"] = binding[library.oneshot]  # type: ignore[index]


# ===========================================================================
# Contract test 8 — B1 restore: one read-only connection, never writes
# ===========================================================================


def test_8_restore_resolves_all_paths_through_one_readonly_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.workbench_library as workbench_library

    library = _seeded_library(tmp_path)
    channels = (
        _user_channel("ch_user_1", library.oneshot),
        _user_channel("ch_user_2", library.loop),
        _user_channel("ch_user_3", library.stale),
    )
    state = _state(channels, (_trigger("ch_user_1", 0),))
    observer: list[int] = []
    before = _library_dir_fingerprint(library.db)

    snapshot_dirs = {"n": 0}
    real_td = workbench_library.tempfile.TemporaryDirectory

    def _counting_td(*args, **kwargs):
        snapshot_dirs["n"] += 1
        return real_td(*args, **kwargs)

    monkeypatch.setattr(workbench_library.tempfile, "TemporaryDirectory", _counting_td)
    with _counted_readonly_opens(monkeypatch) as opens:
        controller, _engine, _transport = _controller(
            resolver=_workbench_library_resolver(library.db),
            state=state,
            observer=observer,
        )

    assert opens["n"] <= 1, "restore must not open one connection per path"
    assert snapshot_dirs["n"] <= 1
    binding = controller.user_metadata
    assert binding[library.oneshot].sample_class == "one_shot"
    assert binding[library.oneshot].source_bpm == pytest.approx(library.oneshot_bpm)
    assert binding[library.loop].sample_class == "loop"
    assert binding[library.loop].source_bpm == pytest.approx(library.loop_bpm)
    # Stale fingerprint degrades to ambiguous with no binding entry.
    assert library.stale not in binding
    assert binding.get(library.stale) is None
    # Restore resolves before observers are wired: resume writes nothing.
    assert observer == []
    assert _library_dir_fingerprint(library.db) == before
    assert controller.state == state


# ===========================================================================
# Contract test 9 — B2 assign gates both playback paths
# ===========================================================================


def test_9_assign_resolves_and_gates_both_playback_paths() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot", LOOP_PATH: "loop"})
    resolver.set_bpm(LOOP_PATH, 100.0)
    controller, _engine, _transport = _controller(resolver=resolver)
    controller.ensure_state()
    kit = controller.live_kit

    controller.add_user_channel()
    oneshot_id = _last_user_channel_id(controller.state)
    state = controller.assign_user_channel_sample(oneshot_id, ONESHOT_PATH)
    binding = controller.user_metadata
    assert binding[ONESHOT_PATH].sample_class == "one_shot"
    assert oneshot_id in point_trigger_eligible_channel_ids(
        state, kit, user_metadata=binding
    )
    assert oneshot_id not in [spec.channel_id for spec in _specs(state, kit, binding)]

    controller.add_user_channel()
    loop_id = _last_user_channel_id(controller.state)
    state = controller.assign_user_channel_sample(loop_id, LOOP_PATH)
    binding = controller.user_metadata
    assert binding[LOOP_PATH].sample_class == "loop"
    assert binding[LOOP_PATH].source_bpm == pytest.approx(100.0)
    assert loop_id not in point_trigger_eligible_channel_ids(
        state, kit, user_metadata=binding
    )
    assert [spec.channel_id for spec in _specs(state, kit, binding)] == [loop_id]

    controller.add_user_channel()
    miss_id = _last_user_channel_id(controller.state)
    state = controller.assign_user_channel_sample(miss_id, "missing_library.wav")
    binding = controller.user_metadata
    assert "missing_library.wav" not in binding
    assert miss_id not in point_trigger_eligible_channel_ids(
        state, kit, user_metadata=binding
    )
    assert miss_id not in [spec.channel_id for spec in _specs(state, kit, binding)]


# ===========================================================================
# Contract test 10 — replacement invalidation + trigger precedence
# ===========================================================================


def test_10a_replacement_drops_old_binding_and_applies_trigger_precedence() -> None:
    resolver = _ScriptedResolver(
        {
            ONESHOT_PATH: "one_shot",
            LOOP_PATH: "loop",
            AMBIGUOUS_PATH: "text",
            SECOND_ONESHOT_PATH: "one_shot",
        }
    )

    # (1) one-shot -> explicit loop strips the stale point triggers.
    controller, oneshot_id = _controller_with_assignment(resolver, ONESHOT_PATH)
    kit = controller.live_kit
    assert _triggers_for(controller.state, oneshot_id) != ()

    state = controller.assign_user_channel_sample(oneshot_id, LOOP_PATH)
    binding = controller.user_metadata
    assert ONESHOT_PATH not in binding, "replaced path must never serve again"
    assert binding[LOOP_PATH].sample_class == "loop"
    assert _triggers_for(state, oneshot_id) == ()
    channel = _channel(state, oneshot_id)
    resolved = sample_class_for_channel(channel, kit, user_metadata=binding)
    assert resolved == "loop"
    assert is_point_trigger_safe(resolved) is False
    assert oneshot_id not in point_trigger_eligible_channel_ids(
        state, kit, user_metadata=binding
    )
    assert [spec.channel_id for spec in _specs(state, kit, binding)] == [oneshot_id]

    # (2)/(3) -> ambiguous and -> one-shot preserve triggers bit-identically and
    # never re-seed DEFAULT_ON.
    for target in (AMBIGUOUS_PATH, SECOND_ONESHOT_PATH):
        resolver_case = _ScriptedResolver({ONESHOT_PATH: "one_shot", target: "text"})
        case_controller, case_id = _controller_with_assignment(
            resolver_case, ONESHOT_PATH
        )
        # Hand-edited pattern: DEFAULT_ON minus step 3.
        case_controller.toggle_step(case_id, 3)
        hand_edited = case_controller.state.pattern.triggers
        assert len(hand_edited) == 15

        state = case_controller.assign_user_channel_sample(case_id, target)
        binding = case_controller.user_metadata

        assert state.pattern.triggers == hand_edited, (
            f"replacement to {target!r} must preserve triggers bit-identical"
        )
        assert len(state.pattern.triggers) == 15, "no DEFAULT_ON re-seed"
        assert ONESHOT_PATH not in binding
        resolved = sample_class_for_channel(
            _channel(state, case_id), case_controller.live_kit, user_metadata=binding
        )
        assert classification_kind(resolved) == (
            "ambiguous" if target == AMBIGUOUS_PATH else "oneshot"
        )


def test_10b_replacement_during_rack_play_is_queued() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot", LOOP_PATH: "loop"})
    controller, channel_id = _controller_with_assignment(resolver, ONESHOT_PATH)
    controller.play()
    assert controller.is_playing is True
    before = controller.state
    observer_before = None

    state = controller.assign_user_channel_sample(channel_id, LOOP_PATH)

    # Durable part is queued; the running Play keeps its own classification.
    assert controller.state is before
    assert _channel(state, channel_id).sample_path == ONESHOT_PATH
    assert LOOP_PATH not in controller.user_metadata
    assert controller.is_playing is True
    assert controller._frozen_loop_specs == ()
    del observer_before

    controller.stop()

    assert _channel(controller.state, channel_id).sample_path == LOOP_PATH
    assert controller.user_metadata[LOOP_PATH].sample_class == "loop"
    assert ONESHOT_PATH not in controller.user_metadata


# ===========================================================================
# Contract test 11 — clear_user_channel_sample semantics
# ===========================================================================


def test_11a_clear_drops_association_preserves_triggers_and_notifies_once() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot", SECOND_ONESHOT_PATH: "one_shot"})
    observer: list[int] = []
    controller, _engine, _transport = _controller(
        resolver=resolver, observer=observer
    )
    controller.ensure_state()
    controller.add_user_channel()
    channel_id = _last_user_channel_id(controller.state)
    controller.assign_user_channel_sample(channel_id, ONESHOT_PATH)
    controller.add_user_channel()
    other_id = _last_user_channel_id(controller.state)
    controller.assign_user_channel_sample(other_id, SECOND_ONESHOT_PATH)
    kit = controller.live_kit

    kept_triggers = _triggers_for(controller.state, channel_id)
    other_triggers = _triggers_for(controller.state, other_id)
    observer.clear()

    state = controller.clear_user_channel_sample(channel_id)

    assert _channel(state, channel_id).sample_path is None
    assert ONESHOT_PATH not in controller.user_metadata
    assert _triggers_for(state, channel_id) == kept_triggers
    assert _triggers_for(state, other_id) == other_triggers
    assert observer == [0], "clear fires the musical-state observer exactly once"
    # Non-bearing: excluded from both playback paths.
    assert channel_id not in point_trigger_eligible_channel_ids(
        state, kit, user_metadata=controller.user_metadata
    )
    assert channel_id not in [spec.channel_id for spec in _specs(state, kit, controller.user_metadata)]
    assert other_id in point_trigger_eligible_channel_ids(
        state, kit, user_metadata=controller.user_metadata
    )


def test_11b_clear_rejects_and_no_ops_without_mutation_or_resolution() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot"})
    observer: list[int] = []
    kit = LiveKitState()
    kit.assign("Kick + Bass", "Kick", _library_row("kick.wav", "kit/kick.wav", bpm=120.0, sample_class="one_shot"))
    controller, _engine, _transport = _controller(
        resolver=resolver, live_kit=kit, observer=observer
    )
    state = _state(
        (_kit_channel("ch_kick", "Kick + Bass", "Kick", "kit/kick.wav"),),
        (_trigger("ch_kick", 0),),
    )
    controller.restore_state(state)
    controller.ensure_state(notify=False)

    before_state = controller.state
    before_calls = resolver.call_count()
    observer.clear()

    with pytest.raises(ValueError):
        controller.clear_user_channel_sample("ch_does_not_exist")
    assert controller.state is before_state
    assert resolver.call_count() == before_calls, "rejected clear must not resolve"
    assert observer == []

    with pytest.raises(ValueError):
        controller.clear_user_channel_sample("ch_kick")
    assert controller.state is before_state
    assert resolver.call_count() == before_calls
    assert observer == []

    controller.add_user_channel()
    empty_id = _last_user_channel_id(controller.state)
    before_empty = controller.state
    calls_before_empty = resolver.call_count()
    observer.clear()

    returned = controller.clear_user_channel_sample(empty_id)

    assert returned is before_empty
    assert controller.state is before_empty, "already-empty clear is a no-op"
    assert resolver.call_count() == calls_before_empty, "no-op must not resolve"
    assert observer == []


def test_11c_shared_path_binding_survives_for_the_survivor() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot"})
    controller, first_id = _controller_with_assignment(resolver, ONESHOT_PATH)
    controller.add_user_channel(sample_path=ONESHOT_PATH)
    second_id = _last_user_channel_id(controller.state)
    assert first_id != second_id
    kit = controller.live_kit
    assert set(controller.user_metadata) == {ONESHOT_PATH}

    state = controller.clear_user_channel_sample(first_id)

    assert ONESHOT_PATH in controller.user_metadata, "survivor keeps the entry"
    assert controller.user_metadata[ONESHOT_PATH].sample_class == "one_shot"
    assert _channel(state, second_id).sample_path == ONESHOT_PATH
    assert second_id in point_trigger_eligible_channel_ids(
        state, kit, user_metadata=controller.user_metadata
    )
    assert [
        spec.channel_id
        for spec in _specs(state, kit, controller.user_metadata)
        if spec.channel_id == second_id
    ] == [second_id]


# ===========================================================================
# Contract test 12 — user-channel reconcile precedence
# ===========================================================================


def test_12_explicit_loop_reconciles_stale_user_triggers_once() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot"})
    observer: list[int] = []
    controller, channel_id = _controller_with_assignment(resolver, ONESHOT_PATH)
    controller.set_on_musical_state_changed(lambda: observer.append(1))
    assert _triggers_for(controller.state, channel_id) != ()
    observer.clear()

    resolver.set_class(ONESHOT_PATH, "loop")

    assert controller.reconcile_live_kit_state() is True
    assert _triggers_for(controller.state, channel_id) == ()
    assert observer == [1]

    # Deterministic once: a second reconcile has nothing left to heal.
    assert controller.reconcile_live_kit_state() is False
    assert observer == [1]


def test_12b_ambiguous_preserves_and_oneshot_never_reseeds() -> None:
    for resolved_class, seeded in (("text", True), ("one_shot", False)):
        resolver = _ScriptedResolver({ONESHOT_PATH: resolved_class})
        observer: list[int] = []
        controller, channel_id = _controller_with_assignment(resolver, ONESHOT_PATH)
        if not seeded:
            # Hand-edited all-off pattern must survive an explicit one-shot.
            for step in range(16):
                controller.toggle_step(channel_id, step)
            assert _triggers_for(controller.state, channel_id) == ()
        persisted = controller.state.pattern.triggers
        controller.set_on_musical_state_changed(lambda: observer.append(1))
        observer.clear()

        assert controller.reconcile_live_kit_state() is False
        assert controller.state.pattern.triggers == persisted
        assert observer == [], f"{resolved_class!r} must not notify"


# ===========================================================================
# Contract test 13 — observer / autosave semantics
# ===========================================================================


def test_13_resolve_only_is_silent_and_loop_strip_notifies_exactly_once() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot", LOOP_PATH: "loop"})
    observer: list[int] = []
    controller, channel_id = _controller_with_assignment(resolver, ONESHOT_PATH)
    controller.set_on_musical_state_changed(lambda: observer.append(1))
    observer.clear()

    # B4 refresh with unchanged library evidence: resolve-only, no state change.
    binding = controller.refresh_user_channel_metadata()
    assert binding[ONESHOT_PATH].sample_class == "one_shot"
    assert _triggers_for(controller.state, channel_id) != ()
    assert observer == [], "resolve-only must not fire observer or autosave"

    # B4 refresh that changes classification: resolve + strip = one observer call.
    resolver.set_class(ONESHOT_PATH, "loop")
    binding = controller.refresh_user_channel_metadata()
    assert binding[ONESHOT_PATH].sample_class == "loop"
    assert _triggers_for(controller.state, channel_id) == ()
    assert observer == [1]

    # Still exactly one for a redundant refresh.
    controller.refresh_user_channel_metadata()
    assert observer == [1]


# ===========================================================================
# Contract test 14 — SYNC-on user loop uses the bound source BPM
# ===========================================================================


def test_14_user_loop_sync_uses_bound_source_bpm_or_fails_closed() -> None:
    kit = LiveKitState()
    channel = _user_channel("ch_user_1", LOOP_PATH)
    state = _state((channel,), ())
    resolver = _ScriptedResolver({LOOP_PATH: "loop"})

    resolver.set_bpm(LOOP_PATH, 100.0)
    binding = resolver.resolve((LOOP_PATH,))
    specs = _specs(state, kit, binding, sync_enabled=True, master_bpm=100.0)
    assert [spec.channel_id for spec in specs] == [channel.channel_id]
    assert specs[0].source_bpm == pytest.approx(100.0)
    assert specs[0].playback_rate == pytest.approx(1.0)
    assert specs[0].sample_path == LOOP_PATH

    resolver.set_bpm(LOOP_PATH, 50.0)
    specs = _specs(state, kit, resolver.resolve((LOOP_PATH,)), sync_enabled=True, master_bpm=100.0)
    assert specs[0].playback_rate == pytest.approx(2.0)

    for invalid in (None, 0.0, -100.0):
        resolver.set_bpm(LOOP_PATH, invalid)
        binding = resolver.resolve((LOOP_PATH,))
        assert (
            _specs(state, kit, binding, sync_enabled=True, master_bpm=100.0) == ()
        ), f"source_bpm={invalid!r} must stay fail-closed"

    # SYNC off keeps the default playback rate path unchanged.
    resolver.set_bpm(LOOP_PATH, None)
    specs = _specs(state, kit, resolver.resolve((LOOP_PATH,)), sync_enabled=False)
    assert [spec.channel_id for spec in specs] == [channel.channel_id]
    assert specs[0].playback_rate == pytest.approx(1.0)


def test_14b_user_channel_loop_without_binding_stays_fail_closed() -> None:
    kit = LiveKitState()
    channel = _user_channel("ch_user_1", LOOP_PATH)
    state = _state((channel,), ())
    assert _specs(state, kit, _binding(), sync_enabled=False) == ()
    assert _specs(state, kit, None, sync_enabled=False) == ()


# ===========================================================================
# Contract test 15 — B3 gesture delta only
# ===========================================================================


def test_15_gesture_apply_resolves_only_the_introduced_or_changed_paths() -> None:
    resolver = _ScriptedResolver(
        {
            "base_kept.wav": "one_shot",
            "base_changed.wav": "one_shot",
            "gesture_a.wav": "one_shot",
            "gesture_b.wav": "loop",
        }
    )
    observer: list[int] = []
    base_channels = (
        _user_channel("ch_user_1", "base_kept.wav"),
        _user_channel("ch_user_2", "base_changed.wav"),
    )
    base = _state(base_channels, (_trigger("ch_user_1", 0),))
    controller, _engine, _transport = _controller(
        resolver=resolver, state=base, observer=observer
    )
    assert set(controller.user_metadata) == {"base_kept.wav", "base_changed.wav"}
    preserved = dict(controller.user_metadata)
    mark = resolver.mark()
    observer.clear()

    composition = GesturePatternCoreComposition(
        channels=(
            _user_channel("ch_user_3", "gesture_a.wav"),
            _user_channel("ch_user_4", "gesture_b.wav"),
        ),
        pattern=Pattern(
            pattern_id="gesture-pat-1",
            length_quarter_notes=Fraction(8, 1),
            triggers=(
                _trigger("ch_user_3", 0),
                _trigger("ch_user_4", 0),
            ),
        ),
    )
    plan = plan_gesture_rack_integration(
        controller.state, composition, allow_pattern_replacement=True
    )
    assert plan.ready_for_apply is True

    state = controller.apply_gesture_integration_plan(plan, feature_enabled=True)

    # Delta only: the two gesture-introduced paths, never the base paths.
    assert resolver.paths_since(mark) == ("gesture_a.wav", "gesture_b.wav")

    binding = controller.user_metadata
    for path, metadata in preserved.items():
        assert binding[path] == metadata, "preserved base binding must be identical"
    assert binding["gesture_a.wav"].sample_class == "one_shot"
    assert binding["gesture_b.wav"].sample_class == "loop"
    assert observer == [0], "gesture apply keeps the single-observer guarantee"
    assert "ch_user_3" in point_trigger_eligible_channel_ids(
        state, controller.live_kit, user_metadata=binding
    )
    assert "ch_user_3" not in [
        spec.channel_id for spec in _specs(state, controller.live_kit, binding)
    ]


# ===========================================================================
# Contract test 16 — resolution boundaries
# ===========================================================================


def test_16_creation_and_assignment_are_resolution_boundaries() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot", LOOP_PATH: "loop"})
    observer: list[int] = []
    controller, _engine, _transport = _controller(resolver=resolver)
    controller.set_on_musical_state_changed(lambda: observer.append(1))

    # B5: materializing state resolves nothing.
    controller.ensure_state()
    assert resolver.call_count() == 0

    # add_user_channel() with no path resolves nothing.
    controller.add_user_channel()
    channel_id = _last_user_channel_id(controller.state)
    assert resolver.call_count() == 0
    assert channel_id not in controller.user_metadata

    # add_user_channel(sample_path=...) is a boundary.
    mark = resolver.mark()
    controller.add_user_channel(sample_path=ONESHOT_PATH)
    added_id = _last_user_channel_id(controller.state)
    assert resolver.call_count() == mark + 1
    assert resolver.paths_since(mark) == (ONESHOT_PATH,)
    assert controller.user_metadata[ONESHOT_PATH].sample_class == "one_shot"

    # assign_user_channel_sample is a boundary (empty -> path).
    mark = resolver.mark()
    controller.assign_user_channel_sample(channel_id, LOOP_PATH)
    assert resolver.call_count() == mark + 1
    assert resolver.paths_since(mark) == (LOOP_PATH,)
    assert controller.user_metadata[LOOP_PATH].sample_class == "loop"

    # Same-path re-assign resolves nothing.
    before = resolver.call_count()
    state = controller.assign_user_channel_sample(channel_id, LOOP_PATH)
    assert controller.state is state
    assert resolver.call_count() == before

    # Empty / whitespace paths are rejected without resolving.
    for invalid in ("", "   "):
        with pytest.raises(ValueError):
            controller.assign_user_channel_sample(channel_id, invalid)
    assert resolver.call_count() == before
    assert added_id != channel_id


# ===========================================================================
# Contract test 17 — PLAYBACK_CLASSIFICATION_FREEZE
# ===========================================================================


def test_17a_path_replacement_mid_play_is_frozen_until_next_rack_play() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot", LOOP_PATH: "loop"})
    resolver.set_bpm(LOOP_PATH, 100.0)
    controller, channel_id = _controller_with_assignment(resolver, ONESHOT_PATH)
    controller.play()
    assert controller.is_playing is True
    play_handle = controller._play_handle
    anchor = controller._loop_anchor_engine_frame
    snapshot = controller.playback_classification_snapshot
    assert snapshot is not None
    assert snapshot[channel_id] == (ONESHOT_PATH, "one_shot", None)

    state = controller.assign_user_channel_sample(channel_id, LOOP_PATH)

    # No mid-Play retarget, no path-key miss, no stop/restart.
    assert controller.is_playing is True
    assert controller._play_handle is play_handle
    assert controller._loop_anchor_engine_frame == anchor
    assert controller._frozen_loop_specs == ()
    assert controller.playback_classification_snapshot == snapshot
    assert _channel(state, channel_id).sample_path == ONESHOT_PATH
    assert LOOP_PATH not in controller.user_metadata

    controller.stop()
    controller.play()

    assert _channel(controller.state, channel_id).sample_path == LOOP_PATH
    new_snapshot = controller.playback_classification_snapshot
    assert new_snapshot is not None
    assert new_snapshot[channel_id] == (LOOP_PATH, "loop", 100.0)
    assert [spec.sample_path for spec in controller._frozen_loop_specs] == [LOOP_PATH]


def test_17b_path_clear_mid_play_is_frozen_until_next_rack_play() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot", LOOP_PATH: "loop"})
    controller, channel_id = _controller_with_assignment(resolver, ONESHOT_PATH)
    controller.play()
    play_handle = controller._play_handle
    snapshot = controller.playback_classification_snapshot
    assert snapshot is not None

    controller.clear_user_channel_sample(channel_id)

    assert controller.is_playing is True
    assert controller._play_handle is play_handle
    assert controller.playback_classification_snapshot == snapshot
    assert ONESHOT_PATH in controller.user_metadata

    controller.stop()
    controller.play()

    assert _channel(controller.state, channel_id).sample_path is None
    final = controller.playback_classification_snapshot
    assert final is not None
    assert channel_id not in final, "non-bearing channel is not audible"


def test_17c_step_toggle_mid_play_stays_immediately_audible() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot"})
    controller, channel_id = _controller_with_assignment(resolver, ONESHOT_PATH)
    controller.play()
    for step in range(16):
        controller.toggle_step(channel_id, step)
    assert _triggers_for(controller.state, channel_id) == ()

    state = controller.toggle_step(channel_id, 6)

    assert _triggers_for(state, channel_id) == (_trigger(channel_id, 6),)
    assert controller.is_playing is True
    snapshot = controller.playback_classification_snapshot
    assert snapshot is not None
    assert snapshot[channel_id][0] == ONESHOT_PATH, "path+class stay per-Play stable"


def test_17d_frozen_snapshot_freezes_path_and_class_together() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot", LOOP_PATH: "loop"})
    controller, channel_id = _controller_with_assignment(resolver, ONESHOT_PATH)
    controller.play()
    snapshot = controller.playback_classification_snapshot
    assert snapshot is not None
    frozen_path, frozen_class, _frozen_bpm = snapshot[channel_id]
    assert frozen_path == ONESHOT_PATH
    assert frozen_class == "one_shot"

    controller.stop()
    controller.assign_user_channel_sample(channel_id, LOOP_PATH)
    assert controller.playback_classification_snapshot is None

    controller.play()
    next_snapshot = controller.playback_classification_snapshot
    assert next_snapshot is not None
    assert next_snapshot[channel_id] != (frozen_path, frozen_class, None)


# ===========================================================================
# Contract test 18 — PLAYBACK_MUTATION_APPLY_POLICY
# ===========================================================================


def test_18a_replacement_mid_play_applies_nothing_until_after_stop() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot", LOOP_PATH: "loop"})
    observer: list[int] = []
    controller, channel_id = _controller_with_assignment(resolver, ONESHOT_PATH)
    controller.set_on_musical_state_changed(lambda: observer.append(1))
    controller.play()
    play_handle = controller._play_handle
    before_state = controller.state
    triggers_before = _triggers_for(controller.state, channel_id)
    assert triggers_before != ()
    observer.clear()

    state = controller.assign_user_channel_sample(channel_id, LOOP_PATH)

    # Nothing durable mid-Play: path, binding, and trigger strip all queued.
    assert controller.state is before_state
    assert _channel(controller.state, channel_id).sample_path == ONESHOT_PATH
    assert _triggers_for(controller.state, channel_id) == triggers_before
    assert LOOP_PATH not in controller.user_metadata
    assert observer == [], "no persistence may happen mid-Play"
    assert controller.is_playing is True
    assert controller._play_handle is play_handle
    assert controller._frozen_loop_specs == ()

    controller.stop()

    assert observer == [1], "queued mutation lands in exactly one observer call"
    assert _channel(controller.state, channel_id).sample_path == LOOP_PATH
    assert _triggers_for(controller.state, channel_id) == ()
    binding = controller.user_metadata
    assert binding[LOOP_PATH].sample_class == "loop"
    assert ONESHOT_PATH not in binding


def test_18b_refresh_mid_play_applies_atomically_after_stop() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot"})
    observer: list[int] = []
    controller, channel_id = _controller_with_assignment(resolver, ONESHOT_PATH)
    controller.set_on_musical_state_changed(lambda: observer.append(1))
    controller.play()
    triggers_before = _triggers_for(controller.state, channel_id)
    assert triggers_before != ()
    observer.clear()

    resolver.set_class(ONESHOT_PATH, "loop")
    binding = controller.refresh_user_channel_metadata()

    assert binding[ONESHOT_PATH].sample_class == "one_shot", (
        "mid-Play refresh must not change live classification"
    )
    assert _triggers_for(controller.state, channel_id) == triggers_before
    assert observer == []
    assert controller.is_playing is True
    assert controller._frozen_loop_specs == ()

    controller.stop()

    assert observer == [1]
    assert controller.user_metadata[ONESHOT_PATH].sample_class == "loop"
    assert _triggers_for(controller.state, channel_id) == ()


def test_18c_queued_mutation_applies_at_next_rack_play_before_its_anchor() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot", LOOP_PATH: "loop"})
    observer: list[int] = []
    controller, channel_id = _controller_with_assignment(resolver, ONESHOT_PATH)
    controller.set_on_musical_state_changed(lambda: observer.append(1))
    controller.play()
    observer.clear()

    controller.assign_user_channel_sample(channel_id, LOOP_PATH)
    assert observer == []

    controller.play()

    assert observer == [1], "next Rack Play adopts the queue in one call"
    assert _channel(controller.state, channel_id).sample_path == LOOP_PATH
    snapshot = controller.playback_classification_snapshot
    assert snapshot is not None
    assert snapshot[channel_id] == (LOOP_PATH, "loop", None)
    assert [spec.sample_path for spec in controller._frozen_loop_specs] == [LOOP_PATH]


def test_18d_immediate_apply_when_rack_play_is_not_active() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot", LOOP_PATH: "loop"})
    observer: list[int] = []
    controller, channel_id = _controller_with_assignment(resolver, ONESHOT_PATH)
    controller.set_on_musical_state_changed(lambda: observer.append(1))
    observer.clear()

    state = controller.assign_user_channel_sample(channel_id, LOOP_PATH)

    assert _channel(state, channel_id).sample_path == LOOP_PATH
    assert _triggers_for(state, channel_id) == ()
    assert observer == [1]
    assert controller.user_metadata[LOOP_PATH].sample_class == "loop"


# ===========================================================================
# Contract test 19 — bottom-Rack projection classifies user rows
# ===========================================================================


def _user_rows(projection: dict[str, Any]) -> list[dict[str, Any]]:
    for group in projection["groups"]:
        if group["name"] == "User":
            return list(group["rows"])
    return []


def test_19_bottom_projection_classifies_user_rows_through_the_binding() -> None:
    kit = LiveKitState()
    channels = (
        _user_channel("ch_user_1", ONESHOT_PATH),
        _user_channel("ch_user_2", LOOP_PATH),
        _user_channel("ch_user_3", AMBIGUOUS_PATH),
    )
    state = _state(channels, (_trigger("ch_user_1", 0), _trigger("ch_user_1", 5)))
    resolver = _ScriptedResolver(
        {ONESHOT_PATH: "one_shot", LOOP_PATH: "loop", AMBIGUOUS_PATH: "text"}
    )
    binding = resolver.resolve((ONESHOT_PATH, LOOP_PATH, AMBIGUOUS_PATH))

    projected = project_bottom_rack_for_qml(state, kit, user_metadata=binding)
    rows = {row["channel_id"]: row for row in _user_rows(projected)}

    oneshot_row = rows["ch_user_1"]
    assert oneshot_row["row_kind"] == "step"
    assert oneshot_row["step_grid_enabled"] is True
    assert len(oneshot_row["steps"]) == 16
    assert oneshot_row["steps"][0] is True
    assert oneshot_row["steps"][5] is True

    loop_row = rows["ch_user_2"]
    assert loop_row["row_kind"] == "loop_identity"
    assert loop_row["step_grid_enabled"] is False
    assert loop_row["steps"] == []

    ambiguous_row = rows["ch_user_3"]
    assert ambiguous_row["row_kind"] == "loop_identity"
    assert ambiguous_row["step_grid_enabled"] is False
    assert ambiguous_row["steps"] == []


def test_19b_projection_is_binding_driven_and_defaults_to_fail_closed() -> None:
    kit = LiveKitState()
    channel = _user_channel("ch_user_1", ONESHOT_PATH)
    state = _state((channel,), (_trigger(channel.channel_id, 0),))
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot"})
    binding = resolver.resolve((ONESHOT_PATH,))

    # Same state, same row: binding decides. No hardcoded user-row class set.
    without = project_bottom_rack_for_qml(state, kit)
    assert _user_rows(without)[0]["row_kind"] == "loop_identity"
    with_binding = project_bottom_rack_for_qml(state, kit, user_metadata=binding)
    assert _user_rows(with_binding)[0]["row_kind"] == "step"
    assert project_bottom_rack_for_qml(state, kit, user_metadata=None) == without


def test_19c_controller_projection_consumes_the_live_binding() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot", LOOP_PATH: "loop"})
    controller, oneshot_id = _controller_with_assignment(resolver, ONESHOT_PATH)
    controller.add_user_channel(sample_path=LOOP_PATH)
    loop_id = _last_user_channel_id(controller.state)
    controller.add_user_channel(sample_path="not_in_library.wav")
    miss_id = _last_user_channel_id(controller.state)

    rows = {row["channel_id"]: row for row in _user_rows(controller.projection())}

    assert rows[oneshot_id]["row_kind"] == "step"
    assert rows[oneshot_id]["step_grid_enabled"] is True
    assert rows[loop_id]["row_kind"] == "loop_identity"
    assert rows[miss_id]["row_kind"] == "loop_identity"
    assert rows[miss_id]["steps"] == []


# ===========================================================================
# Contract test 20 — #926 regression suites stay present
# ===========================================================================


def test_20_protected_regression_suites_remain_present_and_non_empty() -> None:
    for relative in PROTECTED_SUITES:
        path = REPO_ROOT / relative
        assert path.is_file(), f"missing protected regression suite: {relative}"
        source = path.read_text(encoding="utf-8")
        assert "def test_" in source, f"protected suite has no tests: {relative}"


# ===========================================================================
# Section 4 B5 — the never-resolving boundaries
# ===========================================================================


def test_b5_read_and_playback_paths_never_resolve() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot", LOOP_PATH: "loop"})
    controller, _engine, transport = _controller(resolver=resolver)
    controller.ensure_state()
    controller.add_user_channel(sample_path=ONESHOT_PATH)
    controller.add_user_channel(sample_path=LOOP_PATH)
    calls_before = resolver.call_count()

    controller.enter_screen2()
    controller.leave_screen2()
    controller.ensure_state()
    controller.reconcile_live_kit_state()
    controller.projection()
    controller.legacy_screen2_projection()
    controller.play()
    transport.advance(PCM_FRAMES)
    controller.tick_playback()
    controller.stop()

    assert resolver.call_count() == calls_before, (
        "ensure_state / reconcile / projection / play / tick must never resolve"
    )


def test_b5_refresh_is_the_only_explicit_reanalysis_seam() -> None:
    resolver = _ScriptedResolver({ONESHOT_PATH: "one_shot"})
    controller, _engine, _transport = _controller(resolver=resolver)
    controller.ensure_state()
    controller.add_user_channel(sample_path=ONESHOT_PATH)
    calls_before = resolver.call_count()

    binding = controller.refresh_user_channel_metadata()

    assert resolver.call_count() == calls_before + 1
    assert binding[ONESHOT_PATH].sample_class == "one_shot"


def test_b5_no_resolver_means_no_clearing_or_refresh_capability_leak() -> None:
    controller, _engine, _transport = _controller(resolver=None)
    controller.ensure_state()
    controller.add_user_channel(sample_path=ONESHOT_PATH)

    assert dict(controller.user_metadata) == {}
    channel_id = _last_user_channel_id(controller.state)
    controller.clear_user_channel_sample(channel_id)
    assert _channel(controller.state, channel_id).sample_path is None
    assert dict(controller.refresh_user_channel_metadata()) == {}
    assert controller.playback_classification_snapshot is None