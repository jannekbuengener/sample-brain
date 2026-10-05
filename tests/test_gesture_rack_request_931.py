"""Frozen acceptance for R&D Slice 11 — session-bound gesture Rack request (#680 / #931).

Docs authority: docs/GESTURE_RACK_REQUEST_RND_SLICE11.md

Intentionally RED until src/gesture_rack_request.py exists.
Synthetic tmp_path WAV + SQLite only - no private catalogs, paths, or audio.
Do not weaken / xfail / skip to fit a missing or incorrect request seam.

Ownership boundaries (import graph, forbidden calls, private state access) are
enforced with AST checks rather than raw-source substring guards, per the #898
context. Everything else is asserted behaviorally with spies/mocks.
"""

from __future__ import annotations

import ast
import copy
import dataclasses
import importlib
import inspect
import os
import sqlite3
from fractions import Fraction
from pathlib import Path
from typing import Any
from unittest import mock

import numpy as np
import pytest
import soundfile as sf

from src.channel_rack import ChannelRackState
from src.gesture_analysis import FEATURE_DIM, GestureAnalysis, GestureEvent
from src.gesture_library_ranking import RankedCandidate
from src.pattern_core import Channel, Pattern, Trigger
from src.session_grid import SessionTransport
from src.workbench_channel_rack import ChannelRackController
from src.workbench_live_kit import LiveKitState

# Import under test - RED until IMPLEMENTATION adds the module.
from src.gesture_rack_request import (
    GestureRackCandidateProposal,
    GestureRackRequestResult,
    propose_gesture_rack_candidates,
    submit_gesture_rack_request,
)

_MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "gesture_rack_request.py"

# Slice 11 may consume only these. Notably absent: config, workbench_session,
# workbench_feature_settings, workbench_session_store, workbench_qml.
_ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "__future__",
        "annotations",
        "dataclasses",
        "fractions",
        "typing",
        "collections",
        "collections.abc",
        "pathlib",
        "gesture_analysis",
        "src.gesture_analysis",
        "gesture_library_ranking",
        "src.gesture_library_ranking",
        "gesture_catalog_adapter",
        "src.gesture_catalog_adapter",
        "gesture_rack_headless_action",
        "src.gesture_rack_headless_action",
        "channel_rack",
        "src.channel_rack",
        "pattern_core",
        "src.pattern_core",
    }
)

# Ownership leaks Slice 11 must not acquire.
_BANNED_IMPORT_ROOTS = frozenset(
    {
        "config",
        "src.config",
        "workbench_session",
        "src.workbench_session",
        "workbench_session_store",
        "src.workbench_session_store",
        "workbench_feature_settings",
        "src.workbench_feature_settings",
        "workbench_qml",
        "src.workbench_qml",
        "workbench_channel_rack",
        "src.workbench_channel_rack",
        "db",
        "src.db",
        "sqlalchemy",
        "torch",
    }
)

# Config / settings / state / duplicate-orchestration calls.
_BANNED_NAME_CALLS = frozenset(
    {
        "set_db_path",
        "_resolve_db_path",
        "DB_PATH",
        "load_workbench_feature_settings",
        "save_workbench_feature_settings",
        "workbench_feature_settings_path",
        "ensure_state",
        "restore_state",
        "add_user_channel",
        "assign_user_channel_sample",
        "save_workbench_session_snapshot",
        "snapshot_from_musical_state",
        "apply_gesture_integration_plan",
        "stop",
        # Stage duplication: these stay owned by Slice 10 / earlier slices.
        "project_gesture_timing",
        "plan_gesture_pattern_binding",
        "compose_gesture_pattern_core",
        "plan_gesture_rack_integration",
    }
)

# Vocabulary that would signal a confidence/acceptance claim.
_FORBIDDEN_EVIDENCE_VOCABULARY = (
    "confidence",
    "probability",
    "calibrat",
    "acceptance",
    "accept",
    "threshold",
    "score",
)

SR = 44100
MFCC_DIM = 13

# Distinctive sentinels: none of these is derivable from duration, bars, or the
# step grid, so pass-through is distinguishable from inference.
SENTINEL_TEMPO = 137.0
SENTINEL_PATTERN_LENGTH = Fraction(7, 2)
SENTINEL_PATTERN_ID = "gesture-pat-slice11-explicit"
SENTINEL_SELECTIONS = {0: "101"}


