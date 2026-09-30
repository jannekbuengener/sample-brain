"""#738 preview playhead — authoritative snapshot + QML overlay contracts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.native_audio import SB_VOICE_IDLE, SB_VOICE_PLAYING, SB_VOICE_SCHEDULED
from src.workbench_controller import WorkbenchRow
from src.workbench_preview import PreviewResult, WorkbenchPreviewPlayer
from src.workbench_qml import QML_SOURCE, Screen1QmlInteractionAdapter, Screen1QmlViewModel
from src.workbench_transport_adapter import WorkbenchTransportAdapter
from src.workbench_transport_ui import PreviewPlaybackSnapshot, TransportAwarePreview


def _row(name: str = "kick.wav", path: str | None = None) -> WorkbenchRow:
    resolved = path or str(Path(f"C:/samples/{name}"))
    return WorkbenchRow(
        display_name=name,
        relative_path=name,
        path=resolved,
        bpm=120.0,
        key="Am",
        key_conf=0.9,
        loudness=-12.0,
        brightness=0.4,
        sample_class="one_shot",
        pred_type="one_shot",
        status="ok",
        details={"duration_sec": "1.000"},
    )


class _FakeEngine:
    def __init__(self) -> None:
        self.voices: dict[int, SimpleNamespace] = {}
        self._engine_frame = 0
        self.running = True
        self.removed: list[int] = []
        self.stopped: list[int] = []

    def create_voice(self, config) -> int:  # noqa: ANN001
        voice_id = int(config.id)
        self.voices[voice_id] = SimpleNamespace(state=SB_VOICE_PLAYING, config=config)
        return voice_id

    def schedule_voice_start(self, voice_id: int, frame: int) -> None:
        self.voices[voice_id].state = SB_VOICE_PLAYING
        self.voices[voice_id].start_frame = frame

    def stop_voice(self, voice_id: int) -> None:
        self.stopped.append(voice_id)
        if voice_id in self.voices:
            self.voices[voice_id].state = SB_VOICE_IDLE

    def remove_voice(self, voice_id: int) -> None:
        self.removed.append(voice_id)
        self.voices.pop(voice_id, None)

    def set_voice_rate(self, voice_id: int, rate: float) -> None:
        return None

    def snapshot(self):
        ids = list(self.voices)
        states = [self.voices[v].state for v in ids]
        # Pad to look like native snapshot lists indexed by slot; adapter scans by id.
        return SimpleNamespace(
            engine_frame=self._engine_frame,
            running=self.running,
            sample_rate=48000,
            voice_ids=ids + [0] * (8 - len(ids)),
            voice_states=states + [SB_VOICE_IDLE] * (8 - len(states)),
            active_voice_count=len(ids),
            total_voice_count=len(ids),
        )

    def advance(self, frames: int) -> None:
        self._engine_frame += frames


def _native_preview(monkeypatch: pytest.MonkeyPatch) -> tuple[TransportAwarePreview, _FakeEngine]:
    engine = _FakeEngine()
    transport = WorkbenchTransportAdapter(initial_bpm=120.0)
    transport._native_engine = engine  # noqa: SLF001 — test seam
    transport._native_available = True  # noqa: SLF001
    transport._native_owned = False  # noqa: SLF001
    transport._native_opened = True  # noqa: SLF001
    transport._native_started = True  # noqa: SLF001
    transport._last_native_engine_frame = 0  # noqa: SLF001

    preview = TransportAwarePreview(WorkbenchPreviewPlayer(), transport)

    def _pcm_load(path, *, sample_rate: int, start_ms: int):  # noqa: ANN001
        import numpy as np

        # 1 second mono at engine rate; start_ms ignored for fixture length.
        samples = max(1, int(sample_rate * 1.0))
        return np.zeros((samples, 1), dtype=np.float32), 1

    preview._pcm_load_fn = _pcm_load  # noqa: SLF001
    monkeypatch.setattr(
        "src.workbench_transport_preview.read_audio_duration_ms",
        lambda _path: 1000,
    )
    return preview, engine


def test_idle_snapshot_is_fail_closed() -> None:
    transport = WorkbenchTransportAdapter(initial_bpm=120.0)
    preview = TransportAwarePreview(WorkbenchPreviewPlayer(), transport)
    snap = preview.playback_snapshot()
    assert snap == PreviewPlaybackSnapshot.idle()
    assert snap.playing is False
    assert snap.progress == 0.0
    assert snap.sample_path == ""
    assert snap.playback_instance_id == 0


def test_legacy_preview_without_native_voice_does_not_invent_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = WorkbenchTransportAdapter(initial_bpm=120.0)
    transport._native_available = False  # noqa: SLF001
    player = WorkbenchPreviewPlayer(
        play_fn=lambda _path, start_ms=0: PreviewResult(ok=True),
        stop_fn=lambda: None,
    )
    preview = TransportAwarePreview(player, transport)
    row = _row()
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    result = preview.play(Path(row.path))
    assert result.ok
    snap = preview.playback_snapshot()
    assert snap.playing is False
    assert snap.progress == 0.0


def test_native_play_row_snapshot_exposes_engine_backed_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview, engine = _native_preview(monkeypatch)
    row = _row()
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(Path, "resolve", lambda self: Path(row.path))

    assert preview.play_row(row, start_ms=0).ok
    snap = preview.playback_snapshot()
    assert snap.playing is True
    assert snap.sample_path == row.path
    assert snap.duration_ms == 1000
    assert snap.playback_instance_id > 0
    assert 0.0 <= snap.progress <= 1.0

    engine.advance(24_000)  # 0.5s at 48k
    snap_mid = preview.playback_snapshot()
    assert snap_mid.playing is True
    assert snap_mid.progress == pytest.approx(0.5, abs=0.05)


def test_voice_idle_clears_progress_without_fake_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview, engine = _native_preview(monkeypatch)
    row = _row()
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(Path, "resolve", lambda self: Path(row.path))
    assert preview.play_row(row).ok
    voice_id = preview.active_voice_id
    assert voice_id is not None
    engine.voices[voice_id].state = SB_VOICE_IDLE
    snap = preview.playback_snapshot()
    assert snap.playing is False
    assert snap.progress == 0.0


def test_stop_clears_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    preview, _engine = _native_preview(monkeypatch)
    row = _row()
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(Path, "resolve", lambda self: Path(row.path))
    assert preview.play_row(row).ok
    preview.stop()
    assert preview.playback_snapshot() == PreviewPlaybackSnapshot.idle()


def test_rapid_replacement_switches_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview, _engine = _native_preview(monkeypatch)
    a = _row("a.wav", path="C:/samples/a.wav")
    b = _row("b.wav", path="C:/samples/b.wav")
    monkeypatch.setattr(Path, "is_file", lambda self: True)

    def _resolve(self: Path) -> Path:
        return Path(str(self))

    monkeypatch.setattr(Path, "resolve", _resolve)
    assert preview.play_row(a).ok
    first_id = preview.playback_snapshot().playback_instance_id
    assert preview.play_row(b).ok
    second = preview.playback_snapshot()
    assert second.playing is True
    assert second.sample_path.endswith("b.wav")
    assert second.playback_instance_id != first_id


def test_adapter_projects_snapshot_and_clears_on_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview, _engine = _native_preview(monkeypatch)
    row = _row()
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(Path, "resolve", lambda self: Path(row.path))

    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    view_model.set_browser_state(
        rows=(row,),
        selected_index=0,
        browser_context="Library",
        error=None,
    )
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        on_preview_requested=lambda r, *, start_ms=None: preview.play_row(
            r, start_ms=start_ms or 0
        ),
        on_preview_stopped=preview.stop,
        on_preview_snapshot=preview.playback_snapshot,
    )
    adapter.preview_row(0)
    projected = adapter.preview_playback_snapshot()
    assert projected.playing is True
    assert projected.sample_path.endswith("kick.wav")
    assert adapter.stop_preview() is True
    assert adapter.preview_playback_snapshot() == PreviewPlaybackSnapshot.idle()


def test_qml_source_has_shared_playhead_overlay_without_per_row_timers() -> None:
    source = QML_SOURCE
    assert 'objectName: "previewPlayhead"' in source
    assert source.count('objectName: "previewPlayhead"') >= 2  # browser + harmony
    assert "previewPlayingPath" in source
    assert "previewProgress" in source
    assert "waveformMotionMode" in source
    assert "FrameAnimation" in source
    assert "refreshPreviewPlayback" in source
    # No per-delegate Timer for playhead motion.
    browser = source[source.index('objectName: "browserList"') :]
    browser = browser[: browser.index('objectName: "elasticHandleAfterBrowser"')]
    assert "Timer {" not in browser
    assert "Canvas.requestPaint()" not in source or "requestPaint()" in source
    # Playhead must not drive Canvas.requestPaint for motion.
    assert "onPreviewProgressChanged: waveformCanvas.requestPaint()" not in source
    assert "onPreviewProgressChanged: harmonyWaveformCanvas.requestPaint()" not in source


def test_qml_selection_change_requests_waveform_repaint_independently() -> None:
    source = QML_SOURCE
    assert "property bool waveformSelected:" in source
    assert "onWaveformSelectedChanged: requestPaint()" in source
    assert "waveformSelected ? theme.waveformActive : theme.waveformDefault" in source
