"""P0-7: static scanner rejects G4Box fallback markers."""

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


def test_rejects_g4box_fallback():
    result = scan_generated_code(
        _patch('auto box = new G4Box("fallback_geometry", 1, 1, 1);\n'), "test"
    )
    assert result["status"] == "fail"
    assert any(f["issue"] == "g4box_fallback" for f in result["findings"])


def test_rejects_fallback_g4box():
    result = scan_generated_code(_patch("// fallback G4Box used\n"), "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "g4box_fallback" for f in result["findings"])
