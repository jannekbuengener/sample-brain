"""Focused tests for the HÄFTIG Workbench runtime path (issue #327).

These tests exercise the deterministic core wiring only through the existing
infrastructure: the authoritative source playhead in
``WorkbenchTransportAdapter``, the ``workbench_editing`` persistence/orchestration
helpers, and the waveform frame mapping. They do NOT require the native audio
engine.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import soundfile as sf

from src.haeftig import HAEFTIG_REGION_TYPE, HaeftigRegion, select_haeftig_region
from src.workbench_controller import WorkbenchRow
from src.workbench_editing import (
    EditRegionValidationError,
    delete_haeftig_regions,
    load_haeftig_regions,
    load_source_downbeats,
    save_haeftig_region,
    trigger_haeftig_region,
)
from src.workbench_transport_adapter import WorkbenchTransportAdapter
from src.workbench_waveform import frame_region_x


def _make_downbeats(count: int = 32, step: int = 100) -> list[int]:
    """Ordered source downbeat frames for 4/4 bars (32 downbeats = 31 bars)."""
    return [i * step for i in range(count)]


def _make_row(path: str, *, bpm: float | None = 120.0) -> WorkbenchRow:
    return WorkbenchRow(
        display_name="s",
        relative_path="s.wav",
        path=path,
        bpm=bpm,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class=None,
        pred_type=None,
        status="ok",
        details={
            "beat_grid": {
                "downbeats": {
                    "status": "ok",
                    "sample_indices": _make_downbeats(),
                }
            }
        },
    )


def _make_adapter(source_ref: str) -> WorkbenchTransportAdapter:
    adapter = WorkbenchTransportAdapter(initial_bpm=132)
    adapter.set_source_bpm(120, source_ref=source_ref, source_start_frame=0)
    return adapter


class TestHaeftigExactAndMidBarTrigger:
    def test_exact_downbeat_trigger_creates_correct_16_bar_region(self, tmp_path):
        path = str(tmp_path / "s.wav")
        adapter = _make_adapter(path)
        row = _make_row(path)
        # Audible position lands exactly on downbeat index 16 (frame 1600).
        adapter.seek(0, source_frame=1600)

        selection = trigger_haeftig_region(
            adapter,
            row,
            downbeat_frames=_make_downbeats(),
            grid_reliable=True,
        )
        assert selection is not None
        assert selection.status == "ok"
        region = selection.region
        assert region is not None
        assert region.region_type == HAEFTIG_REGION_TYPE
        assert region.source_start_frame == 0
        assert region.source_end_frame_exclusive == 1600
        assert region.source_start_bar_index == 0
        assert region.source_end_bar_index_exclusive == 16

    def test_mid_bar_trigger_selects_the_enclosing_16_bars(self, tmp_path):
        path = str(tmp_path / "s.wav")
        adapter = _make_adapter(path)
        row = _make_row(path)
        # Audible position is mid-bar (frame 1650, between downbeat 16 and 17).
        adapter.seek(0, source_frame=1650)

        selection = trigger_haeftig_region(
            adapter,
            row,
            downbeat_frames=_make_downbeats(),
            grid_reliable=True,
        )
        assert selection is not None and selection.status == "ok"
        region = selection.region
        assert region.source_start_frame == 100  # downbeat[1]
        assert region.source_end_frame_exclusive == 1700  # downbeat[17]
        assert region.source_end_bar_index_exclusive - region.source_start_bar_index == 16


class TestHaeftigSourcePlayheadHonesty:
    def test_playhead_is_piecewise_integrated_not_session_times_rate(self, tmp_path):
        """The source playhead must not be ``session_frame * current_rate``.

        Phase 1 (SYNC ON, rate 2.0) advances 100 engine frames -> +200 source.
        Phase 2 (rate changes to 1.0) advances another 100 engine frames -> +100.
        Honest source frame is 300 at session frame 200; the anti-pattern would
        yield 200 * 1.0 = 200."""
        path = str(tmp_path / "s.wav")
        adapter = WorkbenchTransportAdapter(initial_bpm=132)
        adapter.toggle_sync()  # SYNC ON
        adapter.set_source_bpm(66, source_ref=path, source_start_frame=0)  # rate 2.0
        adapter.seek(0, source_frame=0)
        adapter._transport.play()  # make the transport "playing" so session advances
        adapter.advance(100)  # source 0 -> 200, session 0 -> 100

        adapter.set_source_bpm(132, source_ref=path)  # rate -> 1.0
        adapter.advance(100)  # source 200 -> 300, session 100 -> 200

        context = adapter.get_haeftig_trigger_context(path)
        assert context == (300, 200)
        # Explicit guard against the forbidden back-calculation.
        assert context[0] != 200 * 1.0
        assert context[0] == 300


class TestHaeftigPlayheadTempoBoundaries:
    def test_tempo_boundary_is_piecewise_not_retroactive(self, tmp_path):
        """A tempo change inside one advance must NOT retroactively re-rate the
        already-elapsed frames.

        Master 132 for [0,100) -> rate 1.0 (source 132). Master jumps to 264 at
        frame 100 -> rate 2.0 for [100,200). Honest source = 100 + 200 = 300.
        The forbidden back-calculation would rate the whole 200 frames at 2.0
        and yield 400."""
        path = str(tmp_path / "s.wav")
        adapter = WorkbenchTransportAdapter(initial_bpm=132)
        adapter.toggle_sync()  # SYNC ON
        adapter.set_source_bpm(132, source_ref=path, source_start_frame=0)  # rate 1.0
        adapter.seek(0, source_frame=0)
        # Inject a tempo boundary strictly inside the upcoming advance.
        adapter._transport.tempo_map.add_tempo_change_at_frame(
            effective_frame=100, bpm=264
        )
        adapter._transport.play()
        adapter.advance(200)  # crosses the boundary in a single delta

        context = adapter.get_haeftig_trigger_context(path)
        assert context == (300, 200)
        # The retroactive anti-pattern would yield 400.
        assert context[0] != 400

    def test_engine_runs_but_session_stopped_holds_source(self, tmp_path):
        """When the engine is running but the transport is not advancing, the
        source playhead must not move (engine delta != session delta)."""
        path = str(tmp_path / "s.wav")
        adapter = WorkbenchTransportAdapter(initial_bpm=132)
        adapter.set_source_bpm(120, source_ref=path, source_start_frame=0)
        adapter.seek(0, source_frame=500)
        # Transport NOT started -> session does not advance on advance().
        assert adapter.playing is False
        adapter.advance(100)
        assert adapter.get_source_frame() == 500

    def test_play_preserves_explicit_seek_anchor(self, tmp_path):
        """play() must not overwrite a source position established by an earlier
        explicit seek."""
        path = str(tmp_path / "s.wav")
        adapter = WorkbenchTransportAdapter(initial_bpm=132)
        adapter.set_source_bpm(120, source_ref=path, source_start_frame=0)
        adapter.seek(0, source_frame=777)
        adapter._transport.play()
        adapter.play()
        assert adapter.get_source_frame() == 777
        assert adapter.get_haeftig_trigger_context(path) == (777, 0)


class TestHaeftigFailClosed:
    def test_missing_grid_yields_no_result(self, tmp_path):
        path = str(tmp_path / "s.wav")
        adapter = _make_adapter(path)
        row = _make_row(path)
        adapter.seek(0, source_frame=1600)

        selection = trigger_haeftig_region(
            adapter,
            row,
            downbeat_frames=_make_downbeats(),
            grid_reliable=False,
        )
        assert selection is not None
        assert selection.status == "unavailable"
        assert selection.reason_code == "GRID_UNRELIABLE"
        assert selection.region is None

    def test_unreliable_grid_from_details_yields_no_result(self, tmp_path):
        path = str(tmp_path / "s.wav")
        adapter = _make_adapter(path)
        row = _make_row(path)
        adapter.seek(0, source_frame=1600)
        # details carry a downbeat series that is NOT status "ok".
        bad_row = WorkbenchRow(
            display_name="s",
            relative_path="s.wav",
            path=path,
            bpm=120,
            key=None,
            key_conf=None,
            loudness=None,
            brightness=None,
            sample_class=None,
            pred_type=None,
            status="ok",
            details={
                "beat_grid": {
                    "downbeats": {
                        "status": "failed",
                        "sample_indices": _make_downbeats(),
                    }
                }
            },
        )
        downbeats, reliable, _ref = load_source_downbeats(path, details=bad_row.details)
        assert reliable is False and downbeats == ()
        selection = trigger_haeftig_region(
            adapter, bad_row, downbeat_frames=downbeats, grid_reliable=reliable
        )
        assert selection is not None
        assert selection.status == "unavailable"
        assert selection.reason_code == "GRID_UNRELIABLE"

    def test_no_anchor_fails_closed(self, tmp_path):
        path = str(tmp_path / "s.wav")
        adapter = WorkbenchTransportAdapter(initial_bpm=132)
        row = _make_row(path)
        # Never anchored: _source_frame is None.
        assert adapter.get_haeftig_trigger_context(path) is None
        assert (
            trigger_haeftig_region(
                adapter, row, downbeat_frames=_make_downbeats(), grid_reliable=True
            )
            is None
        )

    def test_source_ref_mismatch_fails_closed(self, tmp_path):
        path = str(tmp_path / "s.wav")
        other = str(tmp_path / "other.wav")
        adapter = _make_adapter(other)  # context is for `other`
        row = _make_row(path)
        adapter.seek(0, source_frame=1600)
        assert adapter.get_haeftig_trigger_context(path) is None
        assert (
            trigger_haeftig_region(
                adapter, row, downbeat_frames=_make_downbeats(), grid_reliable=True
            )
            is None
        )

    def test_polyphony_fails_closed(self, tmp_path):
        path = str(tmp_path / "s.wav")
        adapter = _make_adapter(path)
        row = _make_row(path)
        adapter.seek(0, source_frame=1600)
        adapter.set_voice_source_bpm(0, 120.0)
        adapter.set_voice_source_bpm(1, 120.0)  # two voices -> ambiguous
        assert adapter.get_haeftig_trigger_context(path) is None
        assert (
            trigger_haeftig_region(
                adapter, row, downbeat_frames=_make_downbeats(), grid_reliable=True
            )
            is None
        )

    def test_sync_on_without_source_bpm_fails_closed(self, tmp_path):
        path = str(tmp_path / "s.wav")
        adapter = WorkbenchTransportAdapter(initial_bpm=132)
        adapter.set_source_bpm(None, source_ref=path, source_start_frame=0)
        adapter.toggle_sync()  # SYNC ON, but source bpm unknown -> rate undefined
        adapter.seek(0, source_frame=1600)
        assert adapter.get_haeftig_trigger_context(path) is None
        assert (
            trigger_haeftig_region(
                adapter, row := _make_row(path),
                downbeat_frames=_make_downbeats(), grid_reliable=True
            )
            is None
        )


class TestHaeftigPersistence:
    def test_persist_reload_multiple_and_dedupe(self, tmp_path):
        state = tmp_path / "workbench_edit_regions.json"
        path = str(tmp_path / "s.wav")

        region_a = select_haeftig_region(
            downbeat_frames=_make_downbeats(),
            trigger_source_frame=1600,
            source_ref=path,
            grid_reliable=True,
        ).region
        region_b = select_haeftig_region(
            downbeat_frames=_make_downbeats(),
            trigger_source_frame=1650,
            source_ref=path,
            grid_reliable=True,
        ).region

        _, added_a = save_haeftig_region(region_a, state_path=state)
        assert added_a is True
        _, added_a_again = save_haeftig_region(region_a, state_path=state)
        assert added_a_again is False  # identical deduplicated
        _, added_b = save_haeftig_region(region_b, state_path=state)
        assert added_b is True

        loaded = load_haeftig_regions(path, state_path=state)
        assert len(loaded) == 2
        starts = sorted(r.source_start_frame for r in loaded)
        assert starts == [0, 100]

    def test_tempo_sync_keylock_changes_do_not_alter_stored_bounds(self, tmp_path):
        state = tmp_path / "workbench_edit_regions.json"
        path = str(tmp_path / "s.wav")

        region = select_haeftig_region(
            downbeat_frames=_make_downbeats(),
            trigger_source_frame=1600,
            source_ref=path,
            grid_reliable=True,
        ).region
        save_haeftig_region(region, state_path=state)

        # Mutate every sync/tempo/keylock control on the live adapter.
        adapter = _make_adapter(path)
        adapter.set_tempo(999.0)
        adapter.toggle_sync()
        adapter.set_keylock_mode(True)
        adapter.set_source_bpm(9999, source_ref=path)

        reloaded = load_haeftig_regions(path, state_path=state)
        assert len(reloaded) == 1
        restored = reloaded[0]
        assert restored.region_type == HAEFTIG_REGION_TYPE  # only HÄFTIG
        assert restored.source_start_frame == region.source_start_frame
        assert restored.source_end_frame_exclusive == region.source_end_frame_exclusive
        assert restored.source_start_bar_index == region.source_start_bar_index
        assert (
            restored.source_end_bar_index_exclusive
            == region.source_end_bar_index_exclusive
        )

    def test_version_1_file_migrates_without_losing_edit_regions(self, tmp_path):
        import json

        from src.workbench_editing import (
            _normalized_source_ref,
            load_workbench_edit_region,
        )

        state = tmp_path / "workbench_edit_regions.json"
        src = str(tmp_path / "s.wav")
        key = _normalized_source_ref(src)
        # Hand-written version 1 document (issue #326 edit regions only).
        doc = {
            "version": 1,
            "regions": {
                key: {
                    "source_ref": key,
                    "source_start_frame": 10,
                    "source_end_frame_exclusive": 20,
                    "source_sample_rate": 48000,
                    "snap_mode": "none",
                    "grid_source_ref": None,
                    "label": None,
                    "region_id": None,
                }
            },
        }
        state.write_text(json.dumps(doc), encoding="utf-8")
        # HÄFTIG loader must still work and find no HÄFTIG regions.
        assert load_haeftig_regions(src, state_path=state) == ()
        # The existing #326 region must survive migration.
        existing = load_workbench_edit_region(src, state_path=state)
        assert existing is not None
        assert existing.source_start_frame == 10

    def test_delete_haeftig_regions(self, tmp_path):
        state = tmp_path / "workbench_edit_regions.json"
        path = str(tmp_path / "s.wav")
        region = select_haeftig_region(
            downbeat_frames=_make_downbeats(),
            trigger_source_frame=1600,
            source_ref=path,
            grid_reliable=True,
        ).region
        save_haeftig_region(region, state_path=state)
        assert delete_haeftig_regions(path, state_path=state) is True
        assert load_haeftig_regions(path, state_path=state) == ()


class TestHaeftigWaveformBounds:
    def test_persisted_region_reaches_frame_region_x_with_exact_bounds(self, tmp_path):
        state = tmp_path / "workbench_edit_regions.json"
        path = str(tmp_path / "s.wav")
        total_frames = 4000
        width = 800

        region = select_haeftig_region(
            downbeat_frames=_make_downbeats(),
            trigger_source_frame=1600,
            source_ref=path,
            grid_reliable=True,
        ).region
        save_haeftig_region(region, state_path=state)

        # The persisted region must round-trip with exactly the same source bounds.
        loaded = load_haeftig_regions(path, state_path=state)
        assert len(loaded) == 1
        restored = loaded[0]
        assert restored.source_start_frame == region.source_start_frame
        assert restored.source_end_frame_exclusive == region.source_end_frame_exclusive

        # The waveform helper receives the persisted bounds verbatim (no
        # seconds/BPM back-calculation): mapping the original and the restored
        # fields yields identical canvas coordinates.
        expected = frame_region_x(
            region.source_start_frame,
            region.source_end_frame_exclusive,
            total_frames,
            width,
        )
        actual = frame_region_x(
            restored.source_start_frame,
            restored.source_end_frame_exclusive,
            total_frames,
            width,
        )
        assert actual == expected
        assert actual is not None
        x_start, x_end = actual
        assert x_end > x_start


class TestHaeftigHotkeyHandler:
    def test_ctrl_h_handler_creates_and_persists_region(self, tmp_path, monkeypatch):
        import tkinter as tk

        from src.workbench import WorkbenchApp

        state_dir = tmp_path / "state"
        state_dir.mkdir()
        monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))

        wav = tmp_path / "s.wav"
        sr = 48000
        sf.write(str(wav), [0.0] * 4000, sr)  # enough frames for the region

        root = tk.Tk()
        root.withdraw()
        try:
            app = WorkbenchApp(root)
            row = _make_row(str(wav))
            app._detail_row = row
            app._transport_adapter.set_source_bpm(
                120, source_ref=str(wav), source_start_frame=0
            )
            app._transport_adapter.seek(0, source_frame=1600)

            app._on_haeftig_hotkey()

            regions = load_haeftig_regions(str(wav))
            assert len(regions) == 1
            assert regions[0].source_start_frame == 0
            assert regions[0].source_end_frame_exclusive == 1600
            assert regions[0].region_type == HAEFTIG_REGION_TYPE
        finally:
            root.destroy()
