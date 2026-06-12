from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from agent_core.chat.briefing import ApprovedPlanSummarizer, SimulationBriefingPlanner
from agent_core.models.schemas import ModelTask, ModelTier


def _ready_briefing_payload() -> dict[str, Any]:
    return {
        "status": "ready_for_approval",
        "understanding": "用户要做能量分辨率和 n/gamma 甄别仿真。",
        "questions": [],
        "recommendations": ["先用小事件数验证 scoring。"],
        "draft_plan": {"objective": "Study energy resolution and n/gamma PSD."},
        "missing_critical_fields": [],
        "assumptions": ["使用默认探测器几何占位。"],
        "risks": ["材料和光产额会影响分辨率。"],
        "final_query": "Build an energy-resolution and n/gamma discrimination simulation.",
        "proposed_command": {
            "name": "start_job",
            "args": {
                "query": "Build an energy-resolution and n/gamma discrimination simulation.",
                "run_mode": "strict",
            },
            "risk": "write",
            "status": "pending",
            "summary": "Start after human approval.",
        },
        "approval_request": {
            "requires_human_approval": True,
            "summary": "Start energy-resolution simulation.",
            "risks": ["Validate detector response assumptions."],
        },
    }


@pytest.mark.asyncio
async def test_briefing_planner_uses_single_lite_extraction_call() -> None:
    calls: list[dict[str, Any]] = []

    class _Gateway:
        async def call(self, **kwargs: Any) -> Any:
            calls.append(kwargs)

            class _Result:
                error = None
                parsed_json = {
                    "status": "ready_for_approval",
                    "understanding": "User wants a Geant4 detector simulation.",
                    "questions": [],
                    "recommendations": ["Use a quick validation run before production."],
                    "draft_plan": {
                        "objective": "Measure deposited energy.",
                        "simulation_scope": ["geant4"],
                        "geometry": {"world": "air box"},
                        "materials": [{"name": "Silicon"}],
                        "source": {"particle": "proton", "energy": "10 MeV"},
                        "physics": {"physics_list": "FTFP_BERT"},
                        "scoring": [{"quantity": "edep"}],
                        "run_plan": {"validation_events": 100, "production_events": 1000},
                        "codegen_constraints": ["Keep modules explicit."],
                    },
                    "missing_critical_fields": [],
                    "assumptions": ["World size can be derived from detector size."],
                    "risks": ["Physics list may need validation."],
                    "final_query": "Build a Geant4 detector simulation for deposited energy.",
                    "proposed_command": {
                        "name": "start_job",
                        "args": {
                            "query": "Build a Geant4 detector simulation for deposited energy.",
                            "run_mode": "strict",
                        },
                        "risk": "write",
                        "status": "pending",
                        "summary": "Start the approved simulation workflow.",
                    },
                    "approval_request": {
                        "requires_human_approval": True,
                        "summary": "Ready to start a Geant4 deposited-energy simulation.",
                        "risks": ["Physics list may need validation."],
                    },
                }

            return _Result()

    planner = SimulationBriefingPlanner(gateway_factory=lambda: _Gateway())

    result = await planner.brief(
        user_message="我要仿真一个硅探测器",
        conversation=[],
        workflow_context={"status": "idle"},
    )

    assert result.ready_for_approval is True
    assert result.final_query.startswith("Build a Geant4")
    assert result.proposed_command is not None
    assert result.proposed_command.name == "start_job"
    assert len(calls) == 1
    assert calls[0]["task"] == ModelTask.SIMPLE_EXTRACTION
    assert calls[0]["tier"] == ModelTier.LITE
    assert calls[0]["response_format"] == "json"
    assert calls[0]["metadata"]["module_name"] == "simulation_briefing"
    assert calls[0]["metadata"]["enable_thinking"] is False


@pytest.mark.asyncio
async def test_briefing_prompt_includes_ap8ae8_orbit_radiation_requirements() -> None:
    calls: list[dict[str, Any]] = []

    class _Gateway:
        async def call(self, **kwargs: Any) -> Any:
            calls.append(kwargs)

            class _Result:
                error = None
                parsed_json = {
                    "status": "needs_input",
                    "understanding": "用户想做空间轨道辐照仿真。",
                    "questions": ["请提供 L-shell 和 B/B0，或允许后续接入磁场/轨道采样。"],
                    "recommendations": [],
                    "draft_plan": {"environment": {"model": "AP8/AE8"}},
                    "missing_critical_fields": ["l_shell", "bb0"],
                    "assumptions": [],
                    "risks": ["AP8/AE8 不是动态空间天气模型。"],
                    "final_query": "",
                }

            return _Result()

    planner = SimulationBriefingPlanner(gateway_factory=lambda: _Gateway())

    await planner.brief(
        user_message="我要仿真 500km 太阳同步轨道的空间辐照",
        conversation=[],
        workflow_context={"status": "idle"},
    )

    system_prompt = calls[0]["system_prompt"]
    user_prompt = calls[0]["user_prompt"]
    assert "AP8/AE8" in system_prompt
    assert "L-shell" in system_prompt
    assert "B/B0" in system_prompt
    assert "TLE" in system_prompt
    assert "geodetic" in system_prompt
    assert "altitude/inclination" in system_prompt
    assert "dynamic space-weather" in system_prompt
    assert "aep8/astropy/skyfield/sgp4" in system_prompt
    assert "space_radiation" in user_prompt


