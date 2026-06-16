from __future__ import annotations

import inspect
from typing import Any

from pydantic import BaseModel

from agent_core.pipeline import PIPELINE_PHASES
from agent_core.tui.commands import CommandParseError, command_suggestions, parse_command


PANEL_COMMANDS: dict[str, str] = {
    "check": "tools",
    "inspect": "tools",
    "status": "status",
    "jobs": "jobs",
    "artifacts": "artifacts",
    "gates": "gates",
    "logs": "logs",
    "model": "model",
    "projects": "projects",
    "revisions": "revisions",
    "confirm": "confirmation",
    "credibility": "credibility",
    "diagnose": "diagnosis",
    "memory": "memory",
    "help": "help",
    "options": "options",
}

_REQUIRED_COMMANDS: dict[str, str] = {
    "accept-revision": "Accept a saved revision",
    "approve": "Approve active human confirmation",
    "artifact": "Preview one artifact path",
    "ask-more": "Request more human-confirmation detail",
    "build": "Build generated code",
    "chat": "Ask RadAgent directly",
    "confirm": "Open confirmation review",
    "credibility": "Open credibility report",
    "diagnose": "Explain current workflow block",
    "exit": "Exit the workbench",
    "gates": "Open gate results",
    "logs": "Open service event log",
    "memory": "Open workflow memory",
    "model": "View or update model settings",
    "model-health": "Test model API health and latency",
    "options": "Open workbench options",
    "project": "Switch project",
    "projects": "List projects",
    "reject": "Reject active human confirmation",
    "reject-revision": "Reject a saved revision",
    "revision": "Open one revision",
    "simulate": "Run the generated simulator",
    "step": "Run the next pipeline phase",
}

