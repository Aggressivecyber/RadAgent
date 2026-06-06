"""Unit tests for validators."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent_core.validators.patch_validator import PatchValidator
from agent_core.validators.physics_sanity_validator import PhysicsSanityValidator
from agent_core.validators.schema_validator import SchemaValidator


class TestSchemaValidator:
    """Tests for TaskSpec and SimulationIR schema validation."""

    def setup_method(self):
        self.validator = SchemaValidator()

    def test_valid_task_spec(self):
        """Valid task spec should pass validation."""
        data = {
            "simulation_scope": ["geant4"],
            "particle": {
                "type": "proton",
                "energy_MeV": 10.0,
                "direction": [0.0, 0.0, 1.0],
                "events": 1000,
            },
            "target": {"material": "Si", "size_um": [1000.0, 1000.0, 300.0]},
            "outputs": ["dose_map"],
        }
        is_valid, errors = self.validator.validate_task_spec(data)
        assert is_valid, f"Expected valid, got errors: {errors}"

    def test_invalid_task_spec_missing_scope(self):
        """Task spec without simulation_scope should fail."""
        data = {"outputs": ["dose_map"]}
        is_valid, errors = self.validator.validate_task_spec(data)
        assert not is_valid
        assert any("scope" in e.lower() or "simulation_scope" in e for e in errors)

    def test_invalid_task_spec_bad_output(self):
        """Task spec with unknown output type should fail."""
        data = {
            "simulation_scope": ["geant4"],
            "outputs": ["not_a_real_output"],
        }
        is_valid, errors = self.validator.validate_task_spec(data)
        assert not is_valid

    def test_valid_simulation_ir(self):
        """Valid simulation IR should pass validation."""
        data = {
            "simulation_id": "job_test",
            "task_spec_hash": "abc123",
            "g4_config": {
                "geometry": {"target_material": "Si"},
                "particle_source": {"type": "proton"},
                "scoring": {"edep": True},
                "run_config": {"threads": 1},
            },
        }
        is_valid, errors = self.validator.validate_simulation_ir(data)
        assert is_valid, f"Expected valid, got errors: {errors}"

    def test_invalid_simulation_ir_missing_id(self):
        """Simulation IR without simulation_id should fail."""
        data = {"task_spec_hash": "abc123"}
        is_valid, errors = self.validator.validate_simulation_ir(data)
        assert not is_valid


class TestPatchValidator:
    """Tests for patch format validation."""

    def setup_method(self):
        self.validator = PatchValidator()

    def test_valid_patch(self):
        """Valid patch should pass format validation."""
        patch = {
            "patch_id": "test-123",
            "job_id": "job-1",
            "description": "Test patch",
            "change_type": "create",
            "risk_level": "low",
            "changed_files": [
                {
                    "path": "test.cc",
                    "diff_content": "",
                    "zone": "green",
                    "new_content": "int main() {}",
                }
            ],
            "test_plan": ["test_1"],
            "expected_outputs": ["output.csv"],
        }
        is_valid, errors = self.validator.validate_patch_format(patch)
        assert is_valid, f"Expected valid, got errors: {errors}"

    def test_invalid_patch_missing_fields(self):
        """Patch missing required fields should fail."""
        patch = {"patch_id": "test-123"}
        is_valid, errors = self.validator.validate_patch_format(patch)
        assert not is_valid

    def test_valid_unified_diff(self):
        """Valid unified diff should pass syntax check."""
        diff = """--- a/test.cc
+++ b/test.cc
@@ -1,3 +1,4 @@
 int main() {
+    return 0;
 }
"""
        is_valid, error = self.validator.validate_diff_syntax(diff)
        assert is_valid, f"Expected valid diff, got: {error}"


class TestPhysicsSanityValidator:
    """Tests for physics sanity checks."""

    def setup_method(self):
        self.validator = PhysicsSanityValidator()

    def test_valid_energy_deposition(self):
        """Non-negative energy values should pass."""
        data = [
            {"x": 0, "y": 0, "z": 0, "edep": 1.5},
            {"x": 1, "y": 0, "z": 0, "edep": 0.0},
        ]
        is_valid, errors = self.validator.validate_energy_deposition(data)
        assert is_valid

    def test_negative_energy_fails(self):
        """Negative energy values should fail."""
        data = [{"edep": -1.0}]
        is_valid, errors = self.validator.validate_energy_deposition(data)
        assert not is_valid

    def test_nan_energy_fails(self):
        """NaN energy values should fail."""
        data = [{"edep": float("nan")}]
        is_valid, errors = self.validator.validate_energy_deposition(data)
        assert not is_valid

    def test_valid_time_series(self):
        """Monotonically increasing time should pass."""
        data = [
            {"time": 0.0, "current": 0.0},
            {"time": 1.0, "current": 1.0},
            {"time": 2.0, "current": 0.5},
        ]
        is_valid, errors = self.validator.validate_time_series(data, "time", "current")
        assert is_valid

    def test_non_monotonic_time_fails(self):
        """Non-monotonic time should fail."""
        data = [
            {"time": 0.0, "current": 0.0},
            {"time": 2.0, "current": 1.0},
            {"time": 1.0, "current": 0.5},
        ]
        is_valid, errors = self.validator.validate_time_series(data, "time", "current")
        assert not is_valid
