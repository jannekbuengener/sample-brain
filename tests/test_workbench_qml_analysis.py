from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

from src.workbench_library_navigation import (
    LibraryAvailability,
    LibraryNode,
    LibraryNodeKind,
    LibraryScope,
    LibraryScopeKind,
)
from src.workbench_qml_library import LibrarySelectionIntent, WorkbenchLibraryTreeState


ROOT_ID = "root:7"


@dataclass
class FakeWorker:
    spec: object
    started: bool = False
    cancel_requested: bool = False
    wait_calls: int = 0

    def start(self) -> None:
        self.started = True

    def request_cancel(self) -> None:
        self.cancel_requested = True

    def wait(self) -> None:
        self.wait_calls += 1


@dataclass
class StartFailingWorker(FakeWorker):
    def start(self) -> None:
        raise RuntimeError("thread start failed")


class DbNavigation:
    def __init__(self, library_db_path: Path) -> None:
        self.library_db_path = library_db_path
        self.root = LibraryNode(
            ROOT_ID,
            LibraryNodeKind.REGISTERED_ROOT,
            "Samples",
            "container:sample-sources",
            True,
            False,
            LibraryAvailability.AVAILABLE,
            folder_id=7,
        )
        self.top = (
            LibraryNode(
                "container:sample-sources",
                LibraryNodeKind.SAMPLE_SOURCES,
                "Sample Sources",
                None,
                False,
                True,
                LibraryAvailability.AVAILABLE,
            ),
        )

    def top_level_nodes(self):
        return self.top

    def children(self, node_id: str):
        return (self.root,) if node_id == "container:sample-sources" else ()

    def resolve_scope(self, node_id: str):
        if node_id == ROOT_ID:
            return LibraryScope(
                LibraryScopeKind.ROOT,
                folder_id=7,
                folder_path="C:/samples",
            )
        return None


def test_navigation_runtime_and_loader_share_exact_explicit_db(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src import workbench_qml_runtime as runtime

    db_path = (tmp_path / "library.db").resolve()
    navigation = DbNavigation(db_path)
    tree = WorkbenchLibraryTreeState(navigation)
    composition = runtime.Screen1QmlRuntimeComposition(
        library_db_path=db_path,
        tree_state=tree,
    )
    calls: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        runtime,
        "load_cached_folder_rows",
        lambda folder, *, library_db_path: calls.append(
            (Path(folder), Path(library_db_path))
        )
        or [],
    )

    node = navigation.root
    scope = navigation.resolve_scope(ROOT_ID)
    assert scope is not None
    composition.dispatch_selection(LibrarySelectionIntent(node=node, scope=scope))

    assert composition.library_db_path == db_path
    assert composition.library_tree.library_db_path == db_path
    assert calls == [(Path("C:/samples"), db_path)]


def test_navigation_runtime_and_analyzer_share_exact_explicit_db(
    tmp_path: Path,
) -> None:
    from src import workbench_qml_runtime as runtime
    from src.workbench_qml_analysis import AnalysisJobCoordinator

    db_path = (tmp_path / "library.db").resolve()
    tree = WorkbenchLibraryTreeState(DbNavigation(db_path))
    composition = runtime.Screen1QmlRuntimeComposition(
        library_db_path=db_path,
        tree_state=tree,
    )
    specs = []

    def factory(spec):
        specs.append(spec)
        return FakeWorker(spec)

    coordinator = AnalysisJobCoordinator(
        library_db_path=composition.library_db_path,
        worker_factory=factory,
    )

    assert coordinator.start(41, tmp_path) is True
    assert composition.library_tree.library_db_path == db_path
    assert specs[0].library_db_path == db_path
    assert specs[0].use_cache is True


def test_runtime_rejects_mixed_tree_database_state(tmp_path: Path) -> None:
    from src import workbench_qml_runtime as runtime

    tree_db = (tmp_path / "tree.db").resolve()
    runtime_db = (tmp_path / "runtime.db").resolve()

    with pytest.raises(ValueError, match="dieselbe Library-DB"):
        runtime.Screen1QmlRuntimeComposition(
            library_db_path=runtime_db,
            tree_state=WorkbenchLibraryTreeState(DbNavigation(tree_db)),
        )


