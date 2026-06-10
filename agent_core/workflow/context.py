from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.app.schemas import JobStatus, RadAgentEvent
from agent_core.workflow.schemas import EvidenceSummary, MemoryItem, WorkflowContext
from agent_core.workspace.paths import (
    HC_REPORT,
    STAGE_GATE_VALIDATION,
    STAGE_HUMAN_CONFIRMATION,
)


def build_workflow_context(
    *,
    status: JobStatus,
    state: dict[str, Any],
    recent_events: list[RadAgentEvent],
    artifacts: list[Any],
    gate_results: list[dict[str, Any]],
    workspace_root: Path,
) -> WorkflowContext:
    """Build a compact, frontend-safe context for the workflow copilot."""

    job_id = status.job_id
    return WorkflowContext(
        job_id=job_id,
        run_id=str(state.get("run_id", "")),
        user_query=status.user_query,
        status=status.status,
        current_phase=status.current_phase,
        current_phase_idx=status.current_phase_idx,
        completed_phases=list(status.completed_phases),
        needs_confirmation=status.needs_confirmation,
        key_statuses=dict(status.key_statuses),
        recent_events=[_event_summary(event) for event in recent_events[-20:]],
        artifacts=[_artifact_summary(item) for item in artifacts[:50]],
        gate_results=[_gate_summary(gate) for gate in gate_results[:40]],
        confirmation=_confirmation_summary(state),
        evidence=_evidence_summary(job_id=job_id, state=state, workspace_root=workspace_root),
        memory=_memory_items(status=status, state=state, gate_results=gate_results),
    )


def _event_summary(event: RadAgentEvent) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "status": event.status,
        "phase": event.phase,
        "summary": event.summary,
        "created_at": event.created_at.isoformat(),
    }


def _artifact_summary(item: Any) -> dict[str, Any]:
    data = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
    return {
        "path": data.get("path", ""),
        "stage": data.get("stage", ""),
        "kind": data.get("kind", ""),
        "size_bytes": data.get("size_bytes", 0),
    }


def _gate_summary(gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "gate_id": gate.get("gate_id"),
        "name": gate.get("name", gate.get("gate", "")),
        "status": gate.get("status", "unknown"),
        "message": str(gate.get("message", ""))[:240],
        "failed_items": gate.get("failed_items", [])[:5],
        "warnings": gate.get("warnings", [])[:5],
    }


def _confirmation_summary(state: dict[str, Any]) -> dict[str, Any]:
    report_path = str(state.get("confirmation_report_path", ""))
    record_path = str(state.get("confirmation_record_path", ""))
    plan_path = str(state.get("confirmed_model_plan_path", ""))
    if not report_path and state.get("job_workspace"):
        candidate = Path(str(state["job_workspace"])) / STAGE_HUMAN_CONFIRMATION / HC_REPORT
        if candidate.is_file():
            report_path = str(candidate)
    return {
        "status": state.get("confirmation_status", ""),
        "required": bool(state.get("human_confirmation_required")),
        "unconfirmed_assumptions_count": state.get("unconfirmed_assumptions_count", 0),
        "report_path": report_path,
        "record_path": record_path,
        "confirmed_model_plan_path": plan_path,
    }


def _evidence_summary(
    *,
    job_id: str,
    state: dict[str, Any],
    workspace_root: Path,
) -> EvidenceSummary:
    gate20 = _credibility_gate(state)
    credibility_report_path = str(gate20.get("report_path", ""))
    if not credibility_report_path and job_id:
        candidate = (
            workspace_root
            / "jobs"
            / job_id
            / STAGE_GATE_VALIDATION
            / "credibility_assessment.json"
        )
        if candidate.is_file():
            credibility_report_path = str(candidate)

    evidence_items: list[dict[str, Any]] = []
    evidence_path = str(state.get("evidence_map_path", ""))
    if evidence_path and Path(evidence_path).is_file():
        try:
            data = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
            evidence_items = _compact_evidence_items(data)
        except (OSError, json.JSONDecodeError):
            evidence_items = []

    return EvidenceSummary(
        evidence_map_path=evidence_path,
        credibility_report_path=credibility_report_path,
        credibility_level=str(gate20.get("credibility_level", "")),
        gate_status=str(gate20.get("status", "")),
        evidence_items=evidence_items[:12],
        warnings=[str(item) for item in gate20.get("warnings", [])[:6]],
    )


def _credibility_gate(state: dict[str, Any]) -> dict[str, Any]:
    path = str(state.get("gate_results_path", ""))
    if path and Path(path).is_file():
        try:
            gates = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            gates = []
        if isinstance(gates, list):
            for gate in gates:
                if isinstance(gate, dict) and gate.get("gate_id") == 20:
                    return gate
    return {}


def _compact_evidence_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source in data.get("rag_sources", []):
        for item in source.get("items", [])[:6]:
            items.append(
                {
                    "type": "rag",
                    "title": item.get("title", item.get("doc_id", "")),
                    "source": item.get("source", source.get("source", "")),
                    "score": item.get("score"),
                }
            )
    for source in data.get("web_sources", []):
        for item in source.get("items", [])[:6]:
            items.append(
                {
                    "type": "web",
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "confidence": item.get("confidence"),
                }
            )
    return items


def _memory_items(
    *,
    status: JobStatus,
    state: dict[str, Any],
    gate_results: list[dict[str, Any]],
) -> list[MemoryItem]:
    items = [
        MemoryItem(
            source="run",
            key="current_status",
            summary=(
                f"status={status.status}, phase={status.current_phase or 'idle'}, "
                f"job={status.job_id or 'none'}"
            ),
        )
    ]
    if status.needs_confirmation:
        items.append(
            MemoryItem(
                source="run",
                key="confirmation_pending",
                summary=(
                    "Human confirmation is required before formal code generation can proceed."
                ),
                payload=_confirmation_summary(state),
            )
        )
    failed_gates = [gate for gate in gate_results if gate.get("status") in {"fail", "block"}]
    if failed_gates:
        items.append(
            MemoryItem(
                source="run",
                key="failed_gates",
                summary=f"{len(failed_gates)} gate(s) currently fail.",
                payload={"gates": [_gate_summary(gate) for gate in failed_gates[:8]]},
            )
        )
    return items