@pytest.mark.asyncio
async def test_briefing_planner_rejects_missing_approval_request() -> None:
    class _Gateway:
        async def call(self, **kwargs: Any) -> Any:
            class _Result:
                error = None
                parsed_json = {
                    "status": "ready_for_approval",
                    "understanding": "Incomplete",
                    "questions": [],
                    "recommendations": [],
                    "draft_plan": {},
                    "missing_critical_fields": [],
                    "assumptions": [],
                    "risks": [],
                    "final_query": "Run it",
                }

            return _Result()

    planner = SimulationBriefingPlanner(gateway_factory=lambda: _Gateway())

    with pytest.raises(ValueError, match="approval_request"):
        await planner.brief(
            user_message="开始仿真",
            conversation=[],
            workflow_context={},
        )


@pytest.mark.asyncio
async def test_briefing_planner_requires_pending_start_command_for_approval() -> None:
    class _Gateway:
        async def call(self, **kwargs: Any) -> Any:
            class _Result:
                error = None
                parsed_json = {
                    "status": "ready_for_approval",
                    "understanding": "Ready",
                    "questions": [],
                    "recommendations": [],
                    "draft_plan": {"objective": "Run simulation."},
                    "missing_critical_fields": [],
                    "assumptions": [],
                    "risks": [],
                    "final_query": "Run it",
                    "approval_request": {
                        "requires_human_approval": True,
                        "summary": "Start it.",
                        "risks": [],
                    },
                }

            return _Result()

    planner = SimulationBriefingPlanner(gateway_factory=lambda: _Gateway())

    with pytest.raises(ValueError, match="proposed_command"):
        await planner.brief(
            user_message="开始仿真",
            conversation=[],
            workflow_context={},
        )


@pytest.mark.asyncio
async def test_briefing_planner_normalizes_model_false_approval_flag() -> None:
    class _Gateway:
        async def call(self, **kwargs: Any) -> Any:
            class _Result:
                error = None
                parsed_json = {
                    "status": "ready_for_approval",
                    "understanding": "用户要做能量分辨率和 n/gamma 甄别仿真。",
                    "questions": [],
                    "recommendations": ["先用小事件数验证 scoring。"],
                    "draft_plan": {"objective": "Study energy resolution and n/gamma PSD."},
                    "missing_critical_fields": [],
                    "assumptions": ["使用默认探测器几何占位。"],
                    "risks": ["材料和光产额会影响分辨率。"],
                    "final_query": (
                        "Build a simulation for energy resolution and n/gamma "
                        "discrimination."
                    ),
                    "proposed_command": {
                        "name": "start_job",
                        "args": {
                            "query": (
                                "Build a simulation for energy resolution and n/gamma "
                                "discrimination."
                            ),
                            "run_mode": "strict",
                        },
                        "risk": "write",
                        "status": "pending",
                        "summary": "Start after human approval.",
                    },
                    "approval_request": {
                        "requires_human_approval": False,
                        "summary": "Start energy-resolution simulation.",
                        "risks": ["Validate detector response assumptions."],
                    },
                }

            return _Result()

    planner = SimulationBriefingPlanner(gateway_factory=lambda: _Gateway())

    result = await planner.brief(
        user_message="能量分辨率研究 做n/gamma甄别",
        conversation=[],
        workflow_context={},
    )

    assert result.ready_for_approval is True
    assert result.approval_request is not None
    assert result.approval_request.requires_human_approval is True


@pytest.mark.asyncio
async def test_briefing_planner_recovers_json_from_raw_content() -> None:
    class _Gateway:
        async def call(self, **kwargs: Any) -> Any:
            class _Result:
                error = None
                parsed_json = None
                content = "```json\n" + json.dumps(_ready_briefing_payload()) + "\n```"
                reasoning_content = ""

            return _Result()

    planner = SimulationBriefingPlanner(gateway_factory=lambda: _Gateway())

    result = await planner.brief(
        user_message="能量分辨率研究 做n/gamma甄别",
        conversation=[],
        workflow_context={},
    )

    assert result.ready_for_approval is True
    assert result.final_query.startswith("Build an energy-resolution")


