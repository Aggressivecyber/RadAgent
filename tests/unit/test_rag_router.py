"""Unit tests for RAG router."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agent_core.tools.rag_router import RAGRouter


@pytest.fixture
def router():
    """Create RAG router with test policy."""
    policy_path = Path(__file__).resolve().parent.parent.parent / "agent_core" / "policies" / "rag_policy.yaml"
    return RAGRouter(str(policy_path))


class TestRAGRouter:
    """Tests for RAG routing logic."""

    def test_geant4_scope_routes_to_g4rag(self, router):
        """Geant4-only tasks should route to g4rag."""
        task_spec = {"simulation_scope": ["geant4"], "outputs": ["energy_deposition"]}
        result = router.route(task_spec)
        assert "g4rag" in result

    def test_tcad_scope_routes_to_tcadrag(self, router):
        """TCAD-only tasks should route to tcadrag."""
        task_spec = {"simulation_scope": ["tcad"], "outputs": ["IV curve"]}
        result = router.route(task_spec)
        assert "tcadrag" in result

    def test_spice_scope_routes_to_spicerag(self, router):
        """SPICE-only tasks should route to spicerag."""
        task_spec = {"simulation_scope": ["spice"], "outputs": ["transient circuit"]}
        result = router.route(task_spec)
        assert "spicerag" in result

    def test_multi_scope_routes_to_multiple(self, router):
        """Multi-scope tasks should route to multiple RAG sources."""
        task_spec = {"simulation_scope": ["geant4", "tcad"]}
        result = router.route(task_spec)
        assert "g4rag" in result
        assert "tcadrag" in result

    def test_full_chain_routes_to_all(self, router):
        """Full chain tasks should route to all three sources."""
        task_spec = {"simulation_scope": ["geant4", "tcad", "spice"]}
        result = router.route(task_spec)
        assert "g4rag" in result
        assert "tcadrag" in result
        assert "spicerag" in result

    def test_empty_scope_defaults_to_g4rag(self, router):
        """Empty scope should default to g4rag."""
        task_spec = {"simulation_scope": []}
        result = router.route(task_spec)
        assert "g4rag" in result

    def test_keyword_detection_geant4(self, router):
        """Geant4 keywords should be detected."""
        assert router._match_keywords("energy deposition in silicon", "geant4")
        assert router._match_keywords("Geant4 simulation", "geant4")
        assert router._match_keywords("G4 physics list", "geant4")

    def test_keyword_detection_tcad(self, router):
        """TCAD keywords should be detected."""
        assert router._match_keywords("trap density in silicon", "tcad")
        assert router._match_keywords("TCAD device simulation", "tcad")
        assert router._match_keywords("radiation damage TID", "tcad")

    def test_keyword_detection_spice(self, router):
        """SPICE keywords should be detected."""
        assert router._match_keywords("ngspice netlist", "spice")
        assert router._match_keywords("SPICE transient circuit", "spice")
        assert router._match_keywords("PWL current source", "spice")

    def test_scope_to_sources_mapping(self, router):
        """Scope names should map correctly to source names."""
        assert router._scope_to_sources(["geant4"]) == ["g4rag"]
        assert router._scope_to_sources(["tcad"]) == ["tcadrag"]
        assert router._scope_to_sources(["spice"]) == ["spicerag"]

    def test_fallback_sources(self, router):
        """Fallback should return g4rag."""
        fallback = router.get_fallback_sources()
        assert "g4rag" in fallback
