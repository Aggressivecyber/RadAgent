"""Test that graph code does not import old nodes/integration_assembler."""

from __future__ import annotations

import ast
from pathlib import Path


class TestOldIntegrationAssemblerNotImportedByGraph:
    """Verify graph-related code does not import the old integration_assembler."""

    def _get_imports(self, filepath: Path) -> list[str]:
        """Parse a Python file and return all import targets."""
        try:
            tree = ast.parse(filepath.read_text())
        except SyntaxError:
            return []

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return imports

    def test_g4_codegen_graph_no_old_import(self) -> None:
        """g4_codegen_graph should not import old nodes/integration_assembler."""
        graph_file = Path("agent_core/graph/subgraphs/g4_codegen_graph.py")
        imports = self._get_imports(graph_file)

        for imp in imports:
            assert "g4_modeling.nodes.integration_assembler_node" not in imp, (
                f"g4_codegen_graph imports old integration_assembler_node: {imp}"
            )
            # The new integration assembler is at g4_codegen.integration.integration_assembler
            # which is fine
            assert "g4_modeling.nodes" not in imp or "integration_assembler" not in imp, (
                f"g4_codegen_graph imports old integration assembler: {imp}"
            )

    def test_main_graph_no_old_import(self) -> None:
        """main_graph should not import old nodes/integration_assembler."""
        graph_file = Path("agent_core/graph/main_graph.py")
        imports = self._get_imports(graph_file)

        for imp in imports:
            assert "g4_modeling.nodes.integration_assembler_node" not in imp, (
                f"main_graph imports old integration_assembler_node: {imp}"
            )

    def test_graph_nodes_uses_new_integration_assembler(self) -> None:
        """graph_nodes should import from new location."""
        graph_file = Path("agent_core/g4_codegen/graph_nodes.py")
        content = graph_file.read_text()

        # Should import from the new location
        assert "agent_core.g4_codegen.integration.integration_assembler" in content, (
            "graph_nodes should import from new integration_assembler location"
        )

    def test_no_old_imports_in_subgraph_directory(self) -> None:
        """No file in graph/subgraphs should import old integration_assembler."""
        subgraph_dir = Path("agent_core/graph/subgraphs")
        if not subgraph_dir.exists():
            return

        for py_file in subgraph_dir.glob("*.py"):
            imports = self._get_imports(py_file)
            for imp in imports:
                assert "g4_modeling.nodes.integration_assembler_node" not in imp, (
                    f"{py_file.name} imports old integration_assembler_node: {imp}"
                )
