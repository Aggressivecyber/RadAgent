import json
import threading
import urllib.request
from pathlib import Path

import pytest

from agent_core.app.schemas import (
    ArtifactContent,
    BuildResult,
    JobStatus,
    ModelHealthReport,
    ModelHealthTierResult,
    PhaseResult,
    RadAgentEvent,
    SimulationResult,
)
from agent_core.pipeline import PIPELINE_PHASES
from agent_core.web.api import build_command_catalog, dispatch_web_command
from agent_core.workspace.paths import STAGE_HUMAN_CONFIRMATION


class FakeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def get_status(self) -> JobStatus:
        self.calls.append(("get_status", None))
        return JobStatus(job_id="job-1", status="paused", current_phase="g4_modeling")

    def list_jobs(self, *, include_all_projects: bool = False) -> list[dict[str, object]]:
        self.calls.append(("list_jobs", include_all_projects))
        return [{"job_id": "job-1", "status": "paused"}]

    def get_job(self, job_id: str) -> dict[str, object] | None:
        self.calls.append(("get_job", job_id))
        if job_id == "missing":
            return None
        return {"job_id": job_id, "status": "completed", "user_query": "demo"}

    def list_artifacts(self, job_id: str | None = None) -> list[object]:
        self.calls.append(("list_artifacts", job_id))
        return [{"job_id": job_id or "job-1", "path": "/tmp/report.md", "kind": "report"}]

    def read_artifact(self, path: str, *, max_chars: int = 200_000) -> ArtifactContent:
        self.calls.append(("read_artifact", (path, max_chars)))
        return ArtifactContent(path=path, exists=True, kind="text", text="artifact body")

    def package_generated_source_files(self, job_id: str | None = None) -> dict[str, object]:
        self.calls.append(("package_generated_source_files", job_id))
        return {
            "success": True,
            "path": "/tmp/job-1/downloads/job-1_geant4_source.zip",
            "filename": "job-1_geant4_source.zip",
            "content_type": "application/zip",
            "data": b"PK\x03\x04zip",
            "size_bytes": 7,
        }

    def get_visualization_payload(self, job_id: str | None = None) -> dict[str, object]:
        self.calls.append(("get_visualization_payload", job_id))
        return {
            "status": "ready",
            "job_id": job_id or "job-1",
            "source": {"visual_events": 100},
            "geometry": {"components": [{"id": "detector"}]},
            "tracks": [{"event_id": 0, "track_id": 1, "points_mm": [[0, 0, -1], [0, 0, 1]]}],
            "deposits": [{"event_id": 0, "position_mm": [0, 0, 0], "edep_MeV": 1.0}],
            "stats": {"components": 1, "tracks": 1, "track_points": 2, "deposits": 1},
            "warnings": [],
        }

    def recent_events(self, limit: int = 80) -> list[RadAgentEvent]:
        self.calls.append(("recent_events", limit))
        return [RadAgentEvent(event_type="job_started", summary="started")]

    def get_startup_status(self) -> dict[str, object]:
        self.calls.append(("get_startup_status", None))
        return {"tools": {"geant4": {"available": True}}}

    def get_model_config(self) -> dict[str, object]:
        self.calls.append(("get_model_config", None))
        return {
            "default_api_key_env": "RADAGENT_API_KEY",
            "tiers": {"pro": {"model_name": "mimo-pro", "api_key_configured": True}},
        }

    async def test_model_health(self) -> ModelHealthReport:
        self.calls.append(("test_model_health", None))
        return ModelHealthReport(
            tiers={
                "pro": ModelHealthTierResult(
                    tier="pro",
                    status="ok",
                    model_name="mimo-pro",
                    base_url="https://model.example.test/v1",
                    latency_ms=42.5,
                    response_preview="OK",
                )
            }
        )

    def update_model_config(self, update: dict[str, object]) -> dict[str, object]:
        self.calls.append(("update_model_config", update))
        return {
            "default_api_key_env": str(update.get("api_key_env", "RADAGENT_API_KEY")),
            "tiers": {"pro": {"model_name": update.get("pro_model", ""), "api_key_configured": True}},
        }

    def list_projects(self) -> list[dict[str, object]]:
        self.calls.append(("list_projects", None))
        return [{"slug": "default", "name": "Default"}]

    def set_current_project(self, value: str) -> dict[str, object]:
        self.calls.append(("set_current_project", value))
        return {"slug": value, "name": "Default"}

    def get_gate_results(self, job_id: str | None = None) -> list[dict[str, object]]:
        self.calls.append(("get_gate_results", job_id))
        return [{"gate_id": 20, "status": "pass"}]

    def get_confirmation_review(self, job_id: str | None = None) -> dict[str, object]:
        self.calls.append(("get_confirmation_review", job_id))
        return {"status": "pending", "preview": "review text"}

    def get_credibility_report(self, job_id: str | None = None) -> dict[str, object]:
        self.calls.append(("get_credibility_report", job_id))
        return {"gate_id": 20, "score": 0.91}

    async def get_workflow_diagnosis(self, job_id: str | None = None) -> dict[str, object]:
        self.calls.append(("get_workflow_diagnosis", job_id))
        return {
            "ui_state": "modeling_failed",
            "user_message": "建模失败，需先修复模型。",
            "allowed_actions": ["view_modeling_report"],
            "confirmation_actionable": False,
        }

    def get_workflow_context(self, job_id: str | None = None) -> dict[str, object]:
        self.calls.append(("get_workflow_context", job_id))
        return {"job_id": job_id or "job-1", "summary": "workflow memory"}

    def list_revisions(self, job_id: str | None = None) -> list[dict[str, object]]:
        self.calls.append(("list_revisions", job_id))
        return [{"revision_id": "rev-1", "status": "draft"}]

    def create_revision(self, user_request: str, job_id: str | None = None) -> dict[str, object]:
        self.calls.append(("create_revision", (user_request, job_id)))
        return {"revision_id": "rev-new", "user_request": user_request, "status": "created"}

    async def accept_revision(self, revision_id: str) -> JobStatus:
        self.calls.append(("accept_revision", revision_id))
        return JobStatus(job_id="job-1", status="running")

    def reject_revision(self, revision_id: str, reason: str = "") -> dict[str, object]:
        self.calls.append(("reject_revision", (revision_id, reason)))
        return {"revision_id": revision_id, "status": "rejected", "reason": reason}

    async def chat(self, message: str) -> dict[str, object]:
        self.calls.append(("chat", message))
        return {"message": f"reply:{message}", "commands": []}

    async def build_generated_code(self) -> BuildResult:
        self.calls.append(("build_generated_code", None))
        return BuildResult(success=False, errors="No generated code directory in current state.")

    async def run_simulation(self, *, events: int = 1000) -> SimulationResult:
        self.calls.append(("run_simulation", events))
        return SimulationResult(success=False, errors="No built executable in current state.")

    async def step(self) -> PhaseResult:
        self.calls.append(("step", None))
        return PhaseResult(phase="context", success=True, status=self.get_status())

    async def start_job(
        self,
        query: str,
        *,
        run_mode: str = "strict",
        auto_continue: bool = True,
        briefing_context: dict[str, object] | None = None,
    ) -> JobStatus:
        self.calls.append(("start_job", (query, run_mode, auto_continue, briefing_context)))
        return JobStatus(job_id="job-new", user_query=query, status="running")

    def resume_job(self, job_id: str, *, clear_failure: bool = False) -> JobStatus:
        self.calls.append(("resume_job", (job_id, clear_failure)))
        return JobStatus(job_id=job_id, status="running")

    def continue_in_background(self, *, reason: str = "") -> bool:
        self.calls.append(("continue_in_background", reason))
        return True

    async def run_until_blocked(self) -> JobStatus:
        self.calls.append(("run_until_blocked", None))
        return JobStatus(job_id="job-resumed", status="paused")

    async def submit_confirmation(
        self,
        response: dict[str, object],
        *,
        auto_continue: bool = True,
    ) -> JobStatus:
        self.calls.append(("submit_confirmation", (response, auto_continue)))
        decision = str(response.get("user_decision", ""))
        return JobStatus(
            job_id="job-1",
            status="running" if decision == "approve" else "paused",
        )

    async def submit_repair_continuation(
        self,
        response: dict[str, object],
        *,
        auto_continue: bool = True,
    ) -> JobStatus:
        self.calls.append(("submit_repair_continuation", (response, auto_continue)))
        decision = str(response.get("user_decision", ""))
        return JobStatus(
            job_id="job-1",
            status="running" if decision == "approve" else "failed",
            current_phase="g4_codegen",
            current_phase_idx=PIPELINE_PHASES.index("g4_codegen"),
            state={
                "repair_continuation_status": (
                    "approved" if decision == "approve" else "rejected"
                )
            },
        )


