"""Tests for human_confirmation subgraph nodes."""

import json
from pathlib import Path

import pytest
from agent_core.human_confirmation.nodes import (
    HumanConfirmationState,
    _get_confirmation_dir,
    _load_json,
    _save_json,
    build_proposed_model_completion,
    generate_confirmation_request,
    human_interrupt_node,
    merge_user_confirmation,
    parse_confirmation_response,
    validate_confirmation_completeness,
)
from agent_core.human_confirmation.schemas import (
    ConfirmationRecord,
    ConfirmationRequest,
    ConfirmationResponse,
    ProposedModelCompletion,
)
from agent_core.workspace.paths import STAGE_HUMAN_CONFIRMATION, STAGE_MODEL_IR


@pytest.fixture
def temp_job_dir(tmp_path):
    """Create a temporary job directory structure."""
    job_dir = tmp_path / "jobs" / "test-job-123"
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


@pytest.fixture
def sample_model_ir(temp_job_dir):
    """Create sample model IR for testing."""
    ir_path = temp_job_dir / STAGE_MODEL_IR / "g4_model_ir.json"
    ir_path.parent.mkdir(parents=True, exist_ok=True)
    ir_data = {
        "components": [
            {
                "component_id": "water_tank",
                "component_type": "volume",
                "material_id": "G4_WATER",
                "geometry": {"x": 10.0, "y": 10.0, "z": 10.0},
                "roles": ["target"],
            }
        ],
        "sources": [
            {
                "source_id": "primary",
                "particle_type": "proton",
                "energy": "150 MeV",
            }
        ],
        "scoring": [
            {
                "scoring_id": "dose",
                "scoring_type": "dose",
            }
        ],
    }
    ir_path.write_text(json.dumps(ir_data), encoding="utf-8")
    return str(ir_path)


@pytest.fixture
def sample_evidence_map(temp_job_dir):
    """Create sample evidence map for testing."""
    ev_path = temp_job_dir / STAGE_MODEL_IR / "evidence_map.json"
    ev_path.parent.mkdir(parents=True, exist_ok=True)
    ev_data = {
        "user_provided_fields": ["components.water_tank.material_id"],
        "rag_completed_fields": {
            "sources.primary.energy": {"reason": "From physics manual"},
        },
        "assumptions": ["Standard temperature assumed"],
        "missing_information": ["Beam profile not specified"],
    }
    ev_path.write_text(json.dumps(ev_data), encoding="utf-8")
    return str(ev_path)


@pytest.fixture
def patch_get_job_dir(temp_job_dir, monkeypatch):
    """Monkeypatch get_job_dir to return temp_job_dir for test-job-123."""

    def _mock(job_id: str) -> Path:
        return temp_job_dir

    monkeypatch.setattr("agent_core.human_confirmation.nodes.get_job_dir", _mock)
    return _mock


@pytest.fixture
def base_state(temp_job_dir, sample_model_ir, sample_evidence_map, patch_get_job_dir):
    """Create base state for testing."""
    return HumanConfirmationState(
        job_id="test-job-123",
        user_query="Test query",
        g4_model_ir_path=sample_model_ir,
        evidence_map_path=sample_evidence_map,
        confirmation_status="pending",
    )


class TestJsonUtilities:
    """Test JSON utility functions."""

    def test_save_and_load_json(self, tmp_path):
        """Test _save_json and _load_json roundtrip."""
        test_file = tmp_path / "test.json"
        data = {"key": "value", "number": 123}
        _save_json(data, test_file)
        loaded = _load_json(test_file)
        assert loaded == data

    def test_load_json_missing_file(self, tmp_path):
        """Test _load_json returns None for missing file."""
        result = _load_json(tmp_path / "nonexistent.json")
        assert result is None


class TestGetConfirmationDir:
    """Test _get_confirmation_dir function."""

    def test_get_confirmation_dir_creates_directory(self, tmp_path, monkeypatch):
        """Test that _get_confirmation_dir creates the directory."""

        # Mock get_job_dir to return our temp path
        def mock_get_job_dir(job_id):
            return tmp_path / "jobs" / job_id

        monkeypatch.setattr("agent_core.human_confirmation.nodes.get_job_dir", mock_get_job_dir)

        conf_dir = _get_confirmation_dir("test-job-123")
        assert conf_dir.exists()
        assert conf_dir.name == STAGE_HUMAN_CONFIRMATION


