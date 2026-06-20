from __future__ import annotations

import asyncio
import json
import os
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agent_core.app import PIPELINE_PHASES, RadAgentAppService
from agent_core.models.schemas import ModelCallResult, ModelProvider, ModelTask, ModelTier
from agent_core.workspace.paths import (
    STAGE_CONTEXT,
    STAGE_GATE_VALIDATION,
    STAGE_HUMAN_CONFIRMATION,
    STAGE_INPUT,
    STAGE_TASK_PLAN,
)
from pydantic import ValidationError


def test_service_exposes_pipeline_contract(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)

    assert PIPELINE_PHASES[0] == "prepare_workspace"
    assert PIPELINE_PHASES[3] == "requirements_review"
    assert "human_confirmation" not in PIPELINE_PHASES
    assert len(PIPELINE_PHASES) == 10
    status = service.get_status()
    assert status.status == "idle"
    assert status.workspace_root == str(tmp_path)


@pytest.mark.asyncio
async def test_prepare_workspace_phase_persists_job_and_events(tmp_path, monkeypatch) -> None:
    async def fake_build_job_id(base_id: str, user_query: str) -> str:
        assert base_id == ""
        assert user_query == "build detector"
        return "job_frontend_test"

    monkeypatch.setattr("agent_core.naming.build_job_id", fake_build_job_id)
    events = []
    service = RadAgentAppService(workspace_root=tmp_path, event_callback=events.append)
    service.state = {
        "user_query": "build detector",
        "job_id": "",
        "run_mode": "strict",
        "execution_mode": "strict",
        "errors": [],
    }

    result = await service.run_phase("prepare_workspace")

    assert result.success is True
    assert result.status.job_id == "job_frontend_test"
    assert result.status.current_phase == "context"
    assert (tmp_path / "jobs" / "job_frontend_test" / STAGE_INPUT / "user_query.md").is_file()
    assert service.store.get_job("job_frontend_test") is not None
    assert [event.event_type for event in events] == ["phase_started", "phase_finished"]


def test_read_artifact_supports_text_json_binary_and_missing(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    text_path = tmp_path / "report.md"
    json_path = tmp_path / "data.json"
    binary_path = tmp_path / "image.bin"
    text_path.write_text("hello", encoding="utf-8")
    json_path.write_text('{"ok": true}', encoding="utf-8")
    binary_path.write_bytes(b"\x00\x01")

    text = service.read_artifact(str(text_path))
    data = service.read_artifact(str(json_path))
    binary = service.read_artifact(str(binary_path))
    missing = service.read_artifact(str(tmp_path / "missing.txt"))

    assert text.kind == "text"
    assert text.text == "hello"
    assert data.kind == "json"
    assert data.json_data == {"ok": True}
    assert binary.kind == "binary"
    assert missing.exists is False


def test_read_artifact_resolves_job_relative_model_call_paths(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    service.state = {"job_id": "job_model_debug"}
    transcript = tmp_path / "jobs" / "job_model_debug" / "logs" / "model_calls" / "call.json"
    transcript.parent.mkdir(parents=True)
    transcript.write_text('{"status": "running"}', encoding="utf-8")

    content = service.read_artifact("logs/model_calls/call.json")

    assert content.exists is True
    assert content.kind == "json"
    assert content.json_data == {"status": "running"}


def test_recent_events_includes_model_gateway_job_log_events(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    service.state = {"job_id": "job_model_events"}
    events_path = tmp_path / "jobs" / "job_model_events" / "logs" / "events.jsonl"
    events_path.parent.mkdir(parents=True)
    events_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-06-14T08:00:00+00:00",
                "job_id": "job_model_events",
                "event_type": "model_call_start",
                "status": "running",
                "phase": "codegen",
                "summary": "codegen via openai_compatible",
                "artifacts": [{"path": "logs/model_calls/call.json"}],
                "metrics": {"system_prompt_chars": 5},
                "details": {"model_name": "mimo-v2.5-pro"},
            },
        )
        + "\n",
        encoding="utf-8",
    )

    events = service.recent_events()

    assert any(event.event_type == "model_call_start" for event in events)
    model_event = next(event for event in events if event.event_type == "model_call_start")
    assert model_event.payload["artifacts"] == [{"path": "logs/model_calls/call.json"}]
    assert model_event.payload["details"]["model_name"] == "mimo-v2.5-pro"


