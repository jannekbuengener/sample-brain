from __future__ import annotations

import importlib
import csv
import subprocess
import sys
from pathlib import Path

import pytest

from src.workbench_controller import (
    add_workbench_library_folder,
    add_workbench_row_to_playlist,
    analyze_folder_for_workbench,
    apply_workbench_filters,
    apply_workbench_structured_filters,
    error_message_for_code,
    export_workbench_rows_to_csv,
    export_workbench_rows_to_fl_tags,
    filter_workbench_rows,
    format_path_display_lines,
    format_playlist_add_status,
    format_workbench_detail_field_lines,
    format_workbench_active_filter_summary,
    format_workbench_search_status,
    get_preview_start_ms,
    get_workbench_library_folders,
    list_workbench_playlists,
    is_catalog_readonly_row,
    load_cached_folder_rows,
    load_workbench_analysis_limit,
    load_workbench_last_folder,
    load_workbench_sample_cue,
    load_workbench_view_settings,
    remove_workbench_library_folder,
    parse_workbench_bpm_bound,
    row_source_kind,
    normalize_workbench_analysis_limit_text,
    save_workbench_analysis_limit,
    save_workbench_last_folder,
    save_workbench_sample_cue,
    save_workbench_view_settings,
    sort_workbench_rows,
    validate_workbench_folder,
    workbench_filter_options,
    workbench_view_settings_file,
    effective_workbench_row_filters,
    effective_workbench_text_query,
    format_workbench_view_restore_status,
    format_workbench_view_section_hidden_status,
    DEFAULT_WORKBENCH_VIEW_SETTINGS,
    DEFAULT_WORKBENCH_ANALYSIS_LIMIT_TEXT,
    VIEW_SECTION_FILTERS,
    VIEW_SECTION_SEARCH,
    VIEW_SECTION_WAVEFORM_TOOLS,
    WorkbenchViewSettings,
    workbench_analysis_limit_file,
    workbench_last_folder_file,
    workbench_rows_for_fl_export,
    WorkbenchRow,
    WorkbenchRowFilters,
    WorkbenchSearchStatusContext,
    FILTER_ALL_LABEL,
)
from src.workbench_library import WorkbenchCueMetadata, WorkbenchCueNotFoundError
from tests.audio_fixtures import write_kick_transient_wav, write_sine_wav


@pytest.fixture(autouse=True)
def _isolated_workbench_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_dir = tmp_path / "workbench_state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))


PLAYLIST_KEYS = {
    "display_name",
    "relative_path",
    "bpm",
    "key",
    "key_conf",
    "loudness",
    "brightness",
    "sample_class",
    "pred_type",
    "status",
    "error",
    "error_code",
}


@pytest.fixture
def sample_folder(tmp_path: Path) -> Path:
    samples = tmp_path / "samples"
    write_sine_wav(samples / "tone_a.wav", duration_sec=0.5, frequency_hz=440.0)
    write_kick_transient_wav(samples / "kick_b.wav", bpm=120.0, duration_sec=2.0)
    (samples / "notes.txt").write_text("not audio", encoding="utf-8")
    return samples


def test_format_path_display_lines_keeps_short_path_on_one_line():
    path = "kits/drums/kick.wav"
    assert format_path_display_lines(path) == [path]


def test_format_path_display_lines_collapses_long_middle():
    path = "root/alpha/beta/gamma/delta/epsilon/file.wav"
    lines = format_path_display_lines(path, max_width=34)
    assert lines == ["root/alpha/…/epsilon/file.wav"]


def test_format_path_display_lines_uses_segment_layout_when_collapsed_too_long():
    path = "vault/" + "/".join(f"segment-{index}" for index in range(6)) + "/sample.wav"
    lines = format_path_display_lines(path, max_width=24)
    assert len(lines) > 1
    assert lines[0].startswith("  vault")
    assert any(line.startswith("› ") for line in lines)
    assert lines[-1].endswith("sample.wav")


def test_format_path_display_lines_wraps_long_segment_name():
    long_name = "x" * 40 + ".wav"
    path = f"packs/{long_name}"
    lines = format_path_display_lines(path, max_width=20)
    assert len(lines) >= 3
    assert lines[0] == "  packs"
    assert any(long_name[:12] in line for line in lines)


def test_format_path_display_lines_empty_path():
    assert format_path_display_lines("") == ["—"]
    assert format_path_display_lines("   ") == ["—"]


def test_format_workbench_detail_field_lines_formats_long_library_folder():
    path = "vault/" + "/".join(f"segment-{index}-extra" for index in range(8)) + "/pack"
    lines = format_workbench_detail_field_lines("library_folder", path)
    rendered = "\n".join(lines)
    assert rendered.startswith("library_folder")
    assert "…" in rendered
    assert rendered.endswith("pack") or rendered.splitlines()[-1].endswith("pack")
    assert path not in rendered


def test_format_workbench_detail_field_lines_keeps_short_library_folder_inline():
    path = "kits/drums"
    lines = format_workbench_detail_field_lines("library_folder", path)
    assert lines == [f"library_folder   {path}"]