def test_command_catalog_covers_tui_commands() -> None:
    catalog = build_command_catalog()
    names = {row["name"] for row in catalog}

    assert set(
        """
        "run",
        "approve",
        "check",
        "open",
        "report",
        "demo",
        "help",
        "history",
        "jobs",
        "job",
        "artifacts",
        "inspect",
        "status",
        "mode",
        "resume",
        "retry",
        "revise",
        "revisions",
        "artifact",
        "build",
        "chat",
        "confirm",
        "credibility",
        "exit",
        "gates",
        "logs",
        "memory",
        "model",
        "model-health",
        "options",
        "project",
        "projects",
        "accept-revision",
        "ask-more",
        "reject-revision",
        "reject",
        "revision",
        "simulate",
        "step",
        """.replace('"', "").replace(",", "").split()
    ).issubset(names)
    assert "workbench" not in names
    assert "visual-approve" not in names
    assert "visual-reject" not in names
    for row in catalog:
        assert row["tip"].strip(), row
        assert row["module"].strip(), row
        assert row["connection"] in {"service", "derived", "panel", "alias", "client"}
        assert isinstance(row["visible"], bool)


def test_command_catalog_hides_low_value_or_duplicate_commands() -> None:
    catalog = {row["name"]: row for row in build_command_catalog()}

    assert catalog["run"]["visible"] is True
    assert catalog["run"]["connection"] == "service"
    assert catalog["build"]["module"] == "codegen/build"
    assert catalog["report"]["connection"] == "derived"
    assert catalog["report"]["visible"] is True

    for name in {"demo", "history", "inspect", "mode", "options", "exit"}:
        assert catalog[name]["visible"] is False
        assert catalog[name]["tip"].strip()


