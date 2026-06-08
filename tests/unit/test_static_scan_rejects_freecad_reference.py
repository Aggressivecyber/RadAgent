"""P0-7: static scanner rejects FreeCAD references."""

from __future__ import annotations

from agent_core.g4_codegen.scanners.static_semantic_scanner import scan_generated_code


def test_rejects_freecad():
    patch = {
        "changed_files": [
            {
                "path": "src/Test.cc",
                "new_content": "// Use FreeCAD for geometry\n",
                "zone": "green",
                "module_name": "material",
                "generated_by": "m",
            }
        ]
    }
    result = scan_generated_code(patch, "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "freecad_reference" for f in result["findings"])
