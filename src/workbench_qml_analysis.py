"""Asynchronous analysis coordination for the production QML Screen-1 path.

The module-level coordination contracts are deliberately Qt-free.  The optional
Qt worker factory is created only by the QML runtime, so importing Workbench core
modules does not require PySide6.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, Callable, Literal

from .workbench_controller import WorkbenchResult, analyze_folder_for_workbench


AnalysisPhase = Literal["idle", "scanning", "analyzing", "done", "cancelled", "error"]


@dataclass(frozen=True)
class AnalysisUiState:
    folder_id: int | None = None
    folder_path: Path | None = None
    token: int | None = None
    current: int = 0
    total: int = 0
    display_name: str = ""
    phase: AnalysisPhase = "idle"
    error: str | None = None


@dataclass(frozen=True)
class AnalysisJobSpec:
    folder_id: int
    folder_path: Path
    library_db_path: Path
    token: int
    use_cache: bool = True


@dataclass
class _Job:
    spec: AnalysisJobSpec
    worker: Any
    invalidated: bool = False
    pending_remove: bool = False


StateCallback = Callable[[AnalysisUiState], None]
CompleteCallback = Callable[[int, WorkbenchResult], None]
RemoveCallback = Callable[[int], None]


class AnalysisJobCoordinator:
    """Enforce per-source job, token, cancellation and completion contracts."""

    def __init__(
        self,
        *,
        library_db_path: Path,
        worker_factory: Callable[[AnalysisJobSpec], Any],
        on_state: StateCallback | None = None,
        on_complete: CompleteCallback | None = None,
        on_remove: RemoveCallback | None = None,
    ) -> None:
        self.library_db_path = Path(library_db_path).expanduser().resolve()
        self._worker_factory = worker_factory
        self._on_state = on_state
        self._on_complete = on_complete
        self._on_remove = on_remove
        self._jobs: dict[int, _Job] = {}
        self._states: dict[int, AnalysisUiState] = {}
        self._generation = 0
        self._shutting_down = False

    def state(self, folder_id: int) -> AnalysisUiState:
        return self._states.get(folder_id, AnalysisUiState(folder_id=folder_id))

    def current_token(self, folder_id: int) -> int | None:
        job = self._jobs.get(folder_id)
        return None if job is None else job.spec.token

    def start(self, folder_id: int, folder_path: Path | str) -> bool:
        if self._shutting_down or folder_id in self._jobs:
            return False
        self._generation += 1
        spec = AnalysisJobSpec(
            folder_id=folder_id,
            folder_path=Path(folder_path).expanduser().resolve(),
            library_db_path=self.library_db_path,
            token=self._generation,
            use_cache=True,
        )
        try:
            worker = self._worker_factory(spec)
        except Exception:
            self._publish(
                AnalysisUiState(
                    folder_id=folder_id,
                    folder_path=spec.folder_path,
                    token=spec.token,
                    phase="error",
                    error="Analyse konnte nicht gestartet werden.",
                )
            )
            return False
        job = _Job(spec=spec, worker=worker)
        self._jobs[folder_id] = job
        bind = getattr(worker, "bind", None)
        try:
            if bind is not None and not getattr(worker, "prebound", False):
                bind(
                    self.handle_progress,
                    self.handle_done,
                    self.handle_error,
                    self.handle_finished,
                )
        except Exception:
            self._jobs.pop(folder_id, None)
            self._request_worker_cancel(worker)
            self._publish(
                AnalysisUiState(
                    folder_id=folder_id,
                    folder_path=spec.folder_path,
                    token=spec.token,
                    phase="error",
                    error="Analyse konnte nicht gestartet werden.",
                )
            )
            return False
        self._publish(
            AnalysisUiState(
                folder_id=folder_id,
                folder_path=spec.folder_path,
                token=spec.token,
                phase="scanning",
            )
        )
        try:
            worker.start()
        except Exception:
            self._jobs.pop(folder_id, None)
            self._request_worker_cancel(worker)
            self._publish(
                AnalysisUiState(
                    folder_id=folder_id,
                    folder_path=spec.folder_path,
                    token=spec.token,
                    phase="error",
                    error="Analyse konnte nicht gestartet werden.",
                )
            )
            return False
        return True

    def handle_progress(
        self,
        folder_id: int,
        token: int,
        current: int,
        total: int,
        display_name: str,
        phase: str,
    ) -> None:
        job = self._current_job(folder_id, token)
        if job is None:
            return
        ui_phase: AnalysisPhase = (
            phase if phase in {"scanning", "cancelled"} else "analyzing"
        )
        self._publish(
            AnalysisUiState(
                folder_id=folder_id,
                folder_path=job.spec.folder_path,
                token=token,
                current=current,
                total=total,
                display_name=display_name,
                phase=ui_phase,
            )
        )

    def handle_done(self, folder_id: int, token: int, result: WorkbenchResult) -> None:
        job = self._current_job(folder_id, token)
        if job is None:
            return
        cancelled = bool(result.summary.get("cancelled"))
        if cancelled:
            self._publish(
                AnalysisUiState(
                    folder_id=folder_id,
                    folder_path=job.spec.folder_path,
                    token=token,
                    phase="cancelled",
                )
            )
            return
        self._publish(
            AnalysisUiState(
                folder_id=folder_id,
                folder_path=job.spec.folder_path,
                token=token,
                phase="done",
            )
        )
        if self._on_complete is not None:
            self._on_complete(folder_id, result)

    def handle_error(self, folder_id: int, token: int, _message: str) -> None:
        job = self._current_job(folder_id, token)
        if job is None:
            return
        self._publish(
            AnalysisUiState(
                folder_id=folder_id,
                folder_path=job.spec.folder_path,
                token=token,
                phase="error",
                error="Analyse der Library-Quelle fehlgeschlagen.",
            )
        )

    def handle_finished(self, folder_id: int, token: int) -> None:
        job = self._jobs.get(folder_id)
        if job is None or job.spec.token != token:
            return
        self._jobs.pop(folder_id, None)
        if job.pending_remove and not self._shutting_down and self._on_remove is not None:
            self._on_remove(folder_id)

    def request_cancel(self, folder_id: int) -> bool:
        job = self._jobs.get(folder_id)
        if job is None:
            return False
        self._invalidate(job, pending_remove=False)
        self._request_worker_cancel(job.worker)
        return True

    def request_remove(self, folder_id: int) -> bool:
        job = self._jobs.get(folder_id)
        if job is None:
            if self._on_remove is not None:
                self._on_remove(folder_id)
            return True
        job.pending_remove = True
        self._invalidate(job, pending_remove=True)
        self._request_worker_cancel(job.worker)
        return True

    def shutdown(self, *, wait: bool = False) -> None:
        self._shutting_down = True
        jobs = tuple(self._jobs.values())
        for job in jobs:
            self._invalidate(job, pending_remove=job.pending_remove)
            self._request_worker_cancel(job.worker)
        if wait:
            for job in jobs:
                wait_for_worker = getattr(job.worker, "wait", None)
                if wait_for_worker is not None:
                    wait_for_worker()
                self.handle_finished(job.spec.folder_id, job.spec.token)

    def _current_job(self, folder_id: int, token: int) -> _Job | None:
        job = self._jobs.get(folder_id)
        if job is None or job.invalidated or job.spec.token != token:
            return None
        return job

    def _invalidate(self, job: _Job, *, pending_remove: bool) -> None:
        job.invalidated = True
        job.pending_remove = job.pending_remove or pending_remove
        self._publish(
            AnalysisUiState(
                folder_id=job.spec.folder_id,
                folder_path=job.spec.folder_path,
                token=job.spec.token,
                phase="cancelled",
            )
        )

    def _publish(self, state: AnalysisUiState) -> None:
        if state.folder_id is not None:
            self._states[state.folder_id] = state
        if self._on_state is not None:
            self._on_state(state)

    @staticmethod
    def _request_worker_cancel(worker: Any) -> None:
        request_cancel = getattr(worker, "request_cancel", None)
        if request_cancel is None:
            return
        try:
            request_cancel()
        except Exception:
            # Cancellation is best effort; the worker lifecycle still owns
            # the eventual finished signal and cleanup.
            return


def create_qt_analysis_coordinator(
    *,
    library_db_path: Path,
    on_state: StateCallback | None = None,
    on_complete: CompleteCallback | None = None,
    on_remove: RemoveCallback | None = None,
):
    """Create the optional Qt-backed coordinator without importing Qt globally."""

    try:
        from PySide6.QtCore import QObject, QThread, Signal, Slot
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Die QML-Analyse benötigt die optionale Abhängigkeit: pip install -e '.[qtquick]'"
        ) from exc

    class AnalysisWorker(QObject):
        progress = Signal(int, int, int, int, str, str)
        completed = Signal(int, int, object)
        failed = Signal(int, int, str)
        finished = Signal(int, int)

        def __init__(self, spec: AnalysisJobSpec) -> None:
            super().__init__()
            self.spec = spec
            self._cancel_requested = Event()

        def _progress(self, current: int, total: int, name: str, phase: str) -> None:
            self.progress.emit(self.spec.folder_id, self.spec.token, current, total, name, phase)

        def _should_cancel(self) -> bool:
            return self._cancel_requested.is_set()

        @Slot()
        def run(self) -> None:
            try:
                result = analyze_folder_for_workbench(
                    self.spec.folder_path,
                    progress_callback=self._progress,
                    should_cancel=self._should_cancel,
                    use_cache=self.spec.use_cache,
                    library_db_path=self.spec.library_db_path,
                )
            except Exception as exc:
                self.failed.emit(self.spec.folder_id, self.spec.token, str(exc))
            else:
                self.completed.emit(self.spec.folder_id, self.spec.token, result)
            finally:
                self.finished.emit(self.spec.folder_id, self.spec.token)

        def request_cancel(self) -> None:
            self._cancel_requested.set()

    class QtWorkerHandle:
        def __init__(self, spec: AnalysisJobSpec) -> None:
            self.prebound = False
            self.thread = QThread()
            self.worker = AnalysisWorker(spec)
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)

        def bind(self, on_progress, on_done, on_error, on_finished) -> None:
            self.worker.progress.connect(on_progress)
            self.worker.completed.connect(on_done)
            self.worker.failed.connect(on_error)
            folder_id = self.worker.spec.folder_id
            token = self.worker.spec.token
            self.thread.finished.connect(lambda: on_finished(folder_id, token))

        def start(self) -> None:
            self.thread.start()

        def request_cancel(self) -> None:
            self.worker.request_cancel()

        def wait(self) -> None:
            self.thread.wait()

    class QtAnalysisCoordinator(QObject):
        stateChanged = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._core = AnalysisJobCoordinator(
                library_db_path=library_db_path,
                worker_factory=self._make_worker,
                on_state=on_state,
                on_complete=on_complete,
                on_remove=on_remove,
            )

        def _make_worker(self, spec: AnalysisJobSpec) -> QtWorkerHandle:
            handle = QtWorkerHandle(spec)
            handle.bind(
                self._on_progress,
                self._on_done,
                self._on_error,
                self._on_finished,
            )
            handle.prebound = True
            return handle

        @Slot(int, int, int, int, str, str)
        def _on_progress(
            self,
            folder_id: int,
            token: int,
            current: int,
            total: int,
            display_name: str,
            phase: str,
        ) -> None:
            self._core.handle_progress(
                folder_id,
                token,
                current,
                total,
                display_name,
                phase,
            )

        @Slot(int, int, object)
        def _on_done(self, folder_id: int, token: int, result: WorkbenchResult) -> None:
            self._core.handle_done(folder_id, token, result)

        @Slot(int, int, str)
        def _on_error(self, folder_id: int, token: int, message: str) -> None:
            self._core.handle_error(folder_id, token, message)

        @Slot(int, int)
        def _on_finished(self, folder_id: int, token: int) -> None:
            self._core.handle_finished(folder_id, token)

        @Slot(int, str, result=bool)
        def start(self, folder_id: int, folder_path: str) -> bool:
            return self._core.start(folder_id, folder_path)

        @Slot(int, result=bool)
        def cancel(self, folder_id: int) -> bool:
            return self._core.request_cancel(folder_id)

        @Slot(int, result=bool)
        def remove(self, folder_id: int) -> bool:
            return self._core.request_remove(folder_id)

        @Slot()
        def shutdown(self) -> None:
            self._core.shutdown()

        def close(self) -> None:
            """Finish worker threads after the Qt event loop has stopped."""
            self._core.shutdown(wait=True)

    return QtAnalysisCoordinator()


__all__ = [
    "AnalysisJobCoordinator",
    "AnalysisJobSpec",
    "AnalysisPhase",
    "AnalysisUiState",
    "create_qt_analysis_coordinator",
]
