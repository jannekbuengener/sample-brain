"""Tkinter wiring for exact-frame, non-destructive Workbench regions (issue #326)."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any, Callable

from .workbench_editing import (
    EditRegionValidationError,
    WorkbenchEditRegion,
    audio_source_frame_info,
    build_edit_region,
    delete_workbench_edit_region,
    frame_from_waveform_x,
    load_workbench_edit_region,
    render_workbench_edit_region,
    save_workbench_edit_region,
    source_edit_grid_from_details,
)
from .workbench_waveform import frame_region_x

EDIT_REGION_FILL = "#16334a"
EDIT_REGION_MARKER = "#58b7ff"
EDIT_REGION_HINT = (
    "Bereich schneiden: 1. Klick Start · 2. Klick Ende · "
    "Grenzen werden als Source-Frames gespeichert"
)


class WorkbenchEditingUI:
    """Small UI adapter around the exact source-frame edit contract."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self._pending_start_frame: int | None = None
        self._undo_available = False
        self._undo_source_ref: str | None = None
        self._undo_region: WorkbenchEditRegion | None = None

        self._build_controls()
        self._base_draw: Callable[[Any], None] = app._draw_waveform
        app._draw_waveform = self._draw_waveform_with_region
        app._waveform_canvas.bind("<Button-1>", self._on_waveform_click)
        self._wrap_view_visibility()
        self._sync_visibility()

    def _build_controls(self) -> None:
        host = self.app._waveform_controls.master
        self.frame = ttk.Frame(host, style="Panel.TFrame")
        self.frame.pack(
            fill=tk.X,
            pady=(0, 4),
            before=self.app._waveform_canvas,
        )

        self.edit_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            self.frame,
            text="Bereich schneiden",
            variable=self.edit_mode_var,
            command=self._on_edit_mode_toggled,
        ).pack(side=tk.LEFT)

        ttk.Label(self.frame, text="Snap:", style="Panel.TLabel").pack(
            side=tk.LEFT,
            padx=(10, 4),
        )
        self.snap_mode_var = tk.StringVar(value="none")
        self.snap_combo = ttk.Combobox(
            self.frame,
            textvariable=self.snap_mode_var,
            values=("none", "beat", "bar"),
            state="readonly",
            width=5,
        )
        self.snap_combo.pack(side=tk.LEFT)

        ttk.Button(
            self.frame,
            text="Region löschen",
            command=self._delete_region,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            self.frame,
            text="Region vorhören",
            command=self._preview_region,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            self.frame,
            text="Undo",
            command=self._undo,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            self.frame,
            text="Region rendern",
            command=self._render_region,
        ).pack(side=tk.LEFT, padx=(8, 0))

    def _wrap_view_visibility(self) -> None:
        original = getattr(self.app, "_apply_view_visibility", None)
        if not callable(original):
            return

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            self._sync_visibility()
            return result

        self.app._apply_view_visibility = wrapped

    def _sync_visibility(self) -> None:
        visible_var = getattr(self.app, "_show_waveform_tools_var", None)
        visible = True if visible_var is None else bool(visible_var.get())
        manager = self.frame.winfo_manager()
        if visible and not manager:
            self.frame.pack(
                fill=tk.X,
                pady=(0, 4),
                before=self.app._waveform_canvas,
            )
        elif not visible and manager:
            self.frame.pack_forget()

    def _selected_row(self) -> Any | None:
        return getattr(self.app, "_detail_row", None)

    def _editing_blocked(self, row: Any | None) -> bool:
        if getattr(self.app, "_busy", False):
            return True
        return bool(self.app._block_catalog_edit(row))

    def _on_edit_mode_toggled(self) -> None:
        row = self._selected_row()
        if self.edit_mode_var.get():
            if self._editing_blocked(row):
                self.edit_mode_var.set(False)
                return
            if row is None or not row.path:
                self.edit_mode_var.set(False)
                self.app._set_status("Kein Sample ausgewählt.", tone="neutral")
                return
            self._pending_start_frame = None
            loop_mode = getattr(self.app, "_loop_edit_mode_var", None)
            if loop_mode is not None:
                loop_mode.set(False)
            attack_mode = getattr(self.app, "_attack_edit_mode_var", None)
            if attack_mode is not None:
                attack_mode.set(False)
            self.app._waveform_usage_var.set(EDIT_REGION_HINT)
            self.app._set_status(
                "Bereich schneiden aktiv — 1. Klick: Start",
                tone="active",
            )
            return

        self._pending_start_frame = None
        self.app._update_waveform_usage_hint()
        self.app._set_status("Bereich schneiden aus", tone="neutral")

    def _on_waveform_click(self, event: tk.Event) -> Any:
        if not self.edit_mode_var.get():
            return self.app._on_waveform_click(event)

        row = self._selected_row()
        if self._editing_blocked(row):
            return "break"
        if row is None or not row.path:
            self.app._set_status("Kein Sample ausgewählt.", tone="neutral")
            return "break"

        try:
            total_frames, sample_rate = audio_source_frame_info(row.path)
            width = max(int(self.app._waveform_canvas.winfo_width()), 1)
            click_frame = frame_from_waveform_x(int(event.x), width, total_frames)
        except EditRegionValidationError as exc:
            self.app._set_status(
                f"Kann Schnittposition nicht bestimmen: {exc}",
                tone="error",
            )
            return "break"

        if self._pending_start_frame is None:
            self._pending_start_frame = click_frame
            self.app._set_status(
                f"Start gesetzt: Source-Frame {click_frame} — 2. Klick: Ende",
                tone="active",
            )
            return "break"

        start_frame = min(self._pending_start_frame, click_frame)
        end_frame_exclusive = max(self._pending_start_frame, click_frame)
        self._pending_start_frame = None

        try:
            previous = load_workbench_edit_region(row.path)
            grid = source_edit_grid_from_details(row.details)
            snap_mode = self.snap_mode_var.get().strip().lower() or "none"
            region = build_edit_region(
                source_ref=str(Path(row.path).expanduser().resolve()),
                source_start_frame=start_frame,
                source_end_frame_exclusive=end_frame_exclusive,
                source_sample_rate=sample_rate,
                total_source_frames=total_frames,
                snap_mode=snap_mode,  # type: ignore[arg-type]
                grid=grid,
            )
            stored = save_workbench_edit_region(region)
        except EditRegionValidationError as exc:
            self.app._set_status(f"Region nicht gespeichert: {exc}", tone="error")
            return "break"

        self._remember_undo(row.path, previous)
        self.edit_mode_var.set(False)
        self.app._update_waveform_usage_hint()
        self.app._draw_waveform(row)
        self.app._set_status(
            (
                f"Region gespeichert: [{stored.source_start_frame}, "
                f"{stored.source_end_frame_exclusive}) Frames "
                f"· Snap {stored.snap_mode}"
            ),
            tone="success",
        )
        return "break"

    def _remember_undo(
        self,
        source_path: str,
        previous_region: WorkbenchEditRegion | None,
    ) -> None:
        self._undo_available = True
        self._undo_source_ref = str(Path(source_path).expanduser().resolve())
        self._undo_region = previous_region

    def _delete_region(self) -> None:
        row = self._selected_row()
        if self._editing_blocked(row):
            return
        if row is None or not row.path:
            self.app._set_status("Kein Sample ausgewählt.", tone="neutral")
            return
        try:
            previous = load_workbench_edit_region(row.path)
            if previous is None:
                self.app._set_status("Keine Region gespeichert.", tone="neutral")
                return
            deleted = delete_workbench_edit_region(row.path)
        except EditRegionValidationError as exc:
            self.app._set_status(
                f"Region konnte nicht gelöscht werden: {exc}", tone="error"
            )
            return
        if not deleted:
            self.app._set_status("Keine Region gespeichert.", tone="neutral")
            return
        self._remember_undo(row.path, previous)
        self._pending_start_frame = None
        self.edit_mode_var.set(False)
        self.app._update_waveform_usage_hint()
        self.app._draw_waveform(row)
        self.app._set_status("Region gelöscht.", tone="success")

    def _undo(self) -> None:
        row = self._selected_row()
        if self._editing_blocked(row):
            return
        if row is None or not row.path:
            self.app._set_status("Kein Sample ausgewählt.", tone="neutral")
            return
        resolved = str(Path(row.path).expanduser().resolve())
        if not self._undo_available or self._undo_source_ref != resolved:
            self.app._set_status(
                "Kein letzter Regionszustand zum Zurücksetzen.", tone="neutral"
            )
            return
        try:
            if self._undo_region is None:
                delete_workbench_edit_region(row.path)
            else:
                save_workbench_edit_region(self._undo_region)
        except EditRegionValidationError as exc:
            self.app._set_status(f"Undo fehlgeschlagen: {exc}", tone="error")
            return
        self._undo_available = False
        self._undo_source_ref = None
        self._undo_region = None
        self.app._draw_waveform(row)
        self.app._set_status(
            "Letzten Regionszustand wiederhergestellt.", tone="success"
        )

    def _preview_region(self) -> None:
        row = self._selected_row()
        if row is None or not row.path:
            self.app._set_status("Kein Sample ausgewählt.", tone="neutral")
            return
        try:
            region = load_workbench_edit_region(row.path)
        except EditRegionValidationError as exc:
            self.app._set_status(
                f"Region konnte nicht geladen werden: {exc}", tone="error"
            )
            return
        if region is None:
            self.app._set_status("Keine Region gespeichert.", tone="neutral")
            return
        result = self.app._preview.play_frame_region(
            row.path,
            start_frame=region.source_start_frame,
            end_frame_exclusive=region.source_end_frame_exclusive,
        )
        if result.ok:
            self.app._set_status(
                (
                    f"Region-Preview [{region.source_start_frame}, "
                    f"{region.source_end_frame_exclusive}) Frames"
                ),
                tone="active",
            )
        else:
            self.app._set_status(
                result.message or "Region-Preview fehlgeschlagen.",
                tone="error",
            )

    def _render_region(self) -> None:
        row = self._selected_row()
        if row is None or not row.path:
            self.app._set_status("Kein Sample ausgewählt.", tone="neutral")
            return
        try:
            region = load_workbench_edit_region(row.path)
        except EditRegionValidationError as exc:
            self.app._set_status(
                f"Region konnte nicht geladen werden: {exc}", tone="error"
            )
            return
        if region is None:
            self.app._set_status("Keine Region gespeichert.", tone="neutral")
            return
        destination = filedialog.askdirectory(
            title="Region rendern — Zielordner wählen"
        )
        if not destination:
            self.app._set_status("Rendern abgebrochen.", tone="neutral")
            return
        result = render_workbench_edit_region(
            region,
            Path(destination),
            source_audio_path=row.path,
        )
        if result.status != "rendered":
            detail = ""
            if result.error:
                detail = str(
                    result.error.get("message") or result.error.get("code") or ""
                )
            self.app._set_status(
                f"Region konnte nicht gerendert werden. {detail}".strip(),
                tone="error",
            )
            return
        self.app._set_status(
            f"Region gerendert: assets/{result.request.file_name}",
            tone="success",
        )

    def _draw_waveform_with_region(self, row: Any | None) -> None:
        self._base_draw(row)
        if row is None or not row.path:
            return
        try:
            region = load_workbench_edit_region(row.path)
            if region is None:
                return
            total_frames, _sample_rate = audio_source_frame_info(row.path)
        except EditRegionValidationError:
            return
        width = max(int(self.app._waveform_canvas.winfo_width()), 1)
        height = max(int(self.app._waveform_canvas.winfo_height()), 1)
        bounds = frame_region_x(
            region.source_start_frame,
            region.source_end_frame_exclusive,
            total_frames,
            width,
        )
        if bounds is None:
            return
        x_start, x_end = bounds
        canvas = self.app._waveform_canvas
        canvas.create_rectangle(
            x_start,
            1,
            x_end,
            height - 1,
            fill=EDIT_REGION_FILL,
            outline="",
            stipple="gray50",
        )
        for marker_x in (x_start, x_end):
            canvas.create_line(
                marker_x,
                2,
                marker_x,
                height - 2,
                fill=EDIT_REGION_MARKER,
                width=2,
            )


def attach_workbench_editing_ui(app: Any) -> WorkbenchEditingUI:
    return WorkbenchEditingUI(app)


__all__ = [
    "EDIT_REGION_FILL",
    "EDIT_REGION_HINT",
    "EDIT_REGION_MARKER",
    "WorkbenchEditingUI",
    "attach_workbench_editing_ui",
]