def test_recent_events_includes_active_model_call_while_background_worker_is_running(
    tmp_path,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    service.state = {"job_id": "job_active_model_call"}
    active_path = tmp_path / "jobs" / "job_active_model_call" / "logs" / "active_model_call.json"
    active_path.parent.mkdir(parents=True)
    active_path.write_text(
        json.dumps(
            {
                "model_call_id": "call-active",
                "status": "running",
                "task": "codegen",
                "module_name": "simulation_core",
                "transcript_path": "logs/model_calls/call-active_codegen.json",
            }
        ),
        encoding="utf-8",
    )

    release = threading.Event()
    worker = threading.Thread(target=lambda: release.wait(timeout=5))
    worker.start()
    service._background_continue_thread = worker
    try:
        events = service.recent_events(limit=1)
    finally:
        release.set()
        worker.join(timeout=5)

    assert len(events) == 1
    event = events[0]
    assert event.event_type == "model_call_start"
    assert event.status == "running"
    assert event.phase == "codegen"
    assert event.payload["artifacts"] == [
        {"path": "logs/model_calls/call-active_codegen.json"}
    ]
    assert event.payload["details"]["metadata"] == {
        "model_call_id": "call-active",
        "module_name": "simulation_core",
    }


@pytest.mark.asyncio
async def test_requirements_review_uses_lite_model_and_blocks_for_confirmation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_requirements_review"
    task_dir = tmp_path / "jobs" / job_id / STAGE_TASK_PLAN
    task_dir.mkdir(parents=True)
    task_spec_path = task_dir / "task_spec.json"
    task_spec_path.write_text(
        json.dumps(
            {
                "particle": {"type": "proton", "energy_MeV": 150},
                "target": {"material": "Water"},
            }
        ),
        encoding="utf-8",
    )
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "Build a 150 MeV proton depth-dose benchmark.",
        "task_spec_path": str(task_spec_path),
        "simulation_scope": ["geant4"],
        "task_planning_status": "passed",
        "job_workspace": str(tmp_path / "jobs" / job_id),
        "workspace_root": str(tmp_path),
        "execution_mode": "test",
        "run_mode": "test",
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")
    calls: list[dict[str, object]] = []

    class FakeGateway:
        async def call(self, **kwargs):
            calls.append(kwargs)
            return ModelCallResult(
                task=ModelTask.MODEL_READINESS,
                tier=ModelTier.LITE,
                provider=ModelProvider.MOCK,
                model_name="lite-review",
                content="{}",
                parsed_json={
                    "summary_for_user": "请确认质子束、水箱尺寸和 scoring。",
                    "missing_information": ["Water phantom dimensions are not specified."],
                    "ambiguous_parameters": [
                        {
                            "field_path": "target.size",
                            "proposed_value": "30 cm x 30 cm x 30 cm",
                            "reason": "User asked for depth-dose but did not give phantom size.",
                        }
                    ],
                    "physics_risks": ["Physics cuts are unspecified."],
                    "questions": [
                        {
                            "field_path": "scoring.depth_dose",
                            "question": "Confirm depth-dose bin width.",
                            "proposed_value": "1 mm",
                        }
                    ],
                    "proposed_parameters": [
                        {
                            "field_path": "source.particle",
                            "proposed_value": "proton",
                            "source_type": "user",
                            "confidence": 0.99,
                        }
                    ],
                },
            )

    monkeypatch.setattr("agent_core.models.gateway.get_model_gateway", lambda: FakeGateway())

    result = await service.run_phase("requirements_review")

    assert result.success is True
    assert result.status.status == "paused"
    assert result.status.needs_confirmation is True
    assert service.state["requirements_review_status"] == "needs_user_input"
    assert service.state["confirmation_status"] == "pending"
    assert service.state["human_confirmation_required"] is True
    assert calls[0]["tier"] == ModelTier.LITE
    assert "所有面向用户显示的文字必须使用简体中文" in str(calls[0]["system_prompt"])
    request_path = Path(service.state["requirements_review_request_path"])
    assert request_path.is_file()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["schema_version"] == "requirements_review_v1"
    assert request["missing_information"] == ["Water phantom dimensions are not specified."]
    assert request["ambiguous_fields"][0]["field_path"] == "target.size"


@pytest.mark.asyncio
async def test_requirements_review_repairs_invalid_json_with_lite_model(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_requirements_review_repair"
    task_dir = tmp_path / "jobs" / job_id / STAGE_TASK_PLAN
    task_dir.mkdir(parents=True)
    task_spec_path = task_dir / "task_spec.json"
    task_spec_path.write_text(
        json.dumps(
            {
                "particle": {"type": "neutron", "energy_MeV": 14},
                "materials": ["polyethylene", "borated polyethylene", "lead", "silicon"],
            }
        ),
        encoding="utf-8",
    )
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "Build a 14 MeV neutron shielding stack study.",
        "task_spec_path": str(task_spec_path),
        "simulation_scope": ["geant4"],
        "task_planning_status": "passed",
        "job_workspace": str(tmp_path / "jobs" / job_id),
        "workspace_root": str(tmp_path),
        "execution_mode": "test",
        "run_mode": "test",
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")
    calls: list[dict[str, object]] = []

    class FakeGateway:
        async def call(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return ModelCallResult(
                    task=ModelTask.MODEL_READINESS,
                    tier=ModelTier.LITE,
                    provider=ModelProvider.MOCK,
                    model_name="lite-review",
                    content=(
                        "```json\n"
                        "{\n"
                        '  "summary_for_user": "请确认屏蔽体参数。",\n'
                        '  "missing_information": ["硅探测器尺寸未指定"],\n'
                        '  "ambiguous_parameters": [\n'
                        '    {"field_path": "geometry.stack", "proposed_value": "PE->BPE->Pb->Si", '
                        '"reason": “层厚未确认”}\n'
                        "  ]\n"
                        "}\n"
                        "```"
                    ),
                    parsed_json=None,
                )
            return ModelCallResult(
                task=ModelTask.MODEL_READINESS,
                tier=ModelTier.LITE,
                provider=ModelProvider.MOCK,
                model_name="lite-review",
                content="{}",
                parsed_json={
                    "summary_for_user": "请确认屏蔽体参数。",
                    "missing_information": ["硅探测器尺寸未指定"],
                    "ambiguous_parameters": [
                        {
                            "field_path": "geometry.stack",
                            "proposed_value": "PE->BPE->Pb->Si",
                            "reason": "层厚未确认",
                        }
                    ],
                    "questions": [],
                    "physics_risks": [],
                    "proposed_parameters": [],
                    "proposed_defaults": [],
                },
            )

    monkeypatch.setattr("agent_core.models.gateway.get_model_gateway", lambda: FakeGateway())

    result = await service.run_phase("requirements_review")

    assert result.success is True
    assert len(calls) == 2
    assert calls[0]["tier"] == ModelTier.LITE
    assert calls[1]["tier"] == ModelTier.LITE
    assert "JSON parse failed" in str(calls[1]["user_prompt"])
    assert "Return only the repaired JSON object" in str(calls[1]["system_prompt"])
    request_path = Path(service.state["requirements_review_request_path"])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["summary_for_user"] == "请确认屏蔽体参数。"
    assert request["missing_information"] == ["硅探测器尺寸未指定"]
    assert request["ambiguous_parameters"][0]["reason"] == "层厚未确认"
    assert request["model_error"] == ""
    assert "JSON parse failed" in request["json_repair"]["initial_error"]
    assert request["json_repair"]["repaired"] is True


@pytest.mark.asyncio
async def test_requirements_review_extracts_cards_when_json_repair_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_requirements_review_malformed_cards"
    task_dir = tmp_path / "jobs" / job_id / STAGE_TASK_PLAN
    task_dir.mkdir(parents=True)
    task_spec_path = task_dir / "task_spec.json"
    task_spec_path.write_text(
        json.dumps(
            {
                "particle": {
                    "type": "neutron",
                    "pdg_code": 2112,
                    "energy_MeV": 14.0,
                    "energy_unit": "MeV",
                },
                "materials": ["polyethylene", "borated polyethylene", "lead", "silicon"],
            }
        ),
        encoding="utf-8",
    )
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "Build a 14 MeV neutron shielding stack study.",
        "task_spec_path": str(task_spec_path),
        "simulation_scope": ["geant4"],
        "task_planning_status": "passed",
        "job_workspace": str(tmp_path / "jobs" / job_id),
        "workspace_root": str(tmp_path),
        "execution_mode": "test",
        "run_mode": "test",
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")
    calls: list[dict[str, object]] = []

    class FakeGateway:
        async def call(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return ModelCallResult(
                    task=ModelTask.MODEL_READINESS,
                    tier=ModelTier.LITE,
                    provider=ModelProvider.MOCK,
                    model_name="lite-review",
                    content=(
                        "{\n"
                        '  "status": "needs_user_input",\n'
                        '  "summary_for_user": "请确认仿真目标、关键参数和继续执行条件。",\n'
                        '  "missing_information": [\n'
                        '    "各屏蔽层的厚度（聚乙烯、含硼聚乙烯、铅各多厚？）",\n'
                        '    ""材料堆叠灵敏度"具体指什么？"\n'
                        "  ],\n"
                        '  "questions": [\n'
                        "    {\n"
                        '      "field_path": "shielding.layer_thicknesses",\n'
                        '      "question": "各屏蔽层的厚度分别是多少？",\n'
                        '      "recommended_value": "聚乙烯 5 cm，含硼聚乙烯 5 cm，铅 2 cm，硅探测器 3 mm",\n'
                        '      "reason": "这些是屏蔽研究中常用的典型厚度。"\n'
                        "    },\n"
                        "    {\n"
                        '      "field_path": "shielding.stack_order",\n'
                        '      "question": "屏蔽层从源到硅探测器的排列顺序是什么？",\n'
                        '      "recommended_value": "源 -> 聚乙烯 -> 含硼聚乙烯 -> 铅 -> 硅探测器",\n'
                    ),
                    parsed_json=None,
                )
            return ModelCallResult(
                task=ModelTask.MODEL_READINESS,
                tier=ModelTier.LITE,
                provider=ModelProvider.MOCK,
                model_name="lite-review",
                content="",
                parsed_json=None,
            )

    monkeypatch.setattr("agent_core.models.gateway.get_model_gateway", lambda: FakeGateway())

    result = await service.run_phase("requirements_review")

    assert result.success is True
    assert result.status.needs_confirmation is True
    assert service.state["requirements_review_status"] == "needs_user_input"
    assert len(calls) == 2
    request_path = Path(service.state["requirements_review_request_path"])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["missing_information"]
    assert request["questions"]
    assert request["questions"][0]["field_path"] == "shielding.layer_thicknesses"
    assert request["questions"][0]["recommended_value"]
    assert request["json_repair"]["attempted"] is True
    assert request["json_repair"]["repaired"] is False
    assert request["json_repair"]["fallback_extracted"] is True


@pytest.mark.asyncio
async def test_requirements_review_uses_question_tool_when_json_and_repair_are_unusable(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_requirements_review_question_tool"
    task_dir = tmp_path / "jobs" / job_id / STAGE_TASK_PLAN
    task_dir.mkdir(parents=True)
    task_spec_path = task_dir / "task_spec.json"
    task_spec_path.write_text(
        json.dumps(
            {
                "simulation_scope": ["geant4"],
                "modeling_mode": "realistic",
                "requirements_review_hints": {
                    "questions": [
                        {
                            "field_path": "source.particle",
                            "question": "请确认辐照粒子类型。",
                            "recommended_value": "gamma",
                            "reason": "MOSFET 辐照基准可先用 gamma 做氧化层剂量基准。",
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "做一个mosfet的g4辐照仿真",
        "task_spec_path": str(task_spec_path),
        "simulation_scope": ["geant4"],
        "task_planning_status": "needs_user_input",
        "job_workspace": str(tmp_path / "jobs" / job_id),
        "workspace_root": str(tmp_path),
        "execution_mode": "test",
        "run_mode": "test",
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")
    calls: list[dict[str, object]] = []

    class FakeGateway:
        async def call(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return ModelCallResult(
                    task=ModelTask.MODEL_READINESS,
                    tier=ModelTier.LITE,
                    provider=ModelProvider.MOCK,
                    model_name="lite-review",
                    content="模型输出被截断，无法解析。",
                    parsed_json=None,
                )
            if len(calls) == 2:
                return ModelCallResult(
                    task=ModelTask.MODEL_READINESS,
                    tier=ModelTier.LITE,
                    provider=ModelProvider.MOCK,
                    model_name="lite-review",
                    content="not json",
                    parsed_json=None,
                )
            return ModelCallResult(
                task=ModelTask.MODEL_READINESS,
                tier=ModelTier.LITE,
                provider=ModelProvider.MOCK,
                model_name="lite-review",
                content="{}",
                parsed_json={
                    "status": "needs_user_input",
                    "summary_for_user": "请先确认 MOSFET Geant4 辐照建模参数。",
                    "missing_information": ["辐照源、器件几何和敏感体积未明确"],
                    "cards": [
                        {
                            "field_path": "source.particle",
                            "question": "请确认辐照粒子类型。",
                            "recommended_value": "gamma",
                            "note": "用于先建立可运行的 MOSFET 氧化层剂量基准。",
                        },
                        {
                            "field_path": "geometry.sensitive_volume",
                            "question": "请确认敏感体积。",
                            "recommended_value": "栅氧化层",
                            "note": "Geant4 阶段只计算敏感体积内能量沉积和剂量。",
                        },
                    ],
                },
            )

    monkeypatch.setattr("agent_core.models.gateway.get_model_gateway", lambda: FakeGateway())

    result = await service.run_phase("requirements_review")

    assert result.success is True
    assert len(calls) == 3
    assert calls[2]["metadata"]["module_name"] == "requirements_review_question_tool"
    assert "问题" in str(calls[2]["system_prompt"])
    assert "推荐" in str(calls[2]["system_prompt"])
    assert "备注" in str(calls[2]["system_prompt"])
    request_path = Path(service.state["requirements_review_request_path"])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    question_text = json.dumps(request["questions"], ensure_ascii=False)
    assert "MAX 输出格式异常" not in question_text
    assert request["summary_for_user"] == "请先确认 MOSFET Geant4 辐照建模参数。"
    assert request["questions"][0] == {
        "field_path": "source.particle",
        "question": "请确认辐照粒子类型。",
        "recommended_value": "gamma",
        "reason": "用于先建立可运行的 MOSFET 氧化层剂量基准。",
        "proposed_value": "gamma",
    }
    assert request["json_repair"]["question_tool_attempted"] is True
    assert request["json_repair"]["question_tool_used"] is True


@pytest.mark.asyncio
async def test_requirements_review_filters_runtime_event_count_questions(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_requirements_review_filter_events"
    task_dir = tmp_path / "jobs" / job_id / STAGE_TASK_PLAN
    task_dir.mkdir(parents=True)
    task_spec_path = task_dir / "task_spec.json"
    task_spec_path.write_text(
        json.dumps({"simulation_scope": ["geant4"], "modeling_mode": "realistic"}),
        encoding="utf-8",
    )
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "做一个mosfet的g4辐照仿真",
        "task_spec_path": str(task_spec_path),
        "simulation_scope": ["geant4"],
        "task_planning_status": "passed",
        "job_workspace": str(tmp_path / "jobs" / job_id),
        "workspace_root": str(tmp_path),
        "execution_mode": "test",
        "run_mode": "test",
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")

    class FakeGateway:
        async def call(self, **kwargs):
            return ModelCallResult(
                task=ModelTask.MODEL_READINESS,
                tier=ModelTier.LITE,
                provider=ModelProvider.MOCK,
                model_name="lite-review",
                content="{}",
                parsed_json={
                    "status": "needs_user_input",
                    "summary_for_user": "请确认 Geant4 建模参数。",
                    "missing_information": ["源项和敏感体积未明确"],
                    "questions": [
                        {
                            "field_path": "run.events",
                            "question": "您希望模拟多少个粒子事件？",
                            "recommended_value": "100000",
                            "reason": "事件数越多，统计精度越高。",
                        },
                        {
                            "field_path": "source.particle",
                            "question": "请确认辐照粒子类型。",
                            "recommended_value": "gamma",
                            "reason": "这是 Geant4 源项定义所需参数。",
                        },
                    ],
                },
            )

    monkeypatch.setattr("agent_core.models.gateway.get_model_gateway", lambda: FakeGateway())

    result = await service.run_phase("requirements_review")

    assert result.success is True
    request_path = Path(service.state["requirements_review_request_path"])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    question_blob = json.dumps(request["questions"], ensure_ascii=False)
    assert "run.events" not in question_blob
    assert "粒子事件" not in question_blob
    assert "100000" not in question_blob
    assert request["questions"] == [
        {
            "field_path": "source.particle",
            "question": "请确认辐照粒子类型。",
            "recommended_value": "gamma",
            "reason": "这是 Geant4 源项定义所需参数。",
            "proposed_value": "gamma",
        }
    ]


def test_requirements_review_default_questions_do_not_ask_runtime_events() -> None:
    from agent_core.requirements_review import _fallback_review_from_malformed_content

    review = _fallback_review_from_malformed_content(
        '{"missing_information": ["需要模拟的初级粒子事件数（影响统计精度）"]}',
        task_spec={"simulation_scope": ["geant4"]},
        include_defaults=True,
    )

    question_blob = json.dumps(review["questions"], ensure_ascii=False)
    assert "run.events" not in question_blob
    assert "事件数" not in question_blob
    assert "粒子事件" not in question_blob


@pytest.mark.asyncio
async def test_requirements_review_fallbacks_when_repair_returns_non_review_json(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_requirements_review_repair_echo"
    task_dir = tmp_path / "jobs" / job_id / STAGE_TASK_PLAN
    task_dir.mkdir(parents=True)
    task_spec_path = task_dir / "task_spec.json"
    task_spec_path.write_text(
        json.dumps(
            {
                "particle": {
                    "type": "neutron",
                    "pdg_code": 2112,
                    "energy_MeV": 14.0,
                    "energy_unit": "MeV",
                },
                "materials": ["polyethylene", "borated polyethylene", "lead", "silicon"],
            }
        ),
        encoding="utf-8",
    )
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "Build a 14 MeV neutron shielding stack study.",
        "task_spec_path": str(task_spec_path),
        "simulation_scope": ["geant4"],
        "task_planning_status": "passed",
        "job_workspace": str(tmp_path / "jobs" / job_id),
        "workspace_root": str(tmp_path),
        "execution_mode": "test",
        "run_mode": "test",
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")
    calls: list[dict[str, object]] = []

    class FakeGateway:
        async def call(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return ModelCallResult(
                    task=ModelTask.MODEL_READINESS,
                    tier=ModelTier.LITE,
                    provider=ModelProvider.MOCK,
                    model_name="lite-review",
                    content=(
                        "{\n"
                        '  "status": "needs_user_input",\n'
                        '  "summary_for_user": "请确认仿真目标、关键参数和继续执行条件。",\n'
                        '  "missing_information": ["各屏蔽层的厚度"],\n'
                        '  "questions": [\n'
                        "    {\n"
                        '      "field_path": "shielding.layer_thicknesses",\n'
                        '      "question": "各屏蔽层的厚度分别是多少？",\n'
                        '      "recommended_value": "聚乙烯 5 cm，含硼聚乙烯 5 cm，铅 2 cm，硅探测器 3 mm",\n'
                        '      "reason": "缺少厚度时无法构建可靠几何。"\n'
                        "    }\n"
                        "  ],\n"
                        '  "physics_risks": ["次级伽马代理定义不明确"],\n'
                    ),
                    parsed_json=None,
                )
            return ModelCallResult(
                task=ModelTask.MODEL_READINESS,
                tier=ModelTier.LITE,
                provider=ModelProvider.MOCK,
                model_name="lite-review",
                content='{"instruction":"JSON parse failed","malformed_content":{}}',
                parsed_json={
                    "instruction": "JSON parse failed",
                    "parse_error": "JSON parse failed at line 1, column 1",
                    "malformed_content": {},
                },
            )

    monkeypatch.setattr("agent_core.models.gateway.get_model_gateway", lambda: FakeGateway())

    result = await service.run_phase("requirements_review")

    assert result.success is True
    request_path = Path(service.state["requirements_review_request_path"])
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["summary_for_user"] == "请确认仿真目标、关键参数和继续执行条件。"
    assert request["missing_information"] == ["各屏蔽层的厚度"]
    assert request["questions"][0]["field_path"] == "shielding.layer_thicknesses"
    assert request["json_repair"]["attempted"] is True
    assert request["json_repair"]["repaired"] is False
    assert request["json_repair"]["fallback_extracted"] is True


@pytest.mark.asyncio
async def test_requirements_review_approval_reinvokes_lite_before_modeling(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_requirements_review_approve"
    job_dir = tmp_path / "jobs" / job_id
    review_dir = job_dir / STAGE_TASK_PLAN
    review_dir.mkdir(parents=True)
    request_path = review_dir / "requirements_review_request.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": "requirements_review_v1",
                "summary_for_user": "请确认参数。",
                "proposed_parameters": [
                    {
                        "field_path": "source.energy",
                        "proposed_value": "150 MeV",
                        "source_type": "user",
                        "confidence": 0.99,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "Build proton benchmark",
        "job_workspace": str(job_dir),
        "workspace_root": str(tmp_path),
        "requirements_review_status": "needs_user_input",
        "requirements_review_request_path": str(request_path),
        "confirmation_status": "pending",
        "human_confirmation_required": True,
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")
    task_spec_path = review_dir / "task_spec.json"
    task_spec_path.write_text(
        json.dumps({"particle": {"type": "proton", "energy_MeV": 150}}),
        encoding="utf-8",
    )
    service.state["task_spec_path"] = str(task_spec_path)
    calls: list[dict[str, object]] = []

    class FakeGateway:
        async def call(self, **kwargs):
            calls.append(kwargs)
            return ModelCallResult(
                task=ModelTask.MODEL_READINESS,
                tier=ModelTier.LITE,
                provider=ModelProvider.MOCK,
                model_name="lite-review",
                content="{}",
                parsed_json={
                    "status": "pass",
                    "summary_for_user": "用户确认后参数足够明确。",
                    "missing_information": [],
                    "ambiguous_parameters": [],
                    "physics_risks": [],
                    "questions": [],
                    "proposed_parameters": [
                        {
                            "field_path": "scoring.bin_width",
                            "proposed_value": "1 mm",
                            "source_type": "user_supplement",
                            "confidence": 0.99,
                        }
                    ],
                    "proposed_defaults": [],
                },
            )

    monkeypatch.setattr("agent_core.models.gateway.get_model_gateway", lambda: FakeGateway())

    status = await service.submit_confirmation(
        {"user_decision": "approve", "feedback": "Use 1 mm scoring bins."},
        auto_continue=False,
    )

    assert status.status == "running"
    assert status.current_phase == "g4_modeling"
    assert service.state["requirements_review_status"] == "approved"
    assert service.state["human_confirmation_required"] is False
    assert len(calls) == 1
    assert "Use 1 mm scoring bins." in str(calls[0]["user_prompt"])
    confirmed_path = Path(service.state["confirmed_requirement_plan_path"])
    assert confirmed_path.is_file()
    confirmed = json.loads(confirmed_path.read_text(encoding="utf-8"))
    assert confirmed["schema_version"] == "confirmed_requirement_plan_v1"
    assert confirmed["user_response"]["user_decision"] == "model_pass"
    assert confirmed["user_response"]["requirements_review_supplements"] == [
        {"user_decision": "approve", "feedback": "Use 1 mm scoring bins."}
    ]


@pytest.mark.asyncio
async def test_requirements_review_affirmative_supplement_reinvokes_lite_before_modeling(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_requirements_review_affirmative_supplement"
    job_dir = tmp_path / "jobs" / job_id
    review_dir = job_dir / STAGE_TASK_PLAN
    review_dir.mkdir(parents=True)
    request_path = review_dir / "requirements_review_request.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": "requirements_review_v1",
                "summary_for_user": "请确认参数。",
                "proposed_defaults": [
                    {
                        "field_path": "scoring.bin_width",
                        "proposed_value": "1 mm",
                        "reason": "Depth-dose benchmark default.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "Build proton benchmark",
        "job_workspace": str(job_dir),
        "workspace_root": str(tmp_path),
        "requirements_review_status": "needs_user_input",
        "requirements_review_request_path": str(request_path),
        "confirmation_status": "pending",
        "human_confirmation_required": True,
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")
    task_spec_path = review_dir / "task_spec.json"
    task_spec_path.write_text(
        json.dumps({"particle": {"type": "proton", "energy_MeV": 150}}),
        encoding="utf-8",
    )
    service.state["task_spec_path"] = str(task_spec_path)
    calls: list[dict[str, object]] = []

    class FakeGateway:
        async def call(self, **kwargs):
            calls.append(kwargs)
            return ModelCallResult(
                task=ModelTask.MODEL_READINESS,
                tier=ModelTier.LITE,
                provider=ModelProvider.MOCK,
                model_name="lite-review",
                content="{}",
                parsed_json={
                    "status": "pass",
                    "summary_for_user": "全部按推荐后参数足够明确。",
                    "missing_information": [],
                    "ambiguous_parameters": [],
                    "physics_risks": [],
                    "questions": [],
                    "proposed_parameters": [
                        {
                            "field_path": "scoring.bin_width",
                            "proposed_value": "1 mm",
                            "source_type": "model_recommended_and_user_accepted",
                            "confidence": 0.99,
                        }
                    ],
                    "proposed_defaults": [],
                },
            )

    monkeypatch.setattr("agent_core.models.gateway.get_model_gateway", lambda: FakeGateway())

    status = await service.submit_confirmation(
        {"user_decision": "ask_more", "feedback": "全部按照你的推荐"},
        auto_continue=False,
    )

    assert status.status == "running"
    assert status.current_phase == "g4_modeling"
    assert service.state["requirements_review_status"] == "approved"
    assert service.state["confirmation_status"] == "approved"
    assert len(calls) == 1
    assert "全部按照你的推荐" in str(calls[0]["user_prompt"])
    assert not service.state.get("termination_reason")
    confirmed = json.loads(
        Path(service.state["confirmed_requirement_plan_path"]).read_text(
            encoding="utf-8",
        )
    )
    assert confirmed["user_response"]["user_decision"] == "model_pass"
    assert confirmed["user_response"]["requirements_review_supplements"] == [
        {"user_decision": "ask_more", "feedback": "全部按照你的推荐"}
    ]
    assert str(service.state["requirements_review_response_path"]).startswith(str(tmp_path))
    assert str(service.state["confirmed_requirement_plan_path"]).startswith(str(tmp_path))


@pytest.mark.asyncio
async def test_requirements_review_writes_only_to_service_workspace(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_requirements_review_workspace_isolation"
    task_dir = tmp_path / "jobs" / job_id / STAGE_TASK_PLAN
    task_dir.mkdir(parents=True)
    task_spec_path = task_dir / "task_spec.json"
    task_spec_path.write_text(
        json.dumps({"particle": {"type": "proton", "energy_MeV": 150}}),
        encoding="utf-8",
    )
    real_workspace_job = Path("simulation_workspace") / "jobs" / job_id
    assert not real_workspace_job.exists()
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "Build a 150 MeV proton depth-dose benchmark.",
        "task_spec_path": str(task_spec_path),
        "simulation_scope": ["geant4"],
        "task_planning_status": "passed",
        "job_workspace": str(tmp_path / "jobs" / job_id),
        "workspace_root": str(tmp_path),
        "execution_mode": "test",
        "run_mode": "test",
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")

    class FakeGateway:
        async def call(self, **kwargs):
            return ModelCallResult(
                task=ModelTask.MODEL_READINESS,
                tier=ModelTier.LITE,
                provider=ModelProvider.MOCK,
                model_name="lite-review",
                content="{}",
                parsed_json={
                    "summary_for_user": "请确认参数。",
                    "missing_information": [],
                    "ambiguous_parameters": [],
                    "physics_risks": [],
                    "questions": [],
                    "proposed_parameters": [],
                    "proposed_defaults": [],
                },
            )

    monkeypatch.setattr("agent_core.models.gateway.get_model_gateway", lambda: FakeGateway())

    result = await service.run_phase("requirements_review")

    assert result.success is True
    assert service.state["requirements_review_request_path"].startswith(str(tmp_path))
    assert not real_workspace_job.exists()


@pytest.mark.asyncio
async def test_requirements_review_supplement_reinvokes_lite_until_pass(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_requirements_review_supplement"
    job_dir = tmp_path / "jobs" / job_id
    review_dir = job_dir / STAGE_TASK_PLAN
    review_dir.mkdir(parents=True)
    request_path = review_dir / "requirements_review_request.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": "requirements_review_v1",
                "summary_for_user": "请确认参数。",
                "questions": [
                    {
                        "field_path": "source.energy",
                        "question": "请确认束流能量。",
                        "proposed_value": "150 MeV",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "Build proton benchmark",
        "job_workspace": str(job_dir),
        "workspace_root": str(tmp_path),
        "requirements_review_status": "needs_user_input",
        "requirements_review_request_path": str(request_path),
        "confirmation_status": "pending",
        "human_confirmation_required": True,
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")
    task_spec_path = review_dir / "task_spec.json"
    task_spec_path.write_text(
        json.dumps({"particle": {"type": "proton", "energy_MeV": 150}}),
        encoding="utf-8",
    )
    service.state["task_spec_path"] = str(task_spec_path)
    calls: list[dict[str, object]] = []

    class FakeGateway:
        async def call(self, **kwargs):
            calls.append(kwargs)
            return ModelCallResult(
                task=ModelTask.MODEL_READINESS,
                tier=ModelTier.LITE,
                provider=ModelProvider.MOCK,
                model_name="lite-review",
                content="{}",
                parsed_json={
                    "status": "pass",
                    "summary_for_user": "补充信息已足够，可以进入 Geant4 建模。",
                    "missing_information": [],
                    "ambiguous_parameters": [],
                    "physics_risks": [],
                    "questions": [],
                    "proposed_parameters": [
                        {
                            "field_path": "source.energy",
                            "proposed_value": "160 MeV",
                            "source_type": "user_supplement",
                            "confidence": 0.99,
                        }
                    ],
                    "proposed_defaults": [],
                },
            )

    monkeypatch.setattr("agent_core.models.gateway.get_model_gateway", lambda: FakeGateway())

    status = await service.submit_confirmation(
        {"user_decision": "ask_more", "feedback": "能量改成 160 MeV"},
        auto_continue=False,
    )

    assert status.status == "running"
    assert status.current_phase == "g4_modeling"
    assert status.needs_confirmation is False
    assert service.state["requirements_review_status"] == "approved"
    assert service.state["confirmation_status"] == "approved"
    assert service.state["human_confirmation_required"] is False
    assert service.state["requirements_review_supplements"] == [
        {"user_decision": "ask_more", "feedback": "能量改成 160 MeV"}
    ]
    assert len(calls) == 1
    assert calls[0]["tier"] == ModelTier.LITE
    assert "requirements_review_supplements" in str(calls[0]["user_prompt"])
    assert "能量改成 160 MeV" in str(calls[0]["user_prompt"])
    confirmed_path = Path(service.state["confirmed_requirement_plan_path"])
    assert confirmed_path.is_file()
    assert not service.state.get("termination_reason")


@pytest.mark.asyncio
async def test_requirements_review_confirmed_answers_are_hard_constraints(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_requirements_review_confirmed_answers"
    job_dir = tmp_path / "jobs" / job_id
    review_dir = job_dir / STAGE_TASK_PLAN
    review_dir.mkdir(parents=True)
    request_path = review_dir / "requirements_review_request.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": "requirements_review_v1",
                "summary_for_user": "请确认机器人环境和几何。",
                "questions": [
                    {
                        "field_path": "environment.medium",
                        "question": "是否坚持真空环境，还是改为冷却水介质？",
                        "recommended_value": "保持真空环境",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    task_spec_path = review_dir / "task_spec.json"
    task_spec_path.write_text(
        json.dumps(
            {
                "particle": {"type": "gamma", "energy_MeV": 10},
                "target": {"material": "iron", "dimensions": [10, 10, 20]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "10 MeV gamma 垂直入射铁质机器人，真空环境。",
        "job_workspace": str(job_dir),
        "workspace_root": str(tmp_path),
        "requirements_review_status": "needs_user_input",
        "requirements_review_request_path": str(request_path),
        "task_spec_path": str(task_spec_path),
        "confirmation_status": "pending",
        "human_confirmation_required": True,
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")
    calls: list[dict[str, object]] = []

    class FakeGateway:
        async def call(self, **kwargs):
            calls.append(kwargs)
            return ModelCallResult(
                task=ModelTask.MODEL_READINESS,
                tier=ModelTier.LITE,
                provider=ModelProvider.MOCK,
                model_name="lite-review",
                content="{}",
                parsed_json={
                    "status": "needs_user_input",
                    "summary_for_user": "仍需确认环境。",
                    "missing_information": ["真空环境是否保持不变仍需确认。"],
                    "ambiguous_parameters": [],
                    "physics_risks": [],
                    "questions": [
                        {
                            "field_path": "environment.medium",
                            "question": "是否坚持真空环境，还是改为冷却水介质？",
                            "recommended_value": "保持真空环境",
                            "reason": "模型重复询问已确认字段。",
                        }
                    ],
                    "proposed_parameters": [],
                    "proposed_defaults": [],
                },
            )

    monkeypatch.setattr("agent_core.models.gateway.get_model_gateway", lambda: FakeGateway())

    payload = {
        "schema_version": "requirements_review_answers_v1",
        "confirmed_parameters": [
            {
                "field_path": "environment.medium",
                "question": "是否坚持真空环境，还是改为冷却水介质？",
                "decision": "accept_recommended",
                "selected_value": "保持真空环境",
                "recommended_value": "保持真空环境",
            }
        ],
        "user_note": "先坚持当前简化方案。",
    }
    status = await service.submit_confirmation(
        {
            "user_decision": "ask_more",
            "feedback": (
                "environment.medium: 确认推荐 保持真空环境\n"
                f"RADAGENT_CONFIRMATION_JSON: {json.dumps(payload, ensure_ascii=False)}"
            ),
        },
        auto_continue=False,
    )

    assert status.status == "running"
    assert status.current_phase == "g4_modeling"
    assert service.state["requirements_review_status"] == "approved"
    assert service.state["confirmation_status"] == "approved"
    assert service.state["human_confirmation_required"] is False
    assert len(calls) == 1
    prompt = str(calls[0]["user_prompt"])
    assert "confirmed_requirement_answers" in prompt
    assert "environment.medium" in prompt
    assert "Do not ask again" in prompt
    confirmed = json.loads(
        Path(service.state["confirmed_requirement_plan_path"]).read_text(
            encoding="utf-8",
        )
    )
    assert confirmed["review"]["questions"] == []
    assert confirmed["review"]["missing_information"] == []
    assert confirmed["review"]["confirmed_requirement_answers"][0]["field_path"] == "environment.medium"


@pytest.mark.asyncio
async def test_requirements_review_pending_ignores_prior_briefing_approval(
    tmp_path,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_requirements_review_prior_briefing"
    job_dir = tmp_path / "jobs" / job_id
    review_dir = job_dir / STAGE_TASK_PLAN
    review_dir.mkdir(parents=True)
    request_path = review_dir / "requirements_review_request.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": "requirements_review_v1",
                "summary_for_user": "请确认束流参数。",
                "questions": [
                    {
                        "field_path": "source.energy",
                        "question": "请确认质子束能量。",
                        "recommended_value": "150 MeV",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    service.store.upsert_job(
        job_id=job_id,
        user_query="Build proton benchmark",
        project_id=str(project["id"]),
        status="paused",
        current_phase="requirements_review",
        current_phase_idx=PIPELINE_PHASES.index("requirements_review"),
        job_workspace=str(job_dir),
    )
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "Build proton benchmark",
        "job_workspace": str(job_dir),
        "workspace_root": str(tmp_path),
        "requirements_review_status": "needs_user_input",
        "requirements_review_request_path": str(request_path),
        "confirmation_status": "pending",
        "human_confirmation_required": True,
        "raw_human_response": {
            "user_decision": "approve",
            "user_notes": "Approved before pipeline start through RadAgent briefing.",
        },
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")
    called_phases: list[str] = []

    async def requirements_review(state: dict) -> dict:
        called_phases.append("requirements_review")
        return {
            "requirements_review_status": "approved",
            "confirmation_status": "approved",
            "human_confirmation_required": False,
            "confirmed_requirement_plan_path": str(review_dir / "confirmed_requirement_plan.json"),
        }

    async def human_confirmation(state: dict) -> dict:
        raise AssertionError("requirements review supplement must not enter legacy confirmation")

    service._subgraph_nodes = {
        "requirements_review": requirements_review,
        "human_confirmation": human_confirmation,
    }

    assert service.get_status().needs_confirmation is True

    status = await service.submit_confirmation(
        {"user_decision": "ask_more", "feedback": "全部按照推荐参数"},
        auto_continue=False,
    )

    assert called_phases == ["requirements_review"]
    assert status.status == "running"
    assert status.current_phase == "g4_modeling"
    assert status.needs_confirmation is False
    assert service.state["requirements_review_supplements"] == [
        {"user_decision": "ask_more", "feedback": "全部按照推荐参数"}
    ]


def test_recent_events_ignores_stale_active_model_call_without_runtime_worker(
    tmp_path,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    service.state = {"job_id": "job_stale_model_call"}
    active_path = tmp_path / "jobs" / "job_stale_model_call" / "logs" / "active_model_call.json"
    active_path.parent.mkdir(parents=True)
    active_path.write_text(
        json.dumps(
            {
                "model_call_id": "call-stale",
                "status": "running",
                "task": "codegen",
                "module_name": "simulation_core",
                "transcript_path": "logs/model_calls/call-stale_codegen.json",
            }
        ),
        encoding="utf-8",
    )

    events = service.recent_events(limit=1)

    assert not any(event.event_type == "model_call_start" for event in events)


@pytest.mark.asyncio
async def test_run_until_blocked_routes_task_planning_user_input_to_requirements_review(
    tmp_path,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_task_planning_needs_review"
    job_dir = tmp_path / "jobs" / job_id
    task_dir = job_dir / STAGE_TASK_PLAN
    task_dir.mkdir(parents=True)
    task_spec_path = task_dir / "task_spec.json"
    task_spec_path.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "user_query": "做一个mosfet的g4辐照仿真",
                "simulation_scope": ["geant4"],
                "particle": {},
                "requirements_review_hints": {
                    "missing_information": ["radiation source particle"]
                },
            }
        ),
        encoding="utf-8",
    )
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "做一个mosfet的g4辐照仿真",
        "workspace_root": str(tmp_path),
        "job_workspace": str(job_dir),
        "errors": [],
    }
    service.store.upsert_job(
        job_id=job_id,
        user_query="做一个mosfet的g4辐照仿真",
        project_id=str(project["id"]),
        status="running",
        current_phase="task_planning",
        current_phase_idx=PIPELINE_PHASES.index("task_planning"),
        job_workspace=str(job_dir),
    )
    service.current_phase_idx = PIPELINE_PHASES.index("task_planning")
    calls: list[str] = []

    async def task_planning(state: dict) -> dict:
        calls.append("task_planning")
        return {
            "task_spec_path": str(task_spec_path),
            "simulation_scope": ["geant4"],
            "task_planning_status": "needs_user_input",
            "task_spec_errors": [],
            "clarification_request": {},
            "termination_reason": "",
        }

    async def requirements_review(state: dict) -> dict:
        calls.append("requirements_review")
        return {
            "requirements_review_status": "needs_user_input",
            "requirements_review_request_path": str(task_dir / "requirements_review_request.json"),
            "confirmation_status": "pending",
            "human_confirmation_required": True,
            "confirmation_summary": "请确认辐照粒子类型和能量。",
        }

    service._subgraph_nodes = {
        "task_planning": task_planning,
        "requirements_review": requirements_review,
    }

    status = await service.run_until_blocked()

    assert calls == ["task_planning", "requirements_review"]
    assert status.status == "paused"
    assert status.current_phase == "requirements_review"
    assert status.needs_confirmation is True
    assert service.state["task_planning_status"] == "needs_user_input"
    assert service.state["requirements_review_status"] == "needs_user_input"
    assert not service.state.get("termination_reason")


@pytest.mark.asyncio
async def test_run_until_blocked_context_missing_parameters_enters_requirements_review(
    tmp_path,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_context_missing_params"
    job_dir = tmp_path / "jobs" / job_id
    context_dir = job_dir / STAGE_CONTEXT
    task_dir = job_dir / STAGE_TASK_PLAN
    context_dir.mkdir(parents=True)
    task_dir.mkdir(parents=True)
    context_report_path = context_dir / "context_sufficiency_report.json"
    evidence_map_path = context_dir / "evidence_map.json"
    task_spec_path = task_dir / "task_spec.json"
    task_spec_path.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "user_query": "做一个mosfet的g4辐照仿真",
                "simulation_scope": ["geant4"],
                "clarification_request": {"reason": "ambiguous_device_tid"},
            }
        ),
        encoding="utf-8",
    )
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "做一个mosfet的g4辐照仿真",
        "workspace_root": str(tmp_path),
        "job_workspace": str(job_dir),
        "errors": [],
    }
    service.store.upsert_job(
        job_id=job_id,
        user_query="做一个mosfet的g4辐照仿真",
        project_id=str(project["id"]),
        status="running",
        current_phase="context",
        current_phase_idx=PIPELINE_PHASES.index("context"),
        job_workspace=str(job_dir),
    )
    service.current_phase_idx = PIPELINE_PHASES.index("context")
    calls: list[str] = []

    async def context(state: dict) -> dict:
        calls.append("context")
        return {
            "context_decision": "allow_with_web_supplement",
            "context_report_path": str(context_report_path),
            "evidence_map_path": str(evidence_map_path),
        }

    async def task_planning(state: dict) -> dict:
        calls.append("task_planning")
        return {
            "task_spec_path": str(task_spec_path),
            "simulation_scope": ["geant4"],
            "task_planning_status": "needs_user_input",
            "task_spec_errors": [],
            "clarification_request": {"reason": "ambiguous_device_tid"},
            "termination_reason": "",
        }

    async def requirements_review(state: dict) -> dict:
        calls.append("requirements_review")
        return {
            "requirements_review_status": "needs_user_input",
            "requirements_review_request_path": str(task_dir / "requirements_review_request.json"),
            "confirmation_status": "pending",
            "human_confirmation_required": True,
        }

    service._subgraph_nodes = {
        "context": context,
        "task_planning": task_planning,
        "requirements_review": requirements_review,
    }

    status = await service.run_until_blocked()

    assert calls == ["context", "task_planning", "requirements_review"]
    assert status.status == "paused"
    assert status.current_phase == "requirements_review"
    assert status.needs_confirmation is True
    assert service.state["context_decision"] == "allow_with_web_supplement"
    assert service.state["requirements_review_status"] == "needs_user_input"


def test_status_exposes_runtime_active_for_background_continue(tmp_path, monkeypatch) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    service.state["job_id"] = "job-active-status"
    service.store.upsert_job(job_id="job-active-status", user_query="simulate")
    started = threading.Event()
    release = threading.Event()

    async def fake_run_until_blocked() -> None:
        started.set()
        release.wait(timeout=5)

    monkeypatch.setattr(service, "run_until_blocked", fake_run_until_blocked)

    assert service.continue_in_background(reason="retry") is True
    try:
        assert started.wait(timeout=5) is True
        status = service.get_status()
        assert status.key_statuses["runtime_active"] is True
        assert status.state["runtime_active"] is True
    finally:
        release.set()
        thread = service._background_continue_thread
        if thread is not None:
            thread.join(timeout=5)

    status = service.get_status()
    assert status.key_statuses["runtime_active"] is False
    assert status.state["runtime_active"] is False


def test_read_artifact_reports_invalid_json_without_blocking_text_view(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    json_path = tmp_path / "broken.json"
    json_path.write_text('{"ok": ', encoding="utf-8")

    content = service.read_artifact(str(json_path))

    assert content.kind == "text"
    assert content.text == '{"ok": '
    assert content.json_data is None
    assert content.errors
    assert content.errors[0].startswith("Invalid JSON:")


def test_package_generated_source_files_creates_downloadable_zip(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    job_id = "job_source_package"
    project_dir = tmp_path / "jobs" / job_id / "06_patch" / "geant4_project"
    (project_dir / "src").mkdir(parents=True)
    (project_dir / "include").mkdir()
    (project_dir / "build").mkdir()
    (project_dir / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\n",
        encoding="utf-8",
    )
    (project_dir / "src" / "DetectorConstruction.cc").write_text(
        "// detector\n",
        encoding="utf-8",
    )
    (project_dir / "include" / "DetectorConstruction.hh").write_text(
        "// header\n",
        encoding="utf-8",
    )
    (project_dir / "run.mac").write_text("/run/beamOn 10\n", encoding="utf-8")
    (project_dir / "build" / "radagent").write_text("binary", encoding="utf-8")
    service.state = {
        "job_id": job_id,
        "job_workspace": str(tmp_path / "jobs" / job_id),
        "generated_code_dir": str(project_dir),
    }

    package = service.package_generated_source_files()

    assert package["success"] is True
    assert package["content_type"] == "application/zip"
    assert package["filename"] == f"{job_id}_geant4_source.zip"
    archive_path = Path(package["path"])
    assert archive_path.is_file()
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "CMakeLists.txt" in names
        assert "src/DetectorConstruction.cc" in names
        assert "include/DetectorConstruction.hh" in names
        assert "run.mac" in names
        assert "build/radagent" not in names


@pytest.mark.asyncio
async def test_chat_emits_events_without_ui_dependency(tmp_path, monkeypatch) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    agent = AsyncMock()
    long_answer = "x" * 300
    agent.chat.return_value = long_answer
    agent.last_tool_results = [{"tool": "orbit_radiation_ap8ae8_query", "success": True}]
    service._chat_agent = agent

    response = await service.chat("question")

    assert response.message == long_answer
    assert [event.event_type for event in response.events] == [
        "copilot_started",
        "copilot_finished",
    ]
    assert response.events[0].payload["message"] == "question"
    assert len(response.events[1].summary) == 120
    assert response.events[1].payload["message"] == long_answer
    assert response.events[1].payload["tool_results"] == agent.last_tool_results
    agent.chat.assert_awaited_once()
    args, kwargs = agent.chat.await_args
    assert args == ("question",)
    assert kwargs["workflow_context"]["status"] == "idle"


@pytest.mark.asyncio
async def test_copilot_can_offer_controlled_simulation_start(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)

    response = await service.chat(
        "建立一个 Geant4 仿真：外部质子束沿 z 方向入射硅探测器，观察轨迹和能量沉积"
    )

    assert response.commands == [
        {
            "name": "start_simulation_briefing",
            "args": {
                "query": (
                    "建立一个 Geant4 仿真：外部质子束沿 z 方向入射硅探测器，"
                    "观察轨迹和能量沉积"
                )
            },
            "risk": "write",
            "status": "pending_confirmation",
            "summary": "Prepare simulation briefing",
        }
    ]
    assert "确认" in response.message
    assert "start_job" not in response.message


def test_service_exposes_frontend_safe_model_config(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "RADAGENT_MODEL_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1",
                "RADAGENT_API_KEY=secret-key",
                "RADAGENT_MODEL_PRO=mimo-v2.5-pro",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("RADAGENT_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("RADAGENT_API_KEY", raising=False)
    monkeypatch.delenv("RADAGENT_MODEL_PRO", raising=False)
    service = RadAgentAppService(workspace_root=tmp_path, env_path=env_file)

    config = service.get_model_config()

    assert config.tiers[ModelTier.PRO.value].model_name == "mimo-v2.5-pro"
    assert config.tiers[ModelTier.PRO.value].base_url == "https://token-plan-cn.xiaomimimo.com/v1"
    assert config.tiers[ModelTier.PRO.value].api_key_configured is True
    assert config.agentic_repair_max_turns == 48
    assert config.agentic_repair_history_chars == 0
    assert "secret-key" not in config.model_dump_json()


def test_startup_status_reports_tools_and_models_without_secrets(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RADAGENT_MODEL_LITE", "lite-test")
    monkeypatch.setenv("RADAGENT_MODEL_PRO", "pro-test")
    monkeypatch.setenv("RADAGENT_MODEL_MAX", "max-test")
    monkeypatch.setenv("RADAGENT_API_KEY", "secret-value")
    monkeypatch.setenv("NGSPICE_BIN", "/usr/bin/ngspice")
    monkeypatch.setenv("TCAD_INSTALL_DIR", "/opt/synopsys/tcad")
    monkeypatch.setenv("TCAD_SDEVICE_BIN", "/opt/synopsys/tcad/bin/sdevice")

    service = RadAgentAppService(workspace_root=tmp_path)
    status = service.get_startup_status()

    assert status.product_name == "RadAgent"
    assert status.tools["geant4"].label == "Geant4"
    assert status.tools["tcad"].configured is True
    assert "sdevice=" in status.tools["tcad"].detail
    assert status.tools["ngspice"].path == "/usr/bin/ngspice"
    assert status.models["lite"].model_name == "lite-test"
    assert status.models["pro"].model_name == "pro-test"
    assert status.models["max"].model_name == "max-test"
    assert status.models["lite"].api_key_configured is True
    assert "secret-value" not in status.model_dump_json()


@pytest.mark.asyncio
async def test_repair_continuation_confirmation_sets_turn_override(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    request = {
        "status": "pending",
        "reason": "agent_loop_max_turns",
        "current_turns": 48,
        "increment_turns": 12,
        "requested_total_turns": 60,
        "message": "修复 Agent 已耗尽 48 轮但仍未通过运行门禁，是否增加 12 轮继续修复？",
    }
    service.state = {
        "job_id": "job_repair_continue",
        "user_query": "build detector",
        "job_workspace": str(tmp_path / "jobs" / "job_repair_continue"),
        "workspace_root": str(tmp_path),
        "execution_mode": "strict",
        "run_mode": "strict",
        "g4_codegen_status": "needs_user_input",
        "repair_continuation_status": "pending",
        "repair_continuation_request": request,
        "codegen_errors": ["compile failed"],
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("g4_codegen")

    status = service.get_status()
    review = service.get_confirmation_review()

    assert status.status == "paused"
    assert status.needs_confirmation is True
    assert review["type"] == "repair_continuation"
    assert "是否增加 12 轮" in review["summary"]

    approved = await service.submit_confirmation(
        {"user_decision": "approve", "feedback": "continue"},
        auto_continue=False,
    )

    assert approved.status == "running"
    assert approved.needs_confirmation is False
    assert approved.current_phase == "g4_codegen"
    assert service.state["repair_continuation_status"] == "approved"
    assert service.state["repair_continuation_request"]["status"] == "approved"
    assert service.state["agentic_repair_max_turns_override"] == 60
    assert service.state["g4_codegen_status"] == ""


@pytest.mark.asyncio
async def test_submit_confirmation_does_not_advance_when_modeling_failed(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    service.state = {
        "job_id": "job_failed_modeling",
        "user_query": "build Bragg benchmark",
        "g4_modeling_status": "failed",
        "termination_reason": "g4_modeling status is failed",
        "errors": ["world volume does not contain daughter layers"],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")

    async def fail_if_called(_: str) -> None:
        raise AssertionError("failed modeling should not rerun human confirmation")

    monkeypatch.setattr(service, "run_phase", fail_if_called)

    status = await service.submit_confirmation(
        {"user_decision": "approve", "feedback": "approve"},
        auto_continue=True,
    )

    assert status.status == "failed"
    assert status.current_phase == "requirements_review"
    assert service.current_phase_idx == PIPELINE_PHASES.index("requirements_review")
    assert any(
        event.event_type == "human_confirmation_blocked_by_modeling_failure"
        for event in service.recent_events()
    )


@pytest.mark.asyncio
async def test_submit_confirmation_rejects_legacy_codegen_physics_confirmation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy post-codegen confirmation requests must not be accepted."""
    service = RadAgentAppService(workspace_root=tmp_path)
    job_dir = tmp_path / "jobs" / "job_codegen_physics_confirm"
    confirmation_dir = job_dir / STAGE_HUMAN_CONFIRMATION
    confirmation_dir.mkdir(parents=True)
    request_path = confirmation_dir / "confirmation_request_round_1.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": "codegen_physics_confirmation_v1",
                "source": "physics_quality_review",
                "summary_for_user": "确认 tracker material。",
                "critical_confirmations": [
                    {
                        "field_path": "g4_codegen.physics_quality_review.0",
                        "target": "materials[1]",
                        "proposed_value": "plastic scintillator or silicon",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    service.state = {
        "job_id": "job_codegen_physics_confirm",
        "user_query": "build muon tomography",
        "job_workspace": str(job_dir),
        "workspace_root": str(tmp_path),
        "execution_mode": "strict",
        "run_mode": "strict",
        "g4_modeling_status": "passed",
        "g4_codegen_status": "needs_user_input",
        "human_confirmation_required": True,
        "confirmation_status": "pending",
        "confirmation_request_path": str(request_path),
        "confirmation_summary": "确认 tracker material。",
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("g4_codegen")

    async def fail_if_called(_: str) -> None:
        raise AssertionError("legacy codegen confirmation must not run HC subgraph")

    monkeypatch.setattr(service, "run_phase", fail_if_called)

    status = await service.submit_confirmation(
        {"user_decision": "approve", "feedback": "Use plastic scintillator."},
        auto_continue=False,
    )

    assert status.status == "failed"
    assert status.current_phase == "g4_codegen"
    assert service.state["confirmation_status"] == "rejected"
    assert service.state["human_confirmation_required"] is False
    assert service.state["g4_codegen_status"] == "failed"
    assert "confirmation_record_path" not in service.state
    assert "confirmed_model_plan_path" not in service.state
    assert any(
        event.event_type == "legacy_codegen_physics_confirmation_rejected"
        for event in service.recent_events()
    )


def test_modeling_failure_does_not_surface_empty_actionable_confirmation(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    job_dir = tmp_path / "jobs" / "job_failed_modeling"
    model_dir = job_dir / "03_model_ir"
    model_dir.mkdir(parents=True)
    report_path = model_dir / "validation_report.json"
    report_path.write_text(
        """
        {
          "failed": 1,
          "total_errors": 1,
          "results": [
            {
              "validator": "NoSimplification",
              "passed": false,
              "errors": ["Complex model requested but no oxide component found."]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    service.state = {
        "job_id": "job_failed_modeling",
        "job_workspace": str(job_dir),
        "g4_modeling_status": "failed",
        "human_confirmation_required": True,
        "validation_report_path": str(report_path),
        "termination_reason": "g4_modeling status is failed",
        "errors": ["g4_modeling status is failed"],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")

    status = service.get_status()
    review = service.get_confirmation_review()

    assert status.status == "failed"
    assert status.needs_confirmation is False
    assert review["type"] == "modeling_failure"
    assert review["required"] is False
    assert review["actionable"] is False
    assert "Complex model requested but no oxide component found" in review["summary"]
    assert "validation_report.json" in review["preview"]


def test_legacy_codegen_physics_confirmation_is_not_actionable(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    job_dir = tmp_path / "jobs" / "job_codegen_physics_confirm"
    confirmation_dir = job_dir / STAGE_HUMAN_CONFIRMATION
    confirmation_dir.mkdir(parents=True)
    request_path = confirmation_dir / "confirmation_request_round_1.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": "codegen_physics_confirmation_v1",
                "summary_for_user": "确认 tracker material。",
            }
        ),
        encoding="utf-8",
    )
    service.state = {
        "job_id": "job_codegen_physics_confirm",
        "job_workspace": str(job_dir),
        "g4_modeling_status": "passed",
        "g4_codegen_status": "needs_user_input",
        "human_confirmation_required": True,
        "confirmation_status": "pending",
        "confirmation_request_path": str(request_path),
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("g4_codegen")

    status = service.get_status()
    review = service.get_confirmation_review()

    assert status.status == "failed"
    assert status.needs_confirmation is False
    assert review["type"] == "legacy_codegen_physics_confirmation_disabled"
    assert review["required"] is False
    assert review["actionable"] is False
    assert "codegen" in review["summary"].lower()


def test_confirmation_review_loads_selected_job_without_state_snapshot(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    job_dir = tmp_path / "jobs" / "job_confirmation_only"
    confirmation_dir = job_dir / STAGE_HUMAN_CONFIRMATION
    confirmation_dir.mkdir(parents=True)
    request_path = confirmation_dir / "confirmation_request_round_1.json"
    proposal_path = confirmation_dir / "proposed_model_completion.json"
    report_path = confirmation_dir / "human_confirmation_report.md"
    request_path.write_text(
        json.dumps(
            {
                "summary_for_user": "请确认水层厚度。",
                "questions": [
                    {
                        "field_path": "components.water.dimensions",
                        "proposed_value": {"dz": 300000.0},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    proposal_path.write_text(
        json.dumps(
            {
                "missing_information": ["Step limiter settings need definition."],
                "proposed_components": [
                    {
                        "component_id": "water",
                        "component_type": "layer",
                        "material_id": "G4_WATER",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report_path.write_text("human confirmation report", encoding="utf-8")
    service.store.upsert_job(
        job_id="job_confirmation_only",
        user_query="build water phantom",
        status="paused",
        current_phase="human_confirmation",
        current_phase_idx=PIPELINE_PHASES.index("g4_codegen"),
        job_workspace=str(job_dir),
    )
    service.state = {"job_id": "different_active_job"}

    review = service.get_confirmation_review("job_confirmation_only")

    assert review["job_id"] == "job_confirmation_only"
    assert review["request_path"] == str(request_path)
    assert review["summary"] == "请确认水层厚度。"
    assert review["questions"] == [
        {
            "field_path": "components.water.dimensions",
            "proposed_value": {"dz": 300000.0},
        }
    ]
    assert review["missing_information"] == ["Step limiter settings need definition."]
    assert review["preview"] == "human confirmation report"


@pytest.mark.asyncio
async def test_workflow_diagnosis_uses_lite_model_without_overriding_hard_actions(
    tmp_path,
    monkeypatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    job_dir = tmp_path / "jobs" / "job_failed_modeling"
    model_dir = job_dir / "03_model_ir"
    model_dir.mkdir(parents=True)
    report_path = model_dir / "validation_report.json"
    report_path.write_text(
        """
        {
          "results": [
            {
              "validator": "NoSimplification",
              "passed": false,
              "errors": ["Complex model requested but no oxide component found."]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    service.state = {
        "job_id": "job_failed_modeling",
        "job_workspace": str(job_dir),
        "g4_modeling_status": "failed",
        "human_confirmation_required": True,
        "validation_report_path": str(report_path),
        "termination_reason": "g4_modeling status is failed",
        "errors": ["g4_modeling status is failed"],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")

    class FakeGateway:
        async def call(self, *args, **kwargs):
            from agent_core.models.schemas import (
                ModelCallResult,
                ModelProvider,
                ModelTask,
                ModelTier,
            )

            return ModelCallResult(
                task=ModelTask.FAILURE_DIAGNOSIS,
                tier=ModelTier.LITE,
                provider=ModelProvider.MOCK,
                model_name="fake-lite",
                content=(
                    '{"user_message":"模型误判为需要 oxide。",'
                    '"allowed_actions":["approve"],"next_step_hint":"重新运行建模"}'
                ),
                parsed_json={
                    "user_message": "模型误判为需要 oxide。",
                    "allowed_actions": ["approve"],
                    "next_step_hint": "重新运行建模",
                },
            )

    monkeypatch.setattr("agent_core.models.gateway.get_model_gateway", lambda: FakeGateway())

    diagnosis = await service.get_workflow_diagnosis()

    assert diagnosis["ui_state"] == "modeling_failed"
    assert diagnosis["confirmation_actionable"] is False
    assert diagnosis["allowed_actions"] == ["view_modeling_report", "retry_modeling"]
    assert diagnosis["model_enhanced"] is True
    assert diagnosis["user_message"] == "模型误判为需要 oxide。"


@pytest.mark.asyncio
async def test_workflow_diagnosis_explains_codegen_failure(tmp_path, monkeypatch) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    job_dir = tmp_path / "jobs" / "job_failed_codegen"
    codegen_dir = job_dir / "05_codegen"
    codegen_dir.mkdir(parents=True)
    patch_path = codegen_dir / "proposed_patch.json"
    patch_path.write_text("{}", encoding="utf-8")
    service.state = {
        "job_id": "job_failed_codegen",
        "job_workspace": str(job_dir),
        "g4_codegen_status": "failed",
        "proposed_patch_path": str(patch_path),
        "current_node": "g4_codegen_subgraph",
        "termination_reason": "g4_codegen状态失败",
        "codegen_errors": [
            "simulation_core did not pass layer gate",
            "proposed_patch.changed_files is empty",
        ],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("g4_codegen")

    class FakeGateway:
        async def call(self, *args, **kwargs):
            from agent_core.models.schemas import (
                ModelCallResult,
                ModelProvider,
                ModelTask,
                ModelTier,
            )

            return ModelCallResult(
                task=ModelTask.FAILURE_DIAGNOSIS,
                tier=ModelTier.LITE,
                provider=ModelProvider.MOCK,
                model_name="fake-lite",
                content="{}",
                parsed_json={},
            )

    monkeypatch.setattr("agent_core.models.gateway.get_model_gateway", lambda: FakeGateway())

    diagnosis = await service.get_workflow_diagnosis()

    assert diagnosis["ui_state"] == "codegen_failed"
    assert diagnosis["phase"] == "g4_codegen"
    assert diagnosis["confirmation_actionable"] is False
    assert diagnosis["allowed_actions"] == ["view_codegen_patch", "view_logs", "retry_codegen"]
    assert "simulation_core did not pass layer gate" in diagnosis["blocking_reason"]
    assert str(patch_path) in diagnosis["artifacts"]


@pytest.mark.asyncio
async def test_workflow_diagnosis_identifies_pending_requirements_review(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    review_dir = tmp_path / "jobs" / "job_requirements_review" / STAGE_TASK_PLAN
    review_dir.mkdir(parents=True)
    request_path = review_dir / "requirements_review_request.json"
    request_path.write_text(
        json.dumps(
            {
                "schema_version": "requirements_review_v1",
                "summary_for_user": "请确认水箱尺寸和 depth-dose bin 宽度。",
                "questions": [
                    {
                        "field_path": "scoring.depth_dose.bin_width",
                        "question": "Confirm bin width?",
                        "proposed_value": "1 mm",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    service.state = {
        "job_id": "job_requirements_review",
        "job_workspace": str(tmp_path / "jobs" / "job_requirements_review"),
        "requirements_review_status": "needs_user_input",
        "requirements_review_request_path": str(request_path),
        "confirmation_status": "pending",
        "human_confirmation_required": True,
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("requirements_review")
    real_workspace_job = Path("simulation_workspace") / "jobs" / "job_requirements_review"
    if real_workspace_job.exists():
        import shutil

        shutil.rmtree(real_workspace_job)

    diagnosis = await service.get_workflow_diagnosis()
    review = service.get_confirmation_review()

    assert diagnosis["ui_state"] == "requirements_review_pending"
    assert diagnosis["phase"] == "requirements_review"
    assert diagnosis["confirmation_actionable"] is True
    assert diagnosis["allowed_actions"] == [
        "review_requirements",
        "approve_requirements",
        "reject_requirements",
    ]
    assert diagnosis["artifacts"] == [str(request_path)]
    assert review["type"] == "requirements_review"
    assert review["questions"][0]["field_path"] == "scoring.depth_dose.bin_width"
    assert not real_workspace_job.exists()


@pytest.mark.asyncio
async def test_step_does_not_advance_pending_repair_continuation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    request = {
        "status": "pending",
        "reason": "agent_loop_max_turns",
        "current_turns": 48,
        "increment_turns": 12,
        "requested_total_turns": 60,
        "message": "修复 Agent 已耗尽 48 轮但仍未通过运行门禁，是否增加 12 轮继续修复？",
    }
    service.state = {
        "job_id": "job_repair_step_block",
        "user_query": "build detector",
        "g4_codegen_status": "needs_user_input",
        "repair_continuation_status": "pending",
        "repair_continuation_request": request,
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("g4_codegen")

    async def fail_if_called(_: str) -> None:
        raise AssertionError("step must not rerun g4_codegen while repair approval is pending")

    monkeypatch.setattr(service, "run_phase", fail_if_called)

    result = await service.step()

    assert result.success is False
    assert result.status.status == "paused"
    assert result.status.needs_confirmation is True
    assert result.status.current_phase == "g4_codegen"
    assert service.current_phase_idx == PIPELINE_PHASES.index("g4_codegen")
    assert result.events[0].event_type == "repair_continuation_required"


def test_service_updates_model_config_for_frontend(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    events = []
    monkeypatch.delenv("RADAGENT_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("RADAGENT_API_KEY", raising=False)
    monkeypatch.delenv("RADAGENT_MODEL_LITE", raising=False)
    monkeypatch.delenv("RADAGENT_MODEL_PRO", raising=False)
    monkeypatch.delenv("RADAGENT_MODEL_MAX", raising=False)
    service = RadAgentAppService(
        workspace_root=tmp_path,
        env_path=env_file,
        event_callback=events.append,
    )

    config = service.update_model_config(
        {
            "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
            "api_key": "tp-test-key",
            "lite_model": "mimo-v2.5",
            "pro_model": "mimo-v2.5-pro",
            "max_model": "mimo-v2.5-pro",
            "agentic_repair_max_turns": 12,
            "agentic_repair_history_chars": 36000,
        }
    )

    text = env_file.read_text(encoding="utf-8")
    assert "RADAGENT_MODEL_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1" in text
    assert "RADAGENT_API_KEY=tp-test-key" in text
    assert "RADAGENT_AGENTIC_MAX_TURNS=12" in text
    assert "RADAGENT_AGENTIC_HISTORY_CHARS=36000" in text
    assert config.tiers[ModelTier.LITE.value].model_name == "mimo-v2.5"
    assert config.tiers[ModelTier.PRO.value].api_key_configured is True
    assert config.agentic_repair_max_turns == 12
    assert config.agentic_repair_history_chars == 36000
    assert "provider" not in config.tiers[ModelTier.PRO.value].model_dump()
    assert events[-1].event_type == "model_config_updated"


@pytest.mark.asyncio
async def test_service_model_health_uses_configured_tiers_without_leaking_secret(
    tmp_path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "RADAGENT_MODEL_BASE_URL=https://model.example.test/v1",
                "RADAGENT_API_KEY=secret-value",
                "RADAGENT_MODEL_LITE=lite-model",
                "RADAGENT_MODEL_PRO=pro-model",
                "RADAGENT_MODEL_MAX=max-model",
            ]
        ),
        encoding="utf-8",
    )
    for name in (
        "RADAGENT_MODEL_BASE_URL",
        "RADAGENT_API_KEY",
        "RADAGENT_MODEL_LITE",
        "RADAGENT_MODEL_PRO",
        "RADAGENT_MODEL_MAX",
    ):
        monkeypatch.delenv(name, raising=False)

    calls: list[ModelTier] = []

    async def fake_probe(tier: ModelTier) -> ModelCallResult:
        calls.append(tier)
        return ModelCallResult(
            task=ModelTask.SIMPLE_EXTRACTION,
            tier=tier,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name=f"{tier.value}-model",
            content="OK",
            latency_ms=12.25,
        )

    service = RadAgentAppService(workspace_root=tmp_path, env_path=env_file)
    monkeypatch.setattr(service, "_probe_model_health_tier", fake_probe)

    report = await service.test_model_health()

    assert calls == [ModelTier.LITE, ModelTier.PRO, ModelTier.MAX]
    assert report.tiers["pro"].status == "ok"
    assert report.tiers["pro"].latency_ms == 12.25
    assert report.tiers["pro"].response_preview == "OK"
    assert "secret-value" not in report.model_dump_json()


@pytest.mark.asyncio
async def test_service_model_health_skips_missing_api_key(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "RADAGENT_MODEL_BASE_URL=https://model.example.test/v1",
                "RADAGENT_MODEL_PRO=pro-model",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("RADAGENT_API_KEY", raising=False)
    service = RadAgentAppService(workspace_root=tmp_path, env_path=env_file)

    report = await service.test_model_health()

    assert report.tiers["pro"].status == "skipped"
    assert report.tiers["pro"].error == "Missing API key env: RADAGENT_API_KEY"


@pytest.mark.asyncio
async def test_service_model_health_times_out_one_slow_tier(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "RADAGENT_MODEL_BASE_URL=https://model.example.test/v1",
                "RADAGENT_API_KEY=secret-value",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("RADAGENT_API_KEY", raising=False)
    service = RadAgentAppService(workspace_root=tmp_path, env_path=env_file)

    async def slow_probe(tier: ModelTier) -> ModelCallResult:
        await asyncio.sleep(1)
        return ModelCallResult(
            task=ModelTask.SIMPLE_EXTRACTION,
            tier=tier,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name=tier.value,
            content="OK",
        )

    monkeypatch.setattr(service, "_probe_model_health_tier", slow_probe)

    report = await service.test_model_health(per_tier_timeout_s=0.01)

    assert report.tiers["pro"].status == "error"
    assert "timed out" in report.tiers["pro"].error


def test_service_background_continue_starts_once_and_emits_events(tmp_path, monkeypatch) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    service.state["job_id"] = "job-1"
    service.store.upsert_job(job_id="job-1", user_query="simulate")
    calls: list[str] = []
    started = threading.Event()
    release = threading.Event()

    async def fake_run_until_blocked() -> None:
        calls.append("run")
        started.set()
        release.wait(timeout=5)

    monkeypatch.setattr(service, "run_until_blocked", fake_run_until_blocked)

    assert service.continue_in_background(reason="retry") is True
    thread = service._background_continue_thread
    assert thread is not None
    assert started.wait(timeout=5) is True
    assert service.continue_in_background(reason="retry") is False
    release.set()
    thread.join(timeout=5)

    assert calls == ["run"]
    assert [event.event_type for event in service.recent_events()] == [
        "workflow_continue_queued",
        "workflow_continue_started",
        "workflow_continue_busy",
        "workflow_continue_finished",
    ]


def test_service_background_continue_reports_failed_status(tmp_path, monkeypatch) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    service.state["job_id"] = "job-failed"
    service.store.upsert_job(job_id="job-failed", user_query="simulate")
    service.current_phase_idx = PIPELINE_PHASES.index("g4_codegen")

    async def fake_run_until_blocked() -> object:
        service.state["termination_reason"] = "g4_codegen status is failed"
        return service.get_status()

    monkeypatch.setattr(service, "run_until_blocked", fake_run_until_blocked)

    assert service.continue_in_background(reason="human_confirmation_approved") is True
    thread = service._background_continue_thread
    assert thread is not None
    thread.join(timeout=5)

    events = service.recent_events()
    assert events[-1].event_type == "workflow_continue_failed"
    assert events[-1].summary == "g4_codegen status is failed"
    assert events[-1].payload["reason"] == "g4_codegen status is failed"
    assert events[-1].payload["trigger"] == "human_confirmation_approved"
    assert events[-1].payload["status"] == "failed"
    assert not any(event.event_type == "workflow_continue_finished" for event in events)


def test_completed_passed_termination_reason_keeps_completed_status(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    service.state = {
        "job_id": "job-completed",
        "user_query": "simulate",
        "termination_reason": "completed_passed",
        "errors": [],
    }
    service.current_phase_idx = len(PIPELINE_PHASES)
    service.completed_phases = list(PIPELINE_PHASES)

    status = service.get_status()

    assert status.status == "completed"
    assert status.current_phase == ""
    assert status.key_statuses["termination_reason"] == "completed_passed"


def test_background_continue_completed_passed_reports_finished(tmp_path, monkeypatch) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    service.state = {
        "job_id": "job-completed",
        "user_query": "simulate",
        "errors": [],
    }
    service.store.upsert_job(job_id="job-completed", user_query="simulate")

    async def fake_run_until_blocked() -> object:
        service.state["termination_reason"] = "completed_passed"
        service.current_phase_idx = len(PIPELINE_PHASES)
        service.completed_phases = list(PIPELINE_PHASES)
        return service.get_status()

    monkeypatch.setattr(service, "run_until_blocked", fake_run_until_blocked)

    assert service.continue_in_background(reason="requirements_review_approved") is True
    thread = service._background_continue_thread
    assert thread is not None
    thread.join(timeout=5)

    events = service.recent_events()
    assert events[-1].event_type == "workflow_continue_finished"
    assert events[-1].payload["reason"] == "requirements_review_approved"
    assert not any(
        event.event_type == "workflow_continue_failed"
        and event.payload.get("reason") == "completed_passed"
        for event in events
    )


def test_resume_job_normalizes_progress_and_can_clear_previous_failure(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    job_id = "resume-progress"
    state = {
        "job_id": job_id,
        "user_query": "simulate",
        "execution_mode": "strict",
        "run_mode": "strict",
        "job_workspace": str(tmp_path / "jobs" / job_id),
        "g4_codegen_status": "failed",
        "patch_status": "failed",
        "validation_status": "blocked",
        "termination_reason": "validation status is blocked",
        "errors": [
            "SQLite objects created in a thread can only be used in that same thread.",
            "validation status is blocked",
        ],
    }
    service.store.upsert_job(job_id=job_id, user_query="simulate")
    service.store.save_state_snapshot(
        job_id=job_id,
        state=state,
        completed_phases=[
            "prepare_workspace",
            "context",
            "task_planning",
            "g4_modeling",
            "human_confirmation",
            "g4_codegen",
            "patch",
        ],
        phase="g4_codegen",
        current_phase_idx=5,
        status="failed",
    )

    status = service.resume_job(job_id, clear_failure=True)

    assert status.current_phase == "gate"
    assert status.current_phase_idx == PIPELINE_PHASES.index("gate")
    assert status.status == "running"
    assert status.state["current_node"] == "gate_subgraph"
    assert "termination_reason" not in status.key_statuses
    assert status.state.get("errors") == []
    assert status.key_statuses["g4_codegen_status"] == "passed"
    assert status.key_statuses["patch_status"] == "applied"


def test_resume_job_maps_legacy_human_confirmation_progress_to_codegen(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    job_id = "legacy-human-confirmation-progress"
    state = {
        "job_id": job_id,
        "user_query": "simulate",
        "execution_mode": "strict",
        "run_mode": "strict",
        "job_workspace": str(tmp_path / "jobs" / job_id),
        "confirmation_status": "approved",
        "human_confirmation_required": False,
        "current_node": "human_confirmation_subgraph",
        "errors": [],
    }
    service.store.upsert_job(job_id=job_id, user_query="simulate")
    service.store.save_state_snapshot(
        job_id=job_id,
        state=state,
        completed_phases=[
            "prepare_workspace",
            "context",
            "task_planning",
            "requirements_review",
            "g4_modeling",
            "human_confirmation",
        ],
        phase="human_confirmation",
        current_phase_idx=6,
        status="running",
    )

    status = service.resume_job(job_id)

    assert status.current_phase == "g4_codegen"
    assert status.current_phase_idx == PIPELINE_PHASES.index("g4_codegen")
    assert "human_confirmation" not in status.completed_phases
    assert "requirements_review" in status.completed_phases
    assert status.state["current_node"] == "g4_codegen_subgraph"


@pytest.mark.asyncio
async def test_submit_confirmation_approve_is_idempotent_after_gate(tmp_path, monkeypatch) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    service.state = {
        "job_id": "approved-job",
        "confirmation_status": "approved",
        "raw_human_response": {"user_decision": "approve"},
    }
    service.current_phase_idx = PIPELINE_PHASES.index("gate")
    service.completed_phases = [
        "prepare_workspace",
        "context",
        "task_planning",
        "g4_modeling",
        "human_confirmation",
        "g4_codegen",
        "patch",
    ]
    service.store.upsert_job(job_id="approved-job", user_query="simulate")

    async def fail_run_phase(phase: str):
        raise AssertionError(f"run_phase should not be called for {phase}")

    monkeypatch.setattr(service, "run_phase", fail_run_phase)

    status = await service.submit_confirmation(
        {"user_decision": "approve", "feedback": "approve"},
        auto_continue=False,
    )

    assert status.current_phase == "gate"
    assert status.current_phase_idx == PIPELINE_PHASES.index("gate")
    assert service.state["confirmation_status"] == "approved"
    assert service.recent_events()[-1].event_type == "human_confirmation_already_approved"


def test_status_advances_stale_human_confirmation_current_node_after_approval(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    service.state = {
        "job_id": "approved-node-job",
        "user_query": "simulate",
        "confirmation_status": "approved",
        "human_confirmation_required": False,
        "current_node": "human_confirmation_subgraph",
    }
    service.current_phase_idx = PIPELINE_PHASES.index("g4_codegen")
    service.completed_phases = [
        "prepare_workspace",
        "context",
        "task_planning",
        "g4_modeling",
        "human_confirmation",
    ]

    status = service.get_status()

    assert status.current_phase == "g4_codegen"
    assert status.state["current_node"] == "g4_codegen_subgraph"


def test_service_rejects_provider_in_frontend_model_config(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path, env_path=tmp_path / ".env")

    with pytest.raises(ValidationError):
        service.update_model_config({"provider": "mock"})


def test_service_status_ignores_retired_blocked_visual_review_gate(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    job_id = "job_visual_blocked"
    gate_dir = tmp_path / "jobs" / job_id / STAGE_GATE_VALIDATION
    gate_dir.mkdir(parents=True)
    gate_path = gate_dir / "gate_results.json"
    gate_path.write_text(
        '[{"gate_id": 21, "name": "G4 Visual Review", "status": "blocked"}]',
        encoding="utf-8",
    )
    service.state = {
        "job_id": job_id,
        "gate_results_path": str(gate_path),
        "validation_status": "blocked",
    }

    status = service.get_status()

    assert status.status == "running"
    assert status.needs_confirmation is False


def test_gate_results_hide_retired_visual_review_gate(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    job_id = "job_visual_results"
    gate_dir = tmp_path / "jobs" / job_id / STAGE_GATE_VALIDATION
    gate_dir.mkdir(parents=True)
    gate_path = gate_dir / "gate_results.json"
    gate_path.write_text(
        """
        [
          {"gate_id": 20, "name": "Credibility/Plausibility Assessment", "status": "pass"},
          {"gate_id": 21, "name": "G4 Visual Review", "status": "blocked"}
        ]
        """,
        encoding="utf-8",
    )
    service.state = {"job_id": job_id, "gate_results_path": str(gate_path)}

    results = service.get_gate_results()

    assert [gate["gate_id"] for gate in results] == [20]


@pytest.mark.asyncio
async def test_run_simulation_runs_visual_100_before_requested_events(
    tmp_path,
    monkeypatch,
) -> None:
    events = []
    service = RadAgentAppService(workspace_root=tmp_path, event_callback=events.append)
    job_id = "job_split_sim"
    project_dir = tmp_path / "jobs" / job_id / "06_patch" / "geant4_project"
    executable = project_dir / "build" / "sim"
    (project_dir / "macros").mkdir(parents=True)
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    executable.chmod(0o755)
    (project_dir / "macros" / "run.mac").write_text(
        "/run/initialize\n/run/beamOn 10\n",
        encoding="utf-8",
    )
    service.state = {
        "job_id": job_id,
        "generated_code_dir": str(project_dir),
        "_executable_path": str(executable),
    }
    service.store.upsert_job(
        job_id=job_id,
        user_query="split simulation",
        job_workspace=str(tmp_path / "jobs" / job_id),
    )

    calls: list[dict[str, object]] = []

    class FakeRunner:
        geant4_available = True

        async def simulate(
            self,
            executable: str,
            macro: str | None = None,
            events: int = 100,
            threads: int = 1,
            output_dir: str | None = None,
            job_id: str = "unknown",
        ) -> dict[str, object]:
            assert macro is not None
            assert output_dir is not None
            calls.append(
                {
                    "events": events,
                    "macro": Path(macro).name,
                    "macro_text": Path(macro).read_text(encoding="utf-8"),
                    "output_dir": output_dir,
                    "job_id": job_id,
                }
            )
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            return {
                "success": True,
                "process_success": True,
                "output_dir": output_dir,
                "log": f"BeamOn completed {events} events",
                "errors": "",
            }

        def materialize_output_contract(
            self,
            *,
            output_dir: str,
            executable_dir: str,
            job_id: str,
            events: int,
            sim: dict[str, object],
        ) -> None:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / "g4_summary.json").write_text(
                f'{{"job_id": "{job_id}", "events_requested": {events}}}',
                encoding="utf-8",
            )
            (out / "event_table.csv").write_text(
                "EventID,edep_MeV,dose_Gy\n0,1.0,0.01\n",
                encoding="utf-8",
            )
            (out / "edep_3d.csv").write_text(
                "x_mm,y_mm,z_mm,edep_MeV\n0,0,0,1.0\n",
                encoding="utf-8",
            )
            (out / "dose_3d.csv").write_text(
                "x_mm,y_mm,z_mm,dose_Gy\n0,0,0,0.01\n",
                encoding="utf-8",
            )
            (out / "provenance.json").write_text(
                '{"source": "fake-runner"}',
                encoding="utf-8",
            )
            if events == 100:
                (out / "particle_tracks.json").write_text(
                    '{"events": 100, "tracks": [{"event_id": 0, "track_id": 1, '
                    '"particle": "proton", "points_mm": [[0, 0, -1], [0, 0, 1]]}]}',
                    encoding="utf-8",
                )
                (out / "energy_deposits.json").write_text(
                    '{"deposits": [{"event_id": 0, "track_id": 1, '
                    '"position_mm": [0, 0, 0], "edep_MeV": 1.0}]}',
                    encoding="utf-8",
                )
                (out / "geometry_view.json").write_text(
                    '{"components": [{"id": "detector", "shape": "box", '
                    '"size_mm": [1, 1, 1], "position_mm": [0, 0, 0]}]}',
                    encoding="utf-8",
                )

    monkeypatch.setattr("agent_core.tools.geant4_runner.Geant4Runner", FakeRunner)

    result = await service.run_simulation(events=250)

    assert result.success is True
    assert result.visual_events == 100
    assert result.events == 250
    assert [call["events"] for call in calls] == [100, 250]
    assert "/run/beamOn 100" in str(calls[0]["macro_text"])
    assert "/run/beamOn 250" in str(calls[1]["macro_text"])
    assert Path(str(calls[0]["output_dir"])).name == "visual_100"
    assert Path(service.state["_visual_output_dir"]).name == "visual_100"
    assert Path(service.state["visual_particle_tracks_path"]).is_file()
    assert service.state["_sim_output_dir"] == str(calls[1]["output_dir"])
    assert [event.event_type for event in events if event.event_type.startswith("simulation_")] == [
        "simulation_visual_started",
        "simulation_visual_finished",
        "simulation_started",
        "simulation_finished",
    ]


@pytest.mark.asyncio
async def test_start_job_persists_approved_briefing_context(tmp_path, monkeypatch) -> None:
    async def fake_run_until_blocked() -> object:
        return service.get_status()

    service = RadAgentAppService(workspace_root=tmp_path)
    monkeypatch.setattr(service, "run_until_blocked", fake_run_until_blocked)
    briefing_context = {
        "understanding": "User wants a silicon detector simulation.",
        "final_query": "Build a Geant4 silicon detector deposited-energy simulation.",
        "task_summary_short": {
            "zh": "硅探测器沉积能量仿真",
            "en": "Silicon detector deposited-energy simulation",
        },
        "context_window_stats": {
            "history_usage_ratio": 0.61,
            "threshold": 0.75,
            "state": "normal",
            "cycle": 1,
            "context_window_tokens": 200_000,
        },
        "approval_request": {
            "requires_human_approval": True,
            "summary": "Start silicon detector simulation.",
            "risks": ["Validate physics list."],
        },
        "draft_plan": {"objective": "Measure deposited energy."},
        "assumptions": ["Default world is acceptable."],
        "risks": ["Validate physics list."],
    }

    await service.start_job(
        "Build a Geant4 silicon detector deposited-energy simulation.",
        briefing_context=briefing_context,
    )

    assert service.state["copilot_briefing"]["final_query"] == briefing_context["final_query"]
    assert service.state["copilot_briefing"]["approved"] is True
    assert service.state["raw_human_response"] == {
        "user_decision": "approve",
        "edits": [],
        "user_notes": "Approved before pipeline start through RadAgent briefing.",
    }
    assert service.state["task_summary_short"]["zh"] == "硅探测器沉积能量仿真"
    assert service.state["copilot_context_usage"]["history_usage_ratio"] == 0.61
    context = service.get_workflow_context()
    memory = {item.key: item for item in context.memory}
    assert "copilot_briefing" in memory
    assert "silicon detector" in memory["copilot_briefing"].summary
    assert memory["copilot_briefing"].payload["approval_request"]["requires_human_approval"]


@pytest.mark.asyncio
async def test_preapproved_job_does_not_block_after_g4_modeling_requires_confirmation(
    tmp_path,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_preapproved"
    job_dir = tmp_path / "jobs" / job_id
    job_dir.mkdir(parents=True)
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "build detector",
        "job_workspace": str(job_dir),
        "workspace_root": str(tmp_path),
        "execution_mode": "test",
        "run_mode": "test",
        "errors": [],
        "raw_human_response": {
            "user_decision": "approve",
            "edits": [],
            "user_notes": "Approved before pipeline start through RadAgent briefing.",
        },
    }
    service.current_phase_idx = PIPELINE_PHASES.index("g4_modeling")

    async def g4_modeling(state: dict) -> dict:
        return {"human_confirmation_required": True}

    async def no_op(state: dict) -> dict:
        return {}

    service._subgraph_nodes = {
        "g4_modeling": g4_modeling,
        "g4_codegen": no_op,
        "patch": no_op,
        "gate": no_op,
        "artifact": no_op,
        "report": no_op,
    }

    status = await service.run_until_blocked()

    assert status.status == "completed"
    assert "human_confirmation" not in status.completed_phases
    assert "g4_codegen" in status.completed_phases
    assert [
        event.event_type
        for event in service.recent_events()
        if event.event_type == "human_confirmation_required"
    ] == []


@pytest.mark.asyncio
async def test_patch_phase_auto_builds_and_runs_visual_simulation_before_gate(
    tmp_path,
    monkeypatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_patch_auto_visual"
    project_dir = tmp_path / "jobs" / job_id / "06_patch" / "geant4_project"
    project_dir.mkdir(parents=True)
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "build detector",
        "job_workspace": str(tmp_path / "jobs" / job_id),
        "workspace_root": str(tmp_path),
        "generated_code_dir": str(project_dir),
        "execution_mode": "test",
        "run_mode": "test",
        "errors": [],
    }
    service.store.upsert_job(
        job_id=job_id,
        user_query="build detector",
        job_workspace=str(tmp_path / "jobs" / job_id),
    )
    service.current_phase_idx = PIPELINE_PHASES.index("patch")

    async def patch_node(state: dict) -> dict:
        return {"patch_status": "applied"}

    service._subgraph_nodes = {"patch": patch_node}
    calls: list[str] = []

    async def fake_build_generated_code(*, threads: int = 4):
        calls.append(f"build:{threads}")
        executable = project_dir / "build" / "sim"
        executable.parent.mkdir(parents=True)
        executable.write_text("", encoding="utf-8")
        executable.chmod(0o755)
        service.state["_executable_path"] = str(executable)
        from agent_core.app.schemas import BuildResult

        return BuildResult(success=True, executable_path=str(executable))

    async def fake_run_simulation(*, events: int = 1000):
        calls.append(f"simulate:{events}")
        visual_dir = tmp_path / "jobs" / job_id / "output" / "visual_100"
        visual_dir.mkdir(parents=True)
        tracks = visual_dir / "particle_tracks.json"
        tracks.write_text('{"tracks": []}', encoding="utf-8")
        service.state["_visual_output_dir"] = str(visual_dir)
        service.state["visual_particle_tracks_path"] = str(tracks)
        from agent_core.app.schemas import SimulationResult

        return SimulationResult(
            success=True,
            events=events,
            visual_events=100,
            visual_success=True,
            visual_output_dir=str(visual_dir),
        )

    monkeypatch.setattr(service, "build_generated_code", fake_build_generated_code)
    monkeypatch.setattr(service, "run_simulation", fake_run_simulation)

    result = await service.run_phase("patch")

    assert result.success is True
    assert calls == ["build:4", "simulate:1000"]
    assert service.state["auto_visualization_status"] == "ready"
    assert Path(service.state["visual_particle_tracks_path"]).is_file()
    assert service.current_phase_idx == PIPELINE_PHASES.index("gate")


def test_get_visualization_payload_ignores_stale_visual_run_after_model_regeneration(
    tmp_path: Path,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_stale_visual"
    job_dir = tmp_path / "jobs" / job_id
    visual_dir = job_dir / "07_gate_validation" / "g4_output_package" / "visual_100"
    visual_dir.mkdir(parents=True)
    (visual_dir / "geometry_view.json").write_text(
        json.dumps(
            {
                "components": [
                    {
                        "id": "old_geometry",
                        "shape": "box",
                        "material": "G4_WATER",
                        "size_mm": [1, 1, 1],
                        "position_mm": [0, 0, 0],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (visual_dir / "particle_tracks.json").write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "event_id": 0,
                        "track_id": 1,
                        "particle": "gamma",
                        "points_mm": [[0, 0, -1], [0, 0, 1]],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (visual_dir / "energy_deposits.json").write_text(
        json.dumps(
            {
                "deposits": [
                    {
                        "event_id": 0,
                        "track_id": 1,
                        "volume": "old_geometry",
                        "position_mm": [0, 0, 0],
                        "edep_MeV": 0.1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    for path in visual_dir.iterdir():
        os.utime(path, (1000, 1000))
    os.utime(visual_dir, (1000, 1000))

    model_ir_path = job_dir / "03_model_ir" / "g4_model_ir.json"
    model_ir_path.parent.mkdir(parents=True)
    model_ir_path.write_text(
        json.dumps(
            {
                "global_units": {"length": "mm"},
                "components": [
                    {
                        "component_id": "one_loop_robot",
                        "display_name": "One-loop inspection robot",
                        "geometry_type": "box",
                        "material_id": "G4_Fe",
                        "dimensions": {"x": 100, "y": 100, "z": 200},
                        "placement": {"position": [0, 0, 0]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    os.utime(model_ir_path, (2000, 2000))

    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "workspace_root": str(tmp_path),
        "job_workspace": str(job_dir),
        "_visual_output_dir": str(visual_dir),
        "visual_geometry_view_path": str(visual_dir / "geometry_view.json"),
        "visual_particle_tracks_path": str(visual_dir / "particle_tracks.json"),
        "visual_energy_deposits_path": str(visual_dir / "energy_deposits.json"),
        "auto_visualization_status": "ready",
        "g4_model_ir_path": str(model_ir_path),
    }

    payload = service.get_visualization_payload(job_id)

    assert payload["status"] == "partial"
    assert payload["source"]["output_dir"] == ""
    assert payload["source"]["stale_output_dir"] == str(visual_dir)
    assert payload["geometry"]["components"][0]["id"] == "one_loop_robot"
    assert payload["tracks"] == []
    assert payload["deposits"] == []
    assert any("stale" in warning for warning in payload["warnings"])


@pytest.mark.asyncio
async def test_patch_phase_reruns_auto_visualization_when_previous_visual_output_is_stale(
    tmp_path,
    monkeypatch,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_patch_rerun_stale_visual"
    job_dir = tmp_path / "jobs" / job_id
    project_dir = job_dir / "06_patch" / "geant4_project"
    project_dir.mkdir(parents=True)
    proposed_patch = job_dir / "05_codegen" / "proposed_patch.json"
    proposed_patch.parent.mkdir(parents=True)
    proposed_patch.write_text("{}", encoding="utf-8")
    visual_dir = job_dir / "07_gate_validation" / "g4_output_package" / "visual_100"
    visual_dir.mkdir(parents=True)
    (visual_dir / "geometry_view.json").write_text('{"components": []}', encoding="utf-8")
    os.utime(visual_dir / "geometry_view.json", (1000, 1000))
    os.utime(visual_dir, (1000, 1000))
    os.utime(proposed_patch, (2000, 2000))
    os.utime(project_dir, (2000, 2000))
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "build detector",
        "job_workspace": str(job_dir),
        "workspace_root": str(tmp_path),
        "generated_code_dir": str(project_dir),
        "proposed_patch_path": str(proposed_patch),
        "_visual_output_dir": str(visual_dir),
        "auto_visualization_status": "ready",
        "execution_mode": "test",
        "run_mode": "test",
        "errors": [],
    }
    service.store.upsert_job(
        job_id=job_id,
        user_query="build detector",
        job_workspace=str(job_dir),
    )
    service.current_phase_idx = PIPELINE_PHASES.index("patch")

    async def patch_node(state: dict) -> dict:
        return {"patch_status": "applied"}

    service._subgraph_nodes = {"patch": patch_node}
    calls: list[str] = []

    async def fake_build_generated_code(*, threads: int = 4):
        calls.append(f"build:{threads}")
        executable = project_dir / "build" / "sim"
        executable.parent.mkdir(parents=True)
        executable.write_text("", encoding="utf-8")
        executable.chmod(0o755)
        service.state["_executable_path"] = str(executable)
        from agent_core.app.schemas import BuildResult

        return BuildResult(success=True, executable_path=str(executable))

    async def fake_run_simulation(*, events: int = 1000):
        calls.append(f"simulate:{events}")
        next_visual_dir = job_dir / "output" / "visual_100"
        next_visual_dir.mkdir(parents=True)
        tracks = next_visual_dir / "particle_tracks.json"
        tracks.write_text('{"tracks": []}', encoding="utf-8")
        service.state["_visual_output_dir"] = str(next_visual_dir)
        service.state["visual_particle_tracks_path"] = str(tracks)
        from agent_core.app.schemas import SimulationResult

        return SimulationResult(
            success=True,
            events=events,
            visual_events=100,
            visual_success=True,
            visual_output_dir=str(next_visual_dir),
        )

    monkeypatch.setattr(service, "build_generated_code", fake_build_generated_code)
    monkeypatch.setattr(service, "run_simulation", fake_run_simulation)

    result = await service.run_phase("patch")

    assert result.success is True
    assert calls == ["build:4", "simulate:1000"]
    assert service.state["auto_visualization_status"] == "ready"
    assert service.state["_visual_output_dir"] == str(job_dir / "output" / "visual_100")


@pytest.mark.asyncio
async def test_run_until_blocked_routes_patch_rejection_back_to_codegen(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_patch_repair_route"
    job_dir = tmp_path / "jobs" / job_id
    job_dir.mkdir(parents=True)
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "build detector",
        "job_workspace": str(job_dir),
        "workspace_root": str(tmp_path),
        "execution_mode": "test",
        "run_mode": "test",
        "g4_codegen_status": "passed",
        "auto_visualization_status": "ready",
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("patch")
    service.completed_phases = [
        "prepare_workspace",
        "context",
        "task_planning",
        "requirements_review",
        "g4_modeling",
        "g4_codegen",
    ]

    patch_calls = 0
    codegen_contexts: list[dict] = []

    async def patch(state: dict) -> dict:
        nonlocal patch_calls
        patch_calls += 1
        if patch_calls == 1:
            return {
                "patch_status": "rejected",
                "patch_retry_count": 1,
                "runtime_failure_context": {
                    "source": "patch_review_retry",
                    "errors": ["REJECT (red zone): include/main.cc"],
                },
            }
        return {"patch_status": "applied"}

    async def g4_codegen(state: dict) -> dict:
        codegen_contexts.append(dict(state.get("runtime_failure_context", {})))
        return {
            "g4_codegen_status": "passed",
            "proposed_patch_path": str(job_dir / "05_codegen" / "proposed_patch.json"),
            "generated_code_dir": str(job_dir / "06_patch" / "geant4_project"),
        }

    async def gate(state: dict) -> dict:
        return {"validation_status": "passed", "failed_gates": []}

    async def artifact(state: dict) -> dict:
        return {"artifact_status": "collected"}

    async def report(state: dict) -> dict:
        return {}

    service._subgraph_nodes = {
        "g4_codegen": g4_codegen,
        "patch": patch,
        "gate": gate,
        "artifact": artifact,
        "report": report,
    }

    status = await service.run_until_blocked()

    assert status.status == "completed"
    assert patch_calls == 2
    assert codegen_contexts
    assert codegen_contexts[0]["source"] == "patch_review_retry"
    assert "include/main.cc" in codegen_contexts[0]["errors"][0]


@pytest.mark.asyncio
async def test_patch_phase_reports_auto_visualization_build_setup_failure(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_patch_auto_visual_missing_dir"
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "build detector",
        "job_workspace": str(tmp_path / "jobs" / job_id),
        "workspace_root": str(tmp_path),
        "execution_mode": "test",
        "run_mode": "test",
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("patch")

    async def patch_node(state: dict) -> dict:
        return {"patch_status": "applied"}

    service._subgraph_nodes = {"patch": patch_node}

    result = await service.run_phase("patch")

    assert result.success is False
    assert result.status.key_statuses["patch_status"] == "failed"
    assert result.status.state["auto_visualization_status"] == "failed"
    assert any("No generated code directory" in error for error in result.status.state["errors"])


@pytest.mark.asyncio
async def test_run_phase_stops_when_codegen_status_is_failed(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_codegen_failed"
    job_dir = tmp_path / "jobs" / job_id
    job_dir.mkdir(parents=True)
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "build detector",
        "job_workspace": str(job_dir),
        "workspace_root": str(tmp_path),
        "execution_mode": "test",
        "run_mode": "test",
        "errors": [],
        "auto_visualization_status": "ready",
        "raw_human_response": {"user_decision": "approve", "feedback": "approve"},
    }
    service.current_phase_idx = PIPELINE_PHASES.index("g4_codegen")

    async def failed_codegen(state: dict) -> dict:
        return {
            "g4_codegen_status": "failed",
            "errors": ["runtime_app did not pass layer gate"],
        }

    service._subgraph_nodes = {"g4_codegen": failed_codegen}

    result = await service.run_phase("g4_codegen")

    assert result.success is False
    assert service.current_phase_idx == PIPELINE_PHASES.index("g4_codegen")
    assert "g4_codegen" not in service.completed_phases
    assert service.state["termination_reason"] == "g4_codegen status is failed"
    assert service.recent_events()[-1].event_type == "phase_failed"
    assert result.status.status == "failed"


@pytest.mark.asyncio
async def test_run_until_blocked_routes_failed_gate_to_retry_phase(
    tmp_path,
) -> None:
    events = []
    service = RadAgentAppService(workspace_root=tmp_path, event_callback=events.append)
    project = service.current_project()
    job_id = "job_gate_failed"
    job_dir = tmp_path / "jobs" / job_id
    job_dir.mkdir(parents=True)
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "build detector",
        "job_workspace": str(job_dir),
        "workspace_root": str(tmp_path),
        "execution_mode": "test",
        "run_mode": "test",
        "errors": [],
        "auto_visualization_status": "ready",
        "raw_human_response": {"user_decision": "approve", "feedback": "approve"},
    }
    service.current_phase_idx = PIPELINE_PHASES.index("gate")

    gate_calls = 0

    async def gate(state: dict) -> dict:
        nonlocal gate_calls
        gate_calls += 1
        if gate_calls == 1:
            return {"validation_status": "failed", "failed_gates": [{"gate_id": 1}]}
        return {"validation_status": "passed", "failed_gates": []}

    async def fixed_planning(state: dict) -> dict:
        return {"task_planning_status": "passed", "simulation_scope": ["geant4"]}

    async def requirements_review(state: dict) -> dict:
        return {
            "requirements_review_status": "approved",
            "confirmed_requirement_plan_path": "confirmed_requirement_plan.json",
            "human_confirmation_required": False,
        }

    async def g4_modeling(state: dict) -> dict:
        return {"g4_modeling_status": "passed", "human_confirmation_required": False}

    async def human_confirmation(state: dict) -> dict:
        return {
            "confirmation_status": "approved",
            "human_confirmation_required": False,
            "unconfirmed_assumptions_count": 0,
        }

    async def g4_codegen(state: dict) -> dict:
        return {"g4_codegen_status": "passed"}

    async def patch(state: dict) -> dict:
        return {"patch_status": "applied"}

    async def artifact(state: dict) -> dict:
        return {"artifact_status": "collected"}

    async def no_op(state: dict) -> dict:
        return {}

    service._subgraph_nodes = {
        "gate": gate,
        "task_planning": fixed_planning,
        "requirements_review": requirements_review,
        "g4_modeling": g4_modeling,
        "human_confirmation": human_confirmation,
        "g4_codegen": g4_codegen,
        "patch": patch,
        "artifact": artifact,
        "report": no_op,
    }

    status = await service.run_until_blocked()

    assert status.status == "completed"
    assert gate_calls == 2
    assert "task_planning" in status.completed_phases
    assert "gate" in status.completed_phases
    assert status.key_statuses["validation_status"] == "passed"
    event_types = [event.event_type for event in service.recent_events()]
    assert "phase_retry_routed" in event_types
    retry_event = next(event for event in events if event.event_type == "phase_retry_routed")
    assert retry_event.payload["from_phase"] == "gate"
    assert retry_event.payload["target_phase"] == "task_planning"
    assert retry_event.payload["target_node"] == "task_planning_subgraph"


@pytest.mark.asyncio
async def test_run_until_blocked_stops_on_blocked_context_instead_of_continuing(
    tmp_path,
) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    project = service.current_project()
    job_id = "job_context_blocked"
    job_dir = tmp_path / "jobs" / job_id
    job_dir.mkdir(parents=True)
    service.state = {
        "job_id": job_id,
        "project_id": str(project["id"]),
        "user_query": "build detector",
        "job_workspace": str(job_dir),
        "workspace_root": str(tmp_path),
        "execution_mode": "test",
        "run_mode": "test",
        "errors": [],
    }
    service.current_phase_idx = PIPELINE_PHASES.index("context")

    async def blocked_context(state: dict) -> dict:
        return {"context_decision": "block_no_context"}

    async def fail_if_called(state: dict) -> dict:
        raise AssertionError("task planning should not run after blocked context")

    service._subgraph_nodes = {
        "context": blocked_context,
        "task_planning": fail_if_called,
    }

    status = await service.run_until_blocked()

    assert status.status == "failed"
    assert status.current_phase == "context"
    assert "context" not in status.completed_phases
    assert service.state["termination_reason"] == "context status is block_no_context"
    event_types = [event.event_type for event in service.recent_events()]
    assert "phase_failed" in event_types
    assert "job_finished" not in event_types