@pytest.mark.asyncio
async def test_dispatch_panel_commands_return_json_safe_payloads() -> None:
    service = FakeService()

    status = await dispatch_web_command(service, "/status")
    jobs = await dispatch_web_command(service, "/jobs")
    logs = await dispatch_web_command(service, "/logs")

    assert status["ok"] is True
    assert status["command"] == "status"
    assert status["view"] == "status"
    assert status["data"]["job_id"] == "job-1"
    assert jobs["data"] == [{"job_id": "job-1", "status": "paused"}]
    assert logs["data"][0]["event_type"] == "job_started"
    assert service.calls == [
        ("get_status", None),
        ("list_jobs", True),
        ("recent_events", 80),
    ]


@pytest.mark.asyncio
async def test_dispatch_plain_text_uses_chat_service() -> None:
    service = FakeService()

    result = await dispatch_web_command(service, "explain the current run")

    assert result["ok"] is True
    assert result["command"] == "chat"
    assert result["view"] == "timeline"
    assert result["data"]["message"] == "reply:explain the current run"
    assert service.calls == [("chat", "explain the current run")]


@pytest.mark.asyncio
async def test_dispatch_job_and_artifact_detail_commands_use_service_data() -> None:
    service = FakeService()

    job = await dispatch_web_command(service, "/job job-7")
    artifact = await dispatch_web_command(service, "/artifact /tmp/report.md")

    assert job["ok"] is True
    assert job["view"] == "job"
    assert job["data"]["job_id"] == "job-7"
    assert artifact["ok"] is True
    assert artifact["view"] == "artifact"
    assert artifact["data"]["text"] == "artifact body"
    assert service.calls == [
        ("get_job", "job-7"),
        ("read_artifact", ("/tmp/report.md", 200_000)),
    ]


@pytest.mark.asyncio
async def test_dispatch_inspector_commands_use_service_data() -> None:
    service = FakeService()

    tools = await dispatch_web_command(service, "/check")
    model = await dispatch_web_command(service, "/model")
    model_health = await dispatch_web_command(service, "/model-health")
    projects = await dispatch_web_command(service, "/projects")
    gates = await dispatch_web_command(service, "/gates")
    confirm = await dispatch_web_command(service, "/confirm")
    diagnosis = await dispatch_web_command(service, "/diagnose")
    credibility = await dispatch_web_command(service, "/credibility")
    memory = await dispatch_web_command(service, "/memory")
    revisions = await dispatch_web_command(service, "/revisions")
    help_result = await dispatch_web_command(service, "/help")

    assert tools["data"]["tools"]["geant4"]["available"] is True
    assert model["data"]["tiers"]["pro"]["model_name"] == "mimo-pro"
    assert model_health["view"] == "model-health"
    assert model_health["data"]["tiers"]["pro"]["latency_ms"] == 42.5
    assert projects["data"] == [{"slug": "default", "name": "Default"}]
    assert gates["data"] == [{"gate_id": 20, "status": "pass"}]
    assert confirm["data"]["status"] == "pending"
    assert diagnosis["view"] == "diagnosis"
    assert diagnosis["data"]["ui_state"] == "modeling_failed"
    assert credibility["data"]["score"] == 0.91
    assert memory["data"]["summary"] == "workflow memory"
    assert revisions["data"] == [{"revision_id": "rev-1", "status": "draft"}]
    assert {row["name"] for row in help_result["data"]} >= {"run", "jobs", "model"}
    assert service.calls == [
        ("get_startup_status", None),
        ("get_model_config", None),
        ("test_model_health", None),
        ("list_projects", None),
        ("get_gate_results", None),
        ("get_confirmation_review", None),
        ("get_workflow_diagnosis", None),
        ("get_credibility_report", None),
        ("get_workflow_context", None),
        ("list_revisions", None),
    ]


@pytest.mark.asyncio
async def test_dispatch_confirm_can_open_selected_job_review() -> None:
    service = FakeService()

    result = await dispatch_web_command(service, "/confirm job-7")

    assert result["ok"] is True
    assert result["view"] == "confirmation"
    assert result["data"]["status"] == "pending"
    assert service.calls == [("get_confirmation_review", "job-7")]


@pytest.mark.asyncio
async def test_dispatch_workflow_operation_commands_use_service_methods() -> None:
    service = FakeService()

    build = await dispatch_web_command(service, "/build")
    simulate = await dispatch_web_command(service, "/simulate 25")
    step = await dispatch_web_command(service, "/step")

    assert build["view"] == "build"
    assert build["data"]["errors"] == "No generated code directory in current state."
    assert simulate["view"] == "simulation"
    assert simulate["data"]["errors"] == "No built executable in current state."
    assert step["view"] == "status"
    assert step["data"]["phase"] == "context"
    assert service.calls == [
        ("build_generated_code", None),
        ("run_simulation", 25),
        ("step", None),
        ("get_status", None),
    ]


