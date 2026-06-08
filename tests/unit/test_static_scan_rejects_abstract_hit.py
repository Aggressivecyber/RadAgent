"""P0-7: static scanner rejects abstract G4 base class instantiation."""

from __future__ import annotations

from agent_core.g4_codegen.scanners.static_semantic_scanner import scan_generated_code


def _patch_with_content(content: str) -> dict:
    return {
        "changed_files": [{
            "path": "src/Test.cc",
            "new_content": content,
            "zone": "green",
            "module_name": "material",
            "generated_by": "m",
        }],
    }


def test_rejects_new_g4vhit():
    result = scan_generated_code(_patch_with_content('auto hit = new G4VHit();\n'), "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "abstract_hit" for f in result["findings"])


def test_rejects_new_g4vsensitivedetector():
    result = scan_generated_code(_patch_with_content('auto sd = new G4VSensitiveDetector("sd");\n'), "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "abstract_sensitive_detector" for f in result["findings"])


def test_rejects_new_g4vuserdetectorconstruction():
    result = scan_generated_code(_patch_with_content('auto dc = new G4VUserDetectorConstruction();\n'), "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "abstract_detector_construction" for f in result["findings"])


def test_rejects_new_g4vuserprimarygeneratoraction():
    result = scan_generated_code(_patch_with_content('auto pg = new G4VUserPrimaryGeneratorAction();\n'), "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "abstract_primary_generator" for f in result["findings"])


def test_rejects_new_g4vuseractioninitialization():
    result = scan_generated_code(_patch_with_content('auto ai = new G4VUserActionInitialization();\n'), "test")
    assert result["status"] == "fail"
    assert any(f["issue"] == "abstract_action_initialization" for f in result["findings"])