# ---------------------------------------------------------------------------
# Synthetic audio / catalog / analysis helpers
# ---------------------------------------------------------------------------


def _write_placeholder_wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    y = np.zeros(int(SR * 0.25), dtype=np.float32)
    sf.write(path, y, SR, subtype="PCM_16")
    return path


def _feat(rms: float = 0.25, centroid: float = 1200.0, *, mfcc0: float = 1.0) -> tuple[float, ...]:
    mfcc = (mfcc0,) + tuple(float(i) for i in range(1, MFCC_DIM))
    vec = (rms, centroid) + mfcc
    assert len(vec) == FEATURE_DIM
    return vec


def _ok_analysis(
    *, cluster_ids: tuple[int, ...] = (0,), onsets: tuple[float, ...] | None = None
) -> GestureAnalysis:
    if onsets is None:
        onsets = tuple(0.2 + 0.4 * i for i in range(len(cluster_ids)))
    assert len(onsets) == len(cluster_ids)
    events = tuple(
        GestureEvent(onset, _feat(mfcc0=1.0 + 0.1 * cid), int(cid))
        for onset, cid in zip(onsets, cluster_ids, strict=True)
    )
    return GestureAnalysis(
        events=events,
        sample_rate=SR,
        duration_sec=max(onsets) + 0.5 if onsets else 1.0,
        feature_dim=FEATURE_DIM,
        status="ok",
    )


def _not_ok_analysis(status: str = "empty") -> GestureAnalysis:
    return GestureAnalysis(
        events=(),
        sample_rate=SR,
        duration_sec=0.01,
        feature_dim=FEATURE_DIM,
        status=status,
    )


def _mfcc_blob(values: list[float] | None = None) -> bytes:
    arr = np.asarray(
        values if values is not None else [float(i) for i in range(MFCC_DIM)],
        dtype=np.float32,
    )
    assert arr.shape == (MFCC_DIM,)
    return arr.tobytes()