class TestBuildProposedModelCompletion:
    """Test build_proposed_model_completion node."""

    @pytest.mark.asyncio
    async def test_build_proposed_model_completion(self, base_state, temp_job_dir):
        """Test building proposed model completion."""
        result = await build_proposed_model_completion(base_state)

        assert "proposed_model_completion_path" in result
        assert "requires_human_confirmation" in result

        # Check output file exists
        proposal_path = Path(result["proposed_model_completion_path"])
        assert proposal_path.exists()

        # Load and verify content
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        ProposedModelCompletion.model_validate(proposal)
        assert proposal["job_id"] == "test-job-123"
        assert "proposed_components" in proposal
        assert proposal["schema_version"] == "proposed_model_completion_v1"

    @pytest.mark.asyncio
    async def test_build_proposed_model_completion_preserves_context_missing_information(
        self, base_state, temp_job_dir
    ):
        """Nested context missing info must still be shown on the human review page."""
        evidence_path = Path(base_state["evidence_map_path"])
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence.pop("missing_information", None)
        evidence["user_context_requirements"] = {
            "missing_information": [
                "MOSFET gate oxide thickness was not specified.",
                "Irradiation dose rate was not specified.",
            ]
        }
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

        result = await build_proposed_model_completion(base_state)

        proposal = json.loads(
            Path(result["proposed_model_completion_path"]).read_text(encoding="utf-8")
        )
        assert proposal["requires_human_confirmation"] is True
        assert proposal["missing_information"] == [
            "MOSFET gate oxide thickness was not specified.",
            "Irradiation dose rate was not specified.",
        ]


class TestGenerateConfirmationRequest:
    """Test generate_confirmation_request node."""

    @pytest.mark.asyncio
    async def test_generate_confirmation_request(self, base_state, temp_job_dir):
        """Test generating confirmation request."""
        # First build the proposal
        await build_proposed_model_completion(base_state)

        result = await generate_confirmation_request(base_state)

        assert "confirmation_request_path" in result
        assert "human_confirmation_round" in result

        # Check output file exists
        request_path = Path(result["confirmation_request_path"])
        assert request_path.exists()

        # Load and verify content
        request = json.loads(request_path.read_text(encoding="utf-8"))
        ConfirmationRequest.model_validate(request)
        assert request["job_id"] == "test-job-123"
        assert request["round_id"] == 1
        assert "questions" in request

    @pytest.mark.asyncio
    async def test_generate_confirmation_request_prioritizes_geometry_and_codegen_impact(
        self, base_state, temp_job_dir
    ):
        """Geometry/placement assumptions must be explicit before Geant4 codegen."""
        await build_proposed_model_completion(base_state)

        result = await generate_confirmation_request(base_state)
        request = json.loads(Path(result["confirmation_request_path"]).read_text(encoding="utf-8"))
        question_paths = [q["field_path"] for q in request["questions"]]
        first_question = request["questions"][0]

        assert "components.water_tank.geometry" in question_paths
        assert first_question["field_path"] == "components.water_tank.geometry"
        assert first_question["category"] == "dimension"
        assert "Geant4" in first_question["impact"]
        assert "关键确认项" in request["summary_for_user"]
        assert request["critical_confirmations"][0]["field_path"] == (
            "components.water_tank.geometry"
        )
        assert request["agent_context"]["confirmation_focus"][0]["field_path"] == (
            "components.water_tank.geometry"
        )

    @pytest.mark.asyncio
    async def test_generate_confirmation_request_asks_about_missing_information_when_no_field_question_exists(
        self, base_state, temp_job_dir
    ):
        """A confirmation request must not be empty when the model filled defaults."""
        conf_dir = _get_confirmation_dir(base_state["job_id"])
        proposal_path = conf_dir / "proposed_model_completion.json"
        _save_json(
            {
                "schema_version": "proposed_model_completion_v1",
                "job_id": base_state["job_id"],
                "source_query": "Test query",
                "domain_profile": "geant4",
                "proposed_components": [],
                "proposed_sources": [],
                "proposed_scoring": [],
                "missing_information": ["Beam spot size was auto-filled from default."],
                "assumptions": ["Assumed a pencil beam because the user did not specify source shape."],
                "requires_human_confirmation": True,
                "readiness_status": "draft",
                "readiness_score": 0.4,
            },
            proposal_path,
        )

        result = await generate_confirmation_request(base_state)

        request = json.loads(Path(result["confirmation_request_path"]).read_text(encoding="utf-8"))
        assert request["questions"]
        assert request["questions"][0]["field_path"] == "missing_information.0"
        assert "Beam spot size" in request["questions"][0]["question"]
        assert request["critical_confirmations"]


