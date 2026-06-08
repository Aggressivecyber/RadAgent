"""Tests for human_confirmation validators."""

from agent_core.human_confirmation.validators import (
    ConfirmationValidationResult,
    validate_human_confirmation,
)


class TestValidateHumanConfirmation:
    """Test validate_human_confirmation function."""

    def test_all_confirmed_pass(self):
        """Test validation passes when all components are confirmed."""
        model_ir = {
            "components": [
                {
                    "component_id": "water_tank",
                    "requires_confirmation": True,
                    "confirmed_by_user": True,
                }
            ],
            "assumptions_confirmed": True,
        }
        result = validate_human_confirmation(model_ir)
        assert result.passed is True
        assert len(result.errors) == 0
        assert len(result.unconfirmed_components) == 0

    def test_unconfirmed_component_fails(self):
        """Test validation fails with unconfirmed component."""
        model_ir = {
            "components": [
                {
                    "component_id": "water_tank",
                    "requires_confirmation": True,
                    "confirmed_by_user": False,
                }
            ],
            "assumptions_confirmed": False,
        }
        result = validate_human_confirmation(model_ir)
        assert result.passed is False
        assert len(result.errors) == 1
        assert "water_tank" in result.unconfirmed_components

    def test_unconfirmed_fields_fails(self):
        """Test validation fails with unconfirmed fields."""
        model_ir = {
            "components": [],
            "unconfirmed_fields": ["sources.primary.energy", "scoring.dose.quantity"],
            "assumptions_confirmed": False,
        }
        result = validate_human_confirmation(model_ir)
        assert result.passed is False
        assert len(result.unconfirmed_fields) == 2

    def test_assumptions_not_confirmed_warns(self):
        """Test warning when assumptions_confirmed is False but no specific items."""
        model_ir = {
            "components": [],
            "unconfirmed_fields": [],
            "assumptions_confirmed": False,
        }
        result = validate_human_confirmation(model_ir)
        assert result.passed is True
        assert len(result.warnings) == 1
        assert "assumptions_confirmed is False" in result.warnings[0]

    def test_empty_model_ir_passes(self):
        """Test validation passes with empty model IR."""
        model_ir = {"components": [], "assumptions_confirmed": True}
        result = validate_human_confirmation(model_ir)
        assert result.passed is True
        assert len(result.errors) == 0

    def test_multiple_unconfirmed(self):
        """Test validation with multiple unconfirmed items."""
        model_ir = {
            "components": [
                {
                    "component_id": "comp1",
                    "requires_confirmation": True,
                    "confirmed_by_user": False,
                },
                {
                    "component_id": "comp2",
                    "requires_confirmation": True,
                    "confirmed_by_user": False,
                },
            ],
            "unconfirmed_fields": ["field1", "field2"],
            "assumptions_confirmed": False,
        }
        result = validate_human_confirmation(model_ir)
        assert result.passed is False
        assert len(result.unconfirmed_components) == 2
        assert len(result.unconfirmed_fields) == 2
        assert len(result.errors) == 1


class TestConfirmationValidationResult:
    """Test ConfirmationValidationResult dataclass."""

    def test_validation_result_frozen(self):
        """Test that ValidationResult is immutable."""
        result = ConfirmationValidationResult(
            passed=False,
            errors=["error1"],
            warnings=["warn1"],
            unconfirmed_components=["comp1"],
            unconfirmed_fields=["field1"],
        )
        assert result.passed is False
        assert len(result.errors) == 1
        assert len(result.unconfirmed_components) == 1

    def test_validation_result_default_values(self):
        """Test ValidationResult with minimal arguments."""
        result = ConfirmationValidationResult(passed=True)
        assert result.passed is True
        assert result.errors == []
        assert result.warnings == []
        assert result.unconfirmed_components == []
        assert result.unconfirmed_fields == []
