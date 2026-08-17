from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.audio_fixtures import write_kick_transient_wav, write_sine_wav

from src.deconstruct import (
    STEP_ORDER,
    DeconstructAdapters,
    RunResult,
    StepContext,
    StepResult,
    run_deconstruct,
)


@pytest.fixture
def track_file(tmp_path):
    return write_sine_wav(tmp_path / "t.wav", duration_sec=1.0, frequency_hz=220)


def _abs_pattern(text: str) -> bool:
    """True when the text contains an absolute path (drive/root/file://)."""
    if "file://" in text:
        return True
    for token in text.split('"'):
        t = token.strip()
        if t.startswith("/"):
            return True
        if len(t) >= 3 and t[1] == ":" and t[2] in ("/", "\\"):
            return True
    return False


def _ok(step_id, required, refs=("analysis/track_map.json",), payload=None):
    return (
        StepResult(
            step_id=step_id,
            required=required,
            status="ok",
            output_refs=tuple(refs),
        ),
        payload if payload is not None else {"step": step_id},
    )


def _failed(step_id, required, code="FAIL", message="boom"):
    return (
        StepResult(
            step_id=step_id,
            required=required,
            status="failed",
            error={"code": code, "message": message},
        ),
        None,
    )


def _no_result(step_id, required, reason="NO_RESULT"):
    return (
        StepResult(
            step_id=step_id,
            required=required,
            status="no_result",
            reason_code=reason,
        ),
        None,
    )


def _not_run(step_id, required, reason="NOT_RUN"):
    return (
        StepResult(
            step_id=step_id,
            required=required,
            status="not_run",
            reason_code=reason,
        ),
        None,
    )


def test_steps_run_in_defined_order(track_file, tmp_path):
    calls = []

    def make(step_id, required):
        def adapter(ctx: StepContext):
            calls.append(step_id)
            return _ok(step_id, required)

        return adapter

    adapters = DeconstructAdapters(
        track_map=make("track_map", True),
        arrangement=make("arrangement", False),
        stems=make("stems", False),
        assets=make("assets", False),
    )
    run = run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    assert calls == ["track_map", "arrangement", "stems", "assets"]
    assert [s.step_id for s in run.steps] == [s[0] for s in STEP_ORDER]


def test_orchestrator_delegates_to_injected_adapters(track_file, tmp_path):
    used = {}

    def make(step_id, required):
        def adapter(ctx: StepContext):
            used[step_id] = True
            return _ok(step_id, required)

        return adapter

    adapters = DeconstructAdapters(
        track_map=make("track_map", True),
        arrangement=make("arrangement", False),
        assets=make("assets", False),
        stems=make("stems", False),
    )
    run = run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    assert set(used) == {"track_map", "arrangement", "assets", "stems"}
    assert run.status == "complete"


def test_required_track_map_success_allows_continuation(track_file, tmp_path):
    adapters = DeconstructAdapters(
        track_map=lambda c: _ok("track_map", True),
        arrangement=lambda c: _ok("arrangement", False),
        assets=lambda c: _ok("assets", False),
        stems=lambda c: _ok("stems", False),
    )
    run = run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    assert run.status == "complete"
    assert all(s.status == "ok" for s in run.steps)


def test_required_track_map_failure_yields_overall_failed(track_file, tmp_path):
    calls = []

    def track_map(c):
        return _failed("track_map", True, code="AUDIO_LOAD_FAILED")

    def spy(step_id):
        def adapter(c):
            calls.append(step_id)
            return _ok(step_id, False)

        return adapter

    adapters = DeconstructAdapters(
        track_map=track_map,
        arrangement=spy("arrangement"),
        assets=spy("assets"),
        stems=spy("stems"),
    )
    run = run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    assert run.status == "failed"
    assert run.steps[0].status == "failed"
    # No fake success: following steps must not run and must not be "ok".
    assert calls == []
    assert all(s.status == "not_run" for s in run.steps[1:])
    assert all(
        s.reason_code == "SKIPPED_REQUIRED_STEP_FAILED" for s in run.steps[1:]
    )


