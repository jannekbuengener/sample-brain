"""Local workbench UI — tkinter playlist view for folder analysis."""
from __future__ import annotations

import threading
import textwrap
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .workbench_controller import (
    WorkbenchResult,
    WorkbenchRow,
    analyze_folder_for_workbench,
    validate_workbench_folder,
)

# Dark palette inspired by ui_mockup.png (functional, not pixel-perfect).
BG_DARK = "#121212"
PANEL = "#1e1e1e"
PANEL_ALT = "#252525"
ACCENT = "#ff4500"
ACCENT_DIM = "#3d1510"
TEXT = "#e8e8e8"
TEXT_MUTED = "#9a9a9a"
ERROR = "#ff3b30"
SUCCESS = "#6fcf6f"
BORDER = "#333333"

COLUMNS = (
    ("name", "Name", 180),
    ("bpm", "BPM", 60),
    ("key", "Key", 50),
    ("key_conf", "key_conf", 70),
    ("loudness", "Loudness", 80),
    ("brightness", "Brightness", 90),
    ("pred_type", "Type", 90),
    ("status", "Status", 70),
)


def _fmt(value: float | None, *, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def _wrap_text(value: str, *, width: int = 52) -> str:
    if len(value) <= width:
        return value
    return textwrap.fill(value, width=width, break_long_words=True, break_on_hyphens=False)


class WorkbenchApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Sample Brain — Local Workbench")
        self.root.configure(bg=BG_DARK)
        self.root.minsize(960, 560)

        self._rows: list[WorkbenchRow] = []
        self._busy = False
        self._cancel_event = threading.Event()

        self._build_styles()
        self._build_layout()
        self._set_status("Bereit — Ordnerpfad eingeben oder wählen, dann Analyse starten.")

    def _build_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=BG_DARK, foreground=TEXT, fieldbackground=PANEL)
        style.configure("TFrame", background=BG_DARK)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG_DARK, foreground=TEXT)
        style.configure("Muted.TLabel", background=BG_DARK, foreground=TEXT_MUTED)
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        style.configure("Heading.TLabel", background=PANEL, foreground=ACCENT, font=("Segoe UI", 11, "bold"))
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#ffffff",
            padding=(12, 6),
            font=("Segoe UI", 10, "bold"),
        )
        style.map("Accent.TButton", background=[("active", "#ff6a33"), ("disabled", "#555555")])
        style.configure("TButton", background=PANEL_ALT, foreground=TEXT, padding=(10, 5))
        style.map("TButton", background=[("active", "#333333")])
        style.configure(
            "Treeview",
            background=PANEL,
            foreground=TEXT,
            fieldbackground=PANEL,
            bordercolor=BORDER,
            rowheight=26,
        )
        style.configure(
            "Treeview.Heading",
            background=PANEL_ALT,
            foreground=TEXT,
            relief="flat",
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", ACCENT_DIM)],
            foreground=[("selected", "#ffffff")],
        )
        style.configure("TEntry", fieldbackground=PANEL_ALT, foreground=TEXT, insertcolor=TEXT)
        style.configure("Status.TLabel", background=PANEL_ALT, foreground=TEXT_MUTED, padding=(8, 4))

    def _build_layout(self) -> None:
        toolbar = ttk.Frame(self.root, padding=(12, 10, 12, 6))
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="Ordner:").pack(side=tk.LEFT, padx=(0, 6))
        self._folder_var = tk.StringVar(value="")
        self._folder_entry = ttk.Entry(toolbar, textvariable=self._folder_var)
        self._folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self._folder_entry.bind("<Return>", self._on_folder_enter)

        ttk.Button(toolbar, text="Ordner wählen", command=self._pick_folder).pack(side=tk.LEFT, padx=(0, 8))
        self._analyze_btn = ttk.Button(
            toolbar, text="Analyse starten", style="Accent.TButton", command=self._start_analysis
        )
        self._analyze_btn.pack(side=tk.LEFT, padx=(0, 8))
        self._cancel_btn = ttk.Button(
            toolbar, text="Abbrechen", command=self._cancel_analysis, state=tk.DISABLED
        )
        self._cancel_btn.pack(side=tk.LEFT, padx=(0, 16))

        ttk.Label(toolbar, text="Limit:").pack(side=tk.LEFT)
        self._limit_var = tk.StringVar(value="50")
        limit_entry = ttk.Entry(toolbar, textvariable=self._limit_var, width=6)
        limit_entry.pack(side=tk.LEFT, padx=(6, 0))

        body = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        playlist_frame = ttk.Frame(body, style="Panel.TFrame", padding=8)
        playlist_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        col_ids = [c[0] for c in COLUMNS]
        self._tree = ttk.Treeview(
            playlist_frame,
            columns=col_ids,
            show="headings",
            selectmode="browse",
        )
        for col_id, heading, width in COLUMNS:
            self._tree.heading(col_id, text=heading)
            self._tree.column(col_id, width=width, anchor=tk.W if col_id == "name" else tk.CENTER)

        scroll_y = ttk.Scrollbar(playlist_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll_y.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        detail_frame = ttk.Frame(body, style="Panel.TFrame", padding=10)
        detail_frame.grid(row=0, column=1, sticky="nsew")
        ttk.Label(detail_frame, text="Sample-Details", style="Heading.TLabel").pack(anchor=tk.W, pady=(0, 8))

        self._detail_text = tk.Text(
            detail_frame,
            wrap=tk.WORD,
            bg=PANEL_ALT,
            fg=TEXT,
            insertbackground=TEXT,
            relief=tk.FLAT,
            padx=8,
            pady=8,
            font=("Consolas", 10),
            state=tk.DISABLED,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self._detail_text.pack(fill=tk.BOTH, expand=True)

        status_bar = ttk.Frame(self.root, style="Panel.TFrame")
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        status_inner = ttk.Frame(status_bar, style="Panel.TFrame")
        status_inner.pack(fill=tk.X, padx=8, pady=4)
        self._status_var = tk.StringVar(value="")
        self._status_label = ttk.Label(status_inner, textvariable=self._status_var, style="Status.TLabel")
        self._status_label.pack(fill=tk.X, anchor=tk.W)
        self._progress = ttk.Progressbar(status_inner, mode="determinate", maximum=100)
        self._progress.pack(fill=tk.X, pady=(4, 0))
        self._progress.pack_forget()

    def _on_folder_enter(self, _event: tk.Event | None = None) -> None:
        self._start_analysis()

    def _resolve_folder(self) -> Path | None:
        validation = validate_workbench_folder(self._folder_var.get())
        if not validation.ok:
            message = validation.error_message or "Ungültiger Ordner"
            self._set_status(message, tone="error")
            messagebox.showerror("Ordner", message)
            return None
        assert validation.normalized_path is not None
        self._folder_var.set(str(validation.normalized_path))
        return validation.normalized_path

    def _pick_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Sample-Ordner wählen")
        if not chosen:
            return
        self._folder_var.set(chosen)
        self._set_status(f"Ordner: {chosen}")

    def _parse_limit(self) -> int | None:
        raw = self._limit_var.get().strip()
        if not raw:
            return None
        try:
            value = int(raw)
        except ValueError:
            messagebox.showerror("Limit", "Limit muss eine ganze Zahl sein.")
            return None
        if value <= 0:
            messagebox.showerror("Limit", "Limit muss größer als 0 sein.")
            return None
        return value

    def _start_analysis(self) -> None:
        if self._busy:
            return
        folder = self._resolve_folder()
        if folder is None:
            return
        limit = self._parse_limit()
        if self._limit_var.get().strip() and limit is None:
            return

        self._busy = True
        self._cancel_event.clear()
        self._analyze_btn.state(["disabled"])
        self._cancel_btn.state(["!disabled"])
        self._clear_playlist()
        self._show_progress(0, 1)
        self._set_status("Analyse startet …", tone="active")

        thread = threading.Thread(
            target=self._run_analysis,
            args=(folder, limit),
            daemon=True,
        )
        thread.start()

    def _cancel_analysis(self) -> None:
        if not self._busy:
            return
        self._cancel_event.set()
        self._cancel_btn.state(["disabled"])
        self._set_status("Abbruch angefordert …", tone="active")

    def _on_progress(self, current: int, total: int, display_name: str, phase: str) -> None:
        if phase == "scanning":
            self._set_status("Dateien werden gesammelt …", tone="active")
            return
        if total <= 0:
            self._hide_progress()
            self._set_status("Keine Audiodateien gefunden.", tone="neutral")
            return
        self._show_progress(current, total)
        if phase == "analyzing":
            self._set_status(f"Analysiere {current}/{total}: {display_name}", tone="active")
        elif phase == "error":
            self._set_status(
                f"Analysiere {current}/{total}: {display_name} (Fehler)",
                tone="active",
            )
        elif phase == "cancelled":
            self._set_status("Analyse abgebrochen.", tone="neutral")

    def _show_progress(self, current: int, total: int) -> None:
        if total <= 0:
            self._hide_progress()
            return
        self._progress.configure(maximum=total, value=min(current, total))
        if not self._progress.winfo_ismapped():
            self._progress.pack(fill=tk.X, pady=(4, 0))

    def _hide_progress(self) -> None:
        self._progress.configure(value=0)
        if self._progress.winfo_ismapped():
            self._progress.pack_forget()

    def _run_analysis(self, folder: Path, limit: int | None) -> None:
        def progress_cb(current: int, total: int, display_name: str, phase: str) -> None:
            self.root.after(
                0,
                lambda: self._on_progress(current, total, display_name, phase),
            )

        try:
            result = analyze_folder_for_workbench(
                folder,
                limit=limit,
                progress_callback=progress_cb,
                should_cancel=self._cancel_event.is_set,
            )
            self.root.after(0, lambda: self._on_analysis_done(result, None))
        except Exception as exc:
            self.root.after(0, lambda: self._on_analysis_done(None, exc))

    def _on_analysis_done(self, result: WorkbenchResult | None, error: Exception | None) -> None:
        self._busy = False
        self._cancel_event.clear()
        self._analyze_btn.state(["!disabled"])
        self._cancel_btn.state(["disabled"])
        self._hide_progress()

        if error is not None:
            self._set_status(f"Fehler: {error}", tone="error")
            messagebox.showerror("Analyse", str(error))
            return

        assert result is not None
        self._rows = result.rows
        self._populate_playlist(result)

        s = result.summary
        cancelled = s.get("cancelled", 0)
        if cancelled:
            self._set_status(
                f"Abgebrochen — {s['analyzed_count']} analysiert, "
                f"{s['error_count']} Fehler von {s['files_found']} Dateien.",
                tone="neutral",
            )
            return

        tone = "error" if s["error_count"] else "success"
        self._set_status(
            f"Fertig — {s['files_found']} Dateien, "
            f"{s['analyzed_count']} analysiert, {s['error_count']} Fehler.",
            tone=tone,
        )

    def _clear_playlist(self) -> None:
        self._tree.delete(*self._tree.get_children())
        self._rows = []
        self._set_detail(None)

    def _populate_playlist(self, result: WorkbenchResult) -> None:
        self._tree.delete(*self._tree.get_children())
        for idx, row in enumerate(result.rows):
            tags = ("error",) if row.status == "error" else ()
            self._tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    row.display_name,
                    _fmt(row.bpm, digits=1),
                    row.key or "—",
                    _fmt(row.key_conf, digits=3),
                    _fmt(row.loudness, digits=2),
                    _fmt(row.brightness, digits=1),
                    row.pred_type or row.sample_class or "—",
                    row.status,
                ),
                tags=tags,
            )
        self._tree.tag_configure("error", foreground=ERROR)

    def _on_select(self, _event: tk.Event | None = None) -> None:
        selected = self._tree.selection()
        if not selected:
            self._set_detail(None)
            return
        idx = int(selected[0])
        if 0 <= idx < len(self._rows):
            self._set_detail(self._rows[idx])

    def _set_detail(self, row: WorkbenchRow | None) -> None:
        self._detail_text.configure(state=tk.NORMAL)
        self._detail_text.delete("1.0", tk.END)
        if row is None:
            self._detail_text.insert(tk.END, "Kein Sample ausgewählt.")
        else:
            lines = [
                f"Name:     {row.display_name}",
                f"Pfad:",
            ]
            lines.extend(f"  {part}" for part in _wrap_text(row.path).splitlines())
            lines.append("Relativ:")
            lines.extend(f"  {part}" for part in _wrap_text(row.relative_path).splitlines())
            lines.append(f"Status:   {row.status}")
            short_hint = row.details.get("short_audio_warning")
            if short_hint:
                lines.append(f"Hinweis:  {short_hint}")
            if row.error:
                lines.append(f"Fehler:   {row.error}")
            if row.error_code:
                lines.append(f"Code:     {row.error_code}")
            err_detail = row.details.get("error_detail")
            if err_detail:
                lines.append(f"Ursache:  {err_detail}")
            lines.append("")
            if row.details:
                lines.append("— Analyse —")
                for key, value in row.details.items():
                    if key in {
                        "path",
                        "relative_path",
                        "error_code",
                        "error_detail",
                        "short_audio_warning_code",
                    }:
                        continue
                    if key == "short_audio_warning":
                        continue
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value)
                    lines.append(f"{key:16} {value}")
            else:
                lines.extend(
                    [
                        f"bpm:          {_fmt(row.bpm, digits=1)}",
                        f"key:          {row.key or '—'}",
                        f"key_conf:     {_fmt(row.key_conf, digits=3)}",
                        f"loudness:     {_fmt(row.loudness, digits=2)}",
                        f"brightness:   {_fmt(row.brightness, digits=1)}",
                        f"class:        {row.sample_class or '—'}",
                        f"pred_type:    {row.pred_type or '—'}",
                    ]
                )
            self._detail_text.insert(tk.END, "\n".join(lines))
        self._detail_text.configure(state=tk.DISABLED)

    def _set_status(self, message: str, *, tone: str = "neutral") -> None:
        self._status_var.set(message)
        color = TEXT_MUTED
        if tone == "active":
            color = ACCENT
        elif tone == "error":
            color = ERROR
        elif tone == "success":
            color = SUCCESS
        self._status_label.configure(foreground=color)


def run_workbench(on_ready: Callable[[], None] | None = None) -> None:
    """Start the workbench main loop. *on_ready* is for tests (called after init)."""
    root = tk.Tk()
    WorkbenchApp(root)
    if on_ready is not None:
        on_ready()
    root.mainloop()


__all__ = ["WorkbenchApp", "run_workbench"]