def test_public_add_source_stays_bool_and_internal_registration_exposes_folder_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src import workbench_qml_runtime as runtime

    tree = WorkbenchLibraryTreeState(DbNavigation((tmp_path / "library.db").resolve()))
    composition = runtime.Screen1QmlRuntimeComposition(tree_state=tree)
    monkeypatch.setattr(
        runtime,
        "add_workbench_library_folder",
        lambda folder, **_kwargs: 41,
    )

    registration = composition.register_source_for_analysis(tmp_path)

    assert registration is not None
    assert registration.folder_id == 41
    assert registration.normalized_path == tmp_path.resolve()
    assert composition.add_source(tmp_path) is True


def test_bool_registration_result_uses_internal_folder_lookup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace

    from src import workbench_qml_runtime as runtime

    db_path = (tmp_path / "library.db").resolve()
    tree = WorkbenchLibraryTreeState(DbNavigation(db_path))
    composition = runtime.Screen1QmlRuntimeComposition(
        library_db_path=db_path,
        tree_state=tree,
    )
    monkeypatch.setattr(
        runtime,
        "add_workbench_library_folder",
        lambda _folder, **_kwargs: True,
    )
    monkeypatch.setattr(
        runtime,
        "get_workbench_library_folders",
        lambda **_kwargs: [SimpleNamespace(id=41, path=str(tmp_path.resolve()))],
    )

    registration = composition.register_source_for_analysis(tmp_path)

    assert registration is not None
    assert registration.folder_id == 41


def test_analysis_coordinator_passes_cache_contract_and_rejects_duplicate_job(
    tmp_path: Path,
) -> None:
    from src.workbench_qml_analysis import AnalysisJobCoordinator

    db_path = (tmp_path / "library.db").resolve()
    workers: list[FakeWorker] = []

    def factory(spec):
        worker = FakeWorker(spec)
        workers.append(worker)
        return worker

    coordinator = AnalysisJobCoordinator(
        library_db_path=db_path,
        worker_factory=factory,
    )

    assert coordinator.start(41, tmp_path) is True
    assert coordinator.start(41, tmp_path) is False
    assert len(workers) == 1
    assert workers[0].started is True
    assert workers[0].spec.library_db_path == db_path
    assert workers[0].spec.use_cache is True


def test_remove_invalidates_token_and_waits_for_worker_finished(
    tmp_path: Path,
) -> None:
    from src import workbench_qml_analysis as analysis

    workers: list[FakeWorker] = []
    states: list[analysis.AnalysisUiState] = []
    completed: list[int] = []
    removed: list[int] = []

    def factory(spec):
        worker = FakeWorker(spec)
        workers.append(worker)
        return worker

    coordinator = analysis.AnalysisJobCoordinator(
        library_db_path=(tmp_path / "library.db").resolve(),
        worker_factory=factory,
        on_state=states.append,
        on_complete=lambda folder_id, _result: completed.append(folder_id),
        on_remove=lambda folder_id: removed.append(folder_id),
    )
    assert coordinator.start(41, tmp_path)
    token = workers[0].spec.token

    assert coordinator.request_remove(41) is True
    assert workers[0].cancel_requested is True
    assert removed == []

    coordinator.handle_progress(41, token, 1, 2, "late.wav", "analyzing")
    coordinator.handle_done(41, token, object())
    coordinator.handle_error(41, token, "late failure")
    assert completed == []
    assert states[-1].phase == "cancelled"

    coordinator.handle_finished(41, token)
    assert removed == [41]


def test_per_file_progress_does_not_report_job_done_or_error(
    tmp_path: Path,
) -> None:
    from src.workbench_qml_analysis import AnalysisJobCoordinator

    workers: list[FakeWorker] = []
    states = []

    def factory(spec):
        worker = FakeWorker(spec)
        workers.append(worker)
        return worker

    coordinator = AnalysisJobCoordinator(
        library_db_path=(tmp_path / "library.db").resolve(),
        worker_factory=factory,
        on_state=states.append,
    )
    assert coordinator.start(41, tmp_path)
    token = workers[0].spec.token

    coordinator.handle_progress(41, token, 1, 2, "Kick.wav", "done")
    assert states[-1].phase == "analyzing"
    coordinator.handle_progress(41, token, 2, 2, "Snare.wav", "error")
    assert states[-1].phase == "analyzing"


def test_remove_request_is_non_blocking_and_shutdown_cancels_active_workers(
    tmp_path: Path,
) -> None:
    from src.workbench_qml_analysis import AnalysisJobCoordinator

    workers: list[FakeWorker] = []

    def factory(spec):
        worker = FakeWorker(spec)
        workers.append(worker)
        return worker

    coordinator = AnalysisJobCoordinator(
        library_db_path=(tmp_path / "library.db").resolve(),
        worker_factory=factory,
    )
    assert coordinator.start(41, tmp_path)

    assert coordinator.request_remove(41) is True
    assert coordinator.shutdown() is None
    assert workers[0].cancel_requested is True
    assert workers[0].wait_calls == 0


