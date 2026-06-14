"""Tests for G4 Modeling Subgraph — compilation, state, and node wiring."""

from __future__ import annotations

import json
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

    def test_validation_errors_terminate_without_internal_retry(self) -> None:
        """Deterministic validation errors must not loop back without new feedback."""
        from agent_core.graph.subgraphs.g4_modeling_graph import (
            _route_after_model_ir_validation,
        )

        route = _route_after_model_ir_validation(
            {
                "model_ir_errors": ["physics evidence is placeholder"],
                "retry_count": 0,
            }
        )

        assert route == "persist_model_ir"

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

    async def test_requirement_capture_fills_core_modeling_draft_with_one_lite_call(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The modeling path should use one Lite extraction call, then stay deterministic."""
        from agent_core.g4_modeling.nodes.geometry_decomposition_node import (
            geometry_decomposition_node,
        )
        from agent_core.g4_modeling.nodes.physics_list_node import physics_list_node
        from agent_core.g4_modeling.nodes.requirement_capture_node import (
            requirement_capture_node,
        )
        from agent_core.models.schemas import (
            ModelCallResult,
            ModelProvider,
            ModelTask,
            ModelTier,
        )
        from agent_core.workspace.io import get_stage_dir
        from agent_core.workspace.paths import STAGE_MODEL_IR

        draft = {
            "target_system": "10 MeV proton beam on a 300 um silicon slab",
            "modeling_mode": "simple",
            "components": [
                {
                    "component_id": "world",
                    "display_name": "World",
                    "component_type": "world",
                    "geometry_type": "box",
                    "dimensions": {"dx": 50000.0, "dy": 50000.0, "dz": 50000.0},
                    "material_id": "Air",
                    "placement": {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]},
                    "mother_volume": None,
                    "sensitive": False,
                    "roles": [],
                    "source_evidence": ["lite draft: world envelope"],
                },
                {
                    "component_id": "silicon_slab",
                    "display_name": "Silicon slab",
                    "component_type": "volume",
                    "geometry_type": "box",
                    "dimensions": {"dx": 10000.0, "dy": 10000.0, "dz": 300.0},
                    "material_id": "Silicon",
                    "placement": {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]},
                    "mother_volume": "world",
                    "sensitive": True,
                    "roles": ["edep_region", "dose_scoring_region"],
                    "source_evidence": ["lite draft: silicon slab"],
                    "open_issues": [],
                    "requires_confirmation": False,
                },
            ],
            "physics": {
                "physics_list": "QGSP_BIC",
                "selection_reasoning": (
                    "Proton transport through silicon at 10 MeV needs hadronic "
                    "coverage, so QGSP_BIC is sufficient."
                ),
                "em_physics": "option4",
                "hadronic": "binary_cascade",
                "decay": True,
                "cuts": {"gamma": 0.1, "e-": 0.1},
                "hp_neutron": False,
                "source_evidence": ["lite draft: physics"],
            },
            "open_issues": [],
            "assumptions": [],
            "missing_information": [],
        }
        calls: list[dict[str, Any]] = []

        class LiteGateway:
            async def call(self, **kwargs: Any) -> ModelCallResult:
                calls.append(kwargs)
                return ModelCallResult(
                    task=ModelTask.SIMPLE_EXTRACTION,
                    tier=ModelTier.LITE,
                    provider=ModelProvider.MOCK,
                    model_name="test",
                    content=json.dumps(draft),
                    parsed_json=draft,
                )

        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        monkeypatch.setattr(
            "agent_core.models.gateway.get_model_gateway",
            lambda: LiteGateway(),
        )

        job_id = "job_lite_draft"
        model_ir_dir = get_stage_dir(job_id, STAGE_MODEL_IR)
        model_ir_dir.mkdir(parents=True, exist_ok=True)
        state = {
            "job_id": job_id,
            "user_query": (
                "Build a Geant4 simulation for 10 MeV protons on a 300 um silicon slab"
            ),
            "task_spec": {
                "particle": {
                    "type": "proton",
                    "energy_MeV": 10.0,
                    "energy_unit": "MeV",
                    "direction": [0.0, 0.0, 1.0],
                    "events": 1000,
                },
                "target": {
                    "material": "Silicon",
                    "size_um": [10000.0, 10000.0, 300.0],
                    "geometry_type": "box",
                },
                "outputs": ["edep", "dose_3d", "event_table"],
            },
        }

        captured = await requirement_capture_node(state)
        after_geometry = await geometry_decomposition_node(
            {
                "job_id": job_id,
                "task_spec": state["task_spec"],
                "g4_model_ir": captured["g4_model_ir"],
            }
        )
        after_physics = await physics_list_node(
            {
                "job_id": job_id,
                "task_spec": state["task_spec"],
                "g4_model_ir": after_geometry["g4_model_ir"],
            }
        )

        assert len(calls) == 1
        assert calls[0]["task"] == ModelTask.SIMPLE_EXTRACTION
        assert calls[0]["tier"] == ModelTier.LITE
        assert after_physics["g4_model_ir"]["components"][1]["component_id"] == "silicon_slab"
        assert after_physics["g4_model_ir"]["physics"]["physics_list"] == "QGSP_BIC"

    def test_lite_physics_evidence_is_normalized_before_validation(self) -> None:
        """Lite prose like 'default cuts' should not trip placeholder evidence gates."""
        from agent_core.g4_modeling.nodes.requirement_capture_node import (
            _normalize_physics_draft,
        )
        from agent_core.g4_modeling.schemas.physics_spec import PhysicsSpec
        from agent_core.g4_modeling.validators.no_simplification_validator import (
            NoSimplificationValidator,
        )

        normalized = _normalize_physics_draft(
            {
                "physics_list": "FTFP_BERT",
                "selection_reasoning": "10 MeV protons in silicon with hadronic secondaries.",
                "source_evidence": [
                    "User request: FTFP_BERT physics list with default cuts and secondaries"
                ],
            },
            {"physics_options": {"physics_list": "FTFP_BERT"}},
        )
        physics = PhysicsSpec.model_validate(normalized)

        errors: list[str] = []
        NoSimplificationValidator()._check_evidence(
            physics.physics_list,
            physics.source_evidence,
            "physics",
            errors,
            set(),
        )

        assert errors == []
        assert physics.source_evidence == [
            "task_spec.physics_options: physics_list=FTFP_BERT"
        ]

    async def test_lite_draft_component_materials_keep_scope_guard_unblocked(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Component material IDs from the Lite draft should satisfy material evidence."""
        from agent_core.g4_modeling.nodes.evidence_retrieval_node import (
            evidence_retrieval_node,
        )
        from agent_core.g4_modeling.nodes.model_scope_guard_node import (
            model_scope_guard_node,
        )
        from agent_core.g4_modeling.nodes.requirement_capture_node import (
            requirement_capture_node,
        )
        from agent_core.models.schemas import (
            ModelCallResult,
            ModelProvider,
            ModelTask,
            ModelTier,
        )
        from agent_core.workspace.io import get_stage_dir
        from agent_core.workspace.paths import STAGE_MODEL_IR

        draft = {
            "target_system": "10 MeV proton beam on 300 um silicon slab",
            "modeling_mode": "realistic",
            "components": [
                {
                    "component_id": "world",
                    "display_name": "World Volume",
                    "component_type": "world",
                    "geometry_type": "box",
                    "dimensions": {"dx": 50000.0, "dy": 50000.0, "dz": 50000.0},
                    "material_id": "G4_Galactic",
                    "mother_volume": None,
                    "source_evidence": ["lite draft: world material"],
                },
                {
                    "component_id": "silicon_slab",
                    "display_name": "Silicon slab",
                    "component_type": "volume",
                    "geometry_type": "box",
                    "dimensions": {"dx": 10000.0, "dy": 10000.0, "dz": 300.0},
                    "material_id": "G4_Si",
                    "mother_volume": "world",
                    "sensitive": True,
                    "roles": ["edep_region"],
                    "source_evidence": ["lite draft: silicon material"],
                },
            ],
            "physics": {
                "physics_list": "QGSP_BIC_HP",
                "selection_reasoning": "User requested QGSP_BIC_HP for 10 MeV protons.",
                "decay": True,
                "hp_neutron": True,
                "source_evidence": ["lite draft: physics"],
            },
            "required_outputs": ["edep"],
            "missing_information": [],
            "open_issues": [],
        }

        class LiteGateway:
            async def call(self, **_: Any) -> ModelCallResult:
                return ModelCallResult(
                    task=ModelTask.SIMPLE_EXTRACTION,
                    tier=ModelTier.LITE,
                    provider=ModelProvider.MOCK,
                    model_name="test",
                    content=json.dumps(draft),
                    parsed_json=draft,
                )

        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        monkeypatch.setattr(
            "agent_core.models.gateway.get_model_gateway",
            lambda: LiteGateway(),
        )
        job_id = "job_lite_scope_guard"
        get_stage_dir(job_id, STAGE_MODEL_IR).mkdir(parents=True, exist_ok=True)

        captured = await requirement_capture_node(
            {
                "job_id": job_id,
                "user_query": "Geant4 10 MeV protons on a G4_Si slab",
                "task_spec": {
                    "particle": {"type": "proton", "energy_MeV": 10.0},
                    "modeling_mode": "realistic",
                },
            }
        )
        evidenced = await evidence_retrieval_node(
            {
                "job_id": job_id,
                "g4_model_ir": captured["g4_model_ir"],
                "g4_context": [],
                "web_context": [],
                "context_decision": "block_no_context",
            }
        )
        guarded = await model_scope_guard_node(
            {
                "job_id": job_id,
                "g4_model_ir": evidenced["g4_model_ir"],
            }
        )

        requirements = json.loads(
            (get_stage_dir(job_id, STAGE_MODEL_IR) / "requirements.json").read_text()
        )
        assert {m["name"] for m in requirements["required_materials"]} >= {
            "G4_Galactic",
            "G4_Si",
        }
        assert evidenced["g4_model_ir"]["evidence"]["materials"]
        assert guarded["model_scope_guard_result"]["action"] == "proceed_with_warnings"

    async def test_material_definition_accepts_canonical_nist_names_with_evidence(
        self,
    ) -> None:
        """Canonical G4 material IDs from geometry should resolve as traceable NIST specs."""
        from agent_core.g4_modeling.nodes.material_definition_node import (
            material_definition_node,
        )

        model_ir = self._minimal_model_ir()
        model_ir["components"] = [
            {
                "component_id": "world",
                "display_name": "World Volume",
                "component_type": "world",
                "geometry_type": "box",
                "dimensions": {"dx": 100000.0, "dy": 100000.0, "dz": 100000.0},
                "material_id": "G4_AIR",
                "source_evidence": [
                    "Minimal simulation requires world volume to contain geometry"
                ],
            },
            {
                "component_id": "target_volume",
                "display_name": "Silicon target",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 10000.0, "dy": 10000.0, "dz": 1000.0},
                "material_id": "Silicon",
                "mother_volume": "world",
                "source_evidence": [
                    "target_system: 1 mm thick silicon slab",
                    "task_spec.target.size_um: structured target dimensions",
                ],
            },
        ]
        model_ir["materials"] = []
        model_ir["evidence"]["materials"] = [
            {
                "source_type": "user_requirement",
                "source": "requirements.json",
                "dimension": "materials",
                "text": '[{"name": "Silicon", "reason": "Target material from task specification"}]',
            }
        ]

        result = await material_definition_node({"job_id": "", "g4_model_ir": model_ir})
        materials = {
            mat["material_id"]: mat for mat in result["g4_model_ir"]["materials"]
        }

        assert materials["G4_AIR"]["classification"] == "nist"
        assert materials["G4_AIR"]["nist_name"] == "G4_AIR"
        assert materials["G4_AIR"]["source_evidence"]
        assert "world" in " ".join(materials["G4_AIR"]["source_evidence"])
        assert materials["Silicon"]["classification"] == "nist"
        assert materials["Silicon"]["nist_name"] == "G4_Si"
        assert "Silicon" in " ".join(materials["Silicon"]["source_evidence"])

    async def test_material_definition_knows_polyethylene_shielding_materials(
        self,
    ) -> None:
        """Showcase neutron shielding must not turn common shielding materials into placeholders."""
        from agent_core.g4_modeling.nodes.material_definition_node import (
            material_definition_node,
        )

        model_ir = self._minimal_model_ir()
        model_ir["components"] = [
            {
                "component_id": "world",
                "display_name": "World Volume",
                "component_type": "world",
                "geometry_type": "box",
                "dimensions": {"dx": 100000.0, "dy": 100000.0, "dz": 100000.0},
                "material_id": "G4_AIR",
                "source_evidence": ["world"],
            },
            {
                "component_id": "polyethylene_layer",
                "display_name": "Polyethylene Shielding Layer",
                "component_type": "shielding",
                "geometry_type": "box",
                "dimensions": {"dx": 500000.0, "dy": 500000.0, "dz": 20000.0},
                "material_id": "G4_POLYETHYLENE",
                "mother_volume": "world",
                "source_evidence": ["user request for polyethylene"],
            },
            {
                "component_id": "borated_polyethylene_layer",
                "display_name": "Borated Polyethylene Shielding Layer",
                "component_type": "shielding",
                "geometry_type": "box",
                "dimensions": {"dx": 500000.0, "dy": 500000.0, "dz": 20000.0},
                "material_id": "G4_BORATED_POLYETHYLENE",
                "mother_volume": "world",
                "source_evidence": ["user request for borated polyethylene"],
            },
        ]

        result = await material_definition_node({"job_id": "", "g4_model_ir": model_ir})
        materials = {
            mat["material_id"]: mat for mat in result["g4_model_ir"]["materials"]
        }

        assert materials["G4_POLYETHYLENE"]["name"] == "Polyethylene"
        assert materials["G4_POLYETHYLENE"]["open_issues"] == []
        assert materials["G4_BORATED_POLYETHYLENE"]["name"] == "Borated Polyethylene"
        assert materials["G4_BORATED_POLYETHYLENE"]["open_issues"] == []

    async def test_material_definition_covers_common_showcase_materials(
        self,
    ) -> None:
        """Common detector, shielding, phantom, and tracker materials should resolve deterministically."""
        from agent_core.g4_modeling.nodes.material_definition_node import (
            material_definition_node,
        )

        model_ir = self._minimal_model_ir()
        material_ids = [
            "G4_AIR",
            "Graphite",
            "Concrete",
            "StainlessSteel",
            "G4_Cd",
            "LiF",
            "G4_PLEXIGLASS",
            "Kapton",
            "G4_He",
            "G4_Ar",
            "G4_BGO",
        ]
        model_ir["components"] = [
            {
                "component_id": f"component_{index}",
                "display_name": f"{material_id} component",
                "component_type": "world" if index == 0 else "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 100000.0, "dy": 100000.0, "dz": 1000.0},
                "material_id": material_id,
                "mother_volume": None if index == 0 else "component_0",
                "source_evidence": [f"user requirement material {material_id}"],
            }
            for index, material_id in enumerate(material_ids)
        ]

        result = await material_definition_node({"job_id": "", "g4_model_ir": model_ir})
        materials = {
            mat["material_id"]: mat for mat in result["g4_model_ir"]["materials"]
        }

        for material_id in material_ids:
            assert material_id in materials
            assert materials[material_id]["open_issues"] == []
            assert materials[material_id]["source_evidence"]

        assert materials["Graphite"]["classification"] == "nist"
        assert materials["Graphite"]["nist_name"] == "G4_GRAPHITE"
        assert materials["Concrete"]["name"] == "Concrete"
        assert materials["StainlessSteel"]["name"] == "Stainless Steel"
        assert materials["LiF"]["name"] == "Lithium Fluoride"
        assert materials["G4_PLEXIGLASS"]["name"] == "PMMA / Plexiglass"
        assert materials["Kapton"]["name"] == "Kapton Polyimide"
        assert materials["G4_BGO"]["name"] == "Bismuth Germanate"

    async def test_material_definition_marks_unrecognized_material_for_confirmation_without_placeholder(
        self,
    ) -> None:
        """Unrecognized material references should stay traceable and reviewable, not become Unknown/default text."""
        from agent_core.g4_modeling.nodes.material_definition_node import (
            material_definition_node,
        )
        from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
        from agent_core.g4_modeling.validators.no_simplification_validator import (
            NoSimplificationValidator,
        )

        model_ir = self._minimal_model_ir()
        model_ir["components"] = [
            {
                "component_id": "target_volume",
                "display_name": "Target volume",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 10000.0, "dy": 10000.0, "dz": 1000.0},
                "material_id": "sample_material_pending_user_selection",
                "mother_volume": "world",
                "source_evidence": ["user_requirement: material not provided"],
            },
            {
                "component_id": "world",
                "display_name": "World Volume",
                "component_type": "world",
                "geometry_type": "box",
                "dimensions": {"dx": 100000.0, "dy": 100000.0, "dz": 100000.0},
                "material_id": "G4_AIR",
                "source_evidence": ["world volume envelope"],
            },
        ]

        result = await material_definition_node({"job_id": "", "g4_model_ir": model_ir})
        materials = {
            mat["material_id"]: mat for mat in result["g4_model_ir"]["materials"]
        }
        pending = materials["sample_material_pending_user_selection"]

        assert "Unknown" not in pending["name"]
        assert "default" not in " ".join(pending["source_evidence"]).lower()
        assert pending["open_issues"]
        assert "Silicon" not in pending["name"]

        fixed_ir = G4ModelIR.model_validate(result["g4_model_ir"])
        passed, errors = NoSimplificationValidator().validate(fixed_ir)
        assert passed, errors

    def test_geometry_fallback_marks_missing_component_material_for_confirmation(
        self,
    ) -> None:
        """When the user/model omits a material, geometry must request selection instead of assuming silicon."""
        from agent_core.g4_modeling.nodes.geometry_decomposition_node import (
            _fallback_components,
        )
        from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR

        model_ir = G4ModelIR.model_validate(self._minimal_model_ir())
        components = _fallback_components(
            model_ir,
            {
                "required_components": [
                    {
                        "component_id": "world",
                        "display_name": "World",
                        "component_type": "world",
                        "geometry_type": "box",
                        "material": "Air",
                    },
                    {
                        "component_id": "sample_detector",
                        "display_name": "Sample detector",
                        "component_type": "volume",
                        "geometry_type": "box",
                        "role": "dose scoring detector",
                        "dimensions": {"dx": 10000.0, "dy": 10000.0, "dz": 300.0},
                    },
                ]
            },
            {"outputs": ["dose_distribution"]},
        )
        detector = next(comp for comp in components if comp.component_id == "sample_detector")

        assert detector.material_id == "material_pending_user_selection"
        assert detector.requires_confirmation is True
        assert detector.open_issues
        assert "Silicon" not in detector.material_id

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

    async def test_scope_guard_allows_user_requirement_evidence_when_context_blocked(
        self,
    ) -> None:
        """Explicit user requirements should be enough to keep modeling alive."""
        from agent_core.g4_modeling.nodes.model_scope_guard_node import (
            model_scope_guard_node,
        )

        model_ir = self._minimal_model_ir()
        model_ir["evidence"] = {
            "evidence_decision": "block_no_context",
            "geometry": [{"source_type": "user_requirement", "text": "silicon slab"}],
            "materials": [{"source_type": "user_requirement", "text": "Silicon in air"}],
            "source": [{"source_type": "user_requirement", "text": "1 MeV electrons"}],
            "physics": [],
            "scoring": [{"source_type": "user_requirement", "text": "edep per event"}],
        }

        result = await model_scope_guard_node(
            {
                "simulation_scope": ["geant4"],
                "job_id": "test",
                "g4_model_ir": model_ir,
            }
        )

        guard = result.get("model_scope_guard_result", {})
        assert guard.get("action") == "proceed_with_warnings"
        assert "all — context blocked" not in guard.get("missing_dimensions", [])

    async def test_evidence_retrieval_backfills_local_physics_reference_when_context_missing(
        self,
    ) -> None:
        """Local Geant4 docs should cover physics when RAG/Web context is unavailable."""
        from agent_core.g4_modeling.nodes.evidence_retrieval_node import (
            evidence_retrieval_node,
        )

        result = await evidence_retrieval_node(
            {
                "job_id": "",
                "g4_model_ir": self._minimal_model_ir(),
                "g4_context": [],
                "web_context": [],
                "context_decision": "block_no_context",
            }
        )

        physics_evidence = result["g4_model_ir"]["evidence"]["physics"]
        assert physics_evidence
        assert any(
            item.get("source_type") == "local_geant4_reference"
            and "FTFP_BERT" in item.get("text", "")
            for item in physics_evidence
        )

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

    async def test_source_definition_uses_top_level_energy_and_events(self) -> None:
        """Planning output with top-level energy/events should still configure the source."""
        from agent_core.g4_modeling.nodes.source_definition_node import (
            source_definition_node,
        )

        result = await source_definition_node(
            {
                "job_id": "test",
                "g4_model_ir": self._minimal_model_ir(),
                "task_spec": {
                    "particle": {"type": "electron", "pdg_code": 11},
                    "energy": {"value": 1.0, "unit": "MeV"},
                    "events": 5,
                },
            }
        )

        source = result["g4_model_ir"]["sources"][0]
        assert source["particle_type"] == "electron"
        assert source["energy"]["value"] == 1.0
        assert source["energy"]["unit"] == "MeV"
        assert source["events"] == 5

    async def test_geometry_fallback_uses_task_target_and_required_components(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Offline geometry fallback should preserve user-requested target components."""
        from agent_core.g4_modeling.nodes.geometry_decomposition_node import (
            geometry_decomposition_node,
        )
        from agent_core.workspace.io import get_stage_dir
        from agent_core.workspace.paths import STAGE_MODEL_IR

        class FailingGateway:
            async def call(self, **_: Any) -> Any:
                raise RuntimeError("offline")

        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        monkeypatch.setattr(
            "agent_core.models.gateway.get_model_gateway",
            lambda: FailingGateway(),
        )
        job_id = "job_simple_slab"
        model_ir_dir = get_stage_dir(job_id, STAGE_MODEL_IR)
        model_ir_dir.mkdir(parents=True, exist_ok=True)
        (model_ir_dir / "requirements.json").write_text(
            json.dumps(
                {
                    "required_components": [
                        {
                            "component_id": "world_volume",
                            "display_name": "World Volume",
                            "component_type": "world",
                            "geometry_type": "box",
                            "material": "Air",
                            "role": "air environment",
                            "source": "inferred_from_context",
                        },
                        {
                            "component_id": "silicon_slab_detector",
                            "display_name": "Silicon Detector Slab",
                            "component_type": "volume",
                            "geometry_type": "box",
                            "material": "Silicon",
                            "role": "sensitive detector for energy deposition",
                            "source": "user_specified",
                        },
                    ],
                    "required_outputs": ["edep", "event_table", "edep_3d", "dose_3d"],
                }
            )
        )
        model_ir = self._minimal_model_ir()
        model_ir["target_system"] = "minimal silicon slab detector"
        model_ir["components"] = []

        result = await geometry_decomposition_node(
            {
                "job_id": job_id,
                "g4_model_ir": model_ir,
                "task_spec": {
                    "target": {
                        "material": "Silicon",
                        "geometry_type": "box",
                        "size_um": [10000.0, 10000.0, 1000.0],
                    },
                    "outputs": ["edep", "event_table", "dose_distribution"],
                },
            }
        )

        components = result["g4_model_ir"]["components"]
        slab = next(c for c in components if c["component_id"] == "silicon_slab_detector")
        assert {c["component_type"] for c in components} >= {"world", "volume"}
        assert slab["material_id"] == "Silicon"
        assert slab["dimensions"]["dz"] == 1000.0
        assert slab["sensitive"] is True
        assert "edep_region" in slab["roles"]
        assert result["g4_model_ir"]["interfaces"]

    async def test_geometry_decomposition_enriches_partial_llm_dimensions_from_task_spec(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """LLM geometry output should not discard structured task target dimensions."""
        from agent_core.g4_modeling.nodes.geometry_decomposition_node import (
            geometry_decomposition_node,
        )
        from agent_core.workspace.io import get_stage_dir
        from agent_core.workspace.paths import STAGE_MODEL_IR
        from agent_core.models.schemas import (
            ModelCallResult,
            ModelProvider,
            ModelTask,
            ModelTier,
        )

        class PartialGeometryGateway:
            async def call(self, **_: Any) -> ModelCallResult:
                return ModelCallResult(
                    task=ModelTask.G4_MODELING,
                    tier=ModelTier.PRO,
                    provider=ModelProvider.MOCK,
                    model_name="test",
                    content=json.dumps(
                        [
                            {
                                "component_id": "world_volume",
                                "display_name": "World Volume",
                                "component_type": "world",
                                "geometry_type": "box",
                                "dimensions": {},
                                "material_id": "Air",
                                "mother_volume": None,
                                "source_evidence": ["llm: world dimensions unspecified"],
                            },
                            {
                                "component_id": "silicon_slab",
                                "display_name": "Silicon Slab Detector",
                                "component_type": "volume",
                                "geometry_type": "box",
                                "dimensions": {"dz": 1000.0},
                                "material_id": "Silicon",
                                "mother_volume": "world_volume",
                                "sensitive": True,
                                "roles": ["detector", "scoring_volume"],
                                "source_evidence": ["llm: 1 mm thick silicon slab"],
                            },
                        ]
                    ),
                    parsed_json=None,
                )

        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        monkeypatch.setattr(
            "agent_core.models.gateway.get_model_gateway",
            lambda: PartialGeometryGateway(),
        )
        job_id = "job_partial_llm_geometry"
        model_ir_dir = get_stage_dir(job_id, STAGE_MODEL_IR)
        model_ir_dir.mkdir(parents=True, exist_ok=True)
        (model_ir_dir / "requirements.json").write_text(
            json.dumps(
                {
                    "required_components": [
                        {
                            "component_id": "world_volume",
                            "component_type": "world",
                            "geometry_type": "box",
                            "material": "Air",
                        },
                        {
                            "component_id": "silicon_slab",
                            "component_type": "volume",
                            "geometry_type": "box",
                            "material": "Silicon",
                            "role": "detector scoring volume",
                        },
                    ],
                    "required_outputs": ["edep", "dose_3d", "event_table"],
                }
            )
        )
        model_ir = self._minimal_model_ir()
        model_ir["target_system"] = "minimal silicon slab detector"
        model_ir["components"] = []

        result = await geometry_decomposition_node(
            {
                "job_id": job_id,
                "g4_model_ir": model_ir,
                "task_spec": {
                    "target": {
                        "material": "Silicon",
                        "geometry_type": "box",
                        "size_um": [10000.0, 10000.0, 1000.0],
                    },
                    "outputs": ["energy_deposition_map", "dose_distribution"],
                    "metadata": {
                        "target_lateral_extent_assumption": (
                            "Target lateral dimensions inferred for minimal geometry."
                        )
                    },
                },
            }
        )

        components = result["g4_model_ir"]["components"]
        world = next(c for c in components if c["component_id"] == "world_volume")
        slab = next(c for c in components if c["component_id"] == "silicon_slab")

        assert slab["dimensions"] == {"dx": 10000.0, "dy": 10000.0, "dz": 1000.0}
        assert world["dimensions"] == {"dx": 50000.0, "dy": 50000.0, "dz": 50000.0}
        assert "task_spec.target.size_um" in " ".join(slab["source_evidence"])
        assert "task_spec.target.size_um" in " ".join(world["source_evidence"])

    async def test_geometry_keeps_downstream_detector_outside_shielding_stack(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Shielding showcase geometry should not place detector inside the stack envelope."""
        from agent_core.g4_modeling.nodes.geometry_decomposition_node import (
            geometry_decomposition_node,
        )
        from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
        from agent_core.g4_modeling.validators.overlap_policy_validator import (
            OverlapPolicyValidator,
        )

        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        model_ir = self._minimal_model_ir()
        model_ir["target_system"] = "14 MeV neutron shielding stack with downstream silicon detector"
        model_ir["components"] = [
            {
                "component_id": "world",
                "display_name": "World Volume",
                "component_type": "world",
                "geometry_type": "box",
                "dimensions": {"dx": 1000000.0, "dy": 1000000.0, "dz": 2000000.0},
                "material_id": "G4_AIR",
                "placement": {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]},
                "mother_volume": None,
                "source_evidence": ["standard Geant4 world volume"],
            },
            {
                "component_id": "shielding_stack",
                "display_name": "Shielding Stack Assembly",
                "component_type": "assembly",
                "geometry_type": "box",
                "dimensions": {"dx": 500000.0, "dy": 500000.0, "dz": 100000.0},
                "material_id": "G4_AIR",
                "placement": {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]},
                "mother_volume": "world",
                "source_evidence": ["user request for material stack"],
            },
            {
                "component_id": "polyethylene_layer",
                "display_name": "Polyethylene Shielding Layer",
                "component_type": "shielding",
                "geometry_type": "box",
                "dimensions": {"dx": 500000.0, "dy": 500000.0, "dz": 20000.0},
                "material_id": "G4_POLYETHYLENE",
                "placement": {"position": [0.0, 0.0, -40000.0], "rotation": [0.0, 0.0, 0.0]},
                "mother_volume": "shielding_stack",
                "source_evidence": ["user request for polyethylene"],
            },
            {
                "component_id": "borated_polyethylene_layer",
                "display_name": "Borated Polyethylene Shielding Layer",
                "component_type": "shielding",
                "geometry_type": "box",
                "dimensions": {"dx": 500000.0, "dy": 500000.0, "dz": 20000.0},
                "material_id": "G4_BORATED_POLYETHYLENE",
                "placement": {"position": [0.0, 0.0, -20000.0], "rotation": [0.0, 0.0, 0.0]},
                "mother_volume": "shielding_stack",
                "source_evidence": ["user request for borated polyethylene"],
            },
            {
                "component_id": "lead_layer",
                "display_name": "Lead Shielding Layer",
                "component_type": "shielding",
                "geometry_type": "box",
                "dimensions": {"dx": 500000.0, "dy": 500000.0, "dz": 20000.0},
                "material_id": "G4_Pb",
                "placement": {"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]},
                "mother_volume": "shielding_stack",
                "source_evidence": ["user request for lead"],
            },
            {
                "component_id": "silicon_detector",
                "display_name": "Silicon Detector",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 100000.0, "dy": 100000.0, "dz": 500.0},
                "material_id": "G4_Si",
                "placement": {"position": [0.0, 0.0, 30000.0], "rotation": [0.0, 0.0, 0.0]},
                "mother_volume": "world",
                "sensitive": True,
                "roles": ["edep_region", "dose_scoring_region"],
                "source_evidence": ["user request for downstream silicon detector"],
            },
        ]

        result = await geometry_decomposition_node(
            {
                "job_id": "test",
                "g4_model_ir": model_ir,
                "task_spec": {},
            }
        )

        fixed_ir = G4ModelIR.model_validate(result["g4_model_ir"])
        passed, errors = OverlapPolicyValidator().validate(fixed_ir)
        assert passed, errors
        detector = next(
            comp for comp in result["g4_model_ir"]["components"] if comp["component_id"] == "silicon_detector"
        )
        assert detector["placement"]["position"][2] >= 50500.0

    async def test_scoring_design_creates_edep_and_dose_voxel_scores(self) -> None:
        """3D edep and dose roles should both become explicit scoring specs."""
        from agent_core.g4_modeling.nodes.scoring_design_node import scoring_design_node

        model_ir = self._minimal_model_ir()
        model_ir["components"].append(
            {
                "component_id": "silicon_slab_detector",
                "display_name": "Silicon Detector Slab",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 10000.0, "dy": 10000.0, "dz": 1000.0},
                "material_id": "G4_AIR",
                "mother_volume": "world",
                "sensitive": True,
                "roles": [
                    "edep_region",
                    "dose_scoring_region",
                    "3d_edep_map",
                    "3d_dose_map",
                ],
                "source_evidence": ["user_spec: silicon slab"],
            }
        )
        model_ir["sensitive_detectors"] = [
            {
                "sd_id": "silicon_slab_detector_sd",
                "name": "SiliconSlabDetectorSensitiveDetector",
                "linked_component_ids": ["silicon_slab_detector"],
                "collection_name": "silicon_slab_detector_Hits",
                "hit_fields": [{"name": "edep_MeV", "dtype": "float", "unit": "MeV"}],
            }
        ]

        result = await scoring_design_node({"job_id": "test", "g4_model_ir": model_ir})
        scoring_ids = {sc["scoring_id"] for sc in result["g4_model_ir"]["scoring"]}

        assert "silicon_slab_detector_voxel_dose" in scoring_ids
        assert "silicon_slab_detector_voxel_edep" in scoring_ids

    async def test_scoring_design_uses_requested_output_aliases_for_voxel_scores(
        self,
    ) -> None:
        """3D output aliases from requirements/task_spec should create voxel scores."""
        from agent_core.g4_modeling.nodes.scoring_design_node import scoring_design_node

        model_ir = self._minimal_model_ir()
        model_ir["components"].append(
            {
                "component_id": "silicon_slab",
                "display_name": "Silicon Slab Detector",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 10000.0, "dy": 10000.0, "dz": 1000.0},
                "material_id": "G4_Si",
                "mother_volume": "world",
                "sensitive": True,
                "roles": [
                    "electron_target",
                    "energy_scoring_volume",
                    "dose_scoring_volume",
                ],
                "source_evidence": ["requirements.json: silicon slab"],
            }
        )
        model_ir["sensitive_detectors"] = [
            {
                "sd_id": "silicon_slab_sd",
                "name": "SiliconSlabSensitiveDetector",
                "linked_component_ids": ["silicon_slab"],
                "collection_name": "silicon_slab_Hits",
                "hit_fields": [{"name": "edep_MeV", "dtype": "float", "unit": "MeV"}],
            }
        ]
        model_ir["evidence"]["scoring"] = [
            {
                "source_type": "user_requirement",
                "source": "requirements.json",
                "text": json.dumps(
                    [
                        "energy_deposition_per_event",
                        "energy_deposition_3d_map",
                        "dose_distribution_3d",
                    ]
                ),
            }
        ]

        result = await scoring_design_node(
            {
                "job_id": "test",
                "g4_model_ir": model_ir,
                "task_spec": {
                    "outputs": [
                        "energy_deposition_map",
                        "energy_deposition",
                        "dose_distribution",
                        "event_data",
                    ]
                },
            }
        )
        scoring_ids = {sc["scoring_id"] for sc in result["g4_model_ir"]["scoring"]}

        assert "silicon_slab_voxel_edep" in scoring_ids
        assert "silicon_slab_voxel_dose" in scoring_ids
        assert "silicon_slab_dose" in scoring_ids

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

    async def test_physics_list_fallback_uses_available_evidence(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Offline model selection should still emit traceable evidence, not placeholders."""
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
                "source_id": "electron_source",
                "particle_type": "electron",
                "energy": {"value": 1.0, "unit": "MeV", "distribution": "mono"},
                "beam": {
                    "position": [0.0, 0.0, -500.0],
                    "direction": [0.0, 0.0, 1.0],
                },
                "generator_type": "gun",
                "events": 5,
                "source_evidence": ["task_spec.particle: electron 1.0 MeV"],
            }
        ]
        model_ir["evidence"]["physics"] = [
            {
                "source_type": "local_geant4_reference",
                "source": "geant4_reference:g4_phys_list_factory",
                "title": "G4PhysListFactory — Reference Physics List Factory",
                "text": "G4PhysListFactory creates Geant4 reference physics lists such as FTFP_BERT.",
            }
        ]

        result = await physics_list_node(
            {
                "job_id": "test",
                "g4_model_ir": model_ir,
                "task_spec": {},
            }
        )
        physics = result["g4_model_ir"]["physics"]

        assert physics["physics_list"] == "FTFP_BERT"
        assert physics["source_evidence"] == [
            "local_geant4_reference: geant4_reference:g4_phys_list_factory"
        ]

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
