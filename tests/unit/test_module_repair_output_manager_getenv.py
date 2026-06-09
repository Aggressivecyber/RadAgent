from __future__ import annotations

from agent_core.g4_codegen.repair.module_repair_loop import (
    _normalize_output_manager_getenv_literals,
)


def test_output_manager_repair_normalizes_g4_output_dir_getenv_literal() -> None:
    source = """#include "OutputManager.hh"
#include <cstdlib>

namespace {
const char* kEnvOutputDir = "G4_OUTPUT_DIR";
}

OutputManager::OutputManager() {
    const char* envDir = std::getenv(kEnvOutputDir);
}
"""

    repaired = _normalize_output_manager_getenv_literals(source)

    assert 'std::getenv("G4_OUTPUT_DIR")' in repaired
    assert "std::getenv(kEnvOutputDir)" not in repaired
