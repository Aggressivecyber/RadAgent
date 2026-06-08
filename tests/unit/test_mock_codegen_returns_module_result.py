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
                    "new_content": '#include "DetectorConstruction.hh"\nG4VPhysicalVolume* DetectorConstruction::Construct() { return nullptr; }\n',  # noqa: E501
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
                    "new_content": "#pragma once\n#include <G4VUserDetectorConstruction.hh>\nclass DetectorConstruction : public G4VUserDetectorConstruction { public: G4VPhysicalVolume* Construct() override; };\n",  # noqa: E501
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

    @pytest.mark.asyncio
    async def test_normalizes_top_level_files_to_generated_files(self) -> None:
        """Real providers may return top-level files; normalize into ModuleAgentResult."""
        mock_response = {
            "module_name": "material",
            "status": "generated",
            "files": [
                {
                    "path": "include/MaterialRegistry.hh",
                    "content": "#pragma once\nclass MaterialRegistry {};\n",
                    "generated_by": "material_module_agent",
                    "module_name": "material",
                    "rationale": "Material registry header",
                }
            ],
        }

        with patch(
            "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw

            mock_result = AsyncMock()
            mock_result.error = None
            mock_result.content = '{"module_name": "material", "status": "generated"}'
            mock_result.parsed_json = mock_response
            mock_gw.call.return_value = mock_result

            result = await run_module_agent("material", {"module_name": "material"})

        assert result.status == "generated"
        assert len(result.generated_files) == 1
        assert result.generated_files[0].new_content.startswith("#pragma once")
        assert "content" not in result.generated_files[0].model_dump()

    @pytest.mark.asyncio
    async def test_normalizes_path_keyed_file_map(self) -> None:
        """Real providers may return a dict keyed by file path."""
        mock_response = {
            "include/PlacementManager.hh": {
                "content": "#pragma once\nclass PlacementManager {};\n",
                "rationale": "Placement manager header",
            },
            "src/PlacementManager.cc": '#include "PlacementManager.hh"\n',
        }

        with patch(
            "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw

            mock_result = AsyncMock()
            mock_result.error = None
            mock_result.content = "{}"
            mock_result.parsed_json = mock_response
            mock_gw.call.return_value = mock_result

            result = await run_module_agent("placement", {"module_name": "placement"})

        assert result.status == "generated"
        assert {f.path for f in result.generated_files} == {
            "include/PlacementManager.hh",
            "src/PlacementManager.cc",
        }
        for file_entry in result.generated_files:
            assert file_entry.generated_by == "placement_module_agent"
            assert file_entry.module_name == "placement"
            assert "content" not in file_entry.model_dump()

    @pytest.mark.asyncio
    async def test_normalizes_files_dict_and_file_path_entries(self) -> None:
        """Real providers may return files as a dict or use file_path."""
        mock_response = {
            "files": {
                "include/ScoringManager.hh": {
                    "content": "#pragma once\nclass ScoringManager {};\n",
                    "rationale": "Scoring header",
                },
                "src/ScoringManager.cc": {
                    "file_path": "src/ScoringManager.cc",
                    "content": '#include "ScoringManager.hh"\n',
                },
            }
        }

        with patch(
            "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw

            mock_result = AsyncMock()
            mock_result.error = None
            mock_result.content = "{}"
            mock_result.parsed_json = mock_response
            mock_gw.call.return_value = mock_result

            result = await run_module_agent("scoring", {"module_name": "scoring"})

        assert result.status == "generated"
        assert {f.path for f in result.generated_files} == {
            "include/ScoringManager.hh",
            "src/ScoringManager.cc",
        }

    @pytest.mark.asyncio
    async def test_normalizes_main_cmake_main_path_to_root(self) -> None:
        """main_cmake must place main.cc at the 08_geant4 root."""
        mock_response = {
            "files": [
                {
                    "path": "src/main.cc",
                    "new_content": "int main() { return 0; }\n",
                }
            ]
        }

        with patch(
            "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw

            mock_result = AsyncMock()
            mock_result.error = None
            mock_result.content = "{}"
            mock_result.parsed_json = mock_response
            mock_gw.call.return_value = mock_result

            result = await run_module_agent("main_cmake", {"module_name": "main_cmake"})

        assert [f.path for f in result.generated_files] == ["main.cc"]

    @pytest.mark.asyncio
    async def test_normalizes_snake_case_file_keys(self) -> None:
        """Providers may key files as scoring_manager_hh/scoring_manager_cc."""
        mock_response = {
            "scoring_manager_hh": "#pragma once\nclass ScoringManager {};\n",
            "scoring_manager_cc": '#include "ScoringManager.hh"\n',
        }

        with patch(
            "agent_core.g4_codegen.module_agents.base.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw

            mock_result = AsyncMock()
            mock_result.error = None
            mock_result.content = "{}"
            mock_result.parsed_json = mock_response
            mock_gw.call.return_value = mock_result

            result = await run_module_agent("scoring", {"module_name": "scoring"})

        assert {f.path for f in result.generated_files} == {
            "include/ScoringManager.hh",
            "src/ScoringManager.cc",
        }
