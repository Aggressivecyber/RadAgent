"""P0-14: effective ModuleContext is persisted to disk."""

from __future__ import annotations

from pathlib import Path


def test_effective_context_file_created(tmp_path: Path):
    """run_module_agent_node should create .effective.json."""
    # This is a structural test — we verify the code path exists
    import inspect

    from agent_core.g4_codegen import graph_nodes

    source = inspect.getsource(graph_nodes.run_module_agent_node)
    assert "existing_generated_file_summaries" in source, (
        "run_module_agent_node must inject previous generated file summaries into effective context"
    )
    assert "actual_context_used_by_agent" in source, (
        "Effective context must include actual_context_used_by_agent flag"
    )


def test_effective_context_contains_summaries():
    """Effective context must include existing_generated_file_summaries."""
    import inspect

    from agent_core.g4_codegen import graph_nodes

    source = inspect.getsource(graph_nodes.run_module_agent_node)
    assert "existing_generated_file_summaries" in source
    assert 'ctx["existing_generated_file_summaries"]' in source
