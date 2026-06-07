"""Architecture invariant tests for the subgraph refactoring.

These tests verify the structural constraints specified in the
refactoring requirements.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_CORE = PROJECT_ROOT / "agent_core"


class TestNoOldMonolith:
    """Old monolithic graph_builder.py must NOT exist."""

    def test_no_old_graph_builder(self) -> None:
        assert not (AGENT_CORE / "graph" / "graph_builder.py").exists(), (
            "Old graph_builder.py must be deleted"
        )

    def test_no_old_graph_state(self) -> None:
        assert not (AGENT_CORE / "graph" / "state.py").exists(), "Old state.py must be deleted"

    def test_no_old_routes(self) -> None:
        assert not (AGENT_CORE / "graph" / "routes.py").exists(), "Old routes.py must be deleted"


class TestNoOldFanOut:
    """Old fan-out RAG retrieval must NOT exist."""

    def test_no_retrieve_g4_context(self) -> None:
        nodes_dir = AGENT_CORE / "nodes"
        if nodes_dir.exists():
            assert not (nodes_dir / "retrieve_g4_context.py").exists()
        # Should not exist anywhere
        for p in AGENT_CORE.rglob("retrieve_g4_context.py"):
            pytest.fail(f"Old file found: {p}")

    def test_no_retrieve_tcad_context(self) -> None:
        for p in AGENT_CORE.rglob("retrieve_tcad_context.py"):
            pytest.fail(f"Old file found: {p}")

    def test_no_retrieve_spice_context(self) -> None:
        for p in AGENT_CORE.rglob("retrieve_spice_context.py"):
            pytest.fail(f"Old file found: {p}")


class TestNoOldNaming:
    """Old g4rag/tcadrag/spicerag naming must NOT be used."""

    def test_no_g4rag_references(self) -> None:
        """No Python file should reference 'g4rag' as a module."""
        for py_file in AGENT_CORE.rglob("*.py"):
            content = py_file.read_text(errors="replace")
            assert "g4rag" not in content, f"g4rag found in {py_file}"

    def test_no_tcadrag_references(self) -> None:
        for py_file in AGENT_CORE.rglob("*.py"):
            content = py_file.read_text(errors="replace")
            assert "tcadrag" not in content, f"tcadrag found in {py_file}"

    def test_no_spicerag_references(self) -> None:
        for py_file in AGENT_CORE.rglob("*.py"):
            content = py_file.read_text(errors="replace")
            assert "spicerag" not in content, f"spicerag found in {py_file}"


class TestSubgraphDirectoryStructure:
    """Verify subgraph directory structure exists."""

    REQUIRED_SUBGRAPHS = [
        "context_graph.py",
        "task_planning_graph.py",
        "g4_modeling_graph.py",
        "g4_codegen_graph.py",
        "patch_graph.py",
        "gate_validation_graph.py",
        "artifact_graph.py",
        "report_graph.py",
    ]

    def test_subgraphs_dir_exists(self) -> None:
        assert (AGENT_CORE / "graph" / "subgraphs").is_dir()

    @pytest.mark.parametrize("subgraph_file", REQUIRED_SUBGRAPHS)
    def test_subgraph_file_exists(self, subgraph_file: str) -> None:
        path = AGENT_CORE / "graph" / "subgraphs" / subgraph_file
        assert path.exists(), f"Missing subgraph: {subgraph_file}"


class TestModuleDirectoryStructure:
    """Verify each subgraph has its own module directory."""

    REQUIRED_MODULES = [
        "context",
        "planning",
        "g4_modeling",
        "g4_codegen",
        "patching",
        "gates",
        "artifacts",
        "reports",
    ]

    @pytest.mark.parametrize("module", REQUIRED_MODULES)
    def test_module_dir_exists(self, module: str) -> None:
        mod_dir = AGENT_CORE / module
        assert mod_dir.is_dir(), f"Missing module dir: {module}"
        assert (mod_dir / "__init__.py").exists(), f"Missing __init__.py in {module}"


class TestMainStateIsPathBased:
    """Main state must reference data by paths, not inline."""

    def test_no_inline_g4_model_ir(self) -> None:
        from agent_core.graph.main_state import RadAgentMainState

        annotations = RadAgentMainState.__annotations__
        assert "g4_model_ir" not in annotations, (
            "g4_model_ir must NOT be inline in main state — use g4_model_ir_path"
        )
        assert "g4_model_ir_path" in annotations

    def test_no_inline_task_spec(self) -> None:
        from agent_core.graph.main_state import RadAgentMainState

        annotations = RadAgentMainState.__annotations__
        assert "task_spec" not in annotations, "task_spec must NOT be inline — use task_spec_path"

    def test_no_tcad_spice_fields(self) -> None:
        from agent_core.graph.main_state import RadAgentMainState

        annotations = RadAgentMainState.__annotations__
        for forbidden in [
            "tcad_context",
            "spice_context",
            "tcad_input_package",
            "spice_output_package",
        ]:
            assert forbidden not in annotations, f"Forbidden field: {forbidden}"


class TestNoSimulationWorkspaceInGit:
    """simulation_workspace/jobs must NOT be tracked in git."""

    def test_gitignore_blocks_jobs(self) -> None:
        gitignore = PROJECT_ROOT / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            # Must have some rule blocking simulation_workspace
            assert "simulation_workspace" in content, ".gitignore must block simulation_workspace"


class TestReviewArtifactsArchive:
    """Old MVP-1 artifacts must be archived, not in latest."""

    def test_old_mvp1_artifacts_archived(self) -> None:
        # Old mvp1_e2e should NOT be at top level
        mvp1_top = PROJECT_ROOT / "review_artifacts" / "mvp1_e2e"
        assert not mvp1_top.exists(), (
            "Old mvp1_e2e artifacts must be moved to review_artifacts/archive/"
        )

    def test_archive_exists(self) -> None:
        archive = PROJECT_ROOT / "review_artifacts" / "archive"
        assert archive.is_dir(), "review_artifacts/archive/ must exist"


class TestNoTrackedJobArtifacts:
    """No simulation_workspace/jobs should be in git tracking."""

    def test_no_tracked_jobs_dir(self) -> None:
        """simulation_workspace/ is fully gitignored."""
        gitignore = PROJECT_ROOT / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        # Must have a rule that blocks simulation_workspace
        assert "simulation_workspace/" in content, (
            ".gitignore must block simulation_workspace/ entirely"
        )
