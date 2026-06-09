from __future__ import annotations

# ruff: noqa: N802, N815
import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from agent_core.app import RadAgentAppService, RadAgentEvent

try:
    from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
except ImportError as exc:  # pragma: no cover - exercised only when desktop is launched
    raise RuntimeError(
        "RadAgent desktop bridge requires PySide6. Install with: pip install -e '.[desktop]'"
    ) from exc


class RadAgentBridge(QObject):
    """QObject facade consumed by QML.

    QML must never call the REPL. This bridge delegates all runtime work to
    RadAgentAppService and exposes only serializable state.
    """

    statusChanged = Signal()
    jobsChanged = Signal()
    eventsChanged = Signal()
    artifactsChanged = Signal()
    busyChanged = Signal()
    errorOccurred = Signal(str)
    artifactOpened = Signal("QVariant")

    def __init__(self, service: RadAgentAppService | None = None) -> None:
        super().__init__()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="radagent-ui")
        self._service = service or RadAgentAppService(event_callback=self._on_event)
        self._status: dict[str, Any] = self._service.get_status().model_dump(mode="json")
        self._jobs: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._artifacts: list[dict[str, Any]] = []
        self._busy = False
        self.refreshJobs()

    @Property("QVariant", notify=statusChanged)
    def status(self) -> dict[str, Any]:
        return self._status

    @Property("QVariant", notify=jobsChanged)
    def jobs(self) -> list[dict[str, Any]]:
        return self._jobs

    @Property("QVariant", notify=eventsChanged)
    def events(self) -> list[dict[str, Any]]:
        return self._events

    @Property("QVariant", notify=artifactsChanged)
    def artifacts(self) -> list[dict[str, Any]]:
        return self._artifacts

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Slot(str)
    def sendMessage(self, message: str) -> None:
        message = message.strip()
        if not message:
            return
        self._append_local_event("user_message", "info", message)
        self._run_async(self._service.chat(message), self._after_chat)

    @Slot(str)
    def startJob(self, query: str) -> None:
        query = query.strip()
        if not query:
            self.errorOccurred.emit("Please enter a simulation request.")
            return
        self._append_local_event("user_request", "info", query)
        self._run_async(
            self._service.start_job(query, auto_continue=False),
            lambda _result: self._refresh_all(),
        )

    @Slot()
    def continueJob(self) -> None:
        self._run_async(self._service.run_until_blocked(), lambda _result: self._refresh_all())

    @Slot()
    def stepJob(self) -> None:
        self._run_async(self._service.step(), lambda _result: self._refresh_all())

    @Slot(str)
    def resumeJob(self, job_id: str) -> None:
        job_id = job_id.strip()
        if not job_id:
            return
        try:
            self._service.resume_job(job_id)
        except Exception as exc:
            self.errorOccurred.emit(str(exc))
            return
        self._refresh_all()

    @Slot()
    def refreshJobs(self) -> None:
        try:
            self._jobs = self._service.list_jobs()
        except Exception as exc:
            self.errorOccurred.emit(str(exc))
            self._jobs = []
        self.jobsChanged.emit()

    @Slot()
    def refreshArtifacts(self) -> None:
        self._refresh_artifacts()

    @Slot(str)
    def openArtifact(self, path: str) -> None:
        try:
            content = self._service.read_artifact(path).model_dump(mode="json")
        except Exception as exc:
            self.errorOccurred.emit(str(exc))
            return
        self.artifactOpened.emit(content)

    @Slot()
    def runBuild(self) -> None:
        self._run_async(self._service.build_generated_code(), lambda _result: self._refresh_all())

    @Slot(int)
    def runSimulation(self, events: int) -> None:
        events = max(1, int(events or 1000))
        self._run_async(
            self._service.run_simulation(events=events),
            lambda _result: self._refresh_all(),
        )

    def _run_async(self, coro: Any, on_success: Any | None = None) -> None:
        self._set_busy(True)
        future = self._executor.submit(lambda: asyncio.run(coro))

        def _done(done: Future[Any]) -> None:
            QTimer.singleShot(0, lambda: self._finish_future(done, on_success))

        future.add_done_callback(_done)

    def _finish_future(self, future: Future[Any], on_success: Any | None) -> None:
        self._set_busy(False)
        try:
            result = future.result()
        except Exception as exc:
            self.errorOccurred.emit(str(exc))
            self._append_local_event("operation_failed", "error", str(exc))
            return
        if on_success:
            on_success(result)
        self._refresh_all()

    def _after_chat(self, response: Any) -> None:
        message = getattr(response, "message", "")
        if message:
            self._append_local_event("assistant_message", "success", message)

    def _set_busy(self, value: bool) -> None:
        if self._busy == value:
            return
        self._busy = value
        self.busyChanged.emit()

    def _on_event(self, event: RadAgentEvent) -> None:
        self._events.append(event.model_dump(mode="json"))
        if len(self._events) > 500:
            self._events = self._events[-500:]
        self.eventsChanged.emit()

    def _append_local_event(self, event_type: str, status: str, summary: str) -> None:
        self._events.append(
            {
                "event_type": event_type,
                "status": status,
                "summary": summary,
                "phase": "",
                "job_id": self._status.get("job_id", ""),
                "payload": {},
            }
        )
        self.eventsChanged.emit()

    def _refresh_all(self) -> None:
        self._status = self._service.get_status().model_dump(mode="json")
        self.statusChanged.emit()
        self.refreshJobs()
        self._refresh_artifacts()

    def _refresh_artifacts(self) -> None:
        try:
            job_id = str(self._status.get("job_id", ""))
            self._artifacts = [
                artifact.model_dump(mode="json")
                for artifact in self._service.list_artifacts(job_id)
            ]
        except Exception as exc:
            self.errorOccurred.emit(str(exc))
            self._artifacts = []
        self.artifactsChanged.emit()