class TestHumanInterruptNode:
    """Test human_interrupt_node function."""

    @pytest.mark.asyncio
    async def test_human_interrupt_without_response_returns_pending(self, base_state):
        """No raw_human_response must return pending, NOT approve."""
        # Ensure no raw_human_response
        base_state.pop("raw_human_response", None)
        # Set confirmation_request_path for interrupt_payload
        base_state["confirmation_request_path"] = "/fake/request.json"

        result = await human_interrupt_node(base_state)
        assert result["confirmation_status"] == "pending"
        assert result["human_confirmation_required"] is True
        assert result.get("raw_human_response", {}).get("user_decision") != "approve"

    @pytest.mark.asyncio
    async def test_human_interrupt_with_explicit_response_passes_through(self, base_state):
        """Explicit user response passes through."""
        base_state["raw_human_response"] = {
            "user_decision": "approve",
            "edits": [],
            "user_notes": "confirmed by test user",
        }
        result = await human_interrupt_node(base_state)
        assert result["confirmation_status"] == "received"
        assert result["raw_human_response"]["user_decision"] == "approve"


class TestParseConfirmationResponse:
    """Test parse_confirmation_response node."""

    @pytest.mark.asyncio
    async def test_parse_confirmation_response_approve(self, base_state, temp_job_dir):
        """Test parsing an approve response."""
        # First build proposal and request
        await build_proposed_model_completion(base_state)
        await generate_confirmation_request(base_state)

        # Set raw response
        base_state["raw_human_response"] = {
            "user_decision": "approve",
            "edits": [],
            "user_notes": "Approved",
        }

        result = await parse_confirmation_response(base_state)

        assert result["user_decision"] == "approve"
        assert "confirmation_response_path" in result

        # Check output file exists
        response_path = Path(result["confirmation_response_path"])
        assert response_path.exists()
        ConfirmationResponse.model_validate_json(response_path.read_text(encoding="utf-8"))

    @pytest.mark.asyncio
    async def test_parse_confirmation_response_edit(self, base_state, temp_job_dir):
        """Test parsing an edit response."""
        await build_proposed_model_completion(base_state)
        await generate_confirmation_request(base_state)

        base_state["raw_human_response"] = {
            "user_decision": "edit",
            "edits": [
                {
                    "field_path": "sources.primary.energy",
                    "new_value": 200.0,
                    "unit": "MeV",
                }
            ],
            "user_notes": "Changed energy",
        }

        result = await parse_confirmation_response(base_state)

        assert result["user_decision"] == "edit"
        assert result["total_edits"] == 1

    @pytest.mark.asyncio
    async def test_parse_confirmation_response_reject(self, base_state, temp_job_dir):
        """Test parsing a reject response."""
        await build_proposed_model_completion(base_state)
        await generate_confirmation_request(base_state)

        base_state["raw_human_response"] = {
            "user_decision": "reject",
            "edits": [],
            "user_notes": "Not suitable",
        }

        result = await parse_confirmation_response(base_state)

        assert result["user_decision"] == "reject"


