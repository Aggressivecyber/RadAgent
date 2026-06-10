from __future__ import annotations

from pathlib import Path

from agent_core.g4_codegen.example_lookup import build_geant4_example_manifest
from knowledge_base.geant4.paths import geant4_example_root


def test_geant4_example_root_uses_environment_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    examples_root = tmp_path / "geant4" / "examples"
    (examples_root / "basic" / "B2").mkdir(parents=True)
    monkeypatch.setenv("RADAGENT_GEANT4_EXAMPLES_ROOT", str(examples_root))

    assert geant4_example_root() == examples_root


def test_example_lookup_manifest_uses_configured_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    examples_root = tmp_path / "geant4" / "examples"
    b2b_root = examples_root / "basic" / "B2" / "B2b"
    b2b_root.mkdir(parents=True)
    (b2b_root / "exampleB2b.cc").write_text("int main() { return 0; }\n", encoding="utf-8")
    monkeypatch.setenv("RADAGENT_GEANT4_EXAMPLES_ROOT", str(examples_root))

    manifest = build_geant4_example_manifest()

    assert manifest["status"] == "available"
    assert manifest["examples_root"] == str(examples_root)
    assert "exampleB2b.cc" in manifest["examples"]["B2b"]
