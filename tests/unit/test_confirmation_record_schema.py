"""Tests for ConfirmationRecord and related schemas."""

from agent_core.human_confirmation.schemas import (
    ConfirmationEdit,
    ConfirmationQuestion,
    ConfirmationRecord,
    ConfirmationRequest,
    ConfirmationResponse,
    ProposedComponent,
    ProposedModelCompletion,
    ProposedParameter,
)


class TestProposedParameter:
    """Test ProposedParameter schema."""

    def test_proposed_parameter_creation(self):
        """Test creating a ProposedParameter with all fields."""
        param = ProposedParameter(
            field_path="sources.primary.energy",
            proposed_value=10.0,
            unit="MeV",
            source_type="rag",
            source_ref="doc123",
            confidence=0.8,
            reason="Retrieved from physics manual",
            requires_confirmation=True,
        )
        assert param.field_path == "sources.primary.energy"
        assert param.proposed_value == 10.0
        assert param.unit == "MeV"
        assert param.source_type == "rag"
        assert param.confidence == 0.8
        assert param.requires_confirmation is True


class TestProposedComponent:
    """Test ProposedComponent schema."""

    def test_proposed_component_with_parameters(self):
        """Test creating a component with parameters."""
        params = [
            ProposedParameter(
                field_path="components.water_tank.material_id",
                proposed_value="G4_WATER",
                source_type="user",
                confidence=1.0,
                reason="User specified",
                requires_confirmation=False,
            )
        ]
        component = ProposedComponent(
            component_id="water_tank",
            component_type="volume",
            material_id="G4_WATER",
            geometry={"x": 10.0, "y": 10.0, "z": 10.0},
            placement={"position": [0, 0, 0]},
            roles=["target", "scoring_volume"],
            parameters=params,
            assumptions=["Standard temperature and pressure"],
            confidence=1.0,
            requires_confirmation=False,
        )
        assert component.component_id == "water_tank"
        assert len(component.parameters) == 1
        assert component.parameters[0].source_type == "user"


class TestProposedModelCompletion:
    """Test ProposedModelCompletion schema."""

    def test_proposed_model_completion(self):
        """Test creating a full model completion."""
        completion = ProposedModelCompletion(
            job_id="test-job-123",
            source_query="Simulate proton beam on water phantom",
            domain_profile="geant4",
            proposed_components=[],
            proposed_sources=[],
            proposed_scoring=[],
            missing_information=["Beam profile not specified"],
            assumptions=["Gaussian beam profile assumed"],
            requires_human_confirmation=True,
            readiness_score=0.7,
        )
        assert completion.job_id == "test-job-123"
        assert completion.requires_human_confirmation is True
        assert len(completion.assumptions) == 1


class TestConfirmationQuestion:
    """Test ConfirmationQuestion schema."""

    def test_confirmation_question_with_options(self):
        """Test creating a question with multiple choice options."""
        question = ConfirmationQuestion(
            question_id="q1",
            field_path="sources.primary.particle",
            question="Select particle type",
            proposed_value="proton",
            options=["proton", "electron", "gamma"],
            required=True,
            reason="Primary particle selection",
        )
        assert question.question_id == "q1"
        assert len(question.options) == 3
        assert question.required is True


class TestConfirmationRequest:
    """Test ConfirmationRequest schema."""

    def test_confirmation_request_with_questions(self):
        """Test creating a confirmation request with questions."""
        questions = [
            ConfirmationQuestion(
                question_id="q1",
                field_path="sources.primary.energy",
                question="Confirm beam energy",
                proposed_value="150 MeV",
                required=True,
            )
        ]
        request = ConfirmationRequest(
            job_id="test-job-123",
            round_id=1,
            summary_for_user="Please confirm the following parameters",
            questions=questions,
        )
        assert request.round_id == 1
        assert len(request.questions) == 1
        assert "approve" in request.approval_options


class TestConfirmationResponse:
    """Test ConfirmationResponse schema."""

    def test_confirmation_response_approve(self):
        """Test creating an approve response."""
        response = ConfirmationResponse(
            job_id="test-job-123",
            round_id=1,
            user_decision="approve",
            user_notes="Looks good",
        )
        assert response.user_decision == "approve"
        assert len(response.edits) == 0

    def test_confirmation_response_edit(self):
        """Test creating an edit response with edits."""
        edits = [
            ConfirmationEdit(
                field_path="sources.primary.energy",
                new_value=200.0,
                unit="MeV",
                reason="Higher energy needed",
            )
        ]
        response = ConfirmationResponse(
            job_id="test-job-123",
            round_id=1,
            user_decision="edit",
            edits=edits,
            user_notes="Changed beam energy",
        )
        assert response.user_decision == "edit"
        assert len(response.edits) == 1
        assert response.edits[0].new_value == 200.0

    def test_confirmation_response_reject(self):
        """Test creating a reject response."""
        response = ConfirmationResponse(
            job_id="test-job-123",
            round_id=1,
            user_decision="reject",
            user_notes="Approach not suitable",
        )
        assert response.user_decision == "reject"

    def test_confirmation_response_ask_more(self):
        """Test creating an ask_more response."""
        response = ConfirmationResponse(
            job_id="test-job-123",
            round_id=1,
            user_decision="ask_more",
            user_notes="Need more information",
        )
        assert response.user_decision == "ask_more"


class TestConfirmationRecord:
    """Test ConfirmationRecord schema."""

    def test_confirmation_record_approved(self):
        """Test creating an approved confirmation record."""
        record = ConfirmationRecord(
            job_id="test-job-123",
            total_rounds=1,
            final_status="approved",
            confirmed_fields=["sources.primary.energy"],
            confirmation_history=[{"round_id": 1, "user_decision": "approve"}],
            confirmed_model_plan_path="/path/to/plan.json",
        )
        assert record.final_status == "approved"
        assert record.total_rounds == 1

    def test_confirmation_record_with_history(self):
        """Test creating a record with confirmation history."""
        history = [
            {"round_id": 1, "user_decision": "ask_more", "edits": []},
            {"round_id": 2, "user_decision": "approve", "edits": []},
        ]
        record = ConfirmationRecord(
            job_id="test-job-123",
            total_rounds=2,
            final_status="approved",
            confirmation_history=history,
        )
        assert len(record.confirmation_history) == 2
        assert record.confirmation_history[0]["user_decision"] == "ask_more"

    def test_schema_serialization_roundtrip(self):
        """Test JSON serialization and deserialization roundtrip."""
        original = ConfirmationRequest(
            job_id="test-123",
            round_id=1,
            summary_for_user="Test summary",
            questions=[
                ConfirmationQuestion(
                    question_id="q1",
                    field_path="test.field",
                    question="Test question",
                    proposed_value="test_value",
                )
            ],
        )
        json_str = original.model_dump_json()
        parsed = ConfirmationRequest.model_validate_json(json_str)
        assert parsed.job_id == original.job_id
        assert len(parsed.questions) == len(original.questions)
