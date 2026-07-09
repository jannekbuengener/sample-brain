"""Tests for workbench auto-metadata (loop region, oneshot attack/cue) per #172 / #173."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.workbench_attack_suggest import AttackSuggestion
from src.workbench_auto_metadata import (
    apply_auto_loop_metadata,
    apply_auto_metadata_after_analyze,
    apply_auto_oneshot_metadata,
    is_definite_loop,
    is_definite_oneshot,
    should_skip_auto_metadata,
)
from src.workbench_controller import (
    WorkbenchRow,
    analyze_folder_for_workbench,
    is_catalog_readonly_row,
    load_workbench_sample_cue,
    save_workbench_sample_cue,
)
from src.workbench_library import WorkbenchCueMetadata, workbench_library_db_path
from tests.audio_fixtures import write_sine_wav


@pytest.fixture(autouse=True)
def _isolated_workbench_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_dir = tmp_path / "workbench_state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))


def _row(
    *,
    pred_type: str | None = "Loop",
    sample_class: str | None = "loop",
    duration_sec: float = 2.0,
    path: str = "/tmp/sample.wav",
    catalog_readonly: bool = False,
) -> WorkbenchRow:
    details: dict = {"duration_sec": duration_sec}
    if catalog_readonly:
        details["catalog_readonly"] = True
    return WorkbenchRow(
        display_name="test",
        relative_path="test.wav",
        path=path,
        bpm=120.0,
        key="C",
        key_conf=0.5,
        loudness=-12.0,
        brightness=2000.0,
        sample_class=sample_class,
        pred_type=pred_type,
        status="ok",
        details=details,
    )


def test_is_definite_loop_accepts_loop_labels():
    assert is_definite_loop("Loop", "loop")
    assert is_definite_loop("Drum Loop", "loop")
    assert is_definite_loop(None, "loop")


def test_is_definite_loop_rejects_non_loop():
    assert not is_definite_loop("Drone", "loop")
    assert not is_definite_loop("OneShot", "oneshot")
    assert not is_definite_loop("Kick", "oneshot")
    assert not is_definite_loop(None, "oneshot")


def test_is_definite_oneshot_accepts_oneshot_only():
    assert is_definite_oneshot("OneShot", "oneshot")
    assert is_definite_oneshot(None, "oneshot")
    assert not is_definite_oneshot("Kick", "oneshot")
    assert not is_definite_oneshot("Snare", "oneshot")
    assert not is_definite_oneshot("Loop", "loop")


def test_apply_auto_loop_metadata_sets_full_region():
    existing = WorkbenchCueMetadata()
    result = apply_auto_loop_metadata(existing, duration_ms=2000)
    assert result is not None
    assert result.loop_start_ms == 0
    assert result.loop_end_ms == 2000
    assert result.attack_ms is None
    assert result.cue_start_ms == 0


def test_apply_auto_loop_metadata_skips_when_loop_fields_set():
    existing = WorkbenchCueMetadata(loop_start_ms=100, loop_end_ms=500)
    assert apply_auto_loop_metadata(existing, duration_ms=2000) is None


def test_apply_auto_loop_metadata_skips_invalid_duration():
    existing = WorkbenchCueMetadata()
    assert apply_auto_loop_metadata(existing, duration_ms=None) is None
    assert apply_auto_loop_metadata(existing, duration_ms=0) is None
    assert apply_auto_loop_metadata(existing, duration_ms=-1) is None


def test_apply_auto_loop_metadata_preserves_manual_attack_and_cue():
    existing = WorkbenchCueMetadata(
        cue_start_ms=250,
        attack_ms=80,
        cue_source="manual",
        cue_updated_at="2026-01-01T00:00:00+00:00",
    )
    result = apply_auto_loop_metadata(existing, duration_ms=3000)
    assert result is not None
    assert result.loop_start_ms == 0
    assert result.loop_end_ms == 3000
    assert result.attack_ms == 80
    assert result.cue_start_ms == 250
    assert result.cue_source == "manual"


def test_apply_auto_oneshot_metadata_sets_attack_and_cue(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "shot.wav", duration_sec=0.4, frequency_hz=440.0, amplitude=0.9)
    existing = WorkbenchCueMetadata()
    with patch(
        "src.workbench_auto_metadata.suggest_attack_ms",
        return_value=AttackSuggestion(
            attack_ms=42,
            method="energy_threshold",
            confidence="high",
            reason="test",
        ),
    ):
        result = apply_auto_oneshot_metadata(existing, wav, duration_ms=400)
    assert result is not None
    assert result.attack_ms == 42
    assert result.cue_start_ms == 42
    assert result.cue_source == "detected"


def test_apply_auto_oneshot_metadata_preserves_existing_attack(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "shot.wav", duration_sec=0.4, frequency_hz=440.0)
    existing = WorkbenchCueMetadata(attack_ms=99, cue_source="manual")
    assert apply_auto_oneshot_metadata(existing, wav, duration_ms=400) is None


def test_apply_auto_oneshot_metadata_preserves_manual_cue(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "shot.wav", duration_sec=0.4, frequency_hz=440.0)
    existing = WorkbenchCueMetadata(
        cue_start_ms=120,
        cue_source="manual",
        cue_updated_at="2026-01-01T00:00:00+00:00",
    )
    with patch(
        "src.workbench_auto_metadata.suggest_attack_ms",
        return_value=AttackSuggestion(
            attack_ms=42,
            method="energy_threshold",
            confidence="high",
            reason="test",
        ),
    ):
        result = apply_auto_oneshot_metadata(existing, wav, duration_ms=400)
    assert result is not None
    assert result.attack_ms == 42
    assert result.cue_start_ms == 120
    assert result.cue_source == "manual"


def test_apply_auto_oneshot_metadata_skips_low_confidence(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "shot.wav", duration_sec=0.4, frequency_hz=440.0)
    existing = WorkbenchCueMetadata()
    with patch(
        "src.workbench_auto_metadata.suggest_attack_ms",
        return_value=AttackSuggestion(
            attack_ms=0,
            method="energy_threshold",
            confidence="low",
            reason="uncertain",
        ),
    ):
        assert apply_auto_oneshot_metadata(existing, wav, duration_ms=400) is None


def test_apply_auto_oneshot_metadata_skips_none_suggestion(tmp_path: Path):
    wav = tmp_path / "missing.wav"
    existing = WorkbenchCueMetadata()
    with patch("src.workbench_auto_metadata.suggest_attack_ms", return_value=None):
        assert apply_auto_oneshot_metadata(existing, wav, duration_ms=400) is None


def test_should_skip_auto_metadata_for_catalog_row():
    row = _row(catalog_readonly=True)
    assert should_skip_auto_metadata(row)
    assert is_catalog_readonly_row(row)


def test_apply_auto_metadata_after_analyze_loop_integration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    wav = write_sine_wav(tmp_path / "loopish.wav", duration_sec=2.0, frequency_hz=220.0)
    monkeypatch.setattr(
        "src.workbench_controller.rule_type",
        lambda *_args, **_kwargs: ["Drone"],
    )
    analyze_folder_for_workbench(tmp_path, limit=1)
    row = _row(pred_type="Loop", sample_class="loop", duration_sec=2.0, path=str(wav.resolve()))
    saved = apply_auto_metadata_after_analyze(row)
    assert saved is not None
    loaded = load_workbench_sample_cue(wav)
    assert loaded.loop_start_ms == 0
    assert loaded.loop_end_ms == 2000


def test_apply_auto_metadata_after_analyze_non_loop_unchanged(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.5, frequency_hz=440.0)
    row = _row(pred_type="Snare", sample_class="oneshot", duration_sec=0.5, path=str(wav.resolve()))
    analyze_folder_for_workbench(tmp_path, limit=1)
    apply_auto_metadata_after_analyze(row)
    loaded = load_workbench_sample_cue(wav)
    assert loaded.loop_start_ms is None
    assert loaded.loop_end_ms is None


def test_apply_auto_metadata_after_analyze_preserves_existing_loop(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "loop.wav", duration_sec=2.0, frequency_hz=220.0)
    row = _row(pred_type="Loop", sample_class="loop", duration_sec=2.0, path=str(wav.resolve()))
    analyze_folder_for_workbench(tmp_path, limit=1)
    save_workbench_sample_cue(
        wav,
        WorkbenchCueMetadata(loop_start_ms=100, loop_end_ms=800, cue_source="manual"),
        duration_ms=2000,
    )
    saved = apply_auto_metadata_after_analyze(row)
    assert saved is None
    loaded = load_workbench_sample_cue(wav)
    assert loaded.loop_start_ms == 100
    assert loaded.loop_end_ms == 800


def test_analyze_folder_applies_auto_loop_for_loop_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    wav = write_sine_wav(tmp_path / "loop.wav", duration_sec=1.5, frequency_hz=200.0)
    monkeypatch.setattr(
        "src.workbench_controller.rule_type",
        lambda *_args, **_kwargs: ["Loop"],
    )
    result = analyze_folder_for_workbench(tmp_path)
    assert len(result.rows) == 1
    cue = load_workbench_sample_cue(wav)
    assert cue.loop_start_ms == 0
    assert cue.loop_end_ms == 1500


def test_analyze_folder_applies_auto_oneshot_attack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    wav = write_sine_wav(tmp_path / "shot.wav", duration_sec=0.4, frequency_hz=440.0, amplitude=0.9)
    monkeypatch.setattr(
        "src.workbench_controller.rule_type",
        lambda *_args, **_kwargs: ["OneShot"],
    )
    result = analyze_folder_for_workbench(tmp_path)
    assert len(result.rows) == 1
    cue = load_workbench_sample_cue(wav)
    assert cue.attack_ms is not None
    assert cue.cue_source == "detected"


def test_analyze_folder_does_not_overwrite_manual_loop_on_reanalyze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    wav = write_sine_wav(tmp_path / "loop.wav", duration_sec=1.5, frequency_hz=200.0)
    monkeypatch.setattr(
        "src.workbench_controller.rule_type",
        lambda *_args, **_kwargs: ["Loop"],
    )
    analyze_folder_for_workbench(tmp_path)
    save_workbench_sample_cue(
        wav,
        WorkbenchCueMetadata(loop_start_ms=200, loop_end_ms=900, cue_source="manual"),
        duration_ms=1500,
    )
    analyze_folder_for_workbench(tmp_path)
    cue = load_workbench_sample_cue(wav)
    assert cue.loop_start_ms == 200
    assert cue.loop_end_ms == 900


def test_catalog_readonly_row_never_written_via_apply(tmp_path: Path):
    row = _row(catalog_readonly=True, path=str(tmp_path / "x.wav"))
    assert apply_auto_metadata_after_analyze(row) is None


def test_short_silent_wav_does_not_crash_auto_oneshot(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "silent.wav", duration_sec=0.05, frequency_hz=440.0, amplitude=0.0)
    row = _row(pred_type="OneShot", sample_class="oneshot", duration_sec=0.05, path=str(wav.resolve()))
    analyze_folder_for_workbench(tmp_path, limit=1)
    apply_auto_metadata_after_analyze(row)


def test_workbench_library_db_not_touched_for_unknown_sample(tmp_path: Path):
    row = _row(pred_type="Loop", sample_class="loop", path=str(tmp_path / "ghost.wav"))
    assert apply_auto_metadata_after_analyze(row) is None
    assert not workbench_library_db_path().exists() or load_workbench_sample_cue(
        tmp_path / "ghost.wav"
    ).loop_start_ms is None