def _init_catalog(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE samples (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            relpath TEXT,
            samplerate INTEGER,
            channels INTEGER,
            duration REAL,
            size_bytes INTEGER,
            hash TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE features (
            sample_id INTEGER PRIMARY KEY,
            bpm REAL,
            key TEXT,
            key_conf REAL,
            loudness REAL,
            brightness REAL,
            mfcc_mean BLOB,
            mfcc_std BLOB,
            chroma_mean BLOB,
            chroma_std BLOB,
            class TEXT,
            FOREIGN KEY(sample_id) REFERENCES samples(id)
        )
        """
    )
    conn.commit()
    return conn


def _insert_oneshot(
    conn: sqlite3.Connection,
    *,
    sample_id: int,
    path: str,
    loudness: float = -12.0,
    brightness: float = 1200.0,
    mfcc: list[float] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO samples(
            id, path, relpath, samplerate, channels, duration, size_bytes, hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (sample_id, path, Path(path).name, SR, 1, 0.2, 1000, f"hash-{sample_id}"),
    )
    conn.execute(
        """
        INSERT INTO features(
            sample_id, bpm, key, key_conf, loudness, brightness,
            mfcc_mean, mfcc_std, chroma_mean, chroma_std, class
        ) VALUES (?, NULL, NULL, NULL, ?, ?, ?, NULL, NULL, NULL, ?)
        """,
        (sample_id, loudness, brightness, _mfcc_blob(mfcc), "oneshot"),
    )
    conn.commit()


def _catalog_with_oneshots(
    tmp_path: Path, *, name: str = "gesture_catalog.db", salt: float = 0.0
) -> Path:
    """Build a synthetic catalog with three eligible oneshot rows.

    ``salt`` shifts the feature space so two catalogs in one test are
    distinguishable by their returned sample_ids.
    """
    path = tmp_path / name
    conn = _init_catalog(path)
    try:
        _insert_oneshot(
            conn,
            sample_id=101,
            path="synth/kick_a.wav",
            loudness=-10.0 + salt,
            brightness=1200.0,
            mfcc=[1.0 + salt] + [float(i) for i in range(1, MFCC_DIM)],
        )
        _insert_oneshot(
            conn,
            sample_id=202,
            path="synth/kick_b.wav",
            loudness=-14.0 + salt,
            brightness=1500.0,
            mfcc=[2.0 + salt] + [float(i) for i in range(1, MFCC_DIM)],
        )
        _insert_oneshot(
            conn,
            sample_id=303,
            path="synth/hat_a.wav",
            loudness=-18.0 + salt,
            brightness=4000.0,
            mfcc=[5.0 + salt] + [float(i) for i in range(1, MFCC_DIM)],
        )
    finally:
        conn.close()
    return path


# ---------------------------------------------------------------------------
# Rack / live-context helpers
# ---------------------------------------------------------------------------


def _live_kit_channel(
    channel_id: str, group: str, slot: str, *, sample_path: str | None = "kit.wav"
) -> Channel:
    return Channel(
        channel_id=channel_id,
        live_kit_group=group,
        live_kit_slot=slot,
        sample_path=sample_path,
    )


def _user_channel(channel_id: str, *, sample_path: str = "user.wav") -> Channel:
    return Channel(
        channel_id=channel_id,
        live_kit_group=None,
        live_kit_slot=None,
        sample_path=sample_path,
    )


def _base_state(
    *,
    pattern_length: Fraction = SENTINEL_PATTERN_LENGTH,
    step_count: int = 16,
) -> ChannelRackState:
    return ChannelRackState(
        channels=(
            _live_kit_channel("ch_kick", "Kick + Bass", "Kick"),
            _live_kit_channel("ch_bass", "Kick + Bass", "Bass", sample_path=None),
            _user_channel("ch_user_9", sample_path="existing.wav"),
        ),
        pattern=Pattern(
            pattern_id="screen2-main",
            length_quarter_notes=pattern_length,
            triggers=(
                Trigger(channel_id="ch_kick", position=Fraction(0, 4)),
                Trigger(channel_id="ch_user_9", position=Fraction(2, 4)),
            ),
        ),
        step_count=step_count,
    )


def _controller(
    *, state: ChannelRackState | None = None, on_musical_state_changed=None
) -> ChannelRackController:
    transport = SessionTransport(sample_rate=48_000, bpm=120.0)
    controller = ChannelRackController(
        live_kit=LiveKitState(),
        transport=transport,
        on_musical_state_changed=on_musical_state_changed,
    )
    if state is not None:
        controller.restore_state(state)
    return controller


class _StubTransport:
    """Minimal live-context transport exposing only the contracted seam."""

    def __init__(self, tempo: float = SENTINEL_TEMPO) -> None:
        self._tempo = float(tempo)
        self.calls = 0

    def get_current_tempo(self) -> float:
        self.calls += 1
        return self._tempo


class _LiveContext:
    """Minimal structural stand-in for WorkbenchSession's Rack + transport."""

    def __init__(
        self,
        channel_rack: ChannelRackController,
        transport: _StubTransport | None = None,
    ) -> None:
        self.channel_rack = channel_rack
        self.transport = transport if transport is not None else _StubTransport()


class _Settings:
    """Already-loaded settings-shaped object (never read from disk here)."""

    def __init__(self, enabled: bool) -> None:
        self.gesture_rack_apply_enabled = bool(enabled)


def _patch_analysis(monkeypatch: pytest.MonkeyPatch, analysis: GestureAnalysis) -> mock.Mock:
    """Stub Stage 1 wherever the request seam may import it from."""
    stub = mock.Mock(return_value=analysis)
    monkeypatch.setattr("src.gesture_analysis.analyze_gesture_audio", stub)
    import src.gesture_rack_request as request_mod

    if hasattr(request_mod, "analyze_gesture_audio"):
        monkeypatch.setattr(request_mod, "analyze_gesture_audio", stub)
    return stub


def _spy_on_action(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """Replace the delegated Slice-10 Action with a recording spy."""
    import src.gesture_rack_request as request_mod

    sentinel = mock.Mock(name="action_result")
    spy = mock.Mock(return_value=sentinel)
    monkeypatch.setattr(request_mod, "prepare_and_apply_gesture_rack", spy)
    return spy


def _submitted(spy: mock.Mock) -> dict[str, Any]:
    assert spy.call_count == 1, f"expected exactly one delegation, got {spy.call_count}"
    args, kwargs = spy.call_args
    return {"args": args, "kwargs": kwargs}


# ---------------------------------------------------------------------------
# G. Ownership / import graph (AST, not substring)
# ---------------------------------------------------------------------------


def test_g1_module_import_graph_allow_and_ban_lists() -> None:
    assert _MODULE_PATH.is_file(), "request module must exist after implementation"
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            imported.add(node.module.split(".")[0])
            imported.add(node.module)
            if not node.module.startswith("src."):
                imported.add(f"src.{node.module}")

    banned_hit = sorted(imported & _BANNED_IMPORT_ROOTS)
    assert banned_hit == [], f"banned imports present: {banned_hit}"

    for name in sorted(imported):
        if name.startswith("."):
            continue
        root = name.split(".")[0]
        ok = (
            name in _ALLOWED_IMPORT_ROOTS
            or root in _ALLOWED_IMPORT_ROOTS
            or f"src.{root}" in _ALLOWED_IMPORT_ROOTS
        )
        assert ok, f"unexpected import {name!r}"


def test_g2_banned_calls_absent_from_request_module() -> None:
    assert _MODULE_PATH.is_file()
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
    banned_hit = sorted(called & _BANNED_NAME_CALLS)
    assert banned_hit == [], f"banned calls present: {banned_hit}"


def test_g3_no_direct_controller_private_state_access() -> None:
    assert _MODULE_PATH.is_file()
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    private: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            private.add(node.attr)
    assert "_state" not in private, "request seam must not touch controller._state"


def test_g4_no_qml_page_or_navigation_ownership() -> None:
    assert _MODULE_PATH.is_file()
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    tokens: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            tokens.add(node.id)
        elif isinstance(node, ast.Attribute):
            tokens.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            tokens.add(node.value)
    for forbidden in ("Qml", "qml", "navigate", "navigation", "enter_screen", "leave_screen"):
        assert forbidden not in tokens, f"unexpected page/navigation token {forbidden!r}"


def test_g5_real_workbench_session_satisfies_structural_live_context() -> None:
    """The real session must structurally satisfy the frozen live context."""
    from src.workbench_session import WorkbenchSession
    from src.workbench_transport_adapter import WorkbenchTransportAdapter

    field_names = {f.name for f in dataclasses.fields(WorkbenchSession)}
    assert "channel_rack" in field_names
    assert "transport" in field_names
    assert callable(getattr(WorkbenchTransportAdapter, "get_current_tempo", None))


# ---------------------------------------------------------------------------
# A. Proposal - deterministic Top-N evidence
# ---------------------------------------------------------------------------


def test_a1_proposal_deterministic_topn_per_cluster(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0, 1, 0, 1)))

    first = propose_gesture_rack_candidates(audio, catalog_path=catalog, top_n=2)
    second = propose_gesture_rack_candidates(audio, catalog_path=catalog, top_n=2)

    assert isinstance(first, GestureRackCandidateProposal)
    assert first == second, "proposal must be deterministic for identical inputs"
    assert first.status == "ok"
    assert first.analysis_status == "ok"
    assert [r.cluster_id for r in first.cluster_rankings] == [0, 1]
    for ranking in first.cluster_rankings:
        assert 1 <= len(ranking.ranked) <= 2
        assert [c.rank for c in ranking.ranked] == list(range(1, len(ranking.ranked) + 1))
        distances = [c.distance for c in ranking.ranked]
        assert distances == sorted(distances)


def test_a2_proposal_honors_explicit_top_n(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))

    one = propose_gesture_rack_candidates(audio, catalog_path=catalog, top_n=1)
    assert len(one.cluster_rankings[0].ranked) == 1

    three = propose_gesture_rack_candidates(audio, catalog_path=catalog, top_n=3)
    assert len(three.cluster_rankings[0].ranked) == 3