_COMMAND_AUDIT: dict[str, dict[str, str | bool]] = {
    "run": {
        "module": "workflow/start_job",
        "connection": "service",
        "visible": True,
        "tip": "Start a real RadAgent workflow from a simulation request.",
    },
    "approve": {
        "module": "human_confirmation",
        "connection": "service",
        "visible": True,
        "tip": "Approve the active human-confirmation gate without blocking the web request.",
    },
    "check": {
        "module": "runtime/tools",
        "connection": "service",
        "visible": True,
        "tip": "Inspect configured runtime tools and model availability before running work.",
    },
    "open": {
        "module": "artifacts",
        "connection": "derived",
        "visible": True,
        "tip": "Open or narrow the artifact browser around a target such as report.",
    },
    "report": {
        "module": "artifacts/report",
        "connection": "derived",
        "visible": True,
        "tip": "Show report artifacts produced by the active or selected workflow.",
    },
    "demo": {
        "module": "client/demo-template",
        "connection": "client",
        "visible": False,
        "tip": "TUI demo shortcut only; Web should use explicit /run requests instead.",
    },
    "help": {
        "module": "command_palette",
        "connection": "panel",
        "visible": True,
        "tip": "Open the curated command palette with connected modules and tips.",
    },
    "history": {
        "module": "client/history",
        "connection": "client",
        "visible": False,
        "tip": "TUI local input history; Web timeline already keeps command history.",
    },
    "jobs": {
        "module": "job_store",
        "connection": "service",
        "visible": True,
        "tip": "Browse saved jobs across projects.",
    },
    "job": {
        "module": "job_store",
        "connection": "service",
        "visible": True,
        "tip": "Open one job detail by job id.",
    },
    "artifacts": {
        "module": "artifacts",
        "connection": "service",
        "visible": True,
        "tip": "Browse outputs, logs, reports, source files, and generated data.",
    },
    "inspect": {
        "module": "runtime/tools",
        "connection": "alias",
        "visible": False,
        "tip": "Alias of /check; hidden to avoid duplicate tool-inspection entries.",
    },
    "status": {
        "module": "job_status",
        "connection": "service",
        "visible": True,
        "tip": "Show active job state, phase, run mode, and confirmation status.",
    },
    "mode": {
        "module": "client/composer",
        "connection": "client",
        "visible": False,
        "tip": "TUI composer-mode switch; Web uses visible controls instead.",
    },
    "resume": {
        "module": "job_control",
        "connection": "service",
        "visible": True,
        "tip": "Resume a saved job without automatically retrying the pipeline.",
    },
    "retry": {
        "module": "job_control",
        "connection": "service",
        "visible": True,
        "tip": "Retry the active job stage, or retry a saved job when a job id is provided.",
    },
    "revise": {
        "module": "revision",
        "connection": "service",
        "visible": True,
        "tip": "Create a revision request for the active job.",
    },
    "revisions": {
        "module": "revision",
        "connection": "service",
        "visible": True,
        "tip": "List saved revision sandboxes for the active job.",
    },
    "artifact": {
        "module": "artifacts",
        "connection": "service",
        "visible": True,
        "tip": "Preview one artifact path with text or JSON rendering.",
    },
    "build": {
        "module": "codegen/build",
        "connection": "service",
        "visible": True,
        "tip": "Compile generated Geant4 code for the active job.",
    },
    "chat": {
        "module": "copilot",
        "connection": "service",
        "visible": True,
        "tip": "Ask RadAgent Copilot about the current workflow or next action.",
    },
    "confirm": {
        "module": "human_confirmation",
        "connection": "service",
        "visible": True,
        "tip": "Open the active confirmation review before approving or rejecting.",
    },
    "credibility": {
        "module": "gates/credibility",
        "connection": "service",
        "visible": True,
        "tip": "Inspect credibility gate status, confidence, and warnings.",
    },
    "diagnose": {
        "module": "workflow/diagnosis",
        "connection": "service",
        "visible": True,
        "tip": "Use a lite model to explain why the workflow is blocked while hard rules keep permissions deterministic.",
    },
    "exit": {
        "module": "client/navigation",
        "connection": "client",
        "visible": False,
        "tip": "TUI process exit; Web uses Home navigation or browser close.",
    },
    "gates": {
        "module": "gates",
        "connection": "service",
        "visible": True,
        "tip": "Open validation gate results for the active job.",
    },
    "logs": {
        "module": "events",
        "connection": "service",
        "visible": True,
        "tip": "Show recent structured service events.",
    },
    "memory": {
        "module": "workflow_context",
        "connection": "service",
        "visible": True,
        "tip": "Inspect workflow memory and state context for the active job.",
    },
    "model": {
        "module": "model_config",
        "connection": "service",
        "visible": True,
        "tip": "View or update model endpoint and tier settings without exposing secrets.",
    },
    "model-health": {
        "module": "model_config/health",
        "connection": "service",
        "visible": True,
        "tip": "Run a small model API request and report status plus latency.",
    },
    "options": {
        "module": "client/options",
        "connection": "client",
        "visible": False,
        "tip": "TUI language/theme options; Web uses persistent visible controls where needed.",
    },
    "project": {
        "module": "projects",
        "connection": "service",
        "visible": True,
        "tip": "Switch the active RadAgent project by slug or id.",
    },
    "projects": {
        "module": "projects",
        "connection": "service",
        "visible": True,
        "tip": "List available RadAgent projects.",
    },
    "accept-revision": {
        "module": "revision",
        "connection": "service",
        "visible": True,
        "tip": "Accept a validated revision sandbox into the active generated project.",
    },
    "ask-more": {
        "module": "human_confirmation",
        "connection": "service",
        "visible": True,
        "tip": "Pause confirmation and ask for more detail before continuing.",
    },
    "reject-revision": {
        "module": "revision",
        "connection": "service",
        "visible": True,
        "tip": "Reject a saved revision sandbox without applying it.",
    },
    "reject": {
        "module": "human_confirmation",
        "connection": "service",
        "visible": True,
        "tip": "Reject the active confirmation with a reason.",
    },
    "revision": {
        "module": "revision",
        "connection": "service",
        "visible": True,
        "tip": "Open one revision summary by revision id.",
    },
    "simulate": {
        "module": "simulation",
        "connection": "service",
        "visible": True,
        "tip": "Run the built simulator for a chosen event count.",
    },
    "step": {
        "module": "pipeline",
        "connection": "service",
        "visible": True,
        "tip": "Advance one pipeline phase for the active job.",
    },
}

_COMPLETED_STATUSES = {"completed", "complete", "done", "success", "succeeded", "passed"}