def test_workbench_set_detail_formats_long_paths_in_panel():
    import tkinter as tk

    from src.workbench import WorkbenchApp
    from src.workbench_controller import WorkbenchRow

    long_abs = "vault/" + "/".join(f"segment-{index}-extra" for index in range(8)) + "/sample.wav"
    long_lib = "vault/" + "/".join(f"lib-{index}-extra" for index in range(8)) + "/pack"
    row = WorkbenchRow(
        display_name="demo",
        relative_path="pack/demo.wav",
        path=long_abs,
        bpm=120.0,
        key="C",
        key_conf=0.8,
        loudness=-10.0,
        brightness=50.0,
        sample_class="kick",
        pred_type="kick",
        status="ok",
        details={"library_folder": long_lib, "duration_sec": 1.5},
    )

    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp.__new__(WorkbenchApp)
        app._detail_text = tk.Text(root, wrap="word")
        app._detail_row = None
        app._clear_attack_suggestion = lambda: None  # type: ignore[method-assign]
        app._update_preview_state = lambda _row: None  # type: ignore[method-assign]
        app._draw_waveform = lambda _row: None  # type: ignore[method-assign]

        WorkbenchApp._set_detail(app, row)
        text = app._detail_text.get("1.0", tk.END)
        assert "Pfad:" in text
        assert "library_folder" in text
        assert "…" in text or "› " in text
        assert long_abs not in text
        assert long_lib not in text
    finally:
        root.destroy()


def test_controller_finds_audio_files(sample_folder: Path):
    result = analyze_folder_for_workbench(sample_folder)

    assert result.summary["files_found"] == 2
    names = {row.display_name for row in result.rows}
    assert names == {"tone a", "kick b"}


def test_controller_summary_counts(sample_folder: Path):
    result = analyze_folder_for_workbench(sample_folder, limit=1)

    assert result.summary["files_found"] == 1
    assert result.summary["analyzed_count"] + result.summary["error_count"] == 1
    assert len(result.rows) == 1


def test_controller_collects_errors(tmp_path: Path):
    samples = tmp_path / "broken"
    samples.mkdir()
    bad = samples / "broken.wav"
    bad.write_bytes(b"not-a-valid-wav")

    result = analyze_folder_for_workbench(samples)

    assert result.summary["files_found"] == 1
    assert result.summary["error_count"] == 1
    row = result.rows[0]
    assert row.status == "error"
    assert row.error_code is not None
    assert row.error == error_message_for_code(row.error_code)
    assert row.error != "Could not extract features"
    assert "error_detail" in row.details


def test_sort_workbench_rows_by_name(sample_folder: Path):
    result = analyze_folder_for_workbench(sample_folder)

    ascending = sort_workbench_rows(result.rows, "name")
    assert [row.display_name for row in ascending] == ["kick b", "tone a"]

    descending = sort_workbench_rows(result.rows, "name", reverse=True)
    assert [row.display_name for row in descending] == ["tone a", "kick b"]


def test_sort_workbench_rows_by_bpm(sample_folder: Path):
    result = analyze_folder_for_workbench(sample_folder)

    by_bpm = sort_workbench_rows(result.rows, "bpm")
    bpms = [row.bpm for row in by_bpm if row.bpm is not None]
    assert bpms == sorted(bpms)


def test_sort_workbench_rows_rejects_unknown_column(sample_folder: Path):
    result = analyze_folder_for_workbench(sample_folder)

    with pytest.raises(ValueError, match="Unsupported sort column"):
        sort_workbench_rows(result.rows, "unknown")


def test_filter_workbench_rows_matches_name_and_type(sample_folder: Path):
    result = analyze_folder_for_workbench(sample_folder)

    by_name = filter_workbench_rows(result.rows, "tone")
    assert len(by_name) == 1
    assert by_name[0].display_name == "tone a"

    by_type = filter_workbench_rows(result.rows, "kick")
    assert len(by_type) == 1
    assert by_type[0].display_name == "kick b"


def test_filter_workbench_rows_empty_query_returns_all(sample_folder: Path):
    result = analyze_folder_for_workbench(sample_folder)

    assert filter_workbench_rows(result.rows, "") == result.rows
    assert filter_workbench_rows(result.rows, "   ") == result.rows


def test_filter_workbench_rows_no_match(sample_folder: Path):
    result = analyze_folder_for_workbench(sample_folder)

    assert filter_workbench_rows(result.rows, "zzz-not-found") == []


def test_filter_workbench_rows_matches_library_folder() -> None:
    rows = [
        WorkbenchRow(
            display_name="kick",
            relative_path="pack_a/kick.wav",
            path="/data/pack_a/kick.wav",
            bpm=120.0,
            key="C",
            key_conf=0.8,
            loudness=-10.0,
            brightness=50.0,
            sample_class="kick",
            pred_type="kick",
            status="ok",
            details={"library_folder": "/music/pack_a"},
        ),
        WorkbenchRow(
            display_name="snare",
            relative_path="pack_b/snare.wav",
            path="/data/pack_b/snare.wav",
            bpm=120.0,
            key="C",
            key_conf=0.8,
            loudness=-10.0,
            brightness=50.0,
            sample_class="snare",
            pred_type="snare",
            status="ok",
            details={"library_folder": "/music/other_pack"},
        ),
    ]

    by_folder = filter_workbench_rows(rows, "pack_a")
    assert len(by_folder) == 1
    assert by_folder[0].display_name == "kick"

    by_other = filter_workbench_rows(rows, "other")
    assert len(by_other) == 1
    assert by_other[0].display_name == "snare"


