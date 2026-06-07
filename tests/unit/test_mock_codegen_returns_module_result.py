"""Test that mock CODEGEN returns valid ModuleAgentResult structure."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult
from agent_core.models.gateway import reset_model_gateway


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_model_gateway()
    yield
    reset_model_gateway()


class TestMockCodegenReturnsModuleResult:
    """Verify that mocked CODEGEN returns valid ModuleAgentResult."""

    @pytest.mark.asyncio
    async def test_returns_valid_structure(self) -> None:
        """Mocked CODEGEN should produce a valid ModuleAgentResult."""
        mock_response = {
            "module_name": "geometry",
            "status": "generated",
            "generated_files": [
                {
                    "path": "src/DetectorConstruction.cc",
                    "operation": "create_or_replace",
                    "new_content": '#include "DetectorConstruction.hh"\nG4VPhysicalVolume* DetectorConstruction::Construct() { return nullptr; }\n',
                    "generated_by": "geometry_module_agent",
                    "module_name": "geometry",
                    "rationale": "Geant4 detector construction",
                    "dependencies": ["G4VUserDetectorConstruction"],
                    "satisfies": ["detector_construction"],
                    "risk_notes": [],
                    "used_references": [],
                },
                {
                    "path": "include/DetectorConstruction.hh",
                    "operation": "create_or_replace",
                    "new_content": "#pragma once\n#include <G4VUserDetectorConstruction.hh>\nclass DetectorConstruction : public G4VUserDetectorConstruction { public: G4VPhysicalVolume* Construct() override; };\n",
                    "generated_by": "geometry_module_agent",
                    "module_name": "geometry",
                    "rationale": "Detector header",
                    "dependencies": [],
                    "satisfies": ["detector_construction"],
                    "risk_notes": [],
                    "used_references": [],
                },
            ],
            "warnings": [],
            "errors": [],
        }

        with patch(
            "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw

            mock_result = AsyncMock()
            mock_result.error = None
            mock_result.content = '{"module_name": "geometry", "status": "generated"}'
            mock_result.parsed_json = mock_response
            mock_gw.call.return_value = mock_result

            result = await run_module_agent("geometry", {"module_name": "geometry"})

        assert isinstance(result, ModuleAgentResult)
        assert result.module_name == "geometry"
        assert result.status == "generated"
        assert len(result.generated_files) == 2

        # Verify file structure
        cc_file = result.generated_files[0]
        assert cc_file.path == "src/DetectorConstruction.cc"
        assert cc_file.new_content  # non-empty
        assert cc_file.generated_by == "geometry_module_agent"
        assert cc_file.module_name == "geometry"
