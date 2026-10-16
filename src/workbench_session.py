"""Session ownership seam for Live Kit + shared audition + Channel Rack.

One composed session owns exactly one :class:`LiveKitState`, exactly one
:class:`TransportAwarePreview` audition owner, and one
:class:`ChannelRackController` that reuses the same kit + transport.

Domain audio focus (#807 / #916) is owned here: last explicit playback intent
wins. Rack Play releases audition voice/projection without tearing down the
shared transport for focus transfer; Preview Play while Rack is playing stops
Rack first. Returning from legacy Screen-2 leaves a quiet surface and never
auto-resumes the previous audition.

Musical session persistence (#809 / #818 / #819 / #820): load/validate a local
snapshot under the Workbench state dir, apply MASTER/SYNC onto the shared
transport before first projection, restore kit/rack path refs, expose
persistence honesty status, best-effort rehydrate Live Kit analysis fields
from the local library when ``library_db_path`` is present, then wire autosave
callbacks only after a successful all-or-nothing restore (or fresh empty
session).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .arrangement_32_field_time import (
    classify_channel_rack_state,
    require_32_field_channel_rack_state,
)
from .arrangement_domain import ArrangementError, ArrangementState
from .track_package import (
    OUTCOME_CORRUPT_OR_UNSUPPORTED,
    OUTCOME_OPEN,
    OUTCOME_WRITE_FAILED,
    OUTCOME_DESTINATION_UNAVAILABLE,
    TrackPackageDraft,
    TrackPackageMediaSource,
    TrackPackageResult,
    create_track_package,
    open_track_package,
    save_track_package_musical_state,
)
from .workbench_channel_rack import ChannelRackController
from .workbench_controller import WorkbenchRow, get_preview_start_ms
from .workbench_harmony import HarmonicMatchLibraryController
from .workbench_live_kit import LiveKitState
from .workbench_feature_settings import load_workbench_feature_settings
from .workbench_preview import WorkbenchPreviewPlayer
from .workbench_qml import (
    LiveKitPresenter,
    Screen1QmlInteractionAdapter,
    Screen1QmlViewModel,
)
from .workbench_session_store import (
    ActiveTrackPointer,
    WorkbenchSessionSnapshot,
    DEFAULT_TEMPO_BPM,
    PERSISTENCE_STATUS_AUTOSAVE_FAILED,
    PERSISTENCE_STATUS_FRESH_MISSING,
    apply_snapshot_to_live_kit,
    load_active_track_pointer,
    channel_rack_state_from_snapshot,
    load_workbench_session_outcome,
    rehydrate_live_kit_from_library,
    save_active_track_pointer,
    save_workbench_session_snapshot,
    snapshot_from_musical_state,
    snapshot_from_track_package_musical,
    track_package_musical_from_snapshot,
)
from .workbench_transport_adapter import WorkbenchTransportAdapter
from .workbench_transport_preview import TransportAwarePreview
from .workbench_user_sample_metadata import (
    WorkbenchLibraryUserSampleMetadataResolver,
)

if TYPE_CHECKING:
    from .channel_rack import ChannelRackState
    from .workbench import WorkbenchApp


@dataclass
class WorkbenchSession:
    """Owned Workbench surfaces composed by :func:`compose_workbench_session`."""

    live_kit: LiveKitState
    live_kit_presenter: LiveKitPresenter
    transport: WorkbenchTransportAdapter
    audition: TransportAwarePreview
    qml_interaction_adapter: Screen1QmlInteractionAdapter
    channel_rack: ChannelRackController
    tk_workbench: WorkbenchApp | None = None
    measurement_session_id: str | None = None
    persistence_status: str = PERSISTENCE_STATUS_FRESH_MISSING
    _resume_persistence_status: str = field(
        default=PERSISTENCE_STATUS_FRESH_MISSING,
        repr=False,
        compare=False,
    )
    _persistence_status_listeners: list[Any] = field(
        default_factory=list,
        repr=False,
        compare=False,
    )

    active_track_id: str | None = None
    active_track_package_root: Path | None = None
    track_package_status: str | None = None
    track_package_dirty: bool = False
    # Projection is ephemeral: opening/restoring state does not activate a mode.
    projection_mode: str = field(default="EDIT", init=False)
    _arrangement_entry_in_progress: bool = field(default=False, init=False, repr=False)
    # A committed package whose pointer write failed can be retried without
    # copying media again. This is transaction recovery, not an active track.
    _pending_arrangement_entry: TrackPackageResult | None = field(
        default=None, init=False, repr=False, compare=False
    )
    # Opaque package seam remains inert until an explicit domain consumer reads
    # or updates it. No Arrangement activation during composition/navigation.
    _arrangement_payload: Any = field(default=None, repr=False, compare=False)
    _state_dir: Path | None = field(default=None, repr=False, compare=False)
    _env: Mapping[str, str] | None = field(default=None, repr=False, compare=False)
    # #1086: frozen classification captured at the rack-restore boundary, so a
    # persisted legacy v1 rack is surfaced as migration_required/hold/32-field
    # instead of being silently adopted. `None` = no restore has happened yet.
    _restored_rack_time_status: Mapping[str, object] | None = field(
        default=None, repr=False, compare=False
    )

    @property
    def arrangement_state(self) -> ArrangementState | None:
        if self._arrangement_payload is None:
            return None
        return ArrangementState.from_payload(
            self._arrangement_payload, self.channel_rack.state
        )

    def enter_arrangement_from_edit(
        self, *, package_root: Path | str | None = None
    ) -> TrackPackageResult:
        """Deliberate #1078 entry through the existing package/domain owners.

        Reject active playback without stopping or replacing its authority.
        Partial kits are eligible; legacy Patterns require explicit migration.
        Mode changes only after the package and active pointer are durable.
        """
        if not load_workbench_feature_settings(
            state_dir=self._state_dir, env=self._env
        ).arrangement_mode_enabled:
            return TrackPackageResult(
                "feature_disabled", message="Arrangement mode is disabled."
            )
        if self._arrangement_entry_in_progress:
            return TrackPackageResult(
                "entry_in_progress", message="Arrangement entry is already in progress."
            )
        if (
            self.transport.playing
            or self.channel_rack.is_playing
            or self.audition.playback_snapshot().playing
            # Legacy preview has no reliable natural-end telemetry/clock.
            # Its existing intent remains owned until explicit Stop.
            or (
                self.audition.active_voice_id is None
                and self.audition.current_path is not None
            )
        ):
            return TrackPackageResult(
                "playback_active", message="Stop playback before entering Arrangement."
            )
        self._arrangement_entry_in_progress = True
        try:
            return self._commit_arrangement_entry(package_root)
        except (OSError, RuntimeError, TypeError, ValueError):
            return TrackPackageResult(
                OUTCOME_WRITE_FAILED,
                message="Arrangement entry failed; check package destination and media, then retry.",
            )
        finally:
            self._arrangement_entry_in_progress = False

    def _commit_arrangement_entry(
        self, package_root: Path | str | None
    ) -> TrackPackageResult:
        rack = self.channel_rack.state
        snapshot = snapshot_from_musical_state(self.live_kit, rack, self.transport)
        musical = track_package_musical_from_snapshot(snapshot)
        paths = {
            path
            for slots in snapshot.live_kit.values()
            for path in slots.values()
            if path is not None
        }
        if rack is not None:
            paths.update(c.sample_path for c in rack.channels if c.sample_path)
        if not paths and self.active_track_id is None:
            return TrackPackageResult(
                "empty_draft",
                message="Assign at least one sample before entering Arrangement.",
            )
        try:
            require_32_field_channel_rack_state(rack)
        except (TypeError, ValueError):
            return TrackPackageResult(
                "migration_required",
                message="A valid 32-field Pattern is required; migrate explicitly first.",
            )
        try:
            arrangement = (
                ArrangementState.for_rack(rack)
                if self._arrangement_payload is None
                else ArrangementState.from_payload(self._arrangement_payload, rack)
            )
        except (TypeError, ValueError) as exc:
            return TrackPackageResult(
                OUTCOME_CORRUPT_OR_UNSUPPORTED,
                message=f"Arrangement state is invalid: {exc}",
            )

        if (
            self.active_track_id is not None
            or self.active_track_package_root is not None
        ):
            if self.active_track_id is None or self.active_track_package_root is None:
                return TrackPackageResult(
                    OUTCOME_CORRUPT_OR_UNSUPPORTED,
                    message="Active track selection is incomplete.",
                )
            opened = open_track_package(self.active_track_package_root)
            if not opened.ok:
                return opened
            if opened.track_id != self.active_track_id:
                return TrackPackageResult(
                    OUTCOME_CORRUPT_OR_UNSUPPORTED,
                    message="Active track identity does not match its package.",
                )
            if opened.manifest is not None and opened.manifest.arrangement is not None:
                try:
                    disk_snapshot = snapshot_from_track_package_musical(
                        opened.manifest.musical, self.active_track_package_root
                    )
                    ArrangementState.from_payload(
                        opened.manifest.arrangement, disk_snapshot.channel_rack
                    )
                except (OSError, RuntimeError, TypeError, ValueError):
                    return TrackPackageResult(
                        OUTCOME_CORRUPT_OR_UNSUPPORTED,
                        message="Stored Arrangement state is invalid; package was not changed.",
                    )
            if self.projection_mode == "ARRANGEMENT" and not self.track_package_dirty:
                return opened
            saved = save_track_package_musical_state(
                self.active_track_package_root,
                musical,
                arrangement=arrangement.to_payload(),
            )
            self.track_package_status = saved.outcome
            self.track_package_dirty = not saved.ok
            if not saved.ok:
                return saved
            try:
                _adopt_saved_package_media(self, saved)
            except (OSError, RuntimeError, TypeError, ValueError):
                self.track_package_status = OUTCOME_WRITE_FAILED
                self.track_package_dirty = True
                return TrackPackageResult(
                    OUTCOME_WRITE_FAILED,
                    message="Committed package media could not be restored; retry after checking media.",
                )
            self._arrangement_payload = arrangement.to_payload()
            self.projection_mode = "ARRANGEMENT"
            return saved

        if package_root is None:
            return TrackPackageResult(
                OUTCOME_DESTINATION_UNAVAILABLE,
                message="Choose a track package destination.",
            )
        root = Path(package_root).expanduser().resolve(strict=False)
        pending = self._pending_arrangement_entry
        if pending is not None and pending.package_root == root:
            created = open_track_package(root)
            if not created.ok:
                return created
            if created.manifest != pending.manifest:
                return TrackPackageResult(
                    OUTCOME_CORRUPT_OR_UNSUPPORTED,
                    message="Pending package changed externally; choose another destination.",
                )
            created = save_track_package_musical_state(
                root, musical, arrangement=arrangement.to_payload()
            )
            if not created.ok:
                return created
            self._pending_arrangement_entry = created
        else:
            created = create_track_package(
                TrackPackageDraft(
                    media_sources=tuple(
                        TrackPackageMediaSource(Path(path)) for path in sorted(paths)
                    ),
                    musical=musical,
                    arrangement=arrangement.to_payload(),
                ),
                root,
            )
            if not created.ok:
                return created
            self._pending_arrangement_entry = created
        bound = self.bind_active_track_package(root, preserve_draft_metadata=True)
        if not bound.ok:
            return bound
        self._pending_arrangement_entry = None
        self.projection_mode = "ARRANGEMENT"
        return bound

    def return_to_edit(self) -> None:
        """Change projection only; keep track, musical state and transport."""
        self.projection_mode = "EDIT"

    def set_arrangement_state(self, state: ArrangementState) -> None:
        """Internal control-plane seam; product transition remains #1078.

        The active package owns persistence. Failed writes preserve dirty intent
        in memory and retry through the existing musical autosave path.
        """
        if self.active_track_package_root is None or self.active_track_id is None:
            raise ArrangementError("active_track_required")
        if not isinstance(state, ArrangementState):
            raise ArrangementError("invalid_arrangement_state")
        state.validate(self.channel_rack.state)
        self._arrangement_payload = state.to_payload()
        _autosave_musical_session(
            session=self,
            live_kit=self.live_kit,
            channel_rack=self.channel_rack,
            transport=self.transport,
            state_dir=self._state_dir,
            env=self._env,
        )

    def bind_active_track_package(
        self, package_root: Path | str, *, preserve_draft_metadata: bool = False
    ) -> TrackPackageResult:
        """Bind one validated package as the durable musical authority.

        Only initial draft entry retains analyzed rows while rebasing media.
        Explicit Open must not inherit metadata from an unrelated current kit.
        """
        root = Path(package_root)
        opened = open_track_package(root)
        if (
            opened.outcome != OUTCOME_OPEN
            or opened.manifest is None
            or opened.track_id is None
        ):
            return opened
        try:
            snapshot = snapshot_from_track_package_musical(
                opened.manifest.musical, root
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return TrackPackageResult(
                outcome=OUTCOME_CORRUPT_OR_UNSUPPORTED,
                package_root=root,
                track_id=opened.track_id,
                message="Track package musical state is invalid.",
            )
        try:
            save_active_track_pointer(
                ActiveTrackPointer(track_id=opened.track_id, package_root=root),
                state_dir=self._state_dir,
                env=self._env,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            return TrackPackageResult(
                outcome=OUTCOME_WRITE_FAILED,
                package_root=root,
                track_id=opened.track_id,
                manifest=opened.manifest,
                message="Active track selection could not be persisted.",
            )

        _detach_session_persistence(self)
        try:
            _apply_package_live_kit(
                snapshot, self.live_kit, preserve_metadata=preserve_draft_metadata
            )
            self.transport.set_tempo(float(snapshot.master_bpm))
            self.transport.set_sync_enabled(bool(snapshot.sync_enabled))
            rack_state = channel_rack_state_from_snapshot(snapshot)
            if rack_state is not None:
                self.channel_rack.restore_state(rack_state)
                self._restored_rack_time_status = classify_channel_rack_state(
                    rack_state
                )
            self.active_track_id = opened.track_id
            self._arrangement_payload = opened.manifest.arrangement
            self.active_track_package_root = root.resolve(strict=False)
            self.track_package_status = OUTCOME_OPEN
            self.track_package_dirty = False
        finally:
            _wire_session_persistence(self)
        return TrackPackageResult(
            outcome=OUTCOME_OPEN,
            package_root=self.active_track_package_root,
            track_id=self.active_track_id,
            manifest=opened.manifest,
        )

    def add_persistence_status_listener(self, callback: Any) -> None:
        """Register a no-arg callback for persistence_status changes (#819)."""
        if callback is not None and callback not in self._persistence_status_listeners:
            self._persistence_status_listeners.append(callback)

    def _notify_persistence_status(self) -> None:
        for callback in tuple(self._persistence_status_listeners):
            try:
                callback()
            except Exception:
                continue

    def note_autosave_failed(self) -> None:
        """Mark durable save failure without altering in-memory musical state."""
        if self.persistence_status == PERSISTENCE_STATUS_AUTOSAVE_FAILED:
            return
        self.persistence_status = PERSISTENCE_STATUS_AUTOSAVE_FAILED
        self._notify_persistence_status()

    def note_autosave_succeeded(self) -> None:
        """Clear autosave failure honesty back to the compose-time resume code."""
        if self.persistence_status != PERSISTENCE_STATUS_AUTOSAVE_FAILED:
            return
        self.persistence_status = self._resume_persistence_status
        self._notify_persistence_status()

    def release_screen1_audition(self) -> None:
        """Release audition voice + projection without shared-transport teardown.

        Idempotent focus-transfer seam (#807 / #916). Never resumes a previous
        audition — callers must start a new explicit preview/Live Kit intent.
        Does not stop the shared session transport solely for focus transfer.
        """
        self.qml_interaction_adapter.quiet_audition()

    def enter_screen2(self) -> ChannelRackState:
        """Legacy Screen-2 enter: claim focus, ensure Rack state, set screen."""
        return self.channel_rack.enter_screen2()

    def return_to_screen1(self) -> None:
        """Leave Screen 2 quietly: stop pattern, keep Screen-1 audition off."""
        self.channel_rack.leave_screen2()

    @property
    def channel_rack_time_status(self) -> Mapping[str, object]:
        """Live #1086 rack time-model status (read-only, never activates)."""
        return classify_channel_rack_state(self.channel_rack.state)

    @property
    def restored_rack_time_status(self) -> Mapping[str, object] | None:
        """Frozen #1086 classification captured at the last rack restore."""
        return self._restored_rack_time_status


class _SessionAuditionPlayRow:
    """Resolve ``audition.play_row`` at call time while advertising TAP ownership.

    Frozen ownership tests may replace ``audition.play_row`` on the session
    owner. A captured bound method would miss that patch; this delegate keeps
    ``__self__`` / ``__func__`` aligned with :meth:`TransportAwarePreview.play_row`.

    ``start_ms=None`` (Browser) resolves the saved cue via
    :func:`get_preview_start_ms`. Explicit offsets (Live Kit ``0``) are
    forwarded unchanged — never coerced ``None -> 0``.

    When a Channel Rack holder is bound and Rack is playing, Rack is stopped
    first (last explicit playback intent wins — #916). Failed preview after
    that stop does not restart Rack.
    """

    __slots__ = ("_audition", "_library_db_path", "_rack_holder")

    def __init__(
        self,
        audition: TransportAwarePreview,
        *,
        library_db_path: Path | None = None,
        rack_holder: list[ChannelRackController | None] | None = None,
    ) -> None:
        self._audition = audition
        self._library_db_path = library_db_path
        self._rack_holder = rack_holder if rack_holder is not None else [None]

    @property
    def __self__(self) -> TransportAwarePreview:
        return self._audition

    @property
    def __func__(self) -> Any:
        return type(self._audition).play_row

    def __call__(self, row: WorkbenchRow, *, start_ms: int | None = None) -> object:
        rack = self._rack_holder[0]
        if rack is not None and rack.is_playing:
            rack.stop()
        if start_ms is None:
            resolved = get_preview_start_ms(
                row.path,
                library_db_path=self._library_db_path,
            )
        else:
            resolved = start_ms
        return self._audition.play_row(row, start_ms=resolved)


def _apply_package_live_kit(
    snapshot: WorkbenchSessionSnapshot,
    live_kit: LiveKitState,
    *,
    preserve_metadata: bool,
) -> None:
    """Reuse snapshot restore, retaining current analyzed rows for media rebase."""
    rows = (
        {
            (group, slot): live_kit.assignment_for(group, slot)
            for group, slots in snapshot.live_kit.items()
            for slot in slots
        }
        if preserve_metadata
        else {}
    )
    apply_snapshot_to_live_kit(snapshot, live_kit)
    for (group, slot), row in rows.items():
        path = snapshot.live_kit[group][slot]
        if row is not None and path is not None:
            live_kit.assign(group, slot, replace(row, path=path))


def _adopt_saved_package_media(
    session: WorkbenchSession, result: TrackPackageResult
) -> None:
    """Rebind committed media through the existing snapshot seam.

    Unchanged projections keep their Pattern/Rack identity. Media rebinding
    never creates a second owner or schedules playback.
    """
    if result.manifest is None or session.active_track_package_root is None:
        raise ValueError("Committed package manifest is required.")
    refreshed = snapshot_from_track_package_musical(
        result.manifest.musical, session.active_track_package_root
    )
    current = snapshot_from_musical_state(
        session.live_kit, session.channel_rack.state, session.transport
    )
    if refreshed == current:
        return
    _detach_session_persistence(session)
    try:
        _apply_package_live_kit(refreshed, session.live_kit, preserve_metadata=True)
        rack_state = channel_rack_state_from_snapshot(refreshed)
        if rack_state is not None:
            session.channel_rack.restore_state(rack_state)
            session._restored_rack_time_status = classify_channel_rack_state(rack_state)
            session.channel_rack.reconcile_live_kit_state(notify=False)
    finally:
        _wire_session_persistence(session)


def _autosave_musical_session(
    *,
    session: WorkbenchSession,
    live_kit: LiveKitState,
    channel_rack: ChannelRackController,
    transport: WorkbenchTransportAdapter,
    state_dir: Path | None,
    env: Mapping[str, str] | None,
) -> None:
    """Persist current musical state. IO failures must not corrupt memory."""
    try:
        snapshot = snapshot_from_musical_state(live_kit, channel_rack.state, transport)
    except (TypeError, ValueError):
        if session.active_track_package_root is not None:
            session.track_package_status = OUTCOME_WRITE_FAILED
            session.track_package_dirty = True
        else:
            session.note_autosave_failed()
        return

    if session.active_track_package_root is not None:
        result = save_track_package_musical_state(
            session.active_track_package_root,
            track_package_musical_from_snapshot(snapshot),
            arrangement=session._arrangement_payload,
        )
        session.track_package_status = result.outcome
        session.track_package_dirty = result.outcome != OUTCOME_OPEN
        if (
            result.outcome == OUTCOME_OPEN
            and result.manifest is not None
            and session.active_track_package_root is not None
        ):
            try:
                _adopt_saved_package_media(session, result)
            except (OSError, RuntimeError, TypeError, ValueError):
                session.track_package_status = OUTCOME_WRITE_FAILED
                session.track_package_dirty = True
        return

    try:
        save_workbench_session_snapshot(snapshot, state_dir=state_dir, env=env)
    except OSError:
        # Last good on-disk snapshot remains; in-memory state stays authoritative.
        session.note_autosave_failed()
        return
    session.note_autosave_succeeded()


def _detach_session_persistence(session: WorkbenchSession) -> None:
    session.live_kit.set_on_assignment_changed(None)
    session.channel_rack.set_on_musical_state_changed(None)
    session.transport.set_on_session_clock_changed(None)


def _wire_session_persistence(session: WorkbenchSession) -> None:
    def _on_channel_rack_mutation() -> None:
        _autosave_musical_session(
            session=session,
            live_kit=session.live_kit,
            channel_rack=session.channel_rack,
            transport=session.transport,
            state_dir=session._state_dir,
            env=session._env,
        )

    def _on_live_kit_mutation() -> None:
        session.channel_rack.ensure_state(notify=False)
        _autosave_musical_session(
            session=session,
            live_kit=session.live_kit,
            channel_rack=session.channel_rack,
            transport=session.transport,
            state_dir=session._state_dir,
            env=session._env,
        )

    def _on_session_clock_mutation() -> None:
        _autosave_musical_session(
            session=session,
            live_kit=session.live_kit,
            channel_rack=session.channel_rack,
            transport=session.transport,
            state_dir=session._state_dir,
            env=session._env,
        )

    session.live_kit.set_on_assignment_changed(_on_live_kit_mutation)
    session.channel_rack.set_on_musical_state_changed(_on_channel_rack_mutation)
    session.transport.set_on_session_clock_changed(_on_session_clock_mutation)


def compose_workbench_session(
    *,
    include_tk_workbench: bool = False,
    library_db_path: Path | None = None,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> WorkbenchSession:
    """Compose one shared Live Kit + one TransportAwarePreview audition owner.

    Restore order (#818 / #819 / #820):
    load/validate (+ honesty status) → resolve MASTER/SYNC → construct/apply
    transport clock → restore Live Kit path refs → optional library rehydrate →
    first projection → restore Channel Rack → wire autosave.
    """

    pointer_present, pointer = load_active_track_pointer(state_dir=state_dir, env=env)
    active_track_id: str | None = None
    active_track_root: Path | None = None
    track_package_status: str | None = None

    arrangement_payload: Any = None

    if pointer_present:
        # Presence of an active selection record outranks stale legacy resume.
        # Invalid/missing active package fails closed; legacy remains untouched.
        resume_status = PERSISTENCE_STATUS_FRESH_MISSING
        snapshot = None
        if pointer is None:
            track_package_status = OUTCOME_CORRUPT_OR_UNSUPPORTED
        else:
            active_track_id = pointer.track_id
            active_track_root = pointer.package_root
            opened = open_track_package(pointer.package_root)
            track_package_status = opened.outcome
            if (
                opened.outcome == OUTCOME_OPEN
                and opened.manifest is not None
                and opened.track_id == pointer.track_id
            ):
                try:
                    snapshot = snapshot_from_track_package_musical(
                        opened.manifest.musical, pointer.package_root
                    )
                    arrangement_payload = opened.manifest.arrangement
                except (OSError, RuntimeError, TypeError, ValueError):
                    snapshot = None
                    track_package_status = OUTCOME_CORRUPT_OR_UNSUPPORTED
            elif opened.outcome == OUTCOME_OPEN:
                track_package_status = OUTCOME_CORRUPT_OR_UNSUPPORTED
    else:
        load_outcome = load_workbench_session_outcome(state_dir=state_dir, env=env)
        snapshot = load_outcome.snapshot
        resume_status = load_outcome.status

    if snapshot is not None:
        master_bpm = float(snapshot.master_bpm)
        sync_enabled = bool(snapshot.sync_enabled)
    else:
        master_bpm = float(DEFAULT_TEMPO_BPM)
        sync_enabled = False

    # Empty kit first so Tk can adopt the same LiveKitState instance; clock is
    # applied before kit/rack restore and before any presentation projection.
    live_kit = LiveKitState()
    tk_workbench: WorkbenchApp | None = None

    if include_tk_workbench:
        import tkinter as tk

        from .workbench import WorkbenchApp

        root = tk.Tk()
        root.withdraw()
        tk_workbench = WorkbenchApp(root, live_kit_state=live_kit)
        transport = tk_workbench._transport_adapter
        audition = tk_workbench._preview
        if not isinstance(audition, TransportAwarePreview):
            raise RuntimeError(
                "Tk WorkbenchApp must expose TransportAwarePreview as session audition."
            )
        # Apply persisted clock onto the existing adapter (no second authority).
        transport.set_tempo(master_bpm)
        transport.set_sync_enabled(sync_enabled)
    else:
        transport = WorkbenchTransportAdapter(
            initial_bpm=master_bpm,
            initial_sync_enabled=sync_enabled,
        )
        audition = TransportAwarePreview(WorkbenchPreviewPlayer(), transport)

    if snapshot is not None:
        apply_snapshot_to_live_kit(snapshot, live_kit)
        # #820: enrich restored path refs from local library before projection.
        rehydrate_live_kit_from_library(live_kit, library_db_path=library_db_path)

    presenter = LiveKitPresenter(state=live_kit)

    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=presenter.groups,
    )
    match_observer = None
    measurement_session_id: str | None = None
    try:
        from .measurement.emit import make_match_query_finished_observer

        match_observer, measurement_session_id = make_match_query_finished_observer()
    except Exception:
        match_observer = None
        measurement_session_id = None

    # Late-bound so preview start can arbitrate against Rack after controller exists.
    rack_holder: list[ChannelRackController | None] = [None]
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(
            on_query_finished=match_observer,
        ),
        on_preview_requested=_SessionAuditionPlayRow(
            audition,
            library_db_path=library_db_path,
            rack_holder=rack_holder,
        ),
        on_preview_stopped=audition.stop,
        on_preview_released=audition.release_voice,
        on_preview_snapshot=audition.playback_snapshot,
        live_kit=presenter,
        library_db_path=library_db_path,
    )

    channel_rack = ChannelRackController(
        live_kit=live_kit,
        transport=transport,
        user_metadata_resolver=WorkbenchLibraryUserSampleMetadataResolver(
            library_db_path=library_db_path
        ),
    )
    rack_holder[0] = channel_rack
    restored_rack_time_status: Mapping[str, object] | None = None
    if snapshot is not None:
        rack_state = channel_rack_state_from_snapshot(snapshot)
        if rack_state is not None:
            channel_rack.restore_state(rack_state)
            restored_rack_time_status = classify_channel_rack_state(rack_state)
            # After library rehydrate, classification-aware reconcile may strip
            # stale loop-channel triggers without reseeding oneshot/ambiguous.
            channel_rack.reconcile_live_kit_state(notify=False)

    session = WorkbenchSession(
        live_kit=live_kit,
        live_kit_presenter=presenter,
        transport=transport,
        audition=audition,
        qml_interaction_adapter=adapter,
        channel_rack=channel_rack,
        tk_workbench=tk_workbench,
        measurement_session_id=measurement_session_id,
        persistence_status=resume_status,
        _resume_persistence_status=resume_status,
        active_track_id=active_track_id,
        active_track_package_root=active_track_root,
        track_package_status=track_package_status,
        track_package_dirty=False,
        _arrangement_payload=arrangement_payload,
        _state_dir=state_dir,
        _env=env,
        _restored_rack_time_status=restored_rack_time_status,
    )
    # Single ownership: Channel Rack enter/play/leave claim/release audition
    # through the session policy, including bridge-direct paths. Focus release
    # uses voice-only quiet; explicit preview stop reconciles Rack before any
    # shared-transport teardown (#916).
    channel_rack.set_audio_focus_hooks(
        on_claim_focus=session.release_screen1_audition,
        on_release_to_screen1=session.release_screen1_audition,
    )

    def _reconcile_rack_before_shared_transport_stop() -> None:
        if channel_rack.is_playing:
            channel_rack.stop()

    audition.set_before_shared_transport_stop(
        _reconcile_rack_before_shared_transport_stop
    )

    _wire_session_persistence(session)
    return session


__all__ = [
    "WorkbenchSession",
    "compose_workbench_session",
]
