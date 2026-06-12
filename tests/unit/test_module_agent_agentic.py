"""Tests for the agentic module agent (native tool-calling into a shared workspace).

Replaces the former one-shot JSON module-agent tests. The model is simulated by a
scripted fake gateway that emits write_file tool calls; the agent must write its
owned files into the shared staging workspace and return them as generated_files.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.module_agents.beam_physics_agent import BEAM_PHYSICS_SYSTEM_PROMPT
from agent_core.g4_codegen.module_agents.runtime_app_agent import RUNTIME_APP_SYSTEM_PROMPT
from agent_core.g4_codegen.module_agents.runtime_app_agent import (
    _group_context as runtime_app_group_context,
)
from agent_core.g4_codegen.module_agents.simulation_core_agent import (
    SIMULATION_CORE_SYSTEM_PROMPT,
    _group_context as simulation_core_group_context,
)
from agent_core.models.schemas import (
    ModelCallResult,
    ModelProvider,
    ModelTask,
    ModelTier,
)


def test_agentic_module_prompts_do_not_request_json_responses() -> None:
    """Module agents write files with tools; JSON response instructions waste turns."""
    combined = "\n".join(
        [
            SIMULATION_CORE_SYSTEM_PROMPT,
            BEAM_PHYSICS_SYSTEM_PROMPT,
            RUNTIME_APP_SYSTEM_PROMPT,
        ]
    ).lower()

    assert "只返回 json" not in combined
    assert "return json" not in combined


def test_simulation_core_later_file_groups_can_trust_prior_file_summaries() -> None:
    """Later file groups should not spend a model turn rereading same-module headers."""
    ctx = simulation_core_group_context(
        {"module_contract": {"responsibilities": []}},
        group_name="detector_geometry",
        output_files=["include/DetectorConstruction.hh", "src/DetectorConstruction.cc"],
        group_goal="test",
        prior_files=[
            {
                "path": "include/MaterialRegistry.hh",
                "header_or_interface_content": "class MaterialRegistry { public: void RegisterMaterials(); };",
            }
        ],
    )

    responsibilities = "\n".join(ctx["module_contract"]["responsibilities"]).lower()
    assert "prior_files" in responsibilities
    assert "do not reread" in responsibilities


def test_simulation_core_file_groups_disable_read_file_tool() -> None:
    """Simulation core has full IR/prior context and should not spend turns reading."""
    ctx = simulation_core_group_context(
        {"module_contract": {"responsibilities": []}},
        group_name="materials_and_placement",
        output_files=["include/MaterialRegistry.hh", "src/MaterialRegistry.cc"],
        group_goal="test",
        prior_files=[],
    )

    assert ctx["agent_tool_policy"] == {"allow_read_file": False}


def test_runtime_app_only_macro_group_disables_read_file_tool() -> None:
    """Runtime C++ needs upstream headers; macro generation does not."""
    cpp_ctx = runtime_app_group_context(
        {"module_contract": {"responsibilities": []}},
        group_name="runtime_cpp",
        output_files=["main.cc", "CMakeLists.txt"],
        group_goal="test",
        prior_files=[],
    )
    macro_ctx = runtime_app_group_context(
        {"module_contract": {"responsibilities": []}},
        group_name="runtime_macros",
        output_files=["macros/run.mac"],
        group_goal="test",
        prior_files=[],
    )

    assert cpp_ctx["agent_tool_policy"] == {"allow_read_file": True}
    assert macro_ctx["agent_tool_policy"] == {"allow_read_file": False}


class _FakeGateway:
    """Emits a write_file tool call for each owned file, then stops."""

    def __init__(self, owned_files: dict[str, str]) -> None:
        self._owned = owned_files
        self._fired = False
        self.calls = 0
        self.call_kwargs: list[dict[str, Any]] = []

    async def call(self, **kwargs: Any) -> ModelCallResult:  # type: ignore[no-untyped-def]
        self.calls += 1
        self.call_kwargs.append(kwargs)
        if not self._fired:
            self._fired = True
            tool_calls = [
                {
                    "id": f"call_{i}",
                    "name": "write_file",
                    "arguments": json.dumps({"path": path, "content": content}),
                }
                for i, (path, content) in enumerate(self._owned.items())
            ]
            return ModelCallResult(
                task=ModelTask.CODEGEN,
                tier=ModelTier.PRO,
                provider=ModelProvider.OPENAI_COMPATIBLE,
                model_name="fake",
                content="",
                tool_calls=tool_calls,
                finish_reason="tool_calls",
            )
        return ModelCallResult(
            task=ModelTask.CODEGEN,
            tier=ModelTier.PRO,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="fake",
            content="DONE",
            tool_calls=[],
            finish_reason="stop",
        )


@pytest.mark.asyncio
async def test_agentic_module_agent_writes_owned_files_to_shared_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    owned = {
        "include/Hit.hh": "#pragma once\nclass Hit {};\n",
        "src/Hit.cc": '#include "Hit.hh"\n',
    }
    fake_gw = _FakeGateway(owned)
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )
    # Skip the example-lookup pre-fetch (it hits the gateway / knowledge base).
    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    module_context = {
        "job_id": "job_agentic_test",
        "module_name": "simulation_core",
        "module_contract": {"output_files": list(owned.keys())},
    }
    result = await run_module_agent("simulation_core", module_context)

    assert result.status == "generated"
    assert {f.path for f in result.generated_files} == set(owned.keys())
    by_path = {f.path: f.new_content for f in result.generated_files}
    assert "class Hit" in by_path["include/Hit.hh"]
    assert by_path["src/Hit.cc"].startswith('#include "Hit.hh"')
    # Files were actually written to the shared staging workspace.
    staged = workspace / "jobs" / "job_agentic_test"
    found = list(staged.rglob("module_workspace"))
    assert found, "module_workspace staging dir must exist"
    written = found[0]
    assert (written / "include" / "Hit.hh").read_text().startswith("#pragma once")


@pytest.mark.asyncio
async def test_agentic_module_agent_stops_after_owned_files_are_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Writing all owned files in one tool round should not require a DONE round-trip."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    owned = {
        "include/PrimaryGeneratorAction.hh": "#pragma once\nclass PrimaryGeneratorAction {};\n",
        "src/PrimaryGeneratorAction.cc": '#include "PrimaryGeneratorAction.hh"\n',
    }
    fake_gw = _FakeGateway(owned)
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    module_context = {
        "job_id": "job_fast_stop",
        "module_name": "beam_physics",
        "module_contract": {"output_files": list(owned.keys())},
    }
    result = await run_module_agent("beam_physics", module_context)

    assert result.status == "generated"
    assert fake_gw.calls == 1
    assert result.repair_attempts[0]["stop_reason"] == "stop_hook"
    assert result.repair_attempts[0]["n_turns"] == 1


@pytest.mark.asyncio
async def test_agentic_module_agent_disables_provider_thinking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tool-driven module codegen should avoid slow provider thinking mode."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    fake_gw = _FakeGateway({"main.cc": "int main(){return 0;}\n"})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_no_thinking",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["main.cc"]},
        },
    )

    assert fake_gw.call_kwargs[0]["metadata"]["enable_thinking"] is False


@pytest.mark.asyncio
async def test_agentic_module_agent_can_disable_read_file_tool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """File groups with complete prior context should be forced to write, not inspect."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    fake_gw = _FakeGateway({"main.cc": "int main(){return 0;}\n"})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    await run_module_agent(
        "runtime_app",
        {
            "job_id": "job_no_read_file",
            "module_name": "runtime_app",
            "module_contract": {"output_files": ["main.cc"]},
            "agent_tool_policy": {"allow_read_file": False},
        },
    )

    tool_names = {
        tool["function"]["name"]
        for tool in fake_gw.call_kwargs[0]["tools"]
    }
    assert "read_file" not in tool_names
    assert tool_names == {"write_file", "edit_file"}