_WORKFLOW_CAPABILITIES: tuple[dict[str, str], ...] = (
    {
        "name": "需求捕获 / Intent capture",
        "description": "把一句仿真需求转成结构化目标。",
        "command": "启动工作流",
    },
    {
        "name": "物理模型 / Physics model IR",
        "description": "持续记录几何、源项、计分和假设。",
        "command": "模型记忆",
    },
    {
        "name": "门禁审核 / Gate review",
        "description": "在继续前展示验证门禁和人工确认。",
        "command": "审核门禁",
    },
    {
        "name": "代码生成 / Code generation",
        "description": "由模型生成 Geant4 源码、宏和工程文件。",
        "command": "构建工程",
    },
    {
        "name": "构建模拟 / Build and simulation",
        "description": "编译生成代码并运行可控仿真批次。",
        "command": "运行模拟",
    },
    {
        "name": "产物修订 / Artifacts and revisions",
        "description": "检查报告、源码、修订和最终交付物。",
        "command": "查看产物",
    },
)

_SHOWCASE_EXAMPLES: tuple[dict[str, Any], ...] = (
    {
        "id": "example-hpge-coincidence",
        "title": "HPGe 反符合谱仪",
        "subtitle": "Anti-coincidence HPGe spectrometer",
        "prompt": (
            "Build a Geant4 workflow for an HPGe anti-coincidence gamma spectrometer: "
            "coaxial HPGe crystal, dead layer, BGO veto shield, 662 keV and 1332 keV "
            "gamma sources, energy-deposit scoring in crystal and veto, coincidence "
            "rejection logic, spectrum histogram, and a final report that explains "
            "geometry assumptions and gate criteria."
        ),
        "difficulty": "advanced",
        "tags": ["HPGe", "anti-coincidence", "spectrum"],
        "validation_focus": ["geometry", "coincidence scoring", "report traceability"],
    },
    {
        "id": "example-proton-depth-dose",
        "title": "质子束深度剂量",
        "subtitle": "Layered proton depth-dose benchmark",
        "prompt": (
            "Build a Geant4 proton depth-dose benchmark for a 150 MeV pencil beam "
            "through water, aluminum, and silicon layers. Produce range and Bragg "
            "peak scoring, per-layer energy deposition, step limiter settings, "
            "physics list rationale, CSV output, and validation gates for material "
            "thickness and scoring bin size."
        ),
        "difficulty": "advanced",
        "tags": ["proton", "Bragg peak", "dose"],
        "validation_focus": ["materials", "scoring bins", "physics list"],
    },
    {
        "id": "example-neutron-shielding",
        "title": "中子屏蔽响应",
        "subtitle": "Neutron shielding and activation proxy",
        "prompt": (
            "Build a Geant4 shielding study for 14 MeV neutrons through polyethylene, "
            "borated polyethylene, lead, and a downstream silicon detector. Score "
            "neutron leakage, secondary gamma production proxy, detector dose, "
            "material stack sensitivity, and produce a report with assumptions and "
            "limitations."
        ),
        "difficulty": "expert",
        "tags": ["neutron", "shielding", "secondary gamma"],
        "validation_focus": ["hadronic physics", "material stack", "leakage scoring"],
    },
    {
        "id": "example-muon-tomography",
        "title": "宇宙线缪子断层",
        "subtitle": "Cosmic muon scattering tomography",
        "prompt": (
            "Build a Geant4 cosmic muon scattering tomography workflow with two "
            "tracker planes above and below a dense object. Generate a realistic "
            "angular muon source, score hit positions, scattering angles, and "
            "reconstruction-ready CSV outputs, with gates for tracker spacing and "
            "material placement."
        ),
        "difficulty": "expert",
        "tags": ["muon", "tomography", "tracking"],
        "validation_focus": ["source angular model", "tracker geometry", "CSV outputs"],
    },
)


