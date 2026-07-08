"""Local workbench UI — tkinter playlist view for folder analysis."""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .workbench_controller import (
    WorkbenchCueMetadata,
    WorkbenchResult,
    WorkbenchRow,
    add_workbench_library_folder,
    analyze_folder_for_workbench,
    export_workbench_rows_to_csv,
    filter_workbench_rows,
    format_path_display_lines,
    get_preview_start_ms,
    get_workbench_library_folders,
    load_cached_folder_rows,
    load_workbench_last_folder,
    load_workbench_sample_cue,
    preview_start_ms_from_waveform_x,
    remove_workbench_library_folder,
    save_workbench_last_folder,
    save_workbench_sample_cue,
    sort_workbench_rows,
    validate_workbench_folder,
)
from .workbench_library import WorkbenchCueNotFoundError, WorkbenchCueValidationError
from .workbench_preview import WorkbenchPreviewPlayer, preview_toggle_action
from .workbench_waveform import (
    compute_waveform_envelope,
    cue_marker_x,
    loop_region_x,
    read_audio_duration_ms,
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
WAVEFORM_HEIGHT = 72
CUE_MARKER = "#ffffff"
LOOP_REGION_FILL = "#1a3d28"
LOOP_MARKER = "#6fcf6f"

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


class WorkbenchApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Sample Brain — Local Workbench")
        self.root.configure(bg=BG_DARK)
        self.root.minsize(960, 560)

        self._rows: list[WorkbenchRow] = []
        self._visible_rows: list[WorkbenchRow] = []
        self._sort_column: str | None = None
        self._sort_reverse = False
        self._busy = False
        self._cancel_event = threading.Event()
        self._detail_copy_path: str | None = None
        self._preview = WorkbenchPreviewPlayer()
        self._preview_row_path: str | None = None
        self._detail_row: WorkbenchRow | None = None

        self._build_styles()
        self._build_layout()
        self._restore_last_folder()
        self._refresh_library_list()
        self._set_status("Bereit — Ordnerpfad eingeben oder wählen, dann Analyse starten.")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

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
        body.columnconfigure(0, weight=0, minsize=200)
        body.columnconfigure(1, weight=3)
        body.columnconfigure(2, weight=1)
        body.rowconfigure(0, weight=1)

        library_frame = ttk.Frame(body, style="Panel.TFrame", padding=8)
        library_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        lib_header = ttk.Frame(library_frame, style="Panel.TFrame")
        lib_header.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(lib_header, text="Library-Ordner", style="Heading.TLabel").pack(
            side=tk.LEFT, anchor=tk.W
        )
        lib_btns = ttk.Frame(lib_header, style="Panel.TFrame")
        lib_btns.pack(side=tk.RIGHT)
        ttk.Button(lib_btns, text="+", width=3, command=self._add_library_folder).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(lib_btns, text="−", width=3, command=self._remove_library_folder).pack(
            side=tk.LEFT
        )

        lib_list_frame = ttk.Frame(library_frame, style="Panel.TFrame")
        lib_list_frame.pack(fill=tk.BOTH, expand=True)

        self._library_list = tk.Listbox(
            lib_list_frame,
            bg=PANEL_ALT,
            fg=TEXT,
            selectbackground=ACCENT_DIM,
            selectforeground="#ffffff",
            highlightthickness=1,
            highlightbackground=BORDER,
            activestyle="none",
            font=("Segoe UI", 9),
            relief=tk.FLAT,
        )
        lib_scroll = ttk.Scrollbar(lib_list_frame, orient=tk.VERTICAL, command=self._library_list.yview)
        self._library_list.configure(yscrollcommand=lib_scroll.set)
        self._library_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        lib_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._library_list.bind("<<ListboxSelect>>", self._on_library_select)
        self._library_list.bind("<Double-Button-1>", self._on_library_activate)
        self._library_paths: list[str] = []

        playlist_frame = ttk.Frame(body, style="Panel.TFrame", padding=8)
        playlist_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 8))

        filter_bar = ttk.Frame(playlist_frame, style="Panel.TFrame")
        filter_bar.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(filter_bar, text="Suche:", style="Panel.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self._filter_var = tk.StringVar(value="")
        filter_entry = ttk.Entry(filter_bar, textvariable=self._filter_var)
        filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._filter_var.trace_add("write", self._on_filter_changed)
        filter_entry.bind("<Escape>", self._clear_filter)
        ttk.Button(filter_bar, text="CSV exportieren", command=self._export_csv).pack(
            side=tk.RIGHT, padx=(8, 0)
        )

        tree_frame = ttk.Frame(playlist_frame, style="Panel.TFrame")
        tree_frame.pack(fill=tk.BOTH, expand=True)

        col_ids = [c[0] for c in COLUMNS]
        self._tree = ttk.Treeview(
            tree_frame,
            columns=col_ids,
            show="headings",
            selectmode="browse",
        )
        for col_id, heading, width in COLUMNS:
            self._tree.heading(
                col_id,
                text=heading,
                command=lambda c=col_id: self._on_sort_column(c),
            )
            self._tree.column(col_id, width=width, anchor=tk.W if col_id == "name" else tk.CENTER)

        scroll_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll_y.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-Button-1>", self._on_tree_double_click)
        self._tree.bind("<space>", self._on_space_preview)

        detail_frame = ttk.Frame(body, style="Panel.TFrame", padding=10)
        detail_frame.grid(row=0, column=2, sticky="nsew")
        detail_header = ttk.Frame(detail_frame, style="Panel.TFrame")
        detail_header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(detail_header, text="Sample-Details", style="Heading.TLabel").pack(
            side=tk.LEFT, anchor=tk.W
        )
        detail_actions = ttk.Frame(detail_header, style="Panel.TFrame")
        detail_actions.pack(side=tk.RIGHT)
        self._copy_path_btn = ttk.Button(
            detail_actions,
            text="Pfad kopieren",
            command=self._copy_detail_path,
            state=tk.DISABLED,
        )
        self._copy_path_btn.pack(side=tk.LEFT)

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

        self._waveform_canvas = tk.Canvas(
            detail_frame,
            height=WAVEFORM_HEIGHT,
            bg=PANEL_ALT,
            highlightthickness=1,
            highlightbackground=BORDER,
            relief=tk.FLAT,
        )
        self._waveform_canvas.pack(fill=tk.X, pady=(8, 0))
        self._waveform_canvas.bind("<Configure>", self._on_waveform_resize)
        self._waveform_canvas.bind("<Button-1>", self._on_waveform_click)
        self._waveform_canvas.bind("<Button-3>", self._on_waveform_right_click)

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

    def _library_display_label(self, path: str) -> str:
        parts = Path(path).parts
        if len(parts) <= 2:
            return path
        return f"…/{'/'.join(parts[-2:])}"

    def _refresh_library_list(self) -> None:
        folders = get_workbench_library_folders()
        self._library_paths = [folder.path for folder in folders]
        self._library_list.delete(0, tk.END)
        for folder_path in self._library_paths:
            self._library_list.insert(tk.END, self._library_display_label(folder_path))

    def _selected_library_path(self) -> str | None:
        selection = self._library_list.curselection()
        if not selection:
            return None
        index = int(selection[0])
        if 0 <= index < len(self._library_paths):
            return self._library_paths[index]
        return None

    def _add_library_folder(self) -> None:
        if self._busy:
            return
        raw = self._folder_var.get().strip()
        if raw:
            validation = validate_workbench_folder(raw)
            if not validation.ok:
                messagebox.showerror(
                    "Library",
                    validation.error_message or "Ungültiger Ordner",
                )
                return
            assert validation.normalized_path is not None
            folder = validation.normalized_path
        else:
            chosen = filedialog.askdirectory(title="Ordner zur Library hinzufügen")
            if not chosen:
                return
            validation = validate_workbench_folder(chosen)
            if not validation.ok:
                messagebox.showerror(
                    "Library",
                    validation.error_message or "Ungültiger Ordner",
                )
                return
            assert validation.normalized_path is not None
            folder = validation.normalized_path

        add_workbench_library_folder(folder)
        self._folder_var.set(str(folder))
        save_workbench_last_folder(folder)
        self._refresh_library_list()
        self._select_library_path(str(folder))
        self._load_cached_folder(folder, announce_if_empty=True)
        self._set_status(f"Ordner zur Library hinzugefügt: {folder}", tone="success")

    def _remove_library_folder(self) -> None:
        if self._busy:
            return
        path = self._selected_library_path()
        if path is None:
            messagebox.showinfo("Library", "Bitte zuerst einen Library-Ordner auswählen.")
            return
        confirmed = messagebox.askyesno(
            "Library entfernen",
            "Nur aus Sample Brain entfernen?\n\n"
            "Cache-Metadaten werden gelöscht. Originaldateien bleiben erhalten.",
        )
        if not confirmed:
            return
        removed = remove_workbench_library_folder(path)
        self._refresh_library_list()
        if removed:
            self._set_status("Ordner aus Library entfernt (Dateien unverändert).", tone="neutral")
        else:
            self._set_status("Ordner war nicht in der Library.", tone="neutral")

    def _select_library_path(self, path: str) -> None:
        try:
            index = self._library_paths.index(path)
        except ValueError:
            return
        self._library_list.selection_clear(0, tk.END)
        self._library_list.selection_set(index)
        self._library_list.see(index)

    def _on_library_select(self, _event: tk.Event | None = None) -> None:
        if self._busy:
            return
        path = self._selected_library_path()
        if path is None:
            return
        self._folder_var.set(path)
        save_workbench_last_folder(path)
        self._load_cached_folder(Path(path), announce_if_empty=True)

    def _on_library_activate(self, _event: tk.Event | None = None) -> None:
        self._on_library_select()

    def _load_cached_folder(self, folder: Path, *, announce_if_empty: bool = False) -> None:
        rows = load_cached_folder_rows(folder)
        if not rows:
            self._clear_playlist()
            if announce_if_empty:
                self._set_status(
                    "Kein Cache für diesen Ordner — Analyse starten, um Samples zu laden.",
                    tone="neutral",
                )
            return
        self._rows = rows
        summary = {
            "files_found": len(rows),
            "analyzed_count": sum(1 for row in rows if row.status == "ok"),
            "error_count": sum(1 for row in rows if row.status == "error"),
            "cache_hits": len(rows),
            "cache_misses": 0,
        }
        self._populate_playlist(WorkbenchResult(summary=summary, rows=rows))
        self._set_status(
            f"{len(rows)} gecachte Samples geladen — Analyse starten für Aktualisierung.",
            tone="success",
        )

    def _on_folder_enter(self, _event: tk.Event | None = None) -> None:
        self._start_analysis()

    def _restore_last_folder(self) -> None:
        remembered = load_workbench_last_folder()
        if remembered:
            self._folder_var.set(remembered)

    def _resolve_folder(self) -> Path | None:
        validation = validate_workbench_folder(self._folder_var.get())
        if not validation.ok:
            message = validation.error_message or "Ungültiger Ordner"
            self._set_status(message, tone="error")
            messagebox.showerror("Ordner", message)
            return None
        assert validation.normalized_path is not None
        self._folder_var.set(str(validation.normalized_path))
        save_workbench_last_folder(validation.normalized_path)
        return validation.normalized_path

    def _pick_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Sample-Ordner wählen")
        if not chosen:
            return
        self._folder_var.set(chosen)
        save_workbench_last_folder(chosen)
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

        self._stop_preview()
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
        self._update_preview_state(self._selected_row())

        if error is not None:
            self._set_status(f"Fehler: {error}", tone="error")
            messagebox.showerror("Analyse", str(error))
            return

        assert result is not None
        self._rows = result.rows
        self._populate_playlist(result)
        self._refresh_library_list()
        folder_path = str(self._folder_var.get())
        self._select_library_path(folder_path)

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
        cache_hits = s.get("cache_hits", 0)
        cache_misses = s.get("cache_misses", 0)
        if cache_hits or cache_misses:
            self._set_status(
                f"Fertig — {s['files_found']} Dateien, "
                f"{cache_hits} aus Cache, {cache_misses} neu analysiert, "
                f"{s['error_count']} Fehler.",
                tone=tone,
            )
        else:
            self._set_status(
                f"Fertig — {s['files_found']} Dateien, "
                f"{s['analyzed_count']} analysiert, {s['error_count']} Fehler.",
                tone=tone,
            )

    def _clear_playlist(self) -> None:
        self._stop_preview()
        self._tree.delete(*self._tree.get_children())
        self._rows = []
        self._visible_rows = []
        self._sort_column = None
        self._sort_reverse = False
        self._filter_var.set("")
        self._update_sort_headings()
        self._set_detail(None)

    def _on_sort_column(self, column: str) -> None:
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        self._refresh_playlist_view()

    def _update_sort_headings(self) -> None:
        for col_id, heading, _width in COLUMNS:
            label = heading
            if col_id == self._sort_column:
                label = f"{heading} {'▼' if self._sort_reverse else '▲'}"
            self._tree.heading(
                col_id,
                text=label,
                command=lambda c=col_id: self._on_sort_column(c),
            )

    def _on_filter_changed(self, *_args: object) -> None:
        self._refresh_playlist_view()

    def _clear_filter(self, _event: tk.Event | None = None) -> None:
        self._filter_var.set("")

    def _refresh_playlist_view(self) -> None:
        preserve_path = self._preview_row_path
        visible = filter_workbench_rows(self._rows, self._filter_var.get())
        if self._sort_column is not None:
            visible = sort_workbench_rows(
                visible,
                self._sort_column,
                reverse=self._sort_reverse,
            )
        self._visible_rows = visible
        self._update_sort_headings()
        self._tree.delete(*self._tree.get_children())
        for idx, row in enumerate(self._visible_rows):
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
        if preserve_path:
            for idx, row in enumerate(self._visible_rows):
                if row.path == preserve_path:
                    self._tree.selection_set(str(idx))
                    self._tree.see(str(idx))
                    self._set_detail(row)
                    return
        self._set_detail(None)

    def _populate_playlist(self, result: WorkbenchResult) -> None:
        self._rows = result.rows
        self._refresh_playlist_view()

    def _selected_row(self) -> WorkbenchRow | None:
        selected = self._tree.selection()
        if not selected:
            return None
        idx = int(selected[0])
        if 0 <= idx < len(self._visible_rows):
            return self._visible_rows[idx]
        return None

    def _on_select(self, _event: tk.Event | None = None) -> None:
        row = self._selected_row()
        if row is None:
            self._set_detail(None)
            return
        if (
            self._preview.current_path is not None
            and row.path
            and Path(row.path).resolve() != self._preview.current_path
        ):
            self._stop_preview()
        self._set_detail(row)

    def _on_tree_double_click(self, _event: tk.Event | None = None) -> None:
        if self._busy:
            return
        self._on_select()
        self._play_preview()

    def _on_space_preview(self, _event: tk.Event | None = None) -> str:
        if self._busy or not self._preview_row_path:
            return "break"
        action = preview_toggle_action(
            is_playing=self._preview.current_path is not None,
            current_path=self._preview.current_path,
            requested_path=Path(self._preview_row_path),
        )
        if action == "stop":
            self._stop_preview()
        else:
            self._play_preview()
        return "break"

    def _on_close(self) -> None:
        self._stop_preview()
        self.root.destroy()

    def _update_preview_state(self, row: WorkbenchRow | None) -> None:
        has_path = row is not None and bool(row.path)
        self._preview_row_path = row.path if has_path else None

    def _play_preview(
        self,
        *,
        start_ms: int | None = None,
        from_click_position: bool = False,
    ) -> None:
        if not self._preview_row_path:
            return
        if start_ms is None:
            start_ms = get_preview_start_ms(self._preview_row_path)
        result = self._preview.play(self._preview_row_path, start_ms=start_ms)
        name = Path(self._preview_row_path).name
        if result.ok:
            if from_click_position:
                self._set_status(
                    f"Wiedergabe ab Klickposition ({start_ms} ms): {name}",
                    tone="active",
                )
            elif start_ms > 0:
                self._set_status(f"Wiedergabe ab Cue ({start_ms} ms): {name}", tone="active")
            else:
                self._set_status(f"Wiedergabe ab Anfang: {name}", tone="active")
        else:
            self._set_status(result.message or "Wiedergabe fehlgeschlagen.", tone="error")

    def _stop_preview(self) -> None:
        self._preview.stop()

    def _copy_detail_path(self) -> None:
        if not self._detail_copy_path:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self._detail_copy_path)
        self._set_status("Pfad in Zwischenablage kopiert.", tone="success")

    def _export_csv(self) -> None:
        rows = self._visible_rows if self._visible_rows else self._rows
        if not rows:
            messagebox.showinfo("Export", "Keine Playlist-Daten zum Exportieren.")
            return
        destination = filedialog.asksaveasfilename(
            title="Playlist als CSV speichern",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Alle Dateien", "*.*")],
        )
        if not destination:
            return
        try:
            count = export_workbench_rows_to_csv(rows, Path(destination))
        except OSError as exc:
            messagebox.showerror("Export", f"Export fehlgeschlagen: {exc}")
            return
        self._set_status(f"CSV exportiert ({count} Zeilen).", tone="success")

    def _on_waveform_resize(self, _event: tk.Event | None = None) -> None:
        self._draw_waveform(self._detail_row)

    def _play_selected_from_waveform(self) -> None:
        if self._busy:
            return
        row = self._detail_row
        if row is None or not row.path:
            self._set_status("Kein Sample ausgewählt.", tone="neutral")
            return
        self._play_preview()

    def _play_selected_from_waveform_position(self, x: int) -> None:
        if self._busy:
            return
        row = self._detail_row
        if row is None or not row.path:
            self._set_status("Kein Sample ausgewählt.", tone="neutral")
            return
        duration_ms = read_audio_duration_ms(row.path)
        if duration_ms is None:
            self._set_status("Kann Startposition nicht bestimmen.", tone="error")
            return
        width = max(int(self._waveform_canvas.winfo_width()), 1)
        start_ms = preview_start_ms_from_waveform_x(int(x), width, duration_ms)
        self._play_preview(start_ms=start_ms, from_click_position=True)

    def _cue_start_ms_from_waveform_x(self, x: int) -> int | None:
        """Map waveform canvas x to cue start ms, or None when duration is unknown."""
        row = self._detail_row
        if row is None or not row.path:
            return None
        duration_ms = read_audio_duration_ms(row.path)
        if duration_ms is None:
            return None
        width = max(int(self._waveform_canvas.winfo_width()), 1)
        return preview_start_ms_from_waveform_x(int(x), width, duration_ms)

    def _set_selected_cue_from_waveform_position(self, x: int) -> None:
        if self._busy:
            return
        row = self._detail_row
        if row is None or not row.path:
            self._set_status("Kein Sample ausgewählt.", tone="neutral")
            return
        duration_ms = read_audio_duration_ms(row.path)
        if duration_ms is None:
            self._set_status("Kann Cue-Position nicht bestimmen.", tone="error")
            return
        cue_start_ms = self._cue_start_ms_from_waveform_x(x)
        if cue_start_ms is None:
            self._set_status("Kann Cue-Position nicht bestimmen.", tone="error")
            return
        try:
            existing = load_workbench_sample_cue(row.path)
            metadata = WorkbenchCueMetadata(
                cue_start_ms=cue_start_ms,
                attack_ms=existing.attack_ms,
                loop_start_ms=existing.loop_start_ms,
                loop_end_ms=existing.loop_end_ms,
                cue_source="manual",
            )
            save_workbench_sample_cue(row.path, metadata, duration_ms=duration_ms)
        except WorkbenchCueNotFoundError:
            self._set_status(
                "Sample nicht in der lokalen Bibliothek — zuerst analysieren.",
                tone="error",
            )
            return
        except WorkbenchCueValidationError as exc:
            self._set_status(f"Cue konnte nicht gespeichert werden: {exc}", tone="error")
            return
        self._draw_waveform(row)
        self._set_status(f"Cue dauerhaft gesetzt: {cue_start_ms} ms", tone="success")

    def _on_waveform_click(self, event: tk.Event) -> None:
        if event.state & 0x0001:
            self._set_selected_cue_from_waveform_position(int(event.x))
            return
        self._play_selected_from_waveform()

    def _on_waveform_right_click(self, event: tk.Event) -> None:
        self._play_selected_from_waveform_position(int(event.x))

    def _draw_waveform(self, row: WorkbenchRow | None) -> None:
        canvas = self._waveform_canvas
        canvas.delete("all")
        width = max(int(canvas.winfo_width()), 1)
        height = max(int(canvas.winfo_height()), 1)
        if row is None or not row.path:
            canvas.create_text(width // 2, height // 2, text="—", fill=TEXT_MUTED)
            return
        max_points = max(width // 2, 48)
        envelope = compute_waveform_envelope(row.path, max_points=max_points)
        if not envelope:
            canvas.create_text(
                width // 2,
                height // 2,
                text="Waveform nicht verfügbar",
                fill=TEXT_MUTED,
            )
            return
        mid = height // 2
        step = width / len(envelope)
        cue = load_workbench_sample_cue(row.path)
        duration_ms = read_audio_duration_ms(row.path)
        loop_bounds: tuple[int, int] | None = None
        if duration_ms is not None:
            loop_bounds = loop_region_x(
                cue.loop_start_ms,
                cue.loop_end_ms,
                duration_ms,
                width,
            )
            if loop_bounds is not None:
                x_start, x_end = loop_bounds
                canvas.create_rectangle(
                    x_start,
                    1,
                    x_end,
                    height - 1,
                    fill=LOOP_REGION_FILL,
                    outline="",
                )
        for index, peak in enumerate(envelope):
            x = int(index * step + step / 2)
            bar_height = max(1, int(peak * (height * 0.45)))
            canvas.create_line(
                x,
                mid - bar_height,
                x,
                mid + bar_height,
                fill=ACCENT,
            )
        if duration_ms is not None:
            if loop_bounds is not None:
                x_start, x_end = loop_bounds
                for marker_x in (x_start, x_end):
                    canvas.create_line(
                        marker_x,
                        2,
                        marker_x,
                        height - 2,
                        fill=LOOP_MARKER,
                        width=2,
                    )
            marker_x = cue_marker_x(cue.cue_start_ms, duration_ms, width)
            if marker_x is not None:
                canvas.create_line(
                    marker_x,
                    2,
                    marker_x,
                    height - 2,
                    fill=CUE_MARKER,
                    width=2,
                )

    def _set_detail(self, row: WorkbenchRow | None) -> None:
        self._detail_row = row
        self._detail_text.configure(state=tk.NORMAL)
        self._detail_text.delete("1.0", tk.END)
        self._detail_copy_path = row.path if row is not None else None
        self._update_preview_state(row)
        if row is None:
            self._copy_path_btn.state(["disabled"])
            self._detail_text.insert(tk.END, "Kein Sample ausgewählt.")
        else:
            self._copy_path_btn.state(["!disabled"])
            lines = [
                f"Name:     {row.display_name}",
                "Pfad:",
            ]
            lines.extend(format_path_display_lines(row.path))
            lines.append("Relativ:")
            lines.extend(format_path_display_lines(row.relative_path))
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
        self._draw_waveform(row)

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