def _sample_rows_for_filters() -> list[WorkbenchRow]:
    return [
        WorkbenchRow(
            display_name="kick cache",
            relative_path="kick.wav",
            path="/cache/kick.wav",
            bpm=120.0,
            key="Am",
            key_conf=0.8,
            loudness=-10.0,
            brightness=50.0,
            sample_class="kick",
            pred_type="kick",
            status="ok",
            details={"library_folder": "/music/pack"},
        ),
        WorkbenchRow(
            display_name="pad cache",
            relative_path="pad.wav",
            path="/cache/pad.wav",
            bpm=90.0,
            key="C",
            key_conf=0.7,
            loudness=-12.0,
            brightness=40.0,
            sample_class="pad",
            pred_type="pad",
            status="ok",
            details={},
        ),
        WorkbenchRow(
            display_name="catalog snare",
            relative_path="snare.wav",
            path="/catalog/snare.wav",
            bpm=128.0,
            key="Am",
            key_conf=0.9,
            loudness=-8.0,
            brightness=55.0,
            sample_class="snare",
            pred_type="snare",
            status="pending",
            details={"catalog_readonly": True, "source": "catalog"},
        ),
    ]


def test_row_source_kind_distinguishes_cache_and_catalog():
    rows = _sample_rows_for_filters()
    assert row_source_kind(rows[0]) == "cache"
    assert row_source_kind(rows[2]) == "catalog"


def test_apply_workbench_structured_filters_by_source():
    rows = _sample_rows_for_filters()
    cache_only = apply_workbench_structured_filters(
        rows,
        WorkbenchRowFilters(source="cache"),
    )
    assert [row.display_name for row in cache_only] == ["kick cache", "pad cache"]

    catalog_only = apply_workbench_structured_filters(
        rows,
        WorkbenchRowFilters(source="catalog"),
    )
    assert len(catalog_only) == 1
    assert catalog_only[0].display_name == "catalog snare"


def test_apply_workbench_structured_filters_by_type_key_status():
    rows = _sample_rows_for_filters()

    by_type = apply_workbench_structured_filters(
        rows,
        WorkbenchRowFilters(pred_type="pad"),
    )
    assert len(by_type) == 1
    assert by_type[0].display_name == "pad cache"

    by_key = apply_workbench_structured_filters(
        rows,
        WorkbenchRowFilters(key="Am"),
    )
    assert {row.display_name for row in by_key} == {"kick cache", "catalog snare"}

    by_status = apply_workbench_structured_filters(
        rows,
        WorkbenchRowFilters(status="pending"),
    )
    assert len(by_status) == 1
    assert by_status[0].display_name == "catalog snare"


def test_apply_workbench_filters_combines_text_and_structured():
    rows = _sample_rows_for_filters()
    combined = apply_workbench_filters(
        rows,
        "kick",
        WorkbenchRowFilters(key="Am"),
    )
    assert len(combined) == 1
    assert combined[0].display_name == "kick cache"


def test_apply_workbench_structured_filters_reset_shows_all():
    rows = _sample_rows_for_filters()
    assert apply_workbench_structured_filters(rows, None) == rows
    assert apply_workbench_structured_filters(
        rows,
        WorkbenchRowFilters(source="all", pred_type=FILTER_ALL_LABEL),
    ) == rows


def test_workbench_filter_options_collects_distinct_values():
    rows = _sample_rows_for_filters()
    options = workbench_filter_options(rows)
    assert options["types"] == ("kick", "pad", "snare")
    assert options["keys"] == ("Am", "C")


def test_catalog_readonly_rows_remain_unchanged_by_structured_filter():
    rows = _sample_rows_for_filters()
    catalog_rows = apply_workbench_structured_filters(
        rows,
        WorkbenchRowFilters(source="catalog"),
    )
    assert all(is_catalog_readonly_row(row) for row in catalog_rows)


def test_parse_workbench_bpm_bound_accepts_valid_and_rejects_invalid():
    assert parse_workbench_bpm_bound("") is None
    assert parse_workbench_bpm_bound("  ") is None
    assert parse_workbench_bpm_bound("abc") is None
    assert parse_workbench_bpm_bound("-1") is None
    assert parse_workbench_bpm_bound("120") == 120.0
    assert parse_workbench_bpm_bound("90,5") == 90.5


def test_apply_workbench_structured_filters_by_bpm_range():
    rows = _sample_rows_for_filters()
    in_range = apply_workbench_structured_filters(
        rows,
        WorkbenchRowFilters(min_bpm=100.0, max_bpm=125.0),
    )
    assert [row.display_name for row in in_range] == ["kick cache"]

    above = apply_workbench_structured_filters(rows, WorkbenchRowFilters(min_bpm=125.0))
    assert len(above) == 1
    assert above[0].display_name == "catalog snare"


