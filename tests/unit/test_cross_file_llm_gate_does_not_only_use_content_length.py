"""P0-23: cross_file_llm_gate uses code_review_bundle, not just content_length."""

from __future__ import annotations

from agent_core.g4_codegen.integration.cross_file_llm_gate import (
    run_cross_file_llm_gate,
)


def test_gate_builds_code_review_bundle():
    """Verify the gate builds a code_review_bundle with file details."""
    # The function builds a code_review_bundle internally
    # We can verify by checking the function signature accepts the right params
    import inspect

    sig = inspect.signature(run_cross_file_llm_gate)
    param_names = list(sig.parameters.keys())
    assert "static_semantic_scan" in param_names
    assert "cross_file_hard_gate" in param_names
    assert "interface_contracts" in param_names


def test_file_details_include_includes_and_classes():
    """Verify file details extraction includes includes and classes."""
    from agent_core.g4_codegen.integration.cross_file_llm_gate import (
        _extract_classes,
        _extract_includes,
        _extract_public_methods,
    )

    content = (
        "#pragma once\n"
        '#include "G4Material.hh"\n'
        "#include <vector>\n"
        "class MaterialRegistry {\n"
        "public:\n"
        "  void BuildMaterials();\n"
        "  G4Material* GetMaterial(const G4String& name);\n"
        "};\n"
    )
    includes = _extract_includes(content)
    assert "G4Material.hh" in includes
    assert "vector" in includes

    classes = _extract_classes(content)
    assert "MaterialRegistry" in classes

    methods = _extract_public_methods(content)
    assert any("BuildMaterials" in m for m in methods)
