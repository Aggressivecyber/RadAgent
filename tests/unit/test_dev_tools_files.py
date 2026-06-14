"""Tests for file-navigation tools used by agentic repair."""

from __future__ import annotations

from pathlib import Path


def test_list_files_returns_project_relative_matches(tmp_path: Path) -> None:
    from agent_core.dev_tools import DevToolkit

    (tmp_path / "include").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "include" / "SensitiveDetector.hh").write_text("// header\n")
    (tmp_path / "src" / "SensitiveDetector.cc").write_text("// source\n")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "noise.o").write_text("binary-ish\n")

    toolkit = DevToolkit(tmp_path, tool_names=["list_files"])
    result = toolkit._invoke_sync_for_test("list_files", {"glob": "**/*Detector*", "max_results": 10})

    assert result["ok"] is True
    assert result["matches"] == [
        "include/SensitiveDetector.hh",
        "src/SensitiveDetector.cc",
    ]


def test_search_text_returns_line_matches_without_build_noise(tmp_path: Path) -> None:
    from agent_core.dev_tools import DevToolkit

    (tmp_path / "include").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "build").mkdir()
    (tmp_path / "include" / "SensitiveDetector.hh").write_text(
        "class SensitiveDetector;\nclass ScoringManager;\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "DetectorConstruction.cc").write_text(
        "#include \"SensitiveDetector.hh\"\nvoid ConstructSDandField() {}\n",
        encoding="utf-8",
    )
    (tmp_path / "build" / "compile.log").write_text(
        "SensitiveDetector build artifact\n",
        encoding="utf-8",
    )

    toolkit = DevToolkit(tmp_path, tool_names=["search_text"])
    result = toolkit._invoke_sync_for_test(
        "search_text",
        {"pattern": "SensitiveDetector", "glob": "**/*", "max_results": 10},
    )

    assert result["ok"] is True
    assert [m["path"] for m in result["matches"]] == [
        "include/SensitiveDetector.hh",
        "src/DetectorConstruction.cc",
    ]
    assert result["matches"][0]["line"] == 1
    assert "build/compile.log" not in {m["path"] for m in result["matches"]}


def test_search_text_rejects_parent_traversal(tmp_path: Path) -> None:
    from agent_core.dev_tools import DevToolkit

    toolkit = DevToolkit(tmp_path, tool_names=["search_text"])
    result = toolkit._invoke_sync_for_test(
        "search_text",
        {"pattern": "secret", "glob": "../**/*"},
    )

    assert result["ok"] is False
    assert "escapes project root" in result["error"]
