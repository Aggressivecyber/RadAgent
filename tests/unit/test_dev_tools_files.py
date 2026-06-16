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


async def test_search_geant4_docs_schema_and_dispatch_returns_rag_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from agent_core.dev_tools import DevToolkit

    class FakeResult:
        doc_id = "doc-1"
        title = "G4Allocator"
        content = "Use G4Allocator<Hit>::MallocSingle and FreeSingle for hit objects." * 20
        source = "geant4-docs"
        score = 0.875

    class FakeClient:
        def __init__(self) -> None:
            self.search_calls = []

        async def backend_available(self) -> bool:
            return True

        def index_ready(self) -> bool:
            return True

        async def search(self, query: str, *, top_k: int, min_score: float):
            self.search_calls.append((query, top_k, min_score))
            return [FakeResult()]

    fake_client = FakeClient()
    monkeypatch.setattr(
        "agent_core.dev_tools.geant4_docs.get_geant4_rag_client",
        lambda: fake_client,
    )

    toolkit = DevToolkit(tmp_path, tool_names=["search_geant4_docs"])
    schema_names = [schema["function"]["name"] for schema in toolkit.schemas]
    result = await toolkit.dispatch(
        "search_geant4_docs",
        {"query": "G4Allocator MallocSingle FreeSingle", "top_k": 3},
    )

    assert schema_names == ["search_geant4_docs"]
    assert result["ok"] is True
    assert result["results"][0]["title"] == "G4Allocator"
    assert result["results"][0]["score"] == 0.875
    assert result["results"][0]["content"] == FakeResult.content
    assert fake_client.search_calls == [("G4Allocator MallocSingle FreeSingle", 3, 0.0)]


async def test_search_geant4_docs_reports_unavailable_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from agent_core.dev_tools import DevToolkit

    class FakeClient:
        async def backend_available(self) -> bool:
            return False

        def index_ready(self) -> bool:
            return True

    fake_client = FakeClient()
    monkeypatch.setattr(
        "agent_core.dev_tools.geant4_docs.get_geant4_rag_client",
        lambda: fake_client,
    )

    toolkit = DevToolkit(tmp_path, tool_names=["search_geant4_docs"])
    result = await toolkit.dispatch("search_geant4_docs", {"query": "G4Box"})

    assert result["ok"] is False
    assert "unavailable" in result["error"]


async def test_search_web_schema_and_dispatch_returns_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from agent_core.dev_tools import DevToolkit

    class FakeWebResult:
        title = "Geant4 hits example"
        url = "https://example.org/geant4-hit"
        snippet = "Use a concrete hit class with G4THitsCollection." * 20
        source_type = "web"
        confidence = 0.42

    class FakeSearchTool:
        def __init__(self) -> None:
            self.search_available = True

        async def search(self, query: str, max_results: int = 5):
            assert query == "Geant4 G4THitsCollection Hit compile error"
            assert max_results == 4
            return [FakeWebResult()]

    monkeypatch.setattr(
        "agent_core.dev_tools.web_search.WebSearchTool",
        FakeSearchTool,
    )

    toolkit = DevToolkit(tmp_path, tool_names=["search_web"])
    schema_names = [schema["function"]["name"] for schema in toolkit.schemas]
    result = await toolkit.dispatch(
        "search_web",
        {"query": "Geant4 G4THitsCollection Hit compile error", "top_k": 4},
    )

    assert schema_names == ["search_web"]
    assert result["ok"] is True
    assert result["results"][0]["title"] == "Geant4 hits example"
    assert result["results"][0]["snippet"] == FakeWebResult.snippet
    assert result["results"][0]["url"] == "https://example.org/geant4-hit"


async def test_search_web_reports_unavailable_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from agent_core.dev_tools import DevToolkit

    class FakeSearchTool:
        search_available = False

    monkeypatch.setattr(
        "agent_core.dev_tools.web_search.WebSearchTool",
        FakeSearchTool,
    )

    toolkit = DevToolkit(tmp_path, tool_names=["search_web"])
    result = await toolkit.dispatch("search_web", {"query": "G4Allocator"})

    assert result["ok"] is False
    assert "unavailable" in result["error"]