@pytest.mark.asyncio
async def test_dispatch_build_and_simulate_can_target_saved_job() -> None:
    class TargetJobService(FakeService):
        def __init__(self) -> None:
            super().__init__()
            self.state = {}

        def resume_job(self, job_id: str, *, clear_failure: bool = False) -> JobStatus:
            self.calls.append(("resume_job", (job_id, clear_failure)))
            self.state["job_id"] = job_id
            self.state["generated_code_dir"] = f"/workspace/jobs/{job_id}/06_patch/geant4_project"
            self.state["_executable_path"] = f"/workspace/jobs/{job_id}/06_patch/geant4_project/build/radagent"
            return JobStatus(job_id=job_id, status="completed", state=dict(self.state))

        async def build_generated_code(self) -> BuildResult:
            self.calls.append(("build_generated_code", self.state.get("job_id")))
            return BuildResult(success=True, executable_path=str(self.state.get("_executable_path", "")))

        async def run_simulation(self, *, events: int = 1000) -> SimulationResult:
            self.calls.append(("run_simulation", (events, self.state.get("job_id"))))
            return SimulationResult(success=True, events=events, output_dir="/workspace/output")

    service = TargetJobService()

    build = await dispatch_web_command(service, "/build job-saved")
    simulation = await dispatch_web_command(service, "/simulate 25 job-saved")

    assert build["view"] == "build"
    assert build["data"]["success"] is True
    assert simulation["view"] == "simulation"
    assert simulation["data"]["success"] is True
    assert service.calls == [
        ("resume_job", ("job-saved", False)),
        ("build_generated_code", "job-saved"),
        ("resume_job", ("job-saved", False)),
        ("run_simulation", (25, "job-saved")),
    ]


@pytest.mark.asyncio
async def test_dispatch_removed_native_visual_workbench_commands_are_unavailable() -> None:
    service = FakeService()

    workbench = await dispatch_web_command(service, "/workbench 12")
    visual_approve = await dispatch_web_command(service, "/visual-approve")
    visual_reject = await dispatch_web_command(service, "/visual-reject needs a clearer image")

    assert workbench["ok"] is False
    assert visual_approve["ok"] is False
    assert visual_reject["ok"] is False
    assert service.calls == []


@pytest.mark.asyncio
async def test_dispatch_operation_failures_stay_in_operation_views() -> None:
    class FailingOperationService(FakeService):
        async def build_generated_code(self) -> BuildResult:
            self.calls.append(("build_generated_code", None))
            raise RuntimeError("No generated code directory in current state.")

        async def run_simulation(self, *, events: int = 1000) -> SimulationResult:
            self.calls.append(("run_simulation", events))
            raise RuntimeError("No built executable in current state.")

    service = FailingOperationService()

    build = await dispatch_web_command(service, "/build")
    simulation = await dispatch_web_command(service, "/simulate 25")

    assert build["ok"] is True
    assert build["view"] == "build"
    assert build["data"] == {
        "success": False,
        "configure": {},
        "build": {},
        "executable_path": "",
        "errors": "No generated code directory in current state.",
    }
    assert simulation["ok"] is True
    assert simulation["view"] == "simulation"
    assert simulation["data"] == {
        "success": False,
        "output_dir": "",
        "log": "",
        "errors": "No built executable in current state.",
    }


@pytest.mark.asyncio
async def test_dispatch_run_resume_retry_commands_use_service_methods() -> None:
    service = FakeService()

    run = await dispatch_web_command(service, "/run build a detector")
    resume = await dispatch_web_command(service, "/resume job-4")
    retry = await dispatch_web_command(service, "/retry job-5")

    assert run["view"] == "status"
    assert run["data"]["job_id"] == "job-new"
    assert resume["data"]["job_id"] == "job-4"
    assert retry["data"]["job_id"] == "job-5"
    assert service.calls == [
        ("start_job", ("build a detector", "strict", True, None)),
        ("resume_job", ("job-4", False)),
        ("resume_job", ("job-5", True)),
        ("continue_in_background", "retry"),
    ]


@pytest.mark.asyncio
async def test_dispatch_retry_without_job_id_uses_active_job() -> None:
    service = FakeService()

    retry = await dispatch_web_command(service, "/retry")

    assert retry["view"] == "status"
    assert retry["data"]["job_id"] == "job-1"
    assert service.calls == [
        ("get_status", None),
        ("resume_job", ("job-1", True)),
        ("continue_in_background", "retry"),
    ]


@pytest.mark.asyncio
async def test_dispatch_confirmation_decision_commands_use_service_methods() -> None:
    service = FakeService()

    approve = await dispatch_web_command(service, "/confirm approve")
    reject = await dispatch_web_command(service, "/reject missing detector dimensions")
    ask_more = await dispatch_web_command(service, "/ask-more clarify the source energy")

    assert approve["view"] == "status"
    assert approve["data"]["status"] == "running"
    assert reject["data"]["status"] == "paused"
    assert ask_more["data"]["status"] == "paused"
    assert service.calls == [
        (
            "submit_confirmation",
            (
                {"user_decision": "approve", "feedback": "approve"},
                False,
            ),
        ),
        ("continue_in_background", "requirements_review_approved"),
        (
            "submit_confirmation",
            (
                {
                    "user_decision": "reject",
                    "feedback": "missing detector dimensions",
                },
                False,
            ),
        ),
        (
            "submit_confirmation",
            (
                {
                    "user_decision": "ask_more",
                    "feedback": "clarify the source energy",
                },
                False,
            ),
        ),
    ]


