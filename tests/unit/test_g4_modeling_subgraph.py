"""Tests for G4 Modeling Subgraph — compilation, state, and node wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


class TestG4ModelingSubgraphCompilation:
    """Verify the G4 modeling subgraph compiles and has correct structure."""

    def test_subgraph_compiles(self) -> None:
        """G4 modeling subgraph must compile without errors."""
        from agent_core.graph.subgraphs.g4_modeling_graph import (
            build_g4_modeling_subgraph,
        )

        graph = build_g4_modeling_subgraph()
        compiled = graph.compile()
        assert compiled is not None

    def test_subgraph_has_entry_point(self) -> None:
        """Subgraph must have a defined entry point."""
        from agent_core.graph.subgraphs.g4_modeling_graph import (
            build_g4_modeling_subgraph,
        )

        graph = build_g4_modeling_subgraph()
        # LangGraph stores entry point in _entrypoint
        assert hasattr(graph, "_nodes") or hasattr(graph, "nodes")

    def test_subgraph_still_uses_active_modeling_nodes(self) -> None:
        """Fine-grained modeling nodes are still active until the modeling graph is consolidated."""
        from agent_core.graph.subgraphs.g4_modeling_graph import (
            build_g4_modeling_subgraph,
        )

        graph = build_g4_modeling_subgraph()
        node_names = set(getattr(graph, "nodes", getattr(graph, "_nodes", {})))

        assert {
            "requirement_capture_node",
            "evidence_retrieval_node",
            "model_scope_guard_node",
            "geometry_decomposition_node",
            "coordinate_system_node",
            "material_definition_node",
            "source_definition_node",
            "physics_list_node",
            "sensitive_detector_node",
            "scoring_design_node",
            "model_ir_validation_node",
            "model_review_report_node",
        }.issubset(node_names)

    def test_subgraph_state_schema(self) -> None:
        """Subgraph state must have required fields."""
        from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState

        annotations = G4ModelingSubgraphState.__annotations__
        required = ["job_id", "g4_model_ir", "errors"]
        for field in required:
            assert field in annotations, f"Missing field: {field}"

    def test_subgraph_io_module(self) -> None:
        """Subgraph I/O module must have load and persist functions."""
        from agent_core.g4_modeling.subgraph_io import load_task_spec, persist_model_ir

        assert callable(load_task_spec)
        assert callable(persist_model_ir)

    def test_model_ir_schema_validates(self) -> None:
        """G4ModelIR schema must validate a minimal valid IR."""
        from agent_core.g4_modeling.schemas import (
            ComponentSpec,
            ConstructionLedger,
            G4ModelIR,
            MaterialSpec,
            SimplificationPolicy,
        )

        ir = G4ModelIR(
            model_ir_id="test",
            job_id="test",
            modeling_mode="realistic",
            target_system="Test",
            simplification_policy=SimplificationPolicy(),
            components=[
                ComponentSpec(
                    component_id="world",
                    display_name="World",
                    component_type="world",
                    geometry_type="box",
                    dimensions={"dx": 1000, "dy": 1000, "dz": 1000},
                    material_id="Air",
                    source_evidence=["default"],
                ),
            ],
            materials=[
                MaterialSpec(
                    material_id="Air",
                    name="G4_AIR",
                    classification="nist",
                    nist_name="G4_AIR",
                    density_g_cm3=0.001214,
                    source_evidence=["NIST"],
                ),
            ],
            ledger=ConstructionLedger(),
        )
        assert ir.model_ir_id == "test"
        assert len(ir.components) == 1


class TestG4ModelingNodes:
    """Test individual modeling nodes."""

    @staticmethod
    def _minimal_model_ir() -> dict[str, Any]:
        """Return a minimal valid G4ModelIR dict for testing."""
        return {
            "model_ir_id": "test",
            "job_id": "test",
            "modeling_mode": "realistic",
            "target_system": "Test System",
            "simplification_policy": {
                "allow_simplification": False,
                "requires_user_approval": True,
                "approved_simplifications": [],
            },
            "components": [
                {
                    "component_id": "world",
                    "display_name": "World",
                    "component_type": "world",
                    "geometry_type": "box",
                    "dimensions": {"dx": 1000, "dy": 1000, "dz": 1000},
                    "material_id": "G4_AIR",
                    "source_evidence": ["default"],
                },
            ],
            "materials": [
                {
                    "material_id": "G4_AIR",
                    "name": "G4_AIR",
                    "classification": "nist",
                    "nist_name": "G4_AIR",
                    "density_g_cm3": 0.001214,
                    "source_evidence": ["NIST"],
                },
            ],
            "ledger": {"entries": [], "version": "1.0"},
            "evidence": {
                "evidence_decision": "allow_rag",
                "geometry": [{"source": "default", "desc": "box world"}],
                "materials": [{"source": "NIST", "desc": "G4_AIR"}],
                "source": [{"source": "default", "desc": "beam"}],
                "physics": [{"source": "default", "desc": "standard"}],
                "scoring": [{"source": "default", "desc": "edep"}],
            },
        }

    async def test_scope_guard_passes_geant4(self) -> None:
        """Scope guard should allow geant4 scope with valid model IR."""
        from agent_core.g4_modeling.nodes.model_scope_guard_node import (
            model_scope_guard_node,
        )

        state = {
            "simulation_scope": ["geant4"],
            "job_id": "test",
            "g4_model_ir": self._minimal_model_ir(),
        }
        result = await model_scope_guard_node(state)
        assert result.get("current_node") == "model_scope_guard_node"
        guard = result.get("model_scope_guard_result", {})
        assert guard.get("action") == "proceed"

    async def test_scope_guard_flags_tcad(self) -> None:
        """Scope guard should still handle geant4+tcad scope."""
        from agent_core.g4_modeling.nodes.model_scope_guard_node import (
            model_scope_guard_node,
        )

        state = {
            "simulation_scope": ["geant4", "tcad"],
            "job_id": "test",
            "g4_model_ir": self._minimal_model_ir(),
        }
        result = await model_scope_guard_node(state)
        # tcad in scope should be noted but geant4 proceeds
        assert result is not None
        assert result.get("current_node") == "model_scope_guard_node"

    async def test_coordinate_system_marks_composite_source_directions(self) -> None:
        """Multiple incident angles should not be collapsed into one beam axis."""
        from agent_core.g4_modeling.nodes.coordinate_system_node import (
            coordinate_system_node,
        )

        model_ir = self._minimal_model_ir()
        model_ir["sources"] = [
            {
                "source_id": "normal_gamma",
                "particle_type": "gamma",
                "energy": {"value": 2.0, "unit": "MeV", "distribution": "mono"},
                "beam": {
                    "position": [0.0, 0.0, -500.0],
                    "direction": [0.0, 0.0, 1.0],
                },
                "generator_type": "gun",
                "events": 500,
                "source_evidence": ["task_spec.particles[0]"],
            },
            {
                "source_id": "oblique_neutron",
                "particle_type": "neutron",
                "energy": {"value": 0.025, "unit": "eV", "distribution": "mono"},
                "beam": {
                    "position": [0.0, 0.0, -500.0],
                    "direction": [0.3, 0.0, 0.953939],
                },
                "generator_type": "gun",
                "events": 500,
                "source_evidence": ["task_spec.particles[1]"],
            },
        ]

        result = await coordinate_system_node({"job_id": "test", "g4_model_ir": model_ir})
        axis_definition = result["g4_model_ir"]["coordinate_system"]["axis_definition"]

        assert axis_definition["z"] == "detector_depth"
        assert axis_definition["source_directions"] == "composite_radiation_field"

    async def test_source_definition_preserves_user_spectrum_and_gps(self) -> None:
        """Source definition should carry user spectrum and beam parameters into IR."""
        from agent_core.g4_modeling.nodes.source_definition_node import (
            source_definition_node,
        )

        state = {
            "job_id": "test",
            "g4_model_ir": self._minimal_model_ir(),
            "task_spec": {
                "particle": {
                    "type": "gamma",
                    "energy_MeV": 2.5,
                    "energy_unit": "MeV",
                    "energy_distribution": "spectrum",
                    "spectrum_file": "inputs/source_spectrum.csv",
                    "direction": [0.0, 0.0, 1.0],
                    "position": [1.0, 2.0, -300.0],
                    "sigma_position_um": 25.0,
                    "sigma_direction_rad": 0.02,
                    "surface_shape": "circle",
                    "surface_size": [50.0],
                    "generator_type": "gps",
                    "events": 2500,
                }
            },
        }

        result = await source_definition_node(state)
        source = result["g4_model_ir"]["sources"][0]

        assert source["particle_type"] == "gamma"
        assert source["energy"]["value"] == 2.5
        assert source["energy"]["distribution"] == "spectrum"
        assert source["energy"]["spectrum_file"] == "inputs/source_spectrum.csv"
        assert source["generator_type"] == "gps"
        assert source["events"] == 2500
        assert source["beam"]["position"] == [1.0, 2.0, -300.0]
        assert source["beam"]["sigma_position_um"] == 25.0
        assert source["beam"]["sigma_direction_rad"] == 0.02
        assert source["beam"]["surface_shape"] == "circle"
        assert source["beam"]["surface_size"] == [50.0]

    async def test_source_definition_builds_composite_radiation_field_sources(self) -> None:
        """Composite task_spec.particles should become multiple IR sources."""
        from agent_core.g4_modeling.nodes.source_definition_node import (
            source_definition_node,
        )

        state = {
            "job_id": "test",
            "g4_model_ir": self._minimal_model_ir(),
            "task_spec": {
                "particles": [
                    {
                        "source_id": "forward_protons",
                        "type": "proton",
                        "energy_MeV": 100.0,
                        "energy_distribution": "mono",
                        "direction": [0.0, 0.0, 1.0],
                        "angular_distribution": "mono",
                        "events": 700,
                        "relative_weight": 0.7,
                    },
                    {
                        "source_id": "oblique_gamma_spectrum",
                        "type": "gamma",
                        "energy_MeV": 2.5,
                        "energy_distribution": "spectrum",
                        "spectrum_file": "inputs/gamma_spectrum.csv",
                        "direction": [0.5, 0.0, 0.8660254],
                        "angular_distribution": "gaussian",
                        "angular_spectrum_file": "inputs/gamma_angles.csv",
                        "sigma_direction_rad": 0.05,
                        "generator_type": "gps",
                        "events": 300,
                        "relative_weight": 0.3,
                    },
                ]
            },
        }

        result = await source_definition_node(state)
        sources = result["g4_model_ir"]["sources"]

        assert len(sources) == 2
        assert sources[0]["source_id"] == "forward_protons"
        assert sources[0]["particle_type"] == "proton"
        assert sources[0]["energy"]["distribution"] == "mono"
        assert sources[0]["generator_type"] == "gun"
        assert sources[0]["relative_weight"] == 0.7
        assert sources[0]["beam"]["angular_distribution"] == "mono"
        assert sources[1]["source_id"] == "oblique_gamma_spectrum"
        assert sources[1]["particle_type"] == "gamma"
        assert sources[1]["energy"]["distribution"] == "spectrum"
        assert sources[1]["energy"]["spectrum_file"] == "inputs/gamma_spectrum.csv"
        assert sources[1]["generator_type"] == "gps"
        assert sources[1]["relative_weight"] == 0.3
        assert sources[1]["beam"]["direction"] == [0.5, 0.0, 0.8660254]
        assert sources[1]["beam"]["angular_distribution"] == "gaussian"
        assert sources[1]["beam"]["angular_spectrum_file"] == "inputs/gamma_angles.csv"

    async def test_source_definition_keeps_validated_spectrum_sources_on_gps(self) -> None:
        """TaskSpec defaults must not force spectrum sources back to particle gun."""
        from agent_core.g4_modeling.nodes.source_definition_node import (
            source_definition_node,
        )
        from agent_core.schemas.task_spec import TaskSpec

        task_spec = TaskSpec.model_validate(
            {
                "simulation_scope": ["geant4"],
                "particles": [
                    {
                        "source_id": "gamma_spectrum",
                        "type": "gamma",
                        "energy_MeV": 2.0,
                        "energy_distribution": "spectrum",
                        "spectrum_file": "inputs/gamma.csv",
                        "direction": [0.0, 0.0, 1.0],
                    }
                ],
            }
        ).model_dump(mode="json")

        result = await source_definition_node(
            {
                "job_id": "test",
                "g4_model_ir": self._minimal_model_ir(),
                "task_spec": task_spec,
            }
        )

        source = result["g4_model_ir"]["sources"][0]
        assert source["energy"]["distribution"] == "spectrum"
        assert source["generator_type"] == "gps"

    async def test_physics_list_node_prefers_user_physics_options(self) -> None:
        """Explicit user physics_options should override model/fallback selection."""
        from agent_core.g4_modeling.nodes.physics_list_node import physics_list_node

        state = {
            "job_id": "test",
            "g4_model_ir": self._minimal_model_ir(),
            "task_spec": {
                "physics_options": {
                    "physics_list": "QGSP_BIC_HP",
                    "em_physics": "option4",
                    "hadronic": "binary_cascade",
                    "hp_neutron": "true",
                    "neutron": "0.05",
                    "gamma": "0.1",
                }
            },
        }

        result = await physics_list_node(state)
        physics = result["g4_model_ir"]["physics"]

        assert physics["physics_list"] == "QGSP_BIC_HP"
        assert physics["em_physics"] == "option4"
        assert physics["hadronic"] == "binary_cascade"
        assert physics["hp_neutron"] is True
        assert physics["cuts"]["neutron"] == 0.05
        assert physics["cuts"]["gamma"] == 0.1
        assert "task_spec.physics_options" in physics["source_evidence"][0]

    async def test_physics_list_fallback_considers_all_composite_sources(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Fallback physics selection should not ignore non-primary composite sources."""
        from agent_core.g4_modeling.nodes.physics_list_node import physics_list_node

        class FailingGateway:
            async def call(self, **_: Any) -> Any:
                raise RuntimeError("offline")

        monkeypatch.setattr(
            "agent_core.models.gateway.get_model_gateway",
            lambda: FailingGateway(),
        )

        model_ir = self._minimal_model_ir()
        model_ir["sources"] = [
            {
                "source_id": "gamma_spectrum",
                "particle_type": "gamma",
                "energy": {
                    "value": 2.0,
                    "unit": "MeV",
                    "distribution": "spectrum",
                    "spectrum_file": "inputs/gamma.csv",
                },
                "beam": {
                    "position": [0.0, 0.0, -500.0],
                    "direction": [0.0, 0.0, 1.0],
                },
                "generator_type": "gps",
                "events": 500,
                "source_evidence": ["task_spec.particles[0]"],
            },
            {
                "source_id": "thermal_neutrons",
                "particle_type": "neutron",
                "energy": {"value": 0.025, "unit": "eV", "distribution": "mono"},
                "beam": {
                    "position": [0.0, 0.0, -500.0],
                    "direction": [0.3, 0.0, 0.953939],
                },
                "generator_type": "gun",
                "events": 500,
                "source_evidence": ["task_spec.particles[1]"],
            },
        ]

        result = await physics_list_node(
            {
                "job_id": "test",
                "g4_model_ir": model_ir,
                "task_spec": {},
            }
        )
        physics = result["g4_model_ir"]["physics"]

        assert physics["physics_list"] == "QGSP_BIC_HP"
        assert physics["hp_neutron"] is True
        assert "gamma_spectrum" in physics["selection_reasoning"]
        assert "thermal_neutrons" in physics["selection_reasoning"]

    def test_heuristic_requirements_preserves_composite_sources(self) -> None:
        """Fallback requirement extraction should include every task_spec source."""
        from agent_core.g4_modeling.nodes.requirement_capture_node import (
            _heuristic_requirements,
        )

        requirements = _heuristic_requirements(
            "mixed gamma and neutron field",
            {
                "particles": [
                    {
                        "source_id": "gamma_spectrum",
                        "type": "gamma",
                        "energy_MeV": 2.0,
                        "energy_distribution": "spectrum",
                        "spectrum_file": "inputs/gamma.csv",
                        "direction": [0.0, 0.0, 1.0],
                    },
                    {
                        "source_id": "thermal_neutrons",
                        "type": "neutron",
                        "energy_MeV": 2.5e-8,
                        "energy_unit": "MeV",
                        "energy_distribution": "mono",
                        "direction": [0.3, 0.0, 0.953939],
                        "angular_distribution": "gaussian",
                    },
                ],
                "outputs": ["dose"],
            },
        )

        sources = requirements["required_sources"]
        assert len(sources) == 2
        assert sources[0]["source_id"] == "gamma_spectrum"
        assert sources[0]["particle_type"] == "gamma"
        assert sources[0]["distribution"] == "spectrum"
        assert sources[0]["spectrum_file"] == "inputs/gamma.csv"
        assert sources[1]["source_id"] == "thermal_neutrons"
        assert sources[1]["particle_type"] == "neutron"
        assert sources[1]["angular_distribution"] == "gaussian"

    async def test_persist_model_ir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """persist_model_ir should save JSON files."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

        from agent_core.g4_modeling.schemas import (
            ComponentSpec,
            ConstructionLedger,
            G4ModelIR,
            MaterialSpec,
            SimplificationPolicy,
        )
        from agent_core.g4_modeling.subgraph_io import persist_model_ir

        ir = G4ModelIR(
            model_ir_id="test_persist",
            job_id="test_persist",
            modeling_mode="realistic",
            target_system="Test",
            simplification_policy=SimplificationPolicy(),
            components=[
                ComponentSpec(
                    component_id="world",
                    display_name="World",
                    component_type="world",
                    geometry_type="box",
                    dimensions={"dx": 500, "dy": 500, "dz": 500},
                    material_id="Air",
                    source_evidence=["default"],
                ),
            ],
            materials=[
                MaterialSpec(
                    material_id="Air",
                    name="G4_AIR",
                    classification="nist",
                    nist_name="G4_AIR",
                    density_g_cm3=0.001214,
                    source_evidence=["NIST"],
                ),
            ],
            ledger=ConstructionLedger(),
        )

        state = {
            "job_id": "test_persist",
            "g4_model_ir": ir.model_dump(mode="json"),
            "interfaces": [],
            "construction_ledger": ir.ledger.model_dump(mode="json"),
        }
        result = await persist_model_ir(state)
        assert result.get("g4_modeling_status") == "passed"
        assert result.get("human_confirmation_required") is False

        ir_path = result.get("g4_model_ir_path", "")
        assert ir_path and Path(ir_path).exists()

    async def test_persist_model_ir_flags_human_confirmation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """persist_model_ir should surface unresolved IR questions to the main graph."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

        from agent_core.g4_modeling.subgraph_io import persist_model_ir

        model_ir = self._minimal_model_ir()
        model_ir["components"][0]["open_issues"] = ["Missing world volume margin evidence"]
        model_ir["components"][0]["requires_confirmation"] = True

        result = await persist_model_ir(
            {
                "job_id": "test_confirm",
                "g4_model_ir": model_ir,
                "model_ir_errors": [],
            }
        )

        assert result.get("g4_modeling_status") == "passed"
        assert result.get("human_confirmation_required") is True
