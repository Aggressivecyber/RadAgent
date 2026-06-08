"""No magic number validator — Gate G4-G.

Scans generated C++ code for numeric literals not declared
in the G4ModelIR or config files.
"""

from __future__ import annotations

import re

# Pattern to detect numeric literals in C++ code
# Matches: integers (123), floats (1.5, 1.0e3), excluding 0 and 1
_NUMERIC_LITERAL = re.compile(
    r"(?<![a-zA-Z_])"  # Not preceded by identifier char
    r"(\d+\.?\d*(?:[eE][+-]?\d+)?)"
    r"(?![a-zA-Z_\d])"  # Not followed by identifier char
)


class NoMagicNumberValidator:
    """Validates generated C++ code has no unexplained numeric literals."""

    def validate_code(
        self,
        code: str,
        file_path: str,
        declared_values: set[float],
    ) -> tuple[bool, list[str]]:
        """Check a single C++ source file for magic numbers.

        Parameters:
            code: C++ source code content
            file_path: Path for error reporting
            declared_values: Set of numeric values declared in the IR/config

        Returns (passed, list_of_error_messages).
        """
        errors: list[str] = []
        lines = code.split("\n")

        for line_num, line in enumerate(lines, 1):
            # Skip comments and preprocessor directives
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("#") or stripped.startswith("/*"):
                continue
            if stripped.startswith("*"):  # Block comment continuation
                continue

            # Strip inline comments
            code_part = line.split("//")[0]

            for match in _NUMERIC_LITERAL.finditer(code_part):
                num_str = match.group(1)
                try:
                    value = float(num_str)
                except ValueError:
                    continue

                # Allow 0, 1, -1 (common indices and flags)
                if value in (0.0, 1.0, -1.0):
                    continue

                # Allow values that are Geant4 unit macros (handled at compile time)
                # These are caught as identifiers, not raw numbers

                # Check if value is in declared IR values
                if not self._is_declared(value, declared_values):
                    # Check if the number appears in a comment or string
                    # (rough heuristic)
                    context = code_part[max(0, match.start() - 20) : match.end() + 20]
                    if '"' not in context and "'" not in context:
                        errors.append(
                            f"{file_path}:{line_num}: Magic number {num_str} "
                            f"not found in model IR or config"
                        )

        return len(errors) == 0, errors

    def validate_model_ir(
        self,
        model_ir_dict: dict,
    ) -> tuple[bool, list[str]]:
        """Extract all declared numeric values from the G4ModelIR.

        Returns a set of float values that are considered "declared"
        and may appear in generated code.
        """
        declared: set[float] = set()
        errors: list[str] = []

        # Extract dimensions from components
        components = model_ir_dict.get("components", [])
        for comp in components:
            dims = comp.get("dimensions", {})
            for val in dims.values():
                if isinstance(val, (int, float)):
                    declared.add(float(val))
            placement = comp.get("placement", {})
            for key in ("position", "rotation"):
                for val in placement.get(key, []):
                    if isinstance(val, (int, float)):
                        declared.add(float(val))

        # Extract material properties
        materials = model_ir_dict.get("materials", [])
        for mat in materials:
            density = mat.get("density_g_cm3")
            if density is not None:
                declared.add(float(density))

        # Extract source properties
        sources = model_ir_dict.get("sources", [])
        for src in sources:
            energy = src.get("energy", {})
            val = energy.get("value")
            if val is not None:
                declared.add(float(val))
            events = src.get("events")
            if events is not None:
                declared.add(float(events))

        # Extract scoring voxel sizes
        scoring_list = model_ir_dict.get("scoring", [])
        for sc in scoring_list:
            vg = sc.get("voxel_grid")
            if vg:
                for val in vg.get("voxel_size", []):
                    if isinstance(val, (int, float)):
                        declared.add(float(val))

        # Extract physics cuts
        physics = model_ir_dict.get("physics")
        if physics:
            cuts = physics.get("cuts")
            if cuts:
                for val in cuts.values():
                    if isinstance(val, (int, float)):
                        declared.add(float(val))

        return len(errors) == 0, errors

    @staticmethod
    def _is_declared(value: float, declared: set[float]) -> bool:
        """Check if a value matches a declared value (with tolerance)."""
        tolerance = 1e-6
        for declared_val in declared:
            if abs(value - declared_val) < tolerance:
                return True
        return False