@pytest.mark.asyncio
async def test_dispatch_affirmative_requirements_supplement_continues_in_background() -> None:
    class RequirementsReviewService(FakeService):
        async def submit_confirmation(
            self,
            response: dict[str, object],
            *,
            auto_continue: bool = True,
        ) -> JobStatus:
            self.calls.append(("submit_confirmation", (response, auto_continue)))
            return JobStatus(
                job_id="job-1",
                status="running",
                current_phase="g4_modeling",
                current_phase_idx=PIPELINE_PHASES.index("g4_modeling"),
                state={
                    "requirements_review_status": "approved",
                    "confirmation_status": "approved",
                },
            )

    service = RequirementsReviewService()

    result = await dispatch_web_command(service, "/ask-more 全部按照你的推荐")

    assert result["view"] == "status"
    assert result["data"]["status"] == "running"
    assert service.calls == [
        (
            "submit_confirmation",
            (
                {"user_decision": "ask_more", "feedback": "全部按照你的推荐"},
                False,
            ),
        ),
        ("continue_in_background", "requirements_review_approved"),
    ]


@pytest.mark.asyncio
async def test_dispatch_scoped_confirmation_actions_resume_target_job() -> None:
    service = FakeService()

    approve = await dispatch_web_command(service, "/confirm --job=job-7 approve")
    ask_more = await dispatch_web_command(
        service,
        "/ask-more --job=job-8 clarify source energy\n"
        'RADAGENT_CONFIRMATION_JSON: {"confirmed_parameters": []}',
    )
    reject = await dispatch_web_command(service, "/reject --job=job-9 missing detector dimensions")

    assert approve["view"] == "status"
    assert ask_more["view"] == "status"
    assert reject["view"] == "status"
    assert service.calls == [
        ("resume_job", ("job-7", False)),
        (
            "submit_confirmation",
            (
                {"user_decision": "approve", "feedback": "approve"},
                False,
            ),
        ),
        ("continue_in_background", "requirements_review_approved"),
        ("resume_job", ("job-8", False)),
        (
            "submit_confirmation",
            (
                {
                    "user_decision": "ask_more",
                    "feedback": (
                        "clarify source energy\n"
                        'RADAGENT_CONFIRMATION_JSON: {"confirmed_parameters": []}'
                    ),
                },
                False,
            ),
        ),
        ("resume_job", ("job-9", False)),
        (
            "submit_confirmation",
            (
                {
                    "user_decision": "reject",
                    "feedback": "missing detector dimensions",
                },
                False,
            ),
        ),
    ]


@pytest.mark.asyncio
async def test_dispatch_repair_continuation_commands_use_repair_endpoint() -> None:
    class RepairContinuationService(FakeService):
        def __init__(self) -> None:
            super().__init__()
            self.state = {
                "repair_continuation_status": "pending",
                "repair_continuation_request": {
                    "status": "pending",
                    "increment_turns": 12,
                    "requested_total_turns": 60,
                },
            }

        async def submit_repair_continuation(
            self,
            response: dict[str, object],
            *,
            auto_continue: bool = True,
        ) -> JobStatus:
            result = await super().submit_repair_continuation(
                response,
                auto_continue=auto_continue,
            )
            self.state["repair_continuation_status"] = result.state[
                "repair_continuation_status"
            ]
            self.state["repair_continuation_request"]["status"] = result.state[
                "repair_continuation_status"
            ]
            return result

    service = RepairContinuationService()

    approve = await dispatch_web_command(service, "/approve")
    reject = await dispatch_web_command(service, "/reject stop")

    assert approve["view"] == "status"
    assert approve["data"]["state"]["repair_continuation_status"] == "approved"
    assert reject["view"] == "status"
    assert reject["data"]["status"] == "paused"
    assert service.calls == [
        (
            "submit_repair_continuation",
            ({"user_decision": "approve", "feedback": "approve"}, False),
        ),
        ("continue_in_background", "repair_continuation_approved"),
        (
            "submit_confirmation",
            ({"user_decision": "reject", "feedback": "stop"}, False),
        ),
    ]


@pytest.mark.asyncio
async def test_dispatch_repeated_approve_does_not_continue_background() -> None:
    class AlreadyApprovedService(FakeService):
        async def submit_confirmation(
            self,
            response: dict[str, object],
            *,
            auto_continue: bool = True,
        ) -> JobStatus:
            self.calls.append(("submit_confirmation", (response, auto_continue)))
            return JobStatus(
                job_id="job-1",
                status="paused",
                current_phase="gate",
                current_phase_idx=7,
                completed_phases=[
                    "prepare_workspace",
                    "context",
                    "task_planning",
                    "g4_modeling",
                    "human_confirmation",
                    "g4_codegen",
                    "patch",
                ],
                key_statuses={"confirmation_status": "approved"},
            )

    service = AlreadyApprovedService()

    result = await dispatch_web_command(service, "/approve")

    assert result["ok"] is True
    assert result["data"]["current_phase"] == "gate"
    assert service.calls == [
        (
            "submit_confirmation",
            (
                {"user_decision": "approve", "feedback": "approve"},
                False,
            ),
        )
    ]


