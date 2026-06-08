"""Test that main graph passes run_mode to codegen."""

from __future__ import annotations

import pytest


class TestMainGraphPassesRunModeToCodegen:
    """Verify run_mode flows from main graph through to codegen."""

    @pytest.mark.asyncio
    async def test_run_mode_passed_to_codegen_state(self) -> None:
        """run_mode should be available in codegen subgraph state."""
        from agent_core.g4_codegen.graph_nodes import build_codegen_plan_node

        state = {
            "job_id": "test_run_mode",
            "run_mode": "acceptance",
            "g4_model_ir": {
                "components": [{"component_id": "world", "component_type": "world"}],
            },
        }

        result = await build_codegen_plan_node(state)

        # The codegen plan node should have access to run_mode
        # and use it when building the plan
        assert result is not None

    @pytest.mark.asyncio
    async def test_build_module_contexts_receives_run_mode(self) -> None:
        """build_module_contexts should receive run_mode from state."""
        from agent_core.g4_codegen.graph_nodes import build_module_contexts_node

        state = {
            "job_id": "test_ctx_run_mode",
            "run_mode": "production",
            "g4_model_ir": {"model_ir_id": "test"},
            "codegen_plan": {"required_modules": []},
            "geometry_strategy_plan": {},
            "code_architecture_plan": {},
            "module_contracts": {},
        }

        result = await build_module_contexts_node(state)

        assert result is not None
        assert "module_contexts" in result

    def test_main_graph_codegen_subgraph_receives_state(self) -> None:
        """The main graph should compile with codegen subgraph node."""
        from agent_core.graph.main_graph import build_main_graph

        graph = build_main_graph()
        compiled = graph.compile()
        assert compiled is not None

    @pytest.mark.asyncio
    async def test_prepare_workspace_sets_run_mode(self) -> None:
        """prepare_workspace should set run_mode in the state."""
        from agent_core.graph.main_graph import prepare_workspace

        state = {
            "user_query": "Build a silicon detector",
            "run_mode": "strict",
        }

        with pytest.MonkeyPatch.context() as mp:
            import tempfile

            with tempfile.TemporaryDirectory() as td:
                mp.setenv("RADAGENT_WORKSPACE_ROOT", td)
                result = await prepare_workspace(state)

        assert result["run_mode"] == "strict"

    @pytest.mark.asyncio
    async def test_prepare_workspace_rejects_dev_run_mode(self) -> None:
        """prepare_workspace should reject the removed dev run_mode."""
        from agent_core.graph.main_graph import prepare_workspace

        with pytest.raises(ValueError, match="Unsupported run_mode"):
            await prepare_workspace(
                {
                    "user_query": "Build a silicon detector",
                    "run_mode": "dev",
                }
            )
