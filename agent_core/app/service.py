from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_core.app.schemas import (
    ArtifactContent,
    ArtifactSummary,
    BuildResult,
    CopilotResponse,
    JobStatus,
    ModelConfigUpdate,
    ModelConfigView,
    ModelTierConfig,
    PhaseResult,
    RadAgentEvent,
    RuntimeToolStatus,
    SimulationResult,
    StartupStatusView,
    VisualizationWorkbenchResult,
    VisualReviewResult,
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
from agent_core.workspace.paths import (
    HC_REPORT,
    STAGE_GATE_VALIDATION,
    STAGE_HUMAN_CONFIRMATION,
    STAGE_INPUT,
)

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


def _path_is_executable(path: str) -> bool:
    if not path:
        return False
    target = Path(path)
    return target.is_file() and os.access(target, os.X_OK)


def _status_word(ok: bool) -> str:
    return "ok" if ok else "missing"


def _clip_short_text(value: Any, *, limit: int = 50) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[:limit]


def _normalize_task_summary_short(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        result = {
            key: _clip_short_text(value.get(key))
            for key in ("zh", "en")
            if _clip_short_text(value.get(key))
        }
        return result
    text = _clip_short_text(value)
    if not text:
        return {}
    return {"zh": text, "en": text}


def _normalize_context_usage(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    allowed = {
        "compacted",
        "compacted_history_turns",
        "context_window_tokens",
        "cycle",
        "history_estimated_tokens",
        "history_usage_ratio",
        "recent_history_turns",
        "state",
        "threshold",
    }
    return {key: value[key] for key in allowed if key in value}


def _looks_like_copilot_simulation_start(message: str) -> bool:
    text = message.strip().lower()
    if not text:
        return False
    blocked_question_markers = (
        "?",
        "？",
        "为什么",
        "如何",
        "怎么",
        "解释",
        "说明",
        "what",
        "why",
        "how",
        "explain",
    )
    if any(marker in text for marker in blocked_question_markers):
        return False

    start_markers = (
        "/run",
        "建立",
        "创建",
        "生成",
        "运行",
        "设计",
        "启动",
        "开始",
        "build",
        "create",
        "generate",
        "run",
        "design",
        "start",
    )
    simulation_markers = (
        "geant4",
        "仿真",
        "模拟",
        "simulation",
        "simulate",
        "粒子",
        "质子",
        "电子",
        "中子",
        "探测器",
        "detector",
    )
    objective_markers = (
        "观察",
        "计算",
        "评估",
        "能量沉积",
        "剂量",
        "轨迹",
        "响应",
        "observe",
        "calculate",
        "evaluate",
        "deposit",
        "dose",
        "trajectory",
        "response",
    )
    has_start = any(marker in text for marker in start_markers)
    has_simulation = any(marker in text for marker in simulation_markers)
    has_objective = any(marker in text for marker in objective_markers)
    return has_simulation and (has_start or has_objective)


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
                    context_window_tokens=config.context_window_tokens,
                    thinking_default=thinking_defaults.get(tier, False),
                )
                for tier, config in env.models.items()
            },
        )

    def get_startup_status(self) -> StartupStatusView:
        """Return frontend-safe runtime status for the TUI startup frame."""
        env = load_environment(self.env_path)
        software = env.software
        try:
            project_slug = str(self.current_project().get("slug", "default"))
        except Exception:
            project_slug = "default"
        model_config = self.get_model_config()

        geant4_configured = bool(
            software.geant4_config_bin or software.geant4_install_dir
        )
        geant4_available = _path_is_executable(software.geant4_config_bin)
        geant4_detail = (
            f"config={software.geant4_config_bin or 'unset'}; "
            f"cmake={software.cmake_bin or 'missing'}"
        )

        tcad_tool_paths = [
            software.tcad_sde_bin,
            software.tcad_sdevice_bin,
            software.tcad_svisual_bin,
            software.tcad_swb_bin,
            software.tcad_inspect_bin,
        ]
        tcad_configured = any(
            [
                software.tcad_install_dir,
                software.tcad_docker_container,
                *tcad_tool_paths,
            ]
        )
        tcad_available = Path(software.tcad_install_dir).exists() or any(
            _path_is_executable(path) for path in tcad_tool_paths
        )
        tcad_detail = (
            f"dir={software.tcad_install_dir or 'unset'}; "
            f"sde={_status_word(_path_is_executable(software.tcad_sde_bin))}; "
            f"sdevice={_status_word(_path_is_executable(software.tcad_sdevice_bin))}; "
            f"svisual={_status_word(_path_is_executable(software.tcad_svisual_bin))}; "
            f"swb={_status_word(_path_is_executable(software.tcad_swb_bin))}"
        )

        ngspice_configured = bool(software.ngspice_bin)
        ngspice_available = _path_is_executable(software.ngspice_bin)

        return StartupStatusView(
            product_name="RadAgent",
            project_slug=project_slug,
            workspace_root=str(self.workspace.root),
            env_path=str(self.env_path),
            tools={
                "geant4": RuntimeToolStatus(
                    key="geant4",
                    label="Geant4",
                    configured=geant4_configured,
                    available=geant4_available,
                    path=software.geant4_config_bin,
                    detail=geant4_detail,
                ),
                "tcad": RuntimeToolStatus(
                    key="tcad",
                    label="TCAD",
                    configured=tcad_configured,
                    available=tcad_available,
                    path=software.tcad_install_dir,
                    detail=tcad_detail,
                ),
                "ngspice": RuntimeToolStatus(
                    key="ngspice",
                    label="ngspice",
                    configured=ngspice_configured,
                    available=ngspice_available,
                    path=software.ngspice_bin,
                    detail=software.ngspice_bin or "set NGSPICE_BIN",
                ),
            },
            models=model_config.tiers,
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
        if update.lite_context_window_tokens is not None:
            values["RADAGENT_LITE_CONTEXT_WINDOW_TOKENS"] = str(
                update.lite_context_window_tokens
            )
        if update.pro_context_window_tokens is not None:
            values["RADAGENT_PRO_CONTEXT_WINDOW_TOKENS"] = str(
                update.pro_context_window_tokens
            )
        if update.max_context_window_tokens is not None:
            values["RADAGENT_MAX_CONTEXT_WINDOW_TOKENS"] = str(
                update.max_context_window_tokens
            )

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

    async def chat(self, message: str) -> CopilotResponse:
        """Answer through the single workflow-aware RadAgent copilot."""
        context = self.get_workflow_context()
        command = self._safe_copilot_command(message)
        if command is not None:
            started = self._emit(
                "copilot_started",
                status="running",
                summary=message[:120],
                payload={"command": command["name"]},
            )
            response = self._execute_safe_copilot_command(command)
            finished = self._emit(
                "copilot_finished",
                status="success",
                summary=response[:120],
                payload={"command": command, "message": response},
            )
            return CopilotResponse(
                message=response,
                commands=[command],
                context=context.model_dump(mode="json"),
                events=[started, finished],
            )

        agent = self._get_chat_agent()
        started = self._emit(
            "copilot_started",
            status="running",
            summary=message[:120],
            payload={"message": message, "workflow_context": context.model_dump(mode="json")},
        )
        try:
            response = await agent.chat(
                message,
                workflow_context=context.model_dump(mode="json"),
            )
        except Exception as exc:
            self._emit("copilot_failed", status="error", summary=str(exc))
            raise
        finished = self._emit(
            "copilot_finished",
            status="success",
            summary=response[:120],
            payload={
                "message": response,
                "tool_results": getattr(agent, "last_tool_results", []),
            },
        )
        return CopilotResponse(
            message=response,
            context=context.model_dump(mode="json"),
            events=[started, finished],
        )

    async def brief_simulation(
        self,
        user_message: str,
        *,
        conversation: list[dict[str, str]] | None = None,
    ) -> Any:
        """Plan a simulation request with the MAX-tier briefing copilot."""
        from agent_core.chat.briefing import SimulationBriefingPlanner

        planner = SimulationBriefingPlanner()
        return await planner.brief(
            user_message=user_message,
            conversation=conversation or [],
            workflow_context=self.get_workflow_context().model_dump(mode="json"),
        )

    async def summarize_approved_simulation_plan(
        self,
        briefing_context: dict[str, Any],
    ) -> dict[str, str]:
        """Return a short bilingual task summary for the approved plan."""
        from agent_core.chat.briefing import ApprovedPlanSummarizer

        summarizer = ApprovedPlanSummarizer()
        return await summarizer.summarize(briefing_context)

    def _get_chat_agent(self) -> Any:
        if self._chat_agent is None:
            from agent_core.chat.agent import ChatAgent

            self._chat_agent = ChatAgent()
        return self._chat_agent

    def _safe_copilot_command(self, message: str) -> dict[str, Any] | None:
        stripped = message.strip().lower()
        if _looks_like_copilot_simulation_start(message):
            return {
                "name": "start_simulation_briefing",
                "args": {"query": message.strip()},
                "risk": "write",
                "status": "pending_confirmation",
                "summary": "Prepare simulation briefing",
            }
        aliases = {
            "/status": "status",
            "status": "status",
            "状态": "status",
            "/gates": "gates",
            "gates": "gates",
            "门禁": "gates",
            "/artifacts": "artifacts",
            "artifacts": "artifacts",
            "产物": "artifacts",
            "/memory": "memory",
            "memory": "memory",
            "记忆": "memory",
            "/credibility": "credibility",
            "credibility": "credibility",
            "可信度": "credibility",
            "/confirm": "confirmation",
            "confirm": "confirmation",
            "确认": "confirmation",
        }
        if stripped in aliases:
            name = aliases[stripped]
            return {
                "name": name,
                "args": {},
                "risk": "read",
                "status": "executed",
                "summary": f"Read {name}",
            }
        return None

    def _execute_safe_copilot_command(self, command: dict[str, Any]) -> str:
        name = command.get("name", "")
        if name == "start_simulation_briefing":
            query = str(command.get("args", {}).get("query", "")).strip()
            return (
                "我可以把这条请求整理成受控仿真任务。请确认后进入仿真简报流程："
                f"{query}"
            )
        if name == "status":
            status = self.get_status()
            return (
                f"当前状态: {status.status}; job={status.job_id or 'none'}; "
                f"phase={status.current_phase or 'idle'}; "
                f"confirmation={'yes' if status.needs_confirmation else 'no'}."
            )
        if name == "gates":
            gates = self.get_gate_results()
            if not gates:
                return "当前 job 还没有 gate results。"
            failed = [g for g in gates if g.get("status") in {"fail", "block", "blocked"}]
            gate20 = next((g for g in gates if g.get("gate_id") == 20), None)
            parts = [f"门禁总数 {len(gates)}，失败 {len(failed)}。"]
            if gate20:
                parts.append(
                    "可信度门禁: "
                    f"{gate20.get('status', 'unknown')} "
                    f"({gate20.get('credibility_level', 'unknown')})."
                )
            return " ".join(parts)
        if name == "artifacts":
            artifacts = self.list_artifacts()
            if not artifacts:
                return "当前 job 还没有可展示 artifact。"
            shown = ", ".join(
                item.kind or item.stage or Path(item.path).name
                for item in artifacts[:8]
            )
            return f"当前记录了 {len(artifacts)} 个 artifact：{shown}。"
        if name == "memory":
            context = self.get_workflow_context()
            lines = [item.summary for item in context.memory[:6]]
            return "工作流记忆: " + ("; ".join(lines) if lines else "暂无。")
        if name == "credibility":
            report = self.get_credibility_report()
            if not report:
                return "当前还没有可信度门禁结果。"
            return (
                "可信度门禁: "
                f"{report.get('status', 'unknown')} "
                f"({report.get('credibility_level', 'unknown')}) - "
                f"{report.get('message', '')}"
            )
        if name == "confirmation":
            review = self.get_confirmation_review()
            if not review:
                return "当前没有人工确认报告。"
            return (
                f"人工确认状态: {review.get('status', 'unknown')}; "
                f"report={review.get('report_path', '')}"
            )
        return "这个命令还没有安全只读实现。"

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    async def start_job(
        self,
        query: str,
        *,
        run_mode: str = "strict",
        auto_continue: bool = True,
        briefing_context: dict[str, Any] | None = None,
        reset_chat: bool = True,
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
        if briefing_context:
            self.state["copilot_briefing"] = self._approved_briefing_context(
                briefing_context
            )
            self.state["raw_human_response"] = {
                "user_decision": "approve",
                "edits": [],
                "user_notes": "Approved before pipeline start through RadAgent briefing.",
            }
            summary = _normalize_task_summary_short(
                briefing_context.get("task_summary_short")
            )
            if summary:
                self.state["task_summary_short"] = summary
            context_usage = _normalize_context_usage(
                briefing_context.get("context_window_stats")
            )
            if context_usage:
                self.state["copilot_context_usage"] = context_usage
        self.current_phase_idx = 0
        self.completed_phases = []
        self.run_id = uuid4().hex
        if reset_chat and self._chat_agent is not None:
            self._chat_agent.reset()

        self._emit("job_started", status="running", summary=query[:160])
        if auto_continue:
            await self.run_until_blocked()
        else:
            await self.run_phase("prepare_workspace")
        return self.get_status()

    def _approved_briefing_context(self, briefing_context: dict[str, Any]) -> dict[str, Any]:
        data = dict(briefing_context)
        data["approved"] = True
        approval = data.get("approval_request")
        if isinstance(approval, dict):
            approval["requires_human_approval"] = True
            data["approval_request"] = approval
        else:
            data["approval_request"] = {"requires_human_approval": True}
        return data

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
            if (
                phase == "g4_modeling"
                and self.state.get("human_confirmation_required")
                and not self.state.get("raw_human_response")
            ):
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
            self._set_termination_reason(str(exc))
            self._persist_phase_state(phase, status_override="failed")
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
        failure_reason = self._phase_failure_reason(phase)
        if failure_reason:
            self._set_termination_reason(failure_reason)
            self._persist_phase_state(phase, status_override="failed")
            failed = self._emit(
                "phase_failed",
                status="error",
                phase=phase,
                summary=failure_reason,
                payload=result or {},
            )
            return PhaseResult(
                phase=phase,
                success=False,
                state_delta=result or {},
                status=self.get_status(),
                events=[started, failed],
            )
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

    def _phase_failure_reason(self, phase: str) -> str:
        """Return a blocking phase-level failure reason, or empty string."""
        expectations = {
            "task_planning": ("task_planning_status", {"passed"}),
            "g4_modeling": ("g4_modeling_status", {"passed"}),
            "g4_codegen": ("g4_codegen_status", {"passed"}),
            "patch": ("patch_status", {"applied"}),
            "gate": ("validation_status", {"passed"}),
            "artifact": ("artifact_status", {"collected"}),
        }
        expectation = expectations.get(phase)
        if expectation is None:
            return ""
        key, accepted = expectation
        if key not in self.state:
            return ""
        value = str(self.state.get(key, "") or "")
        if value in accepted:
            return ""
        return f"{key.removesuffix('_status')} status is {value or 'missing'}"

    def _set_termination_reason(self, reason: str) -> None:
        self.state["termination_reason"] = reason
        errors = self.state.setdefault("errors", [])
        if isinstance(errors, list) and reason and reason not in errors:
            errors.append(reason)

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

    def _persist_phase_state(self, phase: str, *, status_override: str | None = None) -> None:
        job_id = str(self.state.get("job_id", ""))
        if not job_id:
            return
        status = status_override or ("completed" if phase == "report" else "running")
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
        visual_review_blocked = self._has_blocked_visual_review_gate()
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
                "visual_review_status",
                "termination_reason",
            )
            if self.state.get(key) is not None
        }
        status = "idle"
        if self.state.get("job_id"):
            status = "completed" if self.current_phase_idx >= len(PIPELINE_PHASES) else "running"
            if self.state.get("confirmation_status") == "pending":
                status = "paused"
            if self.state.get("visual_review_status") in {"pending", "rejected"}:
                status = "paused"
            if visual_review_blocked:
                status = "paused"
            if self.state.get("termination_reason"):
                status = "failed"
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
            or self.state.get("confirmation_status") == "pending"
            or self.state.get("visual_review_status") in {"pending", "rejected"}
            or visual_review_blocked,
            key_statuses=key_statuses,
            state=dict(self.state),
        )

    def _has_blocked_visual_review_gate(self) -> bool:
        gate_results = self.get_gate_results()
        return any(
            gate.get("gate_id") == 21 and gate.get("status") in {"block", "blocked"}
            for gate in gate_results
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

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        self.store.import_existing_jobs()
        return self.store.get_job(job_id)

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

    def get_workflow_context(self, job_id: str | None = None) -> Any:
        from agent_core.workflow import build_workflow_context

        state = self._state_for_job(job_id)
        if not state and job_id:
            status = JobStatus(job_id=job_id, workspace_root=str(self.workspace.root))
        else:
            active_state = self.state
            if job_id and job_id != self.state.get("job_id"):
                active_state = state
            status = self.get_status() if active_state is self.state else JobStatus(
                job_id=str(active_state.get("job_id", job_id or "")),
                user_query=str(active_state.get("user_query", "")),
                status=str(active_state.get("status", "paused")),
                current_phase=str(active_state.get("current_node", "")),
                current_phase_idx=int(active_state.get("current_phase_idx", 0)),
                completed_phases=list(active_state.get("completed_phases", [])),
                execution_mode=str(active_state.get("execution_mode", self.execution_mode)),
                run_mode=str(active_state.get("run_mode", "strict")),
                workspace_root=str(active_state.get("workspace_root", self.workspace.root)),
                job_workspace=str(active_state.get("job_workspace", "")),
            )
        context_state = {**state, "run_id": self.run_id}
        return build_workflow_context(
            status=status,
            state=context_state,
            recent_events=self.recent_events(30),
            artifacts=self.list_artifacts(status.job_id) if status.job_id else [],
            gate_results=self.get_gate_results(status.job_id) if status.job_id else [],
            workspace_root=self.workspace.root,
        )

    def get_confirmation_review(self, job_id: str | None = None) -> dict[str, Any]:
        state = self._state_for_job(job_id)
        report_path = str(state.get("confirmation_report_path", ""))
        if not report_path and state.get("job_workspace"):
            candidate = Path(str(state["job_workspace"])) / STAGE_HUMAN_CONFIRMATION / HC_REPORT
            if candidate.is_file():
                report_path = str(candidate)
        preview = ""
        if report_path and Path(report_path).is_file():
            preview = Path(report_path).read_text(encoding="utf-8", errors="replace")[:8000]
        return {
            "status": state.get("confirmation_status", ""),
            "required": bool(state.get("human_confirmation_required")),
            "unconfirmed_assumptions_count": state.get("unconfirmed_assumptions_count", 0),
            "report_path": report_path,
            "record_path": state.get("confirmation_record_path", ""),
            "confirmed_model_plan_path": state.get("confirmed_model_plan_path", ""),
            "preview": preview,
        }

    def get_credibility_report(self, job_id: str | None = None) -> dict[str, Any]:
        state = self._state_for_job(job_id)
        for gate in self.get_gate_results(job_id):
            if gate.get("gate_id") == 20:
                return gate
        active_job_id = str(job_id or state.get("job_id", ""))
        if active_job_id:
            path = (
                self.workspace.root
                / "jobs"
                / active_job_id
                / STAGE_GATE_VALIDATION
                / "credibility_assessment.json"
            )
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        return {}

    def create_revision(self, user_request: str, job_id: str | None = None) -> dict[str, Any]:
        from agent_core.revision import RevisionManager

        active_job_id = job_id or str(self.state.get("job_id", ""))
        if not active_job_id:
            raise RuntimeError("No active job for revision.")
        base_dir = str(self.state.get("generated_code_dir", ""))
        manager = RevisionManager(workspace_root=self.workspace.root)
        request = manager.create_revision(
            active_job_id,
            user_request,
            base_generated_code_dir=base_dir or None,
        )
        self._emit(
            "revision_created",
            status="success",
            summary=request.revision_id,
            job_id=active_job_id,
            payload=request.model_dump(mode="json"),
        )
        return request.model_dump(mode="json")

    async def run_revision(
        self,
        revision_id: str,
        *,
        proposed_patch_path: str | None = None,
    ) -> dict[str, Any]:
        from agent_core.revision import RevisionManager

        manager = RevisionManager(workspace_root=self.workspace.root)
        status = await manager.arun_revision(revision_id, proposed_patch_path)
        self._emit(
            "revision_finished" if status.status == "completed" else "revision_failed",
            status="success" if status.status == "completed" else "error",
            summary=revision_id,
            job_id=status.job_id,
            payload=status.model_dump(mode="json"),
        )
        return status.model_dump(mode="json")

    def list_revisions(self, job_id: str | None = None) -> list[dict[str, Any]]:
        active_job_id = job_id or str(self.state.get("job_id", ""))
        if not active_job_id:
            return []
        root = self.workspace.root / "jobs" / active_job_id / "revisions"
        if not root.is_dir():
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(root.glob("*/revision_summary.json"), reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                rows.append(data)
        return rows

    async def accept_revision(self, revision_id: str) -> JobStatus:
        from agent_core.revision import RevisionManager, check_accept_preconditions

        manager = RevisionManager(workspace_root=self.workspace.root)
        summary = manager.get_summary(revision_id)
        gate_state = self._revision_gate_state(summary.revision_dir)
        ok, errors = check_accept_preconditions(gate_state)
        if not ok:
            raise RuntimeError("; ".join(errors))
        candidate = Path(summary.candidate_project_dir)
        target_value = str(self.state.get("generated_code_dir", ""))
        if not target_value:
            raise RuntimeError("No generated_code_dir in current workflow state.")
        target = Path(target_value)
        if not candidate.is_dir():
            raise RuntimeError(f"Revision candidate project not found: {candidate}")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(candidate, target)
        self._emit(
            "revision_accepted",
            status="success",
            summary=revision_id,
            job_id=summary.job_id,
            payload=summary.model_dump(mode="json"),
        )
        return self.get_status()

    def reject_revision(self, revision_id: str, reason: str = "") -> dict[str, Any]:
        from agent_core.revision import RevisionManager

        manager = RevisionManager(workspace_root=self.workspace.root)
        summary = manager.get_summary(revision_id)
        self._emit(
            "revision_rejected",
            status="warning",
            summary=revision_id,
            job_id=summary.job_id,
            payload={"reason": reason, "revision": summary.model_dump(mode="json")},
        )
        return summary.model_dump(mode="json")

    def _revision_gate_state(self, revision_dir: str) -> dict[str, Any]:
        path = Path(revision_dir) / "gate_results.json"
        if not path.is_file():
            return {"validation_status": "missing", "gate_results": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"validation_status": "unreadable", "gate_results": []}
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            failed = [g for g in data if g.get("status") in {"fail", "block", "blocked"}]
            return {
                "validation_status": "failed" if failed else "passed",
                "gate_results": data,
            }
        return {"validation_status": "invalid", "gate_results": []}

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

    async def prepare_visualization_workbench(
        self,
        *,
        events: int = 100,
        launch: bool = False,
    ) -> VisualizationWorkbenchResult:
        """Prepare native Geant4 visual workbench macros and launch metadata."""
        if events <= 0:
            raise ValueError("Workbench event count must be positive.")
        code_dir = str(self.state.get("generated_code_dir", ""))
        if not code_dir or not Path(code_dir).exists():
            raise RuntimeError("No generated code directory in current state.")
        executable = str(self.state.get("_executable_path", ""))
        if not executable or not Path(executable).exists():
            raise RuntimeError("No built executable in current state.")

        from agent_core.tools.geant4_workbench import prepare_visual_workbench

        self._emit(
            "visualization_workbench_started",
            status="running",
            summary=f"{events} events",
            payload={"events": events, "executable": executable},
        )
        try:
            metadata = prepare_visual_workbench(
                code_dir,
                executable=executable,
                events=events,
            )
        except Exception as exc:
            result = VisualizationWorkbenchResult(success=False, errors=str(exc))
            self._emit(
                "visualization_workbench_failed",
                status="error",
                summary=result.errors,
                payload=result.model_dump(),
            )
            return result

        launched = False
        pid: int | None = None
        if launch:
            env = dict(os.environ)
            env.update(metadata.get("environment", {}))
            try:
                proc = subprocess.Popen(
                    list(metadata["launch_command"]),
                    cwd=str(metadata["working_dir"]),
                    env=env,
                    start_new_session=True,
                )
            except OSError as exc:
                result = VisualizationWorkbenchResult(
                    success=False,
                    errors=str(exc),
                    **metadata,
                )
                self._emit(
                    "visualization_workbench_failed",
                    status="error",
                    summary=result.errors,
                    payload=result.model_dump(),
                )
                return result
            launched = True
            pid = proc.pid

        result = VisualizationWorkbenchResult(
            success=True,
            launched=launched,
            pid=pid,
            **metadata,
        )
        self.state["visual_workbench"] = result.model_dump()
        self.state["visual_review_status"] = "pending"
        self.state["visual_review_blocking"] = True
        self._emit(
            "visualization_workbench_ready",
            status="success",
            summary=result.executable,
            payload=result.model_dump(),
        )
        return result

    def record_visual_verdict(
        self,
        *,
        approved: bool,
        notes: str = "",
    ) -> VisualReviewResult:
        """Record the blocking human visual-review verdict for the active job."""
        status = "approved" if approved else "rejected"
        clean_notes = " ".join(notes.split()).strip()
        if not approved and not clean_notes:
            raise ValueError("Rejection notes are required.")
        result = VisualReviewResult(status=status, blocking=True, notes=clean_notes)
        self.state["visual_review_status"] = status
        self.state["visual_review_notes"] = clean_notes
        self.state["visual_review_blocking"] = True
        self._emit(
            f"visualization_review_{status}",
            status="success" if approved else "warning",
            summary=clean_notes or status,
            payload=result.model_dump(),
        )
        return result