def test_optional_arrangement_failure_is_partial_not_crash(track_file, tmp_path):
    adapters = DeconstructAdapters(
        track_map=lambda c: _ok("track_map", True),
        arrangement=lambda c: _failed("arrangement", False, code="ARR_FAIL"),
        assets=lambda c: _ok("assets", False),
        stems=lambda c: _ok("stems", False),
    )
    run = run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    assert run.status == "partial"
    assert run.steps[0].status == "ok"
    assert run.steps[1].status == "failed"
    assert run.steps[2].status == "ok"


def test_optional_assets_no_result_keeps_run_usable(track_file, tmp_path):
    adapters = DeconstructAdapters(
        track_map=lambda c: _ok("track_map", True),
        arrangement=lambda c: _ok("arrangement", False),
        stems=lambda c: _ok("stems", False),
        assets=lambda c: _no_result("assets", False, reason="INSUFFICIENT_DOWNBEATS"),
    )
    run = run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    assert run.status == "partial"
    assert run.steps[3].status == "no_result"


def test_missing_stems_not_run_and_no_overall_error(track_file, tmp_path):
    adapters = DeconstructAdapters(
        track_map=lambda c: _ok("track_map", True),
        arrangement=lambda c: _ok("arrangement", False),
        assets=lambda c: _ok("assets", False),
        # stems intentionally omitted -> default adapter reports not_run
    )
    run = run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    assert run.status == "complete"
    assert run.steps[2].step_id == "stems"
    assert run.steps[2].status == "not_run"


def test_step_results_passed_forward(track_file, tmp_path):
    received = {}

    def arrangement(c):
        return _ok("arrangement", False, payload={"structure": "STUB"})

    def assets(c):
        received["arrangement"] = c.artifacts.get("arrangement")
        return _ok("assets", False)

    adapters = DeconstructAdapters(
        track_map=lambda c: _ok("track_map", True),
        arrangement=arrangement,
        assets=assets,
        stems=lambda c: _ok("stems", False),
    )
    run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    assert received["arrangement"] == {"structure": "STUB"}


def test_no_step_executed_twice(track_file, tmp_path):
    counts = {}

    def make(step_id, required):
        def adapter(c):
            counts[step_id] = counts.get(step_id, 0) + 1
            return _ok(step_id, required)

        return adapter

    adapters = DeconstructAdapters(
        track_map=make("track_map", True),
        arrangement=make("arrangement", False),
        assets=make("assets", False),
        stems=make("stems", False),
    )
    run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    assert all(v == 1 for v in counts.values())


def test_pack_root_follows_layout_prefixes(track_file, tmp_path):
    adapters = DeconstructAdapters(
        track_map=lambda c: _ok(
            "track_map", True, refs=("analysis/track_map.json",)
        ),
        arrangement=lambda c: _ok(
            "arrangement", False, refs=("analysis/arrangement_map.json",)
        ),
        assets=lambda c: _ok(
            "assets",
            False,
            refs=("loops/loop_x.json", "sections/section_x.json"),
        ),
        stems=lambda c: _not_run("stems", False, reason="STEMS_NOT_CONFIGURED"),
    )
    run = run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    ref_map = {s.step_id: s.output_refs for s in run.steps}
    assert ref_map["track_map"] == ("analysis/track_map.json",)
    assert ref_map["arrangement"] == ("analysis/arrangement_map.json",)
    assert ref_map["assets"][0].startswith("loops/")
    assert ref_map["assets"][1].startswith("sections/")


def test_output_refs_are_portable_relative(track_file, tmp_path):
    adapters = DeconstructAdapters(
        track_map=lambda c: _ok(
            "track_map", True, refs=("analysis/track_map.json",)
        ),
        arrangement=lambda c: _ok("arrangement", False),
        assets=lambda c: _ok("assets", False, refs=("loops/loop_x.json",)),
        stems=lambda c: _not_run("stems", False),
    )
    run = run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    for step in run.steps:
        for ref in step.output_refs:
            assert not ref.startswith("/")
            assert ".." not in ref
            assert ":" not in ref.replace("://", "")