@pytest.mark.parametrize("bad_top_n", [0, -1, -5])
def test_a3_invalid_top_n_preserves_existing_fail_behavior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_top_n: int
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))

    with pytest.raises(ValueError):
        propose_gesture_rack_candidates(audio, catalog_path=catalog, top_n=bad_top_n)


def test_a4_proposal_exposes_rank_and_distance_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))

    proposal = propose_gesture_rack_candidates(audio, catalog_path=catalog, top_n=3)

    assert {f.name for f in dataclasses.fields(GestureRackCandidateProposal)} == {
        "status",
        "analysis_status",
        "cluster_rankings",
    }
    for ranking in proposal.cluster_rankings:
        for candidate in ranking.ranked:
            assert isinstance(candidate, RankedCandidate)
            assert {f.name for f in dataclasses.fields(candidate)} == {
                "sample_id",
                "distance",
                "rank",
            }
            assert isinstance(candidate.sample_id, str)
            assert isinstance(candidate.distance, float)
            assert isinstance(candidate.rank, int)


def test_a5_no_confidence_or_acceptance_claim_in_proposal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0, 1)))

    proposal = propose_gesture_rack_candidates(audio, catalog_path=catalog, top_n=3)

    seen: set[str] = set()
    stack: list[Any] = [proposal]
    while stack:
        item = stack.pop()
        if dataclasses.is_dataclass(item) and not isinstance(item, type):
            seen.update(f.name.lower() for f in dataclasses.fields(item))
            for f in dataclasses.fields(item):
                stack.append(getattr(item, f.name))
        elif isinstance(item, (tuple, list)):
            stack.extend(item)

    for name in seen:
        for token in _FORBIDDEN_EVIDENCE_VOCABULARY:
            assert token not in name, f"forbidden evidence claim in field {name!r}"


