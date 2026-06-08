"""Unit tests for no magic numbers in C++ code validator."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from agent_core.g4_modeling.validators.no_magic_number_validator import (
    NoMagicNumberValidator,
)


class TestNoMagicNumberValidator:
    """Test NoMagicNumberValidator on C++ code strings."""

    def test_code_with_declared_values_passes(self):
        code = (
            "double dx = 500.0; // from IR: world dx\n"
            "double dy = 500.0; // from IR: world dy\n"
            "double dz = 500.0; // from IR: world dz\n"
        )
        declared: set[float] = {500.0}
        validator = NoMagicNumberValidator()
        passed, errors = validator.validate_code(code, "test.cc", declared)
        assert passed, f"Errors: {errors}"

    def test_code_with_undeclared_magic_number_fails(self):
        code = "double density = 2.33; // g/cm3\ndouble thickness = 0.5; // mm — undeclared!\n"
        declared: set[float] = {2.33}
        validator = NoMagicNumberValidator()
        passed, errors = validator.validate_code(code, "test.cc", declared)
        assert not passed
        assert any("0.5" in e for e in errors)

    def test_integer_values_flagged(self):
        """Integer magic numbers should be flagged too."""
        code = "int max_events = 1000;\n"
        declared: set[float] = set()
        validator = NoMagicNumberValidator()
        passed, errors = validator.validate_code(code, "test.cc", declared)
        assert not passed

    def test_zero_and_one_not_flagged(self):
        """0.0 and 1.0 are common and should not be flagged."""
        code = "double x = 0.0;\ndouble scale = 1.0;\n"
        declared: set[float] = set()
        validator = NoMagicNumberValidator()
        passed, errors = validator.validate_code(code, "test.cc", declared)
        assert passed, f"Errors: {errors}"

    def test_empty_code_passes(self):
        validator = NoMagicNumberValidator()
        passed, errors = validator.validate_code("", "test.cc", set())
        assert passed

    def test_all_declared_passes(self):
        code = (
            'new G4Box("world", 5000.0, 5000.0, 5000.0);\n'
            'new G4Box("sensor", 100.0, 100.0, 10.0);\n'
        )
        declared: set[float] = {5000.0, 100.0, 10.0}
        validator = NoMagicNumberValidator()
        passed, errors = validator.validate_code(code, "test.cc", declared)
        assert passed, f"Errors: {errors}"