def test_serialized_run_has_no_absolute_paths(track_file, tmp_path):
    adapters = DeconstructAdapters(
        track_map=lambda c: _ok("track_map", True),
        arrangement=lambda c: _ok("arrangement", False),
        assets=lambda c: _ok("assets", False, refs=("loops/loop_x.json",)),
        stems=lambda c: _not_run("stems", False),
    )
    run = run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    text = json.dumps(run.to_dict(), default=str)
    assert not _abs_pattern(text)


def test_original_input_not_mutated(track_file, tmp_path):
    before = track_file.read_bytes()

    def arrangement(c):
        return _ok("arrangement", False)

    def assets(c):
        return _ok("assets", False)

    adapters = DeconstructAdapters(
        track_map=lambda c: _ok("track_map", True),
        arrangement=arrangement,
        assets=assets,
        stems=lambda c: _not_run("stems", False),
    )
    run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    after = track_file.read_bytes()
    assert before == after


def test_deterministic_run_with_same_inputs_and_adapters(track_file, tmp_path):
    adapters = DeconstructAdapters(
        track_map=lambda c: _ok("track_map", True),
        arrangement=lambda c: _ok("arrangement", False),
        assets=lambda c: _no_result("assets", False, reason="INSUFFICIENT_DOWNBEATS"),
        stems=lambda c: _not_run("stems", False),
    )
    run1 = run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    run2 = run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    assert json.dumps(run1.to_dict(), sort_keys=True, default=str) == json.dumps(
        run2.to_dict(), sort_keys=True, default=str
    )


def test_skipped_optional_step_reports_not_run(track_file, tmp_path):
    adapters = DeconstructAdapters(
        track_map=lambda c: _ok("track_map", True),
        arrangement=lambda c: _ok("arrangement", False),
        assets=lambda c: _ok("assets", False),
        stems=lambda c: _ok("stems", False),
    )
    run = run_deconstruct(
        track_file, tmp_path / "pack", adapters=adapters, skip={"arrangement", "stems"}
    )
    by_id = {s.step_id: s for s in run.steps}
    assert by_id["arrangement"].status == "not_run"
    assert by_id["arrangement"].reason_code == "SKIPPED_BY_REQUEST"
    assert by_id["stems"].status == "not_run"
    assert by_id["assets"].status == "ok"
    assert run.status == "complete"


def test_track_identity_present_even_on_failure(track_file, tmp_path):
    adapters = DeconstructAdapters(
        track_map=lambda c: _failed("track_map", True, code="AUDIO_LOAD_FAILED"),
    )
    run = run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    assert run.track["file_name"] == track_file.name
    assert run.track["hash"]["algorithm"] == "sha1"
    assert run.track["hash"]["value"]


def test_run_result_is_runresult_instance(track_file, tmp_path):
    adapters = DeconstructAdapters(
        track_map=lambda c: _ok("track_map", True),
        arrangement=lambda c: _ok("arrangement", False),
        assets=lambda c: _ok("assets", False),
        stems=lambda c: _not_run("stems", False),
    )
    run = run_deconstruct(track_file, tmp_path / "pack", adapters=adapters)
    assert isinstance(run, RunResult)


def test_real_orchestrator_runs_end_to_end(tmp_path):
    """Exercise the genuine production adapters (no mocks) on synthetic audio."""
    track = write_kick_transient_wav(tmp_path / "track.wav", bpm=120.0, duration_sec=4.0)
    pack = tmp_path / "pack"
    run = run_deconstruct(track, pack, beat_backend="librosa", skip={"stems"})
    # Must not crash; overall status is one of the valid run statuses.
    assert run.status in ("complete", "partial", "failed")
    # Track Map step always runs and writes its artifact.
    assert run.steps[0].step_id == "track_map"
    assert (pack / "analysis" / "track_map.json").exists()
    # Original input is untouched.
    assert track.exists()
    # No absolute paths leaked into the serialized run result.
    text = json.dumps(run.to_dict(), default=str)
    assert not _abs_pattern(text)
