"""Session ownership seam for Live Kit + shared audition + Screen-2 rack.

One composed session owns exactly one :class:`LiveKitState`, exactly one
:class:`TransportAwarePreview` audition owner, and one Screen-2
:class:`ChannelRackController` that reuses the same kit + transport.

Cross-screen audio focus (#807) is owned here: entering Screen 2 / claiming
Channel Rack playback releases Screen-1 audition; returning to Screen 1 leaves
a quiet surface and never auto-resumes the previous audition.

Musical session persistence (#809 / #818 / #819): load/validate a local snapshot
under the Workbench state dir, apply MASTER/SYNC onto the shared transport
before first projection, restore kit/rack, expose persistence honesty status,
then wire autosave callbacks only after a successful all-or-nothing restore
(or fresh empty session).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .workbench_channel_rack import ChannelRackController
from .workbench_controller import WorkbenchRow, get_preview_start_ms
from .workbench_harmony import HarmonicMatchLibraryController
from .workbench_live_kit import LiveKitState
from .workbench_preview import WorkbenchPreviewPlayer
from .workbench_qml import (
    LiveKitPresenter,
    Screen1QmlInteractionAdapter,
    Screen1QmlViewModel,
)
from .workbench_session_store import (
    DEFAULT_TEMPO_BPM,
    PERSISTENCE_STATUS_AUTOSAVE_FAILED,
    PERSISTENCE_STATUS_FRESH_MISSING,
    apply_snapshot_to_live_kit,
    channel_rack_state_from_snapshot,
    load_workbench_session_outcome,
    save_workbench_session_snapshot,
    snapshot_from_musical_state,
)
from .workbench_transport_adapter import WorkbenchTransportAdapter
from .workbench_transport_preview import TransportAwarePreview

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
        """Stop Screen-1 monophonic audition and clear adapter projection.

        Idempotent. Never resumes a previous audition — callers must start a
        new explicit preview/Live Kit audition intent.
        """
        self.qml_interaction_adapter.quiet_audition()

    def enter_screen2(self) -> ChannelRackState:
        """Claim Channel Rack focus: quiet Screen-1 audition, then enter Screen 2."""
        return self.channel_rack.enter_screen2()

    def return_to_screen1(self) -> None:
        """Leave Screen 2 quietly: stop pattern, keep Screen-1 audition off."""
        self.channel_rack.leave_screen2()


class _SessionAuditionPlayRow:
    """Resolve ``audition.play_row`` at call time while advertising TAP ownership.

    Frozen ownership tests may replace ``audition.play_row`` on the session
    owner. A captured bound method would miss that patch; this delegate keeps
    ``__self__`` / ``__func__`` aligned with :meth:`TransportAwarePreview.play_row`.

    ``start_ms=None`` (Browser) resolves the saved cue via
    :func:`get_preview_start_ms`. Explicit offsets (Live Kit ``0``) are
    forwarded unchanged — never coerced ``None -> 0``.
    """

    __slots__ = ("_audition", "_library_db_path")

    def __init__(
        self,
        audition: TransportAwarePreview,
        *,
        library_db_path: Path | None = None,
    ) -> None:
        self._audition = audition
        self._library_db_path = library_db_path

    @property
    def __self__(self) -> TransportAwarePreview:
        return self._audition

    @property
    def __func__(self) -> Any:
        return type(self._audition).play_row

    def __call__(self, row: WorkbenchRow, *, start_ms: int | None = None) -> object:
        if start_ms is None:
            resolved = get_preview_start_ms(
                row.path,
                library_db_path=self._library_db_path,
            )
        else:
            resolved = start_ms
        return self._audition.play_row(row, start_ms=resolved)


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
        snapshot = snapshot_from_musical_state(
            live_kit, channel_rack.state, transport
        )
        save_workbench_session_snapshot(snapshot, state_dir=state_dir, env=env)
    except OSError:
        # Last good on-disk snapshot remains; in-memory state stays authoritative.
        session.note_autosave_failed()
        return
    session.note_autosave_succeeded()


def compose_workbench_session(
    *,
    include_tk_workbench: bool = False,
    library_db_path: Path | None = None,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> WorkbenchSession:
    """Compose one shared Live Kit + one TransportAwarePreview audition owner.

    Restore order (#818 / #819):
    load/validate (+ honesty status) → resolve MASTER/SYNC → construct/apply
    transport clock → restore Live Kit → restore Channel Rack → presentation →
    wire autosave.
    """

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
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(
            on_query_finished=match_observer,
        ),
        on_preview_requested=_SessionAuditionPlayRow(
            audition,
            library_db_path=library_db_path,
        ),
        on_preview_stopped=audition.stop,
        on_preview_snapshot=audition.playback_snapshot,
        live_kit=presenter,
        library_db_path=library_db_path,
    )

    channel_rack = ChannelRackController(live_kit=live_kit, transport=transport)
    if snapshot is not None:
        rack_state = channel_rack_state_from_snapshot(snapshot)
        if rack_state is not None:
            channel_rack.restore_state(rack_state)

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
    )
    # Single ownership: Channel Rack enter/play/leave claim/release Screen-1
    # audition through the session policy, including bridge-direct paths.
    channel_rack.set_audio_focus_hooks(
        on_claim_focus=session.release_screen1_audition,
        on_release_to_screen1=session.release_screen1_audition,
    )

    def _on_channel_rack_mutation() -> None:
        _autosave_musical_session(
            session=session,
            live_kit=live_kit,
            channel_rack=channel_rack,
            transport=transport,
            state_dir=state_dir,
            env=env,
        )

    def _on_live_kit_mutation() -> None:
        # #817: heal existing rack against Live Kit before one coherent autosave.
        # notify=False avoids nested rack→autosave doubling the Live Kit write.
        channel_rack.reconcile_live_kit_state(notify=False)
        _autosave_musical_session(
            session=session,
            live_kit=live_kit,
            channel_rack=channel_rack,
            transport=transport,
            state_dir=state_dir,
            env=env,
        )

    def _on_session_clock_mutation() -> None:
        # Clock-only intent → one full coherent session save (includes kit/rack).
        _autosave_musical_session(
            session=session,
            live_kit=live_kit,
            channel_rack=channel_rack,
            transport=transport,
            state_dir=state_dir,
            env=env,
        )

    live_kit.set_on_assignment_changed(_on_live_kit_mutation)
    channel_rack.set_on_musical_state_changed(_on_channel_rack_mutation)
    transport.set_on_session_clock_changed(_on_session_clock_mutation)
    return session


__all__ = [
    "WorkbenchSession",
    "compose_workbench_session",
]