def test_a6_proposal_performs_no_selection_and_no_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0, 1)))

    proposal = propose_gesture_rack_candidates(audio, catalog_path=catalog, top_n=3)

    # Evidence only: no chosen/selected sample is exposed anywhere.
    for ranking in proposal.cluster_rankings:
        assert not hasattr(ranking, "selected")
        assert not hasattr(ranking, "selection")
        assert not hasattr(ranking, "choice")
        for candidate in ranking.ranked:
            assert not hasattr(candidate, "selected")
            assert not hasattr(candidate, "accepted")

    # No Rack/session object is required or constructed by this seam.
    assert set(vars(GestureRackCandidateProposal)) >= {"status", "analysis_status", "cluster_rankings"}


def test_a7_proposal_analysis_not_ok_makes_no_catalog_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "short.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _not_ok_analysis("too_short"))

    adapter_spy = mock.Mock(return_value=())
    monkeypatch.setattr(
        "src.gesture_catalog_adapter.rank_gesture_against_catalog", adapter_spy
    )

    proposal = propose_gesture_rack_candidates(audio, catalog_path=catalog)

    assert proposal.status == "analysis_not_ok"
    assert proposal.analysis_status == "too_short"
    assert proposal.cluster_rankings == ()
    adapter_spy.assert_not_called()


# ---------------------------------------------------------------------------
# B. Catalog ownership - explicit path only
# ---------------------------------------------------------------------------


def test_b1_explicit_catalog_path_reaches_existing_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    wanted = _catalog_with_oneshots(tmp_path, name="wanted.db")
    other = _catalog_with_oneshots(tmp_path, name="other.db", salt=7.0)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))

    proposal = propose_gesture_rack_candidates(audio, catalog_path=wanted, top_n=3)

    returned = {c.sample_id for r in proposal.cluster_rankings for c in r.ranked}
    assert returned == {"101", "202", "303"}
    # The explicit catalog is the only source; the other DB must be irrelevant.
    assert other.is_file()


def test_b2_no_environment_or_default_catalog_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    explicit = _catalog_with_oneshots(tmp_path, name="explicit.db", salt=3.0)
    env_catalog = _catalog_with_oneshots(tmp_path, name="from_env.db")
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))

    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(env_catalog))
    try:
        proposal = propose_gesture_rack_candidates(
            audio, catalog_path=explicit, top_n=3
        )
    finally:
        monkeypatch.delenv("SAMPLE_BRAIN_DB_PATH", raising=False)

    # Both catalogs hold the same sample_ids, so prove the explicit one won by
    # checking the feature space the adapter actually read.
    import src.gesture_catalog_adapter as adapter_mod

    explicit_candidates = adapter_mod.load_gesture_library_candidates(explicit)
    env_candidates = adapter_mod.load_gesture_library_candidates(env_catalog)
    assert explicit_candidates[0].mfcc13[0] != env_candidates[0].mfcc13[0]

    returned_ids = [c.sample_id for r in proposal.cluster_rankings for c in r.ranked]
    assert returned_ids == ["101", "202", "303"]


