"""#786 Brand / Analysis Motion contract — frozen RED surface.

Python-only Core contract. Does not touch QML or Theme Authority.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path

import pytest

from src.workbench_display_preferences import MOTION_OFF, MOTION_ON, MOTION_REDUCED
from src.workbench_qml_analysis import AnalysisJobCoordinator, AnalysisUiState


REPO_ROOT = Path(__file__).resolve().parents[1]

PRIMARY_BRAIN = (
    REPO_ROOT
    / "docs"
    / "assets"
    / "portfolio"
    / "references"
    / "brand"
    / "sample_brain_logo_primary.png"
)
SPLASH_TYPOGRAPHY = (
    REPO_ROOT
    / "docs"
    / "assets"
    / "portfolio"
    / "references"
    / "brand"
    / "sample_brain_splash_typography.png"
)
PRIMARY_BRAIN_SHA256 = (
    "6e8ba304d216e8f1ba0e819603388dc37ff18491fe1a3e22b985513258882605"
)
SPLASH_TYPOGRAPHY_SHA256 = (
    "eb130874c65ce8c1e36500b56e3cb1328318d6ac439fd13305547949994a83f6"
)
BRAND_CLAIM = "Sample Brain — Frech aber im Flow."


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_owner_approved_brand_reference_pins_exist() -> None:
    assert PRIMARY_BRAIN.is_file()
    assert SPLASH_TYPOGRAPHY.is_file()
    assert _sha256(PRIMARY_BRAIN) == PRIMARY_BRAIN_SHA256
    assert _sha256(SPLASH_TYPOGRAPHY) == SPLASH_TYPOGRAPHY_SHA256


def test_brand_slots_resolve_only_owner_approved_portfolio_refs() -> None:
    from src.workbench_brand_motion import (
        BRAND_CLAIM as MODULE_CLAIM,
        resolve_brand_slots,
    )

    slots = resolve_brand_slots(repo_root=REPO_ROOT)
    assert MODULE_CLAIM == BRAND_CLAIM
    assert slots["brain_symbol"].path.resolve() == PRIMARY_BRAIN.resolve()
    assert slots["brain_symbol"].sha256 == PRIMARY_BRAIN_SHA256
    assert slots["splash_typography"].path.resolve() == SPLASH_TYPOGRAPHY.resolve()
    assert slots["splash_typography"].sha256 == SPLASH_TYPOGRAPHY_SHA256
    for slot in slots.values():
        assert slot.path.is_file()
        assert _sha256(slot.path) == slot.sha256
        assert "portfolio/references/brand/" in slot.relative_path.replace("\\", "/")
        assert not str(slot.path).lower().endswith(".svg")


def test_screen1_header_policy_forbids_permanent_branding() -> None:
    from src.workbench_brand_motion import SCREEN1_HEADER_PERMITS_PERMANENT_BRANDING

    assert SCREEN1_HEADER_PERMITS_PERMANENT_BRANDING is False


def test_project_analysis_motion_indeterminate_when_total_non_positive() -> None:
    from src.workbench_brand_motion import project_analysis_motion

    for total in (0, -1):
        projection = project_analysis_motion(
            AnalysisUiState(
                phase="scanning",
                current=3,
                total=total,
                display_name="kick.wav",
                token=7,
            ),
            MOTION_ON,
        )
        assert projection.progress_kind == "indeterminate"
        assert projection.progress_ratio is None
        assert projection.sample_name == "kick.wav"
        assert projection.phase == "scanning"
        assert "percent" not in projection.__dataclass_fields__


def test_project_analysis_motion_determinate_ratio_clamped() -> None:
    from src.workbench_brand_motion import project_analysis_motion

    mid = project_analysis_motion(
        AnalysisUiState(
            phase="analyzing",
            current=2,
            total=4,
            display_name="snare.wav",
            token=3,
        ),
        MOTION_ON,
    )
    assert mid.progress_kind == "determinate"
    assert mid.progress_ratio == pytest.approx(0.5)
    assert mid.sample_name == "snare.wav"

    over = project_analysis_motion(
        AnalysisUiState(phase="analyzing", current=9, total=4, display_name="x.wav"),
        MOTION_ON,
    )
    assert over.progress_ratio == pytest.approx(1.0)

    under = project_analysis_motion(
        AnalysisUiState(phase="analyzing", current=-2, total=4, display_name="y.wav"),
        MOTION_ON,
    )
    assert under.progress_ratio == pytest.approx(0.0)


def test_project_analysis_motion_sample_name_only_from_display_name() -> None:
    from src.workbench_brand_motion import project_analysis_motion

    empty = project_analysis_motion(
        AnalysisUiState(phase="analyzing", current=1, total=2, display_name=""),
        MOTION_ON,
    )
    assert empty.sample_name == ""

    named = project_analysis_motion(
        AnalysisUiState(
            phase="analyzing",
            current=1,
            total=2,
            display_name="real_sample.wav",
        ),
        MOTION_ON,
    )
    assert named.sample_name == "real_sample.wav"


def test_project_analysis_motion_modes_on_reduced_off() -> None:
    from src.workbench_brand_motion import project_analysis_motion

    state = AnalysisUiState(
        phase="analyzing",
        current=1,
        total=2,
        display_name="hat.wav",
        token=1,
    )

    on = project_analysis_motion(state, MOTION_ON)
    assert on.motion_mode == MOTION_ON
    assert on.motion_active is True
    assert on.reduced_motion is False
    assert on.static_fallback is False

    reduced = project_analysis_motion(state, MOTION_REDUCED)
    assert reduced.motion_mode == MOTION_REDUCED
    assert reduced.motion_active is True
    assert reduced.reduced_motion is True
    assert reduced.static_fallback is False
    assert reduced.progress_kind == on.progress_kind
    assert reduced.progress_ratio == on.progress_ratio

    off = project_analysis_motion(state, MOTION_OFF)
    assert off.motion_mode == MOTION_OFF
    assert off.motion_active is False
    assert off.static_fallback is True
    assert off.progress_kind == on.progress_kind
    assert off.progress_ratio == on.progress_ratio
    assert off.sample_name == "hat.wav"

    aliased = project_analysis_motion(state, "full")
    assert aliased.motion_mode == MOTION_ON


def test_project_analysis_motion_ignores_stale_job_token() -> None:
    from src.workbench_brand_motion import project_analysis_motion

    live = AnalysisUiState(
        phase="analyzing",
        current=1,
        total=4,
        display_name="live.wav",
        token=10,
    )
    stale = AnalysisUiState(
        phase="analyzing",
        current=3,
        total=4,
        display_name="stale.wav",
        token=9,
    )

    ok = project_analysis_motion(live, MOTION_ON, expected_token=10)
    assert ok.stale is False
    assert ok.sample_name == "live.wav"
    assert ok.progress_kind == "determinate"
    assert ok.progress_ratio == pytest.approx(0.25)

    ignored = project_analysis_motion(stale, MOTION_ON, expected_token=10)
    assert ignored.stale is True
    assert ignored.sample_name == ""
    assert ignored.progress_kind == "none"
    assert ignored.progress_ratio is None
    assert ignored.motion_active is False
    assert ignored.static_fallback is True


def test_stale_token_aligns_with_analysis_job_coordinator_invalidation(
    tmp_path: Path,
) -> None:
    from src.workbench_brand_motion import project_analysis_motion

    workers: list[object] = []

    class FakeWorker:
        def __init__(self, spec: object) -> None:
            self.spec = spec
            self.cancel_requested = False

        def start(self) -> None:
            return None

        def request_cancel(self) -> None:
            self.cancel_requested = True

        def wait(self) -> None:
            return None

    def factory(spec: object) -> FakeWorker:
        worker = FakeWorker(spec)
        workers.append(worker)
        return worker

    coordinator = AnalysisJobCoordinator(
        library_db_path=tmp_path / "library.db",
        worker_factory=factory,
    )
    assert coordinator.start(41, tmp_path / "samples")
    token = workers[0].spec.token
    assert token is not None

    coordinator.handle_progress(41, token, 1, 2, "Kick.wav", "analyzing")
    live_state = coordinator.state(41)
    expected = coordinator.current_token(41)
    live = project_analysis_motion(live_state, MOTION_ON, expected_token=expected)
    assert live.stale is False
    assert live.sample_name == "Kick.wav"

    coordinator.request_cancel(41)
    # Late progress after invalidation is dropped by the coordinator authority.
    coordinator.handle_progress(41, token, 2, 2, "late.wav", "analyzing")
    after = coordinator.state(41)
    assert after.phase == "cancelled"
    assert after.display_name == ""

    # Projector must also refuse a fabricated late state with a mismatched token.
    fabricated_late = AnalysisUiState(
        folder_id=41,
        phase="analyzing",
        current=2,
        total=2,
        display_name="late.wav",
        token=token - 1 if isinstance(token, int) else 0,
    )
    stale = project_analysis_motion(
        fabricated_late,
        MOTION_ON,
        expected_token=expected,
    )
    assert stale.stale is True
    assert stale.sample_name == ""
    assert stale.progress_kind == "none"


def test_project_analysis_motion_uses_only_allowed_analysis_fields() -> None:
    from src.workbench_brand_motion import project_analysis_motion

    source = inspect.getsource(project_analysis_motion)
    tree = ast.parse(source)
    allowed = {
        "phase",
        "current",
        "total",
        "display_name",
        "token",
    }
    referenced: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def visit_Attribute(self, node: ast.Attribute) -> None:
            if isinstance(node.value, ast.Name) and node.value.id in {
                "state",
                "analysis_state",
                "ui_state",
            }:
                referenced.add(node.attr)
            self.generic_visit(node)

    Visitor().visit(tree)
    assert referenced <= allowed
    assert {"phase", "current", "total", "display_name"} <= referenced


def test_brand_motion_module_forbids_theme_and_dsp_authority() -> None:
    module_path = REPO_ROOT / "src" / "workbench_brand_motion.py"
    assert module_path.is_file()
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
                if node.module.startswith("."):
                    imported.add(node.module.lstrip("."))
                for alias in node.names:
                    imported.add(alias.name)

    forbidden_tokens = (
        "workbench_theme",
        "librosa",
        "soundfile",
        "numpy",
        "scipy",
        "fft",
        "rfft",
        "stft",
    )
    lowered = source.lower()
    for token in forbidden_tokens:
        assert token not in lowered
    assert "workbench_qml" not in imported
    assert "theme" not in imported