def test_apply_workbench_structured_filters_excludes_missing_bpm_when_bounds_active():
    rows = _sample_rows_for_filters() + [
        WorkbenchRow(
            display_name="no bpm",
            relative_path="x.wav",
            path="/cache/x.wav",
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
    ]
    filtered = apply_workbench_structured_filters(rows, WorkbenchRowFilters(min_bpm=80.0))
    assert all(row.bpm is not None for row in filtered)
    assert "no bpm" not in {row.display_name for row in filtered}


def test_apply_workbench_filters_bpm_with_text_and_key():
    rows = _sample_rows_for_filters()
    combined = apply_workbench_filters(
        rows,
        "kick",
        WorkbenchRowFilters(min_bpm=110.0, max_bpm=130.0, key="Am"),
    )
    assert len(combined) == 1
    assert combined[0].display_name == "kick cache"


def test_apply_workbench_structured_filters_bpm_sort_stability_via_apply_order():
    rows = _sample_rows_for_filters()
    filtered = apply_workbench_structured_filters(rows, WorkbenchRowFilters(min_bpm=80.0))
    sorted_rows = sort_workbench_rows(filtered, "bpm")
    bpms = [row.bpm for row in sorted_rows if row.bpm is not None]
    assert bpms == sorted(bpms)


def test_format_workbench_search_status_folder_with_filters():
    status = format_workbench_search_status(
        WorkbenchSearchStatusContext(
            mode="folder",
            loaded_count=80,
            visible_count=12,
            filters_active=True,
        )
    )
    assert status == "Ordner: 12 von 80 Treffer"


def test_format_workbench_search_status_folder_without_filters():
    status = format_workbench_search_status(
        WorkbenchSearchStatusContext(
            mode="folder",
            loaded_count=80,
            visible_count=80,
            filters_active=False,
        )
    )
    assert status == "Ordner: 80 Samples"


def test_format_workbench_search_status_global_library_with_filters():
    status = format_workbench_search_status(
        WorkbenchSearchStatusContext(
            mode="global_library",
            loaded_count=240,
            visible_count=23,
            filters_active=True,
        )
    )
    assert status == "Alle Library-Samples: 23 von 240 Treffer"


def test_format_workbench_search_status_global_library_without_filters():
    status = format_workbench_search_status(
        WorkbenchSearchStatusContext(
            mode="global_library",
            loaded_count=240,
            visible_count=240,
            filters_active=False,
            folder_count=5,
        )
    )
    assert status == "Alle Library-Samples: 240 Samples aus 5 Ordner(n)"


def test_format_workbench_search_status_catalog_with_limit_and_filters():
    status = format_workbench_search_status(
        WorkbenchSearchStatusContext(
            mode="catalog",
            loaded_count=500,
            visible_count=18,
            filters_active=True,
            catalog_total=12000,
            catalog_load_limit=5000,
        )
    )
    assert status == (
        "Catalog-Samples: 500 von 12000 geladen, 18 Treffer (read-only, Limit aktiv)"
    )


def test_format_workbench_search_status_catalog_without_filters():
    status = format_workbench_search_status(
        WorkbenchSearchStatusContext(
            mode="catalog",
            loaded_count=500,
            visible_count=500,
            filters_active=False,
            catalog_total=12000,
            catalog_load_limit=5000,
        )
    )
    assert "500 von 12000" in status
    assert "Limit aktiv" in status
    assert "read-only" in status


def test_format_workbench_search_status_catalog_no_hits_with_filters():
    status = format_workbench_search_status(
        WorkbenchSearchStatusContext(
            mode="catalog",
            loaded_count=500,
            visible_count=0,
            filters_active=True,
            catalog_total=12000,
            catalog_load_limit=5000,
        )
    )
    assert status == (
        "Catalog-Samples: 500 von 12000 geladen, 0 Treffer (read-only, Limit aktiv)"
    )


def test_format_workbench_active_filter_summary_empty():
    assert format_workbench_active_filter_summary("", None) == ""
    assert (
        format_workbench_active_filter_summary("  ", WorkbenchRowFilters()) == ""
    )


def test_format_workbench_active_filter_summary_text_only():
    summary = format_workbench_active_filter_summary("kick", None)
    assert summary == 'Aktive Filter: Text="kick"'


def test_format_workbench_active_filter_summary_source():
    summary = format_workbench_active_filter_summary(
        "",
        WorkbenchRowFilters(source="catalog"),
    )
    assert summary == "Aktive Filter: Quelle=Catalog"


def test_format_workbench_active_filter_summary_key_and_bpm_range():
    summary = format_workbench_active_filter_summary(
        "",
        WorkbenchRowFilters(key="Am", min_bpm=120.0, max_bpm=130.0),
    )
    assert summary == "Aktive Filter: Key=Am · BPM 120–130"


def test_format_workbench_active_filter_summary_combined():
    summary = format_workbench_active_filter_summary(
        "kick",
        WorkbenchRowFilters(source="cache", status="ok", pred_type="kick"),
    )
    assert "Text=\"kick\"" in summary
    assert "Quelle=Cache" in summary
    assert "Type=kick" in summary
    assert "Status=ok" in summary


def test_format_workbench_active_filter_summary_ignores_invalid_bpm_fields():
    summary = format_workbench_active_filter_summary(
        "",
        WorkbenchRowFilters(
            pred_type=FILTER_ALL_LABEL,
            key=FILTER_ALL_LABEL,
            status=FILTER_ALL_LABEL,
        ),
    )
    assert summary == ""


def test_workbench_clear_filter_resets_all_filter_fields():
    import tkinter as tk

    from src.workbench import WorkbenchApp

    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp.__new__(WorkbenchApp)
        app._filter_var = tk.StringVar(master=root, value="kick")
        app._source_filter_var = tk.StringVar(master=root, value="cache")
        app._type_filter_var = tk.StringVar(master=root, value="kick")
        app._key_filter_var = tk.StringVar(master=root, value="Am")
        app._status_filter_var = tk.StringVar(master=root, value="ok")
        app._bpm_min_var = tk.StringVar(master=root, value="120")
        app._bpm_max_var = tk.StringVar(master=root, value="130")
        refreshed = {"count": 0}

        def _refresh() -> None:
            refreshed["count"] += 1

        app._refresh_playlist_view = _refresh  # type: ignore[method-assign]
        WorkbenchApp._clear_filter(app)
        root.update_idletasks()
        assert app._filter_var.get() == ""
        assert app._source_filter_var.get() == FILTER_ALL_LABEL
        assert app._type_filter_var.get() == FILTER_ALL_LABEL
        assert app._key_filter_var.get() == FILTER_ALL_LABEL
        assert app._status_filter_var.get() == FILTER_ALL_LABEL
        assert app._bpm_min_var.get() == ""
        assert app._bpm_max_var.get() == ""
        assert refreshed["count"] == 1
    finally:
        root.destroy()


def test_workbench_layout_has_filter_reset_button():
    import inspect

    from src.workbench import WorkbenchApp

    source = inspect.getsource(WorkbenchApp._build_layout)
    assert "Filter zurücksetzen" in source
    assert "command=self._clear_filter" in source


def test_cancel_before_scan_returns_empty(sample_folder: Path):
    result = analyze_folder_for_workbench(
        sample_folder,
        should_cancel=lambda: True,
    )

    assert result.summary["files_found"] == 0
    assert result.summary["analyzed_count"] == 0
    assert result.summary.get("cancelled") == 1
    assert result.rows == []


def test_cancel_mid_analysis_returns_partial_results(sample_folder: Path):
    checks = {"n": 0}

    def cancel_after_first_file() -> bool:
        checks["n"] += 1
        return checks["n"] > 2

    result = analyze_folder_for_workbench(
        sample_folder,
        should_cancel=cancel_after_first_file,
    )

    assert result.summary["files_found"] == 2
    assert result.summary.get("cancelled") == 1
    assert len(result.rows) == 1


def test_cancel_emits_cancelled_phase(sample_folder: Path):
    events: list[tuple[int, int, str, str]] = []

    def cancel_immediately() -> bool:
        return len(events) > 0

    analyze_folder_for_workbench(
        sample_folder,
        progress_callback=lambda c, t, n, p: events.append((c, t, n, p)),
        should_cancel=cancel_immediately,
    )

    assert any(e[3] == "cancelled" for e in events)


def test_progress_callback_reports_current_and_total(sample_folder: Path):
    events: list[tuple[int, int, str, str]] = []

    def progress(current: int, total: int, name: str, phase: str) -> None:
        events.append((current, total, name, phase))

    result = analyze_folder_for_workbench(sample_folder, progress_callback=progress)

    assert result.summary["files_found"] == 2
    analyzing = [e for e in events if e[3] == "analyzing"]
    assert len(analyzing) == 2
    assert analyzing[0][0] == 1 and analyzing[0][1] == 2
    assert analyzing[1][0] == 2 and analyzing[1][1] == 2
    assert events[0][3] == "scanning"


def test_empty_folder_progress_and_summary(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    events: list[tuple[int, int, str, str]] = []

    result = analyze_folder_for_workbench(
        empty,
        progress_callback=lambda c, t, n, p: events.append((c, t, n, p)),
    )

    assert result.summary == {
        "files_found": 0,
        "analyzed_count": 0,
        "error_count": 0,
        "cache_hits": 0,
        "cache_misses": 0,
    }
    assert events and events[0][3] == "scanning"


def test_playlist_rows_contain_expected_fields(sample_folder: Path):
    result = analyze_folder_for_workbench(sample_folder)

    assert result.rows
    for row in result.rows:
        fields = row.playlist_fields()
        assert PLAYLIST_KEYS <= set(fields.keys())
        assert row.details
        assert "path" in row.details


def test_analyze_folder_uses_cache_on_second_run(sample_folder: Path):
    first = analyze_folder_for_workbench(sample_folder)
    assert first.summary["cache_misses"] == 2
    assert first.summary["cache_hits"] == 0

    second = analyze_folder_for_workbench(sample_folder)
    assert second.summary["cache_hits"] == 2
    assert second.summary["cache_misses"] == 0
    assert second.summary["analyzed_count"] == 2


def test_analyze_folder_cache_disabled(sample_folder: Path):
    first = analyze_folder_for_workbench(sample_folder, use_cache=False)
    second = analyze_folder_for_workbench(sample_folder, use_cache=False)

    assert first.summary["cache_hits"] == 0
    assert first.summary["cache_misses"] == 0
    assert second.summary["cache_hits"] == 0
    assert second.summary["cache_misses"] == 0


def test_invalid_folder_raises(tmp_path: Path):
    missing = tmp_path / "does_not_exist"
    with pytest.raises(ValueError, match="Not a directory"):
        analyze_folder_for_workbench(missing)


def test_validate_workbench_folder_rejects_empty():
    result = validate_workbench_folder("   ")

    assert not result.ok
    assert result.error_code == "empty"
    assert result.error_message == "Kein Ordner ausgewählt"
    assert result.normalized_path is None


def test_validate_workbench_folder_rejects_missing(tmp_path: Path):
    missing = tmp_path / "missing_dir"
    result = validate_workbench_folder(str(missing))

    assert not result.ok
    assert result.error_code == "not_found"
    assert result.error_message == "Ordner existiert nicht"


def test_validate_workbench_folder_rejects_file(tmp_path: Path):
    file_path = tmp_path / "not_a_folder.txt"
    file_path.write_text("x", encoding="utf-8")

    result = validate_workbench_folder(str(file_path))

    assert not result.ok
    assert result.error_code == "not_a_directory"
    assert result.error_message == "Pfad ist keine Ordner"


def test_validate_workbench_folder_accepts_valid_directory(tmp_path: Path):
    folder = tmp_path / "samples"
    folder.mkdir()

    result = validate_workbench_folder(str(folder))

    assert result.ok
    assert result.error_code is None
    assert result.normalized_path == folder.resolve()


def test_save_and_load_workbench_last_folder(tmp_path: Path):
    folder = tmp_path / "samples"
    folder.mkdir()
    state_dir = tmp_path / "state"

    assert save_workbench_last_folder(folder, state_dir=state_dir)
    assert load_workbench_last_folder(state_dir=state_dir) == str(folder.resolve())
    assert workbench_last_folder_file(state_dir=state_dir).is_file()


def test_load_workbench_last_folder_returns_none_for_missing_state(tmp_path: Path):
    assert load_workbench_last_folder(state_dir=tmp_path / "missing") is None


def test_load_workbench_last_folder_ignores_invalid_saved_path(tmp_path: Path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    workbench_last_folder_file(state_dir=state_dir).write_text(
        str(tmp_path / "gone"),
        encoding="utf-8",
    )

    assert load_workbench_last_folder(state_dir=state_dir) is None


def test_save_workbench_last_folder_rejects_invalid_path(tmp_path: Path):
    state_dir = tmp_path / "state"
    assert not save_workbench_last_folder("", state_dir=state_dir)
    assert not workbench_last_folder_file(state_dir=state_dir).exists()


def test_export_workbench_rows_to_csv_writes_playlist_fields(sample_folder: Path, tmp_path: Path):
    result = analyze_folder_for_workbench(sample_folder)
    destination = tmp_path / "playlist.csv"

    count = export_workbench_rows_to_csv(result.rows, destination)

    assert count == len(result.rows)
    assert destination.is_file()
    with destination.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(result.rows)
    assert rows[0]["display_name"]
    assert rows[0]["status"]


def test_export_workbench_rows_to_csv_empty_list(tmp_path: Path):
    destination = tmp_path / "empty.csv"

    count = export_workbench_rows_to_csv([], destination)

    assert count == 0
    with destination.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == []


def _ok_workbench_row(tmp_path: Path, name: str = "kick.wav") -> WorkbenchRow:
    sample = tmp_path / name
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_bytes(b"data")
    return WorkbenchRow(
        display_name="kick",
        relative_path=name,
        path=str(sample),
        bpm=128.0,
        key="Am",
        key_conf=0.8,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type="Kick",
        status="ok",
        details={"duration_sec": "2.5"},
    )


def test_workbench_rows_for_fl_export_skips_error_rows(tmp_path: Path):
    ok_row = _ok_workbench_row(tmp_path)
    error_row = WorkbenchRow(
        display_name="bad",
        relative_path="bad.wav",
        path=str(tmp_path / "bad.wav"),
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class=None,
        pred_type=None,
        status="error",
        error="failed",
    )

    exportable = workbench_rows_for_fl_export([ok_row, error_row])

    assert exportable == [ok_row]


def test_export_workbench_rows_to_fl_tags_empty_playlist(tmp_path: Path):
    result = export_workbench_rows_to_fl_tags([], tmp_path / "fl_user")

    assert not result.ok
    assert result.error_message is not None


def test_export_workbench_rows_to_fl_tags_rejects_missing_fl_path(tmp_path: Path):
    row = _ok_workbench_row(tmp_path)

    result = export_workbench_rows_to_fl_tags([row], "   ")

    assert not result.ok
    assert "FL User Data" in (result.error_message or "")


def test_export_workbench_rows_to_fl_tags_writes_tags(tmp_path: Path):
    root = tmp_path / "library"
    row = _ok_workbench_row(root)
    fl_user = tmp_path / "fl_user"

    result = export_workbench_rows_to_fl_tags([row], fl_user, roots=[root])

    assert result.ok
    assert result.exported_count == 1
    assert result.tags_path is not None
    assert result.tags_path.is_file()


def test_cli_help_includes_workbench():
    proc = subprocess.run(
        [sys.executable, "-m", "src.cli", "--help"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert proc.returncode == 0
    assert "workbench" in proc.stdout


def test_cli_import_does_not_load_tkinter():
    for name in ("tkinter", "src.workbench"):
        sys.modules.pop(name, None)

    import src.cli  # noqa: F401

    assert "tkinter" not in sys.modules
    assert "src.workbench" not in sys.modules


def test_workbench_module_imports_tkinter_only_when_loaded():
    mod = importlib.import_module("src.workbench")
    assert mod is not None


def test_get_workbench_library_folders_lists_registered(sample_folder: Path):
    add_workbench_library_folder(sample_folder)

    folders = get_workbench_library_folders()
    paths = {folder.path for folder in folders}
    assert str(sample_folder.resolve()) in paths


def test_remove_workbench_library_folder_returns_bool(sample_folder: Path):
    add_workbench_library_folder(sample_folder)

    assert remove_workbench_library_folder(sample_folder)
    assert not remove_workbench_library_folder(sample_folder)
    assert get_workbench_library_folders() == []


def test_load_cached_folder_rows_after_analysis(sample_folder: Path):
    analyze_folder_for_workbench(sample_folder)

    rows = load_cached_folder_rows(sample_folder)

    assert len(rows) == 2
    names = {row.display_name for row in rows}
    assert names == {"tone a", "kick b"}


def test_load_cached_folder_rows_empty_when_not_analyzed(tmp_path: Path):
    folder = tmp_path / "empty_lib"
    folder.mkdir()
    add_workbench_library_folder(folder)

    assert load_cached_folder_rows(folder) == []


def test_save_and_load_workbench_sample_cue_via_controller(sample_folder: Path):
    result = analyze_folder_for_workbench(sample_folder)
    row = result.rows[0]
    save_workbench_sample_cue(
        row.path,
        WorkbenchCueMetadata(cue_start_ms=123, cue_source="manual"),
        duration_ms=2000,
    )
    loaded = load_workbench_sample_cue(row.path)
    assert loaded.cue_start_ms == 123
    assert loaded.cue_source == "manual"


def test_save_workbench_sample_cue_unknown_path_raises(tmp_path: Path):
    missing = tmp_path / "ghost.wav"
    missing.write_bytes(b"data")
    with pytest.raises(WorkbenchCueNotFoundError):
        save_workbench_sample_cue(missing, WorkbenchCueMetadata(cue_start_ms=0))


def test_get_preview_start_ms_returns_saved_cue(sample_folder: Path):
    result = analyze_folder_for_workbench(sample_folder)
    row = result.rows[0]
    save_workbench_sample_cue(
        row.path,
        WorkbenchCueMetadata(cue_start_ms=456, cue_source="manual"),
        duration_ms=2000,
    )
    assert get_preview_start_ms(row.path) == 456


def test_get_preview_start_ms_defaults_to_zero_for_unknown_path(tmp_path: Path):
    missing = tmp_path / "ghost.wav"
    missing.write_bytes(b"data")
    assert get_preview_start_ms(missing) == 0


def test_effective_workbench_text_query_hides_search_when_bar_hidden():
    assert effective_workbench_text_query("kick", search_visible=False) == ""
    assert effective_workbench_text_query("kick", search_visible=True) == "kick"


def test_effective_workbench_row_filters_hides_structured_filters():
    filters = WorkbenchRowFilters(pred_type="Loop")
    assert effective_workbench_row_filters(filters, filters_visible=False) is None
    assert effective_workbench_row_filters(filters, filters_visible=True) == filters


def test_workbench_view_settings_round_trip(tmp_path: Path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    custom = WorkbenchViewSettings(
        show_search=False,
        show_filters=True,
        show_library_manage=False,
        show_waveform_tools=True,
    )
    assert save_workbench_view_settings(custom, state_dir=state_dir) is True
    loaded = load_workbench_view_settings(state_dir=state_dir)
    assert loaded == custom


def test_workbench_view_settings_invalid_json_falls_back_to_defaults(tmp_path: Path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    path_file = workbench_view_settings_file(state_dir=state_dir)
    path_file.write_text("{not-json", encoding="utf-8")
    assert load_workbench_view_settings(state_dir=state_dir) == DEFAULT_WORKBENCH_VIEW_SETTINGS


def test_save_and_load_workbench_analysis_limit(tmp_path: Path):
    state_dir = tmp_path / "state"

    assert save_workbench_analysis_limit("25", state_dir=state_dir)
    assert load_workbench_analysis_limit(state_dir=state_dir) == "25"
    assert workbench_analysis_limit_file(state_dir=state_dir).is_file()


def test_load_workbench_analysis_limit_defaults_when_missing(tmp_path: Path):
    assert (
        load_workbench_analysis_limit(state_dir=tmp_path / "missing")
        == DEFAULT_WORKBENCH_ANALYSIS_LIMIT_TEXT
    )


def test_load_workbench_analysis_limit_empty_means_no_limit(tmp_path: Path):
    state_dir = tmp_path / "state"
    assert save_workbench_analysis_limit("", state_dir=state_dir)
    assert load_workbench_analysis_limit(state_dir=state_dir) == ""


def test_load_workbench_analysis_limit_invalid_values_fall_back_to_default(tmp_path: Path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    path_file = workbench_analysis_limit_file(state_dir=state_dir)

    path_file.write_text("abc", encoding="utf-8")
    assert load_workbench_analysis_limit(state_dir=state_dir) == DEFAULT_WORKBENCH_ANALYSIS_LIMIT_TEXT

    path_file.write_text("0", encoding="utf-8")
    assert load_workbench_analysis_limit(state_dir=state_dir) == DEFAULT_WORKBENCH_ANALYSIS_LIMIT_TEXT

    path_file.write_text("-3", encoding="utf-8")
    assert load_workbench_analysis_limit(state_dir=state_dir) == DEFAULT_WORKBENCH_ANALYSIS_LIMIT_TEXT


def test_save_workbench_analysis_limit_rejects_invalid_values(tmp_path: Path):
    state_dir = tmp_path / "state"
    assert not save_workbench_analysis_limit("abc", state_dir=state_dir)
    assert not save_workbench_analysis_limit("0", state_dir=state_dir)
    assert not workbench_analysis_limit_file(state_dir=state_dir).exists()


def test_normalize_workbench_analysis_limit_text():
    assert normalize_workbench_analysis_limit_text("") == ""
    assert normalize_workbench_analysis_limit_text("  12  ") == "12"
    assert normalize_workbench_analysis_limit_text("abc") == DEFAULT_WORKBENCH_ANALYSIS_LIMIT_TEXT
    assert normalize_workbench_analysis_limit_text("0") == DEFAULT_WORKBENCH_ANALYSIS_LIMIT_TEXT


def test_format_workbench_view_status_messages():
    assert "zurückgesetzt" in format_workbench_view_section_hidden_status(VIEW_SECTION_FILTERS)
    assert "Waveform" in format_workbench_view_section_hidden_status(VIEW_SECTION_WAVEFORM_TOOLS)
    assert format_workbench_view_restore_status() == "Standardansicht wiederhergestellt"


def test_hidden_search_does_not_filter_playlist_rows():
    rows = [
        WorkbenchRow(
            display_name="kick.wav",
            relative_path="kick.wav",
            path="/a/kick.wav",
            bpm=120.0,
            key="C",
            key_conf=0.8,
            loudness=-10.0,
            brightness=50.0,
            sample_class="oneshot",
            pred_type="Kick",
            status="ok",
        ),
        WorkbenchRow(
            display_name="pad.wav",
            relative_path="pad.wav",
            path="/a/pad.wav",
            bpm=90.0,
            key="Am",
            key_conf=0.7,
            loudness=-12.0,
            brightness=40.0,
            sample_class="loop",
            pred_type="Pad",
            status="ok",
        ),
    ]
    visible = apply_workbench_filters(
        rows,
        effective_workbench_text_query("kick", search_visible=False),
        effective_workbench_row_filters(None, filters_visible=True),
    )
    assert len(visible) == 2


def test_list_workbench_playlists_returns_names(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    from src.workbench_library import create_playlist, workbench_library_db_path

    create_playlist("Song A", db_path=workbench_library_db_path(state_dir=state_dir))
    create_playlist("Song B", db_path=workbench_library_db_path(state_dir=state_dir))

    assert list_workbench_playlists(
        library_db_path=workbench_library_db_path(state_dir=state_dir)
    ) == ["Song A", "Song B"]


def test_add_workbench_row_to_playlist_and_status_message(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    from src.workbench_library import workbench_library_db_path

    sample = tmp_path / "kick.wav"
    sample.write_bytes(b"wav")
    row = WorkbenchRow(
        display_name="kick",
        relative_path="kick.wav",
        path=str(sample),
        bpm=128.0,
        key="Am",
        key_conf=0.8,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type="Kick",
        status="ok",
    )
    db_path = workbench_library_db_path(state_dir=state_dir)

    added = add_workbench_row_to_playlist(row, "Song A", library_db_path=db_path)
    assert added.result == "added"
    assert format_playlist_add_status(added) == 'Sample zu Playlist "Song A" hinzugefügt'

    duplicate = add_workbench_row_to_playlist(row, "Song A", library_db_path=db_path)
    assert duplicate.result == "duplicate"
    assert (
        format_playlist_add_status(duplicate)
        == 'Sample ist bereits in Playlist "Song A"'
    )