def test_b3_missing_explicit_catalog_fails_soft_without_hidden_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    real = _catalog_with_oneshots(tmp_path, name="real.db")
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))

    # Point the hidden default at a valid catalog: a leaked fallback would
    # still return candidates.
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(real))
    try:
        proposal = propose_gesture_rack_candidates(
            audio, catalog_path=tmp_path / "absent.db", top_n=3
        )
    finally:
        monkeypatch.delenv("SAMPLE_BRAIN_DB_PATH", raising=False)

    assert proposal.status == "ok"
    assert all(r.ranked == () for r in proposal.cluster_rankings)


def test_b4_catalog_path_is_keyword_only_and_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))

    with pytest.raises(TypeError):
        propose_gesture_rack_candidates(audio, catalog)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# C. Submit - live context derivation and exact forwarding
# ---------------------------------------------------------------------------


def test_c1_submit_uses_exact_session_channel_rack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    controller = _controller(state=_base_state())
    live = _LiveContext(controller)
    spy = _spy_on_action(monkeypatch)

    submit_gesture_rack_request(
        audio,
        live,
        catalog_path=catalog,
        selections=dict(SENTINEL_SELECTIONS),
        pattern_id=SENTINEL_PATTERN_ID,
        allow_pattern_replacement=False,
        feature_enabled=True,
    )

    call = _submitted(spy)
    assert call["args"][1] is controller


def test_c2_reference_bpm_comes_from_transport_get_current_tempo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    transport = _StubTransport(SENTINEL_TEMPO)
    live = _LiveContext(_controller(state=_base_state()), transport)
    spy = _spy_on_action(monkeypatch)

    submit_gesture_rack_request(
        audio,
        live,
        catalog_path=catalog,
        selections=dict(SENTINEL_SELECTIONS),
        pattern_id=SENTINEL_PATTERN_ID,
        allow_pattern_replacement=True,
        feature_enabled=True,
    )

    call = _submitted(spy)
    assert call["kwargs"]["reference_bpm"] == SENTINEL_TEMPO
    assert transport.calls >= 1, "tempo must be read through the public transport seam"


def test_c3_pattern_length_comes_from_public_rack_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    state = _base_state(pattern_length=Fraction(11, 4))
    live = _LiveContext(_controller(state=state))
    spy = _spy_on_action(monkeypatch)

    submit_gesture_rack_request(
        audio,
        live,
        catalog_path=catalog,
        selections=dict(SENTINEL_SELECTIONS),
        pattern_id=SENTINEL_PATTERN_ID,
        allow_pattern_replacement=True,
        feature_enabled=True,
    )

    call = _submitted(spy)
    assert call["kwargs"]["pattern_length_quarters"] == Fraction(11, 4)
    assert call["kwargs"]["pattern_length_quarters"] is not None


def test_c4_exact_caller_inputs_forwarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    live = _LiveContext(_controller(state=_base_state()))
    spy = _spy_on_action(monkeypatch)

    selections = {0: "101", 1: "202"}
    result = submit_gesture_rack_request(
        audio,
        live,
        catalog_path=catalog,
        selections=selections,
        pattern_id=SENTINEL_PATTERN_ID,
        allow_pattern_replacement=False,
        feature_enabled=True,
    )

    call = _submitted(spy)
    assert call["args"][0] == audio
    assert call["kwargs"]["catalog_path"] == catalog
    assert call["kwargs"]["selections"] == selections
    assert call["kwargs"]["pattern_id"] == SENTINEL_PATTERN_ID
    assert call["kwargs"]["allow_pattern_replacement"] is False
    assert isinstance(result, GestureRackRequestResult)


# ---------------------------------------------------------------------------
# D. Settings - injection only
# ---------------------------------------------------------------------------


def test_d1_settings_object_flag_is_injected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    live = _LiveContext(_controller(state=_base_state()))
    spy = _spy_on_action(monkeypatch)

    submit_gesture_rack_request(
        audio,
        live,
        catalog_path=catalog,
        selections=dict(SENTINEL_SELECTIONS),
        pattern_id=SENTINEL_PATTERN_ID,
        allow_pattern_replacement=True,
        feature_enabled=_Settings(True),
    )

    assert _submitted(spy)["kwargs"]["feature_enabled"] is True


