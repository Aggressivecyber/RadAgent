"""P0-7: static scanner rejects CADMesh references."""

from __future__ import annotations

from agent_core.g4_codegen.scanners.static_semantic_scanner import scan_generated_code


def test_rejects_cadmesh():
    patch = {
        "changed_files": [
            {
                "path": "src/Test.cc",
                "new_content": '#include "CADMesh.hh"\n',
                "zone": "green",
                "module_name": "material",
                "generated_by": "m",
            }
        ]
    }
    result = scan_generated_code(patch, "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "cadmesh_reference" for f in result["findings"])


def test_rejects_cadmesh_lowercase():
    patch = {
        "changed_files": [
            {
                "path": "src/Test.cc",
                "new_content": "// using cadmesh library\n",
                "zone": "green",
                "module_name": "material",
                "generated_by": "m",
            }
        ]
    }
    result = scan_generated_code(patch, "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "cadmesh_reference" for f in result["findings"])
