from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from agent_core.app.schemas import JobStatus
from agent_core.chat.agent import ChatAgent, _format_workflow_context
from agent_core.workflow.context import build_workflow_context


def test_workflow_context_format_includes_memory_items() -> None:
    rendered = _format_workflow_context(
        {
            "job_id": "job_1",
            "status": "running",
            "current_phase": "context",
            "current_phase_idx": 1,
            "needs_confirmation": False,
            "memory": [
                {
                    "source": "run",
                    "key": "copilot_briefing",
                    "summary": "Start silicon detector simulation.",
                    "payload": {"final_query": "Build a Geant4 silicon detector."},
                }
            ],
        }
    )

    assert "memory:" in rendered
    assert "copilot_briefing" in rendered
    assert "Start silicon detector simulation." in rendered
    assert "Build a Geant4 silicon detector." in rendered


def test_chat_prompt_injects_ap8ae8_context_for_orbit_radiation_request() -> None:
    agent = ChatAgent()

    prompt = agent._build_system_prompt(
        [],
        [],
        [],
        workflow_context={"status": "idle"},
        user_message="仿真 500km 太阳同步轨道的空间辐照",
    )

    assert "本地 AP8/AE8" in prompt
    assert "L-shell" in prompt
    assert "B/B0" in prompt
    assert "TLE" in prompt
    assert "geodetic samples" in prompt
    assert "aep8/astropy/skyfield/sgp4" in prompt
    assert "不是动态空间天气模型" in prompt


def test_chat_prompt_does_not_inject_ap8ae8_context_for_plain_beam_request() -> None:
    agent = ChatAgent()

    prompt = agent._build_system_prompt(
        [],
        [],
        [],
        workflow_context={"status": "idle"},
        user_message="simulate a 10 MeV proton beam on silicon",
    )

    assert "本地 AP8/AE8" not in prompt


def test_workflow_context_reads_external_sources_from_task_spec(tmp_path: Path) -> None:
    task_spec_path = tmp_path / "jobs" / "job_ap8" / "02_task_plan" / "task_spec.json"
    task_spec_path.parent.mkdir(parents=True)
    spectrum_path = task_spec_path.parent / "space_radiation" / "ap8.csv"
    spectrum_path.parent.mkdir()
    spectrum_path.write_text("energy_MeV,flux_cm-2_s-1_MeV-1\n1,42\n", encoding="utf-8")
    task_spec_path.write_text(
        json.dumps(
            {
                "simulation_scope": ["geant4"],
                "external_sources": [
                    {
                        "source_id": "ap8_orbit_protons",
                        "source_type": "environment",
                        "domain": "space_radiation",
                        "provider": "ap8ae8",
                        "model": "AP8MIN",
                        "status": "ready",
                        "artifact_paths": [str(spectrum_path)],
                        "parameters": {"l_shell": 2.0, "bb0": 1.05},
                        "provenance": {"dataset_id": "nasa-radbelt-aep8"},
                        "derived_outputs": [
                            {
                                "kind": "geant4_source_spectrum",
                                "path": str(spectrum_path),
                                "consumer": "g4_modeling",
                            }
                        ],
                        "limitations": ["static trapped belt model"],
                        "consumers": ["g4_modeling", "g4_codegen", "gates", "copilot"],
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    context = build_workflow_context(
        status=JobStatus(
            job_id="job_ap8",
            status="running",
            user_query="仿真 AP8 轨道辐照",
            current_phase="task_planning",
            current_phase_idx=2,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
        state={"task_spec_path": str(task_spec_path)},
        recent_events=[],
        artifacts=[],
        gate_results=[],
        workspace_root=tmp_path,
    )

    external_memory = [item for item in context.memory if item.key == "external_sources"]
    assert len(external_memory) == 1
    assert "AP8MIN" in external_memory[0].summary
    assert external_memory[0].payload["sources"][0]["source_id"] == "ap8_orbit_protons"