class TestMergeUserConfirmation:
    """Test merge_user_confirmation node."""

    @pytest.mark.asyncio
    async def test_merge_user_confirmation_approve(self, base_state, temp_job_dir):
        """Test merging an approve decision."""
        # Setup: build proposal, request, and response
        await build_proposed_model_completion(base_state)
        await generate_confirmation_request(base_state)
        base_state["raw_human_response"] = {
            "user_decision": "approve",
            "edits": [],
            "user_notes": "Approved",
        }
        await parse_confirmation_response(base_state)

        result = await merge_user_confirmation(base_state)

        assert result["confirmation_status"] == "approved"
        assert "confirmation_record_path" in result
        assert "confirmed_model_plan_path" in result

        # Check files exist
        assert Path(result["confirmation_record_path"]).exists()
        assert Path(result["confirmed_model_plan_path"]).exists()
        ConfirmationRecord.model_validate_json(
            Path(result["confirmation_record_path"]).read_text(encoding="utf-8")
        )
        confirmed_plan = json.loads(
            Path(result["confirmed_model_plan_path"]).read_text(encoding="utf-8")
        )
        record = json.loads(Path(result["confirmation_record_path"]).read_text(encoding="utf-8"))
        assert confirmed_plan["agent_context"]["confirmed_constraints"]
        assert any(
            item["field_path"] == "components.water_tank.geometry"
            for item in confirmed_plan["agent_context"]["confirmed_constraints"]
        )
        assert record["agent_context"]["confirmed_constraint_count"] >= 1

    @pytest.mark.asyncio
    async def test_merge_user_confirmation_edit(self, base_state, temp_job_dir):
        """Test merging an edit decision."""
        await build_proposed_model_completion(base_state)
        await generate_confirmation_request(base_state)
        # Edit a source field which is processed as a parameter
        base_state["raw_human_response"] = {
            "user_decision": "edit",
            "edits": [
                {
                    "field_path": "sources.primary.energy",
                    "new_value": "200 MeV",
                }
            ],
            "user_notes": "Changed energy",
        }
        await parse_confirmation_response(base_state)

        result = await merge_user_confirmation(base_state)

        assert result["confirmation_status"] == "edited"
        assert result["edited_fields_count"] == 1
        confirmed_plan = json.loads(
            Path(result["confirmed_model_plan_path"]).read_text(encoding="utf-8")
        )
        constraints = confirmed_plan["agent_context"]["confirmed_constraints"]
        edited_constraint = next(
            item for item in constraints if item["field_path"] == "sources.primary.energy"
        )
        assert edited_constraint["value"] == "200 MeV"
        assert edited_constraint["status"] == "edited"
        assert edited_constraint["priority"] == "human_confirmed_hard"
        assert edited_constraint["source"] == "human_confirmation"
        assert edited_constraint["edited"] is True
        assert "edited constraints override" in confirmed_plan["agent_context"][
            "codegen_instruction"
        ].lower()

    @pytest.mark.asyncio
    async def test_merge_user_confirmation_reject(self, base_state, temp_job_dir):
        """Test merging a reject decision."""
        await build_proposed_model_completion(base_state)
        await generate_confirmation_request(base_state)
        base_state["raw_human_response"] = {
            "user_decision": "reject",
            "edits": [],
            "user_notes": "Rejected",
        }
        await parse_confirmation_response(base_state)

        result = await merge_user_confirmation(base_state)

        assert result["confirmation_status"] == "rejected"


class TestValidateConfirmationCompleteness:
    """Test validate_confirmation_completeness node."""

    @pytest.mark.asyncio
    async def test_validate_confirmation_completeness_pass(self, base_state, temp_job_dir):
        """Test validation passes with all confirmed."""
        # Setup complete approved flow
        await build_proposed_model_completion(base_state)
        await generate_confirmation_request(base_state)
        base_state["raw_human_response"] = {
            "user_decision": "approve",
            "edits": [],
        }
        await parse_confirmation_response(base_state)
        await merge_user_confirmation(base_state)

        result = await validate_confirmation_completeness(base_state)

        assert result["validation_passed"] is True
        assert result["confirmation_status"] == "approved"

    @pytest.mark.asyncio
    async def test_validate_confirmation_completeness_pending(self, base_state, temp_job_dir):
        """Test validation returns pending for unconfirmed items."""
        # Build plan with unconfirmed items
        await build_proposed_model_completion(base_state)
        await generate_confirmation_request(base_state)
        base_state["raw_human_response"] = {
            "user_decision": "ask_more",
            "edits": [],
        }
        await parse_confirmation_response(base_state)
        await merge_user_confirmation(base_state)

        result = await validate_confirmation_completeness(base_state)

        assert result["validation_passed"] is False
        assert result["confirmation_status"] == "ask_more"