def to_jsonable(value: Any) -> Any:
    """Convert service models into data that can be passed to JSON encoders."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    return value


def build_command_catalog() -> list[dict[str, Any]]:
    """Return a stable command catalog for the web command palette."""
    descriptions: dict[str, str] = {}
    for suggestion in command_suggestions("", limit=80):
        head, _, description = suggestion.partition(" ")
        name = head.strip().removeprefix("/")
        if name:
            descriptions[name] = " ".join(description.split())

    for name, description in _REQUIRED_COMMANDS.items():
        descriptions.setdefault(name, description)

    rows: list[dict[str, Any]] = []
    for name, audit in _COMMAND_AUDIT.items():
        rows.append(
            {
                "name": name,
                "description": descriptions.get(name, str(audit["tip"])),
                "tip": str(audit["tip"]),
                "module": str(audit["module"]),
                "connection": str(audit["connection"]),
                "visible": bool(audit["visible"]),
            }
        )

    return sorted(rows, key=lambda row: row["name"])


def _as_list(value: Any) -> list[Any]:
    jsonable = to_jsonable(value)
    return jsonable if isinstance(jsonable, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    jsonable = to_jsonable(value)
    return jsonable if isinstance(jsonable, dict) else {}


def _text(value: Any, *, fallback: str = "") -> str:
    text = " ".join(str(value or "").split()).strip()
    return text or fallback


def _unique_texts(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _job_title(job: dict[str, Any]) -> str:
    summary = job.get("task_summary")
    if isinstance(summary, dict):
        for key in ("en", "zh"):
            title = _text(summary.get(key))
            if title:
                return title
    return _text(
        job.get("user_query") or job.get("objective") or job.get("summary"),
        fallback=_text(job.get("job_id"), fallback="RadAgent workflow"),
    )


def _find_by_id(rows: list[Any], key: str, value: str) -> dict[str, Any] | None:
    for row in rows:
        data = _as_dict(row)
        if _text(data.get(key)) == value:
            return data
    return None


def build_home_summary(service: Any) -> dict[str, Any]:
    """Summarize persisted workflow data for the public home screen."""
    projects = _as_list(service.list_projects())
    jobs = [_as_dict(job) for job in _as_list(service.list_jobs(include_all_projects=True))]

    artifacts_by_job: dict[str, list[dict[str, Any]]] = {}
    artifact_total = 0
    for job in jobs:
        job_id = _text(job.get("job_id"))
        if not job_id:
            continue
        try:
            artifacts = [_as_dict(item) for item in _as_list(service.list_artifacts(job_id))]
        except Exception:
            artifacts = []
        artifacts_by_job[job_id] = artifacts
        artifact_total += len(artifacts)

    completed_jobs = [
        job for job in jobs if _text(job.get("status")).lower() in _COMPLETED_STATUSES
    ]
    visible_jobs = completed_jobs or jobs

    project_cards: list[dict[str, Any]] = []
    for job in visible_jobs[:6]:
        job_id = _text(job.get("job_id"))
        artifacts = artifacts_by_job.get(job_id, [])
        project_cards.append(
            {
                "job_id": job_id,
                "title": _job_title(job),
                "project_name": _text(
                    job.get("project_name") or job.get("project_slug"),
                    fallback="RadAgent Project",
                ),
                "status": _text(job.get("status"), fallback="unknown"),
                "phase": _text(job.get("current_phase") or job.get("phase")),
                "updated_at": _text(
                    job.get("updated_at") or job.get("completed_at") or job.get("created_at")
                ),
                "artifact_count": len(artifacts),
                "artifact_kinds": _unique_texts(
                    [artifact.get("kind") or artifact.get("stage") for artifact in artifacts]
                ),
            }
        )

    return {
        "metrics": {
            "projects": len(projects),
            "jobs": len(jobs),
            "completed_jobs": len(completed_jobs),
            "active_jobs": len(jobs) - len(completed_jobs),
            "artifacts": artifact_total,
        },
        "workflow_capabilities": [dict(row) for row in _WORKFLOW_CAPABILITIES],
        "projects": [],
        "showcase_examples": [dict(row) for row in _SHOWCASE_EXAMPLES],
    }


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _should_continue_after_approval(value: Any) -> bool:
    status = _as_dict(value)
    if str(status.get("status") or "").lower() == "failed":
        return False
    state = _as_dict(status.get("state"))
    if state.get("termination_reason"):
        return False
    try:
        current_idx = int(status.get("current_phase_idx", 0))
    except (TypeError, ValueError):
        return True
    return current_idx <= PIPELINE_PHASES.index("g4_codegen")


def _has_pending_repair_continuation(service: Any) -> bool:
    checker = getattr(service, "_is_repair_continuation_pending", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            pass
    state = _as_dict(getattr(service, "state", {}))
    if state:
        request = _as_dict(state.get("repair_continuation_request"))
        return (
            request.get("status") == "pending"
            and state.get("repair_continuation_status") not in {"approved", "rejected"}
        )
    return False


def _approval_continue_reason(value: Any) -> str:
    status = _as_dict(value)
    state = _as_dict(status.get("state"))
    if state.get("repair_continuation_status") == "approved":
        return "repair_continuation_approved"
    return "human_confirmation_approved"


def _active_job_id(service: Any) -> str:
    state = _as_dict(getattr(service, "state", {}))
    job_id = _text(state.get("job_id"))
    if job_id:
        return job_id
    try:
        status = _as_dict(service.get_status())
    except Exception:
        return ""
    return _text(status.get("job_id"))


def _command_job_id_or_active(service: Any, args: str) -> str:
    return _text(args) or _active_job_id(service)


async def dispatch_web_command(service: Any, text: str) -> dict[str, Any]:
    """Dispatch one web composer command through the UI-neutral app service."""
    try:
        command = parse_command(text)
    except CommandParseError as exc:
        return {"ok": False, "error": str(exc), "view": "composer"}

    try:
        match command.name:
            case "chat":
                data = await _maybe_await(service.chat(command.args))
                view = "timeline"
            case "run":
                data = await _maybe_await(
                    service.start_job(
                        command.args,
                        run_mode=getattr(service, "execution_mode", "strict"),
                        auto_continue=True,
                        briefing_context=None,
                    )
                )
                view = "status"
            case "status":
                data = service.get_status()
                view = "status"
            case "jobs":
                data = service.list_jobs(include_all_projects=True)
                view = "jobs"
            case "job":
                data = service.get_job(command.args)
                if data is None:
                    return {
                        "ok": False,
                        "command": command.name,
                        "error": f"Job not found: {command.args}",
                        "view": "jobs",
                    }
                view = "job"
            case "artifacts":
                data = service.list_artifacts(None)
                view = "artifacts"
            case "artifact":
                data = service.read_artifact(command.args)
                view = "artifact"
            case "check" | "inspect":
                data = service.get_startup_status()
                view = "tools"
            case "gates":
                data = service.get_gate_results(None)
                view = "gates"
            case "approve":
                response = {"user_decision": "approve", "feedback": "approve"}
                if _has_pending_repair_continuation(service):
                    data = await _maybe_await(
                        service.submit_repair_continuation(response, auto_continue=False)
                    )
                else:
                    data = await _maybe_await(
                        service.submit_confirmation(response, auto_continue=False)
                    )
                if _should_continue_after_approval(data):
                    service.continue_in_background(reason=_approval_continue_reason(data))
                view = "status"
            case "confirm":
                if command.args.strip().lower() in {"approve", "approved", "yes", "y", "确认", "同意"}:
                    response = {"user_decision": "approve", "feedback": command.args}
                    if _has_pending_repair_continuation(service):
                        data = await _maybe_await(
                            service.submit_repair_continuation(response, auto_continue=False)
                        )
                    else:
                        data = await _maybe_await(
                            service.submit_confirmation(response, auto_continue=False)
                        )
                    if _should_continue_after_approval(data):
                        service.continue_in_background(reason=_approval_continue_reason(data))
                    view = "status"
                else:
                    data = service.get_confirmation_review(_text(command.args) or None)
                    view = "confirmation"
            case "reject":
                response = {"user_decision": "reject", "feedback": command.args}
                if _has_pending_repair_continuation(service):
                    data = await _maybe_await(
                        service.submit_repair_continuation(response, auto_continue=False)
                    )
                else:
                    data = await _maybe_await(
                        service.submit_confirmation(response, auto_continue=False)
                    )
                view = "status"
            case "ask-more":
                data = await _maybe_await(
                    service.submit_confirmation(
                        {"user_decision": "ask_more", "feedback": command.args},
                        auto_continue=False,
                    )
                )
                view = "status"
            case "credibility":
                data = service.get_credibility_report(None)
                view = "credibility"
            case "diagnose":
                data = await _maybe_await(service.get_workflow_diagnosis(None))
                view = "diagnosis"
            case "logs":
                data = service.recent_events(80)
                view = "logs"
            case "memory":
                data = service.get_workflow_context(None)
                view = "memory"
            case "model":
                data = service.get_model_config()
                view = "model"
            case "model-health":
                data = await _maybe_await(service.test_model_health())
                view = "model-health"
            case "project":
                data = service.set_current_project(command.args)
                view = "projects"
            case "projects":
                data = service.list_projects()
                view = "projects"
            case "revise":
                data = await _maybe_await(service.create_revision(command.args, job_id=None))
                view = "revision"
            case "revisions":
                data = service.list_revisions(None)
                view = "revisions"
            case "revision":
                revisions = service.list_revisions(None)
                data = _find_by_id(revisions, "revision_id", command.args)
                if data is None:
                    return {
                        "ok": False,
                        "command": command.name,
                        "error": f"Revision not found: {command.args}",
                        "view": "revisions",
                    }
                view = "revision"
            case "accept-revision":
                data = await _maybe_await(service.accept_revision(command.args))
                view = "status"
            case "reject-revision":
                data = service.reject_revision(command.args)
                view = "revision"
            case "help":
                data = build_command_catalog()
                view = "help"
            case "open":
                artifacts = service.list_artifacts(None)
                data = {"target": command.args, "artifacts": to_jsonable(artifacts)}
                view = "artifacts"
            case "report":
                artifacts = _as_list(service.list_artifacts(None))
                report_artifacts = [
                    artifact
                    for artifact in artifacts
                    if "report"
                    in " ".join(
                        [
                            _text(_as_dict(artifact).get("kind")),
                            _text(_as_dict(artifact).get("stage")),
                            _text(_as_dict(artifact).get("path")),
                        ]
                    ).lower()
                ]
                data = {"target": "report", "artifacts": report_artifacts or artifacts}
                view = "report"
            case "history":
                data = {
                    "message": "Command history is kept in the browser timeline.",
                    "commands": build_command_catalog(),
                }
                view = "history"
            case "mode":
                data = {"mode": command.args}
                view = "mode"
            case "demo":
                data = {
                    "demo": command.args,
                    "command": f"/run demo:{command.args}",
                    "message": "Run the generated command to start the demo workflow.",
                }
                view = "demo"
            case "exit":
                data = {"message": "Use the Home button or close the browser tab to leave the workbench."}
                view = "exit"
            case "resume":
                job_id = _command_job_id_or_active(service, command.args)
                if not job_id:
                    return {
                        "ok": False,
                        "command": command.name,
                        "error": "No active job to resume.",
                        "view": "jobs",
                    }
                data = service.resume_job(job_id)
                view = "status"
            case "retry":
                job_id = _command_job_id_or_active(service, command.args)
                if not job_id:
                    return {
                        "ok": False,
                        "command": command.name,
                        "error": "No active job to retry.",
                        "view": "jobs",
                    }
                data = service.resume_job(job_id, clear_failure=True)
                service.continue_in_background(reason="retry")
                view = "status"
            case "build":
                try:
                    data = await _maybe_await(service.build_generated_code())
                except Exception as exc:
                    data = {
                        "success": False,
                        "configure": {},
                        "build": {},
                        "executable_path": "",
                        "errors": str(exc),
                    }
                view = "build"
            case "simulate":
                events = int(command.args) if command.args else 1000
                try:
                    data = await _maybe_await(service.run_simulation(events=events))
                except Exception as exc:
                    data = {
                        "success": False,
                        "output_dir": "",
                        "log": "",
                        "errors": str(exc),
                    }
                view = "simulation"
            case "step":
                data = await _maybe_await(service.step())
                view = "status"
            case _ if command.name in PANEL_COMMANDS:
                data = {"panel": PANEL_COMMANDS[command.name], "args": command.args}
                view = PANEL_COMMANDS[command.name]
            case _:
                return {
                    "ok": False,
                    "command": command.name,
                    "error": f"Command /{command.name} is not wired in the web adapter yet.",
                    "view": "composer",
                }
    except Exception as exc:
        return {
            "ok": False,
            "command": command.name,
            "error": str(exc),
            "view": "timeline",
        }

    return {
        "ok": True,
        "command": command.name,
        "args": command.args,
        "view": view,
        "data": to_jsonable(data),
    }