@pytest.mark.asyncio
async def test_briefing_planner_uses_local_ready_fallback_for_bad_lite_json() -> None:
    calls: list[dict[str, Any]] = []

    class _Gateway:
        async def call(self, **kwargs: Any) -> Any:
            calls.append(kwargs)

            class _Result:
                error = None
                parsed_json = None
                content = "I need more details before planning."
                reasoning_content = ""

            return _Result()

    planner = SimulationBriefingPlanner(gateway_factory=lambda: _Gateway())

    result = await planner.brief(
        user_message="能量分辨率研究 做n/gamma甄别",
        conversation=[],
        workflow_context={},
    )

    assert result.ready_for_approval is True
    assert result.final_query == "能量分辨率研究 做n/gamma甄别"
    assert result.proposed_command is not None
    assert result.proposed_command.args["query"] == "能量分辨率研究 做n/gamma甄别"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_briefing_planner_uses_local_ready_fallback_when_lite_call_fails() -> None:
    class _Gateway:
        async def call(self, **kwargs: Any) -> Any:
            class _Result:
                error = "connection failed"
                parsed_json = None
                content = ""
                reasoning_content = ""

            return _Result()

    planner = SimulationBriefingPlanner(gateway_factory=lambda: _Gateway())

    result = await planner.brief(
        user_message="能量分辨率研究 做n/gamma甄别",
        conversation=[],
        workflow_context={},
    )

    assert result.ready_for_approval is True
    assert result.final_query == "能量分辨率研究 做n/gamma甄别"
    assert result.approval_request is not None
    assert result.approval_request.requires_human_approval is True


@pytest.mark.asyncio
async def test_briefing_planner_returns_single_guided_question() -> None:
    class _Gateway:
        async def call(self, **kwargs: Any) -> Any:
            class _Result:
                error = None
                parsed_json = {
                    "status": "needs_input",
                    "understanding": "用户想做 He3 管中子探测仿真。",
                    "next_question": {
                        "field": "source",
                        "question": "你主要想模拟哪种入射中子？",
                        "choices": ["热中子", "单能快中子", "能谱源", "先用默认热中子"],
                        "why": "入射源决定物理列表和效率统计。",
                    },
                    "hidden_questions": ["管长和半径？", "He3 气压？"],
                    "questions": ["你主要想模拟哪种入射中子？", "管长和半径？"],
                    "recommendations": [],
                    "draft_plan": {"objective": "He3 tube neutron response"},
                    "missing_critical_fields": ["source"],
                    "assumptions": [],
                    "risks": [],
                    "final_query": "",
                }

            return _Result()

    planner = SimulationBriefingPlanner(gateway_factory=lambda: _Gateway())

    result = await planner.brief(
        user_message="我想要 he3 管仿真",
        conversation=[],
        workflow_context={},
    )

    assert result.ready_for_approval is False
    assert result.next_question is not None
    assert result.next_question.field == "source"
    assert result.next_question.question == "你主要想模拟哪种入射中子？"
    assert result.next_question.choices[1] == "单能快中子"
    assert result.hidden_questions == ["管长和半径？", "He3 气压？"]
    summary = result.summary_text()
    assert "你主要想模拟哪种入射中子？" in summary
    assert "1. 热中子" in summary
    assert "管长和半径" not in summary


@pytest.mark.asyncio
async def test_briefing_planner_compacts_long_context_with_lite_before_max() -> None:
    calls: list[dict[str, Any]] = []

    class _Gateway:
        profiles = {
            ModelTier.MAX: SimpleNamespace(context_window_tokens=100),
        }

        async def call(self, **kwargs: Any) -> Any:
            calls.append(kwargs)

            class _Result:
                error = None
                content = ""
                parsed_json: dict[str, Any] | None = None

            result = _Result()
            if kwargs["task"] == ModelTask.CONTEXT_SUMMARY:
                result.parsed_json = {
                    "stable_facts": ["He3 tube detector"],
                    "answered_fields": {"geometry": "tube"},
                    "open_questions": ["source spectrum"],
                    "rejected_options": [],
                    "latest_user_intent": "refine He3 neutron detector simulation",
                    "risk_notes": ["gas pressure affects efficiency"],
                }
                return result

            prompt = json.loads(kwargs["user_prompt"])
            assert prompt["context_window_stats"]["history_usage_ratio"] > 0.75
            assert prompt["context_window_stats"]["compacted"] is True
            assert prompt["context_window_stats"]["state"] == "compacted"
            assert prompt["context_window_stats"]["cycle"] == 1
            assert "compacted_briefing_memory" in prompt
            assert prompt["compacted_briefing_memory"]["stable_facts"] == [
                "He3 tube detector"
            ]
            assert len(prompt["briefing_conversation"]) <= 5
            assert prompt["latest_user_message"] == "继续打磨"
            assert "old-turn-0" not in json.dumps(prompt, ensure_ascii=False)
            result.parsed_json = {
                "status": "needs_input",
                "understanding": "用户想做 He3 管中子探测仿真。",
                "next_question": {
                    "field": "source",
                    "question": "你主要想模拟哪种入射中子？",
                    "choices": ["热中子", "单能快中子"],
                },
                "hidden_questions": ["He3 气压？"],
                "questions": ["你主要想模拟哪种入射中子？"],
                "recommendations": [],
                "draft_plan": {"objective": "He3 response"},
                "missing_critical_fields": ["source"],
                "assumptions": [],
                "risks": [],
                "final_query": "",
            }
            return result

    conversation = [
        {"role": "user", "content": f"old-turn-{index} " + ("x" * 1600)}
        for index in range(9)
    ]
    conversation.append({"role": "user", "content": "继续打磨"})
    planner = SimulationBriefingPlanner(gateway_factory=lambda: _Gateway())

    result = await planner.brief(
        user_message="继续打磨",
        conversation=conversation,
        workflow_context={},
    )

    assert calls[0]["task"] == ModelTask.CONTEXT_SUMMARY
    assert calls[0]["tier"] == ModelTier.LITE
    assert calls[1]["task"] == ModelTask.SIMPLE_EXTRACTION
    assert calls[1]["tier"] == ModelTier.LITE
    assert result.compacted_briefing_memory["answered_fields"]["geometry"] == "tube"
    assert result.context_window_stats["compacted"] is True
    assert result.context_window_stats["state"] == "compacted"
    assert result.context_window_stats["cycle"] == 1