def test_shutdown_waits_only_in_explicit_post_event_loop_cleanup(
    tmp_path: Path,
) -> None:
    from src.workbench_qml_analysis import AnalysisJobCoordinator

    workers: list[FakeWorker] = []

    def factory(spec):
        worker = FakeWorker(spec)
        workers.append(worker)
        return worker

    coordinator = AnalysisJobCoordinator(
        library_db_path=(tmp_path / "library.db").resolve(),
        worker_factory=factory,
    )
    assert coordinator.start(41, tmp_path)

    coordinator.shutdown(wait=True)

    assert workers[0].cancel_requested is True
    assert workers[0].wait_calls == 1
    assert coordinator.current_token(41) is None


def test_shutdown_does_not_complete_pending_remove_after_event_loop(
    tmp_path: Path,
) -> None:
    from src.workbench_qml_analysis import AnalysisJobCoordinator

    workers: list[FakeWorker] = []
    removed: list[int] = []

    def factory(spec):
        worker = FakeWorker(spec)
        workers.append(worker)
        return worker

    coordinator = AnalysisJobCoordinator(
        library_db_path=(tmp_path / "library.db").resolve(),
        worker_factory=factory,
        on_remove=removed.append,
    )
    assert coordinator.start(41, tmp_path)
    assert coordinator.request_remove(41)

    coordinator.shutdown(wait=True)

    assert workers[0].wait_calls == 1
    assert removed == []


def test_worker_start_failure_is_controlled_and_does_not_leave_active_job(
    tmp_path: Path,
) -> None:
    from src.workbench_qml_analysis import AnalysisJobCoordinator

    states = []
    workers: list[StartFailingWorker] = []

    def factory(spec):
        worker = StartFailingWorker(spec)
        workers.append(worker)
        return worker

    coordinator = AnalysisJobCoordinator(
        library_db_path=(tmp_path / "library.db").resolve(),
        worker_factory=factory,
        on_state=states.append,
    )

    assert coordinator.start(41, tmp_path) is False
    assert coordinator.current_token(41) is None
    assert workers[0].cancel_requested is True
    assert states[-1].phase == "error"
    assert states[-1].error == "Analyse konnte nicht gestartet werden."


def test_production_qml_exposes_real_analysis_state_and_cancel_intent() -> None:
    from src import workbench_qml

    assert "analysisStatus" in workbench_qml.QML_SOURCE
    assert "analysisCurrent" in workbench_qml.QML_SOURCE
    assert "analysisTotal" in workbench_qml.QML_SOURCE
    assert "cancelAnalysis" in workbench_qml.QML_SOURCE
    assert "ProgressBar" in workbench_qml.QML_SOURCE


def test_analysis_core_import_does_not_require_pyside6() -> None:
    repo_root = Path(__file__).parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import src.workbench_qml_analysis; "
            "import src.workbench_qml_runtime; import src.workbench_qml; "
            "assert 'PySide6' not in sys.modules",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 ist in dieser Testumgebung nicht installiert.",
)
def test_qt_bridge_projects_analysis_progress_and_cancel_safely() -> None:
    from PySide6.QtCore import QCoreApplication

    from src.workbench_qml import Screen1QmlViewModel, _qml_screen_data_bridge
    from src.workbench_qml_analysis import AnalysisUiState

    app = QCoreApplication.instance() or QCoreApplication([])
    del app
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    cancelled: list[bool] = []
    bridge = _qml_screen_data_bridge(
        view_model,
        on_cancel_analysis=lambda: cancelled.append(True),
    )
    notifications: list[bool] = []
    bridge.analysisProgressChanged.connect(lambda: notifications.append(True))

    view_model.set_analysis_state(
        AnalysisUiState(
            folder_id=7,
            current=2,
            total=4,
            display_name="Kick.wav",
            phase="analyzing",
        )
    )
    bridge.refresh()
    bridge.cancelAnalysis()

    assert notifications == [True]
    assert bridge.analysisStatus == "analyzing"
    assert bridge.analysisCurrent == 2
    assert bridge.analysisTotal == 4
    assert bridge.analysisSource == "Kick.wav"
    assert cancelled == [True]
