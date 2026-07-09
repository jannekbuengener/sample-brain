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
    WorkbenchRowFilters,
    ALL_LIBRARY_VIEW_LABEL,
    CATALOG_VIEW_LABEL,
    WORKBENCH_CATALOG_LIBRARY_TOKEN,
    WORKBENCH_GLOBAL_LIBRARY_TOKEN,
    FILTER_ALL_LABEL,
    add_workbench_library_folder,
    analyze_folder_for_workbench,
    append_catalog_readonly_status_hint,
    apply_workbench_filters,
    catalog_available,
    catalog_row_display_name,
    CATALOG_READONLY_EDIT_MESSAGE,
    count_catalog_samples,
    DEFAULT_CATALOG_LOAD_LIMIT,
    export_workbench_rows_to_csv,
    effective_workbench_row_filters,
    effective_workbench_text_query,
    format_catalog_load_status,
    format_metadata_provenance_hint,
    format_path_display_lines,
    format_workbench_active_filter_summary,
    format_workbench_search_status,
    format_workbench_view_restore_status,
    format_workbench_view_section_hidden_status,
    WorkbenchSearchStatusContext,
    WorkbenchSearchMode,
    get_preview_start_ms,
    get_workbench_library_folders,
    is_catalog_readonly_row,
    load_all_cached_rows,
    load_cached_folder_rows,
    load_catalog_rows,
    load_workbench_last_folder,
    load_workbench_sample_cue,
    load_workbench_view_settings,
    parse_workbench_bpm_bound,
    preview_start_ms_from_waveform_x,
    remove_workbench_library_folder,
    save_workbench_last_folder,
    save_workbench_sample_cue,
    save_workbench_view_settings,
    sort_workbench_rows,
    validate_workbench_folder,
    workbench_filter_options,
    DEFAULT_WORKBENCH_VIEW_SETTINGS,
    VIEW_SECTION_FILTERS,
    VIEW_SECTION_LIBRARY_MANAGE,
    VIEW_SECTION_SEARCH,
    VIEW_SECTION_WAVEFORM_TOOLS,
    WORKBENCH_VIEW_TOGGLE_HELP,
    WorkbenchViewSettings,
)
from .workbench_attack_suggest import AttackSuggestion, suggest_attack_ms
from .workbench_library import WorkbenchCueNotFoundError, WorkbenchCueValidationError
from .workbench_preview import WorkbenchPreviewPlayer, preview_toggle_action
from .workbench_waveform import (
    attack_marker_x,
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
ATTACK_MARKER = "#ffc857"
WAVEFORM_USAGE_HINT = "Linksklick: Play · Rechtsklick: ab Stelle · Shift+Klick: Cue setzen"
WAVEFORM_LOOP_EDIT_HINT = "Loop-Modus: 1. Klick Start · 2. Klick Ende · Loop löschen"
WAVEFORM_ATTACK_EDIT_HINT = "Attack-Modus: Klick setzt Attack · Attack vorschlagen · Attack löschen"

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
        self._preview = WorkbenchPreviewPlayer()
        self._preview_row_path: str | None = None
        self._detail_row: WorkbenchRow | None = None
        self._loop_edit_pending_start_ms: int | None = None
        self._pending_attack_suggestion: AttackSuggestion | None = None
        self._global_library_mode = False
        self._catalog_library_mode = False
        self._catalog_total_count = 0
        self._catalog_load_limit: int | None = None
        self._view_settings = load_workbench_view_settings()

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

        view_bar = ttk.Frame(self.root, padding=(12, 0, 12, 6))
        view_bar.pack(fill=tk.X)
        ttk.Label(view_bar, text="Ansicht:", style="Muted.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        self._show_search_var = tk.BooleanVar(value=self._view_settings.show_search)
        self._show_filters_var = tk.BooleanVar(value=self._view_settings.show_filters)
        self._show_library_manage_var = tk.BooleanVar(value=self._view_settings.show_library_manage)
        self._show_waveform_tools_var = tk.BooleanVar(value=self._view_settings.show_waveform_tools)
        ttk.Checkbutton(
            view_bar,
            text="Suche",
            variable=self._show_search_var,
            command=lambda: self._on_view_section_toggled(VIEW_SECTION_SEARCH),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(
            view_bar,
            text="Filter",
            variable=self._show_filters_var,
            command=lambda: self._on_view_section_toggled(VIEW_SECTION_FILTERS),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(
            view_bar,
            text="Library +/−",
            variable=self._show_library_manage_var,
            command=lambda: self._on_view_section_toggled(VIEW_SECTION_LIBRARY_MANAGE),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(
            view_bar,
            text="Waveform-Werkzeuge",
            variable=self._show_waveform_tools_var,
            command=lambda: self._on_view_section_toggled(VIEW_SECTION_WAVEFORM_TOOLS),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            view_bar,
            text="Standardansicht wiederherstellen",
            command=self._restore_default_view,
        ).pack(side=tk.LEFT, padx=(8, 0))
        self._view_help_var = tk.StringVar(value=WORKBENCH_VIEW_TOGGLE_HELP)
        ttk.Label(
            view_bar,
            textvariable=self._view_help_var,
            style="Muted.TLabel",
        ).pack(side=tk.LEFT, padx=(16, 0))

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
        self._lib_manage_btns = lib_btns
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
        self._filter_bar = filter_bar
        ttk.Label(filter_bar, text="Suche:", style="Panel.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self._filter_var = tk.StringVar(value="")
        filter_entry = ttk.Entry(filter_bar, textvariable=self._filter_var)
        filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._filter_var.trace_add("write", self._on_filter_changed)
        filter_entry.bind("<Escape>", self._clear_filter)
        ttk.Button(filter_bar, text="CSV exportieren", command=self._export_csv).pack(
            side=tk.RIGHT, padx=(8, 0)
        )

        structured_bar = ttk.Frame(playlist_frame, style="Panel.TFrame")
        structured_bar.pack(fill=tk.X, pady=(0, 6))
        self._structured_bar = structured_bar
        self._source_filter_var = tk.StringVar(value=FILTER_ALL_LABEL)
        self._type_filter_var = tk.StringVar(value=FILTER_ALL_LABEL)
        self._key_filter_var = tk.StringVar(value=FILTER_ALL_LABEL)
        self._status_filter_var = tk.StringVar(value=FILTER_ALL_LABEL)
        self._source_filter_combo = self._add_structured_filter_combo(
            structured_bar,
            "Quelle:",
            self._source_filter_var,
            (FILTER_ALL_LABEL, "cache", "catalog"),
            width=9,
        )
        self._type_filter_combo = self._add_structured_filter_combo(
            structured_bar,
            "Type:",
            self._type_filter_var,
            (FILTER_ALL_LABEL,),
            width=10,
        )
        self._key_filter_combo = self._add_structured_filter_combo(
            structured_bar,
            "Key:",
            self._key_filter_var,
            (FILTER_ALL_LABEL,),
            width=8,
        )
        self._status_filter_combo = self._add_structured_filter_combo(
            structured_bar,
            "Status:",
            self._status_filter_var,
            (FILTER_ALL_LABEL, "ok", "error", "pending"),
            width=8,
        )
        self._bpm_min_var = tk.StringVar(value="")
        self._bpm_max_var = tk.StringVar(value="")
        self._add_bpm_filter_entry(structured_bar, "BPM von:", self._bpm_min_var)
        self._add_bpm_filter_entry(structured_bar, "BPM bis:", self._bpm_max_var)
        ttk.Button(
            structured_bar,
            text="Filter zurücksetzen",
            command=self._clear_filter,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        self._active_filter_var = tk.StringVar(value="")
        ttk.Label(
            playlist_frame,
            textvariable=self._active_filter_var,
            style="Muted.TLabel",
        ).pack(fill=tk.X, pady=(0, 4))

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

        waveform_controls = ttk.Frame(detail_frame, style="Panel.TFrame")
        waveform_controls.pack(fill=tk.X, pady=(8, 4))
        self._waveform_controls = waveform_controls
        self._loop_edit_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            waveform_controls,
            text="Loop bearbeiten",
            variable=self._loop_edit_mode_var,
            command=self._on_loop_edit_mode_toggled,
        ).pack(side=tk.LEFT)
        ttk.Button(
            waveform_controls,
            text="Loop löschen",
            command=self._clear_loop_metadata,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            waveform_controls,
            text="Loop vorhören",
            command=self._play_loop_preview,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            waveform_controls,
            text="Loop wiederholen",
            command=self._play_loop_repeat,
        ).pack(side=tk.LEFT, padx=(8, 0))
        self._attack_edit_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            waveform_controls,
            text="Attack bearbeiten",
            variable=self._attack_edit_mode_var,
            command=self._on_attack_edit_mode_toggled,
        ).pack(side=tk.LEFT, padx=(16, 0))
        ttk.Button(
            waveform_controls,
            text="Attack löschen",
            command=self._clear_attack_metadata,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            waveform_controls,
            text="Attack vorschlagen",
            command=self._suggest_attack_metadata,
        ).pack(side=tk.LEFT, padx=(16, 0))
        self._attack_suggest_apply_btn = ttk.Button(
            waveform_controls,
            text="Vorschlag übernehmen",
            command=self._apply_attack_suggestion,
            state=tk.DISABLED,
        )
        self._attack_suggest_apply_btn.pack(side=tk.LEFT, padx=(8, 0))

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
        self._waveform_usage_var = tk.StringVar(value=WAVEFORM_USAGE_HINT)
        self._waveform_usage_label = ttk.Label(
            detail_frame,
            textvariable=self._waveform_usage_var,
            style="Muted.TLabel",
        )
        self._waveform_usage_label.pack(fill=tk.X, pady=(2, 0))
        self._provenance_var = tk.StringVar(value="")
        self._provenance_label = ttk.Label(
            detail_frame,
            textvariable=self._provenance_var,
            style="Muted.TLabel",
        )
        self._provenance_label.pack(fill=tk.X, pady=(2, 0))

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
        self._apply_view_visibility(notify=False)

    def _current_view_settings(self) -> WorkbenchViewSettings:
        return WorkbenchViewSettings(
            show_search=bool(self._show_search_var.get()),
            show_filters=bool(self._show_filters_var.get()),
            show_library_manage=bool(self._show_library_manage_var.get()),
            show_waveform_tools=bool(self._show_waveform_tools_var.get()),
        )

    def _persist_view_settings(self) -> None:
        self._view_settings = self._current_view_settings()
        save_workbench_view_settings(self._view_settings)

    def _end_waveform_edit_modes(self) -> None:
        self._loop_edit_mode_var.set(False)
        self._attack_edit_mode_var.set(False)
        self._loop_edit_pending_start_ms = None
        self._update_waveform_usage_hint()

    def _apply_view_visibility(self, *, notify: bool, status_message: str | None = None) -> None:
        settings = self._current_view_settings()
        if settings.show_search:
            self._filter_bar.pack(fill=tk.X, pady=(0, 6))
        else:
            self._filter_bar.pack_forget()
            if self._filter_var.get().strip():
                self._filter_var.set("")

        if settings.show_filters:
            self._structured_bar.pack(fill=tk.X, pady=(0, 6))
        else:
            self._structured_bar.pack_forget()
            if self._current_row_filters() is not None:
                self._reset_structured_filters()

        if settings.show_library_manage:
            self._lib_manage_btns.pack(side=tk.RIGHT)
        else:
            self._lib_manage_btns.pack_forget()

        if settings.show_waveform_tools:
            self._waveform_controls.pack(fill=tk.X, pady=(8, 4))
            self._waveform_canvas.pack(fill=tk.X, pady=(8, 0))
            self._waveform_usage_label.pack(fill=tk.X, pady=(2, 0))
            self._provenance_label.pack(fill=tk.X, pady=(2, 0))
        else:
            self._end_waveform_edit_modes()
            self._waveform_controls.pack_forget()
            self._waveform_canvas.pack_forget()
            self._waveform_usage_label.pack_forget()
            self._provenance_label.pack_forget()

        self._view_settings = settings
        self._persist_view_settings()
        self._refresh_playlist_view()
        if notify and status_message:
            self._set_status(status_message, tone="neutral")

    def _on_view_section_toggled(self, section: str) -> None:
        settings = self._current_view_settings()
        hidden_messages = {
            VIEW_SECTION_SEARCH: (not settings.show_search, VIEW_SECTION_SEARCH),
            VIEW_SECTION_FILTERS: (not settings.show_filters, VIEW_SECTION_FILTERS),
            VIEW_SECTION_LIBRARY_MANAGE: (
                not settings.show_library_manage,
                VIEW_SECTION_LIBRARY_MANAGE,
            ),
            VIEW_SECTION_WAVEFORM_TOOLS: (
                not settings.show_waveform_tools,
                VIEW_SECTION_WAVEFORM_TOOLS,
            ),
        }
        is_hidden, key = hidden_messages.get(section, (False, section))
        status_message = (
            format_workbench_view_section_hidden_status(key) if is_hidden else None
        )
        self._apply_view_visibility(notify=True, status_message=status_message)

    def _restore_default_view(self) -> None:
        self._show_search_var.set(True)
        self._show_filters_var.set(True)
        self._show_library_manage_var.set(True)
        self._show_waveform_tools_var.set(True)
        self._apply_view_visibility(
            notify=True,
            status_message=format_workbench_view_restore_status(),
        )

    def _add_structured_filter_combo(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
        values: tuple[str, ...],
        *,
        width: int,
    ) -> ttk.Combobox:
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(frame, text=label, style="Panel.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        combo = ttk.Combobox(
            frame,
            textvariable=variable,
            values=values,
            width=width,
            state="readonly",
        )
        combo.pack(side=tk.LEFT)
        combo.bind("<<ComboboxSelected>>", self._on_structured_filter_changed)
        return combo

    def _add_bpm_filter_entry(
        self,
        parent: ttk.Frame,
        label: str,
        variable: tk.StringVar,
    ) -> ttk.Entry:
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(frame, text=label, style="Panel.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        entry = ttk.Entry(frame, textvariable=variable, width=6)
        entry.pack(side=tk.LEFT)
        variable.trace_add("write", self._on_structured_filter_changed)
        return entry

    def _on_structured_filter_changed(self, *_args: object) -> None:
        self._refresh_playlist_view()

    def _build_row_filters(self) -> WorkbenchRowFilters:
        source_label = self._source_filter_var.get().strip().casefold()
        if source_label == "cache":
            source = "cache"
        elif source_label == "catalog":
            source = "catalog"
        else:
            source = "all"
        return WorkbenchRowFilters(
            source=source,
            pred_type=self._type_filter_var.get(),
            key=self._key_filter_var.get(),
            status=self._status_filter_var.get(),
            min_bpm=parse_workbench_bpm_bound(self._bpm_min_var.get()),
            max_bpm=parse_workbench_bpm_bound(self._bpm_max_var.get()),
        )

    def _current_row_filters(self) -> WorkbenchRowFilters | None:
        filters = self._build_row_filters()
        return filters if filters.active() else None

    def _playlist_filters_active(self) -> bool:
        return bool(self._filter_var.get().strip()) or self._current_row_filters() is not None

    def _update_structured_filter_options(self) -> None:
        options = workbench_filter_options(self._rows)
        type_values = (FILTER_ALL_LABEL, *options["types"])
        key_values = (FILTER_ALL_LABEL, *options["keys"])
        self._type_filter_combo["values"] = type_values
        self._key_filter_combo["values"] = key_values
        if self._type_filter_var.get() not in type_values:
            self._type_filter_var.set(FILTER_ALL_LABEL)
        if self._key_filter_var.get() not in key_values:
            self._key_filter_var.set(FILTER_ALL_LABEL)

    def _reset_structured_filters(self) -> None:
        self._source_filter_var.set(FILTER_ALL_LABEL)
        self._type_filter_var.set(FILTER_ALL_LABEL)
        self._key_filter_var.set(FILTER_ALL_LABEL)
        self._status_filter_var.set(FILTER_ALL_LABEL)
        self._bpm_min_var.set("")
        self._bpm_max_var.set("")

    def _library_display_label(self, path: str) -> str:
        parts = Path(path).parts
        if len(parts) <= 2:
            return path
        return f"…/{'/'.join(parts[-2:])}"

    def _refresh_library_list(self) -> None:
        folders = get_workbench_library_folders()
        self._library_paths = (
            [WORKBENCH_GLOBAL_LIBRARY_TOKEN, WORKBENCH_CATALOG_LIBRARY_TOKEN]
            + [folder.path for folder in folders]
        )
        self._library_list.delete(0, tk.END)
        self._library_list.insert(tk.END, f"★ {ALL_LIBRARY_VIEW_LABEL}")
        catalog_label = CATALOG_VIEW_LABEL
        if not catalog_available():
            catalog_label = f"{CATALOG_VIEW_LABEL} (nicht verfügbar)"
        self._library_list.insert(tk.END, f"⧉ {catalog_label}")
        for folder_path in self._library_paths[2:]:
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
        if path == WORKBENCH_GLOBAL_LIBRARY_TOKEN:
            messagebox.showinfo(
                "Library",
                "Bitte einen konkreten Ordner zum Entfernen auswählen.",
            )
            return
        if path == WORKBENCH_CATALOG_LIBRARY_TOKEN:
            messagebox.showinfo(
                "Library",
                "Catalog-Eintrag ist read-only und kann nicht entfernt werden.",
            )
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
        if self._global_library_mode:
            self._load_all_cached_samples()
        elif self._catalog_library_mode:
            self._load_catalog_samples()
        elif removed:
            self._set_status("Ordner aus Library entfernt (Dateien unverändert).", tone="neutral")
        else:
            self._set_status("Ordner war nicht in der Library.", tone="neutral")

    def _select_library_path(self, path: str) -> None:
        if path == WORKBENCH_GLOBAL_LIBRARY_TOKEN:
            self._library_list.selection_clear(0, tk.END)
            self._library_list.selection_set(0)
            self._library_list.see(0)
            return
        if path == WORKBENCH_CATALOG_LIBRARY_TOKEN:
            self._library_list.selection_clear(0, tk.END)
            self._library_list.selection_set(1)
            self._library_list.see(1)
            return
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
        if path == WORKBENCH_GLOBAL_LIBRARY_TOKEN:
            self._load_all_cached_samples()
            return
        if path == WORKBENCH_CATALOG_LIBRARY_TOKEN:
            self._load_catalog_samples()
            return
        self._global_library_mode = False
        self._catalog_library_mode = False
        self._folder_var.set(path)
        save_workbench_last_folder(path)
        self._load_cached_folder(Path(path), announce_if_empty=True)

    def _on_library_activate(self, _event: tk.Event | None = None) -> None:
        self._on_library_select()

    def _load_all_cached_samples(self) -> None:
        rows = load_all_cached_rows()
        self._global_library_mode = True
        self._catalog_library_mode = False
        if not rows:
            self._clear_playlist()
            self._set_status(
                "Keine gecachten Samples in der Library — Ordner analysieren oder hinzufügen.",
                tone="neutral",
            )
            return
        self._rows = rows
        folder_count = len(
            {
                row.details.get("library_folder")
                for row in rows
                if row.details.get("library_folder")
            }
        )
        summary = {
            "files_found": len(rows),
            "analyzed_count": sum(1 for row in rows if row.status == "ok"),
            "error_count": sum(1 for row in rows if row.status == "error"),
            "cache_hits": len(rows),
            "cache_misses": 0,
        }
        self._populate_playlist(WorkbenchResult(summary=summary, rows=rows))
        self._set_status(
            f"{len(rows)} gecachte Samples aus {folder_count} Ordner(n) geladen.",
            tone="success",
        )

    def _load_catalog_samples(self) -> None:
        if not catalog_available():
            self._clear_playlist()
            self._global_library_mode = False
            self._catalog_library_mode = False
            self._catalog_total_count = 0
            self._catalog_load_limit = None
            self._set_status(
                "Keine catalog.db gefunden — Pfad prüfen (SAMPLE_BRAIN_DB_PATH).",
                tone="neutral",
            )
            return
        total = count_catalog_samples()
        limit = DEFAULT_CATALOG_LOAD_LIMIT
        rows = load_catalog_rows(limit=limit)
        self._catalog_library_mode = True
        self._global_library_mode = False
        self._catalog_total_count = total
        self._catalog_load_limit = limit if total > limit else None
        if not rows:
            self._clear_playlist()
            self._set_status("Catalog.db ohne Samples.", tone="neutral")
            return
        self._rows = rows
        summary = {
            "files_found": len(rows),
            "analyzed_count": sum(1 for row in rows if row.status == "ok"),
            "error_count": sum(1 for row in rows if row.status == "error"),
            "cache_hits": 0,
            "cache_misses": 0,
        }
        self._populate_playlist(WorkbenchResult(summary=summary, rows=rows))
        self._set_status(
            append_catalog_readonly_status_hint(
                format_catalog_load_status(
                    len(rows),
                    total,
                    limit=limit if self._catalog_load_limit is not None else None,
                )
            ),
            tone="success",
        )

    def _load_cached_folder(self, folder: Path, *, announce_if_empty: bool = False) -> None:
        self._global_library_mode = False
        self._catalog_library_mode = False
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
        self._reset_structured_filters()
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
        self._reset_structured_filters()
        self._refresh_playlist_view()

    def _refresh_playlist_view(self) -> None:
        preserve_path = self._preview_row_path
        text_query = effective_workbench_text_query(
            self._filter_var.get(),
            search_visible=self._view_settings.show_search,
        )
        row_filters = effective_workbench_row_filters(
            self._current_row_filters(),
            filters_visible=self._view_settings.show_filters,
        )
        visible = apply_workbench_filters(
            self._rows,
            text_query,
            row_filters,
        )
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
                    catalog_row_display_name(row),
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
        self._active_filter_var.set(
            format_workbench_active_filter_summary(
                text_query,
                row_filters,
            )
        )
        if self._rows and (
            self._catalog_library_mode
            or self._global_library_mode
            or not self._busy
        ):
            filters_active = self._playlist_filters_active()
            folder_count: int | None = None
            if self._global_library_mode:
                folder_count = len(
                    {
                        row.details.get("library_folder")
                        for row in self._rows
                        if row.details.get("library_folder")
                    }
                )
            mode: WorkbenchSearchMode = "folder"
            if self._catalog_library_mode:
                mode = "catalog"
            elif self._global_library_mode:
                mode = "global_library"
            status_line = format_workbench_search_status(
                WorkbenchSearchStatusContext(
                    mode=mode,
                    loaded_count=len(self._rows),
                    visible_count=len(visible),
                    filters_active=filters_active,
                    catalog_total=(
                        self._catalog_total_count if self._catalog_library_mode else None
                    ),
                    catalog_load_limit=(
                        self._catalog_load_limit if self._catalog_library_mode else None
                    ),
                    folder_count=folder_count,
                )
            )
            if self._catalog_library_mode and not filters_active:
                status_line = append_catalog_readonly_status_hint(status_line)
            tone = "neutral" if filters_active else "success"
            self._set_status(status_line, tone=tone)

    def _populate_playlist(self, result: WorkbenchResult) -> None:
        self._rows = result.rows
        self._update_structured_filter_options()
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

    def _play_loop_preview(self) -> None:
        if self._busy:
            return
        row = self._detail_row
        if row is None or not row.path:
            self._set_status("Kein Sample ausgewählt.", tone="neutral")
            return
        try:
            cue = load_workbench_sample_cue(row.path)
        except WorkbenchCueNotFoundError:
            self._set_status(
                "Sample nicht in der lokalen Bibliothek — zuerst analysieren.",
                tone="error",
            )
            return
        if cue.loop_start_ms is None or cue.loop_end_ms is None:
            self._set_status("Kein Loop gesetzt — Loop-Region zuerst setzen.", tone="error")
            return
        start_ms = int(cue.loop_start_ms)
        end_ms = int(cue.loop_end_ms)
        result = self._preview.play_region(row.path, start_ms=start_ms, end_ms=end_ms)
        name = Path(row.path).name
        if result.ok:
            self._set_status(
                f"Loop-Preview ({start_ms}–{end_ms} ms): {name}",
                tone="active",
            )
        else:
            self._set_status(result.message or "Loop-Preview fehlgeschlagen.", tone="error")

    def _play_loop_repeat(self) -> None:
        if self._busy:
            return
        row = self._detail_row
        if row is None or not row.path:
            self._set_status("Kein Sample ausgewählt.", tone="neutral")
            return
        try:
            cue = load_workbench_sample_cue(row.path)
        except WorkbenchCueNotFoundError:
            self._set_status(
                "Sample nicht in der lokalen Bibliothek — zuerst analysieren.",
                tone="error",
            )
            return
        if cue.loop_start_ms is None or cue.loop_end_ms is None:
            self._set_status("Kein Loop gesetzt — Loop-Region zuerst setzen.", tone="error")
            return
        start_ms = int(cue.loop_start_ms)
        end_ms = int(cue.loop_end_ms)
        result = self._preview.play_region_loop(row.path, start_ms=start_ms, end_ms=end_ms)
        name = Path(row.path).name
        if result.ok:
            self._set_status(
                f"Loop-Wiederholung aktiv ({start_ms}–{end_ms} ms): {name} — Stop zum Beenden",
                tone="active",
            )
        else:
            self._set_status(result.message or "Loop-Wiederholung fehlgeschlagen.", tone="error")

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

    def _block_catalog_edit(self, row: WorkbenchRow | None) -> bool:
        if row is not None and is_catalog_readonly_row(row):
            self._set_status(CATALOG_READONLY_EDIT_MESSAGE, tone="neutral")
            return True
        if self._catalog_library_mode and row is None:
            self._set_status(CATALOG_READONLY_EDIT_MESSAGE, tone="neutral")
            return True
        return False

    def _show_catalog_edit_blocked(self) -> None:
        self._set_status(CATALOG_READONLY_EDIT_MESSAGE, tone="neutral")
        messagebox.showinfo("Catalog read-only", CATALOG_READONLY_EDIT_MESSAGE)

    def _set_selected_cue_from_waveform_position(self, x: int) -> None:
        if self._busy:
            return
        row = self._detail_row
        if self._block_catalog_edit(row):
            return
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
                loop_source=existing.loop_source,
                attack_source=existing.attack_source,
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

    def _update_waveform_usage_hint(self) -> None:
        if self._loop_edit_mode_var.get():
            hint = WAVEFORM_LOOP_EDIT_HINT
        elif self._attack_edit_mode_var.get():
            hint = WAVEFORM_ATTACK_EDIT_HINT
        else:
            hint = WAVEFORM_USAGE_HINT
        self._waveform_usage_var.set(hint)

    def _on_loop_edit_mode_toggled(self) -> None:
        if self._loop_edit_mode_var.get():
            if self._catalog_library_mode or (
                self._detail_row is not None and is_catalog_readonly_row(self._detail_row)
            ):
                self._loop_edit_mode_var.set(False)
                self._show_catalog_edit_blocked()
                return
            self._attack_edit_mode_var.set(False)
            self._loop_edit_pending_start_ms = None
            self._update_waveform_usage_hint()
            self._set_status("Loop bearbeiten aktiv — 1. Klick: Loop-Start", tone="active")
            return
        self._loop_edit_pending_start_ms = None
        self._update_waveform_usage_hint()
        self._set_status("Loop bearbeiten aus", tone="neutral")

    def _on_attack_edit_mode_toggled(self) -> None:
        if self._attack_edit_mode_var.get():
            if self._catalog_library_mode or (
                self._detail_row is not None and is_catalog_readonly_row(self._detail_row)
            ):
                self._attack_edit_mode_var.set(False)
                self._show_catalog_edit_blocked()
                return
            self._loop_edit_mode_var.set(False)
            self._loop_edit_pending_start_ms = None
            self._update_waveform_usage_hint()
            self._set_status("Attack bearbeiten aktiv — Klick auf Waveform", tone="active")
            return
        self._update_waveform_usage_hint()
        self._set_status("Attack bearbeiten aus", tone="neutral")

    def _handle_loop_edit_waveform_click(self, x: int) -> None:
        if self._busy:
            return
        row = self._detail_row
        if self._block_catalog_edit(row):
            return
        if row is None or not row.path:
            self._set_status("Kein Sample ausgewählt.", tone="neutral")
            return
        duration_ms = read_audio_duration_ms(row.path)
        if duration_ms is None:
            self._set_status("Kann Loop-Position nicht bestimmen.", tone="error")
            return
        click_ms = self._cue_start_ms_from_waveform_x(x)
        if click_ms is None:
            self._set_status("Kann Loop-Position nicht bestimmen.", tone="error")
            return

        if self._loop_edit_pending_start_ms is None:
            self._loop_edit_pending_start_ms = click_ms
            self._set_status(
                f"Loop-Start gesetzt: {click_ms} ms — 2. Klick: Loop-Ende",
                tone="active",
            )
            return

        start_ms = min(self._loop_edit_pending_start_ms, click_ms)
        end_ms = max(self._loop_edit_pending_start_ms, click_ms)
        self._loop_edit_pending_start_ms = None

        try:
            existing = load_workbench_sample_cue(row.path)
            metadata = WorkbenchCueMetadata(
                cue_start_ms=existing.cue_start_ms,
                attack_ms=existing.attack_ms,
                loop_start_ms=start_ms,
                loop_end_ms=end_ms,
                cue_source=existing.cue_source or "manual",
                loop_source="manual",
                attack_source=existing.attack_source,
            )
            save_workbench_sample_cue(row.path, metadata, duration_ms=duration_ms)
        except WorkbenchCueNotFoundError:
            self._set_status(
                "Sample nicht in der lokalen Bibliothek — zuerst analysieren.",
                tone="error",
            )
            return
        except WorkbenchCueValidationError as exc:
            self._set_status(f"Loop konnte nicht gespeichert werden: {exc}", tone="error")
            return

        self._loop_edit_mode_var.set(False)
        self._update_waveform_usage_hint()
        self._draw_waveform(row)
        self._set_status(f"Loop gesetzt: {start_ms}–{end_ms} ms", tone="success")

    def _handle_attack_edit_waveform_click(self, x: int) -> None:
        if self._busy:
            return
        row = self._detail_row
        if self._block_catalog_edit(row):
            return
        if row is None or not row.path:
            self._set_status("Kein Sample ausgewählt.", tone="neutral")
            return
        duration_ms = read_audio_duration_ms(row.path)
        if duration_ms is None:
            self._set_status("Kann Attack-Position nicht bestimmen.", tone="error")
            return
        attack_ms = self._cue_start_ms_from_waveform_x(x)
        if attack_ms is None:
            self._set_status("Kann Attack-Position nicht bestimmen.", tone="error")
            return

        try:
            existing = load_workbench_sample_cue(row.path)
            metadata = WorkbenchCueMetadata(
                cue_start_ms=existing.cue_start_ms,
                attack_ms=attack_ms,
                loop_start_ms=existing.loop_start_ms,
                loop_end_ms=existing.loop_end_ms,
                cue_source=existing.cue_source or "manual",
                loop_source=existing.loop_source,
                attack_source="manual",
            )
            save_workbench_sample_cue(row.path, metadata, duration_ms=duration_ms)
        except WorkbenchCueNotFoundError:
            self._set_status(
                "Sample nicht in der lokalen Bibliothek — zuerst analysieren.",
                tone="error",
            )
            return
        except WorkbenchCueValidationError as exc:
            self._set_status(f"Attack konnte nicht gespeichert werden: {exc}", tone="error")
            return

        self._attack_edit_mode_var.set(False)
        self._clear_attack_suggestion()
        self._update_waveform_usage_hint()
        self._draw_waveform(row)
        self._set_status(f"Attack gesetzt: {attack_ms} ms", tone="success")

    def _clear_attack_metadata(self) -> None:
        if self._busy:
            return
        row = self._detail_row
        if self._block_catalog_edit(row):
            return
        if row is None or not row.path:
            self._set_status("Kein Sample ausgewählt.", tone="neutral")
            return
        duration_ms = read_audio_duration_ms(row.path)
        try:
            existing = load_workbench_sample_cue(row.path)
            metadata = WorkbenchCueMetadata(
                cue_start_ms=existing.cue_start_ms,
                attack_ms=None,
                loop_start_ms=existing.loop_start_ms,
                loop_end_ms=existing.loop_end_ms,
                cue_source=existing.cue_source or "manual",
                loop_source=existing.loop_source,
                attack_source="manual",
            )
            save_workbench_sample_cue(row.path, metadata, duration_ms=duration_ms)
        except WorkbenchCueNotFoundError:
            self._set_status(
                "Sample nicht in der lokalen Bibliothek — zuerst analysieren.",
                tone="error",
            )
            return
        except WorkbenchCueValidationError as exc:
            self._set_status(f"Attack konnte nicht gelöscht werden: {exc}", tone="error")
            return

        self._attack_edit_mode_var.set(False)
        self._update_waveform_usage_hint()
        self._draw_waveform(row)
        self._clear_attack_suggestion()
        self._set_status("Attack gelöscht", tone="success")

    def _set_attack_suggestion_pending(self, suggestion: AttackSuggestion | None) -> None:
        self._pending_attack_suggestion = suggestion
        btn = getattr(self, "_attack_suggest_apply_btn", None)
        if btn is None:
            return
        if suggestion is None:
            btn.state(["disabled"])
        else:
            btn.state(["!disabled"])

    def _clear_attack_suggestion(self) -> None:
        self._set_attack_suggestion_pending(None)

    def _suggest_attack_metadata(self) -> None:
        if self._busy:
            return
        row = self._detail_row
        if self._block_catalog_edit(row):
            return
        if row is None or not row.path:
            self._set_status("Kein Sample ausgewählt.", tone="neutral")
            return
        suggestion = suggest_attack_ms(row.path)
        if suggestion is None:
            self._clear_attack_suggestion()
            self._set_status("Attack-Vorschlag nicht möglich.", tone="error")
            return
        self._set_attack_suggestion_pending(suggestion)
        self._set_status(
            (
                f"Attack-Vorschlag: {suggestion.attack_ms} ms "
                f"({suggestion.confidence}) — {suggestion.reason} "
                "· Übernehmen oder ignorieren"
            ),
            tone="active",
        )

    def _apply_attack_suggestion(self) -> None:
        if self._busy:
            return
        suggestion = self._pending_attack_suggestion
        if suggestion is None:
            self._set_status("Kein Attack-Vorschlag vorhanden.", tone="neutral")
            return
        row = self._detail_row
        if self._block_catalog_edit(row):
            return
        if row is None or not row.path:
            self._set_status("Kein Sample ausgewählt.", tone="neutral")
            return
        duration_ms = read_audio_duration_ms(row.path)
        try:
            existing = load_workbench_sample_cue(row.path)
            metadata = WorkbenchCueMetadata(
                cue_start_ms=existing.cue_start_ms,
                attack_ms=suggestion.attack_ms,
                loop_start_ms=existing.loop_start_ms,
                loop_end_ms=existing.loop_end_ms,
                cue_source=existing.cue_source or "manual",
                loop_source=existing.loop_source,
                attack_source="manual",
            )
            save_workbench_sample_cue(row.path, metadata, duration_ms=duration_ms)
        except WorkbenchCueNotFoundError:
            self._set_status(
                "Sample nicht in der lokalen Bibliothek — zuerst analysieren.",
                tone="error",
            )
            return
        except WorkbenchCueValidationError as exc:
            self._set_status(f"Attack konnte nicht gespeichert werden: {exc}", tone="error")
            return

        self._attack_edit_mode_var.set(False)
        self._clear_attack_suggestion()
        self._update_waveform_usage_hint()
        self._draw_waveform(row)
        self._set_status(
            f"Attack übernommen: {suggestion.attack_ms} ms ({suggestion.confidence})",
            tone="success",
        )

    def _clear_loop_metadata(self) -> None:
        if self._busy:
            return
        row = self._detail_row
        if self._block_catalog_edit(row):
            return
        if row is None or not row.path:
            self._set_status("Kein Sample ausgewählt.", tone="neutral")
            return
        duration_ms = read_audio_duration_ms(row.path)
        try:
            existing = load_workbench_sample_cue(row.path)
            metadata = WorkbenchCueMetadata(
                cue_start_ms=existing.cue_start_ms,
                attack_ms=existing.attack_ms,
                loop_start_ms=None,
                loop_end_ms=None,
                cue_source=existing.cue_source or "manual",
                loop_source="manual",
                attack_source=existing.attack_source,
            )
            save_workbench_sample_cue(row.path, metadata, duration_ms=duration_ms)
        except WorkbenchCueNotFoundError:
            self._set_status(
                "Sample nicht in der lokalen Bibliothek — zuerst analysieren.",
                tone="error",
            )
            return
        except WorkbenchCueValidationError as exc:
            self._set_status(f"Loop konnte nicht gelöscht werden: {exc}", tone="error")
            return

        self._loop_edit_pending_start_ms = None
        self._loop_edit_mode_var.set(False)
        self._update_waveform_usage_hint()
        self._draw_waveform(row)
        self._set_status("Loop gelöscht", tone="success")

    def _on_waveform_click(self, event: tk.Event) -> None:
        if event.state & 0x0001:
            self._set_selected_cue_from_waveform_position(int(event.x))
            return
        if self._loop_edit_mode_var.get():
            self._handle_loop_edit_waveform_click(int(event.x))
            return
        if self._attack_edit_mode_var.get():
            self._handle_attack_edit_waveform_click(int(event.x))
            return
        self._play_selected_from_waveform()

    def _on_waveform_right_click(self, event: tk.Event) -> None:
        self._play_selected_from_waveform_position(int(event.x))

    def _update_metadata_provenance_display(
        self,
        row: WorkbenchRow | None,
        *,
        cue: WorkbenchCueMetadata | None = None,
    ) -> None:
        if row is None or not row.path:
            self._provenance_var.set("")
            return
        if cue is None:
            try:
                cue = load_workbench_sample_cue(row.path)
            except Exception:
                self._provenance_var.set("")
                return
        self._provenance_var.set(format_metadata_provenance_hint(cue))

    def _draw_waveform(self, row: WorkbenchRow | None) -> None:
        canvas = self._waveform_canvas
        canvas.delete("all")
        width = max(int(canvas.winfo_width()), 1)
        height = max(int(canvas.winfo_height()), 1)
        if row is None or not row.path:
            canvas.create_text(width // 2, height // 2, text="—", fill=TEXT_MUTED)
            self._update_metadata_provenance_display(None)
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
        self._update_metadata_provenance_display(row, cue=cue)
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
            attack_x = attack_marker_x(cue.attack_ms, duration_ms, width)
            if attack_x is not None:
                canvas.create_line(
                    attack_x,
                    2,
                    attack_x,
                    height - 2,
                    fill=ATTACK_MARKER,
                    width=2,
                    dash=(4, 2),
                )

    def _set_detail(self, row: WorkbenchRow | None) -> None:
        self._detail_row = row
        self._clear_attack_suggestion()
        self._detail_text.configure(state=tk.NORMAL)
        self._detail_text.delete("1.0", tk.END)
        self._update_preview_state(row)
        if row is None:
            self._detail_text.insert(tk.END, "Kein Sample ausgewählt.")
        else:
            if is_catalog_readonly_row(row):
                lines = [
                    "Quelle:   catalog.db (read-only)",
                    "Bearbeitung: Cue/Loop/Attack nur im Workbench-Cache speicherbar",
                    "",
                ]
            else:
                lines = []
            lines.extend([
                f"Name:     {row.display_name}",
                "Pfad:",
            ])
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