@pytest.mark.asyncio
async def test_dispatch_approve_does_not_continue_background_after_failed_status() -> None:
    class FailedApprovalService(FakeService):
        async def submit_confirmation(
            self,
            response: dict[str, object],
            *,
            auto_continue: bool = True,
        ) -> JobStatus:
            self.calls.append(("submit_confirmation", (response, auto_continue)))
            return JobStatus(
                job_id="job-1",
                status="failed",
                current_phase="requirements_review",
                current_phase_idx=PIPELINE_PHASES.index("requirements_review"),
                state={"termination_reason": "g4_modeling status is failed"},
                key_statuses={"g4_modeling_status": "failed"},
            )

    service = FailedApprovalService()

    result = await dispatch_web_command(service, "/approve")

    assert result["ok"] is True
    assert result["data"]["status"] == "failed"
    assert service.calls == [
        (
            "submit_confirmation",
            (
                {"user_decision": "approve", "feedback": "approve"},
                False,
            ),
        )
    ]


def test_confirmation_review_includes_structured_request_and_proposal(tmp_path: Path) -> None:
    from agent_core.app.service import RadAgentAppService

    service = RadAgentAppService(workspace_root=tmp_path)
    job_dir = tmp_path / "jobs" / "job-1"
    confirmation_dir = job_dir / STAGE_HUMAN_CONFIRMATION
    confirmation_dir.mkdir(parents=True)
    request_path = confirmation_dir / "confirmation_request_round_1.json"
    proposal_path = confirmation_dir / "proposed_model_completion.json"
    report_path = confirmation_dir / "human_confirmation_report.md"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": "confirmation_request_v1",
                "job_id": "job-1",
                "summary_for_user": "确认水箱几何尺寸。",
                "questions": [{"field_path": "components.water_tank.geometry"}],
                "critical_confirmations": [{"field_path": "components.water_tank.geometry"}],
            }
        ),
        encoding="utf-8",
    )
    proposal_path.write_text(
        json.dumps(
            {
                "schema_version": "proposed_model_completion_v1",
                "job_id": "job-1",
                "missing_information": ["Beam spot size was not specified."],
            }
        ),
        encoding="utf-8",
    )
    report_path.write_text("confirmation report", encoding="utf-8")
    service.state.update(
        {
            "job_id": "job-1",
            "job_workspace": str(job_dir),
            "confirmation_status": "pending",
            "human_confirmation_required": True,
        }
    )

    review = service.get_confirmation_review()

    assert review["status"] == "pending"
    assert review["request_path"] == str(request_path)
    assert review["confirmation_request"]["summary_for_user"] == "确认水箱几何尺寸。"
    assert review["proposed_model_completion"]["missing_information"] == [
        "Beam spot size was not specified."
    ]
    assert review["summary"] == "确认水箱几何尺寸。"
    assert review["summary_for_user"] == "确认水箱几何尺寸。"
    assert review["questions"] == [{"field_path": "components.water_tank.geometry"}]
    assert review["critical_confirmations"] == [{"field_path": "components.water_tank.geometry"}]
    assert review["missing_information"] == ["Beam spot size was not specified."]
    assert review["preview"] == "confirmation report"


@pytest.mark.asyncio
async def test_dispatch_project_and_revision_commands_use_service_methods() -> None:
    service = FakeService()

    project = await dispatch_web_command(service, "/project default")
    revise = await dispatch_web_command(service, "/revise tighten detector spacing")
    revision = await dispatch_web_command(service, "/revision rev-1")
    accept = await dispatch_web_command(service, "/accept-revision rev-1")
    reject = await dispatch_web_command(service, "/reject-revision rev-1")
    approve = await dispatch_web_command(service, "/approve")

    assert project["view"] == "projects"
    assert project["data"]["slug"] == "default"
    assert revise["view"] == "revision"
    assert revise["data"]["revision_id"] == "rev-new"
    assert revision["view"] == "revision"
    assert revision["data"]["revision_id"] == "rev-1"
    assert accept["view"] == "status"
    assert accept["data"]["status"] == "running"
    assert reject["view"] == "revision"
    assert reject["data"]["status"] == "rejected"
    assert approve["view"] == "status"
    assert service.calls == [
        ("set_current_project", "default"),
        ("create_revision", ("tighten detector spacing", None)),
        ("list_revisions", None),
        ("accept_revision", "rev-1"),
        ("reject_revision", ("rev-1", "")),
        (
            "submit_confirmation",
            (
                {"user_decision": "approve", "feedback": "approve"},
                False,
            ),
        ),
        ("continue_in_background", "requirements_review_approved"),
    ]


