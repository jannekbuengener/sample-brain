from __future__ import annotations

import sys

import pytest

from src.cli import _COMMAND_EXAMPLES, main


HELP_CASES = [
    pytest.param(["sample-brain", "init", "--help"], ("init",), id="init-help"),
    pytest.param(["sample-brain", "scan", "--help"], ("scan",), id="scan-help"),
    pytest.param(["sample-brain", "analyze", "--help"], ("analyze",), id="analyze-help"),
    pytest.param(
        ["sample-brain", "context", "analyze", "--help"],
        ("context", "analyze"),
        id="context-analyze-help",
    ),
    pytest.param(
        ["sample-brain", "pond5", "prepare", "--help"],
        ("pond5", "prepare"),
        id="pond5-prepare-help",
    ),
    pytest.param(
        ["sample-brain", "deconstruct", "--help"],
        ("deconstruct",),
        id="deconstruct-help",
    ),
    pytest.param(["sample-brain", "autotype", "--help"], ("autotype",), id="autotype-help"),
    pytest.param(["sample-brain", "export_fl", "--help"], ("export_fl",), id="export-fl-help"),
    pytest.param(["sample-brain", "match", "--help"], ("match",), id="match-help"),
    pytest.param(["sample-brain", "embed", "--help"], ("embed",), id="embed-help"),
    pytest.param(
        ["sample-brain", "index_build", "--help"],
        ("index_build",),
        id="index-build-help",
    ),
    pytest.param(["sample-brain", "search", "--help"], ("search",), id="search-help"),
    pytest.param(
        ["sample-brain", "db", "doctor", "--help"],
        ("db", "doctor"),
        id="db-doctor-help",
    ),
    pytest.param(
        ["sample-brain", "vec", "status", "--help"],
        ("vec", "status"),
        id="vec-status-help",
    ),
    pytest.param(
        ["sample-brain", "vec", "smoke", "--help"],
        ("vec", "smoke"),
        id="vec-smoke-help",
    ),
    pytest.param(
        ["sample-brain", "pack-import", "--help"],
        ("pack-import",),
        id="pack-import-help",
    ),
]


MISSING_ARG_CASES = [
    pytest.param(
        ["sample-brain", "context", "analyze"],
        ("context", "analyze"),
        2,
        id="context-analyze-missing-path",
    ),
    pytest.param(
        ["sample-brain", "pond5", "prepare"],
        ("pond5", "prepare"),
        2,
        id="pond5-prepare-missing-args",
    ),
    pytest.param(
        ["sample-brain", "deconstruct"],
        ("deconstruct",),
        2,
        id="deconstruct-missing-args",
    ),
    pytest.param(
        ["sample-brain", "match"],
        ("match",),
        2,
        id="match-missing-target-bpm",
    ),
    pytest.param(
        ["sample-brain", "pack-import"],
        ("pack-import",),
        2,
        id="pack-import-missing-pack-root",
    ),
]


@pytest.mark.parametrize("argv,cmd_path", HELP_CASES)
def test_agent_cli_help_includes_examples(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    cmd_path: tuple[str, ...],
) -> None:
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "Examples:" in out
    assert _COMMAND_EXAMPLES[cmd_path][0] in out


@pytest.mark.parametrize("argv,cmd_path,expected_exit", MISSING_ARG_CASES)
def test_agent_cli_missing_required_args_are_actionable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    cmd_path: tuple[str, ...],
    expected_exit: int,
) -> None:
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == expected_exit
    err = capsys.readouterr().err
    assert "required" in err.lower() or "Error:" in err
    assert "Examples:" in err
    assert _COMMAND_EXAMPLES[cmd_path][0] in err


def test_search_missing_model_id_shows_examples(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["sample-brain", "search"])
    main()
    out = capsys.readouterr().out
    assert "search requires --model-id" in out
    assert "Examples:" in out
    assert _COMMAND_EXAMPLES[("search",)][0] in out


def test_search_missing_query_shows_examples(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["sample-brain", "search", "--model-id", "1"])
    main()
    out = capsys.readouterr().out
    assert "search requires a text query or --query-audio." in out
    assert "Examples:" in out
    assert 'sample-brain search "snare" --model-id 1' in out