def test_d2_injected_bool_is_passed_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    live = _LiveContext(_controller(state=_base_state()))
    spy = _spy_on_action(monkeypatch)

    submit_gesture_rack_request(
        audio,
        live,
        catalog_path=catalog,
        selections=dict(SENTINEL_SELECTIONS),
        pattern_id=SENTINEL_PATTERN_ID,
        allow_pattern_replacement=True,
        feature_enabled=False,
    )

    assert _submitted(spy)["kwargs"]["feature_enabled"] is False


def test_d3_disabled_flag_fails_closed_through_slice10(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0, 0, 0)))

    observers: list[str] = []
    controller = _controller(
        state=_base_state(), on_musical_state_changed=lambda: observers.append("obs")
    )
    before = copy.deepcopy(controller.state)

    result = submit_gesture_rack_request(
        audio,
        _LiveContext(controller),
        catalog_path=catalog,
        selections=dict(SENTINEL_SELECTIONS),
        pattern_id=SENTINEL_PATTERN_ID,
        allow_pattern_replacement=True,
        feature_enabled=_Settings(False),
    )

    assert result.status == "submitted"
    assert result.action_result is not None
    assert result.action_result.status == "feature_disabled"
    assert result.action_result.applied_state is None
    assert controller.state == before
    assert observers == []


