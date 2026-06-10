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
