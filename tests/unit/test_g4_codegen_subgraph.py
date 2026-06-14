"""Tests for G4 Codegen Subgraph — compilation, nodes, and validators."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


class TestG4CodegenSubgraphCompilation:
    """Verify the G4 codegen subgraph compiles."""

    def test_subgraph_compiles(self) -> None:
        """G4 codegen subgraph must compile without errors."""
        from agent_core.graph.subgraphs.g4_codegen_graph import (
            build_g4_codegen_subgraph,
        )

        graph = build_g4_codegen_subgraph()
        compiled = graph.compile()
        assert compiled is not None

    def test_subgraph_has_parallel_layers_and_global_integration_agent(self) -> None:
        """Subgraph should expose coarse module layers and final integration."""
        from agent_core.graph.subgraphs.g4_codegen_graph import (
            MODULE_LAYERS,
            build_g4_codegen_subgraph,
        )

        graph = build_g4_codegen_subgraph()
        node_names = set(graph.nodes)
        assert "global_integration_agent" in node_names
        retired_nodes = {"global_" + "llm_repair_agent", "global_" + "code_repair_agent"}
        assert node_names.isdisjoint(retired_nodes)
        assert "runtime_execution_audit" in node_names
        assert ("integration_assembler", "global_integration_agent") in graph.edges
        assert ("global_integration_agent", "runtime_execution_audit") in graph.edges
        assert ("physics_quality_review", "persist_codegen_output") in graph.edges
        for layer_name, module_names in MODULE_LAYERS:
            context_node = f"coordinate_{layer_name}_context"
            assert f"run_{layer_name}" in node_names
            assert f"{layer_name}_gate" in node_names
            assert context_node in node_names
            assert (context_node, "build_interface_contracts") in graph.edges or any(
                edge[0] == context_node and edge[1].startswith("run_")
                for edge in graph.edges
            )
            for module_name in module_names:
                assert f"run_{module_name}_agent" not in node_names
                assert f"{module_name}_complete" not in node_names

    def test_subgraph_state_schema(self) -> None:
        """Subgraph state must have required fields."""
        from agent_core.g4_codegen.schemas import G4CodegenSubgraphState

        annotations = G4CodegenSubgraphState.__annotations__
        required = [
            "job_id",
            "g4_model_ir_path",
            "confirmation_record_path",
            "confirmed_model_plan_path",
            "human_confirmation_status",
            "proposed_patch",
            "g4_codegen_status",
        ]
        for field in required:
            assert field in annotations, f"Missing field: {field}"

    def test_failed_layer_gate_routes_to_persist(self) -> None:
        """A failed layer gate must not release the next module layer."""
        from agent_core.graph.subgraphs.g4_codegen_graph import _route_after_layer_gate

        route = _route_after_layer_gate("detector_modules_gate", "run_application_modules")
        assert (
            route(
                {
                    "layer_gate_results": {
                        "detector_modules_gate": {"status": "fail"},
                    }
                }
            )
            == "persist_codegen_output"
        )
        assert (
            route(
                {
                    "layer_gate_results": {
                        "detector_modules_gate": {"status": "pass"},
                    }
                }
            )
            == "run_application_modules"
        )

    def test_runtime_execution_audit_routes_before_physics_review(self) -> None:
        """Physics review should run only after runtime execution audit passes."""
        from agent_core.graph.subgraphs.g4_codegen_graph import (
            _route_after_runtime_execution_audit,
        )

        assert (
            _route_after_runtime_execution_audit(
                {"runtime_execution_audit": {"status": "fail"}}
            )
            == "persist_codegen_output"
        )
        assert (
            _route_after_runtime_execution_audit(
                {"runtime_execution_audit": {"status": "pass"}}
            )
            == "physics_quality_review"
        )


class TestNewIntegrationAssembler:
    """Test the NEW integration assembler (module-level agent path).

    P0-10/P0-12: Old integration_assembler nodes were removed. These tests use
    the supported integration path.
    """

    def test_new_assembler_produces_valid_patch(self) -> None:
        """New integration_assembler must produce PatchValidator-compliant output."""
        from agent_core.g4_codegen.integration.integration_assembler import (
            assemble_proposed_patch,
        )

        module_results = {
            "simulation_core": {
                "status": "generated",
                "generated_files": [
                    {
                        "path": "include/MaterialRegistry.hh",
                        "new_content": "#pragma once\n",
                        "generated_by": "simulation_core_module_agent",
                        "module_name": "simulation_core",
                        "rationale": "test",
                    }
                ],
            },
        }
        patch = assemble_proposed_patch(module_results, "test")

        # Must have all PatchValidator required fields
        required = {
            "patch_id",
            "job_id",
            "description",
            "change_type",
            "risk_level",
            "changed_files",
            "test_plan",
            "expected_outputs",
        }
        assert required <= set(patch.keys()), f"Missing: {required - set(patch.keys())}"

    def test_old_integration_assembler_deleted(self) -> None:
        """P0-10: Old integration_assembler must not exist."""
        from pathlib import Path

        old_path = Path("agent_core/g4_codegen/nodes/integration_assembler.py")
        assert not old_path.exists(), "Old integration_assembler.py must be deleted"


class TestCodegenValidators:
    """Test g4_codegen validators that are still used by production gates."""

    def test_no_magic_number_clean(self) -> None:
        """Code with named constants should pass."""
        from agent_core.g4_codegen.validators.no_magic_number import check_magic_numbers

        code = 'constexpr double WIDTH = 100.0;\nauto box = new G4Box("b", WIDTH, WIDTH, WIDTH);'
        clean, violations = check_magic_numbers(code, "test")
        assert clean, f"Unexpected violations: {violations}"

    def test_no_magic_number_detects_literal(self) -> None:
        """Code with raw numeric literals should be flagged."""
        from agent_core.g4_codegen.validators.no_magic_number import check_magic_numbers

        code = 'auto box = new G4Box("b", 42.5, 42.5, 42.5);'
        clean, violations = check_magic_numbers(code, "test")
        assert not clean
        assert len(violations) > 0

    def test_no_magic_number_ignores_units_zeroes_and_presentation_literals(self) -> None:
        """Validator should focus on physical literals, not C++/visual boilerplate."""
        from agent_core.g4_codegen.validators.no_magic_number import check_magic_numbers

        code = "\n".join(
            [
                "G4ThreeVector origin(0., 0., 0.);",
                "auto source = G4ThreeVector(0.0 * um, 0.0 * um, -1500.0 * um);",
                "G4Colour red(1., 0., 0.);",
                "circle.SetScreenSize(4.);",
                "G4cout << std::setw(7) << value;",
                "auto binDx_um = width / nx;  // 1000 um",
            ]
        )

        clean, violations = check_magic_numbers(code, "test")

        assert clean, violations


class TestLoadModelIr:
    """Test the codegen I/O functions."""

    async def test_load_from_file(self, tmp_path: Path) -> None:
        """Should load model IR from JSON file."""
        from agent_core.g4_codegen.io_nodes import load_model_ir

        ir_file = tmp_path / "ir.json"
        ir_file.write_text(json.dumps({"model_ir_id": "test", "components": []}))

        result = await load_model_ir({"g4_model_ir_path": str(ir_file)})
        assert result["g4_model_ir"]["model_ir_id"] == "test"

    async def test_load_missing_file(self) -> None:
        """Missing file should return empty model IR."""
        from agent_core.g4_codegen.io_nodes import load_model_ir

        result = await load_model_ir({"g4_model_ir_path": "/nonexistent/ir.json"})
        assert result["g4_model_ir"] == {}


@pytest.mark.asyncio
async def test_module_layer_records_agent_start_event(tmp_path, monkeypatch) -> None:
    """Layer execution should expose whether each module agent actually started."""
    from agent_core.g4_codegen import graph_nodes
    from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult

    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    events: list[dict[str, object]] = []

    def fake_record_event(**kwargs):
        events.append(kwargs)

    async def fake_agent(_ctx):
        return ModuleAgentResult(
            module_name="runtime_app",
            status="generated",
            generated_files=[
                GeneratedModuleFile(
                    path="main.cc",
                    new_content="int main(){return 0;}\n",
                    generated_by="runtime_app_module_agent",
                    module_name="runtime_app",
                    rationale="test",
                )
            ],
        )

    monkeypatch.setattr(graph_nodes, "record_event", fake_record_event)
    monkeypatch.setattr(graph_nodes, "_get_agent_function", lambda _module_name: fake_agent)

    await graph_nodes.run_module_layer_node(
        {
            "job_id": "job_runtime_start",
            "module_contexts": {"runtime_app": {"job_id": "job_runtime_start"}},
        },
        "runtime_modules",
        ["runtime_app"],
    )

    assert any(
        event.get("event_type") == "module_agent_start"
        and event.get("module_name") == "runtime_app"
        and event.get("layer") == "runtime_modules"
        for event in events
    )


@pytest.mark.asyncio
async def test_module_layer_preserves_pending_module_contexts(tmp_path, monkeypatch) -> None:
    """Running one layer must not drop contexts needed by later module layers."""
    from agent_core.g4_codegen import graph_nodes
    from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult

    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(graph_nodes, "record_event", lambda **_kwargs: None)

    async def fake_agent(_ctx):
        return ModuleAgentResult(
            module_name="simulation_core",
            status="generated",
            generated_files=[
                GeneratedModuleFile(
                    path="include/DetectorConstruction.hh",
                    new_content="#pragma once\n",
                    generated_by="simulation_core_module_agent",
                    module_name="simulation_core",
                    rationale="test",
                )
            ],
        )

    monkeypatch.setattr(graph_nodes, "_get_agent_function", lambda _module_name: fake_agent)

    update = await graph_nodes.run_module_layer_node(
        {
            "job_id": "job_preserve_contexts",
            "module_contexts": {
                "simulation_core": {"job_id": "job_preserve_contexts"},
                "runtime_app": {
                    "job_id": "job_preserve_contexts",
                    "module_contract": {"module_name": "runtime_app"},
                },
            },
        },
        "core_modules",
        ["simulation_core"],
    )

    assert update["module_contexts"]["runtime_app"]["module_contract"]["module_name"] == (
        "runtime_app"
    )


@pytest.mark.asyncio
async def test_build_module_contexts_injects_confirmed_human_constraints(
    tmp_path, monkeypatch
) -> None:
    """Confirmed human constraints must reach module agents as hard context."""
    from agent_core.g4_codegen import graph_nodes

    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    confirmed_plan_path = tmp_path / "confirmed_model_plan.json"
    confirmed_plan_path.write_text(
        json.dumps(
            {
                "confirmation_status": "approved",
                "agent_context": {
                    "purpose": "codegen_hard_constraints",
                    "status": "approved",
                    "confirmed_constraints": [
                        {
                            "field_path": "components.water_tank.geometry",
                            "value": {"shape": "cylinder", "radius": "50 cm"},
                            "category": "dimension",
                            "source": "human_confirmation",
                            "status": "edited",
                            "priority": "human_confirmed_hard",
                        }
                    ],
                    "codegen_instruction": "Treat confirmed constraints as hard requirements.",
                },
            }
        ),
        encoding="utf-8",
    )

    result = await graph_nodes.build_module_contexts_node(
        {
            "job_id": "job_hc_constraints",
            "run_mode": "strict",
            "human_confirmation_status": "approved",
            "confirmed_model_plan_path": str(confirmed_plan_path),
            "g4_model_ir": {
                "model_ir_id": "ir_hc",
                "components": [{"component_id": "water_tank", "geometry": {}}],
            },
            "codegen_plan": {"required_modules": ["simulation_core"]},
            "geometry_strategy_plan": {},
            "code_architecture_plan": {},
            "module_contracts": {
                "simulation_core": {
                    "module_name": "simulation_core",
                    "output_files": ["include/DetectorConstruction.hh"],
                }
            },
        }
    )

    ctx = result["module_contexts"]["simulation_core"]
    human_context = ctx["human_confirmation_context"]
    assert human_context["status"] == "approved"
    assert human_context["source_path"] == str(confirmed_plan_path)
    assert human_context["confirmed_constraints"][0]["field_path"] == (
        "components.water_tank.geometry"
    )
    assert human_context["edited_constraint_count"] == 1
    assert human_context["constraint_digest"] == [
        "edited dimension components.water_tank.geometry = {\"radius\": \"50 cm\", \"shape\": \"cylinder\"}"
    ]
    assert "hard" in human_context["codegen_instruction"].lower()

    persisted_context = json.loads(
        (
            tmp_path
            / "jobs"
            / "job_hc_constraints"
            / "05_codegen"
            / "module_contexts"
            / "simulation_core.json"
        ).read_text(encoding="utf-8")
    )
    assert persisted_context["human_confirmation_context"]["confirmed_constraints"][0][
        "field_path"
    ] == "components.water_tank.geometry"