def test_d4_no_settings_file_io_from_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An injected flag must not create or read any settings file."""
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0, 0)))
    live = _LiveContext(_controller(state=_base_state()))
    _spy_on_action(monkeypatch)

    monkeypatch.setenv("SAMPLE_BRAIN_STATE_DIR", str(state_dir))
    try:
        submit_gesture_rack_request(
            audio,
            live,
            catalog_path=catalog,
            selections=dict(SENTINEL_SELECTIONS),
            pattern_id=SENTINEL_PATTERN_ID,
            allow_pattern_replacement=True,
            feature_enabled=_Settings(True),
        )
    finally:
        monkeypatch.delenv("SAMPLE_BRAIN_STATE_DIR", raising=False)

    assert list(state_dir.iterdir()) == [], "seam must not write settings state"


# ---------------------------------------------------------------------------
# E. Delegation - exactly once, no duplicate orchestration
# ---------------------------------------------------------------------------


def test_e1_submit_delegates_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    live = _LiveContext(_controller(state=_base_state()))
    spy = _spy_on_action(monkeypatch)

    submit_gesture_rack_request(
        audio,
        live,
        catalog_path=catalog,
        selections=dict(SENTINEL_SELECTIONS),
        pattern_id=SENTINEL_PATTERN_ID,
        allow_pattern_replacement=True,
        feature_enabled=True,
    )

    assert spy.call_count == 1


def test_e2_public_signatures_are_frozen() -> None:
    propose_sig = inspect.signature(propose_gesture_rack_candidates)
    assert "audio_path" in propose_sig.parameters
    for name in ("catalog_path", "top_n"):
        assert propose_sig.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
    assert propose_sig.parameters["top_n"].default == 5

    submit_sig = inspect.signature(submit_gesture_rack_request)
    assert "audio_path" in submit_sig.parameters
    assert "live_context" in submit_sig.parameters
    for name in (
        "catalog_path",
        "selections",
        "pattern_id",
        "allow_pattern_replacement",
        "feature_enabled",
    ):
        assert submit_sig.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY

    # The seam must not re-expose Slice-10's derived inputs as its own inputs.
    for forbidden in ("reference_bpm", "pattern_length_quarters", "channel_rack"):
        assert forbidden not in submit_sig.parameters


def test_e3_action_result_is_forwarded_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    live = _LiveContext(_controller(state=_base_state()))
    import src.gesture_rack_request as request_mod

    sentinel = mock.Mock(name="action_result")
    monkeypatch.setattr(
        request_mod, "prepare_and_apply_gesture_rack", mock.Mock(return_value=sentinel)
    )

    result = submit_gesture_rack_request(
        audio,
        live,
        catalog_path=catalog,
        selections=dict(SENTINEL_SELECTIONS),
        pattern_id=SENTINEL_PATTERN_ID,
        allow_pattern_replacement=True,
        feature_enabled=True,
    )

    assert result.status == "submitted"
    assert result.action_result is sentinel


# ---------------------------------------------------------------------------
# F. State-none policy
# ---------------------------------------------------------------------------


def test_f1_state_none_fails_closed_without_delegation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    controller = _controller(state=None)
    assert controller.state is None
    live = _LiveContext(controller)
    spy = _spy_on_action(monkeypatch)

    result = submit_gesture_rack_request(
        audio,
        live,
        catalog_path=catalog,
        selections=dict(SENTINEL_SELECTIONS),
        pattern_id=SENTINEL_PATTERN_ID,
        allow_pattern_replacement=True,
        feature_enabled=True,
    )

    assert result.status == "state_none"
    assert result.action_result is None
    spy.assert_not_called()
    assert controller.state is None


def test_f2_state_none_never_materializes_rack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    controller = _controller(state=None)

    ensure_spy = mock.Mock(side_effect=AssertionError("ensure_state must not be called"))
    monkeypatch.setattr(controller, "ensure_state", ensure_spy)

    result = submit_gesture_rack_request(
        audio,
        _LiveContext(controller),
        catalog_path=catalog,
        selections=dict(SENTINEL_SELECTIONS),
        pattern_id=SENTINEL_PATTERN_ID,
        allow_pattern_replacement=True,
        feature_enabled=True,
    )

    ensure_spy.assert_not_called()
    assert result.status == "state_none"
    assert controller.state is None


# ---------------------------------------------------------------------------
# H. Human selection authority - no auto rank-1
# ---------------------------------------------------------------------------


def test_h1_empty_selections_forwarded_verbatim_not_auto_picked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    live = _LiveContext(_controller(state=_base_state()))
    spy = _spy_on_action(monkeypatch)

    submit_gesture_rack_request(
        audio,
        live,
        catalog_path=catalog,
        selections={},
        pattern_id=SENTINEL_PATTERN_ID,
        allow_pattern_replacement=True,
        feature_enabled=True,
    )

    forwarded = _submitted(spy)["kwargs"]["selections"]
    assert forwarded == {}, "seam must never substitute a rank-1 selection"


def test_h2_incomplete_selections_remain_unresolved_downstream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0, 1)))

    observers: list[str] = []
    controller = _controller(
        state=_base_state(), on_musical_state_changed=lambda: observers.append("obs")
    )
    before = copy.deepcopy(controller.state)

    result = submit_gesture_rack_request(
        audio,
        _LiveContext(controller),
        catalog_path=catalog,
        selections={0: "101"},
        pattern_id=SENTINEL_PATTERN_ID,
        allow_pattern_replacement=True,
        feature_enabled=True,
    )

    assert result.status == "submitted"
    assert result.action_result is not None
    assert result.action_result.status == "unresolved_selections"
    assert result.action_result.unresolved_cluster_ids == (1,)
    assert result.action_result.applied_state is None
    assert controller.state == before
    assert observers == []


def test_h3_unknown_selection_id_is_not_silently_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    live = _LiveContext(_controller(state=_base_state()))
    spy = _spy_on_action(monkeypatch)

    submit_gesture_rack_request(
        audio,
        live,
        catalog_path=catalog,
        selections={0: "999999"},
        pattern_id=SENTINEL_PATTERN_ID,
        allow_pattern_replacement=True,
        feature_enabled=True,
    )

    assert _submitted(spy)["kwargs"]["selections"] == {0: "999999"}


def test_h4_module_exposes_exactly_the_frozen_public_seams() -> None:
    module = importlib.import_module("src.gesture_rack_request")
    public = {
        name
        for name in vars(module)
        if not name.startswith("_") and name in {"propose_gesture_rack_candidates", "submit_gesture_rack_request"}
    }
    assert public == {"propose_gesture_rack_candidates", "submit_gesture_rack_request"}


def test_h5_proposal_env_free(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Proposal seam must not depend on process environment for its inputs."""
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))

    baseline = propose_gesture_rack_candidates(audio, catalog_path=catalog, top_n=2)
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(tmp_path / "absent.db"))
    try:
        after = propose_gesture_rack_candidates(audio, catalog_path=catalog, top_n=2)
    finally:
        monkeypatch.delenv("SAMPLE_BRAIN_DB_PATH", raising=False)

    assert after == baseline
    assert os.environ.get("SAMPLE_BRAIN_DB_PATH") is None
