"""Tests for patch discipline: layout mapping, single-writer principle."""

from __future__ import annotations

from agent_core.nodes.write_code_patch import _map_to_geant4_layout


class TestGeant4LayoutMapping:
    """Test _map_to_geant4_layout maps bare filenames to proper src/include layout."""

    def test_cc_files_go_to_src(self) -> None:
        files = {
            "DetectorConstruction.cc": "// det",
            "PrimaryGeneratorAction.cc": "// pga",
        }
        result = _map_to_geant4_layout(files)
        paths = [f["path"] for f in result]
        assert "05_geant4/src/DetectorConstruction.cc" in paths
        assert "05_geant4/src/PrimaryGeneratorAction.cc" in paths

    def test_hh_files_go_to_include(self) -> None:
        files = {
            "DetectorConstruction.hh": "#pragma once",
            "VoxelScorer.hh": "#pragma once",
        }
        result = _map_to_geant4_layout(files)
        paths = [f["path"] for f in result]
        assert "05_geant4/include/DetectorConstruction.hh" in paths
        assert "05_geant4/include/VoxelScorer.hh" in paths

    def test_main_cc_stays_at_root(self) -> None:
        files = {"geant4_sim.cc": "int main() {}"}
        result = _map_to_geant4_layout(files)
        paths = [f["path"] for f in result]
        assert "05_geant4/geant4_sim.cc" in paths
        assert "05_geant4/src/geant4_sim.cc" not in paths

    def test_cmakelists_stays_at_root(self) -> None:
        files = {"CMakeLists.txt": "cmake_minimum_required(...)"}
        result = _map_to_geant4_layout(files)
        assert result[0]["path"] == "05_geant4/CMakeLists.txt"

    def test_macro_files_go_to_macros(self) -> None:
        files = {"run.mac": "/run/beamOn 1000"}
        result = _map_to_geant4_layout(files)
        assert result[0]["path"] == "05_geant4/macros/run.mac"

    def test_unknown_extension_goes_to_root(self) -> None:
        files = {"README.md": "# Geant4 Sim"}
        result = _map_to_geant4_layout(files)
        assert result[0]["path"] == "05_geant4/README.md"

    def test_all_entries_have_green_zone(self) -> None:
        files = {
            "DetectorConstruction.cc": "// cc",
            "DetectorConstruction.hh": "// hh",
            "geant4_sim.cc": "// main",
            "CMakeLists.txt": "# cmake",
        }
        result = _map_to_geant4_layout(files)
        for entry in result:
            assert entry["zone"] == "green"
            assert "new_content" in entry
            assert "diff_content" in entry

    def test_empty_files_dict(self) -> None:
        result = _map_to_geant4_layout({})
        assert result == []