@pytest.mark.asyncio
async def test_agentic_module_agent_flags_missing_owned_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If the model never writes an owned file, the result records the error."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    fake_gw = _FakeGateway({})  # writes nothing
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway", lambda: fake_gw
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    module_context = {
        "job_id": "job_missing",
        "module_name": "beam_physics",
        "module_contract": {"output_files": ["src/PrimaryGeneratorAction.cc"]},
    }
    result = await run_module_agent("beam_physics", module_context)
    assert result.status == "failed"
    assert any("did not write owned file" in e for e in result.errors)


@pytest.mark.asyncio
async def test_agentic_module_agent_fails_when_only_some_owned_files_are_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Partial module output must not be marked generated and released downstream."""
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    fake_gw = _FakeGateway({"main.cc": "int main(){return 0;}\n"})
    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        lambda: fake_gw,
    )

    async def _no_examples(**_: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(
        "agent_core.g4_codegen.module_agents.base._collect_example_lookup_context",
        _no_examples,
    )

    module_context = {
        "job_id": "job_partial",
        "module_name": "runtime_app",
        "module_contract": {"output_files": ["main.cc", "macros/run.mac"]},
    }
    result = await run_module_agent("runtime_app", module_context)

    assert result.status == "failed"
    assert {file.path for file in result.generated_files} == {"main.cc"}
    assert result.errors == ["module agent did not write owned file: macros/run.mac"]


@pytest.mark.asyncio
async def test_runtime_app_agent_generates_cpp_and_macro_file_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime app should not ask one agent loop to write C++ plus all macros."""
    from agent_core.g4_codegen.module_agents import runtime_app_agent
    from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult

    calls: list[list[str]] = []

    async def fake_run_module_agent(
        *,
        module_name: str,
        module_context: dict[str, Any],
        system_prompt: str = "",
    ) -> ModuleAgentResult:
        del system_prompt
        assert module_name == "runtime_app"
        output_files = list(module_context["module_contract"]["output_files"])
        calls.append(output_files)
        return ModuleAgentResult(
            module_name="runtime_app",
            status="generated",
            generated_files=[
                GeneratedModuleFile(
                    path=path,
                    new_content=f"// {path}\n",
                    generated_by="runtime_app_module_agent",
                    module_name="runtime_app",
                    rationale="test",
                )
                for path in output_files
            ],
        )

    monkeypatch.setattr(runtime_app_agent, "run_module_agent", fake_run_module_agent)

    result = await runtime_app_agent.run_runtime_app_agent(
        {
            "job_id": "job_runtime_groups",
            "module_contract": {
                "output_files": [
                    "include/OutputManager.hh",
                    "src/OutputManager.cc",
                    "include/ActionInitialization.hh",
                    "src/ActionInitialization.cc",
                    "include/RunAction.hh",
                    "src/RunAction.cc",
                    "include/EventAction.hh",
                    "src/EventAction.cc",
                    "include/SteppingAction.hh",
                    "src/SteppingAction.cc",
                    "main.cc",
                    "CMakeLists.txt",
                    "macros/run.mac",
                    "macros/init.mac",
                    "macros/init_vis.mac",
                    "macros/vis.mac",
                    "macros/gui.mac",
                ]
            },
        }
    )

    assert len(calls) == 2
    assert calls[0] == [
        "include/OutputManager.hh",
        "src/OutputManager.cc",
        "include/ActionInitialization.hh",
        "src/ActionInitialization.cc",
        "include/RunAction.hh",
        "src/RunAction.cc",
        "include/EventAction.hh",
        "src/EventAction.cc",
        "include/SteppingAction.hh",
        "src/SteppingAction.cc",
        "main.cc",
        "CMakeLists.txt",
    ]
    assert calls[1] == [
        "macros/run.mac",
        "macros/init.mac",
        "macros/init_vis.mac",
        "macros/vis.mac",
        "macros/gui.mac",
    ]
    assert result.status == "generated"
    assert len(result.generated_files) == 17
