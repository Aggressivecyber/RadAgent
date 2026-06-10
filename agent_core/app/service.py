from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_core.app.schemas import (
    ArtifactContent,
    ArtifactSummary,
    BuildResult,
    ChatResponse,
    JobStatus,
    ModelConfigUpdate,
    ModelConfigView,
    ModelTierConfig,
    PhaseResult,
    RadAgentEvent,
    SimulationResult,
)
from agent_core.config.environment import (
    DEFAULT_ENV_PATH,
    load_environment,
    write_project_env_values,
)
from agent_core.gates.gate_runner import normalize_run_mode
from agent_core.models.registry import thinking_for_task
from agent_core.models.schemas import ModelTask, ModelTier
from agent_core.pipeline import PIPELINE_PHASES
from agent_core.storage import RadAgentStore
from agent_core.workspace.manager import WorkspaceManager
from agent_core.workspace.paths import STAGE_INPUT

logger = logging.getLogger(__name__)

VALID_MODES = frozenset({"strict", "test", "acceptance", "production"})
TEXT_ARTIFACT_SUFFIXES = {
    ".cc",
    ".cpp",
    ".csv",
    ".h",
    ".hh",
    ".hpp",
    ".json",
    ".jsonl",
    ".log",
    ".mac",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
}

EventCallback = Callable[[RadAgentEvent], None]


