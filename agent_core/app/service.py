from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import threading
from collections.abc import AsyncIterator, Callable
from datetime import datetime
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
    ModelHealthReport,
    ModelHealthTierResult,
    ModelTierConfig,
    PhaseResult,
    RadAgentEvent,
    RuntimeToolStatus,
    SimulationResult,
    StartupStatusView,
)
from agent_core.config.environment import (
    DEFAULT_ENV_PATH,
    load_environment,
    model_endpoint_requires_api_key,
    write_project_env_values,
)
from agent_core.gates.gate_runner import normalize_run_mode
from agent_core.graph.main_routes import route_after_context, route_after_gates
from agent_core.models.registry import thinking_for_task
from agent_core.models.schemas import ModelTask, ModelTier
from agent_core.pipeline import PIPELINE_PHASES
from agent_core.storage import RadAgentStore
from agent_core.workspace.manager import WorkspaceManager
from agent_core.workspace.paths import (
    HC_REPORT,
    HC_REQUEST_TEMPLATE,
    STAGE_CODEGEN,
    STAGE_GATE_VALIDATION,
    STAGE_HUMAN_CONFIRMATION,
    STAGE_INPUT,
    STAGE_MODEL_IR,
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
REQUIREMENTS_REVIEW_WAITING_STATUSES = frozenset({"pending", "needs_user_input"})


def _active_gate_results(results: Any) -> list[dict[str, Any]]:
    if not isinstance(results, list):
        return []
    return [
        gate
        for gate in results
        if isinstance(gate, dict) and not _is_retired_visual_review_gate(gate)
    ]


def _is_retired_visual_review_gate(gate: dict[str, Any]) -> bool:
    try:
        if int(gate.get("gate_id", -1)) == 21:
            return True
    except (TypeError, ValueError):
        pass
    return str(gate.get("name", "")).strip() == "G4 Visual Review"


def _is_modeling_failure_state(state: dict[str, Any]) -> bool:
    modeling_status = str(state.get("g4_modeling_status") or "")
    return bool(modeling_status and modeling_status != "passed")


def _modeling_validation_errors(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for result in report.get("results", []) if isinstance(report.get("results"), list) else []:
        if not isinstance(result, dict):
            continue
        validator = str(result.get("validator") or "validator")
        if result.get("passed") is True:
            continue
        for item in result.get("errors", []) if isinstance(result.get("errors"), list) else []:
            message = str(item).strip()
            if message:
                errors.append(f"{validator}: {message}")
    for item in report.get("errors", []) if isinstance(report.get("errors"), list) else []:
        message = str(item).strip()
        if message:
            errors.append(message)
    return errors


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _confirmation_actionable(state: dict[str, Any]) -> bool:
    status = str(state.get("confirmation_status") or "").lower()
    if status in {"approved", "rejected", "failed", "blocked"}:
        return False
    if _state_has_legacy_codegen_physics_confirmation(state):
        return False
    return bool(state.get("human_confirmation_required") or status == "pending")


def _requirements_review_waiting_status(value: Any) -> bool:
    return str(value or "").strip().lower() in REQUIREMENTS_REVIEW_WAITING_STATUSES


def _state_has_legacy_codegen_physics_confirmation(state: dict[str, Any]) -> bool:
    request_path = str(state.get("confirmation_request_path") or "")
    if not request_path:
        return False
    target = Path(request_path)
    if not target.is_file():
        return False
    try:
        request = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return str(request.get("schema_version") or "") == "codegen_physics_confirmation_v1"


EventCallback = Callable[[RadAgentEvent], None]


def _path_is_executable(path: str) -> bool:
    if not path:
        return False
    target = Path(path)
    return target.is_file() and os.access(target, os.X_OK)


def _status_word(ok: bool) -> str:
    return "ok" if ok else "missing"


def _radagent_event_from_log(payload: dict[str, Any]) -> RadAgentEvent | None:
    event_type = str(payload.get("event_type", "")).strip()
    if not event_type:
        return None
    raw_status = str(payload.get("status", "info")).strip().lower()
    status = {
        "passed": "success",
        "pass": "success",
        "complete": "success",
        "completed": "success",
        "failed": "error",
        "failure": "error",
    }.get(raw_status, raw_status)
    if status not in {"info", "running", "success", "warning", "error"}:
        status = "info"
    details = payload.get("details")
    event_payload = {
        "metrics": payload.get("metrics") or {},
        "details": details if isinstance(details, dict) else {},
        "artifacts": payload.get("artifacts") or [],
        "errors": payload.get("errors") or [],
        "warnings": payload.get("warnings") or [],
        "duration_ms": payload.get("duration_ms"),
    }
    created_at_raw = str(payload.get("timestamp") or payload.get("created_at") or "").strip()
    try:
        created_at = (
            datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
            if created_at_raw
            else None
        )
    except ValueError:
        created_at = None
    kwargs: dict[str, Any] = {
        "event_type": event_type,
        "status": status,
        "summary": str(payload.get("summary", "")),
        "phase": str(payload.get("phase", "")),
        "job_id": str(payload.get("job_id", "")),
        "run_id": str(payload.get("run_id", "")),
        "payload": event_payload,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    return RadAgentEvent(**kwargs)


def _agentic_repair_max_turns() -> int:
    try:
        return max(1, int(os.getenv("RADAGENT_AGENTIC_MAX_TURNS", "48")))
    except ValueError:
        return 48


def _agentic_repair_history_chars() -> int:
    try:
        return max(0, int(os.getenv("RADAGENT_AGENTIC_HISTORY_CHARS", "0")))
    except ValueError:
        return 0


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
        self._background_continue_lock = threading.Lock()
        self._background_continue_thread: threading.Thread | None = None

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
            agentic_repair_max_turns=_agentic_repair_max_turns(),
            agentic_repair_history_chars=_agentic_repair_history_chars(),
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
        if update.agentic_repair_max_turns is not None:
            values["RADAGENT_AGENTIC_MAX_TURNS"] = str(update.agentic_repair_max_turns)
        if update.agentic_repair_history_chars is not None:
            values["RADAGENT_AGENTIC_HISTORY_CHARS"] = str(
                update.agentic_repair_history_chars
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

    async def test_model_health(
        self,
        *,
        per_tier_timeout_s: float = 12.0,
    ) -> ModelHealthReport:
        """Run a small, frontend-safe model connectivity and latency probe."""
        config = self.get_model_config()
        tiers: dict[str, ModelHealthTierResult] = {}
        for tier in (ModelTier.LITE, ModelTier.PRO, ModelTier.MAX):
            tier_config = config.tiers.get(tier.value)
            if tier_config is None:
                tiers[tier.value] = ModelHealthTierResult(
                    tier=tier.value,
                    status="skipped",
                    error="Model tier is not configured.",
                )
                continue

            base = {
                "tier": tier.value,
                "model_name": tier_config.model_name,
                "base_url": tier_config.base_url,
                "api_key_env": tier_config.api_key_env,
            }
            if not tier_config.base_url:
                tiers[tier.value] = ModelHealthTierResult(
                    **base,
                    status="skipped",
                    error="Missing model base URL.",
                )
                continue
            if (
                model_endpoint_requires_api_key(tier_config.base_url)
                and not tier_config.api_key_configured
            ):
                tiers[tier.value] = ModelHealthTierResult(
                    **base,
                    status="skipped",
                    error=f"Missing API key env: {tier_config.api_key_env}",
                )
                continue

            try:
                result = await asyncio.wait_for(
                    self._probe_model_health_tier(tier),
                    timeout=max(0.1, float(per_tier_timeout_s)),
                )
            except TimeoutError:
                tiers[tier.value] = ModelHealthTierResult(
                    **base,
                    status="error",
                    error=f"Model health check timed out after {per_tier_timeout_s:.1f}s.",
                )
                continue
            tiers[tier.value] = ModelHealthTierResult(
                **base,
                status="error" if result.error else "ok",
                latency_ms=float(result.latency_ms or 0.0),
                response_preview=_clip_short_text(result.content, limit=120),
                error=result.error or "",
            )

        report = ModelHealthReport(tiers=tiers)
        self._emit(
            "model_health_checked",
            status="success" if all(row.status == "ok" for row in tiers.values()) else "warning",
            summary="Model health test completed.",
            payload=report.model_dump(mode="json"),
        )
        return report

    async def _probe_model_health_tier(self, tier: ModelTier) -> Any:
        from agent_core.models.gateway import get_model_gateway

        gateway = get_model_gateway()
        return await gateway.call(
            ModelTask.SIMPLE_EXTRACTION,
            "Reply with exactly OK.",
            "Health check. Reply OK.",
            tier=tier,
            temperature=0.0,
            max_tokens=8,
            metadata={
                "module_name": "model_health",
                "job_id": str(self.state.get("job_id", "")),
            },
        )

    def continue_in_background(self, *, reason: str = "") -> bool:
        """Continue the active workflow without blocking a UI request."""
        with self._background_continue_lock:
            if (
                self._background_continue_thread is not None
                and self._background_continue_thread.is_alive()
            ):
                self._emit(
                    "workflow_continue_busy",
                    status="warning",
                    summary="Workflow continuation is already running.",
                    payload={"reason": reason},
                )
                return False
            thread = threading.Thread(
                target=self._run_background_continue,
                args=(reason,),
                name=f"radagent-continue-{self.run_id[:8]}",
                daemon=True,
            )
            self._background_continue_thread = thread

        self._emit(
            "workflow_continue_queued",
            status="running",
            summary=reason or "continue",
            payload={"reason": reason},
        )
        thread.start()
        return True

    def _run_background_continue(self, reason: str) -> None:
        self._emit(
            "workflow_continue_started",
            status="running",
            summary=reason or "continue",
            payload={"reason": reason},
        )
        try:
            status = asyncio.run(self.run_until_blocked())
        except Exception as exc:
            self._set_termination_reason(str(exc))
            self._emit(
                "workflow_continue_failed",
                status="error",
                summary=str(exc),
                payload={"reason": reason},
            )
            logger.exception("Background workflow continuation failed")
        else:
            status_value = str(getattr(status, "status", "") or "")
            if status_value == "failed":
                failure_reason = str(
                    self.state.get("termination_reason", "") or "Workflow continuation failed."
                )
                self._emit(
                    "workflow_continue_failed",
                    status="error",
                    summary=failure_reason,
                    payload={
                        "reason": failure_reason,
                        "trigger": reason,
                        "status": status_value,
                        "current_phase": str(getattr(status, "current_phase", "")),
                    },
                )
                return
            self._emit(
                "workflow_continue_finished",
                status="success",
                summary=reason or "continue",
                payload={"reason": reason},
            )
        finally:
            with self._background_continue_lock:
                if self._background_continue_thread is threading.current_thread():
                    self._background_continue_thread = None

    def _runtime_active(self) -> bool:
        with self._background_continue_lock:
            return bool(
                self._background_continue_thread is not None
                and self._background_continue_thread.is_alive()
            )

    # ------------------------------------------------------------------
    # Event stream
    # ------------------------------------------------------------------

    def recent_events(self, limit: int | None = None) -> list[RadAgentEvent]:
        events = [
            *self._events,
            *self._recent_job_log_events(),
            *self._active_model_call_events(),
        ]
        events.sort(key=lambda event: event.created_at)
        if limit is None:
            return events
        return events[-int(limit) :]

    def _active_model_call_events(self) -> list[RadAgentEvent]:
        if not self._runtime_active():
            return []
        job_id = str(self.state.get("job_id", ""))
        if not job_id:
            return []
        active_path = self.workspace.root / "jobs" / job_id / "logs" / "active_model_call.json"
        if not active_path.exists():
            return []
        try:
            payload = json.loads(active_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(payload, dict):
            return []
        if str(payload.get("status", "")).strip().lower() != "running":
            return []
        call_id = str(payload.get("model_call_id", "")).strip()
        transcript_path = str(payload.get("transcript_path", "")).strip()
        task = str(payload.get("task", "")).strip() or "model_call"
        module_name = str(payload.get("module_name", "")).strip()
        if not call_id and not transcript_path:
            return []
        try:
            created_at = datetime.fromtimestamp(active_path.stat().st_mtime).astimezone()
        except OSError:
            created_at = datetime.now().astimezone()
        return [
            RadAgentEvent(
                event_type="model_call_start",
                status="running",
                summary=f"{task} is generating",
                phase=task,
                job_id=job_id,
                run_id=self.run_id,
                created_at=created_at,
                payload={
                    "metrics": {},
                    "details": {
                        "metadata": {
                            "model_call_id": call_id,
                            "module_name": module_name,
                        }
                    },
                    "artifacts": [{"path": transcript_path}] if transcript_path else [],
                    "errors": [],
                    "warnings": [],
                    "duration_ms": None,
                },
            )
        ]

    def _recent_job_log_events(self, limit: int = 120) -> list[RadAgentEvent]:
        job_id = str(self.state.get("job_id", ""))
        if not job_id:
            return []
        events_path = self.workspace.root / "jobs" / job_id / "logs" / "events.jsonl"
        if not events_path.exists():
            return []
        events: list[RadAgentEvent] = []
        seen = {
            (
                event.event_type,
                event.summary,
                event.phase,
                event.created_at.isoformat(),
            )
            for event in self._events
        }
        for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            event = _radagent_event_from_log(payload)
            if event is None:
                continue
            key = (
                event.event_type,
                event.summary,
                event.phase,
                event.created_at.isoformat(),
            )
            if key in seen:
                continue
            seen.add(key)
            events.append(event)
        return events

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
            if (
                phase == "requirements_review"
                and self._is_requirements_review_pending()
            ):
                self._emit(
                    "requirements_review_required",
                    status="warning",
                    phase=phase,
                    summary="Simulation parameters need review before Geant4 modeling.",
                    payload={
                        "requirements_review_request_path": self.state.get(
                            "requirements_review_request_path", ""
                        )
                    },
                )
                return self.get_status()
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
                if self._route_after_failed_phase(phase):
                    continue
                return result.status
            if phase == "g4_codegen" and self._is_repair_continuation_pending():
                self._emit(
                    "repair_continuation_required",
                    status="warning",
                    phase=phase,
                    summary=str(
                        self.state.get("repair_continuation_request", {}).get(
                            "message",
                            "Repair continuation is pending.",
                        )
                    ),
                    payload=self.state.get("repair_continuation_request", {}),
                )
                return self.get_status()
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

    def _route_after_failed_phase(self, phase: str) -> bool:
        if phase == "gate":
            return self._route_failed_gate()
        return False

    def _route_failed_gate(self) -> bool:
        target_node = route_after_gates(self.state)
        target_phase = self._phase_for_route_node(target_node)
        if target_phase is None or target_phase == "report":
            return False
        if bool(self.state.get("max_retries_reached")):
            return False
        self._clear_previous_failure()
        self.current_phase_idx = PIPELINE_PHASES.index(target_phase)
        self.completed_phases = [
            completed_phase
            for completed_phase in self.completed_phases
            if PIPELINE_PHASES.index(completed_phase) < self.current_phase_idx
        ]
        self._emit(
            "phase_retry_routed",
            status="warning",
            phase="gate",
            summary=f"Gate failure routed to {target_phase}.",
            payload={
                "from_phase": "gate",
                "target_phase": target_phase,
                "target_node": target_node,
                "failed_gates": self.state.get("failed_gates", []),
                "retry_count": self.state.get("retry_count", 0),
            },
        )
        self._persist_phase_state(target_phase, status_override="running")
        return True

    def _phase_for_route_node(self, node: str) -> str | None:
        if node == "artifact_subgraph":
            return "artifact"
        if node == "report_subgraph":
            return "report"
        suffix = "_subgraph"
        if node.endswith(suffix):
            phase = node[: -len(suffix)]
            if phase in PIPELINE_PHASES:
                return phase
        if node in PIPELINE_PHASES:
            return node
        return None

    async def step(self) -> PhaseResult:
        if not self.state:
            raise RuntimeError("No active job. Start or resume a job first.")
        if self._is_repair_continuation_pending():
            event = self._emit(
                "repair_continuation_required",
                status="warning",
                phase="g4_codegen",
                summary=str(
                    self.state.get("repair_continuation_request", {}).get(
                        "message",
                        "Repair continuation is pending.",
                    )
                ),
                payload=self.state.get("repair_continuation_request", {}),
            )
            return PhaseResult(
                phase="g4_codegen",
                success=False,
                state_delta={},
                status=self.get_status(),
                events=[event],
            )
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
        if phase == "g4_codegen" and self._is_repair_continuation_pending():
            self._persist_phase_state(phase, status_override="paused")
            paused = self._emit(
                "phase_paused",
                status="warning",
                phase=phase,
                summary=str(
                    self.state.get("repair_continuation_request", {}).get(
                        "message",
                        "Repair continuation is pending.",
                    )
                ),
                payload=result or {},
            )
            return PhaseResult(
                phase=phase,
                success=True,
                state_delta=result or {},
                status=self.get_status(),
                events=[started, paused],
            )
        if phase == "requirements_review" and self._is_requirements_review_pending():
            self._persist_phase_state(phase, status_override="paused")
            paused = self._emit(
                "phase_paused",
                status="warning",
                phase=phase,
                summary=str(
                    self.state.get("confirmation_summary")
                    or "Simulation parameters need review before Geant4 modeling."
                ),
                payload=result or {},
            )
            return PhaseResult(
                phase=phase,
                success=True,
                state_delta=result or {},
                status=self.get_status(),
                events=[started, paused],
            )
        if phase == "patch":
            visual_ready = await self._prepare_browser_visualization_after_patch()
            if visual_ready:
                result = {**(result or {}), **visual_ready}
                self.state = {**self.state, **visual_ready}
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
        if self._is_repair_continuation_pending():
            return await self.submit_repair_continuation(
                response,
                auto_continue=auto_continue,
            )
        if not self.state.get("job_id"):
            raise RuntimeError("No active job.")
        if self._is_requirements_review_pending():
            return await self._submit_requirements_review_confirmation(
                response,
                auto_continue=auto_continue,
            )
        decision = str(response.get("user_decision", "") or "")
        confirmation_idx = PIPELINE_PHASES.index("human_confirmation")
        modeling_status = str(self.state.get("g4_modeling_status") or "")
        if self._is_legacy_codegen_physics_confirmation_pending():
            return self._reject_legacy_codegen_physics_confirmation(response)
        if decision == "approve" and modeling_status and modeling_status != "passed":
            reason = str(
                self.state.get("termination_reason")
                or f"g4_modeling status is {modeling_status}"
            )
            self._set_termination_reason(reason)
            self.current_phase_idx = confirmation_idx
            self._emit(
                "human_confirmation_blocked_by_modeling_failure",
                status="error",
                phase="human_confirmation",
                summary=reason,
                payload=response,
            )
            self._persist_phase_state("human_confirmation", status_override="failed")
            return self.get_status()
        if (
            decision == "approve"
            and self.state.get("confirmation_status") == "approved"
            and self.current_phase_idx > confirmation_idx
        ):
            self._emit(
                "human_confirmation_already_approved",
                status="info",
                phase="human_confirmation",
                summary="Approval already recorded.",
                payload=response,
            )
            return self.get_status()
        self.state["raw_human_response"] = response
        self._emit(
            "human_confirmation_submitted",
            status="info",
            phase="human_confirmation",
            summary=decision,
            payload=response,
        )
        if self.current_phase_idx != confirmation_idx:
            self.current_phase_idx = confirmation_idx
        await self.run_phase("human_confirmation")
        if auto_continue:
            await self.run_until_blocked()
        return self.get_status()

    def _is_legacy_codegen_physics_confirmation_pending(self) -> bool:
        if not self._is_human_confirmation_pending():
            return False
        request = self._read_json_file(str(self.state.get("confirmation_request_path", "")))
        return str(request.get("schema_version") or "") == "codegen_physics_confirmation_v1"

    def _reject_legacy_codegen_physics_confirmation(
        self,
        response: dict[str, Any],
    ) -> JobStatus:
        reason = (
            "post-codegen physics confirmation is disabled; "
            "model assumptions must be confirmed before Geant4 codegen"
        )
        self.state.update(
            {
                "confirmation_status": "rejected",
                "human_confirmation_required": False,
                "g4_codegen_status": "failed",
            }
        )
        self._set_termination_reason(reason)
        self._emit(
            "legacy_codegen_physics_confirmation_rejected",
            status="error",
            phase="human_confirmation",
            summary=reason,
            payload=response,
        )
        self._persist_phase_state("human_confirmation", status_override="failed")
        return self.get_status()

    async def _submit_requirements_review_confirmation(
        self,
        response: dict[str, Any],
        *,
        auto_continue: bool,
    ) -> JobStatus:
        from agent_core.requirements_review import (
            approve_requirements_review,
            reject_requirements_review,
        )

        decision = str(response.get("user_decision", "") or "").lower()
        approved = decision in {"approve", "approved", "yes", "y", "确认", "同意"}
        if approved:
            updates = approve_requirements_review(self.state, response)
            self.state.update(updates)
            self.current_phase_idx = PIPELINE_PHASES.index("g4_modeling")
            self.state.pop("termination_reason", None)
            self._emit(
                "requirements_review_approved",
                status="info",
                phase="requirements_review",
                summary="Simulation requirements review approved.",
                payload=updates,
            )
            self._persist_phase_state("requirements_review", status_override="success")
            if auto_continue:
                await self.run_until_blocked()
            return self.get_status()

        updates = reject_requirements_review(self.state, response)
        self.state.update(updates)
        self._set_termination_reason("requirements review rejected by user")
        self._emit(
            "requirements_review_rejected",
            status="warning",
            phase="requirements_review",
            summary="Simulation requirements review rejected by user.",
            payload=updates,
        )
        self._persist_phase_state("requirements_review", status_override="failed")
        return self.get_status()

    async def submit_repair_continuation(
        self,
        response: dict[str, Any],
        *,
        auto_continue: bool = True,
    ) -> JobStatus:
        if not self.state.get("job_id"):
            raise RuntimeError("No active job.")
        request = dict(self.state.get("repair_continuation_request") or {})
        if not request or request.get("status") != "pending":
            raise RuntimeError("No pending repair continuation request.")
        decision = str(response.get("user_decision", "") or "").lower()
        approved = decision in {"approve", "approved", "yes", "y", "确认", "同意"}
        if not approved:
            self.state["repair_continuation_status"] = "rejected"
            self.state["repair_continuation_response"] = response
            self._set_termination_reason("repair continuation rejected by user")
            self._emit(
                "repair_continuation_rejected",
                status="warning",
                phase="g4_codegen",
                summary="Repair continuation rejected by user.",
                payload=response,
            )
            self._persist_phase_state("g4_codegen", status_override="failed")
            return self.get_status()

        requested_total = int(request.get("requested_total_turns") or 0)
        self.state["repair_continuation_status"] = "approved"
        self.state["repair_continuation_response"] = response
        self.state["agentic_repair_max_turns_override"] = requested_total
        self.state["g4_codegen_status"] = ""
        self.state["repair_continuation_request"] = {
            **request,
            "status": "approved",
        }
        self._emit(
            "repair_continuation_approved",
            status="info",
            phase="g4_codegen",
            summary=f"Approved repair continuation to {requested_total} turns.",
            payload=self.state["repair_continuation_request"],
        )
        if "g4_codegen" in PIPELINE_PHASES:
            self.current_phase_idx = PIPELINE_PHASES.index("g4_codegen")
        if "g4_codegen" in self.completed_phases:
            self.completed_phases.remove("g4_codegen")
        self.state.pop("termination_reason", None)
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
        if phase == "context" and route_after_context(self.state) != "task_planning_subgraph":
            return f"context status is {self.state.get('context_decision') or 'missing'}"
        expectations = {
            "task_planning": ("task_planning_status", {"passed"}),
            "requirements_review": (
                "requirements_review_status",
                {"approved", "pending", "needs_user_input"},
            ),
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
        if phase == "g4_codegen" and value == "needs_user_input":
            return ""
        return f"{key.removesuffix('_status')} status is {value or 'missing'}"

    def _is_repair_continuation_pending(self) -> bool:
        request = self.state.get("repair_continuation_request")
        status = str(self.state.get("repair_continuation_status") or "")
        return (
            isinstance(request, dict)
            and request.get("status") == "pending"
            and status not in {"approved", "rejected"}
        )

    def _is_requirements_review_pending(self) -> bool:
        return (
            _requirements_review_waiting_status(self.state.get("requirements_review_status"))
            and bool(self.state.get("human_confirmation_required"))
            and not bool(self.state.get("raw_human_response"))
        )

    def _is_human_confirmation_pending(self) -> bool:
        return (
            bool(self.state.get("human_confirmation_required"))
            and str(self.state.get("confirmation_status") or "") == "pending"
            and not bool(self.state.get("raw_human_response"))
        )

    def _set_termination_reason(self, reason: str) -> None:
        self.state["termination_reason"] = reason
        errors = self.state.setdefault("errors", [])
        if isinstance(errors, list) and reason and reason not in errors:
            errors.append(reason)

    async def _prepare_browser_visualization_after_patch(self) -> dict[str, Any]:
        """Build and run the generated project so the browser 3D view has real data."""
        if self.state.get("patch_status") != "applied":
            return {}
        if self.state.get("auto_visualization_status") == "ready":
            return {}

        try:
            build = await self.build_generated_code()
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            return {
                "auto_visualization_status": "failed",
                "patch_status": "failed",
                "errors": [*(self.state.get("errors") or []), message],
            }
        if not build.success:
            return {
                "auto_visualization_status": "failed",
                "auto_build_result": build.model_dump(),
                "patch_status": "failed",
                "errors": [*(self.state.get("errors") or []), build.errors or "build failed"],
            }

        try:
            simulation = await self.run_simulation(events=1000)
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            return {
                "auto_visualization_status": "failed",
                "auto_build_result": build.model_dump(),
                "patch_status": "failed",
                "errors": [*(self.state.get("errors") or []), message],
            }
        if not simulation.success:
            return {
                "auto_visualization_status": "failed",
                "auto_build_result": build.model_dump(),
                "auto_simulation_result": simulation.model_dump(),
                "patch_status": "failed",
                "errors": [
                    *(self.state.get("errors") or []),
                    simulation.errors or "simulation failed",
                ],
            }

        return {
            "auto_visualization_status": "ready",
            "auto_build_result": build.model_dump(),
            "auto_simulation_result": simulation.model_dump(),
        }

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
        if self._is_repair_continuation_pending():
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
        self._sync_current_node_for_status(current_phase)
        runtime_active = self._runtime_active()
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
                "repair_continuation_status",
                "termination_reason",
            )
            if self.state.get(key) is not None
        }
        key_statuses["runtime_active"] = runtime_active
        status = "idle"
        if self.state.get("job_id"):
            status = "completed" if self.current_phase_idx >= len(PIPELINE_PHASES) else "running"
            if self.state.get("confirmation_status") == "pending":
                status = "paused"
            if self._is_requirements_review_pending():
                status = "paused"
            if self._is_repair_continuation_pending():
                status = "paused"
            if _state_has_legacy_codegen_physics_confirmation(self.state):
                status = "failed"
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
            needs_confirmation=(
                (
                    bool(self.state.get("human_confirmation_required"))
                    or self.state.get("confirmation_status") == "pending"
                )
                and not _is_modeling_failure_state(self.state)
                and not _state_has_legacy_codegen_physics_confirmation(self.state)
            )
            or self._is_requirements_review_pending()
            or self._is_repair_continuation_pending(),
            key_statuses=key_statuses,
            state={**dict(self.state), "runtime_active": runtime_active},
        )

    def _sync_current_node_for_status(self, current_phase: str) -> None:
        if not current_phase:
            return
        if (
            self.state.get("current_node") == "human_confirmation_subgraph"
            and self.state.get("confirmation_status") == "approved"
            and not bool(self.state.get("human_confirmation_required"))
            and current_phase != "human_confirmation"
        ):
            self.state["current_node"] = f"{current_phase}_subgraph"

    def resume_job(self, job_id: str, *, clear_failure: bool = False) -> JobStatus:
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
        self._normalize_resumed_progress()
        if clear_failure:
            self._clear_previous_failure()
        self.execution_mode = str(self.state.get("execution_mode", self.execution_mode))
        self._emit("job_resumed", status="success", summary=job_id)
        return self.get_status()

    def _normalize_resumed_progress(self) -> None:
        highest_completed_idx = -1
        for phase in self.completed_phases:
            if phase in PIPELINE_PHASES:
                highest_completed_idx = max(highest_completed_idx, PIPELINE_PHASES.index(phase))
        if highest_completed_idx >= 0:
            self.current_phase_idx = max(self.current_phase_idx, highest_completed_idx + 1)
        self.current_phase_idx = min(self.current_phase_idx, len(PIPELINE_PHASES))
        if "g4_codegen" in self.completed_phases:
            self.state["g4_codegen_status"] = "passed"
        if "patch" in self.completed_phases:
            self.state["patch_status"] = "applied"
        if "gate" in self.completed_phases:
            self.state["validation_status"] = "passed"
        if "artifact" in self.completed_phases:
            self.state["artifact_status"] = "collected"
        if self.current_phase_idx < len(PIPELINE_PHASES):
            current_phase = PIPELINE_PHASES[self.current_phase_idx]
            self.state["current_node"] = f"{current_phase}_subgraph"

    def _clear_previous_failure(self) -> None:
        self.state.pop("termination_reason", None)
        self.state["errors"] = []

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
        artifact_path = self._resolve_artifact_path(path)
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

    def _resolve_artifact_path(self, path: str) -> Path:
        artifact_path = Path(path)
        if artifact_path.is_absolute() or artifact_path.exists():
            return artifact_path
        job_id = str(self.state.get("job_id", ""))
        if job_id:
            job_relative = self.workspace.root / "jobs" / job_id / path
            if job_relative.exists():
                return job_relative
        return artifact_path

    def get_model_ir(self, job_id: str | None = None) -> dict[str, Any] | None:
        state = self._state_for_job(job_id)
        path = state.get("g4_model_ir_path", "")
        if not path or not Path(path).is_file():
            return None
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def get_visualization_payload(self, job_id: str | None = None) -> dict[str, Any]:
        from agent_core.tools.geant4_workbench import VISUAL_WORKBENCH_EVENTS
        from agent_core.web.visualization import build_visualization_payload

        state = self._state_for_job(job_id)
        output_dir = (
            str(state.get("_visual_output_dir") or "")
            or str(state.get("visual_output_dir") or "")
            or str(state.get("_sim_output_dir") or "")
        )
        model_ir = state.get("g4_model_ir")
        if not isinstance(model_ir, dict):
            model_ir = self.get_model_ir(job_id) or {}
        return build_visualization_payload(
            output_dir=output_dir or None,
            job_id=str(job_id or state.get("job_id", "")),
            model_ir=model_ir,
            visual_events=VISUAL_WORKBENCH_EVENTS,
        )

    def get_gate_results(self, job_id: str | None = None) -> list[dict[str, Any]]:
        state = self._state_for_job(job_id)
        path = state.get("gate_results_path", "")
        if not path or not Path(path).is_file():
            return []
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        results = data if isinstance(data, list) else data.get("results", [])
        return _active_gate_results(results)

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
        if _is_modeling_failure_state(state):
            return self._modeling_failure_review(state)
        if _state_has_legacy_codegen_physics_confirmation(state):
            return self._legacy_codegen_physics_confirmation_review(state)
        if _requirements_review_waiting_status(state.get("requirements_review_status")):
            return self._requirements_review_confirmation_review(state)
        request = state.get("repair_continuation_request")
        if (
            isinstance(request, dict)
            and request.get("status") == "pending"
            and state.get("repair_continuation_status") != "rejected"
        ):
            return self._repair_continuation_review(state, request)
        confirmation_dir = (
            Path(str(state["job_workspace"])) / STAGE_HUMAN_CONFIRMATION
            if state.get("job_workspace")
            else None
        )
        report_path = str(state.get("confirmation_report_path", ""))
        if not report_path and confirmation_dir is not None:
            candidate = confirmation_dir / HC_REPORT
            if candidate.is_file():
                report_path = str(candidate)
        preview = ""
        if report_path and Path(report_path).is_file():
            preview = Path(report_path).read_text(encoding="utf-8", errors="replace")[:8000]
        request_path = str(state.get("confirmation_request_path", ""))
        if not request_path and confirmation_dir is not None:
            round_n = int(state.get("human_confirmation_round", 1) or 1)
            candidate = confirmation_dir / HC_REQUEST_TEMPLATE.format(round=round_n)
            if not candidate.is_file():
                candidates = sorted(confirmation_dir.glob("confirmation_request_round_*.json"))
                candidate = candidates[-1] if candidates else candidate
            if candidate.is_file():
                request_path = str(candidate)
        proposal_path = str(state.get("proposed_model_completion_path", ""))
        if not proposal_path and confirmation_dir is not None:
            candidate = confirmation_dir / "proposed_model_completion.json"
            if candidate.is_file():
                proposal_path = str(candidate)
        confirmation_request = self._read_json_file(request_path)
        proposed_model_completion = self._read_json_file(proposal_path)
        summary = str(
            confirmation_request.get("summary_for_user")
            or proposed_model_completion.get("summary_for_user")
            or state.get("confirmation_summary")
            or "请确认本轮 Geant4 模型假设、关键参数和继续执行条件。"
        ).strip()
        missing_information = _as_list(
            proposed_model_completion.get("missing_information")
        ) + _as_list(confirmation_request.get("missing_information"))
        critical_confirmations = _as_list(confirmation_request.get("critical_confirmations"))
        questions = _as_list(confirmation_request.get("questions"))
        assumptions = _as_list(proposed_model_completion.get("assumptions")) + _as_list(
            confirmation_request.get("assumptions")
        )
        return {
            "status": state.get("confirmation_status", ""),
            "required": bool(state.get("human_confirmation_required")),
            "actionable": _confirmation_actionable(state),
            "summary": summary,
            "summary_for_user": summary,
            "missing_information": missing_information,
            "critical_confirmations": critical_confirmations,
            "questions": questions,
            "assumptions": assumptions,
            "unconfirmed_assumptions_count": state.get("unconfirmed_assumptions_count", 0),
            "report_path": report_path,
            "request_path": request_path,
            "record_path": state.get("confirmation_record_path", ""),
            "confirmed_model_plan_path": state.get("confirmed_model_plan_path", ""),
            "confirmation_request": confirmation_request,
            "proposed_model_completion": proposed_model_completion,
            "preview": preview,
        }

    async def get_workflow_diagnosis(self, job_id: str | None = None) -> dict[str, Any]:
        state = self._state_for_job(job_id)
        baseline = self._deterministic_workflow_diagnosis(state, job_id=job_id)
        try:
            model_patch = await self._lite_workflow_diagnosis_patch(state, baseline)
        except Exception as exc:
            return {
                **baseline,
                "model_enhanced": False,
                "model_error": str(exc),
            }
        if not model_patch:
            return baseline
        enhanced = dict(baseline)
        for key in ("user_message", "blocking_reason", "next_step_hint"):
            value = str(model_patch.get(key) or "").strip()
            if value:
                enhanced[key] = value
        enhanced["model_enhanced"] = True
        return enhanced

    def _deterministic_workflow_diagnosis(
        self,
        state: dict[str, Any],
        *,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        status = (
            self.get_status()
            if not job_id or job_id == self.state.get("job_id")
            else JobStatus(
                job_id=str(state.get("job_id", job_id or "")),
                user_query=str(state.get("user_query", "")),
                status=str(state.get("status", "running")),
                current_phase=str(state.get("current_node", "")),
                current_phase_idx=int(state.get("current_phase_idx", 0)),
                completed_phases=list(state.get("completed_phases", [])),
                execution_mode=str(state.get("execution_mode", self.execution_mode)),
                run_mode=str(state.get("run_mode", "strict")),
                workspace_root=str(state.get("workspace_root", self.workspace.root)),
                job_workspace=str(state.get("job_workspace", "")),
            )
        )
        if _is_modeling_failure_state(state):
            review = self._modeling_failure_review(state)
            summary = str(review.get("summary") or "Geant4 modeling failed.")
            report_path = str(review.get("validation_report_path") or "")
            return {
                "ui_state": "modeling_failed",
                "severity": "error",
                "phase": "g4_modeling",
                "status": status.model_dump(mode="json"),
                "user_message": f"建模阶段失败，人工确认不能批准。{summary}",
                "blocking_reason": summary,
                "confirmation_actionable": False,
                "allowed_actions": ["view_modeling_report", "retry_modeling"],
                "next_step_hint": "请先查看建模校验报告并重新运行建模；通过后才会进入人工确认。",
                "artifacts": [report_path] if report_path else [],
                "hard_rules": {
                    "confirmation_actionable": False,
                    "reason": "g4_modeling_status is not passed",
                },
                "model_enhanced": False,
            }
        if (
            str(state.get("g4_codegen_status") or "").lower() == "failed"
            and not self._is_repair_continuation_pending()
        ):
            codegen_errors = [
                str(error).strip()
                for error in state.get("codegen_errors", []) or state.get("errors", []) or []
                if str(error).strip()
            ]
            summary = "; ".join(codegen_errors[:3]) or str(
                state.get("termination_reason") or "Geant4 code generation failed."
            )
            patch_path = str(state.get("proposed_patch_path") or "")
            if not patch_path:
                job_workspace = str(state.get("job_workspace") or "")
                candidate = (
                    Path(job_workspace) / STAGE_CODEGEN / "proposed_patch.json"
                    if job_workspace
                    else None
                )
                if candidate and candidate.is_file():
                    patch_path = str(candidate)
            return {
                "ui_state": "codegen_failed",
                "severity": "error",
                "phase": "g4_codegen",
                "status": status.model_dump(mode="json"),
                "user_message": f"Geant4 工程生成失败，不能进入人工确认。{summary}",
                "blocking_reason": summary,
                "confirmation_actionable": False,
                "allowed_actions": ["view_codegen_patch", "view_logs", "retry_codegen"],
                "next_step_hint": "点击重试阶段会复用当前作业，从失败阶段继续修复和生成。",
                "artifacts": [patch_path] if patch_path else [],
                "hard_rules": {
                    "confirmation_actionable": False,
                    "reason": "g4_codegen_status is failed",
                },
                "model_enhanced": False,
            }
        if self._is_repair_continuation_pending():
            review = self.get_confirmation_review(job_id)
            return {
                "ui_state": "repair_continuation_pending",
                "severity": "warning",
                "phase": "g4_codegen",
                "status": status.model_dump(mode="json"),
                "user_message": str(review.get("summary") or "修复轮数已耗尽，需要批准是否继续。"),
                "blocking_reason": "repair_continuation_status is pending",
                "confirmation_actionable": True,
                "allowed_actions": ["approve_repair_continuation", "reject_repair_continuation"],
                "next_step_hint": "批准后会追加修复轮数继续当前 Geant4 工程修复。",
                "artifacts": [],
                "hard_rules": {"confirmation_actionable": True},
                "model_enhanced": False,
            }
        if self._is_requirements_review_pending():
            review = self.get_confirmation_review(job_id)
            request_path = str(review.get("request_path") or "")
            return {
                "ui_state": "requirements_review_pending",
                "severity": "warning",
                "phase": "requirements_review",
                "status": status.model_dump(mode="json"),
                "user_message": str(review.get("summary") or "需要先核对 Geant4 建模需求参数。"),
                "blocking_reason": "requirements_review_status is needs_user_input",
                "confirmation_actionable": True,
                "allowed_actions": [
                    "review_requirements",
                    "approve_requirements",
                    "reject_requirements",
                ],
                "next_step_hint": "确认参数卡片后再进入 Geant4 建模；不明确时在反馈中补充参数。",
                "artifacts": [request_path] if request_path else [],
                "hard_rules": {"confirmation_actionable": True},
                "model_enhanced": False,
            }
        if status.needs_confirmation:
            review = self.get_confirmation_review(job_id)
            return {
                "ui_state": "human_confirmation_pending",
                "severity": "warning",
                "phase": "human_confirmation",
                "status": status.model_dump(mode="json"),
                "user_message": str(review.get("summary") or "需要人工确认模型假设和关键参数。"),
                "blocking_reason": "human_confirmation_required",
                "confirmation_actionable": True,
                "allowed_actions": [
                    "review_confirmation",
                    "approve_confirmation",
                    "ask_more",
                    "reject_confirmation",
                ],
                "next_step_hint": "打开确认项，确认参数含义后再批准；不清楚时要求 Agent 继续追问。",
                "artifacts": [
                    str(review.get("request_path") or ""),
                    str(review.get("report_path") or ""),
                ],
                "hard_rules": {"confirmation_actionable": True},
                "model_enhanced": False,
            }
        return {
            "ui_state": status.status,
            "severity": "info" if status.status not in {"failed"} else "error",
            "phase": status.current_phase,
            "status": status.model_dump(mode="json"),
            "user_message": (
                f"当前工作流状态：{status.status}，阶段："
                f"{status.current_phase or 'idle'}。"
            ),
            "blocking_reason": str(state.get("termination_reason") or ""),
            "confirmation_actionable": False,
            "allowed_actions": ["status", "logs"],
            "next_step_hint": "查看状态和日志确认下一步。",
            "artifacts": [],
            "hard_rules": {"confirmation_actionable": False},
            "model_enhanced": False,
        }

    async def _lite_workflow_diagnosis_patch(
        self,
        state: dict[str, Any],
        baseline: dict[str, Any],
    ) -> dict[str, Any]:
        from agent_core.models.gateway import get_model_gateway

        payload = {
            "baseline": baseline,
            "state_excerpt": {
                key: state.get(key)
                for key in (
                    "job_id",
                    "user_query",
                    "current_node",
                    "g4_modeling_status",
                    "g4_codegen_status",
                    "patch_status",
                    "validation_status",
                    "confirmation_status",
                    "human_confirmation_required",
                    "termination_reason",
                    "errors",
                )
                if state.get(key) is not None
            },
            "recent_events": [event.model_dump(mode="json") for event in self.recent_events(8)],
        }
        result = await get_model_gateway().call(
            ModelTask.FAILURE_DIAGNOSIS,
            (
                "You are a RadAgent workflow diagnosis assistant. Return JSON only. "
                "Explain the current workflow state to a user in concise Chinese. "
                "Do not decide permissions; hard_rules in baseline are authoritative."
            ),
            json.dumps(payload, ensure_ascii=False, indent=2),
            tier=ModelTier.LITE,
            response_format="json",
            temperature=0.0,
            max_tokens=700,
            metadata={
                "module_name": "workflow_diagnosis",
                "job_id": str(state.get("job_id", "")),
            },
        )
        if result.error:
            return {}
        parsed = result.parsed_json
        return parsed if isinstance(parsed, dict) else {}

    def _repair_continuation_review(
        self,
        state: dict[str, Any],
        request: dict[str, Any],
    ) -> dict[str, Any]:
        current_turns = request.get("current_turns", 0)
        increment = request.get("increment_turns", 12)
        requested_total = request.get("requested_total_turns", 0)
        message = str(request.get("message") or "")
        if not message:
            message = f"修复 Agent 已耗尽 {current_turns} 轮，是否增加 {increment} 轮继续修复？"
        return {
            "status": "pending",
            "required": True,
            "type": "repair_continuation",
            "summary": message,
            "summary_for_user": message,
            "missing_information": [],
            "critical_confirmations": [
                {
                    "field_path": "g4_codegen.repair_continuation",
                    "category": "repair_continuation",
                    "proposed_value": f"+{increment} turns",
                    "impact": (
                        "批准后会继续当前 Geant4 代码修复，不重新创建 job；"
                        "拒绝则保留失败状态。"
                    ),
                }
            ],
            "questions": [
                {
                    "question": f"是否增加 {increment} 轮，让 Agent 继续修复当前失败？",
                    "category": "repair_continuation",
                    "proposed_value": f"total={requested_total}",
                    "impact": "除非你拒绝，否则每次耗尽后都会再次询问。",
                }
            ],
            "repair_continuation_request": request,
            "preview": json.dumps(
                {
                    "job_id": state.get("job_id", ""),
                    "current_phase": "g4_codegen",
                    "current_turns": current_turns,
                    "increment_turns": increment,
                    "requested_total_turns": requested_total,
                    "last_errors": state.get("codegen_errors", [])[-8:],
                },
                ensure_ascii=False,
                indent=2,
            ),
        }

    def _modeling_failure_review(self, state: dict[str, Any]) -> dict[str, Any]:
        report_path = str(state.get("validation_report_path", ""))
        if not report_path and state.get("job_workspace"):
            candidate = (
                Path(str(state["job_workspace"]))
                / STAGE_MODEL_IR
                / "validation_report.json"
            )
            if candidate.is_file():
                report_path = str(candidate)
        report = self._read_json_file(report_path)
        errors = _modeling_validation_errors(report)
        if not errors:
            errors = [
                str(item)
                for item in state.get("errors", [])
                if str(item).strip()
            ]
        reason = str(state.get("termination_reason") or "Geant4 modeling failed.")
        summary = "; ".join(errors[:3]) if errors else reason
        preview_lines = [
            "Geant4 modeling failed before human confirmation.",
            f"Reason: {reason}",
        ]
        if report_path:
            preview_lines.append(f"Validation report: {report_path}")
        if errors:
            preview_lines.append("Blocking modeling errors:")
            preview_lines.extend(f"- {error}" for error in errors[:12])
        return {
            "type": "modeling_failure",
            "status": "failed",
            "required": False,
            "actionable": False,
            "summary": summary,
            "summary_for_user": summary,
            "missing_information": [],
            "critical_confirmations": [],
            "questions": [],
            "report_path": "",
            "request_path": "",
            "record_path": "",
            "confirmed_model_plan_path": "",
            "validation_report_path": report_path,
            "confirmation_request": {},
            "proposed_model_completion": {},
            "preview": "\n".join(preview_lines),
        }

    def _requirements_review_confirmation_review(self, state: dict[str, Any]) -> dict[str, Any]:
        request_path = str(
            state.get("requirements_review_request_path")
            or state.get("confirmation_request_path")
            or ""
        )
        request = self._read_json_file(request_path)
        summary = str(
            request.get("summary_for_user")
            or state.get("confirmation_summary")
            or "请确认仿真目标、关键参数和继续执行条件。"
        )
        return {
            "type": "requirements_review",
            "status": state.get("requirements_review_status", "pending"),
            "required": True,
            "actionable": True,
            "summary": summary,
            "summary_for_user": summary,
            "missing_information": _as_list(request.get("missing_information")),
            "critical_confirmations": _as_list(request.get("critical_confirmations")),
            "questions": _as_list(request.get("questions")),
            "assumptions": _as_list(request.get("physics_risks")),
            "ambiguous_fields": _as_list(
                request.get("ambiguous_fields") or request.get("ambiguous_parameters")
            ),
            "requirements_review": request,
            "unconfirmed_assumptions_count": len(_as_list(request.get("ambiguous_fields"))),
            "report_path": "",
            "request_path": request_path,
            "record_path": "",
            "confirmed_model_plan_path": "",
            "confirmation_request": request,
            "proposed_model_completion": {
                "proposed_parameters": _as_list(request.get("proposed_parameters")),
                "proposed_scoring": [],
                "proposed_sources": [],
                "assumptions": _as_list(request.get("physics_risks")),
                "missing_information": _as_list(request.get("missing_information")),
                "ambiguous_fields": _as_list(
                    request.get("ambiguous_fields") or request.get("ambiguous_parameters")
                ),
            },
            "preview": json.dumps(request, indent=2, ensure_ascii=False) if request else "",
        }

    def _legacy_codegen_physics_confirmation_review(self, state: dict[str, Any]) -> dict[str, Any]:
        request_path = str(state.get("confirmation_request_path", ""))
        summary = (
            "Post-codegen physics confirmation is disabled. Model assumptions "
            "must be confirmed before Geant4 code generation."
        )
        return {
            "type": "legacy_codegen_physics_confirmation_disabled",
            "status": "failed",
            "required": False,
            "actionable": False,
            "summary": summary,
            "summary_for_user": summary,
            "missing_information": [],
            "critical_confirmations": [],
            "questions": [],
            "assumptions": [],
            "unconfirmed_assumptions_count": 0,
            "report_path": "",
            "request_path": request_path,
            "record_path": "",
            "confirmed_model_plan_path": "",
            "confirmation_request": self._read_json_file(request_path),
            "proposed_model_completion": {},
            "preview": summary,
        }

    def _read_json_file(self, path: str) -> dict[str, Any]:
        if not path:
            return {}
        target = Path(path)
        if not target.is_file():
            return {}
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("Failed to read JSON file %s: %s", path, exc)
            return {}
        return data if isinstance(data, dict) else {}

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
            if isinstance(data.get("gate_results"), list):
                data = {**data, "gate_results": _active_gate_results(data.get("gate_results"))}
            return data
        if isinstance(data, list):
            results = _active_gate_results(data)
            failed = [g for g in results if g.get("status") in {"fail", "block", "blocked"}]
            return {
                "validation_status": "failed" if failed else "passed",
                "gate_results": results,
            }
        return {"validation_status": "invalid", "gate_results": []}

    def _state_for_job(self, job_id: str | None) -> dict[str, Any]:
        if not job_id or job_id == self.state.get("job_id"):
            return self.state
        snapshot = self.store.latest_state_snapshot(job_id)
        if snapshot is not None:
            return dict(snapshot["state"])
        self.store.import_existing_jobs()
        job = self.store.get_job(job_id)
        if job is None:
            return {}
        job_workspace = str(job.get("job_workspace") or "")
        confirmation_dir = (
            Path(job_workspace) / STAGE_HUMAN_CONFIRMATION
            if job_workspace
            else None
        )
        confirmed_path = (
            confirmation_dir / "confirmed_model_plan.json"
            if confirmation_dir is not None
            else None
        )
        record_path = (
            confirmation_dir / "confirmation_record.json"
            if confirmation_dir is not None
            else None
        )
        request_paths = (
            sorted(confirmation_dir.glob("confirmation_request_round_*.json"))
            if confirmation_dir is not None and confirmation_dir.is_dir()
            else []
        )
        confirmed_plan = self._read_json_file(str(confirmed_path or ""))
        confirmation_record = self._read_json_file(str(record_path or ""))
        confirmation_status = str(
            confirmed_plan.get("confirmation_status")
            or confirmation_record.get("final_status")
            or ("pending" if request_paths else "")
        )
        return {
            "job_id": str(job.get("job_id") or job_id),
            "user_query": str(job.get("user_query") or ""),
            "status": str(job.get("status") or ""),
            "current_phase": str(job.get("current_phase") or ""),
            "current_phase_idx": int(job.get("current_phase_idx") or 0),
            "execution_mode": str(job.get("execution_mode") or "strict"),
            "run_mode": str(job.get("run_mode") or "strict"),
            "workspace_root": str(self.workspace.root),
            "job_workspace": job_workspace,
            "confirmation_status": confirmation_status,
            "human_confirmation_required": confirmation_status == "pending",
        }

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
        events = max(1, int(events or 1))
        executable = str(self.state.get("_executable_path", ""))
        if not executable or not Path(executable).exists():
            raise RuntimeError("No built executable in current state.")
        code_dir = str(self.state.get("generated_code_dir", ""))
        if not code_dir or not Path(code_dir).exists():
            raise RuntimeError("No generated code directory in current state.")
        job_id = str(self.state.get("job_id", "repl_run"))
        production_output_dir = Path(self.workspace.get_job(job_id).output_dir())
        visual_output_dir = production_output_dir / "visual_100"

        from agent_core.tools.geant4_runner import Geant4Runner
        from agent_core.tools.geant4_workbench import VISUAL_WORKBENCH_EVENTS

        runner = Geant4Runner()
        visual_events = VISUAL_WORKBENCH_EVENTS
        self._emit(
            "simulation_visual_started",
            status="running",
            summary=f"{visual_events} events for browser 3D view",
            payload={
                "events": visual_events,
                "executable": executable,
                "output_dir": str(visual_output_dir),
            },
        )
        visual_raw = await self._run_simulation_batch(
            runner=runner,
            executable=executable,
            code_dir=code_dir,
            output_dir=visual_output_dir,
            job_id=job_id,
            events=visual_events,
        )
        visual_success = bool(visual_raw.get("success"))
        self.state["_visual_output_dir"] = str(visual_raw.get("output_dir", visual_output_dir))
        self._remember_visual_artifacts(Path(self.state["_visual_output_dir"]))
        self._emit(
            "simulation_visual_finished" if visual_success else "simulation_visual_failed",
            status="success" if visual_success else "error",
            summary=self.state["_visual_output_dir"]
            if visual_success
            else str(visual_raw.get("errors", "")),
            payload={
                "events": visual_events,
                "output_dir": self.state["_visual_output_dir"],
                "success": visual_success,
            },
        )

        self._emit(
            "simulation_started",
            status="running",
            summary=f"{events} events",
            payload={
                "events": events,
                "executable": executable,
                "output_dir": str(production_output_dir),
            },
        )
        production_raw = await self._run_simulation_batch(
            runner=runner,
            executable=executable,
            code_dir=code_dir,
            output_dir=production_output_dir,
            job_id=job_id,
            events=events,
        )
        production_success = bool(production_raw.get("success"))
        production_result_dir = str(production_raw.get("output_dir", production_output_dir))
        self.state["_sim_output_dir"] = production_result_dir
        errors = "\n".join(
            item
            for item in [
                str(visual_raw.get("errors", "")),
                str(production_raw.get("errors", "")),
            ]
            if item
        )
        result = SimulationResult(
            success=visual_success and production_success,
            events=events,
            visual_events=visual_events,
            visual_success=visual_success,
            visual_output_dir=self.state["_visual_output_dir"],
            production_success=production_success,
            production_output_dir=production_result_dir,
            output_dir=production_result_dir,
            log="\n".join(
                item
                for item in [
                    str(visual_raw.get("log", "")),
                    str(production_raw.get("log", "")),
                ]
                if item
            ),
            errors=errors,
        )
        if result.success:
            self.record_state_artifacts(job_id)
        self._emit(
            "simulation_finished" if result.success else "simulation_failed",
            status="success" if result.success else "error",
            summary=result.output_dir if result.success else result.errors,
            payload=result.model_dump(),
        )
        return result

    async def _run_simulation_batch(
        self,
        *,
        runner: Any,
        executable: str,
        code_dir: str,
        output_dir: Path,
        job_id: str,
        events: int,
    ) -> dict[str, Any]:
        from agent_core.tools.geant4_workbench import prepare_self_check_macro

        output_dir.mkdir(parents=True, exist_ok=True)
        macro = prepare_self_check_macro(code_dir, events=events)
        raw = await runner.simulate(
            executable=executable,
            macro=str(macro),
            events=events,
            output_dir=str(output_dir),
            job_id=job_id,
        )
        runner.materialize_output_contract(
            output_dir=str(raw.get("output_dir", output_dir)),
            executable_dir=str(Path(executable).parent),
            job_id=job_id,
            events=events,
            sim=raw,
        )
        return raw

    def _remember_visual_artifacts(self, output_dir: Path) -> None:
        for name, key in (
            ("geometry_view.json", "visual_geometry_view_path"),
            ("particle_tracks.json", "visual_particle_tracks_path"),
            ("energy_deposits.json", "visual_energy_deposits_path"),
            ("edep_3d.csv", "visual_edep_3d_path"),
        ):
            path = output_dir / name
            if path.is_file():
                self.state[key] = str(path)
