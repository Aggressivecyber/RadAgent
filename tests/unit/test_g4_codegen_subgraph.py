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

    def test_subgraph_uses_project_agent_as_default_codegen_path(self) -> None:
        """Subgraph should use one full-project agent before runtime audit."""
        from agent_core.graph.subgraphs.g4_codegen_graph import (
            build_g4_codegen_subgraph,
        )

        graph = build_g4_codegen_subgraph()
        node_names = set(graph.nodes)
        assert "geant4_project_agent" in node_names
        retired_nodes = {"global_" + "llm_repair_agent", "global_" + "code_repair_agent"}
        assert node_names.isdisjoint(retired_nodes)
        assert "runtime_execution_audit" in node_names
        assert ("build_interface_contracts", "geant4_project_agent") in graph.edges
        assert ("geant4_project_agent", "runtime_execution_audit") in graph.edges
        assert ("integration_assembler", "global_integration_agent") not in graph.edges
        compiled = graph.compile()
        mermaid = compiled.get_graph().draw_mermaid()
        assert "physics_quality_review" in mermaid
        assert "persist_codegen_output" in mermaid
        assert not any(node.startswith("run_") and node.endswith("_modules") for node in node_names)
        assert not any(node.endswith("_modules_gate") for node in node_names)

    def test_compiled_subgraph_mermaid_shows_project_agent_path(self) -> None:
        """Rendered graph should not imply the retired module-layer flow."""
        from agent_core.graph.subgraphs.g4_codegen_graph import (
            build_g4_codegen_subgraph,
        )

        mermaid = build_g4_codegen_subgraph().compile().get_graph().draw_mermaid()

        assert "geant4_project_agent" in mermaid
        assert "build_interface_contracts --> geant4_project_agent" in mermaid
        assert "geant4_project_agent --> runtime_execution_audit" in mermaid
        assert "run_core_modules" not in mermaid
        assert "integration_assembler" not in mermaid

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

    def test_failed_layer_gate_with_no_generated_files_routes_to_persist(self) -> None:
        """A failed layer gate with no repairable code should fail closed."""
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

    def test_failed_layer_gate_with_generated_files_fails_closed(self) -> None:
        """Failed modules must not be promoted to whole-project integration."""
        from agent_core.graph.subgraphs.g4_codegen_graph import _route_after_layer_gate

        route = _route_after_layer_gate("core_modules_gate", "run_runtime_modules")

        result = route(
            {
                "layer_gate_results": {
                    "core_modules_gate": {"status": "fail"},
                },
                "module_results": {
                    "simulation_core": {
                        "status": "failed",
                        "generated_files": [
                            {"path": "src/DetectorConstruction.cc", "new_content": "broken"}
                        ],
                    }
                },
            }
        )

        assert result == "persist_codegen_output"

    def test_runtime_execution_audit_routes_before_physics_review(self) -> None:
        """Physics review should run only after runtime execution audit passes."""
        from agent_core.graph.subgraphs.g4_codegen_graph import (
            _route_after_runtime_execution_audit,
        )

        assert (
            _route_after_runtime_execution_audit(
                {"runtime_execution_audit": {"status": "fail"}}
            )
            == "geant4_project_agent"
        )
        assert (
            _route_after_runtime_execution_audit(
                {"runtime_execution_audit": {"status": "pass"}}
            )
            == "physics_quality_review"
        )

    def test_runtime_execution_audit_failure_routes_back_to_project_agent_once(self) -> None:
        """Runtime audit failures should be repaired by the full-project agent."""
        from agent_core.graph.subgraphs.g4_codegen_graph import (
            _route_after_runtime_execution_audit,
        )

        assert (
            _route_after_runtime_execution_audit(
                {
                    "runtime_execution_audit": {"status": "fail"},
                    "runtime_audit_repair_attempts": 0,
                }
            )
            == "geant4_project_agent"
        )
        assert (
            _route_after_runtime_execution_audit(
                {
                    "runtime_execution_audit": {"status": "fail"},
                    "runtime_audit_repair_attempts": 2,
                }
            )
            == "persist_codegen_output"
        )

    def test_physics_quality_failure_routes_back_to_project_agent_once(self) -> None:
        """Physics review failures should feed required fixes back to the project agent."""
        from agent_core.graph.subgraphs.g4_codegen_graph import (
            _route_after_physics_quality_review,
        )

        assert (
            _route_after_physics_quality_review(
                {
                    "physics_quality_review": {
                        "status": "fail",
                        "routing_recommendation": "repair_code",
                        "required_fixes": [
                            {
                                "target": "src/OutputManager.cc",
                                "message": "Write real energy deposits.",
                            }
                        ],
                    },
                    "physics_review_repair_attempts": 0,
                }
            )
            == "geant4_project_agent"
        )
        assert (
            _route_after_physics_quality_review(
                {
                    "physics_quality_review": {"status": "fail"},
                    "physics_review_repair_attempts": 2,
                }
            )
            == "persist_codegen_output"
        )

    def test_physics_review_user_input_routes_to_persist(self) -> None:
        """Human/IR physics blockers should pause instead of ping-ponging to codegen."""
        from agent_core.graph.subgraphs.g4_codegen_graph import (
            _route_after_physics_quality_review,
        )

        next_node = _route_after_physics_quality_review(
            {
                "physics_quality_review": {
                    "status": "needs_user_input",
                    "routing_recommendation": "request_user_input",
                    "required_fixes": [],
                    "needs_user_input": [
                        {
                            "target": "materials[1]",
                            "message": (
                                "Get user confirmation on whether tracker planes "
                                "should use plastic scintillator or silicon."
                            ),
                        }
                    ],
                },
                "physics_review_repair_attempts": 0,
            }
        )

        assert next_node == "persist_codegen_output"

    def test_physics_review_old_style_user_confirmation_is_advisory(self) -> None:
        """Post-codegen parameter confirmation gaps should not reopen user review."""
        from agent_core.g4_codegen.physics_quality_reviewer import _normalize_review
        from agent_core.graph.subgraphs.g4_codegen_graph import (
            _route_after_physics_quality_review,
        )

        review = _normalize_review(
            {
                "status": "revise",
                "overall_score": 72,
                "required_fixes": [
                    {
                        "target": "geometry (user confirmation)",
                        "message": (
                            "Obtain user confirmation for the unconfirmed geometry "
                            "components and update G4ModelIR metadata."
                        ),
                    }
                ],
            }
        )

        assert review["status"] == "pass"
        assert review["routing_recommendation"] == "accept"
        assert review["required_fixes"] == []
        assert review["needs_user_input"] == []
        assert review["advisory_findings"]
        assert (
            _route_after_physics_quality_review(
                {
                    "physics_quality_review": review,
                    "physics_review_repair_attempts": 0,
                }
            )
            == "persist_codegen_output"
        )

    def test_physics_review_code_fixes_take_priority_over_user_input_route(self) -> None:
        """Code-level review fixes must go back to the project agent even if routing is noisy."""
        from agent_core.g4_codegen.physics_quality_reviewer import _normalize_review
        from agent_core.graph.subgraphs.g4_codegen_graph import (
            _route_after_physics_quality_review,
        )

        review = _normalize_review(
            {
                "status": "needs_user_input",
                "routing_recommendation": "request_user_input",
                "required_fixes": [
                    {
                        "target": "src/DetectorConstruction.cc",
                        "message": (
                            "Two G4PVPlacement layers overlap because z centers "
                            "use full thickness offsets; fix placement math and "
                            "keep CheckOverlaps enabled."
                        ),
                    }
                ],
                "needs_user_input": [
                    {
                        "target": "components.layers",
                        "message": "confirmed_by_user=false for layer thickness.",
                    }
                ],
            }
        )

        assert review["status"] == "revise"
        assert review["routing_recommendation"] == "repair_code"
        assert review["required_fixes"]
        assert review["needs_user_input"] == []
        assert (
            _route_after_physics_quality_review(
                {
                    "physics_quality_review": review,
                    "physics_review_repair_attempts": 0,
                }
            )
            == "geant4_project_agent"
        )

    def test_physics_review_code_fix_still_routes_to_project_agent(self) -> None:
        """Concrete project-file fixes should still be repairable."""
        from agent_core.g4_codegen.physics_quality_reviewer import _normalize_review
        from agent_core.graph.subgraphs.g4_codegen_graph import (
            _route_after_physics_quality_review,
        )

        review = _normalize_review(
            {
                "status": "revise",
                "required_fixes": [
                    {
                        "target": "src/OutputManager.cc",
                        "message": (
                            "Write particle_tracks.json from real track points; "
                            "the current file is empty."
                        ),
                    }
                ],
            }
        )

        assert review["routing_recommendation"] == "repair_code"
        assert review["required_fixes"]
        assert (
            _route_after_physics_quality_review(
                {
                    "physics_quality_review": review,
                    "physics_review_repair_attempts": 0,
                }
            )
            == "geant4_project_agent"
        )

    @pytest.mark.asyncio
    async def test_runtime_audit_failure_does_not_invoke_legacy_global_repair(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The full-project agent path should fail/continue, not fall back to old repair."""
        from agent_core.g4_codegen import graph_nodes

        async def fake_auditor(**_: object) -> dict[str, object]:
            return {
                "status": "fail",
                "blocking_errors": ["Missing output contract files"],
            }

        async def fail_global_repair(*_: object, **__: object) -> tuple[dict, dict]:
            raise AssertionError("runtime audit must not invoke legacy global repair")

        monkeypatch.setattr(
            "agent_core.g4_codegen.runtime_execution_auditor.run_runtime_execution_auditor",
            fake_auditor,
        )
        monkeypatch.setattr(
            "agent_core.g4_codegen.global_integration_agent.run_global_integration_agent",
            fail_global_repair,
        )

        result = await graph_nodes.runtime_execution_audit_node(
            {
                "job_id": "job_runtime_audit_no_legacy_repair",
                "proposed_patch": {
                    "changed_files": [{"path": "main.cc", "new_content": "int main(){}\n"}],
                    "metadata": {"source": "geant4_project_agent"},
                },
                "global_integration_agent_report": {"status": "passed"},
            }
        )

        assert result["runtime_execution_audit"]["status"] == "fail"
        assert result["current_node"] == "runtime_execution_audit"
        assert "global_integration_agent_report" not in result

    @pytest.mark.asyncio
    async def test_physics_review_failure_does_not_invoke_legacy_global_repair(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Physics review should report required fixes instead of re-entering old repair."""
        from agent_core.g4_codegen import graph_nodes

        async def fake_review(**_: object) -> dict[str, object]:
            return {
                "status": "fail",
                "required_fixes": [
                    {"target": "src/DetectorConstruction.cc", "message": "shield overlaps detector"}
                ],
            }

        async def fail_global_repair(*_: object, **__: object) -> tuple[dict, dict]:
            raise AssertionError("physics review must not invoke legacy global repair")

        monkeypatch.setattr(
            "agent_core.g4_codegen.physics_quality_reviewer.run_physics_quality_reviewer",
            fake_review,
        )
        monkeypatch.setattr(
            "agent_core.g4_codegen.global_integration_agent.run_global_integration_agent",
            fail_global_repair,
        )

        result = await graph_nodes.physics_quality_review_node(
            {
                "job_id": "job_physics_no_legacy_repair",
                "proposed_patch": {
                    "changed_files": [{"path": "main.cc", "new_content": "int main(){}\n"}],
                    "metadata": {"source": "geant4_project_agent"},
                },
                "global_integration_agent_report": {"status": "passed"},
            }
        )

        assert result["physics_quality_review"]["status"] == "fail"
        assert result["current_node"] == "physics_quality_review"
        assert "global_integration_agent_report" not in result

    @pytest.mark.asyncio
    async def test_persist_codegen_output_copies_project_agent_workspace(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Persist should expose the real project-agent project, not a minimal template."""
        from agent_core.g4_codegen.graph_nodes import persist_codegen_output_node
        from agent_core.g4_codegen.project_agent import PROJECT_AGENT_WORKSPACE

        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        job_dir = tmp_path / "jobs" / "job_persist_project_agent"
        project_dir = job_dir / PROJECT_AGENT_WORKSPACE
        project_dir.mkdir(parents=True)
        (project_dir / "main.cc").write_text(
            "// real project agent output\nint main(){return 0;}\n",
            encoding="utf-8",
        )
        (project_dir / "CMakeLists.txt").write_text("project(real_agent)\n", encoding="utf-8")
        (project_dir / "include").mkdir()
        (project_dir / "include" / "main.cc").write_text(
            "// invalid placeholder generated by model\n",
            encoding="utf-8",
        )
        stale_build = project_dir / "build"
        stale_build.mkdir()
        (stale_build / "CMakeCache.txt").write_text(
            "CMAKE_HOME_DIRECTORY:INTERNAL=/tmp/old/geant4_project\n",
            encoding="utf-8",
        )

        result = await persist_codegen_output_node(
            {
                "job_id": "job_persist_project_agent",
                "proposed_patch": {
                    "changed_files": [
                        {
                            "path": "main.cc",
                            "new_content": "// real project agent output\nint main(){return 0;}\n",
                        }
                    ],
                    "metadata": {"source": "geant4_project_agent"},
                },
                "global_integration_agent_report": {"status": "passed"},
                "runtime_execution_audit": {"status": "pass"},
                "physics_quality_review": {"status": "pass", "overall_score": 0.9},
            }
        )

        persisted_main = Path(result["generated_code_dir"]) / "main.cc"
        assert persisted_main.read_text(encoding="utf-8").startswith(
            "// real project agent output"
        )
        assert "silicon_detector" not in persisted_main.read_text(encoding="utf-8")
        assert not (Path(result["generated_code_dir"]) / "build").exists()
        assert not (Path(result["generated_code_dir"]) / "include" / "main.cc").exists()


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

    @pytest.mark.asyncio
    async def test_integration_assembler_node_surfaces_interface_audit_warnings(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Deterministic API audit findings should be visible in graph state."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        from agent_core.g4_codegen.graph_nodes import integration_assembler_node

        result = await integration_assembler_node(
            {
                "job_id": "job_interface_warning",
                "module_results": {
                    "simulation_core": {
                        "status": "generated",
                        "generated_files": [
                            {
                                "path": "include/PlacementManager.hh",
                                "new_content": (
                                    "#pragma once\n"
                                    "class PlacementManager {\n"
                                    "public:\n"
                                    "  void GetPhysicalVolume(const char* id) const;\n"
                                    "};\n"
                                ),
                            },
                            {
                                "path": "src/DetectorConstruction.cc",
                                "new_content": (
                                    '#include "PlacementManager.hh"\n'
                                    "void Build(PlacementManager* mgr) {\n"
                                    '  mgr->RegisterPhysicalVolume("world", nullptr);\n'
                                    "}\n"
                                ),
                            },
                        ],
                    }
                },
            }
        )

        warnings = result.get("codegen_warnings", [])
        assert any("RegisterPhysicalVolume" in warning for warning in warnings)

    @pytest.mark.asyncio
    async def test_persist_codegen_output_bootstraps_minimal_template_project(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Every codegen job should start from the canonical Geant4 scaffold."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        from agent_core.g4_codegen.graph_nodes import persist_codegen_output_node

        result = await persist_codegen_output_node(
            {
                "job_id": "job_template_bootstrap",
                "proposed_patch": {
                    "changed_files": [
                        {
                            "path": "main.cc",
                            "new_content": "int main() { return 0; }\n",
                            "module_name": "runtime_app",
                        }
                    ]
                },
                "module_results": {
                    "simulation_core": {"status": "generated"},
                    "beam_physics": {"status": "generated"},
                    "runtime_app": {"status": "generated"},
                },
                "runtime_execution_audit": {"status": "pass"},
                "physics_quality_review": {"status": "pass"},
            }
        )

        project_dir = Path(result["generated_code_dir"])
        assert (project_dir / "CMakeLists.txt").is_file()
        assert (project_dir / "include" / "OutputManager.hh").is_file()
        manifest = json.loads(
            (
                project_dir.parent.parent
                / "05_codegen"
                / "template_manifest.json"
            ).read_text(encoding="utf-8")
        )
        assert "macros/radagent_self_check_100.mac" in manifest["files"]

    @pytest.mark.asyncio
    async def test_persist_codegen_output_accepts_project_agent_patch_without_modules(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The full-project agent path should not require module_results."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        from agent_core.g4_codegen.graph_nodes import persist_codegen_output_node

        result = await persist_codegen_output_node(
            {
                "job_id": "job_project_agent_persist",
                "proposed_patch": {
                    "changed_files": [
                        {
                            "path": "main.cc",
                            "new_content": "int main() { return 0; }\n",
                            "module_name": "runtime_app",
                        }
                    ],
                    "metadata": {"source": "geant4_project_agent"},
                },
                "global_integration_agent_report": {"status": "passed"},
                "runtime_execution_audit": {"status": "pass"},
                "physics_quality_review": {"status": "pass"},
            }
        )

        assert result["g4_codegen_status"] == "passed"


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
        (
            "edited dimension components.water_tank.geometry = "
            '{"radius": "50 cm", "shape": "cylinder"}'
        )
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
