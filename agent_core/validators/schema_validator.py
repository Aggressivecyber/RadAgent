"""Schema validator for TaskSpec and SimulationIR using Pydantic models."""

from __future__ import annotations

from agent_core.schemas.simulation_ir import SimulationIR
from agent_core.schemas.task_spec import SimulationScope, TaskSpec


class SchemaValidator:
    """Validates raw dictionaries against Pydantic schema models.

    Provides per-schema validation methods plus a generic dispatcher.
    All methods return ``(is_valid, errors)`` tuples.
    """

    def __init__(self) -> None:
        self.errors: list[str] = []

    def _reset(self) -> None:
        """Clear accumulated errors."""
        self.errors = []

    def validate_task_spec(self, data: dict) -> tuple[bool, list[str]]:
        """Validate *data* against the TaskSpec schema.

        Checks that ``simulation_scope`` and ``outputs`` are present and
        that every field conforms to the Pydantic model constraints.

        Returns:
            ``(is_valid, errors)`` — *errors* is empty on success.
        """
        self._reset()
        try:
            TaskSpec.model_validate(data)
        except Exception as exc:
            self.errors = self._format_errors(exc)
        return (len(self.errors) == 0, list(self.errors))

    def validate_simulation_ir(self, data: dict) -> tuple[bool, list[str]]:
        """Validate *data* against the SimulationIR schema.

        Additionally ensures ``g4_config`` is present when the originating
        scope includes ``"geant4"``.

        Returns:
            ``(is_valid, errors)`` — *errors* is empty on success.
        """
        self._reset()
        try:
            SimulationIR.model_validate(data)
        except Exception as exc:
            self.errors = self._format_errors(exc)

        # Cross-field check: geant4 scope requires g4_config
        scope = data.get("simulation_scope", [])
        scope_values = {s.value if isinstance(s, SimulationScope) else s for s in scope}
        if "geant4" in scope_values and data.get("g4_config") is None:
            self.errors.append("g4_config is required when scope includes 'geant4'")

        return (len(self.errors) == 0, list(self.errors))

    def validate_json_schema(self, data: dict, schema_type: str) -> tuple[bool, list[str]]:
        """Dispatch to the correct validator based on *schema_type*.

        Args:
            data: Raw dictionary to validate.
            schema_type: Either ``"task_spec"`` or ``"simulation_ir"``.

        Returns:
            ``(is_valid, errors)`` — *errors* is empty on success.

        Raises:
            ValueError: If *schema_type* is not a recognised value.
        """
        dispatchers: dict[str, callable] = {
            "task_spec": self.validate_task_spec,
            "simulation_ir": self.validate_simulation_ir,
        }
        validator = dispatchers.get(schema_type)
        if validator is None:
            raise ValueError(
                f"Unknown schema_type '{schema_type}'. "
                f"Expected one of: {sorted(dispatchers)}"
            )
        return validator(data)

    @staticmethod
    def _format_errors(exc: Exception) -> list[str]:
        """Turn a Pydantic ValidationError into human-readable strings."""
        if hasattr(exc, "errors"):
            return [
                f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
                for e in exc.errors()
            ]
        return [str(exc)]