@pytest.mark.asyncio
async def test_dispatch_workbench_shell_commands_return_structured_panels() -> None:
    service = FakeService()

    open_report = await dispatch_web_command(service, "/open report")
    report = await dispatch_web_command(service, "/report")
    history = await dispatch_web_command(service, "/history")
    mode = await dispatch_web_command(service, "/mode inspect")
    demo = await dispatch_web_command(service, "/demo geant4")
    exit_result = await dispatch_web_command(service, "/exit")

    assert open_report["ok"] is True
    assert open_report["view"] == "artifacts"
    assert open_report["data"]["target"] == "report"
    assert report["view"] == "report"
    assert history["view"] == "history"
    assert mode["view"] == "mode"
    assert mode["data"] == {"mode": "inspect"}
    assert demo["view"] == "demo"
    assert demo["data"]["command"] == "/run demo:geant4"
    assert exit_result["view"] == "exit"
    assert service.calls == [
        ("list_artifacts", None),
        ("list_artifacts", None),
    ]


def test_create_api_handler_serves_commands_and_dispatch() -> None:
    from agent_core.web.server import create_api_handler

    service = FakeService()
    handler = create_api_handler(service)

    commands_status, commands_body = handler("GET", "/api/commands", b"")
    command_status, command_body = handler(
        "POST",
        "/api/command",
        b'{"text": "/status"}',
    )

    assert commands_status == 200
    assert {row["name"] for row in commands_body["commands"]} >= {"run", "status", "jobs"}
    assert command_status == 200
    assert command_body["ok"] is True
    assert command_body["command"] == "status"
    assert command_body["data"]["job_id"] == "job-1"


def test_create_api_handler_serves_home_summary_from_service_data() -> None:
    from agent_core.web.server import create_api_handler

    class HomeService(FakeService):
        def list_projects(self) -> list[dict[str, object]]:
            self.calls.append(("list_projects", None))
            return [
                {"slug": "default", "name": "Detector Workflows"},
                {"slug": "space", "name": "Space Radiation"},
            ]

        def list_jobs(self, *, include_all_projects: bool = False) -> list[dict[str, object]]:
            self.calls.append(("list_jobs", include_all_projects))
            return [
                {
                    "job_id": "job-complete",
                    "status": "completed",
                    "user_query": "HPGe detector response workflow",
                    "project_name": "Detector Workflows",
                    "current_phase": "report",
                    "updated_at": "2026-06-13 09:12:00",
                },
                {
                    "job_id": "job-paused",
                    "status": "paused",
                    "user_query": "Space radiation dose estimate",
                    "project_name": "Space Radiation",
                    "current_phase": "gate_validation",
                    "updated_at": "2026-06-12 18:20:00",
                },
            ]

        def list_artifacts(self, job_id: str | None = None) -> list[object]:
            self.calls.append(("list_artifacts", job_id))
            if job_id == "job-complete":
                return [
                    {"job_id": job_id, "path": "/tmp/final_report.md", "kind": "report"},
                    {"job_id": job_id, "path": "/tmp/geometry.cc", "kind": "source"},
                ]
            if job_id == "job-paused":
                return [{"job_id": job_id, "path": "/tmp/gate.json", "kind": "gate"}]
            return []

    service = HomeService()
    handler = create_api_handler(service)

    status, body = handler("GET", "/api/home", b"")

    assert status == 200
    assert body["home"]["metrics"] == {
        "projects": 2,
        "jobs": 2,
        "completed_jobs": 1,
        "active_jobs": 1,
        "artifacts": 3,
    }
    assert body["home"]["projects"] == []
    assert body["home"]["showcase_examples"][0]["id"] == "example-hpge-coincidence"
    assert "Geant4" in body["home"]["showcase_examples"][0]["prompt"]
    assert body["home"]["showcase_examples"][0]["difficulty"] == "advanced"
    assert {row["name"] for row in body["home"]["workflow_capabilities"]} == {
        "需求捕获 / Intent capture",
        "物理模型 / Physics model IR",
        "门禁审核 / Gate review",
        "代码生成 / Code generation",
        "构建模拟 / Build and simulation",
        "产物修订 / Artifacts and revisions",
    }
    assert service.calls == [
        ("list_projects", None),
        ("list_jobs", True),
        ("list_artifacts", "job-complete"),
        ("list_artifacts", "job-paused"),
    ]


def test_create_api_handler_serves_job_and_artifact_detail() -> None:
    from agent_core.web.server import create_api_handler

    service = FakeService()
    handler = create_api_handler(service)

    job_status, job_body = handler("POST", "/api/job", b'{"job_id": "job-3"}')
    artifact_status, artifact_body = handler(
        "POST",
        "/api/artifact",
        b'{"path": "/tmp/report.md", "max_chars": 1200}',
    )

    assert job_status == 200
    assert job_body["job"]["job_id"] == "job-3"
    assert artifact_status == 200
    assert artifact_body["artifact"]["text"] == "artifact body"
    assert service.calls == [
        ("get_job", "job-3"),
        ("read_artifact", ("/tmp/report.md", 1200)),
    ]


