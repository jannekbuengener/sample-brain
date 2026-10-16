"""Additional #1078 retry regressions found during independent review."""

from pathlib import Path

from src import workbench_session as ws
from src import track_package as tp
from tests.audio_fixtures import write_sine_wav
from tests.test_active_track_persistence_1098 import _row
from tests.test_edit_arrangement_transition_1078 import draft, enable, enter  # noqa: F401


def test_pointer_failure_retry_uses_current_draft_in_same_package(draft, monkeypatch):
    s, root, _ = draft
    enable(s)
    real_save = ws.save_active_track_pointer

    def fail(*args, **kwargs):
        raise OSError("synthetic pointer failure")

    monkeypatch.setattr(ws, "save_active_track_pointer", fail)
    assert not enter(s, root).ok
    created_id = tp.open_track_package(root).track_id
    s.transport.set_tempo(139)
    monkeypatch.setattr(ws, "save_active_track_pointer", real_save)
    assert enter(s, root).ok
    assert s.active_track_id == created_id
    assert s.transport.get_current_tempo() == 139
    assert tp.open_track_package(root).manifest.musical["master_bpm"] == 139


def test_failed_autosave_retry_adopts_portable_media_paths(
    draft, monkeypatch, tmp_path
):
    s, root, _ = draft
    enable(s)
    assert enter(s, root).ok
    s.return_to_edit()
    real_save = ws.save_track_package_musical_state

    def fail(*args, **kwargs):
        return tp.TrackPackageResult(
            tp.OUTCOME_WRITE_FAILED, message="synthetic save failure"
        )

    monkeypatch.setattr(ws, "save_track_package_musical_state", fail)
    replacement = tmp_path / "new.wav"
    write_sine_wav(replacement, duration_sec=0.05, frequency_hz=110)
    s.live_kit.assign("Kick + Bass", "Kick", _row(replacement))
    assert s.track_package_dirty
    monkeypatch.setattr(ws, "save_track_package_musical_state", real_save)
    assert enter(s).ok
    runtime_path = Path(s.live_kit.assignment_for("Kick + Bass", "Kick").path)
    assert runtime_path.is_relative_to(root)
    assert runtime_path.read_bytes() == replacement.read_bytes()
    assert s.channel_rack.state.channels[0].sample_path == str(runtime_path)
    replacement.unlink()
    assert enter(s).ok


def test_pending_package_external_change_is_rejected(draft, monkeypatch):
    s, root, _ = draft
    enable(s)
    real_save = ws.save_active_track_pointer

    def fail(*args, **kwargs):
        raise OSError("synthetic pointer failure")

    monkeypatch.setattr(ws, "save_active_track_pointer", fail)
    assert not enter(s, root).ok
    opened = tp.open_track_package(root)
    musical = dict(opened.manifest.musical, master_bpm=177)
    assert tp.save_track_package_musical_state(root, musical).ok
    monkeypatch.setattr(ws, "save_active_track_pointer", real_save)
    assert not enter(s, root).ok
    assert s.active_track_id is None
    assert s.projection_mode == "EDIT"
    assert tp.open_track_package(root).manifest.musical["master_bpm"] == 177


def test_committed_media_adoption_failure_keeps_persistence_honest(draft, monkeypatch):
    s, root, _ = draft
    enable(s)
    assert enter(s, root).ok
    s.return_to_edit()

    def fail(*args, **kwargs):
        raise OSError("committed media disappeared: C:/private/producer/session.wav")

    monkeypatch.setattr(ws, "_adopt_saved_package_media", fail)
    result = enter(s)
    assert not result.ok
    assert "C:/private" not in result.message
    assert s.projection_mode == "EDIT"
    assert s.track_package_status == tp.OUTCOME_WRITE_FAILED
    assert s.track_package_dirty