@pytest.mark.asyncio
async def test_briefing_planner_does_not_compact_history_below_window_threshold() -> None:
    calls: list[dict[str, Any]] = []

    class _Gateway:
        profiles = {
            ModelTier.MAX: SimpleNamespace(context_window_tokens=100_000),
        }

        async def call(self, **kwargs: Any) -> Any:
            calls.append(kwargs)

            class _Result:
                error = None
                content = ""
                parsed_json = {
                    "status": "needs_input",
                    "understanding": "用户想做 He3 管中子探测仿真。",
                    "next_question": {
                        "field": "source",
                        "question": "你主要想模拟哪种入射中子？",
                        "choices": ["热中子", "单能快中子"],
                    },
                    "hidden_questions": [],
                    "questions": ["你主要想模拟哪种入射中子？"],
                    "recommendations": [],
                    "draft_plan": {"objective": "He3 response"},
                    "missing_critical_fields": ["source"],
                    "assumptions": [],
                    "risks": [],
                    "final_query": "",
                }

            return _Result()

    planner = SimulationBriefingPlanner(gateway_factory=lambda: _Gateway())

    result = await planner.brief(
        user_message="继续打磨",
        conversation=[
            {"role": "user", "content": "我想要 he3 管仿真"},
            {"role": "assistant", "content": "你主要想模拟哪种入射中子？"},
            {"role": "user", "content": "继续打磨"},
        ],
        workflow_context={},
    )

    assert len(calls) == 1
    assert calls[0]["task"] == ModelTask.SIMPLE_EXTRACTION
    assert calls[0]["tier"] == ModelTier.LITE
    prompt = json.loads(calls[0]["user_prompt"])
    assert prompt["context_window_stats"]["compacted"] is False
    assert prompt["context_window_stats"]["state"] == "normal"
    assert prompt["context_window_stats"]["cycle"] == 0
    assert "compacted_briefing_memory" not in prompt
    assert result.compacted_briefing_memory == {}


@pytest.mark.asyncio
async def test_approved_plan_summarizer_uses_lite_and_returns_bilingual_short_text() -> None:
    calls: list[dict[str, Any]] = []

    class _Gateway:
        async def call(self, **kwargs: Any) -> Any:
            calls.append(kwargs)

            class _Result:
                error = None
                content = ""
                parsed_json = {
                    "zh": "硅探测器沉积能量仿真超过五十字会被截断" * 3,
                    "en": "Silicon detector deposited energy simulation with a long tail",
                }

            return _Result()

    summarizer = ApprovedPlanSummarizer(gateway_factory=lambda: _Gateway())

    result = await summarizer.summarize(
        {
            "final_query": "Build a Geant4 silicon detector deposited-energy simulation.",
            "draft_plan": {"objective": "Measure deposited energy."},
        }
    )

    assert calls[0]["task"] == ModelTask.CONTEXT_SUMMARY
    assert calls[0]["tier"] == ModelTier.LITE
    assert calls[0]["response_format"] == "json"
    assert set(result) == {"en", "zh"}
    assert result["zh"].startswith("硅探测器沉积能量仿真")
    assert result["en"].startswith("Silicon detector")
    assert len(result["zh"]) <= 50
    assert len(result["en"]) <= 50
