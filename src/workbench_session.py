"""Session ownership seam for Live Kit + shared audition + Screen-2 rack.

One composed session owns exactly one :class:`LiveKitState`, exactly one
:class:`TransportAwarePreview` audition owner, and one Screen-2
:class:`ChannelRackController` that reuses the same kit + transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tkinter as tk

from .workbench import WorkbenchApp
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
from .workbench_transport_adapter import WorkbenchTransportAdapter
from .workbench_transport_ui import TransportAwarePreview


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


def compose_workbench_session(
    *,
    include_tk_workbench: bool = False,
    library_db_path: Path | None = None,
) -> WorkbenchSession:
    """Compose one shared Live Kit + one TransportAwarePreview audition owner."""

    live_kit = LiveKitState()
    presenter = LiveKitPresenter(state=live_kit)
    tk_workbench: WorkbenchApp | None = None

    if include_tk_workbench:
        root = tk.Tk()
        root.withdraw()
        tk_workbench = WorkbenchApp(root, live_kit_state=live_kit)
        transport = tk_workbench._transport_adapter
        audition = tk_workbench._preview
        if not isinstance(audition, TransportAwarePreview):
            raise RuntimeError(
                "Tk WorkbenchApp must expose TransportAwarePreview as session audition."
            )
    else:
        transport = WorkbenchTransportAdapter()
        audition = TransportAwarePreview(WorkbenchPreviewPlayer(), transport)

    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=presenter.groups,
    )
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
        on_preview_requested=_SessionAuditionPlayRow(
            audition,
            library_db_path=library_db_path,
        ),
        on_preview_stopped=audition.stop,
        on_preview_snapshot=audition.playback_snapshot,
        live_kit=presenter,
    )

    channel_rack = ChannelRackController(live_kit=live_kit, transport=transport)

    return WorkbenchSession(
        live_kit=live_kit,
        live_kit_presenter=presenter,
        transport=transport,
        audition=audition,
        qml_interaction_adapter=adapter,
        channel_rack=channel_rack,
        tk_workbench=tk_workbench,
    )


__all__ = [
    "WorkbenchSession",
    "compose_workbench_session",
]
