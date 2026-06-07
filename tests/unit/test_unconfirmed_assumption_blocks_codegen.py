"""Tests that unconfirmed assumptions block codegen."""



from agent_core.human_confirmation.validators import validate_human_confirmation


class TestUnconfirmedAssumptionBlocksCodegen:
    """Test that unconfirmed assumptions prevent formal codegen."""

    def test_unconfirmed_component_blocks_codegen(self):
        """Test that unconfirmed components block codegen."""
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
        assert "water_tank" in result.unconfirmed_components
        assert "Unconfirmed modeling assumptions" in result.errors[0]

    def test_unconfirmed_field_blocks_codegen(self):
        """Test that unconfirmed fields block codegen."""
        model_ir = {
            "components": [],
            "unconfirmed_fields": [
                "sources.primary.energy",
                "scoring.dose.quantity",
            ],
            "assumptions_confirmed": False,
        }
        result = validate_human_confirmation(model_ir)
        assert result.passed is False
        assert len(result.unconfirmed_fields) == 2

    def test_confirmed_model_passes(self):
        """Test that fully confirmed model passes validation."""
        model_ir = {
            "components": [
                {
                    "component_id": "water_tank",
                    "requires_confirmation": True,
                    "confirmed_by_user": True,
                },
                {
                    "component_id": "detector",
                    "requires_confirmation": False,
                },
            ],
            "unconfirmed_fields": [],
            "assumptions_confirmed": True,
        }
        result = validate_human_confirmation(model_ir)
        assert result.passed is True
        assert len(result.unconfirmed_components) == 0
        assert len(result.unconfirmed_fields) == 0

    def test_assumption_source_requires_confirmation(self):
        """Test that assumption-derived fields require confirmation."""
        model_ir = {
            "components": [
                {
                    "component_id": "shielding",
                    "requires_confirmation": True,
                    "confirmed_by_user": False,
                    "source_type": "assumption",
                }
            ],
            "assumptions_confirmed": False,
        }
        result = validate_human_confirmation(model_ir)
        assert result.passed is False
        assert "shielding" in result.unconfirmed_components

    def test_user_source_no_confirmation_needed(self):
        """Test that user-provided fields don't require confirmation."""
        model_ir = {
            "components": [
                {
                    "component_id": "target",
                    "requires_confirmation": False,
                    "confirmed_by_user": True,
                    "source_type": "user",
                }
            ],
            "unconfirmed_fields": [],
            "assumptions_confirmed": True,
        }
        result = validate_human_confirmation(model_ir)
        assert result.passed is True
        assert len(result.unconfirmed_components) == 0

    def test_low_confidence_requires_confirmation(self):
        """Test that low confidence fields require confirmation."""
        model_ir = {
            "components": [
                {
                    "component_id": "low_conf_comp",
                    "requires_confirmation": True,
                    "confirmed_by_user": False,
                    "confidence": 0.5,
                }
            ],
            "assumptions_confirmed": False,
        }
        result = validate_human_confirmation(model_ir)
        assert result.passed is False
        assert "low_conf_comp" in result.unconfirmed_components

    def test_high_confidence_still_requires_confirmation(self):
        """Test that even high-confidence RAG fields require confirmation."""
        model_ir = {
            "components": [
                {
                    "component_id": "rag_comp",
                    "requires_confirmation": True,
                    "confirmed_by_user": False,
                    "confidence": 0.85,
                }
            ],
            "assumptions_confirmed": False,
        }
        result = validate_human_confirmation(model_ir)
        assert result.passed is False
        assert "rag_comp" in result.unconfirmed_components

    def test_mixed_confirmation_state(self):
        """Test model with mixed confirmation states."""
        model_ir = {
            "components": [
                {
                    "component_id": "confirmed_comp",
                    "requires_confirmation": True,
                    "confirmed_by_user": True,
                },
                {
                    "component_id": "unconfirmed_comp",
                    "requires_confirmation": True,
                    "confirmed_by_user": False,
                },
            ],
            "unconfirmed_fields": ["some.field"],
            "assumptions_confirmed": False,
        }
        result = validate_human_confirmation(model_ir)
        assert result.passed is False
        assert "unconfirmed_comp" in result.unconfirmed_components
        assert "some.field" in result.unconfirmed_fields
        assert "confirmed_comp" not in result.unconfirmed_components

    def test_no_confirmation_required_no_components(self):
        """Test validation with no components requiring confirmation."""
        model_ir = {
            "components": [],
            "unconfirmed_fields": [],
            "assumptions_confirmed": True,
        }
        result = validate_human_confirmation(model_ir)
        assert result.passed is True
        assert len(result.errors) == 0

    def test_warning_for_inconsistent_state(self):
        """Test warning when assumptions_confirmed=False but no unconfirmed items."""
        model_ir = {
            "components": [
                {
                    "component_id": "comp",
                    "requires_confirmation": True,
                    "confirmed_by_user": True,
                }
            ],
            "unconfirmed_fields": [],
            "assumptions_confirmed": False,
        }
        result = validate_human_confirmation(model_ir)
        assert result.passed is True
        assert len(result.warnings) == 1
        assert "assumptions_confirmed is False" in result.warnings[0]
