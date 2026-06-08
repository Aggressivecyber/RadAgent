"""P0-7: static scanner rejects CAD conversion claims."""

from __future__ import annotations

from agent_core.g4_codegen.scanners.static_semantic_scanner import scan_generated_code


def _patch(content: str) -> dict:
    return {
        "changed_files": [
            {
                "path": "src/Test.cc",
                "new_content": content,
                "zone": "green",
                "module_name": "material",
                "generated_by": "m",
            }
        ]
    }


def test_rejects_step_conversion():
    result = scan_generated_code(_patch("// Convert STEP file to geometry\n"), "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "step_conversion_claim" for f in result["findings"])


def test_rejects_stl_conversion():
    result = scan_generated_code(_patch("// STL convert to G4\n"), "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "stl_conversion_claim" for f in result["findings"])


def test_rejects_ply_conversion():
    result = scan_generated_code(_patch("// PLY convert to mesh\n"), "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "ply_conversion_claim" for f in result["findings"])