class RadAgentAppService:
    """UI-neutral facade for REPL, TUI, web, or API frontends.

    This class owns session state and emits structured events. It contains no
    Rich, prompt_toolkit, or Textual dependencies, so UI layers can render the
    same operations in terminal, TUI, web, or API frontends.
    """

    def __init__(
        self,
        *,
        execution_mode: str = "strict",
        workspace_root: Path | None = None,
        env_path: Path | None = None,
        event_callback: EventCallback | None = None,
    ) -> None:
        if execution_mode not in VALID_MODES:
            raise ValueError(f"Invalid execution_mode: {execution_mode}")
        self.execution_mode = execution_mode
        self.workspace = WorkspaceManager(root=workspace_root)
        self.env_path = env_path or DEFAULT_ENV_PATH
        self.store = RadAgentStore(workspace_root=self.workspace.root)
        self.state: dict[str, Any] = {}
        self.current_phase_idx = 0
        self.completed_phases: list[str] = []
        self.run_id = uuid4().hex
        self._subgraph_nodes: dict[str, Any] | None = None
        self._chat_agent: Any = None
        self._events: list[RadAgentEvent] = []
        self._event_callback = event_callback
        self._subscribers: list[asyncio.Queue[RadAgentEvent]] = []

    # ------------------------------------------------------------------
    # Model configuration
    # ------------------------------------------------------------------

    def get_model_config(self) -> ModelConfigView:
        """Return frontend-safe model configuration without exposing secrets."""
        env = load_environment(self.env_path)
        thinking_defaults = {
            ModelTier.LITE: thinking_for_task(ModelTask.INTENT_ROUTING),
            ModelTier.PRO: thinking_for_task(ModelTask.G4_MODELING),
            ModelTier.MAX: thinking_for_task(ModelTask.FINAL_REVIEW),
        }
        return ModelConfigView(
            env_path=str(self.env_path),
            default_api_key_env="RADAGENT_API_KEY",
            tiers={
                tier.value: ModelTierConfig(
                    tier=config.tier,
                    model_name=config.model_name,
                    base_url=config.base_url,
                    api_key_env=config.api_key_env,
                    api_key_configured=bool(os.getenv(config.api_key_env)),
                    timeout_s=config.timeout_s,
                    max_retries=config.max_retries,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    thinking_default=thinking_defaults.get(tier, False),
                )
                for tier, config in env.models.items()
            },
        )

    def update_model_config(
        self,
        update: ModelConfigUpdate | dict[str, Any],
    ) -> ModelConfigView:
        """Persist OpenAI-compatible model settings and refresh runtime profiles."""
        if not isinstance(update, ModelConfigUpdate):
            update = ModelConfigUpdate.model_validate(update)

        values: dict[str, str] = {}
        api_key_env = update.api_key_env.strip() or "RADAGENT_API_KEY"

        if update.base_url is not None:
            values["RADAGENT_MODEL_BASE_URL"] = update.base_url
        if update.api_key:
            values[api_key_env] = update.api_key
        if api_key_env:
            values["RADAGENT_LITE_API_KEY_ENV"] = api_key_env
            values["RADAGENT_PRO_API_KEY_ENV"] = api_key_env
            values["RADAGENT_MAX_API_KEY_ENV"] = api_key_env
        if update.lite_model is not None:
            values["RADAGENT_MODEL_LITE"] = update.lite_model
        if update.pro_model is not None:
            values["RADAGENT_MODEL_PRO"] = update.pro_model
        if update.max_model is not None:
            values["RADAGENT_MODEL_MAX"] = update.max_model
        if update.lite_timeout_s is not None:
            values["RADAGENT_LITE_TIMEOUT_S"] = str(update.lite_timeout_s)
        if update.pro_timeout_s is not None:
            values["RADAGENT_PRO_TIMEOUT_S"] = str(update.pro_timeout_s)
        if update.max_timeout_s is not None:
            values["RADAGENT_MAX_TIMEOUT_S"] = str(update.max_timeout_s)
        if update.lite_max_tokens is not None:
            values["RADAGENT_LITE_MAX_TOKENS"] = str(update.lite_max_tokens)
        if update.pro_max_tokens is not None:
            values["RADAGENT_PRO_MAX_TOKENS"] = str(update.pro_max_tokens)
        if update.max_max_tokens is not None:
            values["RADAGENT_MAX_MAX_TOKENS"] = str(update.max_max_tokens)

        if not values:
            return self.get_model_config()

        write_project_env_values(values, env_path=self.env_path, update_process_env=True)

        from agent_core.models.gateway import reset_model_gateway

        reset_model_gateway()
        self._chat_agent = None
        updated = self.get_model_config()
        self._emit(
            "model_config_updated",
            status="success",
            summary=str(updated.tiers[ModelTier.PRO.value].model_name),
            payload=updated.model_dump(mode="json"),
        )
        return updated

    # ------------------------------------------------------------------
    # Event stream
    # ------------------------------------------------------------------

    def recent_events(self, limit: int | None = None) -> list[RadAgentEvent]:
        if limit is None:
            return list(self._events)
        return self._events[-int(limit) :]

    async def subscribe_events(self) -> AsyncIterator[RadAgentEvent]:
        queue: asyncio.Queue[RadAgentEvent] = asyncio.Queue()
        self._subscribers.append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.remove(queue)

    def _emit(
        self,
        event_type: str,
        *,
        status: str = "info",
        summary: str = "",
        phase: str = "",
        payload: dict[str, Any] | None = None,
        job_id: str | None = None,
    ) -> RadAgentEvent:
        event = RadAgentEvent(
            event_type=event_type,
            status=status,  # type: ignore[arg-type]
            summary=summary,
            phase=phase,
            job_id=job_id or str(self.state.get("job_id", "")),
            run_id=self.run_id,
            payload=payload or {},
        )
        self._events.append(event)
        if self._event_callback:
            self._event_callback(event)
        for queue in self._subscribers:
            queue.put_nowait(event)
        if event.job_id:
            try:
                self.store.record_event(
                    job_id=event.job_id,
                    run_id=event.run_id,
                    event_type=event.event_type,
                    status=event.status,
                    phase=event.phase,
                    summary=event.summary,
                    payload=event.payload,
                )
            except Exception as exc:
                logger.debug("Failed to persist app event %s: %s", event.event_type, exc)
        return event

    # ------------------------------------------------------------------
    # Chat and intent
    # ------------------------------------------------------------------

    async def classify_intent(self, text: str) -> Any:
        from agent_core.intent.router import classify_intent_with_lite_model

        result = await classify_intent_with_lite_model(
            text,
            has_active_job=bool(self.state.get("job_id")),
        )
        self._emit(
            "intent_classified",
            summary=str(result.intent),
            payload=result.model_dump(),
        )
        return result

    async def chat(self, message: str) -> ChatResponse:
        agent = self._get_chat_agent()
        started = self._emit(
            "chat_started",
            status="running",
            summary=message[:120],
            payload={"message": message},
        )
        try:
            response = await agent.chat(message)
        except Exception as exc:
            self._emit("chat_failed", status="error", summary=str(exc))
            raise
        finished = self._emit(
            "chat_finished",
            status="success",
            summary=response[:120],
            payload={"message": response},
        )
        return ChatResponse(message=response, events=[started, finished])

    def _get_chat_agent(self) -> Any:
        if self._chat_agent is None:
            from agent_core.chat.agent import ChatAgent

            self._chat_agent = ChatAgent()
        return self._chat_agent

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    async def start_job(
        self,
        query: str,
        *,
        run_mode: str = "strict",
        auto_continue: bool = True,
    ) -> JobStatus:
        query = query.strip()
        if not query:
            raise ValueError("query must not be empty")
        self.state = {
            "user_query": query,
            "job_id": "",
            "errors": [],
            "retry_count": 0,
            "max_retries_reached": False,
            "execution_mode": self.execution_mode,
            "run_mode": run_mode,
            "skipped_gates": [],
        }
        self.current_phase_idx = 0
        self.completed_phases = []
        self.run_id = uuid4().hex
        if self._chat_agent is not None:
            self._chat_agent.reset()

        self._emit("job_started", status="running", summary=query[:160])
        if auto_continue:
            await self.run_until_blocked()
        else:
            await self.run_phase("prepare_workspace")
        return self.get_status()

    async def run_until_blocked(self) -> JobStatus:
        while self.current_phase_idx < len(PIPELINE_PHASES):
            phase = PIPELINE_PHASES[self.current_phase_idx]
            if phase == "human_confirmation" and not self.state.get("raw_human_response"):
                self._emit(
                    "human_confirmation_required",
                    status="warning",
                    phase=phase,
                    summary="Human confirmation is pending.",
                )
                return self.get_status()
            result = await self.run_phase(phase)
            if not result.success:
                return result.status
            if phase == "g4_modeling" and self.state.get("human_confirmation_required"):
                self._emit(
                    "human_confirmation_required",
                    status="warning",
                    phase=phase,
                    summary="Modeling produced assumptions requiring review.",
                    payload={
                        "unconfirmed_assumptions_count": self.state.get(
                            "unconfirmed_assumptions_count", 0
                        )
                    },
                )
                return self.get_status()
        self._emit("job_finished", status="success", summary="Pipeline complete.")
        return self.get_status()

    async def step(self) -> PhaseResult:
        if not self.state:
            raise RuntimeError("No active job. Start or resume a job first.")
        if self.current_phase_idx >= len(PIPELINE_PHASES):
            return PhaseResult(
                phase="",
                success=True,
                status=self.get_status(),
                events=self.recent_events(1),
            )
        phase = PIPELINE_PHASES[self.current_phase_idx]
        return await self.run_phase(phase)

    async def run_phase(self, phase: str) -> PhaseResult:
        if phase not in PIPELINE_PHASES:
            raise ValueError(f"Unknown phase: {phase}")
        started = self._emit(
            "phase_started",
            status="running",
            phase=phase,
            summary=f"Running {phase}",
        )
        try:
            if phase == "prepare_workspace":
                result = await self._exec_prepare_workspace()
            else:
                nodes = self._get_subgraph_nodes()
                result = await nodes[phase](self.state)
        except Exception as exc:
            failed = self._emit(
                "phase_failed",
                status="error",
                phase=phase,
                summary=str(exc),
            )
            logger.exception("Phase %s failed", phase)
            return PhaseResult(
                phase=phase,
                success=False,
                status=self.get_status(),
                events=[started, failed],
            )

        if result:
            self.state = {**self.state, **result}
        if phase not in self.completed_phases:
            self.completed_phases.append(phase)
        self.current_phase_idx = PIPELINE_PHASES.index(phase) + 1
        self._persist_phase_state(phase)
        finished = self._emit(
            "phase_finished",
            status="success",
            phase=phase,
            summary=f"Finished {phase}",
            payload=result or {},
        )
        return PhaseResult(
            phase=phase,
            success=True,
            state_delta=result or {},
            status=self.get_status(),
            events=[started, finished],
        )

    async def submit_confirmation(
        self,
        response: dict[str, Any],
        *,
        auto_continue: bool = True,
    ) -> JobStatus:
        if not self.state.get("job_id"):
            raise RuntimeError("No active job.")
        self.state["raw_human_response"] = response
        self._emit(
            "human_confirmation_submitted",
            status="info",
            phase="human_confirmation",
            summary=str(response.get("user_decision", "")),
            payload=response,
        )
        if self.current_phase_idx != PIPELINE_PHASES.index("human_confirmation"):
            self.current_phase_idx = PIPELINE_PHASES.index("human_confirmation")
        await self.run_phase("human_confirmation")
        if auto_continue:
            await self.run_until_blocked()
        return self.get_status()

    def _get_subgraph_nodes(self) -> dict[str, Any]:
        if self._subgraph_nodes is None:
            from agent_core.graph.main_graph import build_subgraph_nodes

            self._subgraph_nodes = build_subgraph_nodes()
        return self._subgraph_nodes

    async def _exec_prepare_workspace(self) -> dict[str, Any]:
        from agent_core.naming import build_job_id

        job_id = await build_job_id(
            str(self.state.get("job_id", "")),
            str(self.state.get("user_query", "")),
        )
        job = self.workspace.create_job(job_id)
        job.write_text(
            STAGE_INPUT,
            "user_query.md",
            f"# User Query\n\n{self.state.get('user_query', '')}\n",
        )

        run_mode = normalize_run_mode(str(self.state.get("run_mode", "strict")))
        execution_mode = run_mode if run_mode in VALID_MODES else self.execution_mode
        project = self.store.current_project()
        self.store.upsert_job(
            job_id=job_id,
            user_query=str(self.state.get("user_query", "")),
            project_id=str(project["id"]),
            status="running",
            current_phase="prepare_workspace",
            current_phase_idx=0,
            execution_mode=execution_mode,
            run_mode=run_mode,
            job_workspace=str(job.dir),
        )
        return {
            "job_id": job_id,
            "project_id": str(project["id"]),
            "run_mode": run_mode,
            "execution_mode": execution_mode,
            "workspace_root": str(self.workspace.root),
            "job_workspace": str(job.dir),
            "retry_count": 0,
            "max_retries_reached": False,
            "errors": [],
            "current_node": "prepare_workspace",
        }

    def _persist_phase_state(self, phase: str) -> None:
        job_id = str(self.state.get("job_id", ""))
        if not job_id:
            return
        status = "completed" if phase == "report" else "running"
        if self.state.get("confirmation_status") == "pending":
            status = "paused"
        self.store.save_state_snapshot(
            job_id=job_id,
            state=self.state,
            completed_phases=self.completed_phases,
            phase=phase,
            current_phase_idx=self.current_phase_idx,
            status=status,
        )
        self.record_state_artifacts(job_id)

    def record_state_artifacts(self, job_id: str | None = None) -> list[ArtifactSummary]:
        job_id = job_id or str(self.state.get("job_id", ""))
        for key, value in self.state.items():
            if not isinstance(value, str) or not value:
                continue
            if not (key.endswith("_path") or key.endswith("_dir")):
                continue
            path = Path(value)
            if not path.exists():
                continue
            stage = path.parent.name if path.is_file() else path.name
            self.store.record_artifact(job_id=job_id, path=str(path), stage=stage, kind=key)
        return self.list_artifacts(job_id)

    # ------------------------------------------------------------------
    # Resume and status
    # ------------------------------------------------------------------

    def get_status(self) -> JobStatus:
        current_phase = ""
        if self.current_phase_idx < len(PIPELINE_PHASES):
            current_phase = PIPELINE_PHASES[self.current_phase_idx]
        key_statuses = {
            key: self.state.get(key)
            for key in (
                "intent",
                "g4_modeling_status",
                "g4_codegen_status",
                "patch_status",
                "validation_status",
                "artifact_status",
                "confirmation_status",
                "termination_reason",
            )
            if self.state.get(key) is not None
        }
        status = "idle"
        if self.state.get("job_id"):
            status = "completed" if self.current_phase_idx >= len(PIPELINE_PHASES) else "running"
            if self.state.get("confirmation_status") == "pending":
                status = "paused"
        return JobStatus(
            job_id=str(self.state.get("job_id", "")),
            user_query=str(self.state.get("user_query", "")),
            status=status,
            current_phase=current_phase,
            current_phase_idx=self.current_phase_idx,
            completed_phases=list(self.completed_phases),
            execution_mode=str(self.state.get("execution_mode", self.execution_mode)),
            run_mode=str(self.state.get("run_mode", "strict")),
            workspace_root=str(self.state.get("workspace_root", self.workspace.root)),
            job_workspace=str(self.state.get("job_workspace", "")),
            needs_confirmation=bool(self.state.get("human_confirmation_required"))
            or self.state.get("confirmation_status") == "pending",
            key_statuses=key_statuses,
            state=dict(self.state),
        )

    def resume_job(self, job_id: str) -> JobStatus:
        snapshot = self.store.latest_state_snapshot(job_id)
        job = self.store.get_job(job_id)
        if snapshot is None and job is None:
            raise ValueError(f"Job not found: {job_id}")
        if snapshot is not None:
            self.state = dict(snapshot["state"])
            self.current_phase_idx = int(snapshot["current_phase_idx"])
            self.completed_phases = list(snapshot["completed_phases"])
        else:
            self.state = {
                "job_id": job["job_id"],
                "user_query": job["user_query"],
                "execution_mode": job["execution_mode"],
                "run_mode": job["run_mode"],
                "job_workspace": job["job_workspace"],
                "errors": [],
                "retry_count": 0,
                "max_retries_reached": False,
                "skipped_gates": [],
            }
            self.current_phase_idx = int(job["current_phase_idx"])
            self.completed_phases = list(PIPELINE_PHASES[: self.current_phase_idx])
        self.execution_mode = str(self.state.get("execution_mode", self.execution_mode))
        self._emit("job_resumed", status="success", summary=job_id)
        return self.get_status()

    def list_jobs(self, *, include_all_projects: bool = False) -> list[dict[str, Any]]:
        self.store.import_existing_jobs()
        return self.store.list_jobs(include_all_projects=include_all_projects)

    def list_projects(self) -> list[dict[str, Any]]:
        return self.store.list_projects()

    def current_project(self) -> dict[str, Any]:
        return self.store.current_project()

    def create_project(self, name: str) -> dict[str, Any]:
        project = self.store.create_project(name)
        self.store.set_current_project(str(project["id"]))
        self._emit("project_created", status="success", summary=str(project.get("slug", "")))
        return project

    def set_current_project(self, value: str) -> dict[str, Any]:
        project = self.store.set_current_project(value)
        if project is None:
            raise ValueError(f"Project not found: {value}")
        self._emit("project_switched", status="success", summary=str(project.get("slug", "")))
        return project

    # ------------------------------------------------------------------
    # Artifacts
    # ------------------------------------------------------------------

    def list_artifacts(self, job_id: str | None = None) -> list[ArtifactSummary]:
        job_id = job_id or str(self.state.get("job_id", ""))
        if not job_id:
            return []
        return [ArtifactSummary(**row) for row in self.store.list_artifacts(job_id)]

    def read_artifact(self, path: str, *, max_chars: int = 200_000) -> ArtifactContent:
        artifact_path = Path(path)
        if not artifact_path.exists():
            return ArtifactContent(path=path, exists=False)
        size = artifact_path.stat().st_size
        if artifact_path.suffix.lower() not in TEXT_ARTIFACT_SUFFIXES:
            return ArtifactContent(
                path=str(artifact_path),
                exists=True,
                kind="binary",
                size_bytes=size,
            )
        text = artifact_path.read_text(encoding="utf-8", errors="replace")
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]
        if artifact_path.suffix.lower() == ".json":
            try:
                return ArtifactContent(
                    path=str(artifact_path),
                    exists=True,
                    kind="json",
                    text=text,
                    json_data=json.loads(text) if not truncated else None,
                    size_bytes=size,
                    truncated=truncated,
                )
            except json.JSONDecodeError as exc:
                return ArtifactContent(
                    path=str(artifact_path),
                    exists=True,
                    kind="text",
                    text=text,
                    size_bytes=size,
                    truncated=truncated,
                    errors=[f"Invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}"],
                )
        return ArtifactContent(
            path=str(artifact_path),
            exists=True,
            kind="text",
            text=text,
            size_bytes=size,
            truncated=truncated,
        )

    def get_model_ir(self, job_id: str | None = None) -> dict[str, Any] | None:
        state = self._state_for_job(job_id)
        path = state.get("g4_model_ir_path", "")
        if not path or not Path(path).is_file():
            return None
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def get_gate_results(self, job_id: str | None = None) -> list[dict[str, Any]]:
        state = self._state_for_job(job_id)
        path = state.get("gate_results_path", "")
        if not path or not Path(path).is_file():
            return []
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("results", [])

    def _state_for_job(self, job_id: str | None) -> dict[str, Any]:
        if not job_id or job_id == self.state.get("job_id"):
            return self.state
        snapshot = self.store.latest_state_snapshot(job_id)
        if snapshot is None:
            return {}
        return dict(snapshot["state"])

    # ------------------------------------------------------------------
    # Build and simulation
    # ------------------------------------------------------------------

    async def build_generated_code(self, *, threads: int = 4) -> BuildResult:
        code_dir = str(self.state.get("generated_code_dir", ""))
        if not code_dir or not Path(code_dir).exists():
            raise RuntimeError("No generated code directory in current state.")
        from agent_core.tools.geant4_runner import Geant4Runner

        runner = Geant4Runner()
        if not runner.geant4_available:
            result = BuildResult(success=False, errors="Geant4 is not available.")
            self._emit("build_failed", status="error", summary=result.errors)
            return result

        source_dir = Path(code_dir)
        if not (source_dir / "CMakeLists.txt").is_file():
            raise RuntimeError(f"No CMakeLists.txt found in {code_dir}")

        build_dir = source_dir / "build"
        self._emit("build_configure_started", status="running", summary=str(source_dir))
        configure = await runner.configure(str(source_dir), str(build_dir))
        if not configure.get("success"):
            result = BuildResult(
                success=False,
                configure=configure,
                errors=configure.get("errors", ""),
            )
            self._emit("build_failed", status="error", summary=result.errors)
            return result

        self._emit("build_started", status="running", summary=str(build_dir))
        build = await runner.build(str(build_dir), threads=threads)
        executable = str(build.get("executable_path") or "")
        self.state["_executable_path"] = executable
        result = BuildResult(
            success=bool(build.get("success")),
            configure=configure,
            build=build,
            executable_path=executable,
            errors=str(build.get("errors", "")),
        )
        self._emit(
            "build_finished" if result.success else "build_failed",
            status="success" if result.success else "error",
            summary=executable or result.errors,
            payload=result.model_dump(),
        )
        return result

    async def run_simulation(self, *, events: int = 1000) -> SimulationResult:
        executable = str(self.state.get("_executable_path", ""))
        if not executable or not Path(executable).exists():
            raise RuntimeError("No built executable in current state.")
        job_id = str(self.state.get("job_id", "repl_run"))
        output_dir = str(self.workspace.get_job(job_id).output_dir())

        from agent_core.tools.geant4_runner import Geant4Runner

        runner = Geant4Runner()
        self._emit(
            "simulation_started",
            status="running",
            summary=f"{events} events",
            payload={"events": events, "executable": executable},
        )
        raw = await runner.simulate(
            executable=executable,
            events=events,
            output_dir=output_dir,
            job_id=job_id,
        )
        result = SimulationResult(
            success=bool(raw.get("success")),
            output_dir=str(raw.get("output_dir", output_dir)),
            log=str(raw.get("log", "")),
            errors=str(raw.get("errors", "")),
        )
        if result.success:
            self.state["_sim_output_dir"] = result.output_dir
            self.record_state_artifacts(job_id)
        self._emit(
            "simulation_finished" if result.success else "simulation_failed",
            status="success" if result.success else "error",
            summary=result.output_dir if result.success else result.errors,
            payload=result.model_dump(),
        )
        return result
