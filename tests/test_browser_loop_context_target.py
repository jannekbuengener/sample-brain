"""#1284 context-target Loop ON invariant vs selection/audition A."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.browser_loop_playback import BrowserLoopOwner
from src.native_audio import SB_VOICE_IDLE
from src.workbench_controller import WorkbenchRow
from src.workbench_preview import WorkbenchPreviewPlayer
from src.workbench_qml import Screen1QmlInteractionAdapter
from src.workbench_qml_spike import build_qml_view_model_from_fixture
from src.workbench_transport_adapter import WorkbenchTransportAdapter
from src.workbench_transport_preview import TransportAwarePreview
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1
from types import SimpleNamespace


def _downbeats(bar_count: int = 4, frames_per_bar: int = 12_000) -> list[int]:
    return [i * frames_per_bar for i in range(bar_count + 1)]


def _enrich_row(row: WorkbenchRow, *, bpm: float = 120.0) -> WorkbenchRow:
    details = dict(row.details or {})
    details["beat_grid"] = {
        "downbeats": {"status": "ok", "sample_indices": _downbeats()},
        "beats": {"status": "ok", "sample_indices": _downbeats()},
    }
    return WorkbenchRow(
        display_name=row.display_name,
        relative_path=row.relative_path,
        path=row.path,
        bpm=bpm,
        key=row.key,
        key_conf=row.key_conf,
        loudness=row.loudness,
        brightness=row.brightness,
        sample_class="loop",
        pred_type="loop",
        status=row.status,
        details=details,
    )


class _FakeEngine:
    def __init__(self) -> None:
        self.voices: dict[int, SimpleNamespace] = {}
        self._engine_frame = 0
        self.running = True

    def create_voice(self, config) -> int:  # noqa: ANN001
        voice_id = int(config.id)
        self.voices[voice_id] = SimpleNamespace(state=1, config=config)
        return voice_id

    def schedule_voice_start(self, voice_id: int, engine_frame: int) -> None:
        self.voices[voice_id].start_frame = engine_frame

    def stop_voice(self, voice_id: int) -> None:
        if voice_id in self.voices:
            self.voices[voice_id].state = SB_VOICE_IDLE

    def remove_voice(self, voice_id: int) -> None:
        self.voices.pop(voice_id, None)

    def set_voice_rate(self, voice_id: int, rate: float) -> None:
        return None

    def snapshot(self):
        ids = list(self.voices)
        return SimpleNamespace(
            engine_frame=self._engine_frame,
            running=self.running,
            sample_rate=48000,
            voice_ids=ids + [0] * max(0, 8 - len(ids)),
            voice_states=[1] * len(ids) + [SB_VOICE_IDLE] * max(0, 8 - len(ids)),
            active_voice_count=len(ids),
            total_voice_count=len(ids),
        )


def test_context_loop_on_b_keeps_selection_and_audition_a(monkeypatch):
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")

    engine = _FakeEngine()
    transport = WorkbenchTransportAdapter(initial_bpm=120.0)
    transport._native_engine = engine  # noqa: SLF001
    transport._native_available = True  # noqa: SLF001
    transport._native_owned = False  # noqa: SLF001
    transport._native_opened = True  # noqa: SLF001
    transport._native_started = True  # noqa: SLF001
    transport._last_native_engine_frame = 0  # noqa: SLF001

    audition = TransportAwarePreview(WorkbenchPreviewPlayer(), transport)

    def pcm_audition(path, *, sample_rate: int, start_ms: int = 0, **_kwargs):  # noqa: ANN001
        return np.zeros((sample_rate, 1), dtype=np.float32), 1

    audition._pcm_load_fn = pcm_audition  # noqa: SLF001
    monkeypatch.setattr(
        "src.workbench_transport_preview.read_audio_duration_ms",
        lambda _p: 1000,
    )

    def pcm_loop(path, *, sample_rate: int, start_frame: int, end_frame_exclusive: int):  # noqa: ANN001
        frames = max(1, int(end_frame_exclusive) - int(start_frame))
        return np.zeros((frames, 1), dtype=np.float32), 1

    browser_loop = BrowserLoopOwner(transport, pcm_load_fn=pcm_loop)
    audition.set_should_keep_shared_transport(lambda: browser_loop.is_active)

    previews: list[str] = []

    def on_preview(row, **kwargs):  # noqa: ANN001
        previews.append(str(row.path))
        return audition.play_row(row, start_ms=0)

    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        on_preview_requested=on_preview,
        on_preview_stopped=audition.stop,
    )
    adapter.bind_browser_loop(browser_loop)

    # Enrich visible rows A/B with reliable downbeats for Loop eligibility.
    row_a = _enrich_row(fixture.browser_rows[0])
    row_b = _enrich_row(fixture.browser_rows[1])
    view_model.set_browser_state(
        rows=(row_a, row_b, *tuple(_enrich_row(r) for r in fixture.browser_rows[2:3])),
        selected_index=0,
        browser_context="test",
        error=None,
    )

    adapter.select_row(0)
    assert view_model.selected_browser_index == 0
    assert audition.play_row(row_a, start_ms=0).ok
    audition_path = audition.current_path
    audition_voice = audition.active_voice_id
    previews.clear()

    opened = adapter.open_sample_context(1)
    assert Path(opened.path) == Path(row_b.path)
    assert adapter.sample_context_target is not None
    assert Path(adapter.sample_context_target.path) == Path(row_b.path)
    assert view_model.selected_browser_index == 0
    assert previews == []
    assert audition.active_voice_id == audition_voice

    target = adapter.request_context_loop_on()
    assert Path(target.path) == Path(row_b.path)
    assert browser_loop.is_active
    assert Path(browser_loop.owner_row.path) == Path(row_b.path)
    assert view_model.selected_browser_index == 0
    assert audition.active_voice_id == audition_voice
    assert Path(str(audition_path)).name == Path(row_a.path).name
