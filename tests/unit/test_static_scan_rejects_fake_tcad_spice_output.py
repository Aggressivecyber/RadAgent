"""P0-7: static scanner rejects fake TCAD/SPICE output."""

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


def test_rejects_fake_tcad():
    result = scan_generated_code(_patch("// fake TCAD output\n"), "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "fake_tcad_output" for f in result["findings"])


def test_rejects_dummy_tcad():
    result = scan_generated_code(_patch("// dummy TCAD data\n"), "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "fake_tcad_output" for f in result["findings"])


def test_rejects_fake_spice():
    result = scan_generated_code(_patch("// fake SPICE output\n"), "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "fake_spice_output" for f in result["findings"])


def test_rejects_dummy_spice():
    result = scan_generated_code(_patch("// dummy SPICE data\n"), "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "fake_spice_output" for f in result["findings"])
