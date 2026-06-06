"""Tests for RAG router — logical names only (geant4, tcad, spice)."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_core.tools.rag_router import RAGRouter


@pytest.fixture
def router():
    """Create RAG router with test policy."""
    policy_path = (
        Path(__file__).resolve().parent.parent.parent
        / "agent_core" / "policies" / "rag_policy.yaml"
    )
    return RAGRouter(str(policy_path))


class TestRAGRouterBasicRouting:
    """Test route() returns logical names with required/optional distinction."""

    def test_geant4_scope_returns_required_geant4(self, router) -> None:
        result = router.route({"simulation_scope": ["geant4"]})
        assert "geant4" in result["required"]
        assert "tcad" in result["optional"]
        assert "spice" in result["optional"]

    def test_tcad_scope_returns_required_tcad(self, router) -> None:
        result = router.route({"simulation_scope": ["tcad"]})
        assert "tcad" in result["required"]

    def test_spice_scope_returns_required_spice(self, router) -> None:
        result = router.route({"simulation_scope": ["spice"]})
        assert "spice" in result["required"]

    def test_multi_scope_geant4_tcad(self, router) -> None:
        result = router.route({"simulation_scope": ["geant4", "tcad"]})
        assert "geant4" in result["required"]
        assert "tcad" in result["required"]
        assert "spice" in result["optional"]

    def test_full_chain_all_three(self, router) -> None:
        result = router.route({"simulation_scope": ["geant4", "tcad", "spice"]})
        assert set(result["required"]) == {"geant4", "tcad", "spice"}

    def test_empty_scope_defaults_to_geant4(self, router) -> None:
        result = router.route({"simulation_scope": []})
        assert "geant4" in result["required"]

    def test_string_scope_converted_to_list(self, router) -> None:
        result = router.route({"simulation_scope": "geant4"})
        assert "geant4" in result["required"]

    def test_all_field_contains_required_plus_optional(self, router) -> None:
        result = router.route({"simulation_scope": ["geant4"]})
        assert set(result["all"]) == {"geant4", "tcad", "spice"}


class TestRAGRouterKeywordDetection:
    """Test keyword-based routing when scope is not specified."""

    def test_geant4_keyword_match(self, router) -> None:
        assert router._match_keywords("energy deposition in silicon", "geant4")
        assert router._match_keywords("Geant4 simulation", "geant4")
        assert router._match_keywords("G4 physics list", "geant4")

    def test_tcad_keyword_match(self, router) -> None:
        assert router._match_keywords("trap density in silicon", "tcad")
        assert router._match_keywords("TCAD device simulation", "tcad")
        assert router._match_keywords("radiation damage TID", "tcad")

    def test_spice_keyword_match(self, router) -> None:
        assert router._match_keywords("ngspice netlist", "spice")
        assert router._match_keywords("SPICE transient circuit", "spice")
        assert router._match_keywords("PWL current source", "spice")


class TestNoLegacyNames:
    """Ensure no g4rag/tcadrag/spicerag in any output."""

    def test_no_legacy_names_in_output(self, router) -> None:
        result = router.route({"simulation_scope": ["geant4", "tcad", "spice"]})
        all_names = result["required"] + result["optional"] + result["all"]
        assert "g4rag" not in all_names
        assert "tcadrag" not in all_names
        assert "spicerag" not in all_names

    def test_no_scope_map_in_module(self) -> None:
        """The _SCOPE_MAP constant should not exist anymore."""
        import agent_core.tools.rag_router as mod
        assert not hasattr(mod, "_SCOPE_MAP")
        assert not hasattr(mod, "_CHAIN_SOURCES")