def test_create_api_handler_serves_active_job_artifact_list() -> None:
    from agent_core.web.server import create_api_handler

    service = FakeService()
    handler = create_api_handler(service)

    status, body = handler("GET", "/api/artifacts?job_id=job-7", b"")

    assert status == 200
    assert body["artifacts"] == [
        {"job_id": "job-7", "path": "/tmp/report.md", "kind": "report"}
    ]
    assert service.calls == [("list_artifacts", "job-7")]


def test_create_api_handler_serves_generated_source_package_download() -> None:
    from agent_core.web.server import create_api_handler

    service = FakeService()
    handler = create_api_handler(service)

    status, headers, body = handler("GET", "/api/source-package?job_id=job-7", b"")

    assert status == 200
    assert headers["Content-Type"] == "application/zip"
    assert headers["Content-Disposition"] == 'attachment; filename="job-1_geant4_source.zip"'
    assert body == b"PK\x03\x04zip"
    assert service.calls == [("package_generated_source_files", "job-7")]


def test_create_api_handler_serves_visualization_payload() -> None:
    from agent_core.web.server import create_api_handler

    service = FakeService()
    handler = create_api_handler(service)

    status, body = handler("GET", "/api/visualization?job_id=job-visual", b"")

    assert status == 200
    assert body["visualization"]["status"] == "ready"
    assert body["visualization"]["source"]["visual_events"] == 100
    assert body["visualization"]["tracks"][0]["points_mm"][-1] == [0, 0, 1]
    assert service.calls == [("get_visualization_payload", "job-visual")]


def test_create_api_handler_rejects_missing_artifact_path() -> None:
    from agent_core.web.server import create_api_handler

    handler = create_api_handler(FakeService())

    status, body = handler("POST", "/api/artifact", b"{}")

    assert status == 400
    assert body["ok"] is False
    assert body["error"] == "Missing artifact path."


def test_create_api_handler_updates_model_config_without_echoing_api_key() -> None:
    from agent_core.web.server import create_api_handler

    service = FakeService()
    handler = create_api_handler(service)

    status, body = handler(
        "POST",
        "/api/model",
        b'{"base_url":"https://api.example.test/v1","api_key":"secret-key","api_key_env":"RADAGENT_API_KEY","pro_model":"rad-pro"}',
    )

    assert status == 200
    assert body["model"]["tiers"]["pro"]["model_name"] == "rad-pro"
    assert "secret-key" not in json.dumps(body)
    assert service.calls == [
        (
            "update_model_config",
            {
                "base_url": "https://api.example.test/v1",
                "api_key": "secret-key",
                "api_key_env": "RADAGENT_API_KEY",
                "pro_model": "rad-pro",
            },
        )
    ]


def test_create_api_handler_serves_model_health_without_secrets() -> None:
    from agent_core.web.server import create_api_handler

    service = FakeService()
    handler = create_api_handler(service)

    status, body = handler("POST", "/api/model/health", b"")

    assert status == 200
    assert body["health"]["tiers"]["pro"]["status"] == "ok"
    assert body["health"]["tiers"]["pro"]["latency_ms"] == 42.5
    assert "secret" not in json.dumps(body).lower()
    assert service.calls == [("test_model_health", None)]


def test_create_api_handler_forwards_agentic_repair_turn_config() -> None:
    from agent_core.web.server import create_api_handler

    service = FakeService()
    handler = create_api_handler(service)

    status, _body = handler(
        "POST",
        "/api/model",
        b'{"agentic_repair_max_turns":12,"agentic_repair_history_chars":36000,"ignored":"x"}',
    )

    assert status == 200
    assert service.calls[-1] == (
        "update_model_config",
        {"agentic_repair_max_turns": 12, "agentic_repair_history_chars": 36000},
    )


def test_build_server_serves_api_over_http(tmp_path) -> None:
    from agent_core.web.server import build_server

    static_root = tmp_path / "dist"
    static_root.mkdir()
    (static_root / "index.html").write_text("<div>RadAgent</div>", encoding="utf-8")
    server = build_server(
        host="127.0.0.1",
        port=0,
        static_root=static_root,
        service=FakeService(),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        with urllib.request.urlopen(f"http://{host}:{port}/api/commands", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert {row["name"] for row in payload["commands"]} >= {"run", "status", "jobs"}


def test_build_server_creates_default_service_in_server_thread(monkeypatch, tmp_path) -> None:
    from agent_core.web import server as web_server

    captured: dict[str, object] = {}

    class CapturingService(FakeService):
        def __init__(self, *, execution_mode: str, env_path) -> None:
            super().__init__()
            captured["execution_mode"] = execution_mode
            captured["env_path"] = env_path
            captured["thread_id"] = threading.get_ident()

    monkeypatch.setattr(web_server, "RadAgentAppService", CapturingService)
    env_path = tmp_path / "web.env"
    server = web_server.build_server(
        host="127.0.0.1",
        port=0,
        static_root=tmp_path,
        env_path=env_path,
    )
    assert captured == {}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        with urllib.request.urlopen(f"http://{host}:{port}/api/status", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert payload["status"]["job_id"] == "job-1"
        assert captured == {
            "execution_mode": "strict",
            "env_path": env_path,
            "thread_id": thread.ident,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
