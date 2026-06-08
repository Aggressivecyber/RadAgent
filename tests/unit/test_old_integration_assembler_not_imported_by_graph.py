"""Test that old nodes/integration_assembler is deprecated and not imported."""

from __future__ import annotations

import ast
from pathlib import Path


class TestOldIntegrationAssemblerDeleted:
    """P0-10/P0-11: Old integration_assembler must be deleted."""

    def test_old_assembler_deleted(self):
        old_path = Path("agent_core/g4_codegen/nodes/integration_assembler.py")
        assert not old_path.exists(), "Old integration_assembler.py must be deleted"


class TestOldIntegrationAssemblerNotImportedByGraph:
    """Verify graph-related code does not import the old integration_assembler."""

    def _get_imports(self, filepath: Path) -> list[str]:
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

    def test_g4_codegen_graph_no_old_import(self):
        graph_file = Path("agent_core/graph/subgraphs/g4_codegen_graph.py")
        imports = self._get_imports(graph_file)
        for imp in imports:
            assert "g4_codegen.nodes.integration_assembler" not in imp, (
                f"g4_codegen_graph imports old: {imp}"
            )

    def test_graph_nodes_no_old_import(self):
        graph_file = Path("agent_core/g4_codegen/graph_nodes.py")
        imports = self._get_imports(graph_file)
        for imp in imports:
            assert "g4_codegen.nodes.integration_assembler" not in imp, (
                f"graph_nodes imports old: {imp}"
            )

    def test_graph_nodes_uses_new_integration_assembler(self):
        graph_file = Path("agent_core/g4_codegen/graph_nodes.py")
        content = graph_file.read_text()
        assert "agent_core.g4_codegen.integration.integration_assembler" in content

    def test_no_old_imports_in_subgraph_directory(self):
        subgraph_dir = Path("agent_core/graph/subgraphs")
        if not subgraph_dir.exists():
            return
        for py_file in subgraph_dir.glob("*.py"):
            imports = self._get_imports(py_file)
            for imp in imports:
                assert "g4_codegen.nodes.integration_assembler" not in imp, (
                    f"{py_file.name} imports old: {imp}"
                )
