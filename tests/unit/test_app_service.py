from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from agent_core.app import PIPELINE_PHASES, RadAgentAppService
from agent_core.models.schemas import ModelCallResult, ModelProvider, ModelTask, ModelTier
from agent_core.workspace.paths import STAGE_GATE_VALIDATION, STAGE_INPUT
from pydantic import ValidationError


def test_service_exposes_pipeline_contract(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)

    assert PIPELINE_PHASES[0] == "prepare_workspace"
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
    assert config.agentic_repair_max_turns == 24
    assert config.agentic_repair_history_chars == 48_000
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
    assert status.current_phase_idx == 7
    assert status.status == "running"
    assert status.state["current_node"] == "gate_subgraph"
    assert "termination_reason" not in status.key_statuses
    assert status.state.get("errors") == []
    assert status.key_statuses["g4_codegen_status"] == "passed"
    assert status.key_statuses["patch_status"] == "applied"


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


def test_service_rejects_provider_in_frontend_model_config(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path, env_path=tmp_path / ".env")

    with pytest.raises(ValidationError):
        service.update_model_config({"provider": "mock"})


@pytest.mark.asyncio
async def test_service_prepares_visualization_workbench_and_records_blocking_verdict(
    tmp_path,
    monkeypatch,
) -> None:
    events = []
    service = RadAgentAppService(workspace_root=tmp_path, event_callback=events.append)
    project_dir = tmp_path / "jobs" / "job_visual" / "06_patch" / "geant4_project"
    executable = project_dir / "build" / "sim"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    executable.chmod(0o755)
    service.state = {
        "job_id": "job_visual",
        "generated_code_dir": str(project_dir),
        "_executable_path": str(executable),
    }
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)

    workbench = await service.prepare_visualization_workbench(events=100)
    rejected = service.record_visual_verdict(approved=False, notes="target offset wrong")
    approved = service.record_visual_verdict(approved=True)

    assert workbench.success is True
    assert workbench.events == 100
    assert Path(workbench.init_macro).is_file()
    assert Path(workbench.vis_macro).is_file()
    assert workbench.environment["QT_QPA_PLATFORM"] == "xcb"
    assert service.state["visual_review_status"] == "approved"
    assert rejected.status == "rejected"
    assert rejected.blocking is True
    assert approved.status == "approved"
    assert [event.event_type for event in events][-3:] == [
        "visualization_workbench_ready",
        "visualization_review_rejected",
        "visualization_review_approved",
    ]


def test_service_status_pauses_on_blocked_visual_review_gate(tmp_path) -> None:
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

    assert status.status == "paused"
    assert status.needs_confirmation is True


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

    async def human_confirmation(state: dict) -> dict:
        assert state["raw_human_response"]["user_decision"] == "approve"
        return {
            "confirmation_status": "approved",
            "human_confirmation_required": False,
            "unconfirmed_assumptions_count": 0,
        }

    async def no_op(state: dict) -> dict:
        return {}

    service._subgraph_nodes = {
        "g4_modeling": g4_modeling,
        "human_confirmation": human_confirmation,
        "g4_codegen": no_op,
        "patch": no_op,
        "gate": no_op,
        "artifact": no_op,
        "report": no_op,
    }

    status = await service.run_until_blocked()

    assert status.status == "completed"
    assert "human_confirmation" in status.completed_phases
    assert "g4_codegen" in status.completed_phases
    assert [
        event.event_type
        for event in service.recent_events()
        if event.event_type == "human_confirmation_required"
    ] == []


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
